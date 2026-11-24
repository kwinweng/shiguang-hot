"""frontend-v11：手机尺寸（390×844）浏览器实测，离线、合成数据。
覆盖：频道/博主一条长流（一直往下刷、「下一个：…」接下一段、到底「内容已结束」、吸顶标题跟着当前段）、
左右换频道（真触摸滑动，跳到下一频道开头）、banner 内横滑不换频道、两种翻法切换并记住、热搜分家与失败态、
卡片没有横滑动作只有长按菜单（频道/博主/收藏/热搜）、整页正文 + 返回原位置（页面返回与系统返回）、
#/item/<id> 深链、旧 #/more/ 链接跳到长流里那一段、底栏、功能模块注册与收藏槽。"""
import base64
import json
import mimetypes
import tempfile
import unittest
from pathlib import Path
from unittest import mock
from urllib.parse import unquote, urlsplit

from rebang.site import builder as site
from tests.rebang_site_testdata import NOW, envelope, health_inputs, hotsearch, site_items

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
        sources, platforms = health_inputs()
        health_in = root / 'health-in'
        health_in.mkdir()
        (health_in / 'ingest.json').write_text(json.dumps(dict(envelope([], 'ingest'), sources=sources)), encoding='utf-8')
        (health_in / 'bloggers.json').write_text(json.dumps(dict(envelope([], 'bloggers'), platforms=platforms)), encoding='utf-8')
        cls.health_out = root / 'health-site'
        site.build(cls.health_out, health_in, now=NOW, hot_archive_dir=root / 'hot')
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
            folder = self.health_out if self._testMethodName.startswith('test_health_') else self.out
            path = folder / (unquote(url.path).lstrip('/') or 'index.html')
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
        """当前在看第几个频道（吸顶标题那一段）"""
        self.page.wait_for_timeout(80)
        return self.page.locator('#channelRoot').evaluate("e => [...e.querySelectorAll(':scope > .ch-sec')].findIndex(s => s.dataset.ch === e.dataset.cur)")

    def section_top(self, slug):
        return self.page.evaluate(f"""(() => {{ const r = document.querySelector('#channelRoot'), s = r.querySelector('.ch-sec[data-ch="{slug}"]');
          return Math.round(s.getBoundingClientRect().top - r.getBoundingClientRect().top); }})()""")

    def scroll_to_end(self, sel, rounds=60):
        for _ in range(rounds):
            self.page.locator(sel).evaluate('e => e.scrollTop = e.scrollHeight')
            self.page.wait_for_timeout(120)
            if self.page.evaluate(f"[...document.querySelectorAll('{sel} [data-end=all]')].some(e => !e.closest('[hidden]'))"):
                self.page.locator(sel).evaluate('e => e.scrollTop = e.scrollHeight')
                self.page.wait_for_timeout(120)
                return True
        return False

    def long_press(self, locator):
        box = locator.bounding_box()
        x, y = box['x'] + min(40, box['width'] / 2), box['y'] + min(30, box['height'] / 2)
        cdp = self.context.new_cdp_session(self.page)
        cdp.send('Input.dispatchTouchEvent', {'type': 'touchStart', 'touchPoints': [{'x': x, 'y': y}]})
        self.page.wait_for_timeout(650)
        cdp.send('Input.dispatchTouchEvent', {'type': 'touchEnd', 'touchPoints': []})
        self.page.wait_for_timeout(350)   # 松手后 250ms 内的补发点击会被吞掉

    def test_health_deep_link_renders_sorted_sources_at_mobile_width(self):
        with self.page.expect_request('**/data/health.json*'):
            self.open('#/health')
        dialog = self.page.get_by_role('dialog', name='来源健康')
        dialog.get_by_role('heading', name='待检查').wait_for()
        self.assertEqual(dialog.locator('.health-name').all_text_contents()[:4], ['微博', '竹新社', 'X', '卫报 World'])
        self.assertIn('2 天 5 小时', dialog.inner_text())
        self.assertLessEqual(dialog.evaluate('e => e.scrollWidth'), 390)
        dialog.get_by_text('查看 6 个账号', exact=True).first.click()
        self.assertTrue(dialog.locator('details[open] .health-account').first.is_visible())
        dialog.get_by_role('button', name='返回').click()
        dialog.wait_for(state='hidden')
        self.assertEqual(self.page.locator('.tabbar button').count(), 4)
        self.assertEqual(urlsplit(self.page.url).fragment, '')
        self.page.go_forward()
        dialog.wait_for()
        self.page.keyboard.press('Escape')
        dialog.wait_for(state='hidden')

    def test_health_diagnostics_link_is_lazy_and_handles_fetch_failure(self):
        requested = []
        self.page.on('request', lambda request: requested.append(request.url))
        self.open()
        self.assertFalse(any('/data/health.json' in url for url in requested))
        self.page.route('**/data/health.json*', lambda route: route.fulfill(status=404))
        title = self.page.locator('#chBtn').bounding_box()
        cdp = self.context.new_cdp_session(self.page)
        cdp.send('Input.dispatchTouchEvent', {'type': 'touchStart', 'touchPoints': [
            {'x': title['x'] + title['width'] / 2, 'y': title['y'] + title['height'] / 2}]})
        link = self.page.get_by_role('link', name='来源健康')
        link.wait_for()
        cdp.send('Input.dispatchTouchEvent', {'type': 'touchEnd', 'touchPoints': []})
        link.click()
        self.page.get_by_text('健康数据暂时加载不出来。').wait_for()
        self.assertEqual(urlsplit(self.page.url).fragment, '/health')
        self.assertEqual(self.page.locator('meta[name="robots"]').get_attribute('content'), 'noindex,nofollow')


        self.open()
        # v16：顶栏只有「频道名 + 下拉」，没有 logo、没有日期；刷新时间收进下拉
        self.assertEqual(self.page.locator('#chName').inner_text(), '时事')
        self.assertEqual(self.page.locator('#when, .logo, .brand img').count(), 0)
        self.page.locator('#chBtn').click()
        self.assertTrue(self.page.locator('#drop.on').is_visible())
        self.assertEqual(self.page.locator('#dropList [data-drop-ch]').count(), 6)
        # v13 第 7 条（阿欢 22:11）：日期只出现一次——同一个北京日只写时间，跨天才带日期。
        expect = self.page.evaluate("'刷新于 ' + RebangLib.fmtRefreshed('2026-11-15T12:00:00Z', new Date())")
        self.assertIn(expect, ('刷新于 20:00', '刷新于 11月15日 20:00'))
        self.assertEqual(self.page.locator('#refreshed').inner_text(), expect)
        self.assertEqual(self.page.locator('#channelRoot > .ch-sec h2.ch').evaluate_all('es => es.map(e => e.textContent)'), ['时事', '环球', '财经', '科技与 AI', '数码', '工具与项目'])
        self.assertEqual(self.page.locator('.see-more, [data-see], #moreView').count(), 0, '「查看更多」入口和整页都去掉了')
        self.assertEqual([t.strip() for t in self.page.locator('.tabbar button').all_inner_texts()], ['频道', '博主', '热搜', '收藏'])
        self.assertEqual(self.page.locator('#view-history').count(), 0, '历史页已改为热搜页')
        for mount in ('#view-hot', '#view-favorites', '#search-panel'):
            self.assertEqual(self.page.locator(mount).count(), 1)

    def test_swipe_changes_channel_but_banner_swipe_does_not(self):
        self.open()
        self.swipe(330, 700, 40, 690)
        self.assertEqual(self.channel_index(), 1)
        self.assertEqual(self.section_top('world'), 0, '左滑跳到下一个频道的开头')
        self.swipe(40, 700, 340, 705)
        self.assertEqual(self.channel_index(), 0)
        self.assertEqual(self.section_top('current'), 0)
        banner = self.page.locator('.ch-sec[data-ch=current] .banner-rail')
        self.assertEqual(self.page.locator('.ch-sec[data-ch=current] .banner-slide').count(), 5)
        box = banner.bounding_box()
        y = box['y'] + box['height'] / 2
        self.swipe(box['x'] + box['width'] - 20, y, box['x'] + 20, y)
        self.assertEqual(self.channel_index(), 0, 'banner 内横滑只滑 banner')
        self.assertEqual(self.page.locator('.ch-sec[data-ch=current] .banner-pager').inner_text(), '2 / 5')

    def test_hotsearch_view_tabs_and_failure_state(self):
        # 2026-11-15 21:26：热搜从时事频道移到底栏「热搜」页，频道里不再有热搜块
        self.open()
        self.assertEqual(self.page.locator('#channelRoot .hot').count(), 0)
        self.page.locator('.tabbar [data-view=hot]').click()
        hot = self.page.locator('#view-hot .hot')
        hot.wait_for()
        self.assertEqual(hot.locator('[role=tab] b').all_inner_texts(), ['百度', '知乎', 'B站'])
        self.assertEqual(hot.locator('.hot-list li').count(), 12, '热搜页直接列全部')
        self.assertEqual(self.page.locator('#hotHost [data-end=hot]').inner_text(), '内容已结束')
        self.assertEqual(self.page.locator('#hotDates .chip').all_inner_texts(), ['今天'])
        hot.locator('[data-hot=zhihu]').click()
        self.assertIn('暂时取不到', self.page.locator('#view-hot .hot-empty').inner_text())

    def test_feed_cards_and_infinite_load_to_end(self):
        self.open()
        page = self.page.locator('.ch-sec[data-ch=current]')
        self.assertEqual(page.locator('.feed-row').count(), 30)
        # banner 仍只挑合格大图；列表里凡是有图（含短边不够 banner 标准的 tnews365:8）都显示缩略图
        self.assertEqual(page.locator('.feed-row:not(.noimg)').count(), 3, '有图的列表项都显示缩略图（含短边 < 240 的）')
        self.assertEqual(page.locator('.feed-row[data-id="tnews365:8"]:not(.noimg)').count(), 1)
        self.assertIn('这条没有正文摘要', page.locator('.feed-row[data-id="tnews365:9"]').inner_text(), '无图且无摘要才显示占位句')
        self.assertTrue(self.page.locator('.ch-sec[data-ch=world]').evaluate('e => e.hidden'), '时事没加载完之前，下一个频道不露出来')
        self.assertTrue(self.scroll_to_end('#channelRoot'))
        self.assertEqual(page.locator('.feed-row').count(), 65)
        self.assertEqual(page.locator('.feed-foot').inner_text().strip(), '下一个：环球', '一个频道刷完接下一个，中间一条细分隔')
        names = self.page.locator('#channelRoot > .ch-sec').evaluate_all('es => es.map(e => [e.dataset.ch, e.hidden, e.querySelector(".feed-foot").innerText.trim()])')
        self.assertEqual([n[0] for n in names], ['current', 'world', 'finance', 'tech-ai', 'digital', 'tools'])
        self.assertTrue(all(not n[1] for n in names), names)
        self.assertEqual([n[2] for n in names][1:], ['下一个：财经', '下一个：科技与 AI', '下一个：数码', '下一个：工具与项目', '内容已结束'])
        self.assertEqual(self.channel_index(), 5, '到底时吸顶标题是最后一个频道')
        self.assertEqual(self.page.locator('#channelRoot [data-end=all]').count(), 1)

    def test_header_follows_scrolled_channel(self):
        self.open()
        self.scroll_to_end('#channelRoot')
        for slug in ('world', 'finance', 'current'):
            self.page.evaluate(f"""(() => {{ const r = document.querySelector('#channelRoot'), s = r.querySelector('.ch-sec[data-ch="{slug}"]');
              r.scrollTop += s.getBoundingClientRect().top - r.getBoundingClientRect().top + 40; }})()""")
            self.page.wait_for_timeout(150)
            self.assertEqual(self.page.locator('#channelRoot').get_attribute('data-cur'), slug)
            name = self.page.locator(f'.ch-sec[data-ch="{slug}"] h2.ch').inner_text()
            self.assertEqual(self.page.locator('#chName').inner_text(), name, 'v16：顶栏频道名跟着当前这一段变')

    def test_article_full_page_and_back_restores_channel_and_scroll(self):
        self.open()
        self.swipe(330, 700, 40, 690)
        self.page.locator('.ch-sec[data-ch=world] .feed-row').first.click()
        self.assertIn('机器翻译', self.page.locator('#articleBody').inner_text())
        self.page.locator('#articleBody [data-art-orig]').click()
        self.assertIn('Synthetic headline', self.page.locator('[data-art-orig-box]').inner_text())
        self.page.locator('#btnBack').click()
        self.page.wait_for_timeout(300)
        self.assertEqual(self.channel_index(), 1)
        current = self.page.locator('#channelRoot')
        current.evaluate('e => e.scrollTop = 900')
        self.page.wait_for_timeout(300)
        row = self.page.locator('.ch-sec[data-ch=current] .feed-row').nth(12)
        row.evaluate('e => e.scrollIntoView({block: "center"})')   # v16 底栏悬浮在内容上，别让点击点落在底栏下面
        self.page.wait_for_timeout(200)
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
        self.assertEqual(self.page.locator('#channelRoot > .ch-sec').count(), 6)

    def test_old_more_links_jump_into_the_feed(self):
        self.open('#/more/ch%3Afinance')
        self.page.wait_for_timeout(300)
        self.assertEqual(self.page.locator('#channelRoot').get_attribute('data-cur'), 'finance')
        self.assertEqual(self.section_top('finance'), 0)
        self.open('#/more/bl%3Ax%3Aall')
        self.page.wait_for_selector('#view-blogger.on #bloggerList .tweet')
        self.assertEqual(self.page.locator('#platChips .on').get_attribute('data-plat'), 'x')

    def test_deep_link_in_already_open_tab(self):
        self.open()
        self.page.locator('#channelRoot').evaluate('e => e.scrollTop = 400')
        self.page.evaluate("location.hash = '#/item/tnews365%3A69'")
        self.page.wait_for_selector('#articleView.on')
        self.assertIn('current 合成标题 69', self.page.locator('#articleBody').inner_text())
        self.page.locator('#btnBack').click()
        self.page.wait_for_timeout(400)
        self.assertFalse(self.page.locator('#articleView').is_visible())
        self.assertEqual(self.page.locator('#channelRoot').evaluate('e => e.scrollTop'), 400)

    def test_vertical_mode_same_feed_no_swipe_and_remembered(self):
        self.open()
        self.page.locator('#chBtn').click()
        self.page.locator('#modeUD').click()
        self.assertEqual(self.page.locator('#channelRoot').get_attribute('class'), 'feed-root ud')
        self.assertEqual(self.page.locator('.ch-sec[data-ch=current] .banner-slide').count(), 5)
        self.assertEqual(self.page.locator('[data-more]').count(), 0, '没有「继续看」按钮，下滑自动加载')
        self.swipe(330, 700, 40, 690)
        self.assertEqual(self.channel_index(), 0, '上下模式横滑不换频道')
        self.assertTrue(self.scroll_to_end('#channelRoot'))
        self.assertEqual(self.page.locator('.ch-sec[data-ch=current] .feed-row').count(), 65)
        self.page.reload()
        self.page.wait_for_selector('#app:not([aria-busy])')
        self.assertFalse(self.page.locator('#drop').evaluate('e => e.classList.contains("on")'))
        self.assertTrue(self.page.locator('#modeUD').evaluate('e => e.classList.contains("on")'))

    def test_cards_have_no_swipe_actions_only_long_press_menu(self):
        """2026-11-16 22:47 阿欢：去掉左滑收藏 / 右滑分享；收藏、分享一律长按弹菜单（频道/博主/收藏/热搜一致）"""
        self.open()
        self.page.locator('#chBtn').click()
        self.page.locator('#modeUD').click()
        self.assertFalse(self.page.locator('#drop').evaluate('e => e.classList.contains("on")'), '选完模式下拉自动收起')
        row = self.page.locator('.ch-sec[data-ch=current] .feed-row').nth(1)
        row.scroll_into_view_if_needed()
        box = row.bounding_box()
        y = box['y'] + box['height'] / 2
        self.swipe(box['x'] + box['width'] - 10, y, box['x'] + 10, y)    # 左滑
        self.swipe(box['x'] + 10, y, box['x'] + box['width'] - 10, y)    # 右滑
        self.assertEqual(self.page.evaluate("localStorage.getItem('rebang.favorites.v1')"), None, '横滑不再收藏')
        self.assertEqual(self.page.locator('.swiping, [data-swipe]').count(), 0)
        self.assertFalse(self.page.locator('#cardMenu').evaluate('e => e.classList.contains("on")'))
        # 频道：长按 → 菜单 → 收藏
        self.long_press(row)
        self.assertTrue(self.page.locator('#cardMenu.on').is_visible())
        self.assertEqual(self.page.locator('#cardMenu [data-menu]').all_inner_texts()[:3], ['收藏', '分享', '复制链接'])
        self.page.locator('#cardMenu [data-menu=fav]').click()
        self.assertEqual(len(self.page.evaluate("RebangFavorites.load()")), 1)
        # 博主
        self.page.locator('.tabbar [data-view=blogger]').click()
        tweet = self.page.locator('#bloggerList .tweet').first
        tweet.wait_for()
        self.long_press(tweet)
        self.assertTrue(self.page.locator('#cardMenu.on').is_visible())
        self.page.locator('#cardMenu [data-menu=cancel]').click()
        # 热搜：长按一行也是同一个菜单，收藏进本机
        self.page.locator('.tabbar [data-view=hot]').click()
        li = self.page.locator('#view-hot .hot-list li').first
        li.wait_for()
        self.assertEqual(self.page.locator('#app').evaluate('e => e.scrollTop'), 0, '整个外壳不会被挪位（面板藏在屏外不撑出滚动）')
        self.long_press(li)
        self.assertTrue(self.page.locator('#cardMenu.on').is_visible())
        self.page.locator('#cardMenu [data-menu=fav]').click()
        self.assertEqual(len(self.page.evaluate("RebangFavorites.load()")), 2)
        self.assertTrue(self.page.locator('#view-hot').evaluate('e => e.classList.contains("on")'), '长按松手不会打开外链')
        # 收藏：长按同样出菜单
        self.page.locator('.tabbar [data-view=favorites]').click()
        fav = self.page.locator('[data-favorites-list] [data-item-id]').first
        fav.wait_for()
        self.assertNotIn('左滑', self.page.locator('#view-favorites').inner_text())
        self.long_press(fav)
        self.assertTrue(self.page.locator('#cardMenu.on').is_visible())

    def test_favorites_infinite_scroll_to_end(self):
        self.open()
        self.page.evaluate("""RebangFavorites.save(Array.from({length: 75}, (_, i) => ({id: 'fav-' + i, title: '收藏 ' + i, source_name: '测试'})))""")
        self.page.locator('.tabbar [data-view=favorites]').click()
        rows = self.page.locator('[data-favorites-list] [data-item-id]')
        rows.first.wait_for()
        self.assertEqual(rows.count(), 30)
        for _ in range(8):
            self.page.locator('#view-favorites .rebang-favorites').evaluate('e => e.scrollTop = e.scrollHeight')
            self.page.wait_for_timeout(150)
        self.assertEqual(rows.count(), 75)
        self.assertEqual(self.page.locator('#view-favorites [data-end=favorites]').inner_text(), '内容已结束')

    def test_feature_queue_ctx_and_favorite_slot_only_in_article(self):
        self.stub_features = True
        self.page.add_init_script(STUB)
        self.open()
        self.assertEqual(self.page.locator('.ch-sec [data-favorite-button], .ch-sec .fav').count(), 0, '列表里没有收藏按钮')
        self.page.locator('.tabbar [data-view=favorites]').click()
        self.assertEqual(self.page.locator('#stub-fav').inner_text(), '收藏桩')
        self.assertEqual(self.page.evaluate('window.__ctx'), {'dataBase': 'data', 'now': True, 'openItem': 'function', 'toast': 'function'})
        self.page.locator('.tabbar [data-view=channels]').click()
        self.page.locator('.ch-sec[data-ch=current] .feed-row').first.click()
        self.assertEqual(self.page.locator('#articleBody #stub-fav-btn').count(), 1)
        self.assertEqual(self.page.evaluate('window.__attached'), 'tnews365:5')
        self.page.locator('#btnBack').click()

    def test_blogger_tab_real_empty_states(self):
        self.open()
        self.page.locator('.tabbar [data-view=blogger]').click()
        self.page.wait_for_selector('#bloggerList .tweet')
        self.assertEqual(self.page.locator('#bloggerList .bl-seg[data-plat=x] .tweet').count(), 2)
        self.page.locator('#platChips [data-plat=weibo]').click()
        self.page.wait_for_timeout(300)
        self.assertIn('还没有成功抓取过', self.page.locator('#bloggerList .bl-seg[data-plat=weibo]').inner_text())
        self.assertEqual(self.page.locator('#platChips .on').get_attribute('data-plat'), 'weibo')
        self.page.locator('#platChips [data-plat=zhihu]').click()
        self.assertIn('知乎', self.page.locator('#bloggerList .bl-seg[data-plat=zhihu]').inner_text())

    def test_blogger_one_feed_chains_platforms_to_end(self):
        self.open()
        self.page.locator('.tabbar [data-view=blogger]').click()
        self.page.wait_for_selector('#bloggerList .tweet')
        order = self.page.locator('#platChips [data-plat]').evaluate_all('es => es.map(e => e.dataset.plat)')
        self.assertTrue(self.scroll_to_end('#view-blogger .sub'))
        segs = self.page.locator('#bloggerList .bl-seg').evaluate_all('es => es.map(e => [e.dataset.plat, e.hidden, e.querySelector(".bl-foot").innerText.trim()])')
        self.assertEqual([x[0] for x in segs], order, '顺序同顶部图标从左到右')
        self.assertTrue(all(not x[1] for x in segs), segs)
        self.assertTrue(segs[0][2].endswith('下一个：' + self.page.locator(f'#platChips [data-plat="{order[1]}"]').get_attribute('aria-label')), segs[0])
        self.assertTrue(segs[-1][2].endswith('内容已结束'), segs[-1])
        self.assertEqual(self.page.locator('#bloggerList [data-end=all]').count(), 1)
        self.assertEqual(self.page.locator('.see-more-bl, [data-see]').count(), 0)
        # 点某个人：这个平台按人分段，从这个人开始，刷完接同平台下一个人
        self.page.locator('#view-blogger .sub').evaluate('e => e.scrollTop = 0')
        person = self.page.locator('#bloggerList .people[data-people=x] [data-person]:not([data-person=all])').first
        handle = person.get_attribute('data-person')
        person.click()
        self.page.wait_for_timeout(400)
        cur = self.page.locator('#bloggerList').get_attribute('data-cur')
        self.assertEqual(self.page.locator(f'#bloggerList .bl-seg[data-seg="{cur}"]').get_attribute('data-handle'), handle)

    def test_v16_read_grey_font_sheets_and_no_red_ring(self):
        """2026-11-16 23:43 阿欢批 v16：读过变灰、详情字号可调、评论/分享底部半屏、博主 X 头像不加红圈"""
        self.open()
        row = self.page.locator('.ch-sec[data-ch=current] .feed-row').nth(1)
        rid = row.get_attribute('data-id')
        h3 = row.locator('h3')
        unread = h3.evaluate('e => getComputedStyle(e).color')
        row.click()
        self.page.wait_for_selector('#articleView.on')
        size = lambda: self.page.locator('#articleBody .art-text, #articleBody .t-body').first.evaluate('e => parseFloat(getComputedStyle(e).fontSize)')
        self.assertEqual(size(), 18)
        self.page.locator('#dFont').click()
        self.page.locator('#fontRange').fill('22')
        self.assertEqual(size(), 22)
        self.page.locator('#actSheet [data-act=x]').click()
        self.page.locator('#dCmt').click()
        self.assertTrue(self.page.locator('#actSheet.on .act-box.half, #actSheet.on').first.is_visible())
        self.assertEqual(self.page.locator('#actSheet').evaluate('e => e.classList.contains("on")'), True)
        self.page.keyboard.press('Escape')
        self.page.locator('#dShare').click()
        self.assertEqual(self.page.locator('#actSheet [data-act]').all_inner_texts()[:2], ['系统分享', '复制链接'])
        self.page.keyboard.press('Escape')
        self.page.locator('#btnBack').click()
        self.page.wait_for_timeout(300)
        row = self.page.locator(f'.ch-sec[data-ch=current] .feed-row[data-id="{rid}"]')
        self.assertTrue(row.evaluate('e => e.classList.contains("read")'), '读过的标记 read')
        self.assertNotEqual(row.locator('h3').evaluate('e => getComputedStyle(e).color'), unread, '读过变灰')
        self.page.reload()
        self.page.wait_for_selector('#app:not([aria-busy])')
        self.assertTrue(self.page.locator(f'.feed-row[data-id="{rid}"]').evaluate('e => e.classList.contains("read")'), '刷新后仍是已读')
        self.assertEqual(self.page.evaluate("getComputedStyle(document.documentElement).getPropertyValue('--rfs').trim()"), '22px', '字号记住')
        # 博主：选中的 X 头像不加红圈
        self.page.locator('.tabbar [data-view=blogger]').click()
        on = self.page.locator('#platChips .avb.on .avc')
        on.wait_for()
        ring = on.evaluate("e => { const s = getComputedStyle(e); return [s.borderTopWidth, s.borderTopStyle, s.outlineStyle, s.boxShadow]; }")
        self.assertTrue(ring[0] == '0px' or ring[1] == 'none', ring)
        self.assertEqual(ring[2], 'none', ring)
        self.assertNotIn('rgb(2', ring[3].replace('rgba(0, 0, 0', ''), ring)
        self.assertEqual(self.page.locator('#view-blogger .avall').inner_text().strip(), '全部')
        self.assertRegex(self.page.locator('#bloggerList .dayh').first.inner_text().replace('\n', ' '), r'^\d+\.\d+ (今天|昨天|周.) 更新 \d+ 篇$')

    def video_state(self):
        return self.page.evaluate('''() => { const v = document.querySelector('#zoomStage video'); if (!v) return null;
          return {paused: v.paused, muted: v.muted, controls: v.controls, loop: v.loop, poster: v.poster, t: v.currentTime, rs: v.readyState}; }''')

    def test_video_player_mixed_media_swipe_and_error_fallback(self):
        self.open()
        self.page.locator('.tabbar [data-view=blogger]').click()
        card = self.page.locator('#bloggerList .tweet[data-id="x-dotey:0"]')
        card.wait_for()
        # v16：列表行只放一张缩略图（在右边）+「3 项」，全部图片和视频在全屏查看器里
        thumb = card.locator('.thumb')
        self.assertEqual(thumb.locator('.cell').count(), 1)
        self.assertIn('3 项', thumb.inner_text())
        self.assertLess(card.locator('.b-main').bounding_box()['x'], thumb.bounding_box()['x'], '缩略图在右边')
        thumb.tap()
        self.page.wait_for_selector('#zoomView.on #zoomStage > img')
        self.assertEqual(self.page.inner_text('#zoomCount'), '1 / 3')
        self.page.locator('#zoomNext').tap()
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
        bad = self.page.locator('#bloggerList .tweet[data-id="x-simonw:1"] .thumb .cell.is-vid')
        bad.scroll_into_view_if_needed()
        bad.tap()
        self.page.wait_for_selector('#zoomStage .zoom-fail a')
        self.assertEqual(self.page.get_attribute('#zoomStage .zoom-fail a', 'href'), 'https://x.com/simonw/status/1')
        self.assertEqual(self.page.locator('#zoomStage .zoom-fail img').count(), 1)
        # 普通图片：点一下仍然关闭
        self.page.locator('#zoomClose').tap()

    def test_telegram_article_plays_video_opens_photo_and_links_unsupported(self):
        self.open('#/item/tnews365%3A8')
        article = self.page.locator('#articleView.on #articleBody')
        self.assertEqual(article.get_by_text('在 Telegram 查看无法内播的视频').get_attribute('href'), 'https://t.me/tnews365/8')
        article.locator('.media-grid .cell.is-vid').tap()
        video = self.page.locator('#zoomStage video')
        video.evaluate('v => v.play()')
        self.page.wait_for_function("document.querySelector('#zoomStage video').currentTime > 0.3")
        self.page.locator('#zoomNext').tap()
        self.assertEqual(self.page.locator('#zoomStage > img').get_attribute('src'), 'https://img.test/p0.png')
        self.page.wait_for_function("document.querySelector('#zoomStage > img').naturalWidth > 0")

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
        current = self.page.locator('#channelRoot')
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
