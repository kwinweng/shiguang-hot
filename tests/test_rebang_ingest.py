"""rebang.ingest：整源一频道、只读 tg.db、14 天图片、订阅/Trending 解析与失败隔离、今日重点规则、翻译接口。不联网。"""
import copy
import hashlib
import io
import json
import sqlite3
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import datetime
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

from PIL import Image

from rebang.contract import load_channels, source_channel, validate_items_envelope
from rebang.ingest import collect
from rebang.ingest import __main__ as cli
from rebang.ingest.core import parse_feed, parse_trending, split_tg_text

ROOT = Path(__file__).resolve().parents[1]
FIX = ROOT / 'tests/fixtures/rebang/ingest'
NOW = datetime(2026, 11, 15, 12, 0, tzinfo=ZoneInfo('Asia/Shanghai'))
TG = [s for c in load_channels()['channels'] for s in c['sources'] if s['type'] == 'telegram']
FEEDS = {s['url']: s for c in load_channels()['channels'] for s in c['sources'] if s['type'] in ('feed', 'page')}


def make_db(folder):
    data = json.loads((FIX / 'tg-messages.json').read_text(encoding='utf-8'))
    db = Path(folder) / 'tg.db'
    con = sqlite3.connect(db)
    con.execute("create table msg(ch text,id int,ts text,text text,links text,html text, images text not null default '[]',primary key(ch,id))")
    con.execute('create table status(ch text primary key,ok int,err text,at text)')
    for ch, i, ts, text, images in data['rows']:
        con.execute('insert into msg values(?,?,?,?,?,?,?)', (ch, i, ts, text, '[]', '', json.dumps(images)))
        for rel in images:
            path = Path(folder) / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            Image.new('RGB', (64, 36), 'gray').save(path, 'WEBP')
    con.executemany('insert into status values(?,?,?,?)', data['status'])
    con.commit(); con.close()
    return db


def inbox_loader(folder):
    data = json.loads((FIX / 'inbox.json').read_text(encoding='utf-8'))
    base = Path(folder) / 'inbox'
    base.mkdir(exist_ok=True)
    Image.new('RGB', (120, 80), 'white').save(base / 'img.png')
    return lambda sid: [(copy.deepcopy(feed), base) for feed in data.get(sid, [])]


def fake_http(fail=()):
    rss = (FIX / 'feed-rss.xml').read_bytes()
    atom = (FIX / 'feed-atom.xml').read_bytes()
    page = (FIX / 'trending.html').read_bytes()

    def get(url, now):
        if FEEDS[url]['id'] in fail:
            raise OSError('network down')
        return page if FEEDS[url]['type'] == 'page' else (atom if 'blog' in FEEDS[url]['id'] else rss)
    return get


class IngestTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.db = make_db(self.dir)
        self.cache = self.dir / 'cache'
        self.loader = inbox_loader(self.dir)

    def tearDown(self):
        self.tmp.cleanup()

    def run_collect(self, **kw):
        kw.setdefault('fetch', False)
        kw.setdefault('translator', None)
        return collect(NOW, db=self.db, cache=self.cache, inbox_loader=self.loader, **kw)

    def by_source(self, env):
        out = {}
        for item in env['items']:
            out.setdefault(item['source_id'], []).append(item)
        return out

    def test_telegraph_link_in_tg_message_becomes_full_body(self):
        con = sqlite3.connect(self.db)
        handles = [s.get('handle') or s['id'] for s in TG]
        ch, i, ts = con.execute(f"select ch,id,ts from msg where ch in ({','.join('?' * len(handles))}) order by ts desc limit 1",
                                handles).fetchone()
        url = 'https://telegra.ph/story-11-15'
        con.execute('update msg set text=?, links=? where ch=? and id=?',
                    ('纽约时报双语版\n宏福苑大火一周年\nTelegraph | 原文链接', json.dumps(['https://cn.nytimes.com/x', url]), ch, i))
        con.commit(); con.close()
        page = (f"<html><body><article class='tl_article_content'><h1>标题</h1><address>频道</address>"
                f"<p>{'Telegraph 文章正文，足够长的一段话。' * 40}</p></article></body></html>").encode('utf-8')
        feeds = fake_http()
        env = self.run_collect(fetch=True, http_get=lambda u, now: page if u == url else feeds(u, now))
        self.assertEqual(validate_items_envelope(env), [])
        item = next(it for it in env['items'] if it['id'].endswith(f':{i}') and it['url'] == f'https://t.me/{ch}/{i}')
        self.assertIn('Telegraph 文章正文', item['body'])
        self.assertTrue(item['blocks'])
        self.assertFalse(any('extract_url' in it for it in env['items']))

    def test_envelope_valid_and_every_item_in_its_configured_channel(self):
        env = self.run_collect(fetch=True, http_get=fake_http())
        self.assertEqual(validate_items_envelope(env), [])
        news = [i for i in env['items'] if i['kind'] == 'news']
        for item in news:
            self.assertEqual(item['channel'], source_channel(item['source_id']), item['id'])
        self.assertEqual({i['channel'] for i in news}, {'current', 'world', 'finance', 'tech-ai', 'digital', 'tools'})
        self.assertEqual(len(env['items']), len(news))
        self.assertFalse({'x', 'world', 'github'} & {s['id'] for s in env['sources']})

    def test_all_18_telegram_sources_reported_and_reorx_excluded(self):
        env = self.run_collect()
        tg_status = [s for s in env['sources'] if s['type'] == 'telegram']
        self.assertEqual(sorted(s['id'] for s in tg_status), sorted(s['id'] for s in TG))
        for s in tg_status:
            self.assertEqual(s['channel'], source_channel(s['id']))
        self.assertNotIn('reorx_share', {i['source_id'] for i in env['items']})
        hua = next(s for s in tg_status if s['id'] == 'HuaErJie1')
        self.assertEqual((hua['status'], hua['count']), ('empty', 0))
        self.assertIn('页面无消息', hua['error'])

    def test_tg_window_title_and_url(self):
        items = self.by_source(self.run_collect())
        ids = [i['id'] for i in items['tnews365']]
        self.assertEqual(ids, ['tnews365:101'])  # 默认只收最近 14 天
        wide = [i['id'] for i in self.by_source(self.run_collect(days=30))['tnews365']]
        self.assertEqual(wide, ['tnews365:101', 'tnews365:90'])  # 9 月那条在 30 天窗口外
        first = items['tnews365'][0]
        self.assertEqual((first['title'], first['url']), ('竹新社标题', 'https://t.me/tnews365/101'))
        self.assertTrue(first['summary'].startswith('这是正文第一段'))
        self.assertEqual(items['zaihuapd'][0]['title'], '研究称六款中国 AI 模型留下 Blackwell 芯片指纹')

    def test_images_kept_only_14_days_and_never_fake_http(self):
        items = {i['id']: i for i in self.run_collect(days=30)['items']}
        fresh, old = items['tnews365:101'], items['tnews365:90']
        self.assertIsNone(fresh['image'])
        self.assertEqual(fresh['image_local']['rel'], 'media/tnews365/101_1.webp')
        self.assertEqual((fresh['image_local']['width'], fresh['image_local']['height']), (64, 36))
        self.assertNotIn('image_local', old)  # 文件还在但消息超过 14 天

    def test_tg_media_reaches_news_without_overwriting_cached_cover(self):
        from rebang.tgmeta import parse_page
        meta = parse_page('''
          <div class="tgme_widget_message" data-post="tnews365/101">
            <a class="tgme_widget_message_reply"><i class="tgme_widget_message_photo_wrap"
              style="background-image:url('https://cdn.test/reply.jpg')"></i></a>
            <a class="tgme_widget_message_video_player">
              <i class="tgme_widget_message_video_thumb" style="background-image:url('https://cdn.test/cover.jpg')"></i>
              <video class="tgme_widget_message_video blured" src="https://cdn.test/spoiler.mp4"></video>
              <div class="tgme_widget_message_video_wrap">
                <video class="tgme_widget_message_video js-message_video" src="https://cdn.test/full.mp4"></video>
              </div>
            </a>
            <a class="tgme_widget_message_photo_wrap" style="background-image:url('//cdn.test/album.jpg')"></a>
            <a class="tgme_widget_message_video_player not_supported">
              <i class="tgme_widget_message_video_thumb" style="background-image:url('https://cdn.test/large-cover.jpg')"></i>
              <div class="tgme_widget_message_video_wrap"></div>
            </a>
          </div>
        ''')
        env = self.run_collect(tgmeta={'tnews365/101': meta[101]})
        self.assertEqual(validate_items_envelope(env), [])
        item = self.by_source(env)['tnews365'][0]
        self.assertEqual(item['image_local']['rel'], 'media/tnews365/101_1.webp')
        self.assertEqual(item['tg']['media'], [
            {'type': 'video', 'url': 'https://cdn.test/full.mp4', 'preview_url': 'https://cdn.test/cover.jpg'},
            {'type': 'image', 'url': 'https://cdn.test/album.jpg'},
            {'type': 'image', 'url': 'https://cdn.test/large-cover.jpg'},
        ])
        self.assertTrue(item['tg']['video_unavailable'])
        (self.dir / 'media/tnews365/101_1.webp').unlink()
        item = self.by_source(self.run_collect(tgmeta={'tnews365/101': meta[101]}))['tnews365'][0]
        self.assertEqual(item['image'], {'url': 'https://cdn.test/cover.jpg'})

    def test_db_opened_read_only(self):
        before = hashlib.sha256(self.db.read_bytes()).hexdigest()
        self.run_collect()
        self.assertEqual(hashlib.sha256(self.db.read_bytes()).hexdigest(), before)
        self.assertFalse(Path(str(self.db) + '-journal').exists())

    def test_feeds_and_trending_parsed_with_14_day_image_rule(self):
        env = self.run_collect(fetch=True, http_get=fake_http())
        items = self.by_source(env)
        bbc = items['bbc-world']
        self.assertEqual([i['title'] for i in bbc], ['Fresh headline'])  # 10-18 那条在 14 天窗口外
        self.assertEqual(bbc[0]['image'], {'url': 'https://example.com/fresh.jpg'})
        self.assertEqual((bbc[0]['lang'], bbc[0]['translated']), ('en', False))
        self.assertEqual(items['apple-newsroom'][0]['channel'], 'digital')
        self.assertEqual(items['google-blog'][0]['url'], 'https://example.com/post-1')
        trending = items['github-trending']
        self.assertEqual(len(trending), 2)
        self.assertTrue(all(i['url'].startswith('https://github.com/') and i['channel'] == 'tools' for i in trending))
        self.assertIn('stars today', trending[0]['body'])

    def test_one_feed_failure_isolated_and_cache_used_without_fetch(self):
        self.run_collect(fetch=True, http_get=fake_http())  # 先写缓存
        env = self.run_collect(fetch=True, http_get=fake_http(fail={'bbc-world'}))
        status = {s['id']: s for s in env['sources']}
        self.assertEqual(status['bbc-world']['status'], 'error')
        self.assertEqual(status['guardian-world']['status'], 'ok')
        self.assertEqual((status['bbc-world']['count'], status['bbc-world']['run_count']), (1, 0))
        self.assertEqual((status['guardian-world']['count'], status['guardian-world']['run_count']), (1, 1))
        offline = {s['id']: s for s in self.run_collect()['sources']}
        self.assertEqual(offline['openai-blog']['status'], 'cached')
        self.assertIsNone(offline['openai-blog']['run_count'])

    def test_cache_write_failure_preserves_fresh_items_and_reports_safe_warning(self):
        from rebang.ingest import core
        from rebang.site.health import build_health

        original_write = core._write_json
        fetch = fake_http()

        def updated(url, now):
            return fetch(url, now).replace(b'Fresh headline', b'New headline')

        def write(path, data):
            if path.name == 'bbc-world.json':
                raise OSError('/private/do-not-publish')
            return original_write(path, data)

        for with_cache in (False, True):
            with self.subTest(with_cache=with_cache):
                if with_cache:
                    self.run_collect(fetch=True, http_get=fetch)
                with patch.object(core, '_write_json', write):
                    result = self.run_collect(fetch=True, http_get=updated)
                self.assertEqual([i['title'] for i in self.by_source(result).get('bbc-world', [])], ['New headline'])
                snapshot = build_health([('ingest.json', result)], result['items'], NOW)
                row = next(s for s in snapshot['sources'] if s['id'] == 'bbc-world')
                self.assertEqual((row['status'], row['run_count'], row['reason']), ('ok', 1, '本轮数据已采集，缓存写入失败'))
                self.assertNotIn('/private/', json.dumps(snapshot))

    def test_read_only_cache_preserves_fresh_collection(self):
        self.cache.mkdir(mode=0o555)
        def get(url, now):
            if url in FEEDS:
                return fake_http()(url, now)
            return ('<article><p>' + 'A full article sentence with enough detail. ' * 80 + '</p></article>').encode()

        def save_translator():
            (self.cache / 'pending.json').write_text('{}')

        try:
            env = self.run_collect(fetch=True, http_get=get, translator=(
                lambda texts, src: ['译文'] * len(texts), 'fixture', save_translator))
        finally:
            self.cache.chmod(0o755)
        bbc = self.by_source(env)['bbc-world'][0]
        self.assertEqual(bbc['title'], 'Fresh headline')
        self.assertTrue(bbc['translated'])
        self.assertGreater(env['extraction']['applied'], 0)
        self.assertEqual(next(s for s in env['sources'] if s['id'] == 'bbc-world')['status'], 'ok')
        self.assertEqual(list(self.cache.iterdir()), [])

    def test_no_fetch_without_cache_reports_not_fetched(self):
        env = self.run_collect()
        status = {s['id']: s for s in env['sources']}
        for sid in ('bbc-world', 'guardian-world', 'google-blog', 'openai-blog', 'github-blog', 'apple-newsroom',
                    'github-trending'):
            self.assertEqual((status[sid]['status'], status[sid]['count']), ('not_fetched', 0))

    def test_collection_leaves_highlights_to_site_build(self):
        with patch.object(self, 'loader') as loader:
            env = self.run_collect()
        loader.assert_called_once_with('hot-daily')
        items = {i['id']: i for i in env['items']}
        self.assertIn('tnews365:101', items)
        self.assertFalse(any('highlight' in i or 'highlight_date' in i for i in items.values()))
        self.assertFalse(any(i['source_id'] == 'hot-daily' for i in items.values()))
        self.assertFalse(any(s['id'] == 'hot-daily' for s in env['sources']))

    def test_leading_bare_urls_stripped_from_summary_only(self):
        from rebang.ingest.core import strip_leading_urls
        self.assertEqual(strip_leading_urls('https://a.b/c  http://d.e 正文开始 https://x.y'), '正文开始 https://x.y')
        self.assertEqual(strip_leading_urls('正文 https://a.b'), '正文 https://a.b')

    def test_translation_interface(self):
        calls = []

        def fake(texts, src):
            calls.append((len(texts), src))
            return [{'Fresh headline': '合成新标题', 'Fresh summary text.': '合成新摘要。'}.get(t, '合成中文译文。')
                    for t in texts]
        env = self.run_collect(fetch=True, http_get=fake_http(), translator=(fake, 'fake-mt'))
        self.assertEqual(validate_items_envelope(env), [])
        bbc = self.by_source(env)['bbc-world'][0]
        self.assertTrue(bbc['translated'])
        self.assertEqual(bbc['translation']['title'], '合成新标题')
        self.assertEqual(bbc['translation']['summary'], '合成新摘要。')
        self.assertEqual(bbc['translation']['engine'], 'fake-mt')
        self.assertEqual(bbc['translation']['label'], '机器翻译')
        # 摘要即正文时会同时译 body，或从正文译文截出摘要
        if 'body' in bbc['translation']:
            self.assertEqual(bbc['translation']['body'], '合成新摘要。')
        trending = self.by_source(env)['github-trending'][0]
        self.assertEqual(trending['translation']['title'], trending['title'])  # 仓库名不翻
        self.assertFalse(any(i['translated'] for i in env['items'] if i['lang'] == 'zh'))
        n = len(calls)
        self.run_collect(fetch=True, http_get=fake_http(), translator=(fake, 'fake-mt'))
        self.assertEqual(len(calls), n)  # 第二次全走缓存，不重复翻


    def test_chinese_trending_description_keeps_repository_metadata_without_translation(self):
        page = '''<article class="Box-row">
          <h2><a href="/example/project">example/project</a></h2>
          <p>这是一个中文工具。</p>
          <span itemprop="programmingLanguage">Python</span>
          <span class="d-inline-block float-sm-right">1,200 stars today</span>
        </article><article class="Box-row">
          <h2><a href="/example/other">example/other</a></h2>
          <p>这是另一个中文工具。</p>
        </article>'''
        get = fake_http()
        calls = []

        def http_get(url, now):
            return page.encode() if FEEDS[url]['id'] == 'github-trending' else get(url, now)

        def fake(texts, src):
            calls.extend(texts)
            return ['合成译文。'] * len(texts)

        for options in ({'fetch': True, 'http_get': http_get}, {}):
            env = self.run_collect(translator=(fake, 'fixture'), **options)
            self.assertEqual(validate_items_envelope(env), [])
            first, second = self.by_source(env)['github-trending']
            self.assertEqual((first['lang'], first['translated']), ('zh', False))
            self.assertEqual(first['body'], '这是一个中文工具。\n编程语言：Python · 今日新增 1,200 星')
            self.assertEqual((second['lang'], second['translated']), ('zh', False))
        self.assertFalse(any('中文工具' in text or 'stars today' in text for text in calls))

    def test_trending_language_untranslated_total_and_pending_agree(self):
        from rebang.chinese_news import needs_translation, public_item
        from rebang.translate import Cache, Translator, list_pending

        english = 'This project provides a command line tool.'
        meta = 'Python · 1 star today'
        cases = [
            ('metadata-only', '', meta, 'zh'),
            ('chinese', '这是一个中文工具。', meta, 'zh'),
            ('english', english, meta, 'en'),
            ('repo-only', '', '', 'zh'),
        ]
        entries = [dict(id=f'example/{repo}', title=f'example/{repo}', url=f'https://github.com/example/{repo}',
                        ts=NOW.isoformat(), summary=summary, meta=metadata)
                   for repo, summary, metadata, _ in cases]
        self.cache.mkdir()
        (self.cache / 'github-trending.json').write_text(
            json.dumps({'fetched_at': NOW.isoformat(), 'entries': entries}), encoding='utf-8')
        translation_cache = self.cache / 'fields.json'
        translator = Translator('cache', cache=Cache(translation_cache))
        env = collect(NOW, db=self.dir / 'missing.db', cache=self.cache, inbox_loader=self.loader,
                      translator=(translator.translate_detailed, translator.engine, translator.save))
        self.assertEqual(validate_items_envelope(env), [])
        self.assertEqual(len(env['items']), len(cases))
        items = {item['title']: item for item in env['items']}
        for repo, _, _, expected_lang in cases:
            item = items[f'example/{repo}']
            with self.subTest(repo=repo):
                needs_zh = expected_lang == 'en'
                self.assertEqual(needs_translation(item), needs_zh)
                self.assertEqual(public_item(item) is None, needs_zh)
                self.assertEqual(item['lang'], expected_lang)
        self.assertEqual(items['example/metadata-only']['body'], '编程语言：Python · 今日新增 1 星')
        self.assertEqual(env['translation']['untranslated'], 1)
        pending = {(row['src'], row['kind']) for row in list_pending(Cache(translation_cache))}
        self.assertEqual(pending, {(english, 'summary'), (f'{english}\n{meta}', 'body')})

    def test_trending_summary_only_translation_still_counts_pending_body(self):
        english = 'This project provides a command line tool.'
        entries = [dict(id='example/partial', title='example/partial', url='https://github.com/example/partial',
                        ts=NOW.isoformat(), summary=english, meta='Python · 1 star today')]
        self.cache.mkdir()
        (self.cache / 'github-trending.json').write_text(
            json.dumps({'fetched_at': NOW.isoformat(), 'entries': entries}), encoding='utf-8')

        def summary_only(texts, src, kinds=None):
            return ['合成中文摘要。' if kind and kind.endswith('summary') else None for kind in (kinds or [None] * len(texts))]

        env = collect(NOW, db=self.dir / 'missing.db', cache=self.cache, inbox_loader=self.loader,
                      translator=(summary_only, 'fixture'))
        self.assertEqual(validate_items_envelope(env), [])
        item, = env['items']
        self.assertTrue(item['translation']['body_pending'])
        self.assertEqual(env['translation']['untranslated'], 1)

    def test_partial_translation_title_without_body(self):
        from rebang.ingest.core import apply_translation
        body = 'Short summary here. ' + ('Long English paragraph. ' * 80)
        items = [{
            'id': 'bbc-world:1', 'source_id': 'bbc-world', 'title': 'Hello world title',
            'summary': 'Short summary here.', 'body': body,
            'blocks': [{'type': 'p', 'text': 'Long English paragraph. ' * 80}],
            'lang': 'en', 'translated': False,
        }]
        def fake(texts, src, kinds=None):
            if any(len(t) > 80 for t in texts):
                return None
            return ['译：' + t for t in texts]
        n = apply_translation(items, (fake, 'fake-mt'))
        self.assertEqual(n, 1)
        self.assertTrue(items[0]['translated'])
        trans = items[0]['translation']
        self.assertEqual(trans['title'], '译：Hello world title')
        self.assertEqual(trans['summary'], '译：Short summary here.')
        self.assertTrue(trans.get('body_pending'))
        self.assertNotIn('body', trans)
        self.assertNotIn('blocks', trans)
        # 正文补上之后去掉 body_pending，摘要可从正文译文截出
        def later(texts, src, kinds=None):
            return ['译：' + t for t in texts]
        apply_translation(items, (later, 'fake-mt'))
        trans = items[0]['translation']
        self.assertFalse(trans.get('body_pending'))
        self.assertTrue(trans['body'].startswith('译：'))
        self.assertIn('blocks', trans)

    def test_translator_failure_leaves_untranslated(self):
        env = self.run_collect(fetch=True, http_get=fake_http(), translator=(lambda t, s: None, 'x'))
        self.assertFalse(any(i.get('translated') for i in env['items']))
        self.assertEqual(validate_items_envelope(env), [])

    def test_cli_no_fetch_writes_valid_file(self):
        out = self.dir / 'in' / 'ingest.json'
        with redirect_stdout(io.StringIO()):
            code = cli.main(['--db', str(self.db), '--out', str(out), '--cache', str(self.cache), '--no-fetch',
                             '--now', NOW.isoformat()])
        self.assertEqual(code, 0)
        self.assertEqual(validate_items_envelope(json.loads(out.read_text(encoding='utf-8'))), [])


class ParserTests(unittest.TestCase):
    def test_split_tg_text(self):
        self.assertEqual(split_tg_text('短标题\n正文'), ('短标题', '正文'))
        self.assertEqual(split_tg_text('【括号标题】正文'), ('括号标题', '正文'))
        long = '这是一条很长很长的消息，' * 10
        title, rest = split_tg_text(long)
        self.assertTrue(title.endswith('，') or title.endswith('…'))
        self.assertLessEqual(len(title), 61)

    def test_parse_feed_and_trending_fixtures(self):
        self.assertEqual(len(parse_feed((FIX / 'feed-rss.xml').read_bytes())), 2)
        self.assertEqual([e['id'] for e in parse_trending((FIX / 'trending.html').read_text(), NOW)][:1],
                         ['backnotprop/plannotator'])
        with self.assertRaises(ValueError):
            parse_trending('<html><body>login</body></html>', NOW)


if __name__ == '__main__':
    unittest.main()
