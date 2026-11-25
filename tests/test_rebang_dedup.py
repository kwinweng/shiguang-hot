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

    def test_bbc_at_params_only_dropped_on_bbc_hosts(self):
        n = dedup.norm_url
        self.assertEqual(n('https://feeds.bbc.com/news/x?at_format=one'), n('https://feeds.bbc.com/news/x'))
        self.assertEqual(n('https://bbc.com/news/x?at_custom1=a'), n('https://bbc.com/news/x'))
        self.assertNotEqual(n('https://a.test/p?at_format=one'), n('https://a.test/p?at_format=two'))
        self.assertNotEqual(n('https://notbbc.com/p?at_medium=x'), n('https://notbbc.com/p'))
        self.assertNotEqual(n('https://a.test/p?cmpid=1'), n('https://a.test/p?cmpid=2'))   # 不明确的不去

    def test_meaningful_params_still_differ_and_order_does_not_matter(self):
        self.assertNotEqual(dedup.norm_url('https://a.test/p?id=1'), dedup.norm_url('https://a.test/p?id=2'))
        self.assertEqual(dedup.norm_url('https://a.test/p?b=2&a=1'), dedup.norm_url('https://a.test/p?a=1&b=2&utm_x=9'))

    def test_generic_params_are_not_tracking(self):
        n = dedup.norm_url
        self.assertNotEqual(n('https://a.test/p?ref=101'), n('https://a.test/p?ref=202'))
        self.assertNotEqual(n('https://a.test/p?from=a'), n('https://a.test/p?from=b'))
        self.assertNotEqual(n('https://a.test/p?si=1'), n('https://a.test/p?si=2'))     # si 只在 YouTube 去
        self.assertEqual(n('https://youtu.be/abc?si=XYZ'), n('https://youtu.be/abc'))
        self.assertEqual(n('https://x.com/u/status/1?s=20&t=abc'), n('https://x.com/u/status/1'))
        self.assertNotEqual(n('https://a.test/p?s=20'), n('https://a.test/p'))
        self.assertEqual(n('https://a.test/p?fbclid=1&gclid=2'), n('https://a.test/p'))

    def test_repeated_params_keep_relative_order(self):
        n = dedup.norm_url
        self.assertNotEqual(n('https://a.test/p?id=1&id=2'), n('https://a.test/p?id=2&id=1'))
        self.assertEqual(n('https://a.test/p?id=1&b=3&id=2'), n('https://a.test/p?b=3&id=1&id=2'))

    def test_route_fragments_kept_plain_fragments_dropped(self):
        n = dedup.norm_url
        self.assertNotEqual(n('https://a.test/#/item/101'), n('https://a.test/#/item/202'))
        self.assertNotEqual(n('https://a.test/#!/a'), n('https://a.test/#!/b'))
        self.assertEqual(n('https://a.test/p#section-2'), n('https://a.test/p'))

    def test_path_case_and_mobile_host_stay_distinct(self):
        n = dedup.norm_url
        self.assertNotEqual(n('https://a.test/News/A'), n('https://a.test/news/a'))
        self.assertNotEqual(n('https://m.a.test/p'), n('https://a.test/p'))

    def test_tme_preview_path_and_non_http(self):
        self.assertEqual(dedup.norm_url('https://t.me/s/tnews365/1'), dedup.norm_url('https://t.me/tnews365/1'))
        self.assertEqual(dedup.norm_url(''), '')
        self.assertEqual(dedup.norm_url('tg://resolve?domain=x'), '')


