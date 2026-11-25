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


BAD_RSS = b'''<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel><title>MacRumors</title>
<item><title>Bad thumbnail keeps the story</title><link>https://www.macrumors.com/2026/11/25/bad-thumb/</link>
<guid>bad-thumb</guid><pubDate>Wed, 25 Nov 2026 08:00:00 +0000</pubDate>
<description>Story with a broken image address.</description><enclosure url="https://" type="image/jpeg"/></item>
<item><title>Broken link is dropped</title><link>https:///2026/11/25/no-host/</link>
<guid>bad-link</guid><pubDate>Wed, 25 Nov 2026 07:00:00 +0000</pubDate><description>No host.</description></item>
<item><title>Healthy story</title><link>https://www.macrumors.com/2026/11/25/ok/</link>
<guid>ok</guid><pubDate>Wed, 25 Nov 2026 06:00:00 +0000</pubDate><description>Fine.</description>
<enclosure url="https://images.macrumors.com/ok.jpg" type="image/jpeg"/></item>
</channel></rss>'''


class BrokenEntryTests(unittest.TestCase):
    """一条坏缩略图/坏链接不能让入库命令整包校验失败、把其他来源一起拖下去。"""

    def run_cli(self, tmp, *extra):
        from unittest.mock import patch
        from rebang.ingest import __main__ as cli
        from rebang.ingest import core
        import io
        import json
        from contextlib import redirect_stdout
        by_url = {url: sid for sid, (_, url) in NEW.items()}

        def http_get(url, now):   # 只回离线样本；其他地址（老来源、正文抽取）一律当网络失败
            if by_url.get(url) == 'macrumors':
                return BAD_RSS
            if url in by_url:
                return (FIX / f'{by_url[url]}.xml').read_bytes()
            raise OSError('offline')

        out = tmp / 'ingest.json'
        env = {'REBANG_TRANSLATE_CACHE': str(tmp / 'translate' / 'cache.json')}
        with patch.object(core, 'default_http_get', http_get), \
                patch.object(core, 'default_inbox_loader', lambda sid: []), \
                patch.dict('os.environ', env), redirect_stdout(io.StringIO()):
            code = cli.main(['--db', str(tmp / 'missing-tg.db'), '--out', str(out), '--cache', str(tmp / 'cache'),
                             '--no-tgmeta', '--now', NOW.isoformat(), *extra])
        return code, (json.loads(out.read_text(encoding='utf-8')) if out.exists() else None)

    def check(self, code, envelope):
        self.assertEqual(code, 0)
        self.assertEqual(validate_items_envelope(envelope), [])
        by_source = {}
        for item in envelope['items']:
            by_source.setdefault(item['source_id'], []).append(item)
        for sid in NEW:   # 其他新来源照常产出
            if sid != 'macrumors':
                self.assertEqual(len(by_source.get(sid, [])), 2, sid)
        mac = {i['id']: i for i in by_source['macrumors']}
        self.assertEqual(set(mac), {'macrumors:bad-thumb', 'macrumors:ok'})   # 坏链接那条丢了
        self.assertIsNone(mac['macrumors:bad-thumb']['image'])                 # 坏图丢掉，条目保留
        self.assertEqual(mac['macrumors:ok']['image'], {'url': 'https://images.macrumors.com/ok.jpg'})

    def test_cli_fetch_survives_bad_thumbnail_and_bad_link(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.check(*self.run_cli(Path(tmp)))

    def test_cli_no_fetch_survives_poisoned_cache(self):
        """缓存里已存了坏图/坏链接（旧版本写入的）：只读缓存的一轮同样不被卡住。"""
        import json
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            self.run_cli(tmp)
            path = tmp / 'cache' / 'macrumors.json'
            cached = json.loads(path.read_text(encoding='utf-8'))
            cached['entries'] = [dict(e, image='https://') if e['id'] == 'bad-thumb' else e for e in cached['entries']]
            cached['entries'].append({'id': 'bad-link', 'ts': '2026-11-25T15:00:00+08:00', 'title': 'Broken link',
                                      'summary': '', 'url': 'https://[broken', 'image': None})
            path.write_text(json.dumps(cached), encoding='utf-8')
            self.check(*self.run_cli(tmp, '--no-fetch'))

    def test_parse_feed_skips_bad_image_for_next_good_one(self):
        from rebang.ingest.core import _valid_http
        for bad in ('https://', 'https:///x.jpg', 'https://[::1', 'ftp://h/x.jpg', '', None, 'javascript:alert(1)'):
            self.assertFalse(_valid_http(bad), bad)
        self.assertTrue(_valid_http('https://img.example.com/a.jpg'))
        entries = {e['id']: e for e in parse_feed(BAD_RSS)}
        self.assertIsNone(entries['bad-thumb']['image'])
        self.assertEqual(entries['ok']['image'], 'https://images.macrumors.com/ok.jpg')


MIXED_RSS = '''<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel><title>CNA</title>
<item><title>中国外交部回应美方关税措施</title><link>https://www.channelnewsasia.com/zh-1</link><guid>zh-1</guid>
<pubDate>Wed, 25 Nov 2026 08:00:00 +0000</pubDate><description>外交部发言人在例行记者会上表示，中方将采取必要措施。</description></item>
<item><title>苹果发布 iPhone 新品</title><link>https://www.channelnewsasia.com/zh-2</link><guid>zh-2</guid>
<pubDate>Wed, 25 Nov 2026 07:30:00 +0000</pubDate><description>苹果公司今天在加州发布会上推出了新款手机。</description></item>
<item><title>Xi meets Lee in Beijing</title><link>https://www.channelnewsasia.com/en-1</link><guid>en-1</guid>
<pubDate>Wed, 25 Nov 2026 07:00:00 +0000</pubDate>
<description>Chinese President Xi Jinping (习近平) met Singapore Prime Minister Lawrence Wong on Tuesday to discuss trade.</description></item>
</channel></rss>'''.encode('utf-8')


class MixedLanguageTests(unittest.TestCase):
    def test_mostly_chinese_rule(self):
        from rebang.ingest.core import mostly_chinese
        self.assertTrue(mostly_chinese('中国外交部回应美方关税措施'))
        self.assertTrue(mostly_chinese('苹果发布 iPhone 新品', ''))
        self.assertFalse(mostly_chinese('Xi meets Lee', 'President Xi Jinping (习近平) met the prime minister'))
        self.assertFalse(mostly_chinese('Plain English headline', ''))
        self.assertFalse(mostly_chinese('', ''))

    def test_chinese_entries_skip_translation_queue(self):
        """真实 rebang.translate 缓存（离线、只写临时目录）：中文条不进 pending，英文条进。"""
        import json
        from rebang.ingest.core import apply_translation
        from rebang.translate import Cache, Translator
        rows = configured()
        sources = [(rows['cna-world'][0], rows['cna-world'][1])]
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            items, _ = remote_items(sources, NOW, NOW - timedelta(days=14), fetch=True, cache=tmp / 'ingest',
                                    http_get=lambda url, now: MIXED_RSS)
            lang = {i['id']: i['lang'] for i in items}
            self.assertEqual(lang, {'cna-world:zh-1': 'zh', 'cna-world:zh-2': 'zh', 'cna-world:en-1': 'en'})
            tr = Translator(engine='cache', cache=Cache(tmp / 'translate' / 'cache.json'))
            apply_translation(items, (lambda texts, src: tr.translate_detailed(texts, src), tr.engine, tr.save),
                              tmp / 'ingest')
            pending = json.loads((tmp / 'translate' / 'pending.json').read_text(encoding='utf-8'))['pending']
        queued = {rec['src'] for rec in pending.values()}
        self.assertIn('Xi meets Lee in Beijing', queued)
        self.assertFalse(any(_has_cjk_only(src) for src in queued), queued)
        self.assertNotIn('中国外交部回应美方关税措施', queued)
        self.assertNotIn('苹果发布 iPhone 新品', queued)
        envelope = {'schema': ITEMS_SCHEMA, 'producer': 'ingest', 'generated_at': NOW.isoformat(), 'items': items}
        self.assertEqual(validate_items_envelope(envelope), [])


def _has_cjk_only(text):
    from rebang.ingest.core import mostly_chinese
    return mostly_chinese(text)


if __name__ == '__main__':
    unittest.main()
