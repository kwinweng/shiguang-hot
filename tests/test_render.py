"""Checks for text cleanup, item normalization, card markup and cache-busted assets."""
import hashlib
import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from bs4 import BeautifulSoup

from shiguang.config import WEB
from shiguang.enrich.clean import clean, headline
from shiguang.model import BEIJING, from_telegram, home_candidates, issue_items
from shiguang.site import build as sitebuild, render

TG = dict(id='tg', type='telegram', channel='chan', name='频道', icon='all', order=50, home=dict(weight=1, cap=4))
INBOX = dict(id='x', type='inbox', name='推特爆款', icon='x', adapter='x', order=30, home=dict(weight=1, cap=8))
NOW = datetime(2026, 10, 17, 12, tzinfo=BEIJING)


def page(rel=''):
    site = render.Site(sources={'tg': TG, 'x': INBOX}, entries=[], tabs=[], favorites={}, private=False, now=NOW,
                       topics=['科技', '其他'], assets={}, is_photo=lambda path: path.endswith('photo.webp'))
    return render.Page(site, rel, 'home')


class HeadlineTests(unittest.TestCase):
    def test_bracket_title_and_body(self):
        self.assertEqual(headline(clean('【美联储降息25个基点】美联储宣布降息。')), ('美联储降息25个基点', '美联储宣布降息。'))

    def test_url_ends_title_and_is_dropped(self):
        title, body = headline(clean('SK海力士重启大连NAND二厂建设 https://www.nbd.com.cn/a.html 计划明年增产。'))
        self.assertEqual(title, 'SK海力士重启大连NAND二厂建设')
        self.assertNotIn('http', title + body)
        self.assertIn('计划明年增产', body)

    def test_divider_lines_and_early_exclamation(self):
        title, body = headline(clean('这次能飞了！特斯拉第二代 Roadster 跑车正式亮相\n========\n特斯拉能飞'))
        self.assertEqual(title, '这次能飞了！特斯拉第二代 Roadster 跑车正式亮相')
        self.assertEqual(body, '特斯拉能飞')

    def test_bold_title_first_line(self):
        text = clean('人工智能公司发布新模型 ======== 经典 A')
        self.assertEqual(headline(text, '<b>人工智能公司发布新模型 ======== 经典 A</b>'), ('人工智能公司发布新模型', '经典 A'))

    def test_title_only_message_has_empty_body(self):
        self.assertEqual(headline(clean('一条只有标题的消息')), ('一条只有标题的消息', ''))

    def test_long_first_sentence_is_truncated(self):
        title, body = headline(clean('长' * 120))
        self.assertTrue(title.endswith('…'))
        self.assertEqual(len(title), 87)
        self.assertEqual(body, '长' * 120)


class CardTests(unittest.TestCase):
    def test_telegram_card_meta_time_and_bookmark_identity(self):
        row = dict(ch='chan', id=42, ts='2026-10-17T09:30:00+08:00', title='邮件标题', body='正文', cat='其他',
                   day='2026-10-17', url='https://t.me/chan/42', images=['media/chan/photo.webp'])
        item = from_telegram(row, TG, public=True)
        self.assertEqual(item.title, '电邮标题')
        html = render.card(page('../'), item)
        soup = BeautifulSoup(html, 'html.parser')
        self.assertEqual([s.get_text() for s in soup.select('.g-card__who span')], ['频道'])  # 其他 adds nothing
        self.assertIsNone(soup.select_one('.source').get('style'))  # no decorative source colours
        self.assertEqual(soup.select_one('time').get_text(), '09:30')
        self.assertEqual(soup.select_one('img')['src'], '../media/chan/photo.webp')
        self.assertIn('card--side', soup.article['class'])
        identity = json.dumps(['tg', 42, row['ts']], ensure_ascii=False)
        saved = json.loads(soup.select_one('[data-bookmark]')['data-bookmark'])
        self.assertEqual(saved['id'], hashlib.sha256(identity.encode()).hexdigest())

    def test_inbox_card_shows_sub_source_once(self):
        issue = dict(date='2026-10-16', sections=[dict(title='s', items=[
            dict(title='Elon Musk', body='b', source='X', date='2026-10-16 08:00', link='javascript:alert(1)',
                 images=[dict(file='x/img/shot.webp')])])])
        item = issue_items(issue, INBOX)[0]
        soup = BeautifulSoup(render.card(page(), item), 'html.parser')
        self.assertEqual([s.get_text() for s in soup.select('.g-card__who span')], ['推特爆款', 'X'])
        self.assertEqual(soup.select_one('time').get_text(), '10-16 08:00')
        self.assertIn('card--wide', soup.article['class'])  # a screenshot, not a photo
        self.assertIsNone(soup.select_one('h2 a'))   # unsafe link dropped

    def test_block_only_issue_links_to_its_page(self):
        issue = dict(date='2026-10-17', sections=[], blocks=[dict(type='markets', items=[])])
        item = home_candidates(issue, INBOX)[0]
        soup = BeautifulSoup(render.card(page(), item), 'html.parser')
        self.assertEqual(soup.select_one('h2 a')['href'], 'x/2026-10-17.html')
        self.assertEqual(soup.select_one('time').get_text(), '今天')


