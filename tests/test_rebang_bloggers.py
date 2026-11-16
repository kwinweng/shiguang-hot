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
                      'wechat': 'ok', 'zhihu': 'empty'}
    assert not [i for i in env['items'] if i['blogger']['platform'] == 'weibo']
    jike = next(p for p in env['platforms'] if p['id'] == 'jike')
    assert {a['status'] for a in jike['accounts']} == {'ok'} and len(jike['accounts']) == 9
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
