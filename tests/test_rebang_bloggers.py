"""博主分支单测：全部用 tests/fixtures/rebang/bloggers 下的真实节选样本，不联网。"""
import json
import os
import shutil
import subprocess
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from rebang.bloggers import run as runmod
from rebang.bloggers.feed import FeedError, feed_posts
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
    for a in platform('youtube')['accounts']:
        urls[f'https://www.youtube.com/feeds/videos.xml?channel_id={a["handle"]}'] = 'youtube_feed.xml'
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
    o = runmod.Options(**base)
    o.youtube_cache = tmp_path / 'yt-watch.json'   # 不写到仓库里的 var/
    return o


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


@pytest.mark.parametrize(('body', 'code'), [
    ('this is not JSON', 'parse'),
    ('{"errors": [{"message": "private upstream details"}]}', 'x_dump_error'),
])
def test_x_unusable_export_keeps_last_success_and_posts(tmp_path, body, code):
    good = runmod.run(('x',), http=fake_http(), now=NOW, opts=opts(tmp_path))
    dump = tmp_path / 'x-export.txt'
    dump.write_text(body)
    later = NOW + timedelta(hours=1)
    os.utime(dump, (later.timestamp(), later.timestamp()))
    result = runmod.run(('x',), http=fake_http(), now=later, previous=good, opts=opts(tmp_path, x_dump=dump))
    assert result['items'] == good['items']
    assert all((a['status'], a.get('error'), a['last_ok_at']) == ('error', code, NOW.isoformat())
               for a in result['platforms'][0]['accounts'])
    assert 'private upstream details' not in json.dumps(result)


def test_x_mixed_export_preserves_identified_failure_and_accepts_valid_zero(tmp_path):
    good = runmod.run(('x',), http=fake_http(), now=NOW, opts=opts(tmp_path))
    later = NOW + timedelta(hours=1)
    dump = tmp_path / 'export'
    dump.mkdir()
    (dump / '_dump.json').write_text(json.dumps({'generated_at': later.isoformat()}))
    (dump / 'search.json').write_text('{"meta": {"result_count": 0}}')
    (dump / 'search-errors.txt').write_text('''output: { "errors": [{"resource_type":"user", "parameter":"username", "value":"LXFATER"}]}''')
    result = runmod.run(('x',), http=fake_http(), now=later, previous=good, opts=opts(tmp_path, x_dump=dump))
    rows = {a['handle']: a for a in result['platforms'][0]['accounts']}
    assert (rows['lxfater']['status'], rows['lxfater'].get('error'), rows['lxfater']['last_ok_at']) == (
        'error', 'x_dump_error', NOW.isoformat())
    assert (rows['karpathy']['status'], rows['karpathy']['last_ok_at']) == ('empty', later.isoformat())


@pytest.mark.parametrize('timestamp', ['2026-11-17T21:00:00+08:00', '9999-12-31T23:00:00+00:00', 'invalid'])
def test_x_rejects_invalid_or_future_export_timestamp(tmp_path, timestamp):
    (tmp_path / '_dump.json').write_text(json.dumps({'generated_at': timestamp}))
    (tmp_path / 'posts.json').write_text('{"data": []}')
    os.utime(tmp_path / 'posts.json', (NOW.timestamp(), NOW.timestamp()))
    result = runmod.run(('x',), http=fake_http(), now=NOW, opts=opts(tmp_path, x_dump=tmp_path))
    assert all((a['status'], a.get('error'), a['last_ok_at']) == ('error', 'x_dump_time_invalid', None)
               for a in result['platforms'][0]['accounts'])


def test_x_missing_dump_is_not_configured_and_keeps_last_good(tmp_path):
    missing = str(tmp_path / 'nope')
    env = run_all(tmp_path, x_dump=missing)
    x = next(p for p in env['platforms'] if p['id'] == 'x')
    assert x['status'] == 'not_configured' and '原始数据' in x['reason']
    assert all(a['error'] == 'x_dump_missing' for a in x['accounts'])
    assert not [i for i in env['items'] if i['blogger']['platform'] == 'x']
    good = run_all(tmp_path)
    env = run_all(tmp_path, x_dump=missing, previous=good)
    good_ids = {i['id'] for i in good['items'] if i['blogger']['platform'] == 'x'}
    assert good_ids and {i['id'] for i in env['items'] if i['blogger']['platform'] == 'x'} == good_ids
    x = next(p for p in env['platforms'] if p['id'] == 'x')
    assert x['last_ok_at'] == good['generated_at']


