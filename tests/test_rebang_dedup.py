"""第 5 步：频道内跨来源去重与同类事件合并的边界用例。全部离线合成样本（标题仿照 11/23 线上快照里真实出现过的写法）。"""
import json
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path
from unittest import mock

from rebang.contract import schema
from rebang.site import builder as site
from rebang.site import dedup
from tests.rebang_site_testdata import NOW, envelope, news


def item(source, n, title, *, minutes=0, url=None, channel='tech-ai', **extra):
    it = news(source, channel, n, minutes=minutes, title=title, **extra)
    if url is not None:
        it['url'] = url
    return it


def groups(items):
    return [[m['id'] for m in g] for g in dedup.cluster(items)]


class NormUrlTests(unittest.TestCase):
    def test_tracking_params_fragment_scheme_www_and_trailing_slash_are_ignored(self):
        base = dedup.norm_url('https://www.bbc.co.uk/news/articles/c5rm')
        for variant in ('http://www.bbc.co.uk/news/articles/c5rm?at_medium=RSS&at_campaign=rss',
                        'https://bbc.co.uk/news/articles/c5rm/#0',
                        'https://www.bbc.co.uk/news/articles/c5rm?utm_source=tg&utm_medium=social'):
            self.assertEqual(dedup.norm_url(variant), base, variant)

    def test_meaningful_params_still_differ_and_order_does_not_matter(self):
        self.assertNotEqual(dedup.norm_url('https://a.test/p?id=1'), dedup.norm_url('https://a.test/p?id=2'))
        self.assertEqual(dedup.norm_url('https://a.test/p?b=2&a=1'), dedup.norm_url('https://a.test/p?a=1&b=2&utm_x=9'))

    def test_tme_preview_path_and_non_http(self):
        self.assertEqual(dedup.norm_url('https://t.me/s/tnews365/1'), dedup.norm_url('https://t.me/tnews365/1'))
        self.assertEqual(dedup.norm_url(''), '')
        self.assertEqual(dedup.norm_url('tg://resolve?domain=x'), '')


