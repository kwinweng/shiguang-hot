"""博主分支单测：全部用 tests/fixtures/rebang/bloggers 下的真实节选样本，不联网。"""
import json
import os
from datetime import datetime
from pathlib import Path

import pytest

from rebang.bloggers import run as runmod
from rebang.bloggers.feed import FeedError, feed_posts
from rebang.bloggers.weibo import map_crawler_json
from rebang.bloggers.x import load_dump, x_posts
from rebang.contract.schema import load_bloggers, validate_item, validate_items_envelope
from rebang.translate import Cache, Translator
from rebang.translate.__main__ import main as translate_cli

FX = Path(__file__).parent / 'fixtures' / 'rebang' / 'bloggers'
NOW = datetime.fromisoformat('2026-11-15T21:00:00+08:00')
FEEDS = {
    'ruanyifeng': 'rss_wechat2rss.xml', 'reorx': 'rss_imtx.xml', 'tualatrix': 'rss_imtx.xml',
    'simonw': 'atom_simonw.xml', 'karpathy': 'rss_karpathy_atom.xml', 'emollick': 'rss_oneusefulthing.xml',
    'lilianweng': 'atom_simonw.xml',
}


def platform(pid):
    return next(p for p in load_bloggers()['platforms'] if p['id'] == pid)


def account(pid, handle):
    return next(a for a in platform(pid)['accounts'] if a['handle'] == handle)


def fake_http(fail=()):
    urls = {}
    for a in platform('blog')['accounts']:
        urls[a['feed']] = FEEDS[a['handle']]
    for a in platform('wechat')['accounts']:
        if a.get('feed'):
            urls[a['feed']] = 'rss_wechat2rss.xml'
    for root in platform('jike')['rsshub_mirrors']:
        for a in platform('jike')['accounts']:
            urls[f'{root}/jike/user/{a["handle"]}'] = 'rss_jike_rsshub.xml'
    calls = []

    def fetch(url):
        calls.append(url)
        if url in fail:
            raise FeedError('http_5xx')
        if url not in urls:
            raise AssertionError(f'unexpected network call {url}')
        return (FX / urls[url]).read_bytes()
    fetch.calls = calls
    return fetch


def opts(tmp_path, **kw):
    base = dict(x_dump=str(FX / 'x_dump'), pause=0, translator=Translator(engine='cache', cache=Cache(tmp_path / 'cache.json')))
    base.update(kw)
    return runmod.Options(**base)


def run_all(tmp_path, previous=None, http=None, **kw):
    now = kw.pop('now', NOW)
    return runmod.run(http=http or fake_http(), now=now, previous=previous, opts=opts(tmp_path, **kw), sleep=lambda s: None)


# ---------- 订阅源 ----------

def test_atom_feed_to_posts_has_real_fields():
    items = feed_posts((FX / 'atom_simonw.xml').read_bytes(), platform('blog'), account('blog', 'simonw'), NOW.isoformat())
    assert len(items) == 2
    for item in items:
        assert validate_item(item) == []
        assert item['kind'] == 'post' and item['channel'] is None
        assert item['lang'] == 'en' and item['title'] and item['url'].startswith('http')
        assert item['published_at'].endswith('+08:00')
        assert item['blogger']['platform'] == 'blog' and item['blogger']['display_name'] == 'Simon Willison'
    assert items[0]['published_at'] >= items[1]['published_at']


def test_rss_content_encoded_gives_body_and_images():
    items = feed_posts((FX / 'rss_oneusefulthing.xml').read_bytes(), platform('blog'), account('blog', 'emollick'), NOW.isoformat())
    assert items and all(validate_item(i) == [] for i in items)
    first = items[0]
    assert first['body'] and len(first['summary']) <= 201
    assert first['image'] and first['image']['url'].startswith('https://')
    assert first['blogger']['media'][0]['type'] == 'image'


def test_chinese_feed_is_zh_and_never_translated(tmp_path):
    items = feed_posts((FX / 'rss_wechat2rss.xml').read_bytes(), platform('wechat'), account('wechat', '夕小瑶科技说'), NOW.isoformat())
    assert items and {i['lang'] for i in items} == {'zh'}
    tr = Translator(engine='cache', cache=Cache(tmp_path / 'c.json'))
    from rebang.bloggers.common import apply_translation
    out = apply_translation(dict(items[0]), tr)
    assert out['translated'] is False and 'translation' not in out
    assert tr.cache.pending == {}


