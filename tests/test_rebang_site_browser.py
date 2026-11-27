"""frontend-v11：手机尺寸（390×844）浏览器实测，离线、合成数据。
覆盖：频道一条长流（一直往下刷、「下一个：…」接下一段、到底「内容已结束」、吸顶标题跟着当前段）、
左右换频道（真触摸滑动，跳到下一频道开头）、banner 内横滑不换频道、两种翻法切换并记住、热搜分家与失败态、
卡片没有横滑动作只有长按菜单（频道/博主/收藏/热搜）、整页正文 + 返回原位置（页面返回与系统返回）、
#/item/<id> 深链、旧 #/more/ 链接跳到长流里那一段、底栏、功能模块注册与收藏槽。"""
import base64
import json
import mimetypes
import tempfile
import unittest
from datetime import timedelta
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
        (health_in / 'ingest.json').write_text(json.dumps(dict(envelope(site_items(), 'ingest'), sources=sources)), encoding='utf-8')
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
        if self._testMethodName.startswith('test_health_'):
            self.page.clock.set_fixed_time(NOW)
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
        dialog.get_by_role('button', name='5 个来源需处理', exact=False).wait_for()
        self.assertEqual(dialog.locator('.health-name').all_text_contents()[:4], ['微博', '竹新社', 'X', '卫报 World'])
        self.assertEqual(dialog.locator('.health-age').first.inner_text(), '2 天前')
        self.assertIn('2026年11月13日 15:00', dialog.locator('.health-age').first.get_attribute('title'))
        self.assertLessEqual(dialog.evaluate('e => e.scrollWidth'), 390)
        dialog.get_by_text('查看 6 个账号', exact=True).first.click()
        self.assertTrue(dialog.locator('.health-accounts[open] .health-account').first.is_visible())
        dialog.get_by_role('button', name='返回').click()
        dialog.wait_for(state='hidden')
        self.assertEqual(self.page.locator('.tabbar button').count(), 4)
        self.assertEqual(urlsplit(self.page.url).fragment, '')
        self.page.go_forward()
        dialog.wait_for()
        self.page.keyboard.press('Escape')
        dialog.wait_for(state='hidden')

    def test_health_channel_entry_opens_counted_groups_and_filters_sources(self):
        requested = []
        self.page.on('request', lambda request: requested.append(request.url))
        self.open()
        entry = self.page.get_by_role('link', name='来源状态，5 个来源需处理')
        self.assertTrue(entry.is_visible())
        self.assertEqual(entry.get_attribute('href'), '#/health')
        self.assertFalse(any('/data/health.json' in url for url in requested))
        self.assertEqual(self.page.locator('.tabbar button').count(), 4)
        entry.tap()
        dialog = self.page.get_by_role('dialog', name='来源健康')
        filters = dialog.get_by_role('group', name='按来源状态筛选')
        filters.wait_for()
        self.assertTrue(filters.evaluate('e => e.scrollWidth === e.clientWidth'))
        snapshot = json.loads((self.health_out / 'data/health.json').read_text())
        total = len(snapshot['sources'])
        self.assertEqual(filters.get_by_role('button').all_text_contents(),
                         ['登录失效 1', '失败 1', '断更 2', '未配置 1', f'正常 {total - 5}'])
        self.assertEqual(dialog.locator('.health-overview').inner_text(), f'5 个来源需处理 · {total - 5} 正常')
        overview = dialog.locator('.health-overview button')
        self.assertEqual(overview.get_attribute('aria-pressed'), 'true')
        self.assertFalse(dialog.locator('[data-health-group="ok"]').evaluate('e => e.open'))
        self.assertEqual(dialog.locator('details.health-section[open]').count(), 4)
        filters.get_by_role('button', name='断更 2').tap()
        self.assertEqual(filters.get_by_role('button', pressed=True).inner_text(), '断更 2')
        self.assertEqual(dialog.locator('.health-name:visible').all_text_contents(), ['X', '卫报 World'])
        self.assertTrue(dialog.get_by_text('检查原始转储', exact=False).is_visible())
        self.assertEqual(dialog.locator('.health-section-head:visible').count(), 0)
        filters.get_by_role('button', name='未配置 1').tap()
        self.assertEqual(dialog.locator('.health-name:visible').all_text_contents(), ['selfh.st'])
        self.assertTrue(dialog.get_by_text('需要时再接入', exact=False).is_visible())
        filters.get_by_role('button', name=f'正常 {total - 5}').tap()
        self.assertEqual(dialog.locator('.health-name:visible').count(), total - 5)
        overview.tap()
        self.assertFalse(dialog.locator('[data-health-group="ok"]').evaluate('e => e.open'))
        failed = dialog.locator('[data-health-group="failed"]')
        self.assertTrue(failed.is_visible())
        failed.locator('summary').tap()
        self.assertFalse(failed.evaluate('e => e.open'))
        self.assertFalse(failed.get_by_text('下轮重试', exact=False).is_visible())
        dialog.get_by_role('button', name='返回').tap()
        dialog.wait_for(state='hidden')
        self.assertTrue(entry.is_visible())

    def test_health_entry_remains_available_when_summary_is_missing_or_all_healthy(self):
        for summary in (None, {'total': 8, 'issues': 0}):
            with self.subTest(summary=summary):
                def serve_meta(route):
                    meta = json.loads((self.health_out / 'data/meta.json').read_text())
                    meta['health_summary'] = summary
                    route.fulfill(json=meta)

                self.page.route('**/data/meta.json*', serve_meta)
                self.open()
                entry = self.page.get_by_role('link', name='来源状态' if summary is None else '来源状态，全部健康', exact=True)
                self.assertTrue(entry.is_visible())
                self.assertNotIn('0', entry.inner_text())
                self.page.unroute('**/data/meta.json*', serve_meta)

    def test_health_all_normal_shows_only_normal_sources(self):
        snapshot = json.loads((self.health_out / 'data/health.json').read_text())
        snapshot['sources'] = [row for row in snapshot['sources'] if row['status'] == 'ok']
        self.page.route('**/data/health.json*', lambda route: route.fulfill(json=snapshot))
        self.open('#/health')
        dialog = self.page.get_by_role('dialog', name='来源健康')
        total = len(snapshot['sources'])
        self.assertEqual(dialog.locator('.health-overview').inner_text(), f'{total} 个来源全部正常')
        filters = dialog.get_by_role('group', name='按来源状态筛选')
        self.assertEqual(filters.get_by_role('button').all_text_contents(), [f'正常 {total}'])
        self.assertEqual(filters.get_by_role('button', pressed=True).inner_text(), f'正常 {total}')
        self.assertEqual(dialog.locator('.health-section-head:visible').count(), 0)
        self.assertEqual(dialog.locator('.health-name:visible').count(), total)

    def test_health_stale_snapshot_uses_wall_clock_in_entry_and_dialog(self):
        def serve_meta(route):
            meta = json.loads((self.health_out / 'data/meta.json').read_text())
            meta['health_summary']['issues'] = 0
            route.fulfill(json=meta)

        self.page.route('**/data/meta.json*', serve_meta)
        payload = json.loads((self.health_out / 'data/health.json').read_text())
        payload['sources'] = [row for row in payload['sources'] if row['status'] == 'ok']
        self.page.route('**/data/health.json*', lambda route: route.fulfill(json=payload))
        self.page.clock.set_fixed_time(NOW + timedelta(hours=3))
        self.open()
        self.page.get_by_role('link', name='来源状态，全部健康').wait_for()
        self.page.clock.set_fixed_time(NOW + timedelta(hours=4))
        self.open()
        entry = self.page.get_by_role('link', name='来源状态，数据已过期')
        entry.wait_for(timeout=3000)
        self.assertIn('数据已过期', entry.inner_text())
        self.assertTrue(entry.evaluate('e => e.classList.contains("has-issues")'))
        entry.tap()
        dialog = self.page.get_by_role('dialog', name='来源健康')
        dialog.get_by_text('数据已过期', exact=False).first.wait_for()
        self.assertIn('5 小时前', dialog.inner_text())
        self.assertNotIn('全部正常', dialog.inner_text())
        self.assertIn('北京时间', dialog.locator('#healthStamp').inner_text())

    def test_health_damaged_snapshot_keeps_visible_rows(self):
        payload = json.loads((self.health_out / 'data/health.json').read_text())
        payload['sources'].append(None)
        weibo = next(row for row in payload['sources'] if row['id'] == 'weibo')
        weibo['accounts'].append(None)
        x = next(row for row in payload['sources'] if row['id'] == 'x')
        x['accounts'] = 'damaged'
        self.page.route('**/data/health.json*', lambda route: route.fulfill(json=payload))
        self.open('#/health')
        dialog = self.page.get_by_role('dialog', name='来源健康')
        dialog.get_by_text('部分数据缺损', exact=False).wait_for(timeout=3000)
        self.assertEqual(dialog.locator('.health-name').all_text_contents()[:4], ['微博', '竹新社', 'X', '卫报 World'])
        self.assertNotIn('查看 7 个账号', dialog.inner_text())
        self.assertIn('查看 6 个账号', dialog.inner_text())

    def test_health_exact_time_is_visible_on_focus_and_tap(self):
        self.open('#/health')
        time = self.page.locator('.health-age:visible').first
        time.wait_for()
        time.focus()
        content = lambda: time.evaluate("e => getComputedStyle(e, '::after').content")
        self.assertIn('2026年11月13日 15:00', content())
        time.blur()
        self.assertEqual(content(), 'none')
        time.tap()
        self.assertIn('北京时间', content())

    def test_health_dialog_respects_standalone_app_height(self):
        self.open('#/health')
        dialog = self.page.locator('#healthView')
        dialog.wait_for()
        self.page.evaluate("""() => {
          document.documentElement.classList.add('app-fullscreen');
          document.documentElement.style.setProperty('--app-h', '900px');
        }""")
        self.assertEqual(dialog.evaluate('el => el.getBoundingClientRect().height'), 900)

    def test_health_open_dashboard_and_entry_age_past_three_hours(self):
        self.page.clock.install(time=NOW)
        def serve_meta(route):
            meta = json.loads((self.health_out / 'data/meta.json').read_text())
            meta['health_summary']['issues'] = 0
            route.fulfill(json=meta)

        snapshot = json.loads((self.health_out / 'data/health.json').read_text())
        snapshot['sources'] = [row for row in snapshot['sources'] if row['status'] == 'ok']
        self.page.route('**/data/meta.json*', serve_meta)
        self.page.route('**/data/health.json*', lambda route: route.fulfill(json=snapshot))
        self.open()
        entry = self.page.locator('#healthEntry')
        entry.click()
        stamp = self.page.locator('#healthStamp')
        stamp.wait_for(timeout=2500)
        self.assertIn('数据更新于', stamp.inner_text())
        overview = self.page.locator('.health-overview')
        self.assertIn('全部正常', overview.inner_text())
        self.assertNotIn('已过期', entry.inner_text())
        self.page.clock.fast_forward(3 * 3600 * 1000 + 1000)
        self.page.wait_for_function("document.querySelector('#healthEntry').textContent.includes('已过期')", timeout=2500)
        self.assertIn('已过期', stamp.inner_text())
        self.assertNotIn('全部正常', overview.inner_text())

    def test_health_same_build_refresh_and_visibility_recompute_freshness(self):
        self.open()
        entry = self.page.locator('#healthEntry')
        self.assertNotIn('已过期', entry.inner_text())
        self.page.clock.set_fixed_time(NOW + timedelta(hours=4))
        self.page.locator('#btnRefresh').click()
        entry.get_by_text('已过期').wait_for(timeout=2500)
        self.page.clock.set_fixed_time(NOW)
        self.page.evaluate("document.dispatchEvent(new Event('visibilitychange'))")
        self.assertNotIn('已过期', entry.inner_text())

    def test_health_invalid_timestamp_never_claims_everything_is_healthy(self):
        def serve_meta(route):
            meta = json.loads((self.health_out / 'data/meta.json').read_text())
            meta['built_at'] = 'invalid'
            meta['health_summary'] = {'total': 1, 'issues': 0}
            route.fulfill(json=meta)

        snapshot = json.loads((self.health_out / 'data/health.json').read_text())
        snapshot['generated_at'] = {'toString': None}
        snapshot['sources'] = [row for row in snapshot['sources'] if row['status'] == 'ok']
        self.page.route('**/data/meta.json*', serve_meta)
        self.page.route('**/data/health.json*', lambda route: route.fulfill(json=snapshot))
        self.open()
        entry = self.page.locator('#healthEntry')
        self.assertIn('时间未知', entry.inner_text())
        self.assertNotIn('全部健康', entry.get_attribute('aria-label'))
        entry.click()
        self.page.locator('#healthStamp').get_by_text('数据时间未知').wait_for(timeout=2500)
        self.assertNotIn('全部正常', self.page.locator('#healthView').inner_text())

    def test_health_bad_built_at_does_not_break_boot_or_claim_healthy(self):
        # 坏对象会让 new Date() 抛错；缺时区的字符串不能当作新鲜。
        for built_at in ({'toString': None}, '2026-11-15T10:00:00'):
            with self.subTest(built_at=built_at):
                meta = json.loads((self.health_out / 'data/meta.json').read_text())
                meta['built_at'] = built_at
                meta['health_summary'] = {'total': 1, 'issues': 0}
                self.page.route('**/data/meta.json*', (lambda body: lambda route: route.fulfill(json=body))(meta))
                self.open()
                self.assertTrue(self.page.locator('#channelRoot > .ch-sec').count())
                entry = self.page.locator('#healthEntry')
                self.assertIn('时间未知', entry.inner_text())
                self.assertNotIn('全部健康', entry.get_attribute('aria-label') or '')
                self.assertEqual(self.page.locator('#refreshed').inner_text(), '刷新时间未知')

    def test_health_keeps_valid_rows_when_source_and_account_fields_are_damaged(self):
        snapshot = json.loads((self.health_out / 'data/health.json').read_text())
        platform = next(row for row in snapshot['sources'] if row.get('accounts'))
        platform['accounts'].append({'name': '损坏账号', 'status': 'ok', 'reason': {'toString': None}})
        snapshot['sources'].append({'name': '损坏来源', 'status': 'ok', 'group': 1, 'reason': {'toString': None}})
        self.page.route('**/data/health.json*', lambda route: route.fulfill(json=snapshot))
        self.open('#/health')
        dialog = self.page.locator('#healthView')
        dialog.get_by_text('部分数据缺损。', exact=True).wait_for(timeout=2500)
        self.assertEqual(dialog.get_by_text('部分数据缺损。', exact=True).count(), 1)
        self.assertIn(platform['name'], dialog.locator('.health-name').all_text_contents())
        self.assertIn(platform['accounts'][0]['name'], dialog.locator('.health-account-name').all_text_contents())
        self.assertNotIn('损坏来源', dialog.locator('.health-name').all_text_contents())
        self.assertNotIn('损坏账号', dialog.locator('.health-account-name').all_text_contents())

    def test_health_diagnostics_link_is_lazy_and_handles_fetch_failure(self):
        requested = []
        self.page.on('request', lambda request: requested.append(request.url))
        self.open()
        self.assertFalse(any('/data/health.json' in url for url in requested))
        self.page.route('**/data/health.json*', lambda route: route.fulfill(status=404))
        self.page.locator('#channelRoot').evaluate('el => el.scrollTop = 240')
        self.page.wait_for_selector('#top.channel-compact')
        title = self.page.locator('#chBtn').bounding_box()
        cdp = self.context.new_cdp_session(self.page)
        cdp.send('Input.dispatchTouchEvent', {'type': 'touchStart', 'touchPoints': [
            {'x': title['x'] + title['width'] / 2, 'y': title['y'] + title['height'] / 2}]})
        link = self.page.get_by_role('link', name='来源健康')
        self.page.wait_for_timeout(2000)
        link.wait_for()
        cdp.send('Input.dispatchTouchEvent', {'type': 'touchEnd', 'touchPoints': []})
        button = self.page.locator('#chBtn')
        button.dispatch_event('click', {'detail': 1})
        self.assertEqual(button.get_attribute('aria-expanded'), 'false')
        self.page.wait_for_timeout(250)
        button.tap()
        self.assertEqual(button.get_attribute('aria-expanded'), 'true')
        self.page.keyboard.press('Escape')
        self.assertEqual(button.get_attribute('aria-expanded'), 'false')
        link.click()
        self.page.get_by_text('健康数据暂时加载不出来。').wait_for()
        self.assertEqual(urlsplit(self.page.url).fragment, '/health')
        self.assertEqual(self.page.locator('meta[name="robots"]').get_attribute('content'), 'noindex,nofollow')


    def test_channel_title_switcher_and_navigation(self):
        self.open()
        # 顶栏只有「频道名 + 下拉」，没有 logo、没有日期；刷新时间收进下拉
        self.assertEqual(self.page.get_by_role('heading', name='时事', exact=True).count(), 1)
        self.assertEqual(self.page.locator('#top, #channelRoot').get_by_text('时事', exact=True).count(), 1)
        self.assertEqual(self.page.locator('.ch-sec[data-ch=current] .desc').inner_text(), '国内外正在发生的事 · 70 条')
        self.assertEqual(self.page.locator('#when, .logo, .brand img').count(), 0)
        self.page.locator('#chBtn').click()
        self.assertTrue(self.page.locator('#drop.on').is_visible())
        self.assertEqual(self.page.locator('#dropList [data-drop-ch]').count(), 6)
        # v13 第 7 条（阿欢 22:11）：日期只出现一次——同一个北京日只写时间，跨天才带日期。
        expect = self.page.evaluate("'刷新于 ' + RebangLib.fmtRefreshed('2026-11-15T12:00:00Z', new Date())")
        self.assertIn(expect, ('刷新于 20:00', '刷新于 11月15日 20:00'))
        self.assertEqual(self.page.locator('#refreshed').inner_text(), expect)
        self.page.get_by_role('option', name='环球', exact=False).tap()
        self.assertEqual(self.page.locator('#chName').inner_text(), '环球')
        self.assertEqual(self.page.locator('#top, #channelRoot').get_by_text('环球', exact=True).count(), 1)
        self.assertEqual(self.page.locator('.see-more, [data-see], #moreView').count(), 0, '「查看更多」入口和整页都去掉了')
        self.assertEqual([t.strip() for t in self.page.locator('.tabbar button').all_inner_texts()], ['频道', '博主', '热搜', '收藏'])
        self.assertEqual(self.page.locator('#view-history').count(), 0, '历史页已改为热搜页')
        for mount in ('#view-hot', '#view-favorites', '#search-panel'):
            self.assertEqual(self.page.locator(mount).count(), 1)

    def test_channel_title_shrinks_on_scroll_and_remains_interactive(self):
        self.open()
        title = self.page.locator('#chName')
        from playwright.sync_api import expect

        expect(title).to_have_css('font-size', '30px')
        root = self.page.locator('#channelRoot')
        root.evaluate('el => el.scrollTop = 240')
        expect(title).to_have_css('font-size', '20px')
        self.assertEqual(self.page.locator('#top, #channelRoot').get_by_text('时事', exact=True).count(), 1)
        self.page.locator('#chBtn').tap()
        self.assertEqual(self.page.locator('#chBtn').get_attribute('aria-expanded'), 'true')
        self.page.keyboard.press('Escape')
        self.assertEqual(self.page.locator('#chBtn').get_attribute('aria-expanded'), 'false')
        root.evaluate('el => el.scrollTop = 0')
        expect(title).to_have_css('font-size', '30px')

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

    def test_a2_cover_click_opens_article_and_summary_visible(self):
        self.open()
        row = self.page.locator('.ch-sec[data-ch=current] .feed-row.cover').first
        row.wait_for()
        box = row.locator('.thumb').bounding_box()
        self.assertLess(box['y'], row.locator('h3').bounding_box()['y'], 'A2：大图在标题上方')
        rid = row.get_attribute('data-id')
        sum_el = row.locator('.sum')
        self.assertEqual(sum_el.count(), 1, '有图的行照样渲染摘要')
        self.assertTrue(sum_el.is_visible(), '有图也显示摘要')
        row.locator('.thumb img').click()
        self.page.locator('#articleBody').wait_for()
        self.assertFalse(self.page.evaluate('!!document.querySelector("#zoomStage") && getComputedStyle(document.querySelector("#zoomStage")).display !== "none" && document.querySelector("#zoomStage").offsetHeight > 0'), '点列表大图进详情，不直接放大')

    def inject_rows(self, items, width=390):
        self.page.set_viewport_size({'width': width, 'height': 844})
        self.page.evaluate("""items => { const list = document.querySelector('.ch-sec[data-ch=current] .feed-list');
          list.insertAdjacentHTML('afterbegin', '<div class="chunk" id="a2probe">' + items.map(RebangLib.feedRowHTML).join('') + '</div>'); }""", items)
        self.page.wait_for_timeout(100)

    def test_a2_layout_meta_right_no_clip_no_upscale_no_overflow(self):
        self.open()
        base = {'kind': 'news', 'channel': 'current', 'source_id': 'tnews365', 'source_name': '竹新社', 'url': 'https://t.me/x/1',
                'published_at': '2026-11-15T11:00:00Z', 'lang': 'zh', 'translated': False}
        self.inject_rows([
            dict(base, id='a2:cover', title='通报', summary='短。', image={'url': 'https://img.test/c.png', 'width': 800, 'height': 450}),
            dict(base, id='a2:small', title='很长的一个标题用来占位很长的一个标题', summary='短。', image={'url': 'https://img.test/s.png', 'width': 32, 'height': 32}),
            dict(base, id='a2:long', title='长串', summary='校验码 ' + 'a' * 64, image=None),
        ], width=320)
        cover = self.page.locator('#a2probe .feed-row[data-id="a2:cover"]')
        row_box = cover.bounding_box()
        when = cover.locator('.f-meta .when').bounding_box()
        self.assertGreater(when['x'] + when['width'], row_box['x'] + row_box['width'] - 24, '大图短文行的时间也靠右')
        small = self.page.locator('#a2probe .feed-row[data-id="a2:small"]')
        small.evaluate("e => e.classList.add('read')")
        meta = small.locator('.f-meta')
        clipped = meta.evaluate("""m => { const r = m.getBoundingClientRect(); const w = m.querySelector('.when').getBoundingClientRect();
          return m.scrollWidth > m.clientWidth + 1 || w.right > r.right + 1; }""")
        self.assertFalse(clipped, '320px 屏上小图行的时间和「已读」不被裁掉')
        self.assertEqual(small.locator('.thumb img').evaluate('i => getComputedStyle(i).objectFit'), 'scale-down', '已知偏小的图不放大')
        self.inject_rows([dict(base, id='a2:smallvid', title='小视频', summary='短。', image={'url': 'https://img.test/v.png', 'width': 64, 'height': 64}, tg={'media': [{'type': 'video'}]})], width=320)
        self.assertEqual(self.page.locator('#a2probe .feed-row[data-id="a2:smallvid"] .thumb img').first.evaluate('i => getComputedStyle(i).objectFit'), 'scale-down', '偏小的视频封面也不放大')
        long_row = self.page.locator('#a2probe .feed-row[data-id="a2:long"]')
        sum_box = long_row.locator('.sum').bounding_box()
        self.assertLessEqual(sum_box['x'] + sum_box['width'], long_row.bounding_box()['x'] + long_row.bounding_box()['width'] + 1)
        self.assertLessEqual(long_row.locator('.sum').evaluate('e => e.scrollWidth - e.clientWidth'), 1, '连续长串换行，不溢出')

    def test_a2_rss_cover_with_text_blocks_still_zoomable_in_article(self):
        """列表点大图进详情；正文 blocks 里没有图时，详情要补上封面，否则就再也放大不了。"""
        def patch(route):
            url = urlsplit(route.request.url)
            if url.netloc == 'rebang.test' and url.path.endswith('/channel/current/page-1.json'):
                data = json.loads((self.out / unquote(url.path).lstrip('/')).read_text(encoding='utf-8'))
                first = data['items'][0]
                first.pop('tg', None); first.pop('quote', None)
                first['image'] = {'url': 'https://img.test/rss.png', 'width': 400, 'height': 200}
                first['blocks'] = [{'type': 'p', 'text': '只有文字的正文。'}]
                return route.fulfill(status=200, body=json.dumps(data), content_type='application/json')
            return self.page_route(route)
        self.page.unroute('**/*')
        self.page.route('**/*', patch)
        self.open()
        row = self.page.locator('.ch-sec[data-ch=current] .feed-row.cover').first
        row.locator('.thumb img').click()
        self.page.locator('#articleBody .art-blocks').wait_for()
        self.assertEqual(self.page.locator('#articleBody img.cover[data-zoom="https://img.test/rss.png"]').count(), 1, '详情里有封面可放大')

    def test_a2_article_cover_kept_unless_same_image_in_blocks(self):
        """正文图没存下来、或正文里是别的图：详情照样放列表大图；正文里已有同一张图才不重复。"""
        cases = [([{'type': 'img', 'missing': True}, {'type': 'p', 'text': '文字'}], 1),
                 ([{'type': 'img', 'src': 'https://img.test/other.png'}, {'type': 'p', 'text': '文字'}], 1),
                 ([{'type': 'img', 'src': 'https://img.test/rss.png'}, {'type': 'p', 'text': '文字'}], 0)]
        for blocks, want in cases:
            with self.subTest(blocks=blocks[0]):
                def make(blocks):
                  def patch(route):
                    url = urlsplit(route.request.url)
                    if url.netloc == 'rebang.test' and url.path.endswith('/channel/current/page-1.json'):
                        data = json.loads((self.out / unquote(url.path).lstrip('/')).read_text(encoding='utf-8'))
                        first = data['items'][0]
                        first.pop('tg', None); first.pop('quote', None)
                        first['image'] = {'url': 'https://img.test/rss.png', 'width': 400, 'height': 200}
                        first['blocks'] = blocks
                        return route.fulfill(status=200, body=json.dumps(data), content_type='application/json')
                    return self.page_route(route)
                  return patch
                self.page.unroute('**/*')
                self.page.route('**/*', make(blocks))
                self.open()
                self.page.locator('.ch-sec[data-ch=current] .feed-row.cover').first.locator('.thumb img').click()
                self.page.locator('#articleBody .art-blocks').wait_for()
                self.assertEqual(self.page.locator('#articleBody img.cover').count(), want)
                self.page.goto('about:blank')

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
        for slug, name in (('world', '环球'), ('finance', '财经'), ('current', '时事')):
            self.page.evaluate(f"""(() => {{ const r = document.querySelector('#channelRoot'), s = r.querySelector('.ch-sec[data-ch="{slug}"]');
              r.scrollTop += s.getBoundingClientRect().top - r.getBoundingClientRect().top + 40; }})()""")
            self.page.wait_for_timeout(150)
            self.assertEqual(self.page.locator('#channelRoot').get_attribute('data-cur'), slug)
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
        self.long_press(tweet.locator('.b-text'))
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

    def test_web_news_body_does_not_default_to_original_when_translation_is_pending(self):
        self.open('#/item/bbc-world%3A1')
        body = self.page.locator('#articleBody')
        body.locator('.art-pending').wait_for()
        self.assertIn('合成译文摘要', body.inner_text())
        original = 'This is the original English news article.'
        self.assertNotIn(original, body.inner_text())
        body.get_by_role('button', name='看原文').click()
        self.assertIn(original, body.inner_text())

    def test_stale_favorite_does_not_mask_ready_search_snapshot(self):
        archived_id = 'bbc-world:archived-1'
        stale_only_id = 'bbc-world:stale-only-1'
        search_payload = {
            'schema': 'rebang.search-index/1',
            'timezone': 'Asia/Shanghai',
            'generated_at': NOW.isoformat(),
            'entries': [{
                'id': archived_id,
                'kind': 'news',
                'channel': 'world',
                'source_id': 'bbc-world',
                'source_name': 'BBC World',
                'title': 'Archived English title',
                'summary': 'Archived English summary',
                'published_at': NOW.isoformat(),
                'lang': 'en',
                'translated': True,
                'display_title': '归档补回的中文标题',
                'display_summary': '归档补回的中文摘要',
                'translation_title': '归档补回的中文标题',
                'translation_summary': '归档补回的中文摘要',
                'summary_source': 'Archived English summary',
                'original_title': 'Archived English title',
                'original_summary': 'Archived English summary',
                'image': None,
            }],
        }
        self.page.route('**/data/search-index.json*', lambda route: route.fulfill(json=search_payload))
        self.open('')
        self.page.evaluate('''([archivedId, staleOnlyId]) => {
            localStorage.setItem('rebang.favorites.v1', JSON.stringify([
                {
                    id: archivedId, kind: 'news', channel: 'world', source_id: 'bbc-world',
                    source_name: 'BBC World', title: 'Archived English title',
                    summary: 'Archived English summary', lang: 'en', translated: false,
                    saved_at: '2026-11-15T00:00:00Z'
                },
                {
                    id: staleOnlyId, kind: 'news', channel: 'world', source_id: 'bbc-world',
                    source_name: 'BBC World', title: 'Untranslated only title',
                    summary: 'Untranslated only summary', lang: 'en', translated: false,
                    saved_at: '2026-11-15T00:00:00Z'
                }
            ]));
        }''', [archived_id, stale_only_id])
        # Trigger search-index load so mounted.search.getItem(id) has the archived entry.
        self.page.locator('#btnSearch').click()
        self.page.locator('#search-panel input').fill('归档补回')
        self.page.locator('#search-panel [data-search-hit]').first.wait_for()
        self.page.locator('#search-panel [data-search-close]').click()
        # Open via favorite click (passes stale English bookmark ref) -> must resolve to ready search snapshot.
        self.page.locator('.tabbar [data-view=favorites]').click()
        self.page.locator(f'[data-favorites-list] [data-item-id="{archived_id}"]').click()
        self.page.locator('#articleView.on').wait_for()
        self.assertEqual(self.page.locator('#articleTitle').inner_text(), '归档补回的中文标题')
        self.assertIn('归档补回的中文摘要', self.page.locator('#articleBody').inner_text())
        self.page.locator('#btnBack').click()
        self.page.locator('#articleView.on').wait_for(state='hidden')
        # Stale-only bookmark with no ready snapshot still refuses to display English.
        self.page.locator(f'[data-favorites-list] [data-item-id="{stale_only_id}"]').click()
        self.page.wait_for_function("document.querySelector('#toast').textContent.includes('中文译文尚未就绪')")
        self.assertFalse(self.page.locator('#articleView').evaluate('e => e.classList.contains("on")'))

    def built_at(self):
        return json.loads((self.out / 'data' / 'meta.json').read_text())['built_at']

    @staticmethod
    def server_order(rows):
        """与 rebang.site.builder.merge_items 相同：先按 id 升序，再稳定地按发布时间倒序。"""
        return sorted(sorted(rows, key=lambda r: str(r['id'])), key=site._sort_key, reverse=True)

    def blogger_fixture(self, x_count=34, weibo_count=34, same_time=False, built_at=None):
        """发布格式的合成分页（发布端排序、site.paginate 切页），两个平台同名同 handle，含跨页重复。"""
        built_at = built_at or self.built_at()
        paths = {}
        platforms, preview, ids = [], [], {}
        for platform, name, count, offset in [('x', 'X', x_count, 0), ('weibo', '微博', weibo_count, 1)]:
            rows = []
            for n in range(count):
                handle = 'other' if n == 4 else 'shared'
                post_id = f'{platform}:{n:02}'
                rows.append(dict(id=post_id, kind='post', title='', summary=f'{name} 合成帖子 {n}',
                                 published_at=(NOW if same_time else NOW - timedelta(minutes=2*n + offset if n != 2 else 4)).isoformat(),
                                 blogger=dict(platform=platform, handle=handle, display_name=handle,
                                              avatar='https://img.test/avatar.png' if n == 0 else None)))
            if rows:
                rows[0].update(lang='en', translated=True, body='Original text',
                               translation=dict(summary='合成译文', body='合成译文', label='机器翻译'))
                rows[0]['blogger']['quote'] = dict(display_name='引用作者', text='合成引用')
            accounts = [dict(key=f'h-{handle}', handle=handle, name=handle,
                             total=sum(r['blogger']['handle'] == handle for r in rows)) for handle in ['shared', 'other']]
            platforms.append(dict(id=platform, name=name, icon=f'icons/{platform}.svg', count=count,
                                  connected=bool(count), accounts=accounts))
            preview.extend(rows[:1])
            for key, selected in [('all', rows), *[(a['key'], [r for r in rows if r['blogger']['handle'] == a['handle']]) for a in accounts]]:
                pages = site.paginate(self.server_order(selected))
                if len(pages) > 1:
                    pages[1]['items'].insert(0, pages[0]['items'][-1])
                for page in pages:
                    path = f'blogger/{platform}/{key}/page-{page["page"]}.json'
                    paths[path] = dict(page, schema='rebang.page/1', platform=platform, key=key, built_at=built_at)
                    if key == 'all':
                        ids.update((it['id'], path) for it in page['items'])
        # 同一合成发布内，索引、每个分页与 meta 使用同一版本；合流次序来自建站端。
        meta = json.loads((self.out / 'data/meta.json').read_text())
        revision = f'fixture-{x_count}-{weibo_count}-{same_time}-{built_at}'
        all_rows = {row['id']: row for path, page in paths.items() if '/all/' in path for row in page['items']}
        for rank, row in enumerate(self.server_order(all_rows.values())):
            row['feed_order'] = rank
        for page in paths.values():
            page['blogger_revision'] = revision
        paths['meta.json'] = dict(meta, built_at=built_at, blogger_revision=revision)
        paths['bloggers.json'] = dict(platforms=platforms, items=preview, built_at=built_at, blogger_revision=revision)
        paths['id-index.json'] = ids
        return paths

    def use_blogger_fixture(self, data, intercept=None):
        def serve(route):
            key = urlsplit(route.request.url).path.removeprefix('/data/')
            if intercept and intercept(route, key):
                return
            if key in data:
                route.fulfill(json=data[key])
            else:
                route.fallback()
        self.page.route('https://rebang.test/data/**', serve)

    def open_blogger(self):
        self.open()
        self.page.locator('.tabbar [data-view=blogger]').click()

    def blogger_ids(self):
        return self.page.locator('#bloggerList .tweet').evaluate_all('es => es.map(e => e.dataset.id)')

    def test_blogger_all_merges_pages_in_stable_order_without_repeats(self):
        data = self.blogger_fixture()
        self.use_blogger_fixture(data)
        self.open_blogger()
        self.page.locator('#bloggerList .tweet').first.wait_for()
        self.assertEqual(self.page.locator('#platChips .on').get_attribute('data-plat'), 'all')
        # x:02 与 weibo:02 同一时刻：按发布端规则 ID 升序
        self.assertEqual(self.blogger_ids()[:8], ['x:00', 'weibo:00', 'x:01', 'weibo:01', 'weibo:02', 'x:02', 'x:03', 'weibo:03'])
        self.assertTrue(self.scroll_to_end('#view-blogger .sub'))
        ordered = [r['id'] for r in self.server_order(
            [r for k, v in data.items() if k.endswith('/all/page-1.json') or k.endswith('/all/page-2.json') for r in v['items']])]
        ordered = list(dict.fromkeys(ordered))
        self.assertEqual(self.blogger_ids(), ordered)
        self.page.locator('#platChips [data-plat=weibo]').click()
        self.page.locator('#bloggerList .tweet').first.wait_for()
        self.assertTrue(self.scroll_to_end('#view-blogger .sub'))
        self.assertEqual(self.blogger_ids(), [x for x in ordered if x.startswith('weibo:')])

    def test_blogger_profile_article_navigation_and_390px_themes(self):
        self.use_blogger_fixture(self.blogger_fixture())
        self.open_blogger()
        first = self.page.locator('#bloggerList .tweet').first
        first.wait_for()
        for theme, bg in [('light', 'rgb(255, 255, 255)'), ('dark', 'rgb(0, 0, 0)')]:
            self.page.emulate_media(color_scheme=theme)
            self.assertEqual(self.page.locator('#platChips').evaluate('e => getComputedStyle(e).backgroundColor'), bg)
            self.assertEqual(self.page.locator('#view-blogger .sub').evaluate('e => [e.clientWidth, e.scrollWidth]'), [390, 390])
            self.assertLess(first.locator('.bl-avatar').bounding_box()['x'], first.locator('.b-main').bounding_box()['x'])
            self.assertTrue(self.page.locator('.tabbar').is_visible())
        translated = first.locator('[data-orig]')
        self.assertEqual(translated.inner_text(), '看原文')
        translated.tap()
        self.assertEqual(translated.get_attribute('aria-expanded'), 'true')
        self.assertTrue(first.get_by_text('Original text', exact=True).is_visible())
        self.assertIn('合成引用', first.inner_text())
        first.locator('[data-bl-menu]').tap()
        self.assertTrue(self.page.locator('#cardMenu.on').is_visible())
        self.assertEqual(urlsplit(self.page.url).fragment, '')
        self.page.locator('#cardMenu [data-menu=cancel]').tap()
        first.locator('.bl-face').tap()
        self.page.locator('#blProfile').get_by_text('X', exact=True).wait_for()
        self.page.locator('#bloggerList .tweet').first.wait_for()
        self.assertTrue(all(x.startswith('x:') for x in self.blogger_ids()))
        self.assertNotIn('x:04', self.blogger_ids())
        self.page.locator('[data-bl-back]').click()
        self.page.locator('#platChips [data-plat=weibo]').click()
        self.page.locator('#bloggerList .tweet[data-id="weibo:00"] .bl-name').tap()
        self.page.locator('#blProfile').get_by_text('微博', exact=True).wait_for()
        self.assertTrue(self.scroll_to_end('#view-blogger .sub'))
        self.assertEqual(self.blogger_ids(), [f'weibo:{n:02}' for n in range(34) if n != 4])
        scroller = self.page.locator('#view-blogger .sub')
        target = self.page.locator('#bloggerList .tweet[data-id="weibo:31"] [data-bl-item]')
        target.scroll_into_view_if_needed()
        before = scroller.evaluate('e => e.scrollTop')
        self.assertGreater(before, 0)
        target.tap()
        self.page.locator('#articleView.on').wait_for()
        self.assertEqual(unquote(urlsplit(self.page.url).fragment), '/item/weibo:31')
        self.page.go_back()
        self.page.locator('#articleView.on').wait_for(state='hidden')
        self.page.wait_for_function('(y) => document.querySelector("#view-blogger .sub").scrollTop === y', arg=before)
        self.assertTrue(self.page.locator('#blProfile').get_by_text('微博', exact=True).is_visible())
        self.assertEqual(self.page.locator('#platChips .on').get_attribute('data-plat'), 'weibo')
        self.page.locator('[data-bl-back]').click()
        self.assertEqual(self.page.locator('#platChips .on').get_attribute('data-plat'), 'weibo')
        self.open('#/item/weibo%3A31')
        self.page.locator('#articleView.on').wait_for()
        self.assertIn('微博 合成帖子 31', self.page.locator('#articleBody').inner_text())

    def test_blogger_pending_request_cannot_replace_another_filter(self):
        data = self.blogger_fixture()
        pending = []

        def delay(route, key):
            if key == 'blogger/x/all/page-1.json' and not pending:
                pending.append(route)
                return True
            return False

        self.use_blogger_fixture(data, delay)
        with self.page.expect_request('**/blogger/x/all/page-1.json'):
            self.open_blogger()
        self.page.locator('#platChips [data-plat=weibo]').click()
        self.page.locator('#bloggerList .tweet').first.wait_for()
        with self.page.expect_response('**/blogger/x/all/page-1.json'):
            pending[0].fulfill(json=data['blogger/x/all/page-1.json'])
        self.assertTrue(self.scroll_to_end('#view-blogger .sub'))
        self.assertEqual(self.blogger_ids(), [f'weibo:{n:02}' for n in range(34)])
        self.page.locator('#platChips [data-plat=all]').click()
        self.page.locator('#bloggerList .tweet[data-id="x:00"]').wait_for()

    def test_blogger_old_page_cannot_reappear_after_refresh_and_missing_x(self):
        data = self.blogger_fixture()
        pending = []

        def delay(route, key):
            if key == 'blogger/x/all/page-1.json' and not pending:
                pending.append(route)
                return True
            return False

        self.use_blogger_fixture(data, delay)
        with self.page.expect_request('**/blogger/x/all/page-1.json'):
            self.open_blogger()
        old = data['blogger/x/all/page-1.json']
        newer = (NOW + timedelta(days=1)).isoformat()
        data.update(self.blogger_fixture(x_count=0, weibo_count=3, built_at=newer))
        self.page.locator('#btnRefresh').click()
        self.page.locator('#bloggerList [data-end=all]').wait_for()
        with self.page.expect_response('**/blogger/x/all/page-1.json'):
            pending[0].fulfill(json=old)
        self.page.wait_for_function("document.querySelector('#toast').textContent.includes('已更新')")
        self.assertEqual(self.blogger_ids(), ['weibo:00', 'weibo:01', 'weibo:02'])
        self.page.locator('#platChips [data-plat=x]').click()
        self.assertTrue(self.page.locator('#bloggerList .empty-plat').is_visible())
        self.assertEqual(self.blogger_ids(), [])
        self.page.locator('#platChips [data-plat=all]').click()
        self.assertEqual(self.blogger_ids(), ['weibo:00', 'weibo:01', 'weibo:02'])

    def test_blogger_failed_page_retries_without_skipping_or_repeating_rows(self):
        data = self.blogger_fixture()
        failures = []

        def fail_once(route, key):
            if key == 'blogger/x/all/page-2.json' and not failures:
                failures.append(key)
                route.fulfill(status=503, body='unavailable')
                return True
            return False

        self.use_blogger_fixture(data, fail_once)
        self.open_blogger()
        scroller = self.page.locator('#view-blogger .sub')
        self.page.locator('#bloggerList .tweet').first.wait_for()
        scroller.evaluate('e => e.scrollTop = e.scrollHeight')
        retry = self.page.locator('#blFoot [data-bl-retry]')
        retry.wait_for()
        before = self.blogger_ids()
        self.assertTrue(before)
        retry.click()
        self.assertTrue(self.scroll_to_end('#view-blogger .sub'))
        after = self.blogger_ids()
        self.assertEqual(after[:len(before)], before)
        self.assertEqual(after[4:6], ['weibo:02', 'x:02'])
        self.assertEqual(sorted(after), sorted(f'{platform}:{n:02}' for n in range(34) for platform in ('x', 'weibo')))
        self.assertEqual(len(after), len(set(after)))

    def test_blogger_same_time_posts_follow_build_order_across_pages(self):
        data = self.blogger_fixture(x_count=31, weibo_count=0, same_time=True)
        for page in (1, 2):   # 只看发布端真实切页，不加人为的跨页重复
            data[f'blogger/x/all/page-{page}.json']['items'] = [
                r for r in data[f'blogger/x/all/page-{page}.json']['items'] if page == 1 or r['id'] == 'x:30']
        self.use_blogger_fixture(data)
        self.open_blogger()
        self.page.locator('#bloggerList .tweet').first.wait_for()
        self.assertTrue(self.scroll_to_end('#view-blogger .sub'))
        expected = [r['id'] for p in (1, 2) for r in data[f'blogger/x/all/page-{p}.json']['items']]
        self.assertEqual(expected[:2], ['x:00', 'x:01'])
        self.assertEqual(self.blogger_ids(), expected)

    def test_blogger_page_from_newer_build_stops_instead_of_mixing(self):
        data = self.blogger_fixture()
        self.use_blogger_fixture(data)
        self.open_blogger()
        self.page.locator('#bloggerList .tweet').first.wait_for()
        first = self.blogger_ids()
        newer = (NOW + timedelta(hours=1)).isoformat()
        # 读完第一页后网站换版：新版在队首插了一条，后面的页整体后移
        new_data = self.blogger_fixture(built_at=newer)
        for key, page in new_data.items():
            if key.startswith('blogger/') and key.endswith('page-2.json'):
                page['items'].insert(0, dict(page['items'][0], id=page['items'][0]['id'] + '-new'))
        data.update({k: v for k, v in new_data.items() if k.startswith('blogger/')})
        self.page.locator('#view-blogger .sub').evaluate('e => e.scrollTop = e.scrollHeight')
        prompt = self.page.locator('#blFoot [data-bl-refresh]')
        prompt.wait_for()
        old_first_pages = {r['id'] for k, v in self.blogger_fixture().items()
                           if k.startswith('blogger/') and '/all/page-1.json' in k for r in v['items']}
        shown = self.blogger_ids()
        self.assertEqual(shown[:len(first)], first)
        self.assertTrue(set(shown) <= old_first_pages, '新版分页不混进旧版列表')
        data.update(new_data)
        prompt.click()
        self.page.wait_for_function("document.querySelector('#toast').textContent.includes('已更新')")
        self.page.locator('#bloggerList .tweet').first.wait_for()
        self.assertTrue(self.scroll_to_end('#view-blogger .sub'))
        ids = self.blogger_ids()
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(len(ids), 68 + 2)

    def test_blogger_open_before_first_meta_waits_for_snapshot(self):
        data, held = self.blogger_fixture(0, 2), []

        def hold(route, key):
            if key == 'meta.json' and not held:
                held.append(route)
                return True
            return False

        self.use_blogger_fixture(data, hold)
        with self.page.expect_request('**/data/meta.json'):
            self.page.goto('https://rebang.test/index.html', wait_until='domcontentloaded')
        self.page.locator('.tabbar [data-view=blogger]').click()
        held[0].fulfill(json=data['meta.json'])
        self.page.wait_for_selector('#app:not([aria-busy])')
        self.page.locator('#blFoot [data-end=all], #blFoot .load-err').wait_for(timeout=3000)
        self.assertEqual(self.blogger_ids(), ['weibo:00', 'weibo:01'])

    def test_blogger_pull_during_boot_does_not_leave_refreshing(self):
        meta = json.loads((self.out / 'data/meta.json').read_text())
        held = []
        self.page.route('**/data/meta.json*', lambda route: held.append(route))
        ptr = self.page.locator('#ptr')
        for first_status in (200, 503):
            with self.subTest(first_status=first_status):
                held.clear()
                with self.page.expect_request('**/data/meta.json'):
                    self.page.goto('https://rebang.test/index.html', wait_until='domcontentloaded')
                self.page.locator('.tabbar [data-view=blogger]').tap()
                self.swipe(160, 200, 160, 420)
                self.assertEqual(len(held), 1, '首屏未就绪，不发第二个请求')
                shown_while_busy = ptr.is_visible()
                held[0].fulfill(status=first_status, json=meta)
                self.page.wait_for_selector('#app:not([aria-busy])')
                self.assertTrue(ptr.is_hidden(), f'首屏结束后仍显示：{ptr.text_content()}')
                self.assertFalse(shown_while_busy, '没开始刷新，不应显示正在刷新')

                # 无论首读成功还是失败，下一次真正的下拉都应只刷新一次，结束后收起提示。
                with self.page.expect_request('**/data/meta.json?*', timeout=3000):
                    self.swipe(160, 200, 160, 420)
                self.assertEqual(len(held), 2)
                self.assertTrue(self.page.locator('#ptr.spin').is_visible())
                held[1].fulfill(json=meta)
                ptr.wait_for(state='hidden', timeout=3000)
                self.page.locator('#bloggerList .tweet').first.wait_for(timeout=3000)

    def test_blogger_old_empty_index_cannot_hide_new_platform(self):
        # 同一秒重新建站也不能把旧索引的「0 条」当成新版本已结束。
        data = self.blogger_fixture(0, 2)
        current = data['bloggers.json']
        data['bloggers.json'] = self.blogger_fixture(0, 0)['bloggers.json']
        self.use_blogger_fixture(data)
        self.open_blogger()
        foot = self.page.locator('#blFoot')
        foot.locator('.empty-plat, .load-err').wait_for()
        self.assertEqual(foot.locator('.empty-plat').count(), 0, '错版索引不是空平台')
        self.assertEqual(self.page.locator('#platChips [data-plat]').count(), 0)
        data['bloggers.json'] = current
        foot.locator('[data-bl-refresh]').click()
        foot.locator('[data-end=all]').wait_for()
        self.assertEqual(self.blogger_ids(), ['weibo:00', 'weibo:01'])
        self.page.locator('#bloggerList .bl-name').first.click()
        foot.locator('[data-end=all]').wait_for()
        self.assertEqual(self.blogger_ids(), ['weibo:00', 'weibo:01'])

    def test_blogger_deep_link_does_not_remember_stale_index_or_page(self):
        for path in ('bloggers.json', 'blogger/x/all/page-1.json'):
            with self.subTest(path=path):
                data = self.blogger_fixture(1, 0)
                data['id-index.json'] = {'x:00': path}
                data[path] = dict(data[path], blogger_revision='stale')
                self.use_blogger_fixture(data)
                # 直接打开新文档，不沿用上一子用例已经载入的 id-index。
                self.page.goto('about:blank')
                with self.page.expect_request(f'**/data/{path}*'):
                    self.open('#/item/x%3A00')
                self.page.wait_for_function("document.querySelector('#articleView').classList.contains('on') || document.querySelector('#toast').textContent.includes('不在')")
                self.assertEqual(self.page.locator('#articleView.on').count(), 0, path)
                self.assertEqual(urlsplit(self.page.url).fragment, '')

    def test_blogger_older_refresh_response_cannot_reauthorize_old_page(self):
        old = self.blogger_fixture(39, 0)
        current = self.blogger_fixture(40, 0, built_at=(NOW + timedelta(hours=1)).isoformat())
        held, requests = [], []
        data = dict(old)

        def hold_first_refresh(route, key):
            if key == 'meta.json' and requests and not held:
                held.append(route)
                return True
            return False

        self.use_blogger_fixture(data, hold_first_refresh)
        self.open_blogger()
        self.page.locator('#bloggerList .tweet').first.wait_for()
        requests.append(True)
        with self.page.expect_request('**/data/meta.json*'):
            self.page.locator('#btnRefresh').click()
        data.update(current)
        self.page.locator('#btnRefresh').click()
        self.page.wait_for_function("document.querySelector('#toast').textContent.includes('有新内容')")
        self.page.locator('#bloggerList .tweet').first.wait_for()
        with self.page.expect_response('**/data/meta.json*'):
            held[0].fulfill(json=old['meta.json'])
        self.page.wait_for_load_state('networkidle')
        # B 首页后端返回了 A 末页。若旧刷新覆盖 meta，这一页就会错误地被接受。
        path = 'blogger/x/all/page-2.json'
        data[path] = old[path]
        self.page.locator('#view-blogger .sub').evaluate('e => e.scrollTop = e.scrollHeight')
        self.page.locator('#blFoot .load-err, #blFoot [data-end=all]').wait_for()
        self.assertNotIn('x:38', self.blogger_ids(), 'B 首页后不得出现 A 的末页')
        self.assertTrue(self.page.locator('#blFoot [data-bl-refresh]').is_visible())
        data[path] = current[path]
        self.page.locator('#blFoot [data-bl-refresh]').click()
        self.assertTrue(self.scroll_to_end('#view-blogger .sub'))
        self.assertEqual(self.blogger_ids(), [f'x:{n:02}' for n in range(40)])

    def test_blogger_vanished_page_recovers_from_footer(self):
        data = self.blogger_fixture(39, 0)
        current = self.blogger_fixture(0, 3, built_at=(NOW + timedelta(hours=1)).isoformat())
        missing = []

        def switch_at_last_page(route, key):
            if key == 'blogger/x/all/page-2.json':
                missing.append(key)
                data.clear()
                data.update(current)
                route.fulfill(status=404, body='gone')
                return True
            return False

        self.use_blogger_fixture(data, switch_at_last_page)
        self.open_blogger()
        self.page.locator('#bloggerList .tweet').first.wait_for()
        self.page.locator('#view-blogger .sub').evaluate('e => e.scrollTop = e.scrollHeight')
        foot = self.page.locator('#blFoot')
        foot.locator('.load-err').wait_for()
        self.assertEqual(foot.locator('[data-bl-refresh]').count(), 1, '消失的页不能只有再试一次')
        foot.locator('[data-bl-refresh]').click()
        foot.locator('[data-end=all]').wait_for()
        self.assertEqual(missing, ['blogger/x/all/page-2.json'])
        self.assertEqual(self.blogger_ids(), ['weibo:00', 'weibo:01', 'weibo:02'])

    def test_blogger_submillisecond_order_across_platforms(self):
        data = self.blogger_fixture(1, 1)
        for row in data['bloggers.json']['items']:
            row['published_at'] = ('2026-11-15T10:00:00.000002+08:00' if row['id'] == 'x:00'
                                   else '2026-11-15T02:00:00.000001Z')
        self.use_blogger_fixture(data)
        self.open_blogger()
        self.page.locator('#blFoot [data-end=all]').wait_for()
        self.assertEqual(self.blogger_ids(), ['x:00', 'weibo:00'])

    def test_blogger_filter_change_cancels_slow_article_lookup(self):
        held = []

        def hold(route, key):
            if key == 'id-index.json' and not held:
                held.append(route)
                return True
            return False

        self.use_blogger_fixture({}, hold)
        self.open_blogger()
        self.page.locator('#bloggerList .tweet').first.wait_for()
        with self.page.expect_request('**/data/id-index.json*'):
            self.page.evaluate("location.hash = '#/item/tnews365%3A69'")
        self.page.locator('#platChips [data-plat=weibo]').click()
        self.assertEqual(self.page.locator('#platChips .on').get_attribute('data-plat'), 'weibo')
        held[0].fallback()
        self.page.wait_for_timeout(400)
        self.assertEqual(self.page.locator('#articleView.on').count(), 0, '换了筛选后，慢回来的正文不再打开')
        self.assertEqual(urlsplit(self.page.url).fragment, '')
        self.assertEqual(self.page.locator('#platChips .on').get_attribute('data-plat'), 'weibo')

    def test_blogger_empty_all_has_no_post_page_requests(self):
        data = self.blogger_fixture(x_count=0, weibo_count=0)
        self.use_blogger_fixture(data)
        pages = []
        self.page.on('request', lambda r: pages.append(r.url) if '/data/blogger/' in r.url else None)
        self.open_blogger()
        self.page.locator('#bloggerList .empty-plat').wait_for()
        self.assertEqual(self.blogger_ids(), [])
        self.assertEqual(pages, [])

    def test_blogger_empty_platform_filter_excludes_other_platform_cards(self):
        self.open()
        self.page.locator('.tabbar [data-view=blogger]').click()
        cards = self.page.locator('#bloggerList .tweet')
        cards.first.wait_for()
        self.page.locator('#platChips [data-plat=weibo]').click()
        self.page.locator('#bloggerList .empty-plat').get_by_text('微博', exact=False).wait_for()
        self.assertEqual(cards.count(), 0)

    def test_blogger_name_opens_person_feed_instead_of_article(self):
        self.open()
        self.page.locator('.tabbar [data-view=blogger]').click()
        cards = self.page.locator('#bloggerList .tweet')
        cards.first.wait_for()
        self.page.locator('#bloggerList .tweet[data-id="x-dotey:0"] .bl-name').click()
        self.page.locator('#blProfile:not([hidden])').wait_for()
        self.page.locator('#bloggerList [data-end=all]').wait_for()
        self.assertEqual(urlsplit(self.page.url).fragment, '')
        self.assertEqual(cards.evaluate_all('es => es.map(e => e.dataset.id)'), ['x-dotey:0'])

    def test_blogger_tab_real_empty_states(self):
        self.open()
        self.page.locator('.tabbar [data-view=blogger]').click()
        self.page.wait_for_selector('#bloggerList [data-end=all]')
        self.assertEqual(self.page.locator('#bloggerList .tweet').count(), 2)
        self.page.locator('#platChips [data-plat=weibo]').click()
        self.assertIn('还没有成功抓取过', self.page.locator('#bloggerList .empty-plat').inner_text())
        self.assertEqual(self.page.locator('#platChips .on').get_attribute('data-plat'), 'weibo')
        self.assertEqual(self.page.locator('#platChips [data-plat=zhihu]').count(), 0)

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
        # 博主：选中的 X 平台图标不加红圈
        self.page.locator('.tabbar [data-view=blogger]').click()
        x = self.page.locator('#platChips [data-plat=x]')
        x.click()
        on = x.locator('.plat-ico')
        ring = on.evaluate("e => { const s = getComputedStyle(e); return [s.borderTopWidth, s.borderTopStyle, s.outlineStyle, s.boxShadow]; }")
        self.assertTrue(ring[0] == '0px' or ring[1] == 'none', ring)
        self.assertEqual(ring[2], 'none', ring)
        self.assertNotIn('rgb(2', ring[3].replace('rgba(0, 0, 0', ''), ring)
        self.assertEqual(self.page.locator('#platChips [data-plat=all]').inner_text().strip(), '全部')

    def video_state(self):
        return self.page.evaluate('''() => { const v = document.querySelector('#zoomStage video'); if (!v) return null;
          return {paused: v.paused, muted: v.muted, controls: v.controls, loop: v.loop, poster: v.poster, t: v.currentTime, rs: v.readyState}; }''')

    def test_video_player_mixed_media_swipe_and_error_fallback(self):
        self.open()
        self.page.locator('.tabbar [data-view=blogger]').click()
        card = self.page.locator('#bloggerList .tweet[data-id="x-dotey:0"]')
        card.wait_for()
        # 样页 A：帖内正文下面多格显示全部媒体（最多 4 格），点哪格从哪格开始看，不进正文
        grid = card.locator('.media-grid')
        self.assertEqual(card.locator('.thumb').count(), 0)
        self.assertEqual(grid.locator('.cell').count(), 3)
        self.assertLess(card.locator('.b-text').bounding_box()['y'], grid.bounding_box()['y'], '媒体在正文下面')
        self.assertLessEqual(grid.bounding_box()['width'], 300, '多格紧凑')
        grid.locator('.cell').nth(1).tap()
        self.page.wait_for_selector('#zoomView.on #zoomStage video')
        self.assertEqual(urlsplit(self.page.url).fragment, '', '点媒体不进正文')
        self.assertEqual(self.page.locator('#articleView.on').count(), 0)
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
        bad = self.page.locator('#bloggerList .tweet[data-id="x-simonw:1"] .media-grid .cell.is-vid')
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
