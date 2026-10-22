"""Offline 402×874 acceptance for both themes, filters, image errors and masonry."""
import mimetypes
import tempfile
import unittest
from pathlib import Path
from urllib.parse import urlsplit

from shiguang.site import render, trials
from shiguang.site.build import publish_assets
from tests import test_news_browser as news_browser
from tests.test_trial_publication import NOW, page, row


@unittest.skipUnless(news_browser.sync_playwright, 'optional Playwright is unavailable')
class TrialBrowserTests(unittest.TestCase):
    setUpClass = classmethod(news_browser.NewsBrowserTests.setUpClass.__func__)
    tearDownClass = classmethod(news_browser.NewsBrowserTests.tearDownClass.__func__)

    def test_two_themes_filters_failure_fallback_and_home(self):
        with tempfile.TemporaryDirectory() as folder:
            out = Path(folder)
            site = page().site
            site.assets = publish_assets(out, True)
            items = trials.prepare([
                row('earthsky'), row('gcores', image_url='https://broken.test/404.jpg'),
                row('appinn', title='Timer application'), row('9to5mac'), row('bambu-lab')], NOW)
            pages = {'play.html': ('好玩', lambda p: trials.body(items, '好玩', p)),
                     'buy.html': ('好买', lambda p: trials.body(items, '好买', p)),
                     'index.html': ('今日', lambda p: trials.home(items, p))}
            for path, (title, body) in pages.items():
                p = render.Page(site, '', 'today')
                (out / path).write_text(render.document(p, title, body(p), '', ''))
            for theme in ['light', 'dark']:
                context = self.browser.new_context(viewport={'width': 402, 'height': 874}, color_scheme=theme)
                try:
                    browser_page = context.new_page()
                    errors = []
                    browser_page.on('pageerror', lambda error: errors.append(str(error)))
                    def serve(route):
                        path = urlsplit(route.request.url).path.lstrip('/')
                        target = out / path
                        if urlsplit(route.request.url).hostname == 'offline.test' and target.is_file():
                            route.fulfill(body=target.read_bytes(), content_type=mimetypes.guess_type(path)[0] or 'application/octet-stream')
                        else:
                            route.fulfill(status=404, body='not found')
                    browser_page.route('**/*', serve)
                    for path in pages:
                        browser_page.goto('https://offline.test/' + path)
                        browser_page.wait_for_timeout(80)
                        self.assertFalse(browser_page.evaluate('document.documentElement.scrollWidth > innerWidth'))
                        self.assertEqual(browser_page.locator('.trial-card:visible').count(), 3 if path == 'play.html' else 2 if path == 'buy.html' else 5)
                    browser_page.goto('https://offline.test/play.html')
                    browser_page.wait_for_function("document.querySelector('.trial-media > img').hidden")
                    self.assertEqual(browser_page.locator('.trial-card[data-trial-category="games"] .trial-textcard').evaluate('(node) => getComputedStyle(node).display'), 'block')
                    browser_page.get_by_role('button', name='观星', exact=True).click()
                    self.assertEqual(browser_page.locator('.trial-card:visible').count(), 1)
                    expected = 'rgb(28, 28, 51)' if theme == 'dark' else 'rgb(235, 235, 247)'
                    self.assertEqual(browser_page.locator('.trial-card:visible .trial-textcard').evaluate('(node) => getComputedStyle(node).backgroundColor'), expected)
                    self.assertEqual(browser_page.get_by_role('button', name='观星', exact=True).get_attribute('aria-pressed'), 'true')
                    browser_page.get_by_role('button', name='全部好玩', exact=True).click()
                    self.assertEqual(browser_page.locator('.trial-card:visible').count(), 3)
                    self.assertEqual(errors, [])
                finally:
                    context.close()
