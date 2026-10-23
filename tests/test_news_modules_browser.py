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

    def test_live_source_and_summary_first(self):
        self.open()
        self.assertEqual(self.page.locator('.flt button').count(),6)
        self.assertEqual(self.page.locator('.row').count(),48)
        self.assertEqual(self.page.locator('.flt button').evaluate_all('(buttons) => buttons.map(b => b.getAttribute("aria-label"))'),
                         ['全部','热门','科技','财经','国际','数码'])
        self.assertEqual(self.page.locator('.row a, .ol').count(), 0)
        self.page.get_by_role('button',name='科技',exact=True).click()
        self.page.wait_for_function("document.querySelectorAll('.row').length === 16")
        self.page.locator('.row').first.click()
        self.page.wait_for_selector('.dt h2')
        self.assertEqual(self.page.locator('.dt h2').inner_text(),'AI 摘要（样例）')
        self.assertIn('可能不准确', self.page.locator('.dt .foot').inner_text())
        self.assertEqual(self.page.locator('.dt a.btn').inner_text().strip(), '看原文')
        self.assertRegex(self.page.locator('.dt a.btn').get_attribute('href'),r'^https://t.me/.+/\d+$')
        self.assertTrue(self.page.url.startswith('https://offline.test/index.html#message/'))
        self.page.locator('.back').click()
        self.page.wait_for_selector('.row')
        self.assertIn('category=',self.page.url)
        self.page.locator('.acts a[href="#sources"]').click()
        self.page.wait_for_selector('.srow')
        self.assertNotIn('邮件精华',self.page.locator('#news').inner_text())
        self.page.locator('.srow[href="#source/xhqcankao"]').click()
        self.page.wait_for_selector('.scope')
        self.assertIn('近7天',self.page.locator('#news').inner_text())
        self.assertEqual(self.page.locator('.scope [aria-current="true"]').inner_text(), '近7天')
        self.assertTrue(self.page.locator('a.ext').is_visible())
        self.page.locator('.scope a').first.click()
        self.page.wait_for_selector('.scope a:first-child[aria-current="true"]')
        self.assertEqual(self.page.locator('.scope [aria-current="true"]').inner_text(), '今天')
        self.assertEqual(self.errors,[])

    def test_calendar_review_expand_filter_and_original_detail(self):
        self.open('history/2026-10')
        self.assertEqual(self.page.locator('.cal a').count(),7)
        self.assertEqual(self.page.locator('.cal .off').count(),24)
        self.page.locator('.cal a[href="#day/2026-10-22"]').click()
        self.page.wait_for_selector('.sum')
        self.assertEqual(self.page.locator('.sum').count(),6)
        self.page.locator('details summary').first.click()
        self.assertTrue(self.page.locator('details').first.get_attribute('open') is not None)
        self.assertTrue(self.page.locator('details .row').first.is_visible())
        self.page.locator('details summary').first.click()
        self.assertIsNone(self.page.locator('details').first.get_attribute('open'))
        self.assertFalse(self.page.locator('details .row').first.is_visible())
        self.assertTrue(self.page.url.endswith('#day/2026-10-22'))
        self.assertEqual(self.page.locator('.flt').count(), 0)
        self.assertEqual(self.page.locator('.sh').first.inner_text(), '热点')
        summary = self.page.locator('.day-summary')
        self.assertLess(summary.locator('h2').evaluate('(el) => parseFloat(getComputedStyle(el).fontSize)'), 20)
        self.assertTrue(summary.locator('p').evaluate('(el) => el.scrollHeight <= el.clientHeight'))
        self.page.locator('.event-title').first.click()
        self.page.wait_for_selector('.dt h2')
        self.assertEqual(self.page.locator('.dt h2').inner_text(),'AI 摘要（样例）')
        self.assertTrue(self.page.locator('.dt .btn').is_visible())
        self.assertEqual(self.errors,[])

    def test_mobile_dark_and_today_has_no_old_news_calendar(self):
        self.open()
        for width in (320,393,1280):
            self.page.set_viewport_size({'width':width,'height':852})
            self.assertTrue(self.page.evaluate('document.documentElement.scrollWidth <= innerWidth'))
        self.page.locator('#theme').click()
        self.assertEqual(self.page.locator('html').get_attribute('data-theme'),'dark')
        self.open('today')
        self.assertEqual(self.page.locator('#news-calendar, #news-history, .cal, .flt').count(),0)
        self.assertNotIn('看往日', self.page.locator('#news').inner_text())
        self.assertEqual(self.errors,[])

    def test_review_summary_source_counts_and_all_raw_messages(self):
        day = '2026-10-22'
        doc = json.loads((self.out/f'history/{day}.json').read_text())
        journal = dict(doc['messages'][0], id='journal-only', source='daily', source_name='日报', type='inbox')
        doc['messages'].append(journal)
        doc['stats']['sources']['daily'] = 1
        doc['stats']['total'] += 1
        self.page.route(f'**/history/{day}.json', lambda route: route.fulfill(json=doc))
        data = json.loads((self.out/'data/sources.json').read_text())
        data['sources'].append(dict(id='daily', name='日报', type='inbox', messages=[]))
        self.page.route('**/data/sources.json', lambda route: route.fulfill(json=data))
        self.open('day/' + day)
        self.assertEqual(self.page.locator('.day-summary h2').inner_text().strip(), 'AI 摘要（样例）')
        self.assertEqual(self.page.locator('.day-summary p').inner_text(), doc['summary'])
        for sid, count in doc['stats']['sources'].items():
            link = self.page.locator(f'.srow[href="#source/{sid}?day={day}"]')
            self.assertIn(f'{count} 条', link.inner_text())
        self.page.locator(f'.srow[href="#source/daily?day={day}"]').click()
        self.page.wait_for_selector('.row')
        self.assertEqual(self.page.locator('.row').count(), 1)
        self.open('day/' + day)
        self.page.get_by_role('link', name='看当天全部原始消息', exact=True).click()
        self.page.wait_for_selector('.row')
        self.assertEqual(self.page.locator('.row').count(), len(doc['messages']))
        self.assertIn('日报', self.page.locator('#news').inner_text())
        self.assertEqual(self.errors, [])

    def test_detail_image_order_note_and_original_post(self):
        data = json.loads((self.out/'data/sources.json').read_text())
        message = next(s['messages'][0] for s in data['sources'] if s['type'] == 'telegram' and s['messages'])
        message['image'] = 'icon-192.png'
        self.page.route('**/data/sources.json', lambda route: route.fulfill(json=data))
        self.open('message/' + message['id'])
        self.page.locator('.dt img').wait_for()
        self.assertEqual(self.page.locator('.dt').evaluate('(el) => Array.from(el.children).map(c => c.tagName)'),
                         ['SMALL', 'H1', 'IMG', 'H2', 'P', 'A', 'P'])
        self.assertIn(message['source_name'], self.page.locator('.dt > small').inner_text())
        self.assertIn(message['time'][:16].replace('T', ' '), self.page.locator('.dt > small').inner_text())
        self.assertEqual(self.page.locator('.dt .btn').get_attribute('href'), message['link'])
        self.assertEqual(self.page.locator('.dt .btn').get_attribute('target'), '_blank')
        for theme in ('light', 'dark'):
            self.page.locator('html').evaluate('(el, theme) => el.dataset.theme = theme', theme)
            self.assertEqual(self.page.locator('.dt .btn').evaluate('(el) => getComputedStyle(el).backgroundColor'),
                             self.page.locator('html').evaluate('(el) => {const s = document.createElement("span"); s.style.color="var(--c-brand)"; el.append(s); const c=getComputedStyle(s).color; s.remove(); return c;}'))
        self.assertEqual(self.errors, [])