def run_x_export(tmp_path, text, *, suffix='.json', direct_dir=False, previous=None):
    dump = tmp_path / 'export'
    dump.mkdir()
    file = dump / f'posts{suffix}'
    file.write_text(text)
    os.utime(file, (NOW.timestamp(), NOW.timestamp()))
    path = dump if direct_dir else file
    env = runmod.run(('x',), now=NOW, previous=previous, opts=opts(tmp_path, x_dump=str(path)))
    return {a['handle']: a for a in env['platforms'][0]['accounts']}


@pytest.mark.parametrize(('suffix', 'text'), [
    ('.json', '{"meta":{"result_count":0}}\n{ "data": ['),
    ('.txt', 'output: {"meta":{"result_count":0}}\n{ "da'),
    ('.json', '{"data":[{"id":"1"}],"meta":{"result_count":1}}'),
    ('.json', '{"data":[{"id":"1","author_id":"2","text":"ok","created_at":"2026-11-15T10:00:00Z"}]}'),
])
def test_x_damaged_export_never_advances_success(tmp_path, suffix, text):
    previous = runmod.run(('x',), now=NOW - timedelta(minutes=5), opts=opts(tmp_path))
    rows = run_x_export(tmp_path, text, suffix=suffix, previous=previous)
    assert all(a['status'] == 'error' and a['error'] == 'parse' for a in rows.values())
    assert all(a['last_ok_at'] == previous['generated_at'] for a in rows.values())


@pytest.mark.parametrize('broken', [False, True])
def test_x_keeps_account_errors_with_damaged_auxiliary_rows(tmp_path, broken):
    text = json.dumps([
        {'errors': [{'username': 'karpathy'}], 'includes': {'users': [None, {'id': [], 'username': 'bad'}, {'id': '2', 'username': {}}],
         'media': [None], 'posts': [None]}},
        {'meta': {'result_count': 0}},
    ])
    if broken:
        text += '\n{"data": ['
    rows = run_x_export(tmp_path, text, suffix='.txt' if broken else '.json')
    assert rows['karpathy']['error'] == 'x_dump_error'
    assert rows['karpathy']['last_ok_at'] is None
    others = [row for handle, row in rows.items() if handle != 'karpathy']
    assert all(row['status'] == ('error' if broken else 'empty') for row in others)
    assert all(row['last_ok_at'] == (None if broken else NOW.isoformat()) for row in others)


def test_x_accepts_txt_only_export_directory(tmp_path):
    rows = run_x_export(tmp_path, 'output: {"meta": {"result_count": 0}}', suffix='.txt', direct_dir=True)
    assert all(a['status'] == 'empty' and a['last_ok_at'] == NOW.isoformat() for a in rows.values())


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
    first = next(p for p in good['platforms'] if p['id'] == 'x')['accounts'][0]
    assert row['dump_at'] == first['dump_at'] != row['last_ok_at']


# ---------- 编排 / 登录类平台 ----------

def test_full_run_envelope_valid_and_login_platforms_not_configured(tmp_path):
    env = run_all(tmp_path)
    assert validate_items_envelope(env) == []
    status = {p['id']: p['status'] for p in env['platforms']}
    assert status == {'x': 'ok', 'blog': 'ok', 'jike': 'ok', 'weibo': 'not_configured',
                      'wechat': 'ok', 'youtube': 'ok', 'zhihu': 'empty'}
    assert not [i for i in env['items'] if i['blogger']['platform'] == 'weibo']
    jike = next(p for p in env['platforms'] if p['id'] == 'jike')
    assert {a['status'] for a in jike['accounts']} == {'ok'} and len(jike['accounts']) == 9
    yt = next(p for p in env['platforms'] if p['id'] == 'youtube')
    assert len(yt['accounts']) == 13 and {a['status'] for a in yt['accounts']} == {'ok'}
    assert {a['via'] for a in yt['accounts']} == {'rss'}
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


WB = Path(__file__).parent / 'fixtures' / 'rebang' / 'weibo'
WB_COOKIE = 'SUB=FAKE-TEST-COOKIE-VALUE; SUBP=FAKE2'


