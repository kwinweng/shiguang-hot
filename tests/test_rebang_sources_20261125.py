"""2026-11-25 阿欢确认的 8 个免登录官方订阅 + 撤掉知乎博主占位。只用离线样本，不联网。

样本来自 2026-11-25 用 curl 只读拉的一次真实订阅，每源留前 2 条、去掉正文全文（`tests/fixtures/rebang/ingest/sources-20261125/`）。
"""
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from rebang.contract import ITEMS_SCHEMA, load_bloggers, load_channels, source_channel, validate_items_envelope
from rebang.ingest.core import parse_feed, remote_items

ROOT = Path(__file__).resolve().parents[1]
FIX = ROOT / 'tests/fixtures/rebang/ingest/sources-20261125'
NOW = datetime(2026, 11, 25, 19, 0, tzinfo=ZoneInfo('Asia/Shanghai'))

NEW = {
    'cna-world': ('world', 'https://www.channelnewsasia.com/api/v1/rss-outbound-feed?_format=xml&category=6311'),
    'france24-en': ('world', 'https://www.france24.com/en/rss'),
    'dw-world': ('world', 'https://rss.dw.com/xml/rss-en-world'),
    'npr-world': ('world', 'https://feeds.npr.org/1004/rss.xml'),
    'android-authority': ('digital', 'https://www.androidauthority.com/feed/'),
    'macrumors': ('digital', 'https://feeds.macrumors.com/MacRumors-All'),
    'selfhst': ('tools', 'https://selfh.st/rss/'),
    'itsfoss': ('tools', 'https://itsfoss.com/rss/'),
}


def configured():
    return {s['id']: (c['slug'], s) for c in load_channels()['channels'] for s in c['sources']}


class NewSourceConfigTests(unittest.TestCase):
    def test_each_new_source_is_a_feed_in_one_channel(self):
        rows = configured()
        for sid, (slug, url) in NEW.items():
            with self.subTest(sid=sid):
                self.assertEqual(source_channel(sid), slug)
                self.assertEqual(rows[sid][1]['type'], 'feed')
                self.assertEqual(rows[sid][1]['url'], url)

    def test_world_keeps_bbc_and_guardian_first(self):
        world = [s['id'] for c in load_channels()['channels'] if c['slug'] == 'world' for s in c['sources']]
        self.assertEqual(world, ['bbc-world', 'guardian-world', 'cna-world', 'france24-en', 'dw-world', 'npr-world'])

    def test_feed_urls_unique(self):
        urls = [s['url'] for _, s in configured().values() if s['type'] in ('feed', 'page')]
        self.assertEqual(len(urls), len(set(urls)))

    def test_zhihu_blogger_placeholder_removed(self):
        self.assertNotIn('zhihu', [p['id'] for p in load_bloggers()['platforms']])
        from rebang.bloggers.run import ALL_PLATFORMS
        self.assertEqual(set(ALL_PLATFORMS), {p['id'] for p in load_bloggers()['platforms']})


class NewSourceFixtureTests(unittest.TestCase):
    def test_each_sample_parses(self):
        for sid in NEW:
            with self.subTest(sid=sid):
                entries = parse_feed((FIX / f'{sid}.xml').read_bytes())
                self.assertEqual(len(entries), 2)
                for e in entries:
                    self.assertTrue(e['title'].strip())
                    self.assertTrue(e['url'].startswith('https://'))
                    self.assertIsNotNone(datetime.fromisoformat(e['ts']).tzinfo)
                    self.assertTrue(e['id'])

    def test_remote_items_produce_valid_news_in_their_channel(self):
        rows = configured()
        sources = [(rows[sid][0], rows[sid][1]) for sid in NEW]
        by_url = {url: sid for sid, (_, url) in NEW.items()}

        def http_get(url, now):
            return (FIX / f'{by_url[url]}.xml').read_bytes()

        with tempfile.TemporaryDirectory() as tmp:
            items, statuses = remote_items(sources, NOW, NOW - timedelta(days=14), fetch=True, cache=Path(tmp),
                                           http_get=http_get)
            # 第二轮不联网：走缓存，条目不丢
            cached, cached_status = remote_items(sources, NOW, NOW - timedelta(days=14), fetch=False, cache=Path(tmp),
                                                 http_get=None)
        self.assertEqual({s['id']: s['status'] for s in statuses}, {sid: 'ok' for sid in NEW})
        self.assertEqual({s['id']: s['status'] for s in cached_status}, {sid: 'cached' for sid in NEW})
        self.assertEqual(len(cached), len(items))
        self.assertEqual(len(items), 16)
        for item in items:
            self.assertEqual(item['channel'], NEW[item['source_id']][0])
            self.assertEqual(item['lang'], 'en')
            self.assertTrue(item['id'].startswith(item['source_id'] + ':'))
        self.assertEqual(len({i['id'] for i in items}), len(items))
        envelope = {'schema': ITEMS_SCHEMA, 'producer': 'ingest', 'generated_at': NOW.isoformat(), 'items': items}
        self.assertEqual(validate_items_envelope(envelope), [])

    def test_one_new_feed_failing_does_not_affect_others(self):
        rows = configured()
        sources = [(rows[sid][0], rows[sid][1]) for sid in NEW]
        by_url = {url: sid for sid, (_, url) in NEW.items()}

        def http_get(url, now):
            if by_url[url] == 'dw-world':
                raise OSError('network')
            return (FIX / f'{by_url[url]}.xml').read_bytes()

        with tempfile.TemporaryDirectory() as tmp:
            items, statuses = remote_items(sources, NOW, NOW - timedelta(days=14), fetch=True, cache=Path(tmp),
                                           http_get=http_get)
        status = {s['id']: s['status'] for s in statuses}
        self.assertEqual(status.pop('dw-world'), 'error')
        self.assertEqual(set(status.values()), {'ok'})
        self.assertNotIn('dw-world', {i['source_id'] for i in items})