class ClusterTests(unittest.TestCase):
    """边界用例清单（第 3 轮复核后改为最保守规则）：
    1. 同链接（参数不同）合并，标题无关；有实际含义的参数不同不合。
    2. 非 BBC 站点的 ?at_format=one / two 是两个地址，不合；BBC 的 at_* 照去。
    3. 完全相同的原标题（全半角、大小写、空白、末尾标点不同）跨来源 24 小时内合并。
    4. 标题只是相近（多一个表情、少一对引号、改一个词）一律不合。
    5. Gemini Hydrogen / Neon 两条英文原标题不同、机器翻译标题相同：不合（不用译文比较）。
    6. 句首型号不同（「Gemini 4 Hydrogen …」/「Gemini 4 Neon …」开头）不合。
    7. is liable / is not liable 不合；两边都有否定词、结论相反（未下调 / 没有上调）不合。
    8. 同链接后到的 Neon 条目：只有它真和组里某条同链接才进组，否则不把三条拉成一组。
    9. 短标题（含中文不到 8 个字、外文不到 4 个词）即使完全相同也不合。
    10. 发布时间相差超过 24 小时不合；按标题连起来的整组跨度也不超过 24 小时。
    11. 同来源完全相同标题不合（同链接除外）；每组每个来源最多一条（同链接优先）。
    12. 打乱输入顺序 30 次，分组结果一致。
    """

    def test_same_link_with_different_params_merges_even_with_unrelated_titles(self):
        a = item('xhqcankao', 1, '甲来源的说法', url='https://news.test/a?id=7&utm_source=x', minutes=30)
        b = item('zaihuapd', 2, '完全不同的写法', url='https://news.test/a/?id=7#top')
        self.assertEqual(groups([a, b]), [['xhqcankao:1', 'zaihuapd:2']])

    def test_same_link_with_different_meaningful_params_does_not_merge(self):
        a = item('xhqcankao', 1, '甲来源的说法', url='https://news.test/a?id=7')
        b = item('zaihuapd', 2, '完全不同的写法', url='https://news.test/a?id=8')
        self.assertEqual(len(groups([a, b])), 2)

    def test_at_params_on_non_bbc_site_do_not_merge(self):
        a = item('xhqcankao', 1, '甲来源关于某事的第一篇报道', url='https://news.test/story?at_format=one')
        b = item('zaihuapd', 2, '乙来源关于另一件事的完整报道', url='https://news.test/story?at_format=two')
        self.assertEqual(len(groups([a, b])), 2)

    def test_identical_titles_across_sources_merge_earliest_is_primary(self):
        a = item('zaihuapd', 1, 'DeepSeek 开放全家桶应用 API', minutes=10)
        b = item('xhqcankao', 2, 'ＤｅｅｐＳｅｅｋ　开放全家桶应用  api。', minutes=40)   # 全角、大小写、空白、末尾标点
        self.assertEqual(groups([a, b]), [['xhqcankao:2', 'zaihuapd:1']])

    def test_identical_english_titles_merge(self):
        a = item('bbc-world', 1, 'Mexican soldiers attacked after drug lord arrest', channel='world', lang='en')
        b = item('guardian-world', 2, 'Mexican Soldiers Attacked After Drug Lord Arrest.', channel='world', lang='en')
        self.assertEqual(len(groups([a, b])), 1)

    def test_similar_but_not_identical_titles_do_not_merge(self):
        pairs = [('🤖 DeepSeek 开放全家桶应用 API', 'DeepSeek开放“全家桶”应用API'),
                 ('腾讯控股第三季度营收2073.4亿元，预估2105.3亿元', '#腾讯 控股第三季度营收2,073.4亿元 #人民币 ，预估2,105.3亿元人民币'),
                 ('Mexican soldiers attacked in wake of drug lord arrest', 'Mexican soldiers attacked after drug lord arrest'),
                 ('腾讯第三季度营收不及预期', '拼多多第三季度营收不及预期')]
        for x, y in pairs:
            a = item('pelosi3', 1, x, channel='finance')
            b = item('FinanceNewsDaily', 2, y, channel='finance')
            self.assertEqual(len(groups([a, b])), 2, (x, y))

    def test_same_translation_different_original_does_not_merge(self):
        tr = {'title': '谷歌面向全球开发者推出新一代模型', 'summary': '', 'engine': 't', 'label': '机器翻译'}
        a = item('google-blog', 1, 'Google launches Gemini 4 Hydrogen model for developers worldwide', lang='en',
                 translated=True, translation=dict(tr))
        b = item('techcrunch', 2, 'Google launches Gemini 4 Neon model for developers worldwide', lang='en',
                 translated=True, translation=dict(tr))
        self.assertEqual(len(groups([a, b])), 2)
        en = item('google-blog', 3, 'Introducing a faster Gemini model for developers', lang='en', translated=True,
                  translation={'title': '谷歌为开发者推出更快的新模型', 'summary': '', 'engine': 't', 'label': '机器翻译'})
        zh = item('zaihuapd', 4, '谷歌为开发者推出更快的新模型')
        self.assertEqual(len(groups([en, zh])), 2)                      # 译文和中文标题一样也不合

    def test_leading_model_name_difference_does_not_merge(self):
        a = item('google-blog', 1, 'Gemini 4 Hydrogen is now available to all developers', lang='en')
        b = item('techcrunch', 2, 'Gemini 4 Neon is now available to all developers', lang='en')
        self.assertEqual(len(groups([a, b])), 2)
        c = item('zaihuapd', 3, 'Hydrogen 模型今天起向全球开发者开放')
        d = item('xhqcankao', 4, 'Neon 模型今天起向全球开发者开放')
        self.assertEqual(len(groups([c, d])), 2)

    def test_negation_differences_do_not_merge(self):
        a = item('bbc-world', 1, 'Court rules tech giant is liable for user data breach', lang='en', channel='world')
        b = item('guardian-world', 2, 'Court rules tech giant is not liable for user data breach', lang='en', channel='world')
        self.assertEqual(len(groups([a, b])), 2)
        c = item('pelosi3', 3, '央行宣布本月未下调存款准备金率', channel='finance')     # 两边都有否定、结论相反
        d = item('FinanceNewsDaily', 4, '央行宣布本月没有上调存款准备金率', channel='finance')
        self.assertEqual(len(groups([c, d])), 2)
        e = item('pelosi3', 5, 'Regulator does not approve merger, says it will not appeal', lang='en', channel='finance')
        f = item('FinanceNewsDaily', 6, 'Regulator does approve merger, says it will not appeal', lang='en', channel='finance')
        self.assertEqual(len(groups([e, f])), 2)

    def test_late_same_link_item_joins_only_by_its_real_link(self):
        a = item('xhqcankao', 1, '谷歌发布 Gemini 新一代大模型 面向全球开发者开放', url='https://a.test/1', minutes=60)
        b = item('zaihuapd', 2, '谷歌发布 Gemini 新一代大模型 面向全球开发者开放', url='https://b.test/2', minutes=30)
        c = item('OneMillion_AI', 3, '谷歌发布 Gemini Neon 新一代大模型 面向全球开发者开放', url='https://c.test/3')
        got = groups([a, b, c])
        self.assertEqual(sorted(map(len, got)), [1, 2])
        self.assertIn(['OneMillion_AI:3'], got)
        c_same = dict(c, url='https://b.test/2/?utm_source=tg')       # 真和 b 同链接：才进组
        self.assertEqual(sorted(map(len, groups([a, b, c_same]))), [3])

    def test_short_identical_titles_do_not_merge(self):
        for title, lang in (('📈 ETF 数据汇总', 'zh'), ('今日早盘快讯', 'zh'), ('Markets wrap up', 'en'), ('Breaking news', 'en')):
            a = item('pelosi3', 1, title, channel='finance', lang=lang)
            b = item('FinanceNewsDaily', 2, title, channel='finance', lang=lang)
            self.assertEqual(len(groups([a, b])), 2, title)
        a = item('pelosi3', 1, '今日早盘快讯汇总一览', channel='finance')         # 刚好 8 个字：合
        b = item('FinanceNewsDaily', 2, '今日早盘快讯汇总一览', channel='finance')
        self.assertEqual(len(groups([a, b])), 1)

    def test_outside_24_hours_does_not_merge_and_no_long_chain(self):
        title = '福特官宣正式进入电池业务 底层技术来自宁德时代'
        a = item('zaihuapd', 1, title, minutes=25 * 60)
        b = item('xhqcankao', 2, title)
        self.assertEqual(len(groups([a, b])), 2)
        a = item('zaihuapd', 1, title, minutes=40 * 60)
        m = item('OneMillion_AI', 3, title, minutes=20 * 60)
        b = item('xhqcankao', 2, title)
        got = groups([a, m, b])
        self.assertEqual(sorted(map(len, got)), [1, 2])                  # 两两相差 20 小时，但整组跨度 40 小时：只并一对

    def test_same_source_identical_titles_stay_separate(self):
        a = item('zaihuapd', 1, '谷歌拟提前向日本提供尖端 AI 模型助力网络防御', minutes=5)
        b = item('zaihuapd', 2, '谷歌拟提前向日本提供尖端 AI 模型助力网络防御')
        self.assertEqual(len(groups([a, b])), 2)

    def test_one_item_per_source_in_a_group_but_same_link_wins(self):
        title = '习近平会见美国总统特朗普 双方就经贸问题交换意见'
        a = item('pelosi3', 1, title, minutes=60, channel='finance')
        b = item('FinanceNewsDaily', 2, title, minutes=30, channel='finance')
        c = item('FinanceNewsDaily', 3, title, channel='finance')
        self.assertEqual(sorted(map(len, groups([a, b, c]))), [1, 2])
        # 同链接优先：同链接的两条照样一组（同来源也合）；这组已有 FinanceNewsDaily，
        # 就不再按标题并入另一条 FinanceNewsDaily
        d = item('FinanceNewsDaily', 4, '另一种写法', url='https://n.test/x', channel='finance', minutes=10)
        e = item('pelosi3', 5, title, url='https://n.test/x', channel='finance')
        f = item('FinanceNewsDaily', 6, title, channel='finance', minutes=20)
        got = groups([d, e, f])
        self.assertIn(['FinanceNewsDaily:4', 'pelosi3:5'], got)
        self.assertIn(['FinanceNewsDaily:6'], got)
        g = item('FinanceNewsDaily', 7, '同来源第二种写法', url='https://n.test/x', channel='finance')
        self.assertEqual(groups([d, g]), [['FinanceNewsDaily:4', 'FinanceNewsDaily:7']])

    def test_result_is_independent_of_input_order(self):
        import random
        title = '谷歌发布 Gemini 新一代大模型 面向全球开发者开放'
        pool = [item('xhqcankao', 1, title, minutes=60), item('zaihuapd', 2, title, minutes=30),
                item('zaihuapd', 3, title, minutes=20), item('OneMillion_AI', 4, title, minutes=10),
                item('OneMillion_AI', 5, '别的写法 同一个链接', url='https://a.test/s', minutes=5),
                item('tnews365', 6, '再一种写法 同一个链接', url='https://a.test/s?utm_medium=x'),
                item('tnews365', 7, title, minutes=25 * 60),
                item('freechinese', 8, '一条独立的消息，和别的都不像', minutes=15)]
        expected = groups(pool)
        rng = random.Random(20261125)
        for _ in range(30):
            shuffled = pool[:]
            rng.shuffle(shuffled)
            self.assertEqual(groups(shuffled), expected)

    def test_highlighted_member_becomes_primary(self):
        a = item('xhqcankao', 1, 'DeepSeek 开放全家桶应用 API', minutes=40)
        b = item('zaihuapd', 2, 'DeepSeek 开放全家桶应用 API', highlight=True, highlight_date='2026-11-15')
        self.assertEqual(groups([a, b]), [['zaihuapd:2', 'xhqcankao:1']])

    def test_same_raw_url_same_source_folds(self):
        a = item('zaihuapd', 1, '一条消息的第一种写法', url='https://news.test/x', minutes=5)
        b = item('zaihuapd', 2, '完全不同的另一种写法', url='https://news.test/x')
        self.assertEqual(groups([a, b]), [['zaihuapd:1', 'zaihuapd:2']])

    def test_title_key_ignores_korean_as_han(self):
        self.assertIsNone(dedup._CJK.search('삼성전자 실적 발표'))
        self.assertEqual(dedup.title_key({'title': '삼성 실적'}), '')            # 2 个词：太短
        self.assertTrue(dedup.title_key({'title': '삼성전자 3분기 실적 발표했다'}))   # 4 个词：够长

    def test_fold_returns_copies_and_does_not_mutate_input(self):
        a = item('zaihuapd', 1, 'DeepSeek 开放全家桶应用 API', minutes=10)
        b = item('xhqcankao', 2, 'DeepSeek 开放全家桶应用 API', minutes=40)
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
        items = [item('zaihuapd', 1, 'DeepSeek 开放全家桶应用 API', minutes=10),
                 item('xhqcankao', 2, 'DeepSeek 开放全家桶应用 API。', minutes=40),
                 item('xhqcankao', 3, '一条独立的消息，和别的都不像', minutes=50),
                 item('tnews365', 4, 'DeepSeek 开放全家桶应用 API', channel='current')]  # 别的频道不跨频道合并
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

    def test_same_raw_url_keeps_every_id_reachable_and_highlight_only_marks(self):
        url = 'https://news.test/same-article'
        items = [item('zaihuapd', 1, '同一篇文章甲来源的写法', url=url, minutes=10, body='甲的正文'),
                 item('xhqcankao', 2, '同一篇文章乙来源的说法', url=url, minutes=40, body='乙的正文'),
                 item('zaihuapd', 3, '同一篇文章甲来源又发一次', url=url, minutes=5),
                 item('hot-daily', 4, '今日重点', url=url, highlight=True, highlight_date='2026-11-15')]
        seen = []
        with mock.patch.object(site, '_run_archive', lambda its, out, report: seen.extend(i['id'] for i in its)):
            data, _ = self.build(items)
        self.assertEqual(sorted(seen), ['xhqcankao:2', 'zaihuapd:1', 'zaihuapd:3'])   # 搜索索引收到每个 id
        index = json.loads((data / 'id-index.json').read_text(encoding='utf-8'))
        self.assertNotIn('hot-daily:4', index)                                           # 今日重点仍只打标
        page = json.loads((data / 'channel' / 'tech-ai' / 'page-1.json').read_text(encoding='utf-8'))
        self.assertEqual([i['id'] for i in page['items']], ['zaihuapd:3'])   # 被打上今日重点标的那条当主条
        self.assertTrue(page['items'][0].get('highlight'))
        self.assertEqual({m['id'] for m in page['items'][0]['merged']}, {'zaihuapd:1', 'xhqcankao:2'})
        for ident in ('xhqcankao:2', 'zaihuapd:1', 'zaihuapd:3'):                      # 每个 id 都能按 id-index 打开
            payload = json.loads((data / index[ident]).read_text(encoding='utf-8'))
            got = [i for i in payload.get('items', []) if i['id'] == ident]
            self.assertEqual(len(got), 1, ident)
        merged = json.loads((data / 'channel' / 'tech-ai' / 'merged.json').read_text(encoding='utf-8'))
        self.assertEqual(next(i for i in merged['items'] if i['id'] == 'zaihuapd:1')['body'], '甲的正文')

    def test_primary_still_validates_as_contract_item(self):
        items = [item('zaihuapd', 1, 'DeepSeek 开放全家桶应用 API', minutes=10),
                 item('xhqcankao', 2, 'DeepSeek 开放全家桶应用 API。', minutes=40)]
        data, _ = self.build(items)
        page = json.loads((data / 'channel' / 'tech-ai' / 'page-1.json').read_text(encoding='utf-8'))
        self.assertEqual(schema.validate_item(page['items'][0], 'primary'), [])


if __name__ == '__main__':
    unittest.main()
