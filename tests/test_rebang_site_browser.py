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

VIDEO = (Path(__file__).parent / 'fixtures' / 'rebang-tiny.webm').read_bytes()
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
            if url.netloc == 'vid.test':
                if url.path == '/missing.webm':
                    return route.fulfill(status=404, body=b'missing', content_type='text/plain')
                return route.fulfill(status=200, body=VIDEO, content_type='video/webm')
            if url.netloc != 'rebang.test':
                return route.abort()
            path = self.out / (unquote(url.path).lstrip('/') or 'index.html')
            if getattr(self, 'stub_features', False) and unquote(url.path).startswith('/features/'):
                return route.fulfill(status=200, body=b'', content_type='application/javascript')  # 只测桩，不让真模块覆盖
            route.fulfill(status=200 if path.is_file() else 404, body=path.read_bytes() if path.is_file() else b'missing',
                          content_type=mimetypes.guess_type(str(path))[0] or 'application/octet-stream')
        self.page_route = serve
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
        # v13 第 7 条（阿欢 22:11）：日期只出现一次——同一个北京日只写时间，跨天才带日期。
        expect = self.page.evaluate("'刷新于 ' + RebangLib.fmtRefreshed('2026-11-15T12:00:00Z', new Date())")
        self.assertIn(expect, ('刷新于 20:00', '刷新于 11月15日 20:00'))
        self.assertEqual(self.page.locator('#refreshed').inner_text(), expect)
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
        # banner 仍只挑合格大图；列表里凡是有图（含短边不够 banner 标准的 tnews365:8）都显示缩略图
        self.assertEqual(page.locator('.feed-row:not(.noimg)').count(), 3, '有图的列表项都显示缩略图（含短边 < 240 的）')
        self.assertEqual(page.locator('.feed-row[data-id="tnews365:8"]:not(.noimg)').count(), 1)
        self.assertIn('这条没有正文摘要', page.locator('.feed-row[data-id="tnews365:9"]').inner_text(), '无图且无摘要才显示占位句')
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

    def video_state(self):
        return self.page.evaluate('''() => { const v = document.querySelector('#zoomStage video'); if (!v) return null;
          return {paused: v.paused, muted: v.muted, controls: v.controls, loop: v.loop, poster: v.poster, t: v.currentTime, rs: v.readyState}; }''')

    def test_video_player_mixed_media_swipe_and_error_fallback(self):
        self.open()
        self.page.locator('.tabbar [data-view=blogger]').click()
        card = self.page.locator('#bloggerList .tweet[data-id="x-dotey:0"]')
        card.wait_for()
        self.assertEqual(card.locator('.cell.is-vid .vid-mark').count(), 2)
        self.assertIn('0:03', card.locator('.cell.is-vid').first.inner_text())
        card.locator('.cell.is-vid').first.tap()
        self.page.wait_for_selector('#zoomView.on #zoomStage video')
        self.assertEqual(self.page.get_attribute('#zoomView', 'aria-label'), '查看图片和视频')
        self.assertEqual(self.page.inner_text('#zoomCount'), '2 / 3')
        s = self.video_state()
        self.assertTrue(s['controls'] and s['paused'] and not s['muted'] and s['poster'].endswith('/v1.png'), s)   # 不自动出声
        box = self.page.locator('#zoomStage video').bounding_box()
        cdp = self.context.new_cdp_session(self.page)
        for _ in range(2):   # 点在视频中间：不关闭查看器
            cdp.send('Input.dispatchTouchEvent', {'type': 'touchStart', 'touchPoints': [{'x': box['x'] + box['width'] / 2, 'y': box['y'] + box['height'] / 2}]})
            cdp.send('Input.dispatchTouchEvent', {'type': 'touchEnd', 'touchPoints': []})
            self.page.wait_for_timeout(200)
        self.assertTrue(self.page.is_visible('#zoomView'))
        self.page.evaluate("document.querySelector('#zoomStage video').play()")
        self.page.wait_for_function("(() => { const v = document.querySelector('#zoomStage video'); return v && v.currentTime > 0.3 && v.readyState >= 2; })()", timeout=8000)
        self.page.evaluate("window.__v = document.querySelector('#zoomStage video')")
        self.swipe(300, 400, 80, 400)   # 左滑到 GIF
        self.assertEqual(self.page.inner_text('#zoomCount'), '3 / 3')
        self.assertTrue(self.page.evaluate('window.__v.paused'))   # 离开即暂停
        self.page.wait_for_function("(() => { const v = document.querySelector('#zoomStage video'); return v && !v.paused && v.currentTime > 0.2; })()", timeout=8000)
        s = self.video_state()
        self.assertTrue(s['muted'] and s['loop'] and not s['controls'], s)
        self.swipe(300, 400, 80, 400)   # 循环到第一张图
        self.assertEqual(self.page.inner_text('#zoomCount'), '1 / 3')
        self.assertEqual(self.page.locator('#zoomStage > img').count(), 1)
        self.page.locator('#zoomClose').tap()
        self.assertFalse(self.page.is_visible('#zoomView'))
        # 坏地址：保留封面，给原帖链接
        bad = self.page.locator('#bloggerList .tweet[data-id="x-simonw:1"] .cell.is-vid')
        bad.scroll_into_view_if_needed()
        bad.tap()
        self.page.wait_for_selector('#zoomStage .zoom-fail a')
        self.assertEqual(self.page.get_attribute('#zoomStage .zoom-fail a', 'href'), 'https://x.com/simonw/status/1')
        self.assertEqual(self.page.locator('#zoomStage .zoom-fail img').count(), 1)
        # 普通图片：点一下仍然关闭
        self.page.locator('#zoomClose').tap()

    def test_zoom_bar_buttons_do_not_close_viewer_on_touch(self):
        self.open()
        self.page.locator('.tabbar [data-view=blogger]').click()
        self.page.locator('#bloggerList .tweet[data-id="x-dotey:0"] .cell').first.tap()
        self.page.wait_for_selector('#zoomView.on #zoomStage > img')
        self.page.locator('#zoomNext').tap()
        self.assertTrue(self.page.is_visible('#zoomView'))
        self.assertEqual(self.page.inner_text('#zoomCount'), '2 / 3')

    def test_tab_switch_keeps_channel_scroll_and_hidden_views_are_inert(self):
        self.open()
        current = self.page.locator('.page-b[data-ch=current]')
        current.evaluate('e => e.scrollTop = 700')
        self.page.wait_for_timeout(100)
        before = current.evaluate('e => e.scrollTop')
        self.page.locator('.tabbar [data-view=hot]').tap()
        self.assertFalse(self.page.locator('#view-channels').is_visible())
        self.assertEqual(self.page.locator('#view-channels').evaluate('e => getComputedStyle(e).pointerEvents'), 'none')
        self.page.locator('.tabbar [data-view=channels]').tap()
        self.assertTrue(self.page.locator('#view-channels').is_visible())
        self.assertEqual(current.evaluate('e => e.scrollTop'), before)

    def test_one_icon_set_lucide_everywhere(self):
        self.open()
        self.page.locator('.tabbar [data-view=blogger]').click()
        self.page.wait_for_selector('#bloggerList .tweet')
        stray = self.page.evaluate("[...document.querySelectorAll('svg')].filter(s => !s.classList.contains('lucide')).map(s => s.outerHTML.slice(0, 80))")
        self.assertEqual(stray, [])
        self.assertGreater(self.page.locator('svg.lucide').count(), 10)

    def test_refresh_icon_does_not_spin_backwards(self):
        self.open()
        svg = self.page.locator('#btnRefresh svg')
        self.assertEqual(svg.evaluate('e => getComputedStyle(e).transitionDuration'), '0s')   # 平时没有过渡：去掉 .spin 不会倒转
        self.page.locator('#btnRefresh').click()
        self.assertEqual(svg.evaluate('e => getComputedStyle(e).transitionDuration'), '0.3s')

    def test_reduced_motion_zeroes_durations(self):
        ctx = self.browser.new_context(viewport={'width': 390, 'height': 844}, is_mobile=True, has_touch=True, reduced_motion='reduce')
        self.addCleanup(ctx.close)
        page = ctx.new_page()
        page.route('**/*', self.page_route)
        page.goto('https://rebang.test/index.html')
        page.wait_for_selector('#app:not([aria-busy])')
        self.assertEqual(page.evaluate("getComputedStyle(document.documentElement).getPropertyValue('--duration-slow').trim()"), '0ms')


if __name__ == '__main__':
    unittest.main()
