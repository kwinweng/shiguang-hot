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
        self.page.get_by_role('button',name='科技AI',exact=True).click()
        self.page.wait_for_function("document.querySelectorAll('.row').length === 16")
        self.page.locator('.row').first.click()
        self.page.wait_for_selector('.dt h2')
        self.assertEqual(self.page.locator('.dt h2').inner_text(),'摘要')
        self.assertRegex(self.page.locator('.dt a.btn').get_attribute('href'),r'^https://t.me/.+/\d+$')
        self.assertTrue(self.page.url.startswith('https://offline.test/index.html#message/'))
        self.page.locator('.back').click()
        self.page.wait_for_selector('.row')
        self.assertIn('category=',self.page.url)
        self.page.locator('.acts a[href="#sources"]').click()
        self.page.wait_for_selector('.srow')
        self.assertNotIn('邮件精华',self.page.locator('#news').inner_text())
        self.page.locator('.srow').first.click()
        self.page.wait_for_selector('.scope')
        self.assertIn('近7天',self.page.locator('#news').inner_text())
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
        self.page.get_by_role('button',name='社会',exact=True).click()
        self.page.wait_for_function("document.querySelectorAll('.sum').length === 1")
        self.page.locator('.event-title').click()
        self.page.wait_for_selector('.dt h2')
        self.assertEqual(self.page.locator('.dt h2').inner_text(),'摘要')
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
        self.assertEqual(self.errors,[])
