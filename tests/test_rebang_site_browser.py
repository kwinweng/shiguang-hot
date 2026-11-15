"""frontend-v11：手机尺寸（390×844）浏览器实测，离线、合成数据。
覆盖：左右换频道（真触摸滑动）、banner 内横滑不换频道、两种翻法切换并记住、热搜分家与失败态、
无限加载到「没有更多了」、整页正文 + 返回原频道原位置（页面返回与系统返回）、#/item/<id> 深链、底栏、功能模块注册与收藏槽。"""
import base64
import json
import mimetypes
import tempfile
import unittest
from pathlib import Path
from unittest import mock
from urllib.parse import unquote, urlsplit

from rebang.site import builder as site
from tests.rebang_site_testdata import NOW, envelope, hotsearch, site_items

try:
    from playwright.sync_api import sync_playwright
except ImportError:  # pragma: no cover
    sync_playwright = None

PNG = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+M8AAQUBAScY42YAAAAASUVORK5CYII=')
STUB = """
window.Rebang = window.Rebang || {};
window.Rebang._queue = [['favorites', function (el, ctx) {
  window.__ctx = {dataBase: ctx.dataBase, now: !!ctx.now, openItem: typeof ctx.openItem, toast: typeof ctx.toast};
  el.innerHTML = '<div class="sub"><p id="stub-fav">收藏桩</p></div>';
  return {attachButton: function (slot, item) { slot.innerHTML = '<button class="fav" id="stub-fav-btn">收藏这条</button>'; window.__attached = item.id; }};
}]];
"""


