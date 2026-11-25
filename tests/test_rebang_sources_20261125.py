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


if __name__ == '__main__':
    unittest.main()