def weibo_get(expire_after=None, fail_uid=None):
    """假的 weibo.com ajax：每个 uid 都回阑夕的真实（裁剪过的）回包；可在第 N 次请求后模拟 Cookie 失效。"""
    calls = []

    def get(url, cookie):
        calls.append(url)
        assert cookie == WB_COOKIE   # Cookie 只作为参数传给请求函数
        if expire_after is not None and len(calls) > expire_after:
            from rebang.bloggers.weibo import WeiboError
            raise WeiboError('login_expired')
        if fail_uid and f'uid={fail_uid}&' in url:
            from rebang.bloggers.weibo import WeiboError
            raise WeiboError('network')
        if '/ajax/statuses/mymblog?' in url:
            return json.loads((WB / 'mymblog-1560906700.json').read_text())
        if url.endswith('/ajax/statuses/longtext?id=RrFnBaNaI'):
            return json.loads((WB / 'longtext-RrFnBaNaI.json').read_text())
        if '/ajax/statuses/longtext?id=' in url:
            return {'ok': 1, 'data': {}}   # 接口给不出长文时的真实形态
        raise AssertionError(f'unexpected weibo call {url}')
    get.calls = calls
    return get


def weibo_opts(tmp_path, get, **kw):
    cookie = tmp_path / 'weibo-cookie.txt'
    cookie.write_text(WB_COOKIE + '\n')
    os.chmod(cookie, 0o600)
    o = opts(tmp_path, weibo_cookie_file=str(cookie), weibo_output=str(tmp_path / 'wb-out'), **kw)
    o.weibo_get = get
    return o


def test_weibo_real_sample_mapping():
    from rebang.bloggers.weibo import map_posts
    posts = json.loads((WB / 'mymblog-1560906700.json').read_text())['data']['list']
    full = json.loads((WB / 'longtext-RrFnBaNaI.json').read_text())['data']['longTextContent']
    items = map_posts(posts, platform('weibo'), account('weibo', '1560906700'), NOW.isoformat(), {'RrFnBaNaI': full})
    assert len(items) == 4 and all(validate_item(i) == [] for i in items)
    assert [i['published_at'] for i in items] == sorted((i['published_at'] for i in items), reverse=True)
    by = {i['url'].rsplit('/', 1)[1]: i for i in items}
    assert set(by) == {'RrFnBaNaI', 'RrEZhkirq', 'RrDKUkc9k', 'RrxEwgT4C'}
    long_ = by['RrFnBaNaI']
    assert long_['url'] == 'https://weibo.com/1560906700/RrFnBaNaI' and long_['published_at'] == '2026-11-16T17:57:50+08:00'
    assert len(long_['body']) > len(posts[0]['text_raw']) and long_['body'].startswith('看到警方查实')   # 长文补全
    assert long_['id'] == 'weibo-1560906700:5365939232572300' and long_['lang'] == 'zh'
    b = long_['blogger']
    assert b['handle'] == '1560906700' and b['display_name'] == '阑夕' and b['avatar'].startswith('https://') and '?' not in b['avatar']
    assert b['metrics'] == {'like': 45, 'reply': 8, 'repost': 5}
    one = by['RrDKUkc9k']['blogger']['media']
    assert len(one) == 1 and one[0]['type'] == 'image' and '/large/' in one[0]['url'] and one[0]['url'].startswith('https://wx')
    many = by['RrxEwgT4C']['blogger']['media']
    assert len(many) == 12 and all(m['type'] == 'image' and m.get('width') for m in many)
    rep = by['RrEZhkirq']
    v = rep['blogger']['media'][0]
    assert v['type'] == 'video' and v['url'].startswith('https://f.video.weibocdn.com/') and v['preview_url'].startswith('https://')
    assert v['duration_ms'] == 9000 and rep['image']['url'] == v['preview_url']
    q = rep['blogger']['quote']
    assert q['handle'].isdigit() and q['display_name'] and q['text'] and q['url'].startswith('https://weibo.com/') and rep['body'] == '这是为啥'
    assert not any('\u200b' in i['body'] for i in items)