def test_not_a_feed_raises():
    with pytest.raises(FeedError):
        feed_posts(b'<html><body>login</body></html>', platform('blog'), account('blog', 'simonw'), NOW.isoformat())


# ---------- X ----------

def test_x_dump_builds_real_cards():
    by = x_posts(load_dump(FX / 'x_dump'), platform('x'), NOW.isoformat())
    assert set(by) == {a['handle'] for a in platform('x')['accounts']}
    items = [i for v in by.values() for i in v]
    assert items and all(validate_item(i) == [] for i in items)
    for item in items:
        b = item['blogger']
        assert '_400x400.' in b['avatar'] and '_normal' not in b['avatar']
        assert isinstance(b['verified'], bool)  # 照实写，假的不画
        assert set(b['metrics']) <= {'reply', 'repost', 'like', 'quote', 'bookmark', 'view'}
        assert item['url'].startswith('https://x.com/' + b['handle'] + '/status/')
    long_post = next(i for i in items if i['id'].endswith('2121946496119533937'))
    assert '2480 × 2248' in long_post['body']  # note_tweet 全文，不是截断的 text
    video = [m for i in items for m in i['blogger']['media'] if m['type'] == 'video']
    assert video and video[0]['preview_url'].startswith('https://') and '.mp4' in video[0]['url']
    assert video[0]['duration_ms'] > 0
    quoted = [i for i in items if i['blogger']['quote']]
    assert quoted and all(q['blogger']['quote']['handle'] and q['blogger']['quote']['text'] for q in quoted)
    with_comments = [i for i in items if i['blogger'].get('comments')]
    assert with_comments
    c = with_comments[0]['blogger']['comments'][0]
    assert c['text'] and not c['text'].startswith('@') and c['url'].startswith('https://x.com/')



def test_x_reply_store_merges_comments(tmp_path):
    """持久回复缓存与 dump 分开放，刷新时仍能补到评论，不会只活在单次 dump 里。"""
    import json, shutil
    from rebang.bloggers.x import load_dump, merge_reply_store, x_posts
    dump = tmp_path / 'x-dump' / 'run1'
    dump.mkdir(parents=True)
    src = FX / 'x_dump'
    for f in src.iterdir():
        if f.is_file():
            shutil.copy2(f, dump / f.name)
    # 先确认：不依赖 store 时已有的评论来自 dump 自身；再造一条只存在于 store 的回复
    posts, users, media = load_dump(dump)
    # 选一条主帖
    main = next(p for p in posts.values() if p.get('_main'))
    rid = '9000000000000000001'
    uid = '9000000000000000002'
    store = tmp_path / 'x-replies' / 'store.json'
    store.parent.mkdir(parents=True)
    store.write_text(json.dumps({
        'schema': 'rebang.x-replies-store/1',
        'posts': {
            main['id']: {
                'fetched_at': '2026-11-16T01:40:00+08:00',
                'count': 1,
                'response': {
                    'data': [{
                        'id': rid,
                        'author_id': uid,
                        'conversation_id': main['id'],
                        'text': 'This is a cached top reply about the post.',
                        'created_at': '2026-11-15T12:00:00.000Z',
                        'public_metrics': {'like_count': 42, 'reply_count': 0, 'retweet_count': 0, 'quote_count': 0},
                    }],
                    'includes': {'users': [{'id': uid, 'name': 'Cache User', 'username': 'cacheuser',
                                            'profile_image_url': 'https://pbs.twimg.com/profile_images/x_normal.jpg'}]},
                },
            }
        },
    }, ensure_ascii=False), encoding='utf-8')
    posts, users, media = load_dump(dump)
    assert rid in posts
    assert users[uid]['username'] == 'cacheuser'
    by = x_posts((posts, users, media), platform('x'), NOW.isoformat())
    items = [i for v in by.values() for i in v]
    target = next(i for i in items if i['id'].endswith(':' + main['id']) or i['url'].endswith(main['id']))
    comments = target['blogger']['comments']
    cached = [c for c in comments if c['handle'] == 'cacheuser']
    assert cached and cached[0]['like'] == 42 and cached[0]['text'] == 'This is a cached top reply about the post.'


