"""Checks for text cleanup, item normalization, card markup and cache-busted assets."""
import hashlib
import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from bs4 import BeautifulSoup

import render
import sitebuild
from items import BEIJING, from_telegram, home_candidates, issue_items
from textclean import clean, headline

TG = dict(id='tg', type='telegram', channel='chan', name='频道', color='#4279c2', icon='all')
INBOX = dict(id='x', type='inbox', name='推特爆款', color='#222', icon='x', adapter='x')
NOW = datetime(2026, 10, 17, 12, tzinfo=BEIJING)


def page(rel=''):
    site = render.Site(sources={'tg': TG, 'x': INBOX}, entries=[], tabs=[], favorites={}, private=False, now=NOW,
                       categories=['科技', '综合'], assets={}, is_photo=lambda path: path.endswith('photo.webp'))
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
        row = dict(ch='chan', id=42, ts='2026-10-17T09:30:00+08:00', title='邮件标题', body='正文', cat='综合',
                   day='2026-10-17', url='https://t.me/chan/42', images=['media/chan/photo.webp'])
        item = from_telegram(row, TG, public=True)
        self.assertEqual(item.title, '电邮标题')
        html = render.card(page('../'), item)
        soup = BeautifulSoup(html, 'html.parser')
        self.assertEqual([s.get_text() for s in soup.select('.card__meta span')], ['频道'])  # 综合 adds nothing
        self.assertEqual(soup.select_one('.source')['style'], '--source:#4279c2')
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
        self.assertEqual([s.get_text() for s in soup.select('.card__meta span')], ['推特爆款', 'X'])
        self.assertEqual(soup.select_one('time').get_text(), '10-16 08:00')
        self.assertIn('card--wide', soup.article['class'])  # a screenshot, not a photo
        self.assertIsNone(soup.select_one('h2 a'))   # unsafe link dropped

    def test_block_only_issue_links_to_its_page(self):
        issue = dict(date='2026-10-17', sections=[], blocks=[dict(type='markets', items=[])])
        item = home_candidates(issue, INBOX)[0]
        soup = BeautifulSoup(render.card(page(), item), 'html.parser')
        self.assertEqual(soup.select_one('h2 a')['href'], 'x/2026-10-17.html')
        self.assertEqual(soup.select_one('time').get_text(), '今天')


class DesignSystemTests(unittest.TestCase):
    def test_every_icon_reference_has_a_symbol(self):
        import re
        from icons import GLYPHS, sprite
        defined = re.findall(r'<symbol id="i-([a-z-]+)"', sprite())
        self.assertEqual(len(defined), len(set(defined)))
        self.assertEqual(set(defined), set(GLYPHS))
        site = page().site
        site.entries = [('home', 'index.html', '首页', 'home'), ('daily', 'archive/index.html', '日报', 'archive')]
        site.tabs = ['favorites', 'daily', 'home', 'news', 'x']
        site.favorites = {'enabled': True, 'label': '收藏', 'path': 'favorites.html', 'column': True}
        site.assets = {'css': 'style.css', 'js': 'app.js', 'version': '1'}
        row = dict(ch='chan', id=1, ts='2026-10-17T09:30:00+08:00', title='t', body='b', cat='科技', day='2026-10-17', url='https://t.me/chan/1')
        html = render.document(render.Page(site, '', 'home'), 'x', render.card(page(), from_telegram(row, TG, True)), '', '')
        used = set(re.findall(r'href="#i-([a-z-]+)"', html))
        self.assertTrue(used)
        self.assertLessEqual(used, set(defined))
        self.assertEqual(html.count('<svg class="sprite"'), 1)
        soup = BeautifulSoup(html, 'html.parser')
        self.assertIsNotNone(soup.select_one('nav.bottom a.home-slot.active.slot-3'))
        self.assertIn('slot-3', soup.select_one('nav.bottom .tab__pill')['class'])
        self.assertEqual(len(soup.select('nav.bottom .tab__pill')), 1)

    def test_sun_is_only_ever_a_fill(self):
        # README 设计规范: sun is the only accent colour and is used only as a fill.
        import re
        css = (Path(__file__).parent / 'style.css').read_text()
        offending = re.findall(r'(?<![-\w])(color|stroke|outline[-a-z]*|border[-a-z]*|text-decoration[-a-z]*)\s*:[^;{}]*var\(--sun\)', css)
        self.assertEqual(offending, [])


class AssetTests(unittest.TestCase):
    def test_hashed_assets_and_stale_cleanup(self):
        with tempfile.TemporaryDirectory() as folder:
            root, out = Path(folder) / 'repo', Path(folder) / 'site'
            (root / 'assets').mkdir(parents=True); out.mkdir()
            (root / 'assets' / 'favicon.svg').write_text('<svg/>')
            (root / 'style.css').write_text('body{}'); (root / 'app.js').write_text('1')
            (out / 'style.0000000000.css').write_text('old')
            with patch.object(sitebuild, 'ROOT', root):
                names = sitebuild.publish_assets(out, full=False)
                self.assertTrue((out / 'style.0000000000.css').exists())  # inbox-only builds keep old pages working
                self.assertEqual((out / names['css']).read_text(), 'body{}')
                sitebuild.publish_assets(out, full=True)
            self.assertFalse((out / 'style.0000000000.css').exists())
            self.assertRegex(names['js'], r'^app\.[0-9a-f]{10}\.js$')


if __name__ == '__main__':
    unittest.main()
