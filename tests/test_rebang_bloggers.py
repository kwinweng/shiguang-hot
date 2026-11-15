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
    assert status == {'x': 'ok', 'blog': 'ok', 'jike': 'not_configured', 'weibo': 'not_configured',
                      'wechat': 'ok', 'zhihu': 'empty'}
    for pid in ('jike', 'weibo'):
        assert not [i for i in env['items'] if i['blogger']['platform'] == pid]
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