def test_x_accounts_without_posts_are_empty_not_invented(tmp_path):
    env = run_all(tmp_path)
    x = next(p for p in env['platforms'] if p['id'] == 'x')
    rows = {a['handle']: a for a in x['accounts']}
    assert rows['karpathy']['status'] == 'empty' and rows['karpathy']['count'] == 0
    assert not [i for i in env['items'] if i['source_id'] == 'x-karpathy']


def test_x_missing_dump_is_not_configured(tmp_path):
    env = run_all(tmp_path, x_dump=str(tmp_path / 'nope'))
    x = next(p for p in env['platforms'] if p['id'] == 'x')
    assert x['status'] == 'not_configured' and '公开 X' in x['reason']
    assert not [i for i in env['items'] if i['blogger']['platform'] == 'x']


def test_x_stale_dump_is_error_and_keeps_last_good(tmp_path):
    good = run_all(tmp_path)
    later = datetime.fromisoformat('2026-11-18T09:00:00+08:00')
    env = run_all(tmp_path, previous=good, now=later)
    x = next(p for p in env['platforms'] if p['id'] == 'x')
    assert x['status'] == 'error'
    kept = [i for i in env['items'] if i['blogger']['platform'] == 'x']
    assert kept and all(i['fetched_at'] == good['generated_at'] for i in kept)
    row = next(a for a in x['accounts'] if a['handle'] == 'lxfater')
    assert row['stale'] is True and row['last_ok_at'] == good['generated_at']


# ---------- 编排 / 登录类平台 ----------

def test_full_run_envelope_valid_and_login_platforms_not_configured(tmp_path):
    env = run_all(tmp_path)
    assert validate_items_envelope(env) == []
    status = {p['id']: p['status'] for p in env['platforms']}
    assert status == {'x': 'ok', 'blog': 'ok', 'jike': 'ok', 'weibo': 'not_configured',
                      'wechat': 'ok', 'youtube': 'empty', 'zhihu': 'empty'}
    assert not [i for i in env['items'] if i['blogger']['platform'] == 'weibo']
    jike = next(p for p in env['platforms'] if p['id'] == 'jike')
    assert {a['status'] for a in jike['accounts']} == {'ok'} and len(jike['accounts']) == 9
    yt = next(p for p in env['platforms'] if p['id'] == 'youtube')
    assert yt['reason'] == runmod.REASONS['youtube_pending_confirm'] and yt['accounts'] == []
    wechat = next(p for p in env['platforms'] if p['id'] == 'wechat')
    rows = {a['handle']: a['status'] for a in wechat['accounts']}
    assert rows.pop('夕小瑶科技说') == 'ok' and set(rows.values()) == {'not_configured'}
    assert {i['source_id'] for i in env['items'] if i['blogger']['platform'] == 'wechat'} == {'wechat-夕小瑶科技说'}
    blog = next(p for p in env['platforms'] if p['id'] == 'blog')
    assert {a['status'] for a in blog['accounts']} == {'ok'} and len(blog['accounts']) == 7


def test_blog_failure_keeps_previous_items_with_date(tmp_path):
    good = run_all(tmp_path)
    simon = account('blog', 'simonw')['feed']
    later = datetime.fromisoformat('2026-11-16T21:00:00+08:00')
    env = run_all(tmp_path, previous=good, http=fake_http(fail={simon}), now=later)
    blog = next(p for p in env['platforms'] if p['id'] == 'blog')
    row = next(a for a in blog['accounts'] if a['handle'] == 'simonw')
    assert row['status'] == 'error' and row['stale'] is True and row['last_ok_at'] == good['generated_at']
    assert blog['status'] == 'ok'  # 其它博客照常
    kept = [i for i in env['items'] if i['source_id'] == 'blog-simonw']
    assert kept and all(i['fetched_at'] == good['generated_at'] for i in kept)
    assert validate_items_envelope(env) == []