def test_weibo_run_reads_cookie_only_for_requests_and_never_outputs_it(tmp_path, capsys):
    get = weibo_get()
    o = weibo_opts(tmp_path, get)
    slept = []
    env = runmod.run(('weibo',), http=fake_http(), now=NOW, opts=o, sleep=slept.append)
    assert validate_items_envelope(env) == []
    wb = next(p for p in env['platforms'] if p['id'] == 'weibo')
    assert wb['status'] == 'ok' and len(wb['accounts']) == 6 and {a['status'] for a in wb['accounts']} == {'ok'}
    # 6 个号各 1 次列表；两条长文各取一次（第二个号起命中缓存，空长文也缓存）；karminski 用配置里的数字 uid
    assert sum('/mymblog?' in u for u in get.calls) == 6 and sum('/longtext?' in u for u in get.calls) == 2
    assert any('uid=2169039837&' in u for u in get.calls) and not any('linfcstmr' in u for u in get.calls)
    assert slept and min(slept) >= 3.0   # 请求之间至少隔 3 秒
    out = tmp_path / 'wb-out'
    assert (out / 'longtext-cache.json').exists() and (out / 'raw-2169039837.json').exists()
    blob = json.dumps(env, ensure_ascii=False) + ''.join(f.read_text() for f in out.iterdir()) + ''.join(capsys.readouterr())
    assert 'FAKE-TEST-COOKIE' not in blob and 'SUB=' not in blob
    # 第二轮：长文走缓存，不再请求
    get2 = weibo_get()
    runmod.run(('weibo',), http=fake_http(), now=NOW, previous=env, opts=weibo_opts(tmp_path, get2), sleep=lambda s: None)
    assert sum('/longtext?' in u for u in get2.calls) == 0


def test_weibo_cookie_expired_keeps_last_good_and_stops_requests(tmp_path, capsys):
    good = runmod.run(('weibo',), http=fake_http(), now=NOW, opts=weibo_opts(tmp_path, weibo_get()), sleep=lambda s: None)
    assert len([i for i in good['items'] if i['blogger']['platform'] == 'weibo']) == 24
    (tmp_path / 'wb-out' / 'longtext-cache.json').unlink()
    get = weibo_get(expire_after=0)   # 第一次请求就失效（ok!=1 / 跳登录）
    later = datetime.fromisoformat('2026-11-15T21:30:00+08:00')
    env = runmod.run(('weibo',), http=fake_http(), now=later, previous=good, opts=weibo_opts(tmp_path, get), sleep=lambda s: None)
    assert validate_items_envelope(env) == []
    wb = next(p for p in env['platforms'] if p['id'] == 'weibo')
    assert wb['status'] == 'login_expired' and 'Cookie 已失效' in wb['reason']
    assert {a['error'] for a in wb['accounts']} == {'weibo_cookie_expired'}
    assert all(a['stale'] and a['last_ok_at'] == good['generated_at'] for a in wb['accounts'])
    assert len(get.calls) == 1   # 失效后不再请求其它号
    kept = [i for i in env['items'] if i['blogger']['platform'] == 'weibo']
    assert len(kept) == 24 and {i['id'] for i in kept} == {i['id'] for i in good['items']}
    err = capsys.readouterr().err
    assert 'weibo cookie expired' in err and 'FAKE' not in err


def test_weibo_one_account_network_error_keeps_its_last_posts(tmp_path):
    good = runmod.run(('weibo',), http=fake_http(), now=NOW, opts=weibo_opts(tmp_path, weibo_get()), sleep=lambda s: None)
    env = runmod.run(('weibo',), http=fake_http(), now=NOW, previous=good,
                     opts=weibo_opts(tmp_path, weibo_get(fail_uid='1233486457')), sleep=lambda s: None)
    wb = next(p for p in env['platforms'] if p['id'] == 'weibo')
    row = next(a for a in wb['accounts'] if a['handle'] == '1233486457')
    assert wb['status'] == 'ok' and row['status'] == 'error' and row['error'] == 'weibo_fetch_failed' and row['stale']
    assert len([i for i in env['items'] if i['source_id'] == 'weibo-1233486457']) == 4