class SpecComponentTests(unittest.TestCase):
    def test_several_photos_make_a_strip_with_dots(self):
        row = dict(ch='chan', id=7, ts='2026-10-17T09:30:00+08:00', title='t', body='b', cat='其他', day='2026-10-17',
                   url='https://t.me/chan/7', images=['media/a.webp', 'media/b.webp', 'media/c.webp'])
        soup = BeautifulSoup(render.card(page(), from_telegram(row, TG, True)), 'html.parser')
        self.assertEqual(len(soup.select('.g-strip .g-print img')), 3)
        self.assertEqual(len(soup.select('.g-dots i')), 3)
        self.assertEqual(len(soup.select('.g-dots i[aria-current]')), 1)

    def test_group_carries_its_light(self):
        soup = BeautifulSoup(render.group(['推特爆款'], '', light=('data:light', 'data:dark')), 'html.parser')
        self.assertEqual((soup.section['data-light'], soup.section['data-light-dark']), ('data:light', 'data:dark'))
        self.assertNotIn('data-light', render.group(['x'], ''))

    def test_reading_switch_has_three_sizes(self):
        soup = BeautifulSoup(render.reading_switch(), 'html.parser')
        self.assertEqual([b['data-reading'] for b in soup.select('.g-seg__item')], ['1', '2', '3'])
        css = (WEB / 'style.css').read_text()
        self.assertIn('font-size:18px;line-height:33px', css)
        self.assertIn('font-size:19.5px;line-height:36px', css)


class FilterTests(unittest.TestCase):
    def test_topics_and_sources_are_separate_and_only_present_ones_offered(self):
        row = dict(ch='chan', id=1, ts='2026-10-17T09:30:00+08:00', title='t', body='b', cat='科技', day='2026-10-17', url='')
        soup = BeautifulSoup(render.filters(page(), [from_telegram(row, TG, True)]), 'html.parser')
        self.assertEqual([b.get_text() for b in soup.select('.filters .pill')], ['全部', '科技'])
        self.assertEqual([(o['value'], o.get_text()) for o in soup.select('#channel option')], [('', '全部来源'), ('chan', '频道')])

    def test_redirect_keeps_target_and_works_without_script(self):
        html = render.redirect('../index.html?source=chan', '频道')
        self.assertIn('content="0;url=../index.html?source=chan"', html)
        self.assertIn('location.replace("../index.html?source=chan"+location.hash)', html)