def test_platform_filter_keeps_other_platforms_from_previous(tmp_path):
    good = run_all(tmp_path)
    http = fake_http()
    env = runmod.run(('x',), http=http, now=NOW, previous=good, opts=opts(tmp_path), sleep=lambda s: None)
    assert http.calls == []  # 只刷 X，不碰博客网络
    assert {p['id'] for p in env['platforms']} == {p['id'] for p in good['platforms']}
    assert len([i for i in env['items'] if i['blogger']['platform'] == 'blog']) == \
        len([i for i in good['items'] if i['blogger']['platform'] == 'blog'])


def test_jike_uses_configured_rsshub_route(tmp_path):
    seen = []

    def http(url):
        seen.append(url)
        return (FX / 'rss_wechat2rss.xml').read_bytes()
    env = runmod.run(('jike',), http=http, now=NOW, opts=opts(tmp_path, jike_rsshub='http://127.0.0.1:1200/'), sleep=lambda s: None)
    assert seen[0] == 'http://127.0.0.1:1200/jike/user/7B1385A9-FCC9-4446-B8CE-472EAF6817B2'
    assert next(p for p in env['platforms'] if p['id'] == 'jike')['status'] == 'ok'


def test_jike_public_mirrors_rotate_and_fall_back(tmp_path):
    mirrors = platform('jike')['rsshub_mirrors']
    seen = []
    body = (FX / 'rss_jike_rsshub.xml').read_bytes()

    def http(url):
        seen.append(url)
        if url.startswith(mirrors[0]):
            raise FeedError('http_5xx')          # 第一个实例挂了
        if url.startswith(mirrors[1]):
            return b'<html><title>Welcome to RSSHub</title></html>'   # 第二个回错误页
        return body
    env = runmod.run(('jike',), http=http, now=NOW, opts=opts(tmp_path), sleep=lambda s: None)
    jike = next(p for p in env['platforms'] if p['id'] == 'jike')
    assert jike['status'] == 'ok' and {a['status'] for a in jike['accounts']} == {'ok'}
    assert seen[0].startswith(mirrors[0]) and seen[2].startswith(mirrors[2])   # 第一个账号：挂→错误页→成功
    assert {a['via'] for a in jike['accounts']} <= {m.split('://')[1] for m in mirrors[2:]}
    assert all('Cookie' not in u for u in seen)


def test_jike_all_mirrors_down_is_error_not_fake(tmp_path):
    def http(url):
        raise FeedError('http_5xx')
    env = runmod.run(('jike',), http=http, now=NOW, opts=opts(tmp_path), sleep=lambda s: None)
    jike = next(p for p in env['platforms'] if p['id'] == 'jike')
    assert jike['status'] == 'error' and not env['items']
    assert {a['error'] for a in jike['accounts']} == {'jike_mirrors_down'}
    assert '公共 RSSHub' in jike['reason']


def test_jike_post_mapping_strips_prefix_and_splits_quote():
    from rebang.bloggers.jike import jike_posts
    acc = account('jike', 'C0052298-F57E-483F-9BBA-0C6BF17AB59E')
    items = jike_posts((FX / 'rss_jike_rsshub.xml').read_bytes(), platform('jike'), acc, NOW.isoformat())
    assert len(items) == 3 and all(validate_item(i) == [] for i in items)
    assert all(i['title'] == '' and not i['summary'].startswith(('发布了', '转发了')) for i in items)
    repost = next(i for i in items if '/reposts/' in i['url'])
    q = repost['blogger']['quote']
    assert q['display_name'] == '造App' and q['url'].startswith('https://m.okjike.com/users/') and '独立开发者' in q['text']
    assert 'rsshub-quote' not in repost['body'] and '造App: 作为苹果' not in repost['body']
    assert all(i['blogger']['avatar'].startswith('https://cdnv2.ruguoapp.com/') for i in items)
    with_img = [i for i in items if i['blogger']['media']]
    assert with_img and all(m['url'].startswith('https://cdnv2.ruguoapp.com/') for i in with_img for m in i['blogger']['media'])


