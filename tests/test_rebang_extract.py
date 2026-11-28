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


def test_extract_nested_nav_does_not_crash():
    """分解祖先节点后，后代再调用 tag.get 不能 AttributeError（BBC 页就会撞上）。"""
    from rebang.extract import extract_html
    html = """<html><head><title>Story</title></head><body>
    <article><div class="story-body">
      <p>""" + ("This is a sufficiently long paragraph about the news. " * 20) + """</p>
      <nav class="share"><div class="share-tools"><span>Share</span></div></nav>
      <p>""" + ("Another long paragraph continues the article so we keep enough text. " * 20) + """</p>
    </div></article></body></html>"""
    got = extract_html(html, 'https://www.bbc.co.uk/news/articles/example')
    assert got and len(got['body']) >= 400


TELEGRAPH = """<!doctype html><html><head><title>宏福苑大火一周年 - 纽约时报双语版 – Telegraph</title></head><body>
<div class="tl_page"><main class="tl_article"><header class="tl_article_header" dir="auto">
<h1>宏福苑大火一周年 - 纽约时报双语版</h1><address><a rel="author">纽约时报双语版</a><time>November 27, 2026</time></address>
</header><article id="_tl_editor" class="tl_article_content"><h1>宏福苑大火一周年 - 纽约时报双语版<br></h1>
<address>纽约时报双语版<br></address>
<figure><img src="https://static01.nyt.com/images/fire.jpg"><figcaption>周四，人们在香港献花。</figcaption></figure>
<p>A year ago Thursday, a blaze tore through a sprawling high-rise apartment complex in Hong Kong, spreading from one tower to the next, killing 168 people.</p>
<p>一年前的周四，一场大火席卷香港一座占地广阔的高层公寓楼群，火势从一栋楼蔓延到另一栋楼，造成168人遇难。对于留下的家属来说，如何哀悼逝者已成为一个政治敏感问题。</p>
<p>In the days leading up to the anniversary, Beijing warned against efforts to exploit the disaster, and the city government said it would not hold a memorial.</p>
<p>在周年纪念日前夕，北京警告不要利用这场灾难“以灾乱港”，港府表示不会举办悼念活动。</p>
</article></main></div></body></html>"""
TELEGRAPH_URL = 'https://telegra.ph/hongfuyuan-11-27'


class TelegraphTests(unittest.TestCase):
    def test_telegraph_article_only_without_repeated_title_or_byline(self):
        got = extract_html(TELEGRAPH, TELEGRAPH_URL)
        self.assertIsNotNone(got)
        self.assertTrue(got['body'].startswith('周四，人们在香港献花') or 'A year ago Thursday' in got['body'])
        self.assertNotIn('宏福苑大火一周年 - 纽约时报双语版', got['body'])
        self.assertNotIn('纽约时报双语版', got['body'])
        self.assertIn('以灾乱港', got['body'])
        self.assertEqual([b['src'] for b in got['blocks'] if b['type'] == 'img'], ['https://static01.nyt.com/images/fire.jpg'])

    def test_telegraph_url_recognised_only_for_article_pages(self):
        from rebang.extract import is_telegraph_url
        self.assertTrue(is_telegraph_url(TELEGRAPH_URL))
        self.assertTrue(is_telegraph_url('https://graph.org/abc-11-27'))
        self.assertFalse(is_telegraph_url('https://telegra.ph/'))
        self.assertFalse(is_telegraph_url('http://telegra.ph/abc'))
        self.assertFalse(is_telegraph_url('https://telegra.ph.evil.com/abc'))
        self.assertFalse(is_telegraph_url('https://t.me/shuangyunews_rss/1'))

    def test_tg_item_fetches_its_telegraph_page_and_keeps_tme_link(self):
        seen = []

        def http_get(url, now):
            seen.append(url)
            return TELEGRAPH.encode('utf-8')

        item = {'id': 'shuangyunews_rss:9', 'kind': 'news', 'source_id': 'shuangyunews_rss',
                'title': '纽约时报双语版', 'summary': '宏福苑大火一周年', 'url': 'https://t.me/shuangyunews_rss/9',
                'body': '纽约时报双语版\n宏福苑大火一周年\nTelegraph | 原文链接 | 频道大全', 'lang': 'zh',
                'extract_url': TELEGRAPH_URL, 'image_local': {'path': '/x.webp'}}
        plain = {'id': 'other:1', 'kind': 'news', 'source_id': 'other', 'title': 't', 'summary': 's',
                 'url': 'https://t.me/other/1', 'body': 's', 'lang': 'zh'}
        with tempfile.TemporaryDirectory() as d:
            report = apply_extraction([item, plain], d, fetch=True, http_get=http_get,
                                      now=datetime(2026, 11, 28, tzinfo=timezone.utc))
        self.assertEqual(seen, [TELEGRAPH_URL])          # 没有 Telegraph 链接的 TG 条目照旧不抓
        self.assertEqual(report['applied'], 1)
        self.assertIn('以灾乱港', item['body'])
        self.assertEqual(item['url'], 'https://t.me/shuangyunews_rss/9')
        self.assertNotIn('extract_url', item)            # 不写进成品
        self.assertNotIn('image', item)                   # 已有本地预览图，不换成外站图
        self.assertNotIn('blocks', plain)
