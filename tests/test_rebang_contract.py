"""数据契约自检（集成分支 feat/rebang-v1 所有）。"""
import copy
import json
import unittest
from pathlib import Path

from rebang.contract import (channel_slugs, load_bloggers, load_channels, load_hotsearch, source_channel,
                             validate_hotsearch, validate_item, validate_items_envelope)

ROOT = Path(__file__).resolve().parents[1]
FIX = ROOT / 'tests/fixtures/rebang/contract'


def fixture(name):
    return json.loads((FIX / name).read_text(encoding='utf-8'))


class ChannelConfigTests(unittest.TestCase):
    def test_six_channels_in_confirmed_order(self):
        self.assertEqual(channel_slugs(), ['current', 'world', 'finance', 'tech-ai', 'digital', 'tools'])
        names = [c['name'] for c in sorted(load_channels()['channels'], key=lambda c: c['order'])]
        self.assertEqual(names, ['时事', '环球', '财经', '科技与 AI', '数码', '工具与项目'])

    def test_each_source_in_exactly_one_channel(self):
        ids = [s['id'] for c in load_channels()['channels'] for s in c['sources']]
        self.assertEqual(len(ids), len(set(ids)))

    def test_eighteen_telegram_channels_all_known_to_existing_ingest(self):
        tg = [s['id'] for c in load_channels()['channels'] for s in c['sources'] if s['type'] == 'telegram']
        self.assertEqual(len(tg), 18)
        existing = {s['id'] for s in json.loads((ROOT / 'sources.json').read_text(encoding='utf-8'))['sources']
                    if s['type'] == 'telegram'}
        self.assertFalse(set(tg) - existing, '新 TG 源必须先在 sources.json 存在')
        self.assertNotIn('reorx_share', tg)

    def test_inbox_sources_exist(self):
        existing = {s['id'] for s in json.loads((ROOT / 'sources.json').read_text(encoding='utf-8'))['sources']}
        inbox = [s['id'] for c in load_channels()['channels'] for s in c['sources'] if s['type'] == 'inbox']
        self.assertFalse(set(inbox) - existing)
        self.assertIn(load_channels()['highlights']['source_id'], existing)

    def test_no_channel_embeds_hotsearch_and_curated_inbox_left_channels(self):
        # 2026-11-15 21:26：热搜去底栏「热搜」页；推特爆款/环球要闻/GitHub 热门进博主页 Grok bot
        self.assertEqual([c['slug'] for c in load_channels()['channels'] if c.get('hotsearch')], [])
        self.assertEqual(load_hotsearch()['view'], 'hot')
        for sid in ('x', 'world', 'github', 'hot-daily'):
            self.assertIsNone(source_channel(sid))
        self.assertEqual(load_hotsearch()['max_items_per_provider'], 51)
        self.assertNotIn('尚未最终确认', load_hotsearch()['note'])

    def test_current_and_world_sources_20261117(self):
        # 2026-11-17：FREE 中文、双语新闻从环球调进时事；环球只留 BBC 与卫报
        channels = {c['slug']: [s['id'] for s in c['sources']] for c in load_channels()['channels']}
        self.assertEqual(channels['current'],
                         ['tnews365', 'myBigCharacterPoster', 'freechinese', 'shuangyunews_rss'])
        self.assertEqual(channels['world'], ['bbc-world', 'guardian-world'])
        self.assertEqual(source_channel('freechinese'), 'current')
        self.assertEqual(source_channel('shuangyunews_rss'), 'current')

    def test_apple_in_digital(self):
        self.assertEqual(source_channel('apple-newsroom'), 'digital')
        self.assertIsNone(source_channel('reorx_share'))


class HotsearchConfigTests(unittest.TestCase):
    def test_phase1_providers_no_weibo(self):
        ids = [p['id'] for p in load_hotsearch()['providers'] if p['enabled']]
        self.assertEqual(ids, ['baidu', 'zhihu', 'bilibili'])

    def test_fixture_valid(self):
        self.assertEqual(validate_hotsearch(fixture('hotsearch-valid.json')), [])

    def test_failed_provider_must_be_empty(self):
        bad = fixture('hotsearch-valid.json')
        bad['providers'][1]['items'] = copy.deepcopy(bad['providers'][0]['items'])
        self.assertTrue(validate_hotsearch(bad))

    def test_ok_needs_items(self):
        bad = fixture('hotsearch-valid.json')
        bad['providers'][0]['items'] = []
        self.assertTrue(validate_hotsearch(bad))


