"""Safety and product boundaries of the isolated, example-only playground."""
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from bs4 import BeautifulSoup
from shiguang.site.ui import media_card, news_card, safe_url

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('design_preview', ROOT / 'tools/design_preview.py')
preview = importlib.util.module_from_spec(spec)
spec.loader.exec_module(preview)


class PlaygroundTests(unittest.TestCase):
    def test_untrusted_titles_reasons_and_sources_are_text(self):
        item = dict(id='x', kind='look', title='<img src=x onerror=alert(1)>', reason='<script>bad()</script>', source='<iframe>', url='javascript:alert(1)')
        tree = BeautifulSoup(news_card(item), 'html.parser')
        self.assertIsNone(tree.find('script'))
        self.assertIsNone(tree.find('iframe'))
        self.assertIsNone(tree.find('img'))
        self.assertIn('<img src=x onerror=alert(1)>', tree.get_text())
        self.assertEqual(tree.find('a')['href'], '#')
        self.assertEqual(safe_url('//host.example/a'), '#')
        self.assertEqual(safe_url('/design/assets/../private.png'), '#')

    def test_missing_price_does_not_invent_amount_or_empty_price_row(self):
        item = dict(id='a', kind='buy', title='Sample', reason='Example', group='数码', source='Sample', url='https://example.org/')
        tree = BeautifulSoup(media_card(item), 'html.parser')
        self.assertIsNone(tree.select_one('.price'))
        self.assertIsNone(tree.select_one('.fixture-label'))

    def test_build_is_example_only_and_fixed_preview_counts(self):
        with tempfile.TemporaryDirectory() as directory:
            target = preview.build(directory)
            html = (target / 'index.html').read_text()
            tree = BeautifulSoup(html, 'html.parser')
            today = tree.select_one('[data-panel=today]')
            self.assertEqual(len(today.select('.news-card')), 4)
            self.assertEqual(len(today.select('.hero-card')), 1)
            self.assertEqual([len(row.select('.media-card')) for row in today.select('.horizontal-cards')], [4, 4])
            self.assertEqual(len(tree.select('.app-panel')), 5)
            hot_cards = tree.select('[data-look-view=hot] [data-item]')
            hour_nine = [c['data-item'] for c in hot_cards if c.select_one('.news-meta').get_text().strip().endswith(('09:40', '09:58', '09:55'))]
            self.assertEqual(hour_nine, ['look-7', 'look-5', 'look-6'])
            data = json.loads((target / 'samples.json').read_text())
            self.assertTrue(data['example'])
            self.assertTrue(all(i['fixture'] for i in data['items']))
            self.assertNotIn('\u90ae\u4ef6', html)
            self.assertFalse((Path(directory) / 'tg.db').exists())
            self.assertFalse((Path(directory) / 'site').exists())
            self.assertFalse((Path(directory) / 'public-feeds').exists())
            standalone = preview.standalone(target).read_text()
            self.assertIn('window.__SHIGUANG_DESIGN_SAMPLES__', standalone)
            self.assertNotIn('src="/design/', standalone)
            self.assertNotIn('href="/design/', standalone)
            self.assertIn('data:image/', standalone)

    def test_public_assets_do_not_include_design_route_or_shared_preview_files(self):
        from shiguang.site.build import publish_assets
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory)
            names = publish_assets(out, True)
            self.assertEqual((out / names['css']).read_bytes(), (ROOT / 'web/style.css').read_bytes())
            self.assertEqual((out / names['js']).read_bytes(), (ROOT / 'web/app.js').read_bytes())
            self.assertFalse((out / 'design').exists())
            self.assertFalse((out / 'ui').exists())
            self.assertFalse((out / 'samples.json').exists())

    def test_all_shared_ui_icons_are_local_phosphor_with_a_saved_bookmark_glyph(self):
        with tempfile.TemporaryDirectory() as directory:
            target = preview.build(directory)
            tree = BeautifulSoup((target / 'index.html').read_text(), 'html.parser')
            self.assertIn('Copyright (c) 2023 Phosphor Icons', str(tree))
            self.assertIn('MIT License', preview.standalone(target).read_text())
            icons = tree.select('svg.icon')
            self.assertGreater(len(icons), 20)
            for icon in icons:
                self.assertEqual(icon.get('data-icon-family'), 'phosphor')
                self.assertEqual(icon.get('viewbox'), '0 0 256 256')
                self.assertEqual(icon.get('aria-hidden'), 'true')
                self.assertIsNone(icon.find('use'))
                self.assertIsNotNone(icon.find('path'))
            bookmarks = tree.select('[data-save] svg')
            self.assertTrue(bookmarks)
            for bookmark in bookmarks:
                self.assertEqual(bookmark.get('data-icon'), 'bookmark-simple')
                self.assertIsNotNone(bookmark.select_one('.icon-regular path'))
                self.assertIsNotNone(bookmark.select_one('.icon-fill path'))

    def test_builder_refuses_production_or_source_output(self):
        for output in [ROOT, ROOT / 'site', ROOT / 'site/private', ROOT / 'web/tmp', ROOT / 'design/output']:
            with self.subTest(output=output):
                with self.assertRaises(ValueError):
                    preview.build(output)


if __name__ == '__main__':
    unittest.main()
