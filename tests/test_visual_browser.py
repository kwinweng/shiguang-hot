"""Production renderer interaction regressions, with offline approved-reference fixtures."""
import json
import mimetypes
from pathlib import Path
import tempfile
import unittest
from urllib.parse import urlsplit

from shiguang.site.build import publish_assets
from shiguang.site import render
from tests.test_trial_publication import page as page_context
from tests import test_news_browser as news_browser
from tools.qa_v03 import fixture

REFERENCE = Path('/workspace/proto-bot/rebang-visual/deploy')


@unittest.skipUnless(news_browser.sync_playwright and REFERENCE.exists(), 'Playwright and approved reference required')
class VisualBrowserTests(unittest.TestCase):
    setUpClass = classmethod(news_browser.NewsBrowserTests.setUpClass.__func__)
    tearDownClass = classmethod(news_browser.NewsBrowserTests.tearDownClass.__func__)

    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.out = Path(self.folder.name)
        site = page_context().site
        site.assets = publish_assets(self.out, True)
        self.out.joinpath('index.html').write_text(render.document(render.Page(site, '', 'today'), '今日', '', '', ''))
        self.data = fixture(REFERENCE)
        self.context = self.browser.new_context(viewport={'width':402,'height':874})
        self.addCleanup(self.context.close)
        self.page = self.context.new_page()
        self.errors = []
        self.page.on('pageerror', lambda err: self.errors.append(str(err)))

        def serve(route):
            path = urlsplit(route.request.url).path.lstrip('/')
            if path == 'visual-data.json':
                route.fulfill(json=self.data)
            elif path.startswith('qa-img/'):
                image = REFERENCE / 'img' / Path(path).name
                route.fulfill(body=image.read_bytes(), content_type=mimetypes.guess_type(image)[0])
            elif (self.out / path).is_file():
                route.fulfill(body=(self.out / path).read_bytes(), content_type=mimetypes.guess_type(path)[0] or 'text/plain')
            else:
                route.fulfill(status=404, body='not found')

        self.page.route('**/*', serve)
        self.page.add_init_script("localStorage.setItem('rebang-onboarded','true')")
        self.page.goto('https://offline.test/index.html#screens/today')
        self.page.wait_for_function('window.rebang !== undefined')

    def test_navigation_detail_back_and_live_favorites(self):
        page = self.page
        self.assertEqual(page.locator('#visual-app .bar button').all_text_contents(), ['今日','资讯','好玩','好买','收藏'])
        self.assertEqual(page.locator('.visual-main section').count(), 3)
        self.assertEqual(page.locator('.visual-main section').nth(1).locator('.gc').count(), 4)
        self.assertEqual(page.locator('.visual-main section').nth(2).locator('.gc').count(), 4)
        page.locator('.visual-main [data-save]').first.click()
        page.locator('.bar [data-go="fav"]').click()
        self.assertEqual(page.locator('.visual-main .row').count(), 1)
        page.locator('.visual-main [data-open]').first.click()
        self.assertEqual(page.evaluate('rebang.page'), 'detail')
        self.assertEqual(page.locator('.detail .bmk').get_attribute('aria-pressed'), 'true')
        page.locator('[data-back]').click()
        self.assertEqual(page.evaluate('rebang.page'), 'fav')
        page.locator('.visual-main [data-save]').click()
        self.assertEqual(page.locator('.visual-main .row').count(), 0)
        page.locator('#visual-toast button').click()
        self.assertEqual(page.locator('.visual-main .row').count(), 1)
        self.assertEqual(self.errors, [])

    def test_joint_filters_search_and_all_page_states(self):
        page = self.page
        page.locator('.bar [data-go="news"]').click()
        page.locator('[data-source="world"]').click()
        page.locator('[data-category="财经"]').click()
        expected = [x for x in self.data['news'] if x['source_id']=='world' and x['category']=='财经']
        self.assertEqual(page.locator('.visual-main .row').count(), min(20,len(expected)))
        page.locator('.ph [data-go="search"]').click()
        page.locator('#visual-query').fill('zzzz-no-match')
        self.assertIn('没有找到', page.locator('#visual-results').inner_text())
        page.locator('#visual-query').fill('iPhone')
        self.assertGreater(page.locator('#visual-results .row').count(), 0)
        for target in ['today','news','play','buy','fav','mag']:
            for state in ['loading','empty','error']:
                page.evaluate('s => rebang.setState(s)', {'page':target,'status':state})
                selector = '.skeleton' if state=='loading' else '.empty' if state=='empty' else '.failure'
                self.assertTrue(page.locator('.visual-main '+selector).is_visible())
        self.assertEqual(self.errors, [])

    def test_drawer_focus_calendar_lightbox_and_grouping(self):
        page = self.page
        page.locator('.ph [data-modal="drawer"]').click()
        self.assertTrue(page.locator('#visual-dialog').is_visible())
        page.keyboard.press('Shift+Tab')
        self.assertTrue(page.evaluate('document.querySelector("#visual-dialog").contains(document.activeElement)'))
        page.keyboard.press('Escape')
        self.assertFalse(page.locator('#visual-dialog').is_visible())
        self.assertEqual(page.locator(':focus').get_attribute('aria-label'), '全部导航')
        page.locator('.ph [data-modal="cal"]').click()
        page.locator('[data-date="2026-10-01"]').click()
        self.assertEqual(page.locator('#visual-toast').inner_text(), '这一天没有存档')
        page.locator('[data-date="2026-10-21"]').click()
        self.assertIn('10月21日', page.locator('.capsule').inner_text())
        page.locator('[data-today]').click()
        self.assertEqual(page.locator('.capsule').count(), 0)
        page.locator('.bar [data-go="play"]').click()
        self.assertEqual(page.locator('.chips button').all_text_contents(), ['全部','北京','全国和世界','线上','看读'])
        page.locator('[data-group="北京"]').click()
        self.assertGreater(page.locator('.gc').count(), 0)
        page.locator('.gc [data-open]').first.click()
        self.assertEqual(page.evaluate('rebang.page'), 'detail')
        page.locator('[data-back]').click()
        page.evaluate("rebang.setState({page:'detail',item:rebang.data.news.find(x=>x.image).id})")
        page.locator('[data-modal="lightbox"]').click()
        self.assertEqual(page.locator('#visual-dialog.lightbox').evaluate('(x)=>getComputedStyle(x).backgroundColor'), 'rgb(0, 0, 0)')
        self.assertEqual(self.errors, [])

    def test_refresh_retry_toast_expiry_and_cache_scope(self):
        page = self.page
        page.clock.install()
        page.route('**/visual-data.json', lambda route: route.abort())
        page.evaluate('rebang.refresh()')
        self.assertIn('没更新成功', page.locator('#visual-toast').inner_text())
        page.route('**/visual-data.json', lambda route: route.fulfill(json=self.data))
        page.locator('#visual-toast button').click()
        page.wait_for_function("document.querySelector('#visual-toast').textContent.includes('已更新')")
        page.clock.run_for(2600)
        self.assertFalse(page.locator('#visual-toast').is_visible())
        self.assertTrue(page.evaluate("() => {try{rebang.setState({data:{...rebang.data,scope:'private'}});return false}catch{return true}}"))
        self.context.set_offline(True)
        page.evaluate("rebang.setState({data:{...rebang.data,news:[],cards:[],magazines:[]},page:'news'})")
        self.assertIn('还没有缓存', page.locator('.visual-main .empty').inner_text())
        self.assertTrue(page.locator('.visual-main [data-retry]').is_visible())
        self.assertEqual(self.errors, [])

    def test_five_detail_variants_and_image_dark_mode(self):
        page = self.page
        cases = [next(x for x in self.data['news'] if x['image']),
                 next(x for x in self.data['news'] if not x['image']),
                 next(x for x in self.data['cards'] if x['kind']=='play' and x['image']),
                 next(x for x in self.data['cards'] if x['kind']=='play' and not x['image']),
                 next(x for x in self.data['cards'] if x['kind']=='buy')]
        for index, item in enumerate(cases):
            page.evaluate('item => localStorage.setItem("shiguang-favorites-public",JSON.stringify(item))', [item] if index%2 else [])
            page.evaluate('id => rebang.setState({page:"detail",status:"normal",item:id})', item['id'])
            self.assertEqual(page.locator('.detail h1').inner_text(), item['title'])
            self.assertEqual(page.locator('.detail .bmk').get_attribute('aria-pressed'), str(bool(index%2)).lower())
        page.emulate_media(color_scheme='dark')
        page.evaluate('id => rebang.setState({page:"news",status:"normal"})', None)
        self.assertEqual(page.locator('.thumb').first.evaluate('(x)=>getComputedStyle(x).filter'), 'none')
        self.assertEqual(page.locator('html').get_attribute('data-theme'), 'dark')
        self.assertEqual(self.errors, [])
