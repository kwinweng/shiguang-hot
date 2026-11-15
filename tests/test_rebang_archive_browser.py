"""手机尺寸无头浏览器实测：收藏存取、搜索命中、按日期回看。"""
import json
import mimetypes
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from urllib.parse import unquote, urlsplit

from rebang.archive import EMPTY_MESSAGE, build

ROOT = Path(__file__).resolve().parents[1]
FIX = ROOT / 'tests/fixtures/rebang/archive'
FEATURES = ROOT / 'web-v11/features'
EVIDENCE = ROOT / 'docs/rebang-v1/evidence/history-favorites-search'

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    sync_playwright = None


@unittest.skipUnless(sync_playwright, 'optional Playwright is unavailable')
class HistoryFavoritesSearchBrowserTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.playwright = sync_playwright().start()
        executable = os.getenv('NEWS_TEST_CHROME') or next(
            (path for path in ('/opt/ungoogled-chromium/chrome', '/usr/bin/google-chrome')
             if Path(path).is_file()), None)
        try:
            cls.browser = cls.playwright.chromium.launch(
                executable_path=executable, headless=True,
                args=['--no-sandbox', '--disable-crash-reporter', '--disable-breakpad'])
        except Exception as error:
            cls.playwright.stop()
            raise unittest.SkipTest(f'Browser unavailable: {str(error).splitlines()[0]}')
        cls.temp = tempfile.TemporaryDirectory()
        cls.site = Path(cls.temp.name) / 'site-v11'
        cls.archive = Path(cls.temp.name) / 'archive'
        fixture = json.loads((FIX / 'published-items.json').read_text(encoding='utf-8'))
        build(fixture['items'], cls.site, archive_dir=cls.archive,
              generated_at='2026-11-15T20:00:00+08:00')
        shutil.copyfile(FIX / 'harness.html', cls.site / 'index.html')
        EVIDENCE.mkdir(parents=True, exist_ok=True)

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.playwright.stop()
        cls.temp.cleanup()

    def setUp(self):
        self.context = self.browser.new_context(
            viewport={'width': 393, 'height': 852},
            locale='zh-CN',
        )
        self.addCleanup(self.context.close)
        self.page = self.context.new_page()
        self.errors = []
        self.page.on('pageerror', lambda error: self.errors.append(str(error)))

        pixel = (b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01'
                 b'\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00'
                 b'\x0cIDATx\x9cc\xd0\x80\x01\x00\x00\x03\x00\x01\x1e\xd4\x03'
                 b'\x1b\x00\x00\x00\x00IEND\xaeB`\x82')

        def serve(route):
            url = urlsplit(route.request.url)
            path_name = unquote(url.path)
            if path_name.startswith('/features/'):
                path = FEATURES / path_name.split('/features/', 1)[1]
            else:
                path = self.site / (path_name.lstrip('/') or 'index.html')
            if path.is_file():
                mime, _ = mimetypes.guess_type(path.name)
                route.fulfill(status=200, body=path.read_bytes(),
                              content_type=mime or 'application/octet-stream')
            elif path_name.endswith(('.jpg', '.jpeg', '.png', '.webp', '.gif')):
                route.fulfill(status=200, body=pixel, content_type='image/png')
            else:
                route.fulfill(status=404, body=b'missing', content_type='text/plain')

        self.page.route('**/*', serve)

    def open(self):
        self.page.goto('https://offline.test/index.html')
        self.page.evaluate('() => window.__ready')
        self.page.wait_for_selector('#channelList [data-open-id]')
        self.page.wait_for_selector('#view-history[data-history-date]', state='attached')

    def shot(self, name):
        path = EVIDENCE / name
        self.page.screenshot(path=str(path), full_page=False)
        return path

    def test_favorites_persist_search_hits_and_history_by_date(self):
        self.open()

        self.page.locator('#channelList [data-open-id="tnews365:1001"]').click()
        self.page.wait_for_selector('[data-favorite-button="tnews365:1001"]')
        self.assertEqual(self.page.locator('[data-favorite-button]').inner_text(), '收藏这条')
        self.page.locator('[data-favorite-button]').click()
        self.page.wait_for_function('() => document.querySelector("[data-favorite-button]").textContent.includes("取消收藏")')
        self.page.locator('#btnBack').click()
        self.page.locator('.tabbar button[data-view="favorites"]').click()
        self.page.wait_for_selector('#view-favorites [data-item-id="tnews365:1001"]')
        self.assertIn('合成标题一', self.page.locator('#view-favorites [data-item-id="tnews365:1001"]').inner_text())
        self.assertIn('换手机或清理数据会消失', self.page.locator('[data-favorites-note]').inner_text())
        self.shot('01-favorites-after-save.png')

        self.page.reload()
        self.page.evaluate('() => window.__ready')
        self.page.locator('.tabbar button[data-view="favorites"]').click()
        self.page.wait_for_selector('#view-favorites [data-item-id="tnews365:1001"]')
        self.assertIn('合成标题一', self.page.locator('#view-favorites [data-item-id="tnews365:1001"]').inner_text())
        self.shot('02-favorites-after-reload.png')

        self.page.locator('#btnSearch').click()
        self.page.wait_for_selector('#search-panel.on [data-search-input]')
        self.page.locator('[data-search-input]').fill('合成标题一')
        self.page.wait_for_selector('[data-search-hit="tnews365:1001"]')
        self.assertIn('合成标题一', self.page.locator('[data-search-hit="tnews365:1001"]').inner_text())
        self.shot('03-search-hit.png')
        self.page.locator('[data-search-input]').fill('合成译文标题')
        self.page.wait_for_selector('[data-search-hit="bbc-world:abc123"]')
        self.page.locator('[data-search-close]').click()

        self.page.locator('.tabbar button[data-view="history"]').click()
        self.page.wait_for_selector('#view-history[data-history-date="2026-11-15"]')
        self.assertIn('合成标题一', self.page.locator('#view-history [data-item-id="tnews365:1001"]').inner_text())
        self.shot('04-history-day-with-items.png')

        self.page.locator('[data-history-prev]').click()
        self.page.wait_for_selector('#view-history[data-history-date="2026-11-14"]')
        self.page.wait_for_selector('p[data-history-empty]')
        self.assertIn(EMPTY_MESSAGE, self.page.locator('p[data-history-empty]').inner_text())
        self.shot('05-history-empty-day.png')

        self.page.locator('[data-history-prev]').click()
        self.page.wait_for_selector('#view-history[data-history-date="2026-11-13"]')
        self.page.wait_for_selector('#view-history [data-item-id="tnews365:1301"]')
        self.assertIn('十三日旧闻', self.page.locator('#view-history [data-item-id="tnews365:1301"]').inner_text())
        self.shot('06-history-prev-day.png')

        self.assertEqual(self.errors, [])


if __name__ == '__main__':
    unittest.main()