def test_weibo_cookie_path_only_checked_never_read(tmp_path):
    cookie = tmp_path / 'weibo.cookie'
    cookie.write_text('SECRET-SHOULD-NOT-BE-READ')
    os.chmod(cookie, 0)  # 代码若尝试读取会 PermissionError
    try:
        env = runmod.run(('weibo',), http=fake_http(), now=NOW, opts=opts(tmp_path, weibo_cookie_file=str(cookie)), sleep=lambda s: None)
    finally:
        os.chmod(cookie, 0o600)
    wb = next(p for p in env['platforms'] if p['id'] == 'weibo')
    assert wb['status'] == 'not_configured'
    assert {a['error'] for a in wb['accounts']} == {'weibo_crawler_output_missing'}
    assert 'SECRET' not in json.dumps(env, ensure_ascii=False)


def test_weibo_crawler_output_mapping(tmp_path):
    data = {'user': {'id': '1560906700', 'screen_name': '阑夕', 'avatar_hd': 'https://tvax1.sinaimg.cn/a.jpg'},
            'weibo': [{'id': '5001', 'bid': 'PabcD', 'user_id': '1560906700', 'screen_name': '阑夕',
                       'text': '合成样本：一条测试正文', 'pics': 'https://wx1.sinaimg.cn/large/x.jpg,https://wx1.sinaimg.cn/large/y.jpg',
                       'created_at': '2026-11-15 10:00:00', 'attitudes_count': 12, 'comments_count': '3', 'reposts_count': 0}]}
    items = map_crawler_json(data, platform('weibo'), account('weibo', '1560906700'), NOW.isoformat())
    assert len(items) == 1 and validate_item(items[0]) == []
    b = items[0]['blogger']
    assert b['metrics'] == {'like': 12, 'reply': 3, 'repost': 0} and len(b['media']) == 2
    assert items[0]['url'] == 'https://weibo.com/1560906700/PabcD'
    assert items[0]['published_at'] == '2026-11-15T10:00:00+08:00'


# ---------- 翻译 ----------

def test_cache_engine_pending_then_fill_gives_labeled_translation(tmp_path):
    cache_path = tmp_path / 'cache.json'
    env = run_all(tmp_path)  # opts 用同一路径的缓存
    foreign = [i for i in env['items'] if not i['lang'].startswith('zh')]
    assert foreign and all(i['translated'] is False and 'translation' not in i for i in foreign)
    pending = json.loads((tmp_path / 'pending.json').read_text())['pending']
    assert pending
    fills = [{'src': v['src'], 'src_lang': v['src_lang'], 'zh': '译文：' + v['src'][:10]} for v in pending.values()]
    (tmp_path / 'fill.json').write_text(json.dumps(fills, ensure_ascii=False))
    assert translate_cli(['fill', str(tmp_path / 'fill.json'), '--engine', 'grok-bot', '--cache', str(cache_path)]) == 0
    env2 = run_all(tmp_path)
    foreign2 = [i for i in env2['items'] if not i['lang'].startswith('zh')]
    assert all(i['translated'] for i in foreign2)
    t = foreign2[0]['translation']
    assert t['label'] == '机器翻译' and t['engine'] == 'grok-bot' and t['summary'].startswith('译文：')
    assert validate_items_envelope(env2) == []
    assert all(not i.get('translated') for i in env2['items'] if i['lang'] == 'zh')


def test_fill_rejects_text_not_in_pending(tmp_path):
    cache_path = tmp_path / 'cache.json'
    (tmp_path / 'f.json').write_text(json.dumps([{'src': 'made up', 'zh': '编的'}]))
    translate_cli(['fill', str(tmp_path / 'f.json'), '--engine', 'x', '--cache', str(cache_path)])
    assert Cache(cache_path).entries == {}


