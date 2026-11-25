"""第 5 步：频道里「另有 N 个来源」折叠的手机尺寸（390×844）浏览器实测。离线、合成数据。"""
import json
import mimetypes
import tempfile
import unittest
from pathlib import Path
from unittest import mock
from urllib.parse import unquote, urlsplit

from rebang.site import builder as site
from tests.rebang_site_testdata import NOW, envelope, hotsearch, news, site_items

try:
    from playwright.sync_api import sync_playwright
except ImportError:  # pragma: no cover
    sync_playwright = None


def dup_items():
    return [news('freechinese', 'current', 901, minutes=0, title='🤖 DeepSeek 开放全家桶应用 API 合成测试'),
            news('tnews365', 'current', 900, minutes=1, title='DeepSeek开放“全家桶”应用API 合成测试',
                 body='被折叠那条的正文')]


@unittest.skipUnless(sync_playwright, 'Playwright 不可用')
class DedupBrowserTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        root = Path(cls.tmp.name)
        (root / 'in').mkdir()
        (root / 'in' / 'ingest.json').write_text(json.dumps(envelope(site_items() + dup_items())), encoding='utf-8')
        (root / 'in' / 'hotsearch.json').write_text(json.dumps(hotsearch()), encoding='utf-8')
        cls.out = root / 'site'
        with mock.patch.object(site, '_run_archive', lambda items, out, report: None):
            site.build(cls.out, root / 'in', now=NOW, hot_archive_dir=root / 'hot')
        cls.pw = sync_playwright().start()
        cls.browser = cls.pw.chromium.launch()

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.pw.stop()
        cls.tmp.cleanup()

    def setUp(self):
        self.context = self.browser.new_context(viewport={'width': 390, 'height': 844}, is_mobile=True, has_touch=True)
        self.addCleanup(self.context.close)
        self.page = self.context.new_page()
        self.errors = []
        self.page.on('pageerror', lambda e: self.errors.append(str(e)))
        self.addCleanup(lambda: self.assertEqual(self.errors, []))

        def serve(route):
            url = urlsplit(route.request.url)
            if url.netloc != 'rebang.test':
                return route.abort()
            path = self.out / (unquote(url.path).lstrip('/') or 'index.html')
            route.fulfill(status=200 if path.is_file() else 404, body=path.read_bytes() if path.is_file() else b'missing',
                          content_type=mimetypes.guess_type(str(path))[0] or 'application/octet-stream')
        self.page.route('**/*', serve)

    def test_folded_sources_expand_in_place_and_open_the_folded_item(self):
        self.page.goto('https://rebang.test/index.html')
        self.page.wait_for_selector('#app:not([aria-busy])')
        row = self.page.locator('.feed-row[data-id="tnews365:900"]').first
        row.scroll_into_view_if_needed()
        self.assertEqual(self.page.locator('.feed-row[data-id="freechinese:901"]').count(), 0)   # 被折叠，不单独成条
        btn = row.locator('.dup-btn')
        self.assertEqual(btn.inner_text(), '另有 1 个来源')
        self.assertFalse(row.locator('.dup-list').is_visible())
        btn.tap()
        self.page.wait_for_timeout(200)
        self.assertTrue(row.locator('.dup-list').is_visible())
        self.assertEqual(btn.get_attribute('aria-expanded'), 'true')
        self.assertFalse(self.page.locator('#articleView').is_visible())          # 展开不打开主条
        row.locator('.dup-row[data-dup-id="freechinese:901"]').tap()
        self.page.wait_for_selector('#articleView.on')
        self.assertEqual(self.page.evaluate('location.hash'), '#/item/freechinese%3A901')
        self.assertIn('DeepSeek', self.page.locator('#articleTitle').inner_text())

    def test_deep_link_to_a_folded_item_cold_start(self):
        self.page.goto('https://rebang.test/index.html#/item/freechinese%3A901')
        self.page.wait_for_selector('#articleView.on')
        self.assertIn('全家桶', self.page.locator('#articleTitle').inner_text())


if __name__ == '__main__':
    unittest.main()
