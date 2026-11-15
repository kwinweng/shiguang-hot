"""rebang.extract: public page extraction, cache, fallback. No network."""
import tempfile
import unittest
from datetime import datetime, timezone

from rebang.extract import apply_extraction, extract_html, is_public_article_url, should_extract

ARTICLE = """
<!doctype html><html><head><title>A long piece</title></head>
<body>
<nav>Home Login Subscribe</nav>
<article>
  <h1>Headline about the event</h1>
  <p>The first paragraph explains what happened in considerable detail so the extractor has enough text to work with, including several commas, and a proper story.</p>
  <p>The second paragraph continues the account with more facts, names, and a clear narrative that is much longer than a typical RSS teaser summary would be.</p>
  <p>A third paragraph wraps up the piece and mentions further context that readers would expect in a full article body rather than a one-line blurb.</p>
  <figure><img src="https://img.example/pic.jpg" alt="scene" width="800" height="500"></figure>
</article>
<footer>Copyright</footer>
</body></html>
"""

PAYWALL = """<!doctype html><html><head><title>Subscribe to continue</title></head>
<body><p>Please sign in or subscribe to continue reading this article on our site today.</p></body></html>"""


class ExtractTests(unittest.TestCase):
    def test_skips_login_and_private_hosts(self):
        self.assertFalse(is_public_article_url('https://t.me/foo/1'))
        self.assertFalse(is_public_article_url('https://x.com/a/status/1'))
        self.assertFalse(is_public_article_url('https://mp.weixin.qq.com/s/abc'))
        self.assertFalse(is_public_article_url('https://www.theguardian.com/account/login'))
        self.assertTrue(is_public_article_url('https://www.theguardian.com/world/2026/nov/15/story'))

    def test_extracts_article_and_image_in_order(self):
        got = extract_html(ARTICLE, 'https://www.example.com/story')
        self.assertIsNotNone(got)
        self.assertIn('first paragraph explains', got['body'])
        self.assertGreater(len(got['body']), 400)
        imgs = [b for b in got['blocks'] if b['type'] == 'img']
        self.assertEqual(imgs[0]['src'], 'https://img.example/pic.jpg')

    def test_paywall_page_returns_none(self):
        self.assertIsNone(extract_html(PAYWALL, 'https://www.example.com/pay'))

    def test_apply_uses_cache_and_falls_back_when_short(self):
        now = datetime(2026, 11, 16, 1, 0, tzinfo=timezone.utc)
        with tempfile.TemporaryDirectory() as d:
            item = {'id': 'bbc-world:1', 'kind': 'news', 'source_id': 'bbc-world',
                    'title': 'Headline about the event', 'summary': 'Short teaser.',
                    'url': 'https://www.example.com/story', 'body': 'Short teaser.', 'lang': 'en'}

            def http_get(url, _now):
                return ARTICLE.encode('utf-8')

            report = apply_extraction([item], d, fetch=True, http_get=http_get, now=now)
            self.assertEqual(report['fetched'], 1)
            self.assertEqual(report['applied'], 1)
            self.assertIn('first paragraph explains', item['body'])
            self.assertEqual(item['image']['url'], 'https://img.example/pic.jpg')

            def no(url, _now):
                raise AssertionError('should not fetch')

            item2 = {'id': 'bbc-world:1', 'kind': 'news', 'source_id': 'bbc-world',
                     'title': 'Headline about the event', 'summary': 'Short teaser.',
                     'url': 'https://www.example.com/story', 'body': 'Short teaser.', 'lang': 'en'}
            report2 = apply_extraction([item2], d, fetch=True, http_get=no, now=now)
            self.assertEqual(report2['from_cache'], 1)
            self.assertIn('first paragraph explains', item2['body'])

    def test_existing_long_body_is_left_alone(self):
        item = {'id': 'tnews365:1', 'kind': 'news', 'url': 'https://www.example.com/story',
                'body': 'x' * 900, 'summary': 's', 'source_id': 'tnews365'}
        self.assertFalse(should_extract(item))


if __name__ == '__main__':
    unittest.main()
