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
    """边界用例清单（2026-11-25 第 3 轮复核到上限后改为唯一一条规则：同链接且原标题相同）：
    1. 同链接（追踪参数、http/https、尾 / 不同照算同链接）且原标题相同、不同来源、24 小时内：合并。
    2. 滚动新闻共用一个链接、标题相反（「上调」/「下调」）：不合。
    3. 仅标题相同、链接不同：不合（A、B 同题不同链接；同名「实时汇总」不同链接）。
    4. 同链接、只差大小写（100 mW / 100 MW）：不合。
    5. 同链接、只差标点（？/。）或全半角：不合。
    6. 同链接、只差首尾空白或连续空白：照合。
    7. 同链接同标题但同一来源：不合（每组每个来源最多一条）。
    8. 发布时间相差超过 24 小时不合；整组最早最晚也不超过 24 小时（0/20/40 小时三条只并一对）。
    9. 有实际含义的参数不同、非 http 链接、没有链接：不合。
    10. 打乱输入顺序 30 次，分组结果一致。
    11. 组里有今日重点标的当主条，否则最早发的。
    """

    def test_same_link_and_same_title_across_sources_merge(self):
        title = 'DeepSeek 开放全家桶应用 API'
        a = item('xhqcankao', 1, title, url='https://news.test/a?id=7&utm_source=x', minutes=30)
        b = item('zaihuapd', 2, title, url='http://www.news.test/a/?id=7#top')
        self.assertEqual(groups([a, b]), [['xhqcankao:1', 'zaihuapd:2']])

    def test_rolling_live_link_with_opposite_titles_does_not_merge(self):
        live = 'https://live.test/finance/rolling'
        a = item('pelosi3', 1, '央行宣布上调存款准备金率 0.25 个百分点', url=live, channel='finance', minutes=10)
        b = item('FinanceNewsDaily', 2, '央行宣布下调存款准备金率 0.25 个百分点', url=live, channel='finance')
        self.assertEqual(len(groups([a, b])), 2)

    def test_same_title_different_link_does_not_merge(self):
        a = item('pelosi3', 1, '央行宣布下调存款准备金率 0.25 个百分点', url='https://a.test/1', channel='finance')
        b = item('FinanceNewsDaily', 2, '央行宣布下调存款准备金率 0.25 个百分点', url='https://b.test/2', channel='finance')
        self.assertEqual(len(groups([a, b])), 2)
        c = item('pelosi3', 3, '美股盘前实时汇总', url='https://a.test/live/1123', channel='finance')
        d = item('FinanceNewsDaily', 4, '美股盘前实时汇总', url='https://b.test/live/1124', channel='finance')
        self.assertEqual(len(groups([c, d])), 2)

    def test_case_difference_does_not_merge(self):
        url = 'https://news.test/laser'
        a = item('google-blog', 1, 'New laser hits 100 mW output', url=url, lang='en')
        b = item('techcrunch', 2, 'New laser hits 100 MW output', url=url, lang='en')
        self.assertEqual(len(groups([a, b])), 2)

    def test_punctuation_or_width_difference_does_not_merge(self):
        url = 'https://news.test/q'
        for x, y in (('苹果会推出折叠屏 iPhone 吗？', '苹果会推出折叠屏 iPhone 吗。'),
                     ('DeepSeek 开放全家桶应用 API', 'ＤｅｅｐＳｅｅｋ 开放全家桶应用 API'),
                     ('DeepSeek 开放全家桶应用 API', 'DeepSeek 开放全家桶应用 API。')):
            a = item('zaihuapd', 1, x, url=url)
            b = item('xhqcankao', 2, y, url=url)
            self.assertEqual(len(groups([a, b])), 2, (x, y))

    def test_surrounding_and_repeated_whitespace_is_ignored(self):
        url = 'https://news.test/ws'
        a = item('zaihuapd', 1, '  DeepSeek   开放全家桶应用\tAPI ', url=url, minutes=5)
        b = item('xhqcankao', 2, 'DeepSeek 开放全家桶应用 API', url=url)
        self.assertEqual(groups([a, b]), [['zaihuapd:1', 'xhqcankao:2']])

    def test_same_source_same_link_same_title_does_not_merge(self):
        url = 'https://news.test/x'
        a = item('zaihuapd', 1, '谷歌拟提前向日本提供尖端 AI 模型', url=url, minutes=5)
        b = item('zaihuapd', 2, '谷歌拟提前向日本提供尖端 AI 模型', url=url)
        self.assertEqual(len(groups([a, b])), 2)
        c = item('xhqcankao', 3, '谷歌拟提前向日本提供尖端 AI 模型', url=url, minutes=1)   # 另一来源：只和其中一条并
        got = groups([a, b, c])
        self.assertEqual(sorted(map(len, got)), [1, 2])
        self.assertIn(['zaihuapd:1', 'xhqcankao:3'], got)                # 最早那条先成组

    def test_outside_24_hours_does_not_merge_and_group_span_is_bounded(self):
        url, title = 'https://news.test/ford', '福特官宣正式进入电池业务'
        a = item('zaihuapd', 1, title, url=url, minutes=25 * 60)
        b = item('xhqcankao', 2, title, url=url)
        self.assertEqual(len(groups([a, b])), 2)
        a = item('zaihuapd', 1, title, url=url, minutes=40 * 60)
        m = item('OneMillion_AI', 3, title, url=url, minutes=20 * 60)
        b = item('xhqcankao', 2, title, url=url)
        self.assertEqual(sorted(map(len, groups([a, m, b]))), [1, 2])   # 两两相差 20 小时，整组会到 40 小时：只并一对

    def test_unusable_or_different_links_do_not_merge(self):
        t = '一条消息的同一种写法'
        for ua, ub in (('https://news.test/a?id=7', 'https://news.test/a?id=8'),
                       ('https://news.test/s?at_format=one', 'https://news.test/s?at_format=two'),
                       ('tg://resolve?domain=x', 'tg://resolve?domain=x'),
                       ('', '')):
            a = item('xhqcankao', 1, t, url=ua)
            b = item('zaihuapd', 2, t, url=ub)
            self.assertEqual(len(groups([a, b])), 2, (ua, ub))

    def test_result_is_independent_of_input_order(self):
        import random
        url, title = 'https://a.test/s', '谷歌发布 Gemini 新一代大模型'
        pool = [item('xhqcankao', 1, title, url=url, minutes=60), item('zaihuapd', 2, title, url=url, minutes=30),
                item('zaihuapd', 3, title, url=url + '?utm_medium=x', minutes=20),
                item('OneMillion_AI', 4, title, url=url, minutes=10),
                item('tnews365', 5, title, url=url, minutes=26 * 60),       # 和别的都差 24 小时以上
                item('tnews365', 6, title, url=url, minutes=5),
                item('freechinese', 7, title, url='https://b.test/other', minutes=15),
                item('freechinese', 8, title + '？', url=url, minutes=12)]
        expected = groups(pool)
        self.assertEqual(sorted(map(len, expected)), [1, 1, 1, 1, 4])     # zaihuapd:3 和 zaihuapd:2 同来源，单独一组
        rng = random.Random(20261125)
        for _ in range(30):
            shuffled = pool[:]
            rng.shuffle(shuffled)
            self.assertEqual(groups(shuffled), expected)

    def test_highlighted_member_becomes_primary(self):
        url = 'https://news.test/hl'
        a = item('xhqcankao', 1, 'DeepSeek 开放全家桶应用 API', url=url, minutes=40)
        b = item('zaihuapd', 2, 'DeepSeek 开放全家桶应用 API', url=url, highlight=True, highlight_date='2026-11-15')
        self.assertEqual(groups([a, b]), [['zaihuapd:2', 'xhqcankao:1']])

    def test_fold_returns_copies_and_does_not_mutate_input(self):
        url = 'https://news.test/fold'
        a = item('zaihuapd', 1, 'DeepSeek 开放全家桶应用 API', url=url, minutes=10)
        b = item('xhqcankao', 2, 'DeepSeek 开放全家桶应用 API', url=url, minutes=40)
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
        url = 'https://news.test/deepseek'
        items = [item('zaihuapd', 1, 'DeepSeek 开放全家桶应用 API', url=url, minutes=10),
                 item('xhqcankao', 2, 'DeepSeek 开放全家桶应用 API', url=url, minutes=40),
                 item('xhqcankao', 3, '一条独立的消息，和别的都不像', minutes=50),
                 item('tnews365', 4, 'DeepSeek 开放全家桶应用 API', url=url, channel='current')]  # 别的频道不跨频道合并
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
        items = [item('zaihuapd', 1, '同一篇文章的原标题', url=url, minutes=10, body='甲的正文'),
                 item('xhqcankao', 2, '同一篇文章的原标题', url=url, minutes=40, body='乙的正文'),
                 item('zaihuapd', 3, '同一个链接换了标题再发一次', url=url, minutes=5),
                 item('hot-daily', 4, '今日重点', url=url, highlight=True, highlight_date='2026-11-15')]
        seen = []
        with mock.patch.object(site, '_run_archive', lambda its, out, report: seen.extend(i['id'] for i in its)):
            data, _ = self.build(items)
        self.assertEqual(sorted(seen), ['xhqcankao:2', 'zaihuapd:1', 'zaihuapd:3'])   # 搜索索引收到每个 id
        index = json.loads((data / 'id-index.json').read_text(encoding='utf-8'))
        self.assertNotIn('hot-daily:4', index)                                           # 今日重点仍只打标
        page = json.loads((data / 'channel' / 'tech-ai' / 'page-1.json').read_text(encoding='utf-8'))
        # 同链接不同标题不合；同链接同标题的两条合成一组，最早那条（xhqcankao:2）当主条
        self.assertEqual([i['id'] for i in page['items']], ['zaihuapd:3', 'xhqcankao:2'])
        self.assertTrue(page['items'][0].get('highlight'))               # 今日重点标打在最新那条上
        self.assertNotIn('merged', page['items'][0])
        self.assertEqual([m['id'] for m in page['items'][1]['merged']], ['zaihuapd:1'])
        for ident in ('xhqcankao:2', 'zaihuapd:1', 'zaihuapd:3'):                      # 每个 id 都能按 id-index 打开
            payload = json.loads((data / index[ident]).read_text(encoding='utf-8'))
            got = [i for i in payload.get('items', []) if i['id'] == ident]
            self.assertEqual(len(got), 1, ident)
        merged = json.loads((data / 'channel' / 'tech-ai' / 'merged.json').read_text(encoding='utf-8'))
        self.assertEqual(next(i for i in merged['items'] if i['id'] == 'zaihuapd:1')['body'], '甲的正文')

    def test_primary_still_validates_as_contract_item(self):
        url = 'https://news.test/deepseek'
        items = [item('zaihuapd', 1, 'DeepSeek 开放全家桶应用 API', url=url, minutes=10),
                 item('xhqcankao', 2, 'DeepSeek 开放全家桶应用 API', url=url, minutes=40)]
        data, _ = self.build(items)
        page = json.loads((data / 'channel' / 'tech-ai' / 'page-1.json').read_text(encoding='utf-8'))
        self.assertEqual(schema.validate_item(page['items'][0], 'primary'), [])


if __name__ == '__main__':
    unittest.main()