class DesignSystemTests(unittest.TestCase):
    """Rules of the 「光」 spec that the stylesheet and templates must keep."""
    css = (WEB / 'style.css').read_text()

    def test_every_icon_reference_has_a_symbol(self):
        import re
        from shiguang.site.icons import sprite
        defined = re.findall(r'<symbol id="([a-z]+-[a-z0-9-]+)"', sprite())
        self.assertEqual(len(defined), len(set(defined)))
        self.assertEqual(sprite().count('id="status-sun"'), 1)  # gradients defined once, not per icon
        site = page().site
        site.entries = [('today', 'index.html', '今日', 'home'), ('hot', 'hot.html', '热点', 'hot')]
        site.tabs = ['today', 'hot', 'columns', 'favorites']
        site.favorites = {'enabled': True, 'label': '收藏', 'path': 'favorites.html', 'column': True}
        site.assets = {'css': 'style.css', 'js': 'app.js', 'version': '1'}
        row = dict(ch='chan', id=1, ts='2026-10-17T09:30:00+08:00', title='t', body='b', cat='科技', day='2026-10-17', url='https://t.me/chan/1')
        p = render.Page(site, '', 'today')
        html = render.document(p, 'x', render.heading(p, '今天 1 条要闻', 'note') + render.card(page(), from_telegram(row, TG, True)), '', '')
        used = set(re.findall(r'href="#([a-z]+-[a-z0-9-]+)"', html))
        self.assertTrue(used)
        self.assertLessEqual(used, set(defined))
        self.assertEqual(html.count('<svg class="sprite"'), 1)
        soup = BeautifulSoup(html, 'html.parser')
        self.assertIsNotNone(soup.select_one('nav.bottom a.active.slot-1'))
        self.assertIn('slot-1', soup.select_one('nav.bottom .tab__pill')['class'])
        # Tab bar: words only.
        self.assertIsNone(soup.select_one('nav.bottom svg'))
        self.assertEqual(soup.select_one('nav.bottom a.active').get_text(), '今日')
        # Lead block uses a 3D status icon at lead size.
        self.assertIsNotNone(soup.select_one('.g-lead .s-icon--lead'))

    def test_sun_is_only_ever_a_fill(self):
        import re
        offending = re.findall(r'(?<![-\w])(color|stroke|outline[-a-z]*|border[-a-z]*|text-decoration[-a-z]*)\s*:[^;{}]*var\(--sun\)', self.css)
        self.assertEqual(offending, [])

    def test_weights_and_letter_spacing(self):
        import re
        self.assertLessEqual({int(w) for w in re.findall(r'font-weight:\s*(\d+)', self.css)}, {400, 500, 600, 700})
        spaced = {sel.strip().split(',')[0] for sel, val in re.findall(r'([^{}]+)\{[^}]*?letter-spacing:([\d.]+)px', self.css) if float(val) > 0}
        self.assertLessEqual(spaced, {'.g-card__label', '.g-topbar__brand', '.section-label h2', '.sheet__group'})

    def test_glass_cards_never_blur(self):
        import re
        for selector, body in re.findall(r'([^{}]+)\{([^}]*)\}', self.css):
            if 'backdrop-filter:blur' in body:
                self.assertFalse(re.search(r'\.(g-card|g-sheet|card)\b', selector), selector)

    def test_light_follows_the_spec(self):
        from shiguang.site import light
        dawn = light.ambient_pixels(None, 'light')
        self.assertEqual(len(dawn), 30 * 40)
        # Dawn sky: warmer at the top than at the bottom.
        top, bottom = dawn[0], dawn[-1]
        self.assertGreater(top[0] - top[2], bottom[0] - bottom[2])
        for scheme, (lo, hi) in (('light', (.77, .94)), ('dark', (.17, .47))):
            for rgb in light.ambient_pixels(None, scheme)[::97]:
                L = light.oklab(tuple(v / 255 for v in rgb))[0]
                self.assertGreaterEqual(L, lo - .02); self.assertLessEqual(L, hi + .02)
        self.assertTrue(light.light_css('/no/such/file.jpg').startswith(':root{--light-image:url("data:image/png;base64,'))


class AssetTests(unittest.TestCase):
    def test_hashed_assets_and_stale_cleanup(self):
        with tempfile.TemporaryDirectory() as folder:
            root, out = Path(folder) / 'repo', Path(folder) / 'site'
            (root / 'assets').mkdir(parents=True); out.mkdir()
            (root / 'assets' / 'favicon.svg').write_text('<svg/>')
            (root / 'style.css').write_text('body{}'); (root / 'app.js').write_text('1')
            (out / 'style.0000000000.css').write_text('old')
            with patch.object(sitebuild, 'WEB', root):
                names = sitebuild.publish_assets(out, full=False)
                self.assertTrue((out / 'style.0000000000.css').exists())  # inbox-only builds keep old pages working
                self.assertEqual((out / names['css']).read_text(), 'body{}')
                sitebuild.publish_assets(out, full=True)
            self.assertFalse((out / 'style.0000000000.css').exists())
            self.assertRegex(names['js'], r'^app\.[0-9a-f]{10}\.js$')


if __name__ == '__main__':
    unittest.main()
