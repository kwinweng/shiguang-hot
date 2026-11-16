"""TG 公开页面附加信息（v13，阿欢 2026-11-15 22:08）：频道自己的话、引用/转发卡、表情回应、浏览数、公开评论。不联网。"""
import io
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from rebang.contract import validate_item
from rebang.ingest.core import _tg_parts
from rebang.tgmeta import merge_meta, parse_count, parse_discussion, parse_page, refresh

FIX = Path(__file__).parent / 'fixtures' / 'rebang' / 'tgmeta'
BJ = timezone(timedelta(hours=8))


class ParseTests(unittest.TestCase):
    def setUp(self):
        self.page = parse_page((FIX / 'page.html').read_text(encoding='utf-8'))

    def test_reply_keeps_channel_own_text_not_quoted_original(self):
        m = self.page[101]
        self.assertEqual(m['text'], '【频道自己的话】\n这是频道对原帖的评论。')
        self.assertEqual(m['reply'], {'name': '演示频道', 'text': '被引用的原帖原文，第一句。', 'url': 'https://t.me/demo/90'})

    def test_reactions_views_counts_from_page_only(self):
        m = self.page[101]
        self.assertEqual([(r['emoji'], r['count'], r['label']) for r in m['reactions']],
                         [('👍', 1200, '1.2K'), ('😁', 34, '34'), ('⭐', 3, '3')], '自定义表情没字符就跳过，不编')
        self.assertEqual((m['views'], m['views_label']), (20200, '20.2K'))
        self.assertNotIn('reactions', self.page[103])
        self.assertNotIn('views', self.page[103])

    def test_forward(self):
        self.assertEqual(self.page[102]['forward'], {'name': '别的频道', 'url': 'https://t.me/other/555'})

    def test_parse_count(self):
        self.assertEqual([parse_count(x) for x in ('7', '1.3M', '20.2K', 'abc', '')], [7, 1300000, 20200, None, None])

    def test_discussion_public_and_off(self):
        d = parse_discussion((FIX / 'discussion.html').read_text(encoding='utf-8'))
        self.assertTrue(d['enabled'])
        self.assertEqual(d['total'], 12)
        self.assertEqual([(c['display_name'], c['text']) for c in d['comments']], [('读者甲', '第一条评论'), ('读者乙', '回复甲')],
                         '只有图片的评论没有文字，跳过；回复里的引用不当评论正文')
        self.assertEqual(d['comments'][1]['reply_to'], '读者甲')
        # 评论楼：楼号、被回复的楼号和原话都留下，前端用来画「回复 某人：…」
        self.assertEqual(d['comments'][0]['id'], 1)
        self.assertEqual((d['comments'][1]['id'], d['comments'][1]['reply_to_id'], d['comments'][1]['reply_text']), (2, 1, '第一条评论'))
        self.assertNotIn('reply_to', d['comments'][0])
        off = parse_discussion((FIX / 'discussion-off.html').read_text(encoding='utf-8'))
        self.assertEqual(off, {'enabled': False, 'total': None, 'comments': []})


class MergeTests(unittest.TestCase):
    def setUp(self):
        self.page = parse_page((FIX / 'page.html').read_text(encoding='utf-8'))

    def test_reply_item_shows_own_words_then_quote(self):
        db_text = '被引用的原帖原文，第一句。'   # 旧 tg.db 存成了被引用的原文
        title, rest, body, quote, tg = _tg_parts('demo', db_text, self.page[101])
        self.assertEqual((title, rest), ('频道自己的话', '这是频道对原帖的评论。'))
        self.assertIn('这是频道对原帖的评论', body)
        self.assertEqual(quote['kind'], 'reply')
        self.assertEqual(quote['text'], '被引用的原帖原文，第一句。')
        self.assertEqual(tg['views'], 20200)

    def test_forward_item_has_no_own_text(self):
        title, rest, body, quote, tg = _tg_parts('demo', '转发来的原帖全文。', self.page[102])
        self.assertEqual((rest, body), ('', ''))
        self.assertEqual(title, '转发来的原帖全文。')
        self.assertEqual(quote, {'kind': 'forward', 'source_name': '别的频道', 'url': 'https://t.me/other/555', 'text': '转发来的原帖全文。'})

    def test_no_meta_keeps_old_behaviour(self):
        self.assertEqual(_tg_parts('demo', '标题\n正文', None), ('标题', '正文', '标题\n正文', None, None))

    def test_comments_only_when_public(self):
        meta = dict(self.page[101], comments={'enabled': False, 'total': None, 'comments': []})
        self.assertNotIn('comments', merge_meta(meta)['tg'])
        meta['comments'] = parse_discussion((FIX / 'discussion.html').read_text(encoding='utf-8'))
        self.assertEqual(merge_meta(meta)['tg']['comments_total'], 12)

    def test_schema_accepts_quote_tg_and_rejects_bad(self):
        item = {'id': 'tnews365:1', 'kind': 'news', 'channel': 'current', 'source_id': 'tnews365', 'source_name': '竹新社',
                'title': 't', 'summary': '', 'url': 'https://t.me/tnews365/1', 'published_at': '2026-11-15T10:00:00+08:00',
                'lang': 'zh', 'quote': {'kind': 'forward', 'source_name': 'x', 'url': 'https://t.me/x/1', 'text': 'y'},
                'tg': {'views': 3, 'views_label': '3', 'reactions': [{'emoji': '👍', 'count': 2, 'label': '2'}],
                       'comments_total': 1, 'comments': [{'display_name': 'a', 'text': 'b'}]}}
        self.assertEqual(validate_item(item), [])
        bad = dict(item, quote={'kind': 'quote', 'text': 1}, tg={'views': -1, 'reactions': [{'emoji': '', 'count': 'x'}]})
        self.assertEqual(len(validate_item(bad)), 3)