def test_openai_compatible_engine_pluggable_and_failure_is_none(tmp_path, monkeypatch):
    monkeypatch.setenv('REBANG_TRANSLATE_URL', 'https://example.invalid/v1/chat/completions')
    monkeypatch.setenv('REBANG_TRANSLATE_MODEL', 'm1')
    monkeypatch.setenv('REBANG_TRANSLATE_API_KEY', 'k-test')
    sent = {}

    def ok(url, body, headers):
        sent['auth'] = headers['Authorization']
        texts = json.loads(body['messages'][0]['content'].split('\n', 1)[1])
        return {'choices': [{'message': {'content': json.dumps(['中' + t for t in texts], ensure_ascii=False)}}]}
    tr = Translator(engine='openai-compatible', cache=Cache(tmp_path / 'c.json'), http_post=ok)
    assert tr.translate(['Hello', 'World']) == ['中Hello', '中World']
    assert sent['auth'] == 'Bearer k-test'
    assert tr.translate_detailed(['Hello', 'World'])[1] == 'openai-compatible:m1'  # 第二次走缓存

    def boom(url, body, headers):
        raise RuntimeError('down')
    tr2 = Translator(engine='openai-compatible', cache=Cache(tmp_path / 'd.json'), http_post=boom)
    assert tr2.translate(['Bye']) is None


def test_openai_engine_without_config_returns_none(tmp_path, monkeypatch):
    for k in ('REBANG_TRANSLATE_URL', 'REBANG_TRANSLATE_MODEL', 'REBANG_TRANSLATE_API_KEY'):
        monkeypatch.delenv(k, raising=False)
    tr = Translator(engine='openai-compatible', cache=Cache(tmp_path / 'c.json'), http_post=lambda *a: 1 / 0)
    assert tr.translate(['Hello']) is None


def test_none_engine_and_module_signature(monkeypatch):
    import rebang.translate as t
    monkeypatch.setattr(t, '_default', Translator(engine='none'))
    assert t.translate(['Hello'], src_lang='en') is None


def test_wechat_header_lines_not_in_summary():
    items = feed_posts((FX / 'rss_wechat2rss.xml').read_bytes(), platform('wechat'), account('wechat', '夕小瑶科技说'), NOW.isoformat())
    assert all(not i['summary'].startswith('原创') for i in items)
    assert items[0]['title'] and items[0]['body']


# ---------- YouTube（名单待确认；管道用合成名单测） ----------

YT_ACC = {'handle': 'UCpnuadQ_w3r6f4Q_NRlqd-w', 'name': 'Kraig Adams', 'home': 'https://www.youtube.com/@KraigAdams'}


def yt_platform(accounts=(YT_ACC,)):
    return dict(platform('youtube'), accounts=list(accounts))


def test_youtube_feed_to_posts_uses_embed_player_and_real_fields():
    from rebang.bloggers import youtube as yt
    calls = []

    def http(url):
        calls.append(url)
        return (FX / 'youtube_feed.xml').read_bytes()
    items, via = yt.channel_posts(http, yt_platform(), YT_ACC, NOW.isoformat())
    assert via == 'rss' and calls == ['https://www.youtube.com/feeds/videos.xml?channel_id=UCpnuadQ_w3r6f4Q_NRlqd-w']
    assert len(items) == 3 and all(validate_item(i) == [] for i in items)
    first = items[0]
    assert first['published_at'] >= items[1]['published_at']
    m = first['blogger']['media'][0]
    vid = first['id'].split(':')[-1]
    assert m == {'type': 'youtube', 'url': f'https://www.youtube-nocookie.com/embed/{vid}', 'preview_url': f'https://i.ytimg.com/vi/{vid}/hqdefault.jpg'}
    assert first['url'] == f'https://www.youtube.com/watch?v={vid}' and first['title']
    assert isinstance(first['blogger']['metrics']['view'], int)


def test_youtube_rss_404_falls_back_to_public_pages_and_caches_dates():
    from rebang.bloggers import youtube as yt
    calls, naps = [], []

    def http(url):
        calls.append(url)
        if 'feeds/videos.xml' in url:
            raise FeedError('http_status')        # 2026 年常见：订阅接口对存在的频道回 404
        if url.endswith('/videos'):
            return (FX / 'youtube_channel_videos.html').read_bytes()
        if 'watch?v=AAAAAAAAAA1' in url:
            return (FX / 'youtube_watch.html').read_bytes()
        raise FeedError('http_5xx')               # 第二个视频页取不到：这轮不出，不编时间
    cache = {}
    items, via = yt.channel_posts(http, yt_platform(), YT_ACC, NOW.isoformat(), cache=cache, sleep=naps.append)
    assert via == 'page' and naps == [yt.RETRY_PAUSE]
    assert sum('feeds/videos.xml' in u for u in calls) == 2      # 订阅重试一次
    assert [i['id'].split(':')[-1] for i in items] == ['AAAAAAAAAA1']
    assert items[0]['published_at'] == '2026-11-12T02:43:56+08:00' and items[0]['summary'].startswith('第一行简介')
    assert items[0]['blogger']['media'][0]['duration_ms'] == 914000
    assert 'AAAAAAAAAA1' in cache and 'AAAAAAAAAA2' not in cache
    calls.clear()
    yt.channel_posts(http, yt_platform(), YT_ACC, NOW.isoformat(), cache=cache, sleep=naps.append)
    assert not any('watch?v=AAAAAAAAAA1' in u for u in calls)    # 已缓存的视频不再打开视频页


