"""Offline browser acceptance. Optional Playwright; no real database or network requests."""
import json
import mimetypes
import os
import shutil
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit, unquote

from shiguang.model import BEIJING
from shiguang.site import history, pages, render
from shiguang.site.build import publish_assets
from tests.test_news_history import context, item

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    sync_playwright = None


@unittest.skipUnless(sync_playwright, 'optional Playwright is unavailable')
class NewsBrowserTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.playwright = sync_playwright().start()
        executable = os.getenv('NEWS_TEST_CHROME') or next((p for p in
            ['/opt/ungoogled-chromium/chrome', '/usr/bin/google-chrome'] if Path(p).is_file()), None)
        try:
            cls.browser = cls.playwright.chromium.launch(executable_path=executable, headless=True,
                args=['--no-sandbox', '--disable-crash-reporter', '--disable-breakpad'])
        except Exception as error:
            cls.playwright.stop()
            raise unittest.SkipTest(f'Browser unavailable: {str(error).splitlines()[0]}')

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.playwright.stop()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.out = Path(self.temp.name)
        rows = [item(n, ts=f'2026-10-22T{20-n//6:02}:{(n%6)*10:02}:00+08:00') for n in range(24)]
        rows += [item(50, source='world', category='财经'), item(51, source='world', ts='2026-10-20T12:00:00+08:00', category='AI'),
                 item(52, source='world', ts='2025-10-22', category='全球')]
        self.content, self.site = context(rows)
        self.site.entries = pages.CORE
        self.site.tabs = pages.TABS
        self.site.favorites = pages.FAVORITES
        self.site.assets = publish_assets(self.out, True)
        by_day, changed = history.prepare(self.content, self.site, self.out)
        for day in changed:
            pages.news_day_page(pages.Writer(self.site, self.out), self.content, day, by_day[day])
        self.browser_context = self.browser.new_context(viewport={'width': 393, 'height': 852})
        self.addCleanup(self.browser_context.close)
        self.page = self.browser_context.new_page()
        self.page.clock.install(time=datetime(2026, 10, 22, 12, tzinfo=BEIJING))
        self.page.clock.pause_at(datetime(2026, 10, 22, 12, 0, 1, tzinfo=BEIJING))
        self.requests = []
        self.errors = []
        self.page.on('pageerror', lambda error: self.errors.append(str(error)))
        self.fail_day = None
        def serve(route):
            path = unquote(urlsplit(route.request.url).path).lstrip('/') or 'index.html'
            if path.startswith('archive/data/'):
                self.requests.append(path)
            if self.fail_day and self.fail_day in path:
                route.fulfill(status=503, body='offline')
                return
            target = self.out / path
            if target.is_file():
                route.fulfill(body=target.read_bytes(), content_type=mimetypes.guess_type(path)[0] or 'application/octet-stream')
            else:
                route.fulfill(status=404, body='not found')
        self.page.route('**/*', serve)

    def open(self, query='', cards=True):
        self.page.goto(f'https://offline.test/index.html{query}#screens/look')
        self.page.wait_for_selector('.news-ready')
        if cards:
            self.page.wait_for_selector('#news-list article')

    def test_floating_bottom_bar_mobile_themes_and_content_clearance(self):
        for key, path in (('columns', 'columns.html'), ('favorites', 'favorites.html')):
            document = render.document(render.Page(self.site, '', key), key,
                                       '<p style="min-height:1600px">Navigation fixture</p>', '', '')
            (self.out / path).write_text(document)
        self.page.emulate_media(reduced_motion='reduce')
        for width in (320, 393, 844):
            self.page.set_viewport_size({'width': width, 'height': 852})
            for theme in ('light', 'dark'):
                with self.subTest(width=width, theme=theme):
                    self.page.goto('https://offline.test/columns.html?theme=' + theme)
                    bar = self.page.locator('nav.bottom')
                    self.assertTrue(bar.is_visible())
                    self.assertEqual(bar.locator('a').count(), 4)
                    self.assertEqual(bar.locator('svg.phosphor').count(), 4)
                    metrics = bar.evaluate('''bar => {
                        const box = bar.getBoundingClientRect(), style = getComputedStyle(bar);
                        const active = bar.querySelector('a.active');
                        return {left: box.left, right: box.right, height: box.height,
                            radius: style.borderRadius, background: style.backgroundColor,
                            color: getComputedStyle(active).color,
                            padding: parseFloat(getComputedStyle(document.querySelector('.layout')).paddingBottom),
                            bottom: parseFloat(style.bottom)};
                    }''')
                    self.assertGreaterEqual(metrics['left'], 16)
                    self.assertLessEqual(metrics['right'], width - 16)
                    self.assertEqual(metrics['height'], 70)
                    self.assertEqual(metrics['radius'], '35px')
                    self.assertEqual(metrics['color'], 'rgb(215, 40, 47)')
                    self.assertIn('30, 32, 36' if theme == 'dark' else '255, 255, 255', metrics['background'])
                    self.assertGreaterEqual(metrics['padding'], metrics['height'] + metrics['bottom'] + 22)
                    self.page.evaluate('scrollTo(0, document.documentElement.scrollHeight)')
                    footer = self.page.locator('.footer').bounding_box()
                    self.assertLessEqual(footer['y'] + footer['height'], bar.bounding_box()['y'])
                    link = bar.locator('a').last
                    link.focus()
                    self.assertTrue(link.evaluate('link => link === document.activeElement'))
                    self.assertEqual(link.get_attribute('href'), 'favorites.html')
                    bar.locator('a.active').click()
                    self.page.wait_for_function('scrollY === 0')
                    link.click()
                    self.page.wait_for_url('**/favorites.html')
                    self.assertEqual(self.page.locator('nav.bottom a[aria-current="page"]').inner_text(), '收藏')
        self.page.set_viewport_size({'width': 1280, 'height': 900})
        self.assertFalse(self.page.locator('nav.bottom').is_visible())
        self.assertTrue(self.page.locator('.desktop-nav').is_visible())
        self.assertEqual(self.errors, [])

    def test_initial_target_only_direct_jump_and_failed_jump_preserves_cards(self):
        self.open()
        self.assertEqual(self.requests, ['archive/data/2026-10-22.json'])
        self.fail_day = '2025-10-22'
        self.page.click('#news-date-toggle')
        self.page.click('[data-day="2025-10-22"]')
        self.page.wait_for_function("document.querySelector('#news-status').textContent.includes('503')")
        self.assertEqual(self.page.locator('#news-list article').first.get_attribute('data-day'), '2026-10-22')
        self.assertNotIn('archive/data/2026-10-20.json', self.requests)
        self.fail_day = None
        self.page.click('#news-retry')
        self.page.wait_for_function("document.querySelector('#news-list article').dataset.day === '2025-10-22'")
        self.assertIn('已到最早存档', self.page.locator('#news-status').inner_text())
        self.assertEqual(self.errors, [])

    def test_joint_filters_and_loaded_only_search(self):
        self.open('?source=world&topic=科技', cards=False)
        self.assertIn('无匹配', self.page.locator('#news-status').inner_text())
        self.assertEqual(self.page.locator('#news-dates button').count(), 1)
        self.assertEqual(self.page.locator('#news-dates button').get_attribute('data-day'), '2026-10-20')
        self.assertEqual(self.requests, [])

    def test_capsule_clock_keyboard_cancel_theme_and_hit_area(self):
        self.open('?theme=dark')
        capsule = self.page.locator('#news-capsule')
        self.assertEqual(capsule.evaluate('(e) => getComputedStyle(e).opacity'), '0')
        self.page.evaluate("dispatchEvent(new Event('wheel')); dispatchEvent(new Event('scroll'))")
        self.page.clock.run_for(200)
        self.assertIn('is-visible', capsule.get_attribute('class'))
        self.page.mouse.move(0, 0)
        self.page.clock.run_for(799)
        self.assertIn('is-visible', capsule.get_attribute('class'))
        self.page.clock.run_for(2)
        self.assertNotIn('is-visible', capsule.get_attribute('class'))
        capsule.focus()
        self.page.clock.run_for(1200)
        self.assertIn('is-visible', capsule.get_attribute('class'))
        capsule.press('End')
        self.assertIn('2025-10-22', capsule.get_attribute('aria-valuetext'))
        self.assertEqual(self.page.locator('#news-list article').first.get_attribute('data-day'), '2026-10-22')
        capsule.press('Escape')
        self.assertIn('2026-10-22', capsule.get_attribute('aria-valuetext'))
        self.assertGreaterEqual(capsule.bounding_box()['width'], 44)
        self.assertEqual(capsule.locator('i').evaluate('(e) => getComputedStyle(e).width'), '6px')
        self.assertEqual(capsule.locator('i').evaluate('(e) => getComputedStyle(e).backgroundColor'), 'rgba(180, 216, 179, 0.55)')
        for width in (320, 393, 1280):
            self.page.set_viewport_size({'width': width, 'height': 852})
            self.assertLessEqual(self.page.evaluate('document.documentElement.scrollWidth'), width)

    def test_loaded_search_auto_continuation_and_back_forward(self):
        self.page.clock.resume()
        self.open('?source=world')
        self.page.click('#news-search-toggle')
        self.page.fill('#news-query', 'Story 51')
        self.assertIn('未加载日期尚未搜索', self.page.locator('#news-status').inner_text())
        self.assertEqual(self.requests, ['archive/data/2026-10-22.json'])
        self.page.click('#news-retry')
        self.page.wait_for_function("document.querySelector('#news-list').textContent.includes('Story 51')")
        self.assertEqual(self.page.locator('#news-list article').count(), 1)
        self.assertEqual(self.page.locator('#news-list article').get_attribute('data-day'), '2026-10-20')
        self.assertEqual(len(self.requests), 2)
        self.page.click('#news-clear')
        self.page.wait_for_function("!new URL(location.href).searchParams.has('source')")
        self.page.go_back()
        self.page.wait_for_function("document.querySelector('#news-query').value === 'Story 51'")
        self.assertEqual(self.page.locator('#news-source').input_value(), 'world')
        self.page.go_forward()
        self.page.wait_for_function("document.querySelector('#news-source').value === ''")
        self.assertEqual(self.errors, [])

    def test_pointer_cancel_does_not_commit_preview(self):
        self.open()
        capsule = self.page.locator('#news-capsule')
        capsule.focus()
        current = self.page.locator('#news-current').inner_text()
        box = capsule.bounding_box()
        self.page.mouse.move(box['x'] + box['width'] - 5, box['y'] + 10)
        self.page.mouse.down()
        self.page.mouse.move(box['x'] + box['width'] - 5, 850)
        self.assertIn('2025-10-22', capsule.get_attribute('aria-valuetext'))
        self.assertEqual(self.page.locator('#news-current').inner_text(), current)
        capsule.dispatch_event('pointercancel', {'pointerId': 1})
        self.page.mouse.up()
        self.assertIn('2026-10-22', capsule.get_attribute('aria-valuetext'))
        self.assertEqual(self.requests, ['archive/data/2026-10-22.json'])
        self.assertEqual(self.errors, [])

    def test_automatic_continuation_does_not_wait_for_local_source_expansion(self):
        self.page.clock.resume()
        self.open()
        self.assertEqual(self.page.locator('#news-list details:not([open])').count(), 1)
        self.page.mouse.wheel(0, 1500)
        self.page.wait_for_function("document.querySelector('#news-list article[data-day=\"2026-10-20\"]') !== null")
        self.assertEqual(self.requests[:2], ['archive/data/2026-10-22.json', 'archive/data/2026-10-20.json'])
        ids = self.page.locator('#news-list article').evaluate_all('(cards) => cards.map(card => card.dataset.uid)')
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(self.errors, [])

    def test_missing_sidecars_leave_standalone_html_readable(self):
        (self.out / 'archive/manifest.json').unlink()
        shutil.rmtree(self.out / 'archive/data')
        self.page.goto('https://offline.test/archive/2025-10-22.html#screens/look')
        self.page.wait_for_selector('#news-fallback article')
        self.assertIn('Story 52', self.page.locator('#news-fallback').inner_text())
        self.assertIn('仅日期', self.page.locator('#news-fallback').inner_text())
        self.assertTrue(self.page.locator('#news-fallback [data-bookmark]').is_visible())
        self.assertEqual(self.errors, [])


if __name__ == '__main__':
    unittest.main()