def test_weibo_http_json_detects_login_redirect_and_non_json(monkeypatch):
    from rebang.bloggers import weibo as weibo_mod

    class Resp:
        def __init__(self, url, body):
            self.url, self.body = url, body
        def __enter__(self):
            return self
        def __exit__(self, *a):
            return False
        def geturl(self):
            return self.url
        def read(self):
            return self.body
    cases = [('https://passport.weibo.com/visitor/visitor?entry=miniblog', b'<html>'),
             ('https://weibo.com/ajax/statuses/mymblog?uid=1', b'<html>login</html>'),
             ('https://weibo.com/ajax/statuses/mymblog?uid=1', b'{"ok": -100, "url": "https://passport.weibo.com/"}')]
    for final, body in cases:
        monkeypatch.setattr(weibo_mod.urllib.request, 'urlopen', lambda req, timeout=0, f=final, b=body: Resp(f, b))
        with pytest.raises(weibo_mod.WeiboError) as exc:
            weibo_mod.http_json('https://weibo.com/ajax/statuses/mymblog?uid=1', WB_COOKIE)
        assert exc.value.code == 'login_expired' and 'FAKE' not in str(exc.value)
    monkeypatch.setattr(weibo_mod.urllib.request, 'urlopen', lambda req, timeout=0: Resp('https://weibo.com/x', b'{"ok": 1, "data": {}}'))
    assert weibo_mod.http_json('https://weibo.com/x', WB_COOKIE)['ok'] == 1


def test_weibo_empty_cookie_file_is_not_configured(tmp_path):
    cookie = tmp_path / 'weibo-cookie.txt'
    cookie.write_text('\n')
    get = weibo_get()
    o = opts(tmp_path, weibo_cookie_file=str(cookie), weibo_output=str(tmp_path / 'out'))
    o.weibo_get = get
    env = runmod.run(('weibo',), http=fake_http(), now=NOW, opts=o, sleep=lambda s: None)
    wb = next(p for p in env['platforms'] if p['id'] == 'weibo')
    assert wb['status'] == 'not_configured' and not get.calls


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
    assert mac[0]['url'] == 'https://mp.weixin.qq.com/s/bbbb' and mac[1]['url'] == 'https://mp.weixin.qq.com/s/aaaa'
    assert mac[0]['image'] == {'url': 'https://mmbiz.qpic.cn/fake/cover1.jpg'}
    assert not [u for u in calls if '/api/store/search' in u]       # book_id 已写在配置里，不再搜


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


def test_jike_images_shrunk_on_cdn_only():
    from rebang.bloggers.jike import sized
    u = 'https://cdnv2.ruguoapp.com/x.heic?imageMogr2/format/jpeg'
    assert sized(u) == u + '/thumbnail/1080x%3E' and sized(sized(u)) == sized(u)
    assert sized('https://example.com/a.jpg') == 'https://example.com/a.jpg'


def test_weread_login_refreshes_qr_when_server_says_no_retry(tmp_path):
    """LOGIN_TIMEOUT 且没有 canRetry：换新二维码接着等，而不是直接退出。"""
    from rebang.bloggers import weread
    logs, uids = [], iter(['u-a', 'u-b'])
    polls = iter([{'logicCode': 'LOGIN_TIMEOUT'}, {'succeed': True, 'webLoginVid': 7, 'accessToken': 'S'}])
    seen = []

    def get(url, session=None, timeout=25):
        if url.endswith('getLoginUid'):
            return {'uid': next(uids)}
        seen.append(url)
        return next(polls)
    assert weread.login(wait=300, session_path=tmp_path / 's.json', get=get, log=logs.append) is True
    steps = [json.loads(x)['step'] for x in logs]
    assert steps == ['scan', 'refreshed', 'done']
    assert 'uid=u-a' in seen[0] and 'uid=u-b' in seen[1]
    assert json.loads(logs[1])['confirm_url'].endswith('uid=u-b')


def test_weread_login_with_otp_does_not_refresh(tmp_path):
    from rebang.bloggers import weread
    logs = []

    def get(url, session=None, timeout=25):
        assert 'getLoginUid' not in url
        return {'logicCode': 'LOGIN_TIMEOUT'}
    assert weread.login(wait=30, uid='u-9', otp='1234', session_path=tmp_path / 's.json', get=get, log=logs.append) is False
    assert json.loads(logs[-1])['step'] == 'expired'


