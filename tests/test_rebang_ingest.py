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
        offline = {s['id']: s for s in self.run_collect()['sources']}
        self.assertEqual(offline['openai-blog']['status'], 'cached')

    def test_no_fetch_without_cache_reports_not_fetched(self):
        env = self.run_collect()
        status = {s['id']: s for s in env['sources']}
        for sid in ('bbc-world', 'guardian-world', 'google-blog', 'openai-blog', 'github-blog', 'apple-newsroom',
                    'github-trending'):
            self.assertEqual((status[sid]['status'], status[sid]['count']), ('not_fetched', 0))

    def test_highlight_rule(self):
        env = self.run_collect()
        items = {i['id']: i for i in env['items']}
        self.assertTrue(items['tnews365:101']['highlight'])
        self.assertEqual(items['tnews365:101']['highlight_date'], '2026-11-14')
        self.assertFalse(any(i['source_id'] == 'hot-daily' for i in env['items']))
        hot = next(s for s in env['sources'] if s['id'] == 'hot-daily' and s.get('role') == 'highlight-marks')
        self.assertEqual((hot['marked'], hot['unmatched']), (1, 2))

    def test_leading_bare_urls_stripped_from_summary_only(self):
        from rebang.ingest.core import strip_leading_urls
        self.assertEqual(strip_leading_urls('https://a.b/c  http://d.e 正文开始 https://x.y'), '正文开始 https://x.y')
        self.assertEqual(strip_leading_urls('正文 https://a.b'), '正文 https://a.b')

    def test_translation_interface(self):
        calls = []

        def fake(texts, src):
            calls.append((len(texts), src))
            return ['译：' + t for t in texts]
        env = self.run_collect(fetch=True, http_get=fake_http(), translator=(fake, 'fake-mt'))
        self.assertEqual(validate_items_envelope(env), [])
        bbc = self.by_source(env)['bbc-world'][0]
        self.assertTrue(bbc['translated'])
        self.assertEqual(bbc['translation']['title'], '译：Fresh headline')
        self.assertEqual(bbc['translation']['summary'], '译：Fresh summary text.')
        self.assertEqual(bbc['translation']['engine'], 'fake-mt')
        self.assertEqual(bbc['translation']['label'], '机器翻译')
        # 摘要即正文时会同时译 body，或从正文译文截出摘要
        if 'body' in bbc['translation']:
            self.assertTrue(bbc['translation']['body'].startswith('译：'))
        trending = self.by_source(env)['github-trending'][0]
        self.assertEqual(trending['translation']['title'], trending['title'])  # 仓库名不翻
        self.assertFalse(any(i['translated'] for i in env['items'] if i['lang'] == 'zh'))
        n = len(calls)
        self.run_collect(fetch=True, http_get=fake_http(), translator=(fake, 'fake-mt'))
        self.assertEqual(len(calls), n)  # 第二次全走缓存，不重复翻


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