class ClusterTests(unittest.TestCase):
    def test_same_link_with_different_params_merges_even_with_unrelated_titles(self):
        a = item('xhqcankao', 1, '甲来源的说法', url='https://news.test/a?id=7&utm_source=x', minutes=30)
        b = item('zaihuapd', 2, '完全不同的写法', url='https://news.test/a/?id=7#top')
        self.assertEqual(groups([a, b]), [['xhqcankao:1', 'zaihuapd:2']])

    def test_same_link_with_different_meaningful_params_does_not_merge(self):
        a = item('xhqcankao', 1, '甲来源的说法', url='https://news.test/a?id=7')
        b = item('zaihuapd', 2, '完全不同的写法', url='https://news.test/a?id=8')
        self.assertEqual(len(groups([a, b])), 2)

    def test_slightly_different_titles_across_sources_merge_earliest_is_primary(self):
        a = item('zaihuapd', 1, '🤖 DeepSeek 开放全家桶应用 API', minutes=10)
        b = item('xhqcankao', 2, 'DeepSeek开放“全家桶”应用API', minutes=40)
        self.assertEqual(groups([a, b]), [['xhqcankao:2', 'zaihuapd:1']])

    def test_numbers_formatted_differently_still_merge(self):
        a = item('pelosi3', 1, '腾讯控股第三季度营收2073.4亿元，预估2105.3亿元', channel='finance')
        b = item('FinanceNewsDaily', 2, '#腾讯 控股第三季度营收2,073.4亿元 #人民币 ，预估2,105.3亿元人民币', channel='finance')
        self.assertEqual(len(groups([a, b])), 1)

    def test_shared_words_with_conflicting_numbers_do_not_merge(self):
        a = item('pelosi3', 1, '腾讯控股第三季度营收2073.4亿元，预估2105.3亿元', channel='finance')
        b = item('FinanceNewsDaily', 2, '#腾讯 控股第三季度资本支出814.3亿元 #人民币 ，预估554亿元人民币', channel='finance')
        self.assertEqual(len(groups([a, b])), 2)

    def test_shared_words_with_conflicting_product_names_do_not_merge(self):
        a = item('zaihuapd', 1, '🤖 谷歌发布 Gemini 4 Hydrogen 模型')
        b = item('xhqcankao', 2, '谷歌发布 Gemini 4 Neon 模型')
        self.assertEqual(len(groups([a, b])), 2)

    def test_same_template_different_company_does_not_merge(self):
        a = item('pelosi3', 1, '腾讯第三季度营收不及预期', channel='finance')
        b = item('FinanceNewsDaily', 2, '拼多多第三季度营收不及预期', channel='finance')
        self.assertEqual(len(groups([a, b])), 2)

    def test_short_titles_are_never_merged_by_title(self):
        a = item('pelosi3', 1, '📈 ETF 数据汇总', channel='finance')
        b = item('FinanceNewsDaily', 2, 'ETF 数据汇总', channel='finance')
        self.assertEqual(len(groups([a, b])), 2)

    def test_same_source_near_duplicates_stay_separate(self):
        a = item('zaihuapd', 1, '谷歌有意提前向日本提供尖端AI模型助力网络防御', minutes=5)
        b = item('zaihuapd', 2, '谷歌拟提前向日本提供尖端 AI 模型助力网络防御')
        self.assertEqual(len(groups([a, b])), 2)

    def test_one_item_per_source_in_a_group(self):
        a = item('pelosi3', 1, '习近平会见美国总统特朗普', minutes=60, channel='finance')
        b = item('FinanceNewsDaily', 2, '#习近平 会见 #美国 总统 #特朗普', minutes=30, channel='finance')
        c = item('FinanceNewsDaily', 3, '#习近平 会见 #美国 总统 #特朗普 。', channel='finance')
        got = groups([a, b, c])
        self.assertEqual(sorted(map(len, got)), [1, 2])

    def test_outside_24_hours_does_not_merge(self):
        a = item('zaihuapd', 1, '福特官宣正式进入电池业务 底层技术来自宁德时代', minutes=25 * 60)
        b = item('xhqcankao', 2, '福特进入电池业务 底层技术来自宁德时代')
        self.assertEqual(len(groups([a, b])), 2)

    def test_english_titles_need_higher_overlap(self):
        a = item('bbc-world', 1, 'Mexican soldiers attacked in wake of drug lord arrest', channel='world')
        b = item('guardian-world', 2, 'Mexican soldiers attacked after drug lord arrest', channel='world')
        c = item('guardian-world', 3, 'Mexican president defends drug lord arrest strategy', channel='world')
        self.assertEqual(len(groups([a, b])), 1)
        self.assertEqual(len(groups([a, c])), 2)

    def test_machine_translated_title_matches_chinese_title(self):
        en = item('google-blog', 1, 'Introducing a faster Gemini model for developers', lang='en', translated=True,
                  translation={'title': '谷歌为开发者推出更快的新模型', 'summary': '', 'engine': 't', 'label': '机器翻译'})
        zh = item('zaihuapd', 2, '谷歌为开发者推出更快的新模型')
        self.assertEqual(len(groups([en, zh])), 1)

    def test_english_title_without_translation_never_matches_chinese(self):
        en = item('google-blog', 1, 'Introducing Gemini 4 Neon', lang='en')
        zh = item('zaihuapd', 2, '谷歌发布 Gemini 4 Neon 模型')
        self.assertEqual(len(groups([en, zh])), 2)

    def test_highlighted_member_becomes_primary(self):
        a = item('xhqcankao', 1, 'DeepSeek开放“全家桶”应用API', minutes=40)
        b = item('zaihuapd', 2, '🤖 DeepSeek 开放全家桶应用 API', highlight=True, highlight_date='2026-11-15')
        self.assertEqual(groups([a, b]), [['zaihuapd:2', 'xhqcankao:1']])

    def test_no_chaining_through_a_middle_item(self):
        a = item('xhqcankao', 1, '英伟达董事会准备罢免CEO黄仁勋', minutes=120)
        b = item('zaihuapd', 2, '英伟达董事会准备罢免黄仁勋 另有女高管涉事', minutes=60)
        c = item('OneMillion_AI', 3, '另有女高管涉事 英伟达股价盘后下跌')
        for g in dedup.cluster([a, b, c]):
            ids = {m['id'] for m in g}
            self.assertFalse({'xhqcankao:1', 'OneMillion_AI:3'} <= ids)

    def test_fold_returns_copies_and_does_not_mutate_input(self):
        a = item('zaihuapd', 1, '🤖 DeepSeek 开放全家桶应用 API', minutes=10)
        b = item('xhqcankao', 2, 'DeepSeek开放“全家桶”应用API', minutes=40)
        shown, folded = dedup.fold([a, b])
        self.assertEqual([i['id'] for i in shown], ['xhqcankao:2'])
        self.assertEqual([i['id'] for i in folded], ['zaihuapd:1'])
        self.assertEqual(shown[0]['merged'][0]['id'], 'zaihuapd:1')
        self.assertEqual(set(shown[0]['merged'][0]), {'id', 'source_id', 'source_name', 'title', 'url', 'published_at'})
        self.assertNotIn('merged', b)
        unique = [item('zaihuapd', 9, '一条独立的消息，和别的都不像')]
        self.assertEqual(dedup.fold(unique), (unique, []))


class SiteFoldTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)
        (self.dir / 'in').mkdir()
        patcher = mock.patch.object(site, '_run_archive', lambda items, out, report: report.update(archive='test-skip'))
        patcher.start()
        self.addCleanup(patcher.stop)

    def build(self, items):
        (self.dir / 'in' / 'ingest.json').write_text(json.dumps(envelope(items), ensure_ascii=False), encoding='utf-8')
        out = self.dir / 'site'
        report = site.build(out, self.dir / 'in', now=NOW, hot_archive_dir=self.dir / 'hot')
        return out / 'data', report

    def test_build_writes_primary_with_merged_refs_and_keeps_folded_items_reachable(self):
        items = [item('zaihuapd', 1, '🤖 DeepSeek 开放全家桶应用 API', minutes=10),
                 item('xhqcankao', 2, 'DeepSeek开放“全家桶”应用API', minutes=40),
                 item('xhqcankao', 3, '一条独立的消息，和别的都不像', minutes=50),
                 item('tnews365', 4, '🤖 DeepSeek 开放全家桶应用 API', channel='current')]  # 别的频道不跨频道合并
        data, report = self.build(items)
        page = json.loads((data / 'channel' / 'tech-ai' / 'page-1.json').read_text(encoding='utf-8'))
        self.assertEqual([i['id'] for i in page['items']], ['xhqcankao:2', 'xhqcankao:3'])
        self.assertEqual([m['id'] for m in page['items'][0]['merged']], ['zaihuapd:1'])
        self.assertNotIn('merged', page['items'][1])
        merged = json.loads((data / 'channel' / 'tech-ai' / 'merged.json').read_text(encoding='utf-8'))
        self.assertEqual(merged['schema'], 'rebang.merged/1')
        self.assertEqual([i['id'] for i in merged['items']], ['zaihuapd:1'])
        self.assertEqual(schema.validate_item(merged['items'][0], 'merged'), [])
        index = json.loads((data / 'id-index.json').read_text(encoding='utf-8'))
        self.assertEqual(index['zaihuapd:1'], 'channel/tech-ai/merged.json')
        self.assertEqual(index['xhqcankao:2'], 'channel/tech-ai/page-1.json')
        self.assertEqual(index['tnews365:4'], 'channel/current/page-1.json')
        self.assertFalse((data / 'channel' / 'current' / 'merged.json').exists())
        meta = json.loads((data / 'meta.json').read_text(encoding='utf-8'))
        tech = next(c for c in meta['channels'] if c['slug'] == 'tech-ai')
        self.assertEqual((tech['total'], tech['feed_total'], tech['merged_total']), (2, 2, 1))
        self.assertEqual(meta['counts']['news'], 4)        # 总条数不因折叠变少
        self.assertEqual(report['channels']['tech-ai']['merged'], 1)

    def test_primary_still_validates_as_contract_item(self):
        items = [item('zaihuapd', 1, '🤖 DeepSeek 开放全家桶应用 API', minutes=10),
                 item('xhqcankao', 2, 'DeepSeek开放“全家桶”应用API', minutes=40)]
        data, _ = self.build(items)
        page = json.loads((data / 'channel' / 'tech-ai' / 'page-1.json').read_text(encoding='utf-8'))
        self.assertEqual(schema.validate_item(page['items'][0], 'primary'), [])


if __name__ == '__main__':
    unittest.main()
