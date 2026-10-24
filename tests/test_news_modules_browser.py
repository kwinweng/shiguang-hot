"""Offline browser proof for the new live/source/review application."""
import json
import mimetypes
import os
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch
from urllib.parse import unquote, urlsplit

from tests import test_news_browser as legacy
from pipeline import sample_rows
from shiguang.config import config
from shiguang.model import BEIJING
from shiguang.site.build import build


@unittest.skipUnless(legacy.sync_playwright, 'optional Playwright unavailable')
class NewsModulesBrowserTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        legacy.NewsBrowserTests.setUpClass.__func__(cls)
        cls.temp = tempfile.TemporaryDirectory()
        cls.out = Path(cls.temp.name)/'site'
        now = datetime(2026,10,23,12,tzinfo=BEIJING)
        with patch.dict(os.environ,{'SITE_OUT':str(cls.out),'SITE_MODE':'public','MAIL_DIGEST':'0','SAMPLE_DATA':'1','NO_FETCH':'1'}):
            build(sample_rows(config(),now),[],now)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()
        legacy.NewsBrowserTests.tearDownClass.__func__(cls)

    def setUp(self):
        self.context = self.browser.new_context(viewport={'width':393,'height':852})
        self.addCleanup(self.context.close)
        self.page = self.context.new_page()
        self.errors = []
        self.page.on('pageerror',lambda error:self.errors.append(str(error)))
        def serve(route):
            url = urlsplit(route.request.url)
            self.assertEqual(url.netloc,'offline.test')
            path = self.out/(unquote(url.path).lstrip('/') or 'index.html')
            route.fulfill(status=200 if path.is_file() else 404,
                          body=path.read_bytes() if path.is_file() else b'missing',
                          content_type=mimetypes.guess_type(path)[0] or 'application/octet-stream')
        self.page.route('**/*',serve)

    def open(self,hash='feed'):
        self.page.goto('https://offline.test/index.html#'+hash)
        self.page.wait_for_selector('#news:not([aria-busy])')

    def test_default_tabs_filters_and_no_image_detail(self):
        self.open('')
        self.assertEqual(self.page.locator('.news-nav a').all_text_contents(), ['资讯', '探索', '我的'])
        self.assertEqual(self.page.locator('.seg a').all_text_contents(), ['实时', '热点', '回顾'])
        self.assertEqual(self.page.locator('.seg [aria-current]').inner_text(), '实时')
        self.assertEqual(self.page.locator('.row').count(), 48)
        self.page.get_by_role('button', name='科技', exact=True).click()
        self.page.wait_for_function("document.querySelectorAll('.row').length === 16")
        self.page.locator('.row').first.click()
        self.page.wait_for_selector('.dt h1')
        self.assertEqual(self.page.locator('.dt img').count(), 0)
        self.assertRegex(self.page.locator('.dt a.btn').get_attribute('href'), r'^https://t.me/.+/\d+$')
        self.page.get_by_role('button', name='收藏', exact=True).click()
        self.open('favorites')
        self.assertEqual(self.page.locator('.row').count(), 1)
        self.page.locator('.row').click()
        self.page.wait_for_selector('.dt h1')
        self.page.get_by_role('button', name='取消收藏', exact=True).click()
        self.open('favorites')
        self.assertEqual(self.page.locator('.row').count(), 0)
        self.assertEqual(self.errors, [])

    def test_existing_public_bookmarks_remain_reachable(self):
        saved = dict(id='old-saved-item', title='已有收藏', url='https://example.test/original',
                     source='旧来源', time='2026-10-20', snippet='已有摘要')
        self.page.add_init_script('localStorage.setItem("shiguang-favorites-public", '+json.dumps(json.dumps([saved], ensure_ascii=False))+');')
        self.open('favorites')
        self.assertEqual(self.page.locator('.row b').inner_text(), '已有收藏')
        self.page.locator('.row').click()
        self.page.wait_for_selector('.dt h1')
        self.assertEqual(self.page.locator('.dt a').get_attribute('href'), saved['url'])
        self.assertEqual(self.page.locator('.dt p').inner_text(), saved['snippet'])
        self.page.get_by_role('button', name='取消收藏', exact=True).click()
        self.assertEqual(self.page.evaluate('JSON.parse(localStorage.getItem("shiguang-favorites-public"))'), [])
        self.assertEqual(self.errors, [])

    def test_review_date_strip_expand_and_today_pending(self):
        self.open('review/2026-10-22')
        self.assertEqual(self.page.locator('.cal').count(), 0)
        self.assertTrue(self.page.locator('.date-strip').is_visible())
        self.assertEqual(self.page.locator('.day-summary').count(), 0)
        self.assertEqual(self.page.locator('.review-event').count(), 6)
        self.page.locator('.review-event summary').first.click()
        self.assertTrue(self.page.locator('.review-event .row').first.is_visible())
        self.page.locator('.review-event .row').first.click()
        self.page.wait_for_selector('.dt h1')
        self.page.locator('.back').click()
        self.page.wait_for_selector('.date-strip')
        self.page.get_by_role('link', name='今天', exact=True).click()
        self.page.wait_for_function("document.querySelector('#news').textContent.includes('00:30 后生成')")
        self.assertEqual(self.errors, [])

    def test_focus_switches_at_2200_and_expands_all_published_items(self):
        self.page.clock.set_fixed_time(datetime(2026, 10, 24, 21, 59, tzinfo=BEIJING))
        data = json.loads((self.out/'data/live.json').read_text())
        rows = data['messages'][:12]
        self.page.route('**/data/focus.json', lambda r: r.fulfill(json={'days': {'2026-10-23': rows, '2026-10-24': rows[:2]}}))
        self.open('focus')
        self.assertIn('10月23日的热点 · 今晚 22:00 更新', self.page.locator('#news').inner_text())
        self.assertEqual(self.page.locator('.focus-row').count(), 12)
        self.page.locator('.focus-row summary').first.click()
        self.assertTrue(self.page.locator('.focus-body').first.is_visible())
        self.assertIn(rows[0]['source_name'], self.page.locator('.focus-body').first.inner_text())
        self.page.clock.set_fixed_time(datetime(2026, 10, 24, 22, 0, tzinfo=BEIJING))
        self.open('me')
        self.open('focus')
        self.assertEqual(self.page.locator('.focus-row').count(), 2)
        self.assertIn('10月24日 22:00 日报', self.page.locator('#news').inner_text())
        self.assertEqual(self.errors, [])

    def test_explore_classification_detail_and_broken_image(self):
        base = json.loads((self.out/'data/live.json').read_text())['messages'][0]
        rows = [dict(base, id='play', section='play', category='温泉', image='missing.jpg'),
                dict(base, id='kan', section='kan', category='电影', image=''),
                dict(base, id='buy', section='buy', category='数码', image='')]
        self.page.route('**/data/explore.json', lambda r: r.fulfill(json={'messages': rows}))
        self.open('explore/play')
        self.assertEqual(self.page.locator('.seg a').all_text_contents(), ['好玩', '好看', '好买'])
        self.assertEqual(self.page.locator('.chips button').all_text_contents(), ['全部', '温泉'])
        self.page.get_by_role('button', name='温泉', exact=True).click()
        self.page.wait_for_function("document.querySelector('.chips [aria-pressed=true]').textContent==='温泉'")
        self.assertEqual(self.page.locator('.row').count(), 1)
        self.page.wait_for_function("document.querySelector('.row img') === null")
        self.assert_full_width_text()
        for section in ('kan', 'buy'):
            self.open('explore/' + section)
            self.assertEqual(self.page.locator('.row').count(), 1)
            self.page.locator('.row').click()
            self.page.wait_for_selector('.dt h1')
            self.assertEqual(self.page.locator('.dt img').count(), 0)
        self.assertEqual(self.errors, [])

    def test_explore_image_category_above_title_and_trimmed_title(self):
        console_errors = []
        self.page.on('console', lambda message: console_errors.append(message.text)
                     if message.type == 'error' else None)
        base = json.loads((self.out/'data/live.json').read_text())['messages'][0]
        title = '‘Paralyzed’ 标题中的 空格保留'
        rows = [dict(base, id='with-image', section='play', category='影视',
                     title=' \t\u3000' + title + '\u00a0\n', summary='独立正文内容',
                     image='icon-192.png'),
                dict(base, id='without-image', section='play', category='游戏',
                     title='无图标题', image='')]
        self.page.route('**/data/explore.json', lambda r: r.fulfill(json={'messages': rows}))
        self.open('explore/play')
        self.page.get_by_role('button', name='影视', exact=True).click()
        self.page.wait_for_function("document.querySelectorAll('.row').length === 1")
        self.assertEqual(self.page.locator('.row b').text_content(), title)
        self.assertEqual(self.page.locator('.row p').text_content(), '独立正文内容')
        self.page.wait_for_function("document.querySelector('.row img').naturalWidth > 0")
        for width in (320, 393, 1280):
            self.page.set_viewport_size({'width': width, 'height': 852})
            boxes = self.page.locator('.row').evaluate("""row => {
                const box = el => {
                    const r = el.getBoundingClientRect();
                    return {left:r.left, right:r.right, top:r.top, bottom:r.bottom};
                };
                return {row:box(row), category:box(row.querySelector('.cc')),
                        title:box(row.querySelector('b')), text:box(row.querySelector('p')),
                        image:box(row.querySelector('img'))};
            }""")
            for part in ('category', 'title', 'text'):
                self.assertAlmostEqual(boxes[part]['left'], boxes['row']['left'], delta=1)
                self.assertLessEqual(boxes[part]['right'], boxes['image']['left'] - 11)
            self.assertLessEqual(boxes['category']['bottom'], boxes['title']['top'])
            self.assertAlmostEqual(boxes['image']['right'], boxes['row']['right'], delta=1)
            self.assertAlmostEqual(boxes['image']['right'] - boxes['image']['left'], 76, delta=1)
        self.page.screenshot(path='/tmp/rebang-explore-image-desktop.png')
        self.page.set_viewport_size({'width': 393, 'height': 852})
        self.page.screenshot(path='/tmp/rebang-explore-image-mobile.png')
        self.assertEqual(self.page.url, 'https://offline.test/index.html#explore/play?category=%E5%BD%B1%E8%A7%86')
        self.assertIn('拾光热榜', self.page.title())
        self.assertEqual(console_errors, [])
        self.assertEqual(self.errors, [])

    def assert_full_width_text(self):
        for width in (320, 393, 1280):
            self.page.set_viewport_size({'width': width, 'height': 852})
            dimensions = self.page.locator('.row').first.evaluate("""row => ({
                row:row.getBoundingClientRect().width,
                title:row.querySelector('b').getBoundingClientRect().width,
                images:row.querySelectorAll('img').length
            })""")
            self.assertEqual(dimensions['images'], 0)
            self.assertAlmostEqual(dimensions['title'], dimensions['row'], delta=1)

    def test_explore_play_without_image_uses_full_width(self):
        base = json.loads((self.out/'data/live.json').read_text())['messages'][0]
        rows = [dict(base, id='no-image', section='play', category='温泉', image='')]
        self.page.route('**/data/explore.json', lambda r: r.fulfill(json={'messages': rows}))
        self.open('explore/play')
        self.assertEqual(self.page.locator('.row').count(), 1)
        self.assert_full_width_text()
        self.assertEqual(self.errors, [])

    def test_refresh_six_tabs_bypasses_cache_and_counts_new_ids(self):
        self.page.add_init_script("""window.fetchOptions=[]; const nativeFetch=window.fetch;
            window.fetch=(url, options)=>{window.fetchOptions.push(options?.cache);return nativeFetch(url, options);};""")
        base = json.loads((self.out/'data/live.json').read_text())
        fresh = dict(base, messages=[dict(base['messages'][0], id='new-item'), *base['messages'][1:]])
        for target in ('feed', 'focus', 'review/2026-10-22', 'explore/play', 'explore/kan', 'explore/buy'):
            self.open(target)
            requests = []
            self.page.on('request', lambda r: requests.append(r))
            self.page.evaluate('window.fetchOptions=[]')
            self.page.route('**/data/live.json', lambda r: r.fulfill(json=fresh))
            self.page.evaluate("""() => {
                const touch = y => new Touch({identifier:1,target:document.body,clientY:y});
                document.dispatchEvent(new TouchEvent('touchstart',{touches:[touch(10)]}));
                document.dispatchEvent(new TouchEvent('touchmove',{touches:[touch(120)],cancelable:true}));
                document.dispatchEvent(new TouchEvent('touchend',{touches:[]}));
            }""")
            self.page.wait_for_function("!document.querySelector('#news').hasAttribute('aria-busy') && /新增|已是最新/.test(document.querySelector('#refresh-status').textContent)")
            self.assertGreater(len(requests), 0)
            self.assertTrue(all(v == 'no-store' for v in self.page.evaluate('window.fetchOptions')))
            if target == 'feed':
                self.assertEqual(self.page.locator('#refresh-status').inner_text(), '新增 1 条')
        self.assertEqual(self.errors, [])

    def test_retry_offline_cache_unknown_route_and_404_file(self):
        self.page.route('**/data/live.json', lambda r: r.fulfill(status=503, body='unavailable'))
        self.open()
        self.assertIn('加载失败', self.page.locator('#news').inner_text())
        self.page.unroute('**/data/live.json')
        self.page.get_by_role('button', name='重试', exact=True).click()
        self.page.wait_for_selector('.row')
        self.context.set_offline(True)
        self.page.wait_for_selector('.offline')
        self.assertEqual(self.page.locator('.row').count(), 48)
        self.context.set_offline(False)
        self.open('unknown')
        self.assertEqual(self.page.get_by_role('link', name='回到资讯', exact=True).get_attribute('href'), '#feed')
        self.page.goto('https://offline.test/404.html')
        self.page.wait_for_selector('#news:not([aria-busy])')
        self.assertTrue(self.page.get_by_role('link', name='回到资讯', exact=True).is_visible())
        self.assertEqual(self.errors, [])

    def test_mobile_theme_layout_and_about_logo(self):
        self.open()
        for width in (320, 393, 1280):
            self.page.set_viewport_size({'width': width, 'height': 852})
            self.assertTrue(self.page.evaluate('document.documentElement.scrollWidth <= innerWidth'))
        self.open('settings')
        self.page.get_by_role('button', name='暗色', exact=True).click()
        self.assertEqual(self.page.locator('html').get_attribute('data-theme'), 'dark')
        self.page.reload()
        self.page.wait_for_selector('#news:not([aria-busy])')
        self.assertEqual(self.page.locator('html').get_attribute('data-theme'), 'dark')
        self.open('about')
        self.assertEqual(self.page.locator('.about img').get_attribute('src'), 'favicon.svg')
        self.assertEqual(self.errors, [])

    def test_row_c_dimensions_and_title_weights(self):
        live = json.loads((self.out/'data/live.json').read_text())
        r = live['messages'][0]
        r['image'] = 'icon-192.png'
        sources = json.loads((self.out/'data/sources.json').read_text())
        for source in sources['sources']:
            for message in source['messages']:
                if message['id'] == r['id']:
                    message['image'] = r['image']
        self.page.route('**/data/live.json', lambda route: route.fulfill(json=live))
        self.page.route('**/data/sources.json', lambda route: route.fulfill(json=sources))
        self.open()
        dimensions = self.page.locator('.row').first.evaluate("""row => ({
            category:row.querySelector('.cc'),
            image:[row.querySelector('img').width,row.querySelector('img').height],
            titleWeight:getComputedStyle(row.querySelector('b')).fontWeight,
            columns:getComputedStyle(row).gridTemplateColumns
        })""")
        self.assertIsNone(dimensions['category'])
        self.assertEqual(dimensions['image'], [76,76])
        self.assertEqual(dimensions['titleWeight'], '400')
        self.page.locator('.row').first.click()
        self.page.wait_for_selector('.dt h1')
        self.assertEqual(self.page.locator('.dt h1').evaluate('el=>getComputedStyle(el).fontSize'), '24px')
        self.assertEqual(self.page.locator('.dt h1').evaluate('el=>getComputedStyle(el).fontWeight'), '600')
        self.assertEqual(self.errors, [])

    def test_round_one_metadata_brand_missing_item_and_focus(self):
        self.open()
        self.assertTrue(self.page.locator('.brand img').is_visible())
        self.assertEqual(self.page.locator('.ph h1').evaluate('e=>getComputedStyle(e).fontWeight'), '600')
        self.assertRegex(self.page.locator('.row .meta').first.inner_text(), r'.+ · .+ · \d{2}:\d{2}$')
        self.assertEqual(self.page.locator('.flt button').first.inner_text(), '全部 48')
        self.page.locator('.seg a').nth(1).click()
        self.page.wait_for_selector('.seg a[href="#focus"][aria-current]')
        self.assertEqual(self.page.locator('.seg a').nth(1).evaluate('e=>getComputedStyle(e).backgroundColor'), 'rgba(0, 0, 0, 0)')
        self.open('message/does-not-exist')
        self.assertIn('这条内容找不到了', self.page.locator('#news').inner_text())
        self.assertEqual(self.page.locator('.skeleton').count(), 0)
        self.assertTrue(self.page.get_by_role('link', name='返回资讯').is_visible())
        self.open('explore/kan')
        self.assertTrue(self.page.get_by_role('link', name='先去看资讯').is_visible())
        self.open('review/2026-10-22')
        dates = self.page.locator('.date-strip a').evaluate_all('els=>els.map(e=>e.hash)')
        self.assertEqual(dates, sorted(dates, reverse=True))
        self.assertEqual(self.page.locator('.date-nav').count(), 0)
        self.assertNotIn('摘要（样例）', self.page.locator('#news').inner_text())
        self.assertEqual(self.errors, [])