BAD_RSS = b"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel><title>MacRumors</title>
<item><title>Bad thumbnail keeps the story</title><link>https://www.macrumors.com/2026/11/25/bad-thumb/</link>
<guid>bad-thumb</guid><pubDate>Wed, 25 Nov 2026 08:00:00 +0000</pubDate>
<description>Story with a broken image address.</description><enclosure url="https://" type="image/jpeg"/></item>
<item><title>Broken link keeps the story</title><link>https:///2026/11/25/no-host/</link>
<guid>bad-link</guid><pubDate>Wed, 25 Nov 2026 07:00:00 +0000</pubDate><description>No host.</description></item>
<item><title>Healthy story</title><link>https://www.macrumors.com/2026/11/25/ok/</link>
<guid>ok</guid><pubDate>Wed, 25 Nov 2026 06:00:00 +0000</pubDate><description>Fine.</description>
<enclosure url="https://images.macrumors.com/ok.jpg" type="image/jpeg"/></item>
</channel></rss>"""

# 合法 Atom：相对链接靠 xml:base（feed 级、entry 级叠加）或订阅自身地址补全；补不出合格地址的置空，条目都保留
ATOM_REL = b"""<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom" xml:base="https://news.example.org/"><title>NPR</title>
<entry><id>rel-root</id><title>Root relative story</title><link href="/world/story"/>
<updated>2026-11-25T08:00:00Z</updated><summary>Relative href with feed xml:base.</summary></entry>
<entry xml:base="section/"><id>rel-entry</id><title>Entry base story</title><link rel="alternate" href="a.html"/>
<updated>2026-11-25T07:30:00Z</updated><summary>Entry level xml:base stacks on the feed one.</summary></entry>
<entry><id>abs</id><title>Absolute story</title><link href="https://other.example.com/x"/>
<updated>2026-11-25T07:00:00Z</updated><summary>Already absolute.</summary></entry>
<entry><id>js</id><title>Script link story</title><link href="javascript:alert(1)"/>
<updated>2026-11-25T06:30:00Z</updated><summary>Unusable link.</summary></entry>
</feed>"""
ATOM_NO_BASE = b"""<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom"><title>NPR</title>
<entry><id>feed-url</id><title>Resolved against feed URL</title><link href="/2026/11/25/story"/>
<updated>2026-11-25T08:00:00Z</updated><summary>No xml:base at all.</summary></entry>
</feed>"""

MIXED_RSS = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel><title>CNA</title>
<item><title>中国外交部回应美方关税措施</title><link>https://www.channelnewsasia.com/zh-1</link><guid>zh-1</guid>
<pubDate>Wed, 25 Nov 2026 08:00:00 +0000</pubDate><description>外交部发言人在例行记者会上表示，中方将采取必要措施。</description></item>
<item><title>MacBook Pro M4 Max 评测</title><link>https://www.channelnewsasia.com/zh-2</link><guid>zh-2</guid>
<pubDate>Wed, 25 Nov 2026 07:50:00 +0000</pubDate><description>Apple M4 Max benchmark results and battery life tests.</description></item>
<item><title>震后救援</title><link>https://www.channelnewsasia.com/zh-3</link><guid>zh-3</guid>
<pubDate>Wed, 25 Nov 2026 07:40:00 +0000</pubDate><description>https://www.channelnewsasia.com/zh-3</description></item>
<item><title>Review of 《黑神话：悟空》</title><link>https://www.channelnewsasia.com/en-2</link><guid>en-2</guid>
<pubDate>Wed, 25 Nov 2026 07:30:00 +0000</pubDate><description>游戏科学 action RPG, reviewed.</description></item>
<item><title>Xi meets Lee in Beijing</title><link>https://www.channelnewsasia.com/en-1</link><guid>en-1</guid>
<pubDate>Wed, 25 Nov 2026 07:00:00 +0000</pubDate>
<description>中国国家主席习近平在北京会见新加坡总理黄循财，双方讨论贸易。</description></item>
</channel></rss>""".encode('utf-8')

