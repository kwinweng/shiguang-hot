"""第 5 步：频道里「另有 N 个来源」折叠的手机尺寸（390×844）浏览器实测。离线、合成数据。"""
import json
import mimetypes
import tempfile
import unittest
from pathlib import Path
from unittest import mock
from urllib.parse import unquote, urlsplit

from rebang.site import builder as site
from tests.rebang_site_testdata import NOW, envelope, hotsearch, img, news, site_items

try:
    from playwright.sync_api import sync_playwright
except ImportError:  # pragma: no cover
    sync_playwright = None


HL = {'highlight': True, 'highlight_date': '2026-11-15'}
SAME_URL = 'https://news.test/same-raw-url'


def dup_items():
    return [news('freechinese', 'current', 901, minutes=0, title='🤖 DeepSeek 开放全家桶应用 API 合成测试',
                 body='被折叠那条的正文', **HL),
            news('tnews365', 'current', 900, minutes=1, title='DeepSeek开放“全家桶”应用API 合成测试', **HL),
            # 顶部大图卡上的主条（比时事其它条都新，排在 banner 第 1 屏）
            news('myBigCharacterPoster', 'current', 961, minutes=-3, title='大图卡折叠测试：谷歌发布新一代开源模型 面向开发者',
                 image=img(961)),
            news('shuangyunews_rss', 'current', 960, minutes=-4, title='大图卡折叠测试：谷歌发布新一代开源模型 面向开发者',
                 image=img(960), body='大图卡折叠那条的正文'),
            # 原始链接完全相同的两条：两个 id 都要能打开
            news('myBigCharacterPoster', 'current', 970, minutes=200, title='同链接甲', url=SAME_URL, body='同链接甲的正文'),
            news('shuangyunews_rss', 'current', 971, minutes=210, title='同链接乙', url=SAME_URL, body='同链接乙的正文')]


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

    def open_home(self):
        self.page.goto('https://rebang.test/index.html')
        self.page.wait_for_selector('#app:not([aria-busy])')

    def long_press(self, locator):
        box = locator.bounding_box()
        x, y = box['x'] + box['width'] / 2, box['y'] + box['height'] / 2
        cdp = self.context.new_cdp_session(self.page)
        cdp.send('Input.dispatchTouchEvent', {'type': 'touchStart', 'touchPoints': [{'x': x, 'y': y}]})
        self.page.wait_for_timeout(650)
        cdp.send('Input.dispatchTouchEvent', {'type': 'touchEnd', 'touchPoints': []})
        self.page.wait_for_timeout(350)

    def test_hero_card_has_folded_sources_entry(self):
        self.open_home()
        hero = self.page.locator('.banner-rail .hero[data-id="myBigCharacterPoster:961"]').first
        hero.scroll_into_view_if_needed()
        btn = hero.locator('.dup-btn')
        self.assertTrue(btn.is_visible())
        self.assertEqual(btn.inner_text(), '另有 1 个来源')
        btn.tap()
        self.page.wait_for_timeout(200)
        self.assertTrue(hero.locator('.dup-list').is_visible())
        self.assertEqual(btn.get_attribute('aria-expanded'), 'true')
        self.assertFalse(self.page.locator('#articleView').is_visible())          # 展开不打开主条
        hero.locator('.dup-row[data-dup-id="shuangyunews_rss:960"]').tap()
        self.page.wait_for_selector('#articleView.on')
        self.assertIn('大图卡折叠那条的正文', self.page.locator('#articleBody').inner_text())

    def test_long_press_on_fold_control_does_not_open_card_menu(self):
        self.open_home()
        row = self.page.locator('.feed-row[data-id="tnews365:900"]').first
        row.scroll_into_view_if_needed()
        self.long_press(row.locator('.dup-btn'))
        self.assertFalse(self.page.locator('#cardMenu').evaluate('e => e.classList.contains("on")'))
        self.long_press(row.locator('h3'))                                            # 卡片本身长按照旧弹菜单
        self.assertTrue(self.page.locator('#cardMenu.on').is_visible())

    def test_fold_control_works_with_keyboard(self):
        self.open_home()
        row = self.page.locator('.feed-row[data-id="tnews365:900"]').first
        row.scroll_into_view_if_needed()
        btn = row.locator('.dup-btn')
        btn.focus()
        self.page.keyboard.press('Enter')
        self.page.wait_for_timeout(150)
        self.assertEqual(btn.get_attribute('aria-expanded'), 'true')
        self.page.keyboard.press('Tab')
        self.assertEqual(self.page.evaluate('document.activeElement.dataset.dupId'), 'freechinese:901')
        self.page.keyboard.press('Enter')
        self.page.wait_for_selector('#articleView.on')
        self.assertEqual(self.page.evaluate('location.hash'), '#/item/freechinese%3A901')

    def test_cold_start_open_from_snapshot_reads_full_item_from_this_build(self):
        requested = []
        self.page.on('request', lambda r: requested.append(urlsplit(r.url).path))
        self.open_home()
        # 收藏 / 搜索只存了快照（没有正文、没有今日重点标）；打开时应按 id 读本次发布的完整条目
        snap = {'id': 'freechinese:901', 'kind': 'news', 'channel': 'current', 'source_id': 'freechinese',
                'source_name': 'freechinese', 'title': '🤖 DeepSeek 开放全家桶应用 API 合成测试', 'summary': '',
                'url': 'https://example.com/freechinese/901', 'published_at': NOW.isoformat(), 'lang': 'zh',
                'translated': False, 'translation': None, 'image': None}
        self.page.evaluate('s => window.Rebang.openItem(s)', snap)
        self.page.wait_for_selector('#articleView.on')
        self.assertIn('/data/channel/current/merged.json', requested)
        self.assertIn('被折叠那条的正文', self.page.locator('#articleBody').inner_text())
        self.assertTrue(self.page.locator('#articleBody .hlb').is_visible())        # 今日重点标

    def test_both_ids_with_identical_raw_url_open(self):
        for ident, body in (('myBigCharacterPoster:970', '同链接甲的正文'), ('shuangyunews_rss:971', '同链接乙的正文')):
            self.page.goto('https://rebang.test/index.html#/item/' + ident.replace(':', '%3A'))
            self.page.wait_for_selector('#articleView.on')
            self.assertIn(body, self.page.locator('#articleBody').inner_text(), ident)

    def test_deep_link_to_a_folded_item_cold_start(self):
        self.page.goto('https://rebang.test/index.html#/item/freechinese%3A901')
        self.page.wait_for_selector('#articleView.on')
        self.assertIn('全家桶', self.page.locator('#articleTitle').inner_text())


if __name__ == '__main__':
    unittest.main()