def test_weread_login_keeps_same_qr_on_retryable_timeout(tmp_path):
    """真实回包（2026-11-16）：长轮询约 56 秒回 {LOGIN_TIMEOUT, canRetry: true, succeed: false}，同一个码接着等。"""
    from rebang.bloggers import weread
    logs, seen = [], []
    polls = iter([{'logicCode': 'LOGIN_TIMEOUT', 'canRetry': True, 'succeed': False}] * 3
                 + [{'succeed': True, 'webLoginVid': 8, 'accessToken': 'S2'}])

    def get(url, session=None, timeout=25):
        if url.endswith('getLoginUid'):
            assert not seen, 'should not ask for a new QR'
            return {'uid': 'u-same'}
        seen.append(url)
        return next(polls)
    assert weread.login(wait=600, session_path=tmp_path / 's.json', get=get, log=logs.append) is True
    assert [json.loads(x)['step'] for x in logs] == ['scan', 'done']
    assert len(seen) == 4 and all('uid=u-same' in u for u in seen)


def test_x_silent_account_keeps_last_posts_from_previous_run(tmp_path):
    """dump 只搜 24 小时：这次没发帖的博主保留上次的帖子（不编新内容），新帖数记 new=0。"""
    good = run_all(tmp_path)
    lx = [i for i in good['items'] if i['source_id'] == 'x-lxfater']
    assert lx
    empty_dump = tmp_path / 'dump-empty'
    empty_dump.mkdir()
    (empty_dump / 'posts.json').write_text('{"data": [], "includes": {"users": []}}', encoding='utf-8')
    (empty_dump / '_dump.json').write_text(json.dumps({'generated_at': NOW.isoformat()}), encoding='utf-8')
    env = run_all(tmp_path, previous=good, x_dump=str(empty_dump))
    assert validate_items_envelope(env) == []
    row = next(a for a in next(p for p in env['platforms'] if p['id'] == 'x')['accounts'] if a['handle'] == 'lxfater')
    assert row['status'] == 'ok' and row['new'] == 0 and row['count'] == len(lx)
    assert [i['id'] for i in env['items'] if i['source_id'] == 'x-lxfater'] == [i['id'] for i in lx]
    karpathy = next(a for a in next(p for p in env['platforms'] if p['id'] == 'x')['accounts'] if a['handle'] == 'karpathy')
    assert karpathy['status'] == 'empty' and karpathy['count'] == 0


def test_x_latest_dump_skips_dump_still_being_written(tmp_path):
    from rebang.bloggers.x import latest_dump
    done, writing = tmp_path / '20261116T1353', tmp_path / '20261116T1550'
    done.mkdir(); writing.mkdir()
    (done / 'posts.json').write_text('{}'); (done / '_dump.json').write_text('{}')
    (writing / 'search-p1.json').write_text('{}')          # 例程还在写，没有 _dump.json
    assert latest_dump(tmp_path) == done
    (writing / '_dump.json').write_text('{}')
    assert latest_dump(tmp_path) == writing


def test_x_reads_older_complete_dumps_in_window(tmp_path):
    root = tmp_path / 'x-dump'
    shutil.copytree(FX / 'x_dump', root / '20261116T0752')
    newest = root / '20261116T1353'
    newest.mkdir()
    (newest / 'posts.json').write_text('{"data": [], "includes": {"users": []}}', encoding='utf-8')
    (newest / '_dump.json').write_text(json.dumps({'generated_at': NOW.isoformat()}), encoding='utf-8')
    base = run_all(tmp_path / 'a')
    env = run_all(tmp_path / 'b', x_dump=str(root))
    ids = lambda e: sorted(i['id'] for i in e['items'] if i['blogger']['platform'] == 'x')
    assert ids(env) == ids(base) and ids(env)


def test_youtube_watch_page_without_microformat_uses_date_text():
    from rebang.bloggers import youtube as yt
    html = '"playabilityStatus":{"status":"LOGIN_REQUIRED"} "dateText":{"simpleText":"Premiered Nov 14, 2026"}'
    assert yt.parse_watch_page(html)['published'] == '2026-11-14T12:00:00-08:00'
    assert yt.parse_watch_page('"playabilityStatus":{"status":"LOGIN_REQUIRED"}') is None