def test_youtube_platform_run_keeps_previous_when_unreachable(tmp_path, monkeypatch):
    from rebang.contract import schema
    real = schema.load_bloggers()
    cfg = dict(real, platforms=[yt_platform() if p['id'] == 'youtube' else p for p in real['platforms']])
    monkeypatch.setattr(runmod, 'load_bloggers', lambda: cfg)
    monkeypatch.setattr(schema, 'load_bloggers', lambda: cfg)
    good_http = lambda url: (FX / 'youtube_feed.xml').read_bytes()
    o = opts(tmp_path)
    o.youtube_cache = tmp_path / 'yt.json'
    good = runmod.run(('youtube',), http=good_http, now=NOW, opts=o, sleep=lambda s: None)
    yt = next(p for p in good['platforms'] if p['id'] == 'youtube')
    assert yt['status'] == 'ok' and yt['accounts'][0]['via'] == 'rss' and validate_items_envelope(good) == []

    def down(url):
        raise FeedError('http_status')
    later = datetime.fromisoformat('2026-11-16T21:00:00+08:00')
    env = runmod.run(('youtube',), http=down, now=later, previous=good, opts=o, sleep=lambda s: None)
    yt = next(p for p in env['platforms'] if p['id'] == 'youtube')
    row = yt['accounts'][0]
    assert row['status'] == 'error' and row['error'] == 'youtube_unreachable' and row['stale'] is True
    assert len([i for i in env['items'] if i['blogger']['platform'] == 'youtube']) == 3


def test_youtube_bad_channel_id_is_not_fetched(tmp_path, monkeypatch):
    from rebang.contract import schema
    real = schema.load_bloggers()
    bad = {'handle': '@KraigAdams', 'name': 'x'}
    cfg = dict(real, platforms=[yt_platform([bad]) if p['id'] == 'youtube' else p for p in real['platforms']])
    monkeypatch.setattr(runmod, 'load_bloggers', lambda: cfg)

    def http(url):
        raise AssertionError('should not fetch')
    env = runmod.run(('youtube',), http=http, now=NOW, opts=opts(tmp_path), sleep=lambda s: None)
    assert next(p for p in env['platforms'] if p['id'] == 'youtube')['accounts'][0]['error'] == 'parse'


# ---------- 微信读书（5 个公众号；扫码前 not_configured，扫码后的读取用合成回包测） ----------

def test_weread_login_writes_private_session_and_never_prints_token(tmp_path):
    from rebang.bloggers import weread
    seen, logs = [], []
    replies = iter([{'logicCode': 'WAITING'}, {'succeed': True, 'webLoginVid': 12345, 'accessToken': 'TOKEN-SECRET'}])

    def get(url, session=None, timeout=25):
        seen.append(url)
        if url.endswith('/api/auth/getLoginUid'):
            return {'uid': 'u-1'}
        return next(replies)
    sess = tmp_path / 'cfg' / 'weread-session.json'
    assert weread.login(qr_png=None, wait=30, session_path=sess, get=get, log=logs.append) is True
    assert seen[1].startswith('https://weread.qq.com/api/auth/getLoginInfo?uid=u-1')
    assert json.loads(logs[0])['confirm_url'] == 'https://weread.qq.com/web/confirm?uid=u-1'
    assert oct(sess.stat().st_mode & 0o777) == '0o600' and oct(sess.parent.stat().st_mode & 0o777) == '0o700'
    assert weread.load_session(sess)['skey'] == 'TOKEN-SECRET'
    assert 'TOKEN-SECRET' not in ''.join(logs)