class RefreshTests(unittest.TestCase):
    def test_pages_until_known_and_probe_discussion_once(self):
        page = (FIX / 'page.html').read_text(encoding='utf-8')
        disc = (FIX / 'discussion.html').read_text(encoding='utf-8')
        calls = []

        def get(url):
            calls.append(url)
            if 'discussion=1' in url:
                return disc
            return page if '?before=' not in url else '<html></html>'
        now = datetime(2026, 11, 15, 21, 0, tzinfo=BJ)
        store, stats = refresh(['demo'], now=now, store={'schema': 'rebang.tgmeta/1', 'channels': {}, 'messages': {}}, get=get, sleep=0)
        self.assertEqual(set(store['messages']), {'demo/101', 'demo/102', 'demo/103'})
        self.assertTrue(store['channels']['demo']['discussion'])
        self.assertEqual(store['messages']['demo/103']['comments']['total'], 12, '最新一条用来探测，同时存下它的评论')
        self.assertGreaterEqual(stats['comments_fetched'], 1)
        before = len(calls)
        store, _ = refresh(['demo'], now=now + timedelta(hours=1), store=store, get=get, sleep=0)
        self.assertFalse(any('discussion=1' in u and '/103?' in u for u in calls[before:]), '6 小时内不重抓同一条评论')

    def test_channel_error_keeps_old_data(self):
        store = {'schema': 'rebang.tgmeta/1', 'channels': {}, 'messages': {'demo/1': {'text': 'old', 'published_at': '2026-11-15T10:00:00+08:00'}}}

        def get(url):
            raise RuntimeError('boom')
        store, stats = refresh(['demo'], now=datetime(2026, 11, 15, 21, 0, tzinfo=BJ), store=store, get=get, sleep=0)
        self.assertIn('demo', stats['errors'])
        self.assertEqual(store['messages']['demo/1']['text'], 'old')


if __name__ == '__main__':
    unittest.main()


class ForwardNameTests(unittest.TestCase):
    EMPTY = ('<div class="tgme_widget_message" data-post="demo/7"><div class="tgme_widget_message_forwarded_from">Forwarded from '
             '<span class="tgme_widget_message_forwarded_from_name"><span dir="auto"></span></span> '
             '(<span class="tgme_widget_message_forwarded_from_author">作者甲</span>)</div>'
             '<div class="tgme_widget_message_text">原帖</div><time datetime="2026-11-15T10:00:00+00:00"></time></div>')

    def test_empty_name_falls_back_to_author(self):
        self.assertEqual(parse_page(self.EMPTY)[7]['forward'], {'name': '作者甲', 'url': ''})

    def test_refresh_keeps_known_name(self):
        prev = {'text': '原帖', 'published_at': '2026-11-15T10:00:00+00:00', 'forward': {'name': '别的频道', 'url': 'https://t.me/o/1'}}
        store = {'schema': 'rebang.tgmeta/1', 'channels': {}, 'messages': {'demo/7': prev}}
        get = lambda url: '<html></html>' if ('before=' in url or 'discussion' in url) else self.EMPTY
        store, _ = refresh(['demo'], now=datetime(2026, 11, 15, 21, 0, tzinfo=BJ), store=store, get=get, sleep=0)
        self.assertEqual(store['messages']['demo/7']['forward'], {'name': '别的频道', 'url': 'https://t.me/o/1'})


class DiscussionUrlTest(unittest.TestCase):
    def test_widget_url_asks_for_thread_not_default_five(self):
        from rebang.tgmeta import COMMENT_PREVIEW, discussion_url
        self.assertEqual(discussion_url('demo', 103), f'https://t.me/demo/103?embed=1&discussion=1&comments_limit={COMMENT_PREVIEW}')
        self.assertGreaterEqual(COMMENT_PREVIEW, 30)