def test_youtube_keeps_previous_videos_when_page_fallback_returns_fewer(tmp_path):
    good = run_all(tmp_path)
    kraig = 'youtube-UCpnuadQ_w3r6f4Q_NRlqd-w'
    before = [i['id'] for i in good['items'] if i['source_id'] == kraig]
    assert len(before) == 3

    def http(url):
        if 'feeds/videos.xml' in url and 'UCpnuadQ_w3r6f4Q_NRlqd-w' in url:
            raise FeedError('http_status')
        if url.endswith('/videos'):
            return (FX / 'youtube_channel_videos.html').read_bytes()
        if 'watch?v=' in url:
            return (FX / 'youtube_watch.html').read_bytes()
        return fake_http()(url)
    env = run_all(tmp_path, previous=good, http=http)
    after = [i['id'] for i in env['items'] if i['source_id'] == kraig]
    assert set(before) <= set(after) and len(after) > len(before)
    row = next(a for p in env['platforms'] if p['id'] == 'youtube' for a in p['accounts'] if a['handle'] == 'UCpnuadQ_w3r6f4Q_NRlqd-w')
    assert row['via'] == 'page' and row['new'] >= 1



@pytest.mark.parametrize('failure', ['network', 'content_time_missing'])
def test_weread_cover_failure_preserves_content_and_last_success(tmp_path, failure):
    from rebang.bloggers import weread
    body = json.loads((FX / 'weread_mp_articles.json').read_text(encoding='utf-8'))
    good = runmod.run(('wechat',), http=fake_http(), now=NOW,
                      opts=weread_opts(tmp_path, lambda *a, **k: body), sleep=lambda s: None)

    def get(url, **kwargs):
        if '/web/mp/articles?' in url:
            return {'errCode': -2041}
        return {'reviewId': 'MP_WXS_123_latest', 'title': '最新文章'}

    def get_text(*args, **kwargs):
        if failure == 'network':
            raise weread.WereadError('network')
        return '<html>没有可验证的发布时间</html>'

    config = weread_opts(tmp_path, get)
    config.weread_get_text = get_text
    later = datetime.fromisoformat('2026-11-15T22:00:00+08:00')
    env = runmod.run(('wechat',), http=fake_http(), now=later, previous=good,
                     opts=config, sleep=lambda s: None)
    assert validate_items_envelope(env) == []
    row = next(a for p in env['platforms'] if p['id'] == 'wechat'
               for a in p['accounts'] if a['handle'] == 'MacTalk')
    assert row['status'] == 'error' and row['detail'] == failure and row['stale'] is True
    assert row['last_ok_at'] == NOW.isoformat()
    assert [i for i in env['items'] if i['source_id'] == 'wechat-MacTalk'] == [
        i for i in good['items'] if i['source_id'] == 'wechat-MacTalk']


def test_weread_content_meta_reads_time_and_url():
    from rebang.bloggers import weread
    html = """<meta property="og:url" content="https://mp.weixin.qq.com/s?__biz=MjM5MDczODM3Mw==&amp;mid=1#rd">
               ori_create_time: '1794670399' * 1"""
    meta = weread.content_meta(html)
    assert meta['published'] == 1794670399
    assert meta['url'].startswith('https://mp.weixin.qq.com/s?__biz=MjM5MDczODM3Mw==')
    assert weread.content_meta('nope')['published'] is None


def test_wechat_articles_2041_falls_back_to_cover_not_expired(tmp_path):
    """真实会话上 /web/mp/articles 回 -2041，但 cover + 正文页可用，不能把登录判死。"""
    from rebang.bloggers import weread
    calls = []

    def get(url, session=None, timeout=25):
        calls.append(url)
        if '/web/mp/articles' in url:
            return {'errCode': -2041, 'errMsg': '-2041'}
        if '/api/mp/cover' in url:
            return {'name': 'MacTalk', 'title': '封面这篇', 'pic': 'https://mmbiz.qpic.cn/fake/c.jpg',
                    'reviewId': 'MP_WXS_2398460220_TOKEN1'}
        raise AssertionError(url)

    def get_text(url, session=None, timeout=40):
        calls.append(url)
        assert 'reviewId=MP_WXS_2398460220_TOKEN1' in url
        return 'ori_create_time: \'1794495217\'  <meta property="og:url" content="https://mp.weixin.qq.com/s/TOKEN1">'

    o = weread_opts(tmp_path, get)
    o.weread_get_text = get_text
    env = runmod.run(('wechat',), http=fake_http(), now=NOW, opts=o, sleep=lambda s: None)
    assert validate_items_envelope(env) == []
    wechat = next(p for p in env['platforms'] if p['id'] == 'wechat')
    mac = next(a for a in wechat['accounts'] if a['handle'] == 'MacTalk')
    assert mac['status'] == 'ok' and mac['via'] == 'cover' and mac['count'] >= 1
    item = next(i for i in env['items'] if i['source_id'] == 'wechat-MacTalk')
    assert item['title'] == '封面这篇' and item['url'] == 'https://mp.weixin.qq.com/s/TOKEN1'
    assert item['published_at'].startswith('2026-')
    assert not any('/api/store/search' in u for u in calls)   # book_id 已写在配置里


