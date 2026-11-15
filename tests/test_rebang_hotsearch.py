"""热搜适配器离线单测：三家正常样本、一家失败不影响别家、全失败仍是合法空榜。不联网。"""
import json
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

from rebang.contract import load_hotsearch, validate_hotsearch
from rebang.hotsearch import collect
from rebang.hotsearch.http import FixtureHttp, HttpResponse, ProviderError
from rebang.hotsearch.providers import baidu, bilibili, zhihu

ROOT = Path(__file__).resolve().parents[1]
FIX = ROOT / 'tests/fixtures/rebang/hotsearch'
NOW = datetime(2026, 11, 15, 20, 41, tzinfo=ZoneInfo('Asia/Shanghai'))
ENDPOINTS = {p['id']: p['endpoint'] for p in load_hotsearch()['providers']}


def load_json(name):
    return json.loads((FIX / name).read_text(encoding='utf-8'))


def ok_http(overrides=None):
    return FixtureHttp(FIX, overrides=overrides)


def text(name):
    return (FIX / name).read_text(encoding='utf-8')


class ParseSampleTests(unittest.TestCase):
    def test_baidu_sample_has_pinned_title_score_link_summary_image(self):
        items = baidu.parse(load_json('baidu.json'), cap=50)
        self.assertEqual(len(items), 50)
        top = items[0]
        self.assertEqual(top['title'], '亚太共此时')
        self.assertTrue(top['pinned'])
        self.assertEqual(top['rank'], 1)
        self.assertEqual(top['hot_score'], 7904112)
        self.assertTrue(top['url'].startswith('https://www.baidu.com/s?'))
        self.assertIn('APEC', top['summary'])
        self.assertTrue(top['image'].startswith('https://'))
        second = items[1]
        self.assertEqual(second['title'], '见识到秋假的威力了')
        self.assertFalse(second['pinned'])
        self.assertEqual(second['rank'], 2)
        self.assertLessEqual(len(items), 50)

    def test_zhihu_rewrites_question_url_and_keeps_label(self):
        items = zhihu.parse(load_json('zhihu.json'), cap=50)
        self.assertEqual(len(items), 30)
        first = items[0]
        self.assertTrue(first['title'].startswith('S16 总决赛'))
        self.assertEqual(first['url'], 'https://www.zhihu.com/question/2105016991765509602')
        self.assertEqual(first['hot_label'], '4173 万热度')
        self.assertFalse(first['pinned'])
        self.assertTrue(first.get('summary'))
        self.assertTrue(first.get('image', '').startswith('https://'))
        self.assertTrue(all(item['url'].startswith('https://www.zhihu.com/question/') for item in items))
        self.assertTrue(all('api.zhihu.com' not in item['url'] for item in items))

    def test_bilibili_links_to_site_search(self):
        items = bilibili.parse(load_json('bilibili.json'), cap=50)
        self.assertEqual(len(items), 50)
        first = items[0]
        self.assertEqual(first['title'], 'BLG夺冠')
        self.assertEqual(first['url'], 'https://search.bilibili.com/all?keyword=BLG%E5%A4%BA%E5%86%A0')
        self.assertEqual(first['hot_score'], 20375199)
        self.assertFalse(first['pinned'])
        self.assertTrue(all(item['url'].startswith('https://search.bilibili.com/all?keyword=') for item in items))


class FailureShapeTests(unittest.TestCase):
    def test_baidu_success_false(self):
        with self.assertRaises(ProviderError) as ctx:
            baidu.parse(load_json('baidu-success-false.json'))
        self.assertEqual(ctx.exception.code, 'success_false')

    def test_bilibili_nonzero_code(self):
        with self.assertRaises(ProviderError) as ctx:
            bilibili.parse(load_json('bili-code-error.json'))
        self.assertEqual(ctx.exception.code, 'code_-403')

    def test_not_json(self):
        with self.assertRaises(ProviderError) as ctx:
            HttpResponse(200, text('not-json.txt')).json()
        self.assertEqual(ctx.exception.code, 'not_json')

    def test_empty_list_is_empty_not_error(self):
        self.assertEqual(baidu.parse(load_json('baidu-empty.json')), [])
        self.assertEqual(zhihu.parse(load_json('zhihu-empty.json')), [])