def test_weread_login_need_otp_stops_with_instruction(tmp_path):
    from rebang.bloggers import weread
    logs = []

    def get(url, session=None, timeout=25):
        return {'uid': 'u-2'} if url.endswith('getLoginUid') else {'logicCode': 'NEED_OTP'}
    assert weread.login(wait=30, session_path=tmp_path / 's.json', get=get, log=logs.append) is False
    assert json.loads(logs[-1])['step'] == 'need_otp' and '--uid u-2' in json.loads(logs[-1])['how']
    assert not (tmp_path / 's.json').exists()


def weread_opts(tmp_path, get, session=True):
    from rebang.bloggers import weread
    sess = tmp_path / 'weread-session.json'
    if session:
        weread.save_session('1', 'k', sess)
    o = opts(tmp_path)
    o.weread_session = str(sess)
    o.weread_books = tmp_path / 'books.json'
    o.weread_get = get
    return o


def test_wechat_weread_articles_mapping(tmp_path):
    body = json.loads((FX / 'weread_mp_articles.json').read_text(encoding='utf-8'))
    calls = []

    def get(url, session=None, timeout=25):
        calls.append(url)
        assert session == {'vid': '1', 'skey': 'k', 'saved_at': session['saved_at']}
        if '/api/store/search' in url:
            return {'results': [{'books': [{'bookInfo': {'bookId': 'MP_WXS_999', 'title': '别的号'}},
                                           {'bookInfo': {'bookId': 'MP_WXS_123', 'title': _kw(url)}}]}]}
        return body
    env = runmod.run(('wechat',), http=fake_http(), now=NOW, opts=weread_opts(tmp_path, get), sleep=lambda s: None)
    assert validate_items_envelope(env) == []
    wechat = next(p for p in env['platforms'] if p['id'] == 'wechat')
    assert {a['status'] for a in wechat['accounts']} == {'ok'}
    mac = [i for i in env['items'] if i['source_id'] == 'wechat-MacTalk']
    assert [i['title'] for i in mac] == ['合成样例：最新一篇', '合成样例：第二篇']
    assert mac[0]['url'] == 'https://mp.weixin.qq.com/s/bbbb' and mac[1]['url'] == ''
    assert mac[0]['image'] == {'url': 'https://mmbiz.qpic.cn/fake/cover1.jpg'}
    assert json.loads((tmp_path / 'books.json').read_text(encoding='utf-8'))['MacTalk'] == 'MP_WXS_123'
    calls.clear()
    runmod.run(('wechat',), http=fake_http(), now=NOW, opts=weread_opts(tmp_path, get), sleep=lambda s: None)
    assert not [u for u in calls if '/api/store/search' in u]       # bookId 已缓存，不再搜


def _kw(url):
    from urllib.parse import parse_qs, urlsplit
    return parse_qs(urlsplit(url).query)['keyword'][0]


def test_wechat_weread_expired_marks_rest_and_keeps_old(tmp_path):
    from rebang.bloggers import weread

    def get(url, session=None, timeout=25):
        raise weread.WereadError('login_expired')
    env = runmod.run(('wechat',), http=fake_http(), now=NOW, opts=weread_opts(tmp_path, get), sleep=lambda s: None)
    wechat = next(p for p in env['platforms'] if p['id'] == 'wechat')
    rows = {a['handle']: a for a in wechat['accounts']}
    assert rows.pop('夕小瑶科技说')['status'] == 'ok'
    assert {r['status'] for r in rows.values()} == {'login_expired'}


def test_wechat_without_session_stays_not_configured(tmp_path):
    def get(url, session=None, timeout=25):
        raise AssertionError('no network without session')
    env = runmod.run(('wechat',), http=fake_http(), now=NOW, opts=weread_opts(tmp_path, get, session=False), sleep=lambda s: None)
    wechat = next(p for p in env['platforms'] if p['id'] == 'wechat')
    rows = {a['handle']: (a['status'], a.get('reason')) for a in wechat['accounts']}
    rows.pop('夕小瑶科技说')
    assert set(rows.values()) == {('not_configured', runmod.REASONS['wechat_weread_qr'])}