def test_weibo_default_cookie_path_not_present_is_not_configured(tmp_path, monkeypatch):
    """默认 ~/.config/rebang/weibo-cookie.txt 还不存在时，不抓、不报错。"""
    from rebang.bloggers import weibo as weibo_mod
    monkeypatch.setattr(weibo_mod, 'DEFAULT_COOKIE', tmp_path / 'missing-cookie.txt')
    o = opts(tmp_path, weibo_cookie_file=str(weibo_mod.DEFAULT_COOKIE), weibo_output=str(tmp_path / 'out'))
    env = runmod.run(('weibo',), http=fake_http(), now=NOW, opts=o, sleep=lambda s: None)
    wb = next(p for p in env['platforms'] if p['id'] == 'weibo')
    assert wb['status'] == 'not_configured'
    assert not [i for i in env['items'] if i['blogger']['platform'] == 'weibo']


def test_weibo_missing_cookie_refresh_keeps_content_and_reports_not_configured(tmp_path, monkeypatch):
    from rebang.bloggers import weibo
    from rebang.site.health import build_health

    good = runmod.run(('weibo',), http=fake_http(), now=NOW, opts=weibo_opts(tmp_path, weibo_get()), sleep=lambda _: None)
    assert good['items']

    def unexpected(*args, **kwargs):
        pytest.fail('missing configuration must not read a cookie or request media')

    monkeypatch.setattr(weibo, 'read_cookie', unexpected)
    later = NOW + timedelta(hours=1)
    o = opts(tmp_path, weibo_cookie_file=tmp_path / 'missing-cookie')
    o.localize_media = True
    o.weibo_media_get = unexpected
    o.media_dir = tmp_path / 'media'
    result = runmod.run(('weibo',), http=unexpected, now=later, previous=good, opts=o)
    assert result['platforms'][0]['status'] == 'not_configured'
    assert result['items'] == good['items']
    snapshot = build_health([('bloggers.json', result)], result['items'], later)
    row = next(r for r in snapshot['sources'] if r['id'] == 'weibo')
    assert (row['status'], row['last_ok_at'], row['reason']) == ('not_configured', NOW.isoformat(), '微博登录尚未配置')


def test_refresh_dispatches_weibo_even_without_cookie_file(tmp_path, monkeypatch):
    tools = tmp_path / 'tools'
    tools.mkdir()
    refresh = tools / 'rebang_refresh.sh'
    shutil.copyfile(Path(__file__).resolve().parents[1] / 'tools/rebang_refresh.sh', refresh)
    # A temporary root and stand-ins exercise argument selection without running collection or publication.
    fake_python = tools / 'fake-python'
    fake_python.write_text('''#!/bin/sh
case "$2" in
    rebang.bloggers) printf '%s\n' "$*" > bloggers-args ;;
    rebang.ingest) touch var/rebang/in/ingest.json.tmp ;;
    rebang.site) mkdir -p "$6/data" && touch "$6/index.html" "$6/data/meta.json" ;;
esac
''')
    fake_flock = tools / 'flock'
    fake_flock.write_text('#!/bin/sh\nexit 0\n')
    for path in (fake_python, fake_flock):
        path.chmod(0o700)
    monkeypatch.setenv('PATH', str(tools) + os.pathsep + os.environ['PATH'])
    monkeypatch.setenv('BOX_PYTHON', str(fake_python))
    monkeypatch.setenv('REBANG_WEIBO_COOKIE', str(tmp_path / 'missing-cookie'))
    monkeypatch.setenv('REBANG_WEIBO_OUTPUT', str(tmp_path / 'weibo-output'))
    subprocess.run(['sh', str(refresh), '--no-publish'], cwd=tmp_path, check=True, capture_output=True)
    arguments = (tmp_path / 'bloggers-args').read_text().split()
    assert 'weibo' in arguments[arguments.index('--platform') + 1].split(',')
    assert not (tmp_path / 'weibo-output').exists()