class BloggerConfigTests(unittest.TestCase):
    def test_counts(self):
        counts = {p['id']: len(p['accounts']) for p in load_bloggers()['platforms']}
        self.assertEqual(counts, {'x': 16, 'grok': 4, 'blog': 7, 'jike': 9, 'weibo': 6, 'wechat': 6, 'youtube': 13, 'zhihu': 0})


class ItemTests(unittest.TestCase):
    def test_fixture_valid(self):
        self.assertEqual(validate_items_envelope(fixture('items-valid.json')), [])

    def _item(self, index=0):
        return copy.deepcopy(fixture('items-valid.json')['items'][index])

    def test_source_cannot_move_channel(self):
        item = self._item()
        item['channel'] = 'world'
        self.assertTrue(any('只能进' in e for e in validate_item(item)))

    def test_naive_time_rejected(self):
        item = self._item()
        item['published_at'] = '2026-11-15T19:00:00'
        self.assertTrue(validate_item(item))

    def test_translated_needs_label(self):
        item = self._item(1)
        item['translation']['label'] = ''
        self.assertTrue(validate_item(item))

    def test_chinese_not_translated(self):
        item = self._item()
        item.update(translated=True, translation={'title': 'a', 'summary': 'b', 'engine': 'e', 'label': '机器翻译'})
        self.assertTrue(validate_item(item))

    def test_post_has_no_channel_and_needs_blogger(self):
        item = self._item(3)
        item['channel'] = 'current'
        self.assertTrue(validate_item(item))
        item = self._item(3)
        del item['blogger']
        self.assertTrue(validate_item(item))

    def test_unknown_metric_rejected(self):
        item = self._item(3)
        item['blogger']['metrics']['fans'] = 1
        self.assertTrue(validate_item(item))

    def test_javascript_url_rejected(self):
        item = self._item()
        item['url'] = 'javascript:alert(1)'
        self.assertTrue(validate_item(item))

    def test_duplicate_id_rejected(self):
        env = fixture('items-valid.json')
        env['items'].append(copy.deepcopy(env['items'][0]))
        self.assertTrue(validate_items_envelope(env))


if __name__ == '__main__':
    unittest.main()


class IntegrationContractTests(unittest.TestCase):
    """集成阶段并入的契约变更（INTEGRATION-NOTES 各分支请求）。"""

    def base_post(self):
        return {'id': 'x:1', 'kind': 'post', 'channel': None, 'source_id': 'x', 'source_name': '推特爆款',
                'title': 't', 'summary': '', 'url': '', 'published_at': '2026-11-15T08:00:00+08:00', 'lang': 'und',
                'blogger': {'platform': 'grok', 'handle': 'x', 'display_name': '推特爆款', 'media': []}}

    def test_grok_platform_post_and_lang_und_valid(self):
        self.assertEqual(validate_item(self.base_post()), [])
        self.assertEqual([a['name'] for a in next(p for p in load_bloggers()['platforms'] if p['id'] == 'grok')['accounts']],
                         ['今日重点', '推特爆款', '环球要闻', 'GitHub 热门'])

    def test_image_local_and_comments_and_quote_extras(self):
        item = self.base_post()
        item['image_local'] = {'path': '/x/a.webp', 'rel': 'media/a.webp', 'width': 640, 'height': 360, 'alt': ''}
        item['blogger']['comments'] = [{'handle': 'a', 'text': 'hi', 'display_name': 'A'}]
        item['blogger']['quote'] = {'handle': 'b', 'text': 'q', 'display_name': 'B', 'url': 'https://x.com/b/1'}
        self.assertEqual(validate_item(item), [])
        item['image_local']['rel'] = '../etc/passwd'
        self.assertTrue(validate_item(item))
        item['image_local'] = {'path': '/x/a.webp'}
        item['blogger']['comments'] = [{'text': 'no handle'}]
        self.assertTrue(validate_item(item))

    def test_envelope_sources_and_platforms(self):
        env = {'schema': 'rebang.items/1', 'producer': 'ingest', 'generated_at': '2026-11-15T08:00:00+08:00',
               'items': [self.base_post()], 'sources': [{'id': 'bbc-world', 'status': 'ok', 'count': 1}],
               'platforms': [{'id': 'x', 'status': 'ok'}]}
        self.assertEqual(validate_items_envelope(env), [])
        env['sources'] = [{'id': 'bbc-world'}]
        self.assertTrue(validate_items_envelope(env))
