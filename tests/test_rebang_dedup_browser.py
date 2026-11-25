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
DUP_URL = 'https://news.test/deepseek-api'
HERO_URL = 'https://news.test/hero-open-model'


def snapshot(ident, title):
    """收藏 / 搜索索引里存的快照：没有正文。"""
    source, n = ident.split(':')
    return {'id': ident, 'kind': 'news', 'channel': 'current', 'source_id': source, 'source_name': source,
            'title': title, 'summary': '', 'url': f'https://example.com/{source}/{n}', 'published_at': NOW.isoformat(),
            'lang': 'zh', 'translated': False, 'translation': None, 'image': None}


SEARCH_ENTRIES = [snapshot('tnews365:900', 'DeepSeek 开放全家桶应用 API 合成测试'),
                  snapshot('freechinese:901', 'DeepSeek 开放全家桶应用 API 合成测试')]


def dup_items():
    # 只有同链接且原标题相同、不同来源才合并
    return [news('freechinese', 'current', 901, minutes=0, title='DeepSeek 开放全家桶应用 API 合成测试',
                 url=DUP_URL, body='被折叠那条的正文', **HL),
            news('tnews365', 'current', 900, minutes=1, title='DeepSeek 开放全家桶应用 API 合成测试', url=DUP_URL, **HL),
            # 顶部大图卡上的主条（比时事其它条都新，排在 banner 第 1 屏）
            news('myBigCharacterPoster', 'current', 961, minutes=-3, title='大图卡折叠测试：谷歌发布新一代开源模型 面向开发者',
                 url=HERO_URL, image=img(961)),
            news('shuangyunews_rss', 'current', 960, minutes=-4, title='大图卡折叠测试：谷歌发布新一代开源模型 面向开发者',
                 url=HERO_URL, image=img(960), body='大图卡折叠那条的正文'),
            # 原始链接完全相同、标题不同的两条：不合，两个 id 都要能打开
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

        self.hold_paths, self.held = set(), []    # 挂起这些路径的请求，测试里再放行（模拟慢网 / 卡死）

        def serve(route):
            url = urlsplit(route.request.url)
            if url.netloc != 'rebang.test':
                return route.abort()
            if url.path in self.hold_paths:
                self.held.append(route)
                return None
            return self.fulfill(route)
        self.page.route('**/*', serve)

    def fulfill(self, route):
        url = urlsplit(route.request.url)
        if url.path == '/data/search-index.json':
            return route.fulfill(status=200, content_type='application/json', body=json.dumps({'entries': SEARCH_ENTRIES}))
        path = self.out / (unquote(url.path).lstrip('/') or 'index.html')
        route.fulfill(status=200 if path.is_file() else 404, body=path.read_bytes() if path.is_file() else b'missing',
                      content_type=mimetypes.guess_type(str(path))[0] or 'application/octet-stream')

    def release(self):
        self.hold_paths.clear()
        held, self.held = self.held, []
        for route in held:
            try:
                self.fulfill(route)
            except Exception:  # noqa: BLE001  请求可能已被页面中止（超时）
                pass

    def wait_held(self):
        for _ in range(60):                                       # 等请求真被挂起
            if self.held:
                return
            self.page.wait_for_timeout(50)
        self.fail('请求没有被挂起')

    def assert_detail_closed(self):
        self.assertFalse(self.page.locator('#articleView').evaluate('e => e.classList.contains("on")'))
        self.assertNotIn('#/item/', self.page.evaluate('location.hash'))

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
        snap = snapshot('freechinese:901', 'DeepSeek 开放全家桶应用 API 合成测试')
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

    def test_back_from_search_opened_folded_item_returns_to_search_results(self):
        self.open_home()
        self.page.locator('#btnSearch').click()
        self.page.wait_for_selector('#search-panel.on [data-search-input]')
        self.page.locator('[data-search-input]').fill('合成测试')
        hit = self.page.locator('[data-search-hit="freechinese:901"]')
        hit.wait_for()
        hit.click()                                               # 被折叠的条目：要先异步读 id-index、merged.json
        self.page.wait_for_selector('#articleView.on')
        self.assertIn('被折叠那条的正文', self.page.locator('#articleBody').inner_text())
        self.page.locator('#btnBack').click()
        self.page.wait_for_selector('#search-panel.on')
        self.assertFalse(self.page.locator('#articleView').evaluate('e => e.classList.contains("on")'))
        self.assertTrue(self.page.locator('[data-search-hit="freechinese:901"]').is_visible())
        self.assertEqual(self.page.locator('[data-search-input]').input_value(), '合成测试')

    def test_later_open_wins_over_slow_earlier_open(self):
        self.open_home()
        self.hold_paths.add('/data/id-index.json')
        self.page.evaluate("() => { window.Rebang.openItem('freechinese:901'); }")      # A：要读 id-index，被挂起
        self.wait_held()
        self.page.evaluate("() => { window.Rebang.openItem('myBigCharacterPoster:961'); }")   # B：已在内存
        self.page.wait_for_selector('#articleView.on')
        self.release()                                            # A 现在才读完：结果过期，丢弃
        self.page.wait_for_timeout(600)
        self.assertIn('大图卡折叠测试', self.page.locator('#articleTitle').inner_text())
        self.assertEqual(self.page.evaluate('location.hash'), '#/item/myBigCharacterPoster%3A961')

    def test_hung_index_request_times_out_and_late_response_does_not_override_snapshot(self):
        self.open_home()
        self.hold_paths.add('/data/id-index.json')
        self.page.evaluate("s => { window.Rebang.openItem(s); }", snapshot('freechinese:901', '快照里的标题 合成测试'))
        start = self.page.evaluate('performance.now()')
        self.page.wait_for_selector('#articleView.on', timeout=9000)
        waited = self.page.evaluate('performance.now()') - start
        self.assertIn('快照里的标题', self.page.locator('#articleTitle').inner_text())
        self.assertGreater(waited, 3000)
        self.assertEqual(self.page.evaluate('location.hash'), '#/item/freechinese%3A901')
        self.release()                                            # 超时之后才晚到的响应：不覆盖已显示的快照
        self.page.wait_for_timeout(600)
        self.assertIn('快照里的标题', self.page.locator('#articleTitle').inner_text())
        self.assertNotIn('被折叠那条的正文', self.page.locator('#articleBody').inner_text())
        self.assertEqual(self.page.evaluate('location.hash'), '#/item/freechinese%3A901')

    def test_back_while_next_item_is_loading_does_not_reopen_detail(self):
        self.open_home()
        self.page.locator('#btnSearch').click()
        self.page.wait_for_selector('#search-panel.on [data-search-input]')
        self.page.locator('[data-search-input]').fill('合成测试')
        self.page.locator('[data-search-hit="freechinese:901"]').wait_for()
        ids = self.page.evaluate("() => [...document.querySelectorAll('[data-search-hit]')].map(e => e.dataset.searchHit)")
        self.page.locator('[data-search-hit="tnews365:900"]').click()   # 已在内存：立刻打开
        self.page.wait_for_selector('#articleView.on')
        hash_before = self.page.evaluate('location.hash')
        # 「下一条 / 上一条」指向被折叠的 901：要读 id-index、merged.json，全部挂起
        self.hold_paths.update({'/data/id-index.json', '/data/channel/current/merged.json'})
        direction = '1' if ids.index('freechinese:901') > ids.index('tnews365:900') else '-1'
        self.page.locator(f'#artNav [data-nav="{direction}"]').click()
        self.wait_held()
        self.page.locator('#btnBack').click()
        self.page.wait_for_timeout(300)
        self.assert_detail_closed()
        hash_after_back = self.page.evaluate('location.hash')
        self.release()
        self.page.wait_for_timeout(800)
        self.assert_detail_closed()                               # 放行后不重开详情
        self.assertEqual(self.page.evaluate('location.hash'), hash_after_back)   # 地址栏不变
        self.assertNotEqual(hash_after_back, hash_before)

    def test_browser_back_during_slow_deep_link_does_not_open_detail(self):
        self.open_home()
        self.hold_paths.add('/data/id-index.json')
        self.page.evaluate("() => { location.hash = '#/item/freechinese%3A901'; }")   # 正文还没显示
        self.wait_held()
        self.page.evaluate('() => history.back()')
        self.page.wait_for_function("() => !location.hash")
        self.release()
        self.page.wait_for_timeout(800)
        self.assert_detail_closed()
        self.assertEqual(self.page.evaluate('location.hash'), '')

    def test_switching_tab_during_slow_open_does_not_open_detail(self):
        self.open_home()
        self.hold_paths.add('/data/id-index.json')
        self.page.evaluate("() => { window.Rebang.openItem('freechinese:901'); }")
        self.wait_held()
        self.page.locator('.tabbar button[data-view="hot"]').click()
        self.release()
        self.page.wait_for_timeout(800)
        self.assert_detail_closed()
        self.assertEqual(self.page.evaluate('location.hash'), '')

    def test_opening_health_cancels_in_flight_detail_open(self):
        self.open_home()
        self.hold_paths.add('/data/id-index.json')
        self.page.evaluate("() => { window.Rebang.openItem('freechinese:901'); }")
        self.wait_held()
        self.page.locator('#healthEntry').click()
        self.page.wait_for_function("() => document.querySelector('#healthView').open")
        self.release()
        self.page.wait_for_timeout(600)
        self.assert_detail_closed()
        self.assertEqual(self.page.evaluate('location.hash'), '#/health')

    def test_reopening_search_cancels_in_flight_detail_open(self):
        self.open_home()
        self.page.locator('#btnSearch').click()
        self.page.wait_for_selector('#search-panel.on [data-search-input]')
        self.page.locator('[data-search-input]').fill('合成测试')
        self.page.locator('[data-search-hit="freechinese:901"]').wait_for()
        self.hold_paths.add('/data/id-index.json')
        self.page.locator('[data-search-hit="freechinese:901"]').click()
        self.wait_held()
        self.page.locator('#btnSearch').click()
        self.page.wait_for_selector('#search-panel.on')
        self.release()
        self.page.wait_for_timeout(600)
        self.assert_detail_closed()
        self.assertTrue(self.page.locator('#search-panel').evaluate("el => el.classList.contains('on')"))

    def test_failed_deep_link_keeps_url_and_body_consistent(self):
        self.open_home()
        self.page.evaluate("() => { location.hash = '#/item/nonexistent%3A99999'; }")
        self.page.wait_for_timeout(600)
        self.assert_detail_closed()
        self.assertEqual(self.page.evaluate('location.hash'), '')

    def test_search_detail_step_offline_falls_back_to_search_snapshot(self):
        self.open_home()
        self.page.locator('#btnSearch').click()
        self.page.wait_for_selector('#search-panel.on [data-search-input]')
        self.page.locator('[data-search-input]').fill('合成测试')
        self.page.locator('[data-search-hit="freechinese:901"]').wait_for()
        ids = self.page.evaluate("() => [...document.querySelectorAll('[data-search-hit]')].map(e => e.dataset.searchHit)")
        self.page.locator('[data-search-hit="tnews365:900"]').click()
        self.page.wait_for_selector('#articleView.on')
        # 断网（拦截 id-index 和 merged.json 返回 500），点上一条/下一条切到折叠条 901 应回退搜索快照打开
        self.page.route('**/data/id-index.json*', lambda route: route.fulfill(status=500, body=''))
        self.page.route('**/data/channel/*/merged.json*', lambda route: route.fulfill(status=500, body=''))
        direction = '1' if ids.index('freechinese:901') > ids.index('tnews365:900') else '-1'
        self.page.locator(f'#artNav [data-nav="{direction}"]').click()
        self.page.wait_for_function("() => location.hash.includes('freechinese%3A901')")
        self.assertIn('合成测试', self.page.locator('#articleBody').inner_text())

    def test_stale_merged_response_after_refresh_does_not_pollute_cache(self):
        self.open_home()
        self.hold_paths.add('/data/channel/current/merged.json')
        self.page.evaluate("() => { window.Rebang.openItem('freechinese:901'); }")
        self.wait_held()
        # 模拟版本刷新：返回新的 built_at 与新的 merged.json 标题
        self.page.route('**/data/meta.json*', lambda route: route.fulfill(
            status=200, content_type='application/json',
            body=json.dumps({**json.loads((self.out / 'data' / 'meta.json').read_text(encoding='utf-8')),
                             'built_at': '2026-11-26T00:00:00+08:00'})))
        self.page.locator('#btnRefresh').click()
        self.page.wait_for_timeout(400)
        # 放行旧版 merged.json：不应污染新版缓存，也不应打开旧详情
        self.release()
        self.page.wait_for_timeout(600)
        self.assert_detail_closed()
        # 新版本下再次打开 901，应重新请求新版 merged.json 而不是读到旧缓存
        new_merged_hits = []
        def serve_new_merged(route):
            new_merged_hits.append(route.request.url)
            payload = json.loads((self.out / 'data' / 'channel' / 'current' / 'merged.json').read_text(encoding='utf-8'))
            for it in payload['items']:
                if it['id'] == 'freechinese:901':
                    it['body'] = '新版正文标记'
            route.fulfill(status=200, content_type='application/json', body=json.dumps(payload))
        self.page.route('**/data/channel/current/merged.json*', serve_new_merged)
        self.page.evaluate("() => { window.Rebang.openItem('freechinese:901'); }")
        self.page.wait_for_selector('#articleView.on')
        self.assertTrue(new_merged_hits)
        self.assertIn('新版正文标记', self.page.locator('#articleBody').inner_text())

    def _trigger_version_refresh(self, built_at='2026-11-26T00:00:00+08:00'):
        meta_body = json.dumps({**json.loads((self.out / 'data' / 'meta.json').read_text(encoding='utf-8')),
                                'built_at': built_at})
        self.page.route('**/data/meta.json*', lambda route: route.fulfill(
            status=200, content_type='application/json', body=meta_body))
        self.page.evaluate("() => document.querySelector('#btnRefresh').click()")

    def _dispatch_right_swipe_back(self):
        self.page.evaluate("""() => {
          const av = document.querySelector('#articleView');
          const mk = (type, x) => {
            const touch = new Touch({identifier: 1, target: av, clientX: x, clientY: 200, pageX: x, pageY: 200});
            const touches = type === 'touchend' ? [] : [touch];
            return new TouchEvent(type, {bubbles: true, cancelable: true, touches, targetTouches: touches, changedTouches: [touch]});
          };
          av.dispatchEvent(mk('touchstart', 10));
          av.dispatchEvent(mk('touchmove', 30));
          av.dispatchEvent(mk('touchmove', 150));
          av.dispatchEvent(mk('touchend', 150));
        }""")

    def test_right_swipe_back_still_closes_if_refresh_runs_during_animation(self):
        self.open_home()
        self.page.evaluate("() => { window.Rebang.openItem('tnews365:900'); }")
        self.page.wait_for_selector('#articleView.on')
        self._dispatch_right_swipe_back()
        # 动画未结束前触发新版本刷新（会递增 openSeq）：旧正文仍应正常关闭，不能留在屏外
        self._trigger_version_refresh()
        self.page.wait_for_timeout(500)
        self.assert_detail_closed()
        self.assertEqual(self.page.locator('#articleView').evaluate('e => e.style.transform'), '')
        self.assertEqual(self.page.evaluate('location.hash'), '')

    def test_right_swipe_timer_does_not_close_newly_opened_article(self):
        self.open_home()
        self.page.evaluate("() => { window.Rebang.openItem('tnews365:900'); }")
        self.page.wait_for_selector('#articleView.on')
        self._dispatch_right_swipe_back()
        # 动画未结束前立刻打开另一篇新正文：旧定时器不能把新正文关掉
        self.page.evaluate("() => { window.Rebang.openItem('myBigCharacterPoster:961'); }")
        self.page.wait_for_timeout(500)
        self.assertTrue(self.page.locator('#articleView').evaluate('e => e.classList.contains("on")'))
        self.assertIn('大图卡折叠测试', self.page.locator('#articleTitle').inner_text())
        self.assertEqual(self.page.locator('#articleView').evaluate('e => e.style.transform'), '')

    def test_hot_deep_link_cancelled_by_refresh_cleans_up_article_and_hash(self):
        self.open_home()
        self.page.evaluate("() => { window.Rebang.openItem('tnews365:900'); }")
        self.page.wait_for_selector('#articleView.on')
        self.hold_paths.add('/data/id-index.json')
        # 正文 A 打开时，通过热深链改到 B；B 等待期间触发新版本刷新
        self.page.evaluate("() => { location.hash = '#/item/freechinese%3A901'; }")
        self.wait_held()
        self._trigger_version_refresh()
        self.release()
        self.page.wait_for_timeout(600)
        # 不能残留 A 的正文 + B 的地址栏
        self.assert_detail_closed()
        self.assertEqual(self.page.evaluate('location.hash'), '')

    def test_stale_blogger_responses_after_refresh_do_not_pollute_cache(self):
        bloggers_payload = json.loads((self.out / 'data' / 'bloggers.json').read_text(encoding='utf-8'))
        first_post = bloggers_payload['items'][0]
        first_id = first_post['id']
        first_plat = first_post['blogger']['platform']
        seg_path = f'/data/blogger/{first_plat}/all/page-1.json'
        seg_payload = json.loads((self.out / 'data' / 'blogger' / first_plat / 'all' / 'page-1.json').read_text(encoding='utf-8'))

        def mark_post(payload, text):
            copy = json.loads(json.dumps(payload))
            copy['items'][0]['summary'] = text
            copy['items'][0]['body'] = text
            return copy

        # 场景 1：旧 bloggers.json 晚于新版本刷新返回，不能污染 items 缓存
        self.open_home()
        self.hold_paths.add('/data/bloggers.json')
        self.page.locator('.tabbar button[data-view="blogger"]').click()
        self.wait_held()
        stale_bloggers = mark_post(bloggers_payload, '旧版博主索引脏数据')
        fresh_bloggers = mark_post(bloggers_payload, '新版博主索引正文')
        fresh_seg = mark_post(seg_payload, '新版博主分页正文')
        self.hold_paths.discard('/data/bloggers.json')
        self.page.route('**/data/bloggers.json*', lambda route: route.fulfill(
            status=200, content_type='application/json', body=json.dumps(fresh_bloggers)))
        self.page.route(f'**{seg_path}*', lambda route: route.fulfill(
            status=200, content_type='application/json', body=json.dumps(fresh_seg)))
        self._trigger_version_refresh('2026-11-26T00:00:00+08:00')
        self.page.wait_for_timeout(400)
        # 把挂起的旧 bloggers.json 放行（返回旧版脏数据）
        for r in self.held[:]:
            if urlsplit(r.request.url).path == '/data/bloggers.json':
                r.fulfill(status=200, content_type='application/json', body=json.dumps(stale_bloggers))
                self.held.remove(r)
        self.page.wait_for_timeout(400)
        self.page.evaluate("id => window.Rebang.openItem(id)", first_id)
        self.page.wait_for_selector('#articleView.on')
        body_txt = self.page.locator('#articleBody').inner_text()
        self.assertTrue('新版博主索引正文' in body_txt or '新版博主分页正文' in body_txt, body_txt)
        self.assertNotIn('旧版博主索引脏数据', body_txt)
        self.page.locator('#btnBack').click()
        self.page.wait_for_timeout(200)

        # 场景 2：旧 blogger 分页响应晚于新版本刷新返回，不能污染 items 缓存
        stale_seg = mark_post(seg_payload, '旧版博主分页脏数据')
        fresh_seg_v3 = mark_post(seg_payload, '新版博主分页v3')
        fresh_bloggers_v2 = mark_post(bloggers_payload, '新版博主索引v2')
        self.page.unroute('**/data/bloggers.json*')
        self.page.unroute(f'**{seg_path}*')
        self.page.route('**/data/bloggers.json*', lambda route: route.fulfill(
            status=200, content_type='application/json', body=json.dumps(fresh_bloggers_v2)))
        self.hold_paths.add(seg_path)
        self._trigger_version_refresh('2026-11-26T01:00:00+08:00')
        self.wait_held()
        # 此时 seg_path (v2) 已发出并挂起；再触发一次 v3 刷新，先让 v3 完成，再放行 v2 的旧分页
        self.hold_paths.discard(seg_path)
        self.page.route(f'**{seg_path}*', lambda route: route.fulfill(
            status=200, content_type='application/json', body=json.dumps(fresh_seg_v3)))
        self._trigger_version_refresh('2026-11-26T02:00:00+08:00')
        self.page.wait_for_timeout(400)
        for r in self.held[:]:
            if urlsplit(r.request.url).path == seg_path:
                r.fulfill(status=200, content_type='application/json', body=json.dumps(stale_seg))
                self.held.remove(r)
        self.page.wait_for_timeout(400)
        self.page.evaluate("id => window.Rebang.openItem(id)", first_id)
        self.page.wait_for_selector('#articleView.on')
        body_txt2 = self.page.locator('#articleBody').inner_text()
        self.assertIn('新版博主分页v3', body_txt2)
        self.assertNotIn('旧版博主分页脏数据', body_txt2)

if __name__ == '__main__':
    unittest.main()
