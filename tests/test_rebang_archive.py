"""归档增量、北京日期边界、去重、空日期与搜索索引（不联网）。"""
import copy
import json
import tempfile
import time
import unittest
from pathlib import Path

from rebang.archive import EMPTY_MESSAGE, beijing_date, build, empty_day_payload
from rebang.contract import validate_item, validate_items_envelope

ROOT = Path(__file__).resolve().parents[1]
CONTRACT_FIX = ROOT / 'tests/fixtures/rebang/contract'
ARCHIVE_FIX = ROOT / 'tests/fixtures/rebang/archive'


def contract_items():
    return json.loads((CONTRACT_FIX / 'items-valid.json').read_text(encoding='utf-8'))


def make_item(index=0, **overrides):
    item = copy.deepcopy(contract_items()['items'][index])
    item.update(overrides)
    return item


class BeijingDateTests(unittest.TestCase):
    def test_midnight_boundary(self):
        # 2026-11-14 23:59:59 北京 = 15:59:59Z，仍算 14 日。
        self.assertEqual(beijing_date('2026-11-14T15:59:59Z'), '2026-11-14')
        self.assertEqual(beijing_date('2026-11-14T15:59:59+00:00'), '2026-11-14')
        # 2026-11-15 00:00:00 北京 = 16:00:00Z，算 15 日。
        self.assertEqual(beijing_date('2026-11-14T16:00:00Z'), '2026-11-15')
        self.assertEqual(beijing_date('2026-11-15T00:00:00+08:00'), '2026-11-15')

    def test_naive_rejected(self):
        with self.assertRaises(ValueError):
            beijing_date('2026-11-15T00:00:00')


class IncrementalArchiveTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.archive = Path(self.temp.name) / 'archive'
        self.out = Path(self.temp.name) / 'site-v11'

    def _build(self, items, **kwargs):
        return build(items, self.out, archive_dir=self.archive, generated_at='2026-11-15T20:00:00+08:00', **kwargs)

    def _day(self, date):
        return json.loads((self.archive / f'{date}.json').read_text(encoding='utf-8'))

    # 2026-11-15 21:26：按日期翻新闻的历史页去掉了，站点不再写 data/history/；按日归档本身照旧，从归档读
    def _history(self, date):
        records = self._day(date)['items']
        items = sorted(({**r['latest'], 'first_published_at': r['first']['published_at']} for r in records),
                       key=lambda it: it['published_at'], reverse=True)
        return {'count': len(items), 'items': items}

    def _index(self):
        self.assertFalse((self.out / 'data/history').exists())
        dates = sorted((p.stem for p in self.archive.glob('20*.json')), reverse=True)
        return {'dates': [{'date': d, 'count': len(self._day(d)['items'])} for d in dates]}

    def _search(self):
        return json.loads((self.out / 'data/search-index.json').read_text(encoding='utf-8'))

    def test_groups_by_beijing_date_across_midnight(self):
        early = make_item(id='tnews365:14', published_at='2026-11-14T15:59:59Z', title='十四日边界前')
        late = make_item(id='tnews365:15', published_at='2026-11-14T16:00:00Z', title='十五日零点')
        self._build([early, late])
        self.assertEqual(sorted(p.stem for p in self.archive.glob('20*.json')), ['2026-11-14', '2026-11-15'])
        self.assertEqual([it['id'] for it in self._history('2026-11-14')['items']], ['tnews365:14'])
        self.assertEqual([it['id'] for it in self._history('2026-11-15')['items']], ['tnews365:15'])
        dates = {row['date']: row['count'] for row in self._index()['dates']}
        self.assertEqual(dates, {'2026-11-14': 1, '2026-11-15': 1})

    def test_duplicate_id_keeps_first_and_latest(self):
        first = make_item(id='tnews365:1001', title='首次标题', summary='首次摘要', published_at='2026-11-15T08:00:00+08:00')
        latest = make_item(id='tnews365:1001', title='最新标题', summary='最新摘要', published_at='2026-11-15T18:00:00+08:00')
        self._build([first])
        self._build([latest])
        record = self._day('2026-11-15')['items'][0]
        self.assertEqual(record['id'], 'tnews365:1001')
        self.assertEqual(record['first']['title'], '首次标题')
        self.assertEqual(record['latest']['title'], '最新标题')
        history = self._history('2026-11-15')
        self.assertEqual(len(history['items']), 1)
        self.assertEqual(history['items'][0]['title'], '最新标题')
        self.assertEqual(history['items'][0]['first_published_at'], '2026-11-15T08:00:00+08:00')

    def test_duplicate_id_in_same_batch(self):
        first = make_item(id='tnews365:7', title='一', published_at='2026-11-15T08:00:00+08:00')
        latest = make_item(id='tnews365:7', title='二', published_at='2026-11-15T09:00:00+08:00')
        self._build([first, latest])
        record = self._day('2026-11-15')['items'][0]
        self.assertEqual(record['first']['title'], '一')
        self.assertEqual(record['latest']['title'], '二')

    def test_unchanged_day_file_not_rewritten(self):
        old = make_item(id='tnews365:13', title='十三日旧稿', published_at='2026-11-13T12:00:00+08:00')
        today = make_item(id='tnews365:15', title='十五日初稿', published_at='2026-11-15T12:00:00+08:00')
        self._build([old, today])
        old_path = self.archive / '2026-11-13.json'
        stamp = old_path.stat().st_mtime_ns
        checksum = old_path.read_bytes()
        time.sleep(0.02)
        newer = make_item(id='tnews365:15', title='十五日改稿', published_at='2026-11-15T13:00:00+08:00')
        result = self._build([newer])
        self.assertEqual(old_path.read_bytes(), checksum)
        self.assertEqual(old_path.stat().st_mtime_ns, stamp)
        self.assertIn('2026-11-15', result['updated_dates'])
        self.assertNotIn('2026-11-13', result['updated_dates'])
        self.assertEqual(self._history('2026-11-13')['items'][0]['title'], '十三日旧稿')

    def test_empty_date_payload_and_index_omits_gaps(self):
        early = make_item(id='tnews365:13', title='有内容的十三日', published_at='2026-11-13T12:00:00+08:00')
        late = make_item(id='tnews365:15', title='有内容的十五日', published_at='2026-11-15T12:00:00+08:00')
        self._build([early, late])
        dates = [row['date'] for row in self._index()['dates']]
        self.assertEqual(dates, ['2026-11-15', '2026-11-13'])
        self.assertFalse((self.archive / '2026-11-14.json').exists())
        empty = empty_day_payload('2026-11-14')
        self.assertTrue(empty['empty'])
        self.assertEqual(empty['count'], 0)
        self.assertEqual(empty['items'], [])
        self.assertEqual(empty['message'], EMPTY_MESSAGE)
        self.assertEqual(EMPTY_MESSAGE, '这天没有内容')

    def test_search_index_excludes_unpublished_and_has_no_ai_summary(self):
        published = [
            make_item(id='tnews365:1001', title='合成标题一', published_at='2026-11-15T19:00:00+08:00'),
            make_item(1, id='bbc-world:abc123', published_at='2026-11-15T11:00:00Z'),
        ]
        unpublished = make_item(id='tnews365:9999', title='未上站草稿', summary='不该出现在索引里',
                                published_at='2026-11-15T10:00:00+08:00')
        self.assertEqual(validate_item(unpublished), [])
        self._build(published)
        index = self._search()
        ids = [entry['id'] for entry in index['entries']]
        self.assertEqual(set(ids), {'tnews365:1001', 'bbc-world:abc123'})
        self.assertNotIn('tnews365:9999', ids)
        blob = json.dumps(index, ensure_ascii=False)
        self.assertNotIn('未上站草稿', blob)
        self.assertNotIn('ai_summary', blob)
        self.assertNotIn('ai-summary', blob)
        bbc = next(entry for entry in index['entries'] if entry['id'] == 'bbc-world:abc123')
        self.assertEqual(bbc['original_title'], 'Synthetic headline')
        self.assertEqual(bbc['translation_title'], '合成译文标题')
        self.assertEqual(bbc['display_title'], '合成译文标题')

    def test_build_accepts_envelope_and_keeps_existing_history(self):
        envelope = contract_items()
        self.assertEqual(validate_items_envelope(envelope), [])
        self._build(envelope)
        later = make_item(id='tnews365:2002', title='第二天追加', published_at='2026-11-16T09:00:00+08:00')
        self._build([later])
        dates = [row['date'] for row in self._index()['dates']]
        self.assertIn('2026-11-15', dates)
        self.assertIn('2026-11-16', dates)
        fifteen = self._history('2026-11-15')
        self.assertGreaterEqual(fifteen['count'], 1)
        self.assertIn('tnews365:1001', [it['id'] for it in fifteen['items']])

    def test_published_fixture_builds_search_and_history_for_harness(self):
        fixture = json.loads((ARCHIVE_FIX / 'published-items.json').read_text(encoding='utf-8'))
        self.assertEqual(validate_items_envelope({k: fixture[k] for k in ('schema', 'producer', 'generated_at', 'items')}), [])
        result = self._build(fixture['items'])
        self.assertEqual(result['search_entries'], 4)
        text = (self.out / 'data/search-index.json').read_text(encoding='utf-8')
        self.assertNotIn('未上站草稿不应出现', text)
        self.assertIn('合成标题一', text)
        self.assertIn('十三日旧闻', (self.archive / '2026-11-13.json').read_text(encoding='utf-8'))
        self.assertFalse((self.out / 'data/history').exists())


if __name__ == '__main__':
    unittest.main()