@unittest.skipUnless(sync_playwright, 'Playwright 不可用')
class SiteBrowserTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        root = Path(cls.tmp.name)
        (root / 'in').mkdir()
        (root / 'in' / 'ingest.json').write_text(json.dumps(envelope(site_items())), encoding='utf-8')
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
            if url.netloc == 'img.test':
                return route.fulfill(status=200, body=PNG, content_type='image/png')
            if url.netloc != 'rebang.test':
                return route.abort()
            path = self.out / (unquote(url.path).lstrip('/') or 'index.html')
            if getattr(self, 'stub_features', False) and unquote(url.path).startswith('/features/'):
                return route.fulfill(status=200, body=b'', content_type='application/javascript')  # 只测桩，不让真模块覆盖
            route.fulfill(status=200 if path.is_file() else 404, body=path.read_bytes() if path.is_file() else b'missing',
                          content_type=mimetypes.guess_type(str(path))[0] or 'application/octet-stream')
        self.page.route('**/*', serve)

    def open(self, hash=''):
        self.page.goto('https://rebang.test/index.html' + hash)
        self.page.wait_for_selector('#app:not([aria-busy])')
        self.page.wait_for_timeout(150)

    def swipe(self, x0, y0, x1, y1, steps=8):
        cdp = self.context.new_cdp_session(self.page)
        cdp.send('Input.dispatchTouchEvent', {'type': 'touchStart', 'touchPoints': [{'x': x0, 'y': y0}]})
        for i in range(1, steps + 1):
            cdp.send('Input.dispatchTouchEvent', {'type': 'touchMove', 'touchPoints': [
                {'x': x0 + (x1 - x0) * i / steps, 'y': y0 + (y1 - y0) * i / steps}]})
            self.page.wait_for_timeout(16)
        cdp.send('Input.dispatchTouchEvent', {'type': 'touchEnd', 'touchPoints': []})
        self.page.wait_for_timeout(500)

    def channel_index(self):
        return self.page.locator('#channelRoot').evaluate('e => Math.round(e.scrollLeft / e.clientWidth)')

    def test_top_bar_tabs_and_six_channels(self):
        self.open()
        self.assertEqual(self.page.locator('#when').inner_text(), self.page.evaluate('RebangLib.fmtDay(new Date())'))
        self.assertEqual(self.page.locator('#refreshed').inner_text(), '刷新于 11月15日 20:00')
        self.assertEqual(self.page.locator('.page-b h2.ch').all_inner_texts(), ['时事', '环球', '财经', '科技与 AI', '数码', '工具与项目'])
        self.assertEqual([t.strip() for t in self.page.locator('.tabbar button').all_inner_texts()], ['频道', '博主', '热搜', '收藏'])
        self.assertEqual(self.page.locator('#view-history').count(), 0, '历史页已改为热搜页')
        for mount in ('#view-hot', '#view-favorites', '#search-panel'):
            self.assertEqual(self.page.locator(mount).count(), 1)

    def test_swipe_changes_channel_but_banner_swipe_does_not(self):
        self.open()
        self.swipe(330, 700, 40, 690)
        self.assertEqual(self.channel_index(), 1)
        self.swipe(40, 700, 340, 705)
        self.assertEqual(self.channel_index(), 0)
        banner = self.page.locator('.page-b[data-ch=current] .banner-rail')
        self.assertEqual(self.page.locator('.page-b[data-ch=current] .banner-slide').count(), 5)
        box = banner.bounding_box()
        y = box['y'] + box['height'] / 2
        self.swipe(box['x'] + box['width'] - 20, y, box['x'] + 20, y)
        self.assertEqual(self.channel_index(), 0, 'banner 内横滑只滑 banner')
        self.assertEqual(self.page.locator('.page-b[data-ch=current] .banner-pager').inner_text(), '2 / 5')

    def test_hotsearch_view_tabs_and_failure_state(self):
        # 2026-11-15 21:26：热搜从时事频道移到底栏「热搜」页，频道里不再有热搜块
        self.open()
        self.assertEqual(self.page.locator('#channelRoot .hot').count(), 0)
        self.page.locator('.tabbar [data-view=hot]').click()
        hot = self.page.locator('#view-hot .hot')
        hot.wait_for()
        self.assertEqual(hot.locator('[role=tab]').all_inner_texts(), ['百度热搜', '知乎热榜', 'B 站热搜'])
        self.assertEqual(hot.locator('.hot-list li').count(), 12, '热搜页直接列全部')
        self.assertEqual(self.page.locator('#hotDates .chip').all_inner_texts(), ['今天 · 现在'])
        hot.locator('[data-hot=zhihu]').click()
        self.assertIn('暂时取不到', self.page.locator('#view-hot .hot-empty').inner_text())

    def test_feed_cards_and_infinite_load_to_end(self):
        self.open()
        page = self.page.locator('.page-b[data-ch=current]')
        self.assertEqual(page.locator('.feed-row').count(), 30)
        self.assertEqual(page.locator('.feed-row:not(.noimg)').count(), 2, '只有合格图（banner 用剩的）显示左图；小图不合格与无图走标题+摘要')
        self.assertIn('这条没有正文摘要', page.locator('.feed-row[data-id="tnews365:9"]').inner_text())
        for _ in range(6):
            page.evaluate('e => e.scrollTop = e.scrollHeight')
            self.page.wait_for_timeout(300)
        self.assertEqual(page.locator('.feed-row').count(), 65)
        self.assertEqual(page.locator('.end-hint').inner_text(), '没有更多了')

    def test_article_full_page_and_back_restores_channel_and_scroll(self):
        self.open()
        self.page.locator('#channelRoot').evaluate('e => e.scrollLeft = e.clientWidth')
        self.page.wait_for_timeout(200)
        self.page.locator('.page-b[data-ch=world] .feed-row').first.click()
        self.assertIn('机器翻译', self.page.locator('#articleBody').inner_text())
        self.page.locator('#articleBody [data-art-orig]').click()
        self.assertIn('Synthetic headline', self.page.locator('[data-art-orig-box]').inner_text())
        self.page.locator('#btnBack').click()
        self.page.wait_for_timeout(300)
        self.assertEqual(self.channel_index(), 1)
        current = self.page.locator('.page-b[data-ch=current]')
        self.page.locator('#channelRoot').evaluate('e => e.scrollLeft = 0')
        current.evaluate('e => e.scrollTop = 900')
        self.page.wait_for_timeout(300)
        row = self.page.locator('.page-b[data-ch=current] .feed-row').nth(12)
        row.scroll_into_view_if_needed()
        before = current.evaluate('e => e.scrollTop')
        self.assertGreater(before, 500)
        row_id = row.get_attribute('data-id')
        row.click()
        self.assertTrue(self.page.locator('#articleView').is_visible())
        self.assertEqual(self.page.evaluate('location.hash'), '#/item/' + row_id.replace(':', '%3A'))
        self.page.go_back()  # 系统返回 / 手势返回
        self.page.wait_for_timeout(300)
        self.assertFalse(self.page.locator('#articleView').is_visible())
        self.assertEqual((self.channel_index(), current.evaluate('e => e.scrollTop')), (0, before))

    def test_deep_link_opens_item_on_a_later_page(self):
        self.open('#/item/tnews365%3A69')
        self.page.wait_for_selector('#articleView.on')
        self.assertIn('current 合成标题 69', self.page.locator('#articleBody').inner_text())
        self.page.go_back()
        self.page.wait_for_timeout(300)
        self.assertFalse(self.page.locator('#articleView').is_visible())
        self.assertEqual(self.page.locator('.page-b').count(), 6)

    def test_deep_link_in_already_open_tab(self):
        self.open()
        self.page.locator('.page-b[data-ch=current]').evaluate('e => e.scrollTop = 400')
        self.page.evaluate("location.hash = '#/item/tnews365%3A69'")
        self.page.wait_for_selector('#articleView.on')
        self.assertIn('current 合成标题 69', self.page.locator('#articleBody').inner_text())
        self.page.locator('#btnBack').click()
        self.page.wait_for_timeout(400)
        self.assertFalse(self.page.locator('#articleView').is_visible())
        self.assertEqual(self.page.locator('.page-b[data-ch=current]').evaluate('e => e.scrollTop'), 400)

    def test_vertical_mode_more_button_end_and_remembered(self):
        self.open()
        self.page.locator('#modeUD').click()
        self.assertEqual(self.page.locator('#channelRoot').get_attribute('class'), 'pager-a')
        block = self.page.locator('.block-a[data-ch=current]')
        self.assertEqual(block.locator('.feed-row').count(), 6)
        self.assertEqual(block.locator('.banner-slide').count(), 5)
        for _ in range(3):
            block.locator('[data-more]').click()
            self.page.wait_for_timeout(200)
        self.assertEqual(block.locator('.feed-row').count(), 65)
        self.assertEqual(block.locator('.end-hint').inner_text(), '没有更多了')
        self.page.reload()
        self.page.wait_for_selector('#app:not([aria-busy])')
        self.assertTrue(self.page.locator('#modeUD').evaluate('e => e.classList.contains("on")'))
        self.assertEqual(self.page.locator('#channelRoot > .end-hint').inner_text(), '没有更多了')

    def test_feature_queue_ctx_and_favorite_slot_only_in_article(self):
        self.stub_features = True
        self.page.add_init_script(STUB)
        self.open()
        self.assertEqual(self.page.locator('.page-b [data-favorite-button], .page-b .fav').count(), 0, '列表里没有收藏按钮')
        self.page.locator('.tabbar [data-view=favorites]').click()
        self.assertEqual(self.page.locator('#stub-fav').inner_text(), '收藏桩')
        self.assertEqual(self.page.evaluate('window.__ctx'), {'dataBase': 'data', 'now': True, 'openItem': 'function', 'toast': 'function'})
        self.page.locator('.tabbar [data-view=channels]').click()
        self.page.locator('.page-b[data-ch=current] .feed-row').first.click()
        self.assertEqual(self.page.locator('#articleBody #stub-fav-btn').count(), 1)
        self.assertEqual(self.page.evaluate('window.__attached'), 'tnews365:5')
        self.page.locator('#btnBack').click()

    def test_blogger_tab_real_empty_states(self):
        self.open()
        self.page.locator('.tabbar [data-view=blogger]').click()
        self.page.wait_for_selector('#bloggerList .tweet')
        self.assertEqual(self.page.locator('#bloggerList .tweet').count(), 2)
        self.page.locator('[data-plat=weibo]').click()
        self.assertIn('还没有成功抓取过', self.page.locator('#bloggerList').inner_text())
        self.page.locator('[data-plat=zhihu]').click()
        self.assertIn('知乎', self.page.locator('#bloggerList').inner_text())


if __name__ == '__main__':
    unittest.main()