ZH_IDS = {'cna-world:zh-1', 'cna-world:zh-2', 'cna-world:zh-3'}
EN_IDS = {'cna-world:en-1', 'cna-world:en-2'}


class IngestCliEdgeTests(unittest.TestCase):
    """从入库命令入口验证：坏图只丢图、坏链接/相对链接不丢条、按标题判语言、中文条不进待翻队列。"""

    FEEDS = {'macrumors': BAD_RSS, 'npr-world': ATOM_REL, 'dw-world': ATOM_NO_BASE, 'cna-world': MIXED_RSS}

    def run_cli(self, tmp, *extra):
        from unittest.mock import patch
        from rebang.ingest import __main__ as cli
        from rebang.ingest import core
        import io
        import json
        from contextlib import redirect_stdout
        by_url = {url: sid for sid, (_, url) in NEW.items()}

        def http_get(url, now):   # 只回离线样本；其他地址（老来源、正文抽取）一律当网络失败
            sid = by_url.get(url)
            if sid in self.FEEDS:
                return self.FEEDS[sid]
            if sid:
                return (FIX / f'{sid}.xml').read_bytes()
            raise OSError('offline')

        out = tmp / 'ingest.json'
        env = {'REBANG_TRANSLATE_CACHE': str(tmp / 'translate' / 'cache.json')}
        with patch.object(core, 'default_http_get', http_get), \
                patch.dict('os.environ', env), redirect_stdout(io.StringIO()):
            code = cli.main(['--db', str(tmp / 'missing-tg.db'), '--out', str(out), '--cache', str(tmp / 'cache'),
                             '--no-tgmeta', '--now', NOW.isoformat(), *extra])
        envelope = json.loads(out.read_text(encoding='utf-8')) if out.exists() else None
        pending_path = tmp / 'translate' / 'pending.json'
        pending = json.loads(pending_path.read_text(encoding='utf-8'))['pending'] if pending_path.exists() else {}
        return code, envelope, {rec['src'] for rec in pending.values()}

    def by_id(self, envelope):
        return {i['id']: i for i in envelope['items']}

    def check_common(self, code, envelope):
        self.assertEqual(code, 0)
        self.assertEqual(validate_items_envelope(envelope), [])
        counts = {}
        for item in envelope['items']:
            counts[item['source_id']] = counts.get(item['source_id'], 0) + 1
        for sid in NEW:   # 其他新来源照常产出
            if sid not in self.FEEDS:
                self.assertEqual(counts.get(sid), 2, sid)
        items = self.by_id(envelope)
        self.assertLessEqual({'macrumors:bad-thumb', 'macrumors:bad-link', 'macrumors:ok'},
                             {k for k in items if k.startswith('macrumors:')})
        self.assertIsNone(items['macrumors:bad-thumb']['image'])                 # 坏图丢掉，条目保留
        self.assertEqual(items['macrumors:bad-thumb']['url'], 'https://www.macrumors.com/2026/11/25/bad-thumb/')
        self.assertEqual(items['macrumors:bad-link']['url'], '')                 # 坏链接置空，条目保留
        self.assertEqual(items['macrumors:ok']['image'], {'url': 'https://images.macrumors.com/ok.jpg'})
        self.assertEqual({k for k in items if k.startswith('npr-world:')},
                         {'npr-world:rel-root', 'npr-world:rel-entry', 'npr-world:abs', 'npr-world:js'})
        self.assertEqual(items['npr-world:abs']['url'], 'https://other.example.com/x')
        self.assertEqual(items['npr-world:js']['url'], '')
        self.assertIn('dw-world:feed-url', items)
        return items

    def check_lang(self, items, queued):
        lang = {k: v['lang'] for k, v in items.items() if k.startswith('cna-world:')}
        self.assertEqual(lang, {**{k: 'zh' for k in ZH_IDS}, **{k: 'en' for k in EN_IDS}})
        self.assertIn('Review of 《黑神话：悟空》', queued)
        self.assertIn('Xi meets Lee in Beijing', queued)
        for zh in ('中国外交部回应美方关税措施', 'MacBook Pro M4 Max 评测', '震后救援',
                   'Apple M4 Max benchmark results and battery life tests.'):
            self.assertNotIn(zh, queued)

    def test_cli_fetch(self):
        with tempfile.TemporaryDirectory() as tmp:
            code, envelope, queued = self.run_cli(Path(tmp))
        items = self.check_common(code, envelope)
        self.assertEqual(items['npr-world:rel-root']['url'], 'https://news.example.org/world/story')
        self.assertEqual(items['npr-world:rel-entry']['url'], 'https://news.example.org/section/a.html')
        self.assertEqual(items['dw-world:feed-url']['url'], 'https://rss.dw.com/2026/11/25/story')
        self.check_lang(items, queued)

    def test_cli_no_fetch_reads_old_cache(self):
        """旧版本写入的缓存：存着相对链接（没有基准地址）、坏图、坏链接。只读缓存的一轮置空链接、保留条目。"""
        import json
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            self.run_cli(tmp)
            for sid, patch_entries in (
                    ('macrumors', lambda es: [dict(e, image='https://') if e['id'] == 'bad-thumb' else e for e in es]
                     + [{'id': 'broken-v6', 'ts': '2026-11-25T15:00:00+08:00', 'title': 'Broken IPv6 link',
                         'summary': '', 'url': 'https://[broken', 'image': None}]),
                    ('npr-world', lambda es: [dict(e, url='/world/story') if e['id'] == 'rel-root' else e for e in es])):
                path = tmp / 'cache' / f'{sid}.json'
                cached = json.loads(path.read_text(encoding='utf-8'))
                cached['entries'] = patch_entries(cached['entries'])
                path.write_text(json.dumps(cached), encoding='utf-8')
            code, envelope, queued = self.run_cli(tmp, '--no-fetch')
        items = self.check_common(code, envelope)
        self.assertEqual(items['macrumors:broken-v6']['url'], '')
        self.assertEqual(items['npr-world:rel-root']['url'], '')                  # 旧缓存没基准：置空
        self.assertEqual(items['npr-world:rel-entry']['url'], 'https://news.example.org/section/a.html')
        self.check_lang(items, queued)

    def test_parse_feed_drops_only_bad_images(self):
        from rebang.ingest.core import _valid_http
        for bad in ('https://', 'https:///x.jpg', 'https://[::1', 'ftp://h/x.jpg', '', None, 'javascript:alert(1)'):
            self.assertFalse(_valid_http(bad), bad)
        self.assertTrue(_valid_http('https://img.example.com/a.jpg'))
        entries = {e['id']: e for e in parse_feed(BAD_RSS)}
        self.assertEqual(set(entries), {'bad-thumb', 'bad-link', 'ok'})
        self.assertIsNone(entries['bad-thumb']['image'])
        self.assertEqual(entries['ok']['image'], 'https://images.macrumors.com/ok.jpg')
        rel = {e['id']: e['url'] for e in parse_feed(ATOM_REL)}   # 不给订阅地址也能用 xml:base 补全
        self.assertEqual(rel['rel-root'], 'https://news.example.org/world/story')
        self.assertEqual(parse_feed(ATOM_NO_BASE)[0]['url'], '')    # 没有任何基准：置空、条目保留


class MostlyChineseTests(unittest.TestCase):
    def test_title_only_rule(self):
        from rebang.ingest.core import mostly_chinese
        cases = {
            'Review of 《黑神话：悟空》': False,
            'MacBook Pro M4 Max 评测': True,
            '震后救援': True,
            '中国外交部回应美方关税措施': True,
            'Plain English headline': False,
            'Xi says 「合作共赢」 at summit': False,
            'Quote “你好” only': False,
            'Review of 「中文 https://example.com」 today': False,
            '“中文 https://example.com” English': False,
            'https://example.com，最新消息': True,
            '（https://example.com）最新消息': True,
            'See https://example.cn/中文 now': False,
            '': False,
            None: False,
        }
        for title, want in cases.items():
            with self.subTest(title=title):
                self.assertIs(mostly_chinese(title), want)


if __name__ == '__main__':
    unittest.main()