class CollectIsolationTests(unittest.TestCase):
    def test_three_ok_samples_validate(self):
        payload = collect(NOW, http=ok_http())
        self.assertEqual(validate_hotsearch(payload), [])
        ids = [p['id'] for p in payload['providers']]
        self.assertEqual(ids, ['baidu', 'zhihu', 'bilibili'])
        counts = {p['id']: (p['status'], len(p['items'])) for p in payload['providers']}
        self.assertEqual(counts['baidu'], ('ok', 50))
        self.assertEqual(counts['zhihu'], ('ok', 30))
        self.assertEqual(counts['bilibili'], ('ok', 50))
        self.assertEqual(payload['generated_at'], '2026-11-15T20:41:00+08:00')
        self.assertIsNone(payload['providers'][0].get('error'))

    def test_each_provider_failure_leaves_others_ok(self):
        cases = {
            'baidu': ProviderError('timeout'),
            'zhihu': HttpResponse(403, '{"error":"forbidden"}'),
            'bilibili': HttpResponse(200, text('bili-code-error.json')),
        }
        expected_error = {'baidu': 'timeout', 'zhihu': 'http_403', 'bilibili': 'code_-403'}
        for failed in ('baidu', 'zhihu', 'bilibili'):
            with self.subTest(failed=failed):
                payload = collect(NOW, http=ok_http({ENDPOINTS[failed]: cases[failed]}))
                self.assertEqual(validate_hotsearch(payload), [])
                by_id = {p['id']: p for p in payload['providers']}
                self.assertEqual(by_id[failed]['status'], 'error')
                self.assertEqual(by_id[failed]['items'], [])
                self.assertEqual(by_id[failed]['error'], expected_error[failed])
                for other in set(cases) - {failed}:
                    self.assertEqual(by_id[other]['status'], 'ok')
                    self.assertGreater(len(by_id[other]['items']), 0)

    def test_all_fail_still_valid_empty_lists(self):
        overrides = {url: ProviderError('timeout') for url in ENDPOINTS.values()}
        payload = collect(NOW, http=ok_http(overrides))
        self.assertEqual(validate_hotsearch(payload), [])
        self.assertEqual(len(payload['providers']), 3)
        for provider in payload['providers']:
            self.assertEqual(provider['status'], 'error')
            self.assertEqual(provider['items'], [])
            self.assertEqual(provider['error'], 'timeout')

    def test_empty_successful_fetch_is_status_empty(self):
        overrides = {ENDPOINTS['baidu']: HttpResponse(200, text('baidu-empty.json'))}
        payload = collect(NOW, http=ok_http(overrides))
        self.assertEqual(validate_hotsearch(payload), [])
        baidu_row = next(p for p in payload['providers'] if p['id'] == 'baidu')
        self.assertEqual(baidu_row['status'], 'empty')
        self.assertEqual(baidu_row['items'], [])
        self.assertNotIn('error', baidu_row)

    def test_one_request_per_provider(self):
        http = ok_http()
        calls = []
        original = http.get

        def wrapped(url, timeout=10, headers=None):
            calls.append(url)
            return original(url, timeout=timeout, headers=headers)

        http.get = wrapped
        collect(NOW, http=http)
        self.assertEqual(calls, [ENDPOINTS['baidu'], ENDPOINTS['zhihu'], ENDPOINTS['bilibili']])

    def test_fixtures_do_not_touch_network(self):
        with patch('urllib.request.urlopen', side_effect=AssertionError('network')):
            payload = collect(NOW, http=ok_http())
        self.assertEqual(validate_hotsearch(payload), [])


class CliTests(unittest.TestCase):
    def test_fixtures_cli_writes_envelope(self):
        import tempfile
        from rebang.hotsearch.__main__ import main

        with tempfile.TemporaryDirectory() as folder, \
                patch('urllib.request.urlopen', side_effect=AssertionError('network')):
            out = Path(folder) / 'hotsearch.json'
            code = main(['--out', str(out), '--fixtures', str(FIX)])
            self.assertEqual(code, 0)
            payload = json.loads(out.read_text(encoding='utf-8'))
            self.assertEqual(validate_hotsearch(payload), [])
            self.assertEqual([p['status'] for p in payload['providers']], ['ok', 'ok', 'ok'])


if __name__ == '__main__':
    unittest.main()
