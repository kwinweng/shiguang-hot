"""frontend-v11：构建器单测（分页、banner 选图、本地图、来源状态、深链索引、功能挂载、归档调用）。不联网。"""
import json
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

from rebang.contract import schema
from rebang.site import builder as site
from tests.rebang_site_testdata import NOW, envelope, hotsearch, img, news, site_items

ROOT = Path(__file__).resolve().parents[1]


class SiteBuildTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)
        self.inp = self.dir / 'in'
        self.inp.mkdir()
        # 不让单测去真的调 history 分支的归档（写仓库 var/），归档调用单独测
        patcher = mock.patch.object(site, '_run_archive', lambda items, out, report: report.update(archive='test-skip'))
        patcher.start()
        self.addCleanup(patcher.stop)

    def write(self, name, data):
        (self.inp / name).write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')

    def build(self, **kw):
        out = self.dir / 'site'
        kw.setdefault('hot_archive_dir', self.dir / 'hot-archive')  # 不写仓库 var/
        report = site.build(out, self.inp, now=NOW, **kw)
        return out, report

    def read(self, out, rel):
        return json.loads((out / 'data' / rel).read_text(encoding='utf-8'))

    def test_pagination_30_per_page_and_last_page_has_no_more(self):
        pages = site.paginate(list(range(65)))
        self.assertEqual([len(p['items']) for p in pages], [30, 30, 5])
        self.assertEqual([p['has_more'] for p in pages], [True, True, False])
        self.assertEqual({p['pages'] for p in pages}, {3})
        empty = site.paginate([])
        self.assertEqual(len(empty), 1)
        self.assertEqual(empty[0]['items'], [])
        self.assertFalse(empty[0]['has_more'])

    def test_banner_picks_at_most_five_good_unique_recent_images(self):
        items = [news('tnews365', 'current', n, minutes=n, image=img(n)) for n in range(7)]
        items[1]['image'] = img(0)                     # 同图不重复
        items[2]['image'] = img(2, 200, 100)           # 短边 < 240
        items[3]['image'] = img(3, 3000, 1000)         # 比例 3.0 > 2.4
        items[4]['image'] = {'url': 'https://img.test/nodim.png'}  # 宽高未知不进 banner
        picked = site.select_banners(items)
        self.assertEqual([i['id'] for i in picked], ['tnews365:0', 'tnews365:5', 'tnews365:6'])
        many = [news('tnews365', 'current', n, minutes=n, image=img(n)) for n in range(9)]
        self.assertEqual(len(site.select_banners(many)), 5)
        old = [news('tnews365', 'current', 0, image=None), news('tnews365', 'current', 1, minutes=60 * 40, image=img(1))]
        self.assertEqual(site.select_banners(old), [], '超出「当天最新」窗口的旧图不进 banner')

    def test_fixture_fallback_when_input_dir_empty(self):
        out, report = self.build()
        self.assertTrue(report['fallback_fixture'])
        meta = self.read(out, 'meta.json')
        self.assertTrue(meta['fixture'])
        self.assertEqual([c['slug'] for c in meta['channels']], schema.channel_slugs())
        self.assertTrue((out / 'index.html').exists() and (out / 'app.js').exists() and (out / 'lib.js').exists())

    def test_brand_icons_copied_and_head_tags_present(self):
        out, _ = self.build()
        html = (out / 'index.html').read_text(encoding='utf-8')
        self.assertIn('noindex,nofollow', html)
        self.assertIn('favicon-32x32.png', html)
        self.assertIn('apple-touch-icon.png', html)
        self.assertIn('manifest.webmanifest', html)
        self.assertIn('<title>拾光资讯</title>', html)
        self.assertIn('<meta property="og:site_name" content="拾光资讯">', html)
        self.assertIn('https://news.kwinweng.com/og-image.png', html)
        self.assertNotIn('class="brand-logo"', html)
        self.assertNotIn('src="logo.png"', html)
        for name in ('favicon.ico', 'favicon-16x16.png', 'favicon-32x32.png', 'apple-touch-icon.png',
                     'icon-192.png', 'icon-512.png', 'icon-192-maskable.png', 'icon-512-maskable.png',
                     'logo.png', 'og-image.png', 'manifest.webmanifest',
                     'apple-splash-1170x2532.png', 'apple-splash-1179x2556.png', 'apple-splash-1290x2796.png'):
            self.assertTrue((out / name).is_file(), name)
        from PIL import Image
        self.assertEqual(Image.open(out / 'favicon-32x32.png').size, (32, 32))
        self.assertEqual(Image.open(out / 'apple-touch-icon.png').size, (180, 180))
        self.assertEqual(Image.open(out / 'icon-192.png').size, (192, 192))
        self.assertEqual(Image.open(out / 'icon-512.png').size, (512, 512))
        self.assertEqual(Image.open(out / 'og-image.png').size, (1200, 630))
        manifest = json.loads((out / 'manifest.webmanifest').read_text(encoding='utf-8'))
        self.assertEqual(manifest['name'], '拾光资讯')
        self.assertEqual(manifest['short_name'], '拾光资讯')
        purposes = {(icon['src'], icon['purpose']) for icon in manifest['icons']}
        self.assertEqual(purposes, {('icon-192.png', 'any'), ('icon-512.png', 'any'),
                                    ('icon-192-maskable.png', 'maskable'), ('icon-512-maskable.png', 'maskable')})

    def test_full_build_pages_banner_feed_hotsearch_and_id_index(self):
        self.write('ingest.json', envelope(site_items()))
        self.write('hotsearch.json', hotsearch())
        out, report = self.build(public_base='https://news.example/')
        meta = self.read(out, 'meta.json')
        self.assertEqual(meta['public_base'], 'https://news.example/')
        current = meta['channels'][0]
        self.assertEqual((current['slug'], len(current['banner']), current['feed_total'], current['pages']), ('current', 5, 65, 3))
        page3 = self.read(out, 'channel/current/page-3.json')
        self.assertEqual((len(page3['items']), page3['has_more']), (5, False))
        banner_ids = {i['id'] for i in current['banner']}
        feed_ids = {i['id'] for n in (1, 2, 3) for i in self.read(out, f'channel/current/page-{n}.json')['items']}
        self.assertFalse(banner_ids & feed_ids, 'banner 条目不在信息流里重复')
        self.assertEqual(self.read(out, 'channel/finance/page-1.json')['total'], 3)
        index = self.read(out, 'id-index.json')
        self.assertEqual(index['tnews365:69'], 'channel/current/page-3.json')
        self.assertEqual(index['tnews365:0'], 'meta.json')
        self.assertEqual(index['x-dotey:0'], 'bloggers.json')
        hot = self.read(out, 'hotsearch.json')
        self.assertEqual([p['status'] for p in hot['providers']], ['ok', 'error', 'empty'])
        bloggers = self.read(out, 'bloggers.json')
        x = next(p for p in bloggers['platforms'] if p['id'] == 'x')
        self.assertTrue(x['connected'])
        self.assertFalse(next(p for p in bloggers['platforms'] if p['id'] == 'weibo')['connected'])

    def test_invalid_items_dropped_and_duplicates_merged(self):
        good = news('tnews365', 'current', 1)
        dup_url = news('tnews365', 'current', 2, url=good['url'])
        wrong_channel = news('tnews365', 'world', 3)
        hl = news('hot-daily', 'current', 4, url=good['url'], highlight=True, highlight_date='2026-11-15')
        self.write('ingest.json', envelope([good, dup_url, wrong_channel, hl, dict(good)]))
        out, report = self.build()
        entry = next(f for f in report['files'] if f['file'] == 'ingest.json')
        self.assertEqual(entry['dropped'], 1)
        items = self.read(out, 'channel/current/page-1.json')['items']
        # 同来源同链接、标题不同：频道内合并只认「同链接且原标题相同、不同来源」，两条都留
        self.assertEqual(sorted(i['id'] for i in items), ['tnews365:1', 'tnews365:2'])
        self.assertEqual(sum(bool(i.get('highlight')) for i in items), 1, '今日重点按 url 并进已有条目，只打标')
        self.assertNotIn('hot-daily:4', self.read(out, 'id-index.json'))

    def test_invalid_hotsearch_becomes_error_not_fake_ranks(self):
        self.write('ingest.json', envelope([news('tnews365', 'current', 1)]))
        bad = hotsearch()
        bad['providers'][1]['items'] = [{'rank': 1, 'title': 'x', 'url': 'https://a.b/', 'pinned': False}]
        self.write('hotsearch.json', bad)
        out, report = self.build()
        hot = self.read(out, 'hotsearch.json')
        self.assertTrue(report['hotsearch']['errors'])
        self.assertEqual({p['status'] for p in hot['providers']}, {'error'})
        self.assertEqual(sum(len(p['items']) for p in hot['providers']), 0)

    def test_local_images_copied_into_site_media(self):
        pic = self.dir / 'media' / 'tnews365' / '1_1.webp'
        pic.parent.mkdir(parents=True)
        pic.write_bytes(b'RIFFfakewebp')
        a = news('tnews365', 'current', 1)
        a['image_local'] = {'path': str(pic), 'rel': 'media/tnews365/1_1.webp', 'width': 1200, 'height': 700}
        b = news('tnews365', 'current', 2, minutes=1)
        b['image_local'] = {'path': str(self.dir / 'missing.webp'), 'rel': 'media/x.webp', 'width': 1200, 'height': 700}
        c = news('tnews365', 'current', 3, minutes=2, image=img(3))
        c['image_local'] = {'path': str(pic), 'rel': 'media/tnews365/1_1.webp', 'width': 1, 'height': 1}
        d = news('tnews365', 'current', 4, minutes=3)
        d['image_local'] = {'path': str(pic), 'rel': '../../etc/passwd', 'width': 1, 'height': 1}
        self.write('ingest.json', envelope([a, b, c, d]))
        out, report = self.build()
        self.assertEqual(report['media_copied'], 1)
        self.assertEqual(report['files'][0]['dropped'], 1, '契约拒收带 .. 的 image_local.rel')
        self.assertEqual((out / 'media/tnews365/1_1.webp').read_bytes(), b'RIFFfakewebp')
        meta = self.read(out, 'meta.json')
        banner = {i['id']: i for i in meta['channels'][0]['banner']}
        self.assertEqual(banner['tnews365:1']['image'], {'url': 'media/tnews365/1_1.webp', 'width': 1200, 'height': 700})
        self.assertEqual(banner['tnews365:3']['image']['url'], 'https://img.test/3.png', '已有网络图不被本地图覆盖')
        feed = self.read(out, 'channel/current/page-1.json')['items']
        self.assertIsNone(next(i for i in feed if i['id'] == 'tnews365:2')['image'], '本地文件不在就当无图')
        self.assertFalse(any('image_local' in i for i in feed))

    def test_source_status_marks_unavailable_sources_per_channel(self):
        env = envelope([news('tnews365', 'current', 1)])
        env['sources'] = [{'id': 'tnews365', 'name': '竹新社', 'channel': 'current', 'status': 'ok'},
                          {'id': 'bbc-world', 'name': 'BBC World', 'channel': 'world', 'status': 'error', 'error': 'http_500'},
                          {'id': 'hot-daily', 'name': '今日重点', 'channel': None, 'status': 'error'}]
        self.write('ingest.json', env)
        out, _ = self.build()
        meta = {c['slug']: c for c in self.read(out, 'meta.json')['channels']}
        self.assertEqual(meta['current']['unavailable'], [])
        self.assertEqual([s['name'] for s in meta['world']['unavailable']], ['BBC World'])

    def test_feature_scripts_injected_only_when_present(self):
        web = self.dir / 'web'
        (web / 'features').mkdir(parents=True)
        (web / 'index.html').write_text('<body><!--FEATURES--></body>', encoding='utf-8')
        out, _ = self.build(web_dir=web)
        self.assertEqual((out / 'index.html').read_text(), '<body></body>')
        (web / 'features' / 'search.js').write_text('', encoding='utf-8')
        (web / 'features' / 'history.js').write_text('', encoding='utf-8')
        out, _ = self.build(web_dir=web)
        self.assertEqual((out / 'index.html').read_text(),
                         '<body><script src="features/history.js"></script>\n<script src="features/search.js"></script></body>')

    def test_refuses_to_overwrite_foreign_directory(self):
        out = self.dir / 'site'
        out.mkdir()
        (out / 'keep.txt').write_text('x')
        with self.assertRaises(SystemExit):
            site.build(out, self.inp, now=NOW)
        self.assertTrue((out / 'keep.txt').exists())


class ArchiveHookTests(unittest.TestCase):
    def test_calls_rebang_archive_build_when_available_and_skips_otherwise(self):
        calls = []
        fake = types.ModuleType('rebang.archive')
        fake.build = lambda items, out_dir: calls.append((len(items), Path(out_dir)))
        report = {}
        with mock.patch.dict(sys.modules, {'rebang.archive': fake}):
            site._run_archive([{'id': 'a'}], Path('/tmp/x'), report)
        self.assertEqual((report['archive'], calls), ('ok', [(1, Path('/tmp/x'))]))
        report = {}
        with mock.patch.dict(sys.modules, {'rebang.archive': None}):
            site._run_archive([], Path('/tmp/x'), report)
        self.assertTrue(report['archive'].startswith('skipped'))


@unittest.skipUnless((ROOT / 'var' / 'rebang' / 'in' / 'ingest.json').exists(), '本 worktree 没有真实 var/rebang/in')
class RealInputBuildTests(unittest.TestCase):
    def test_real_inputs_build(self):
        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch.object(site, '_run_archive', lambda items, out, report: None):
            report = site.build(Path(tmp) / 'site', site.DEFAULT_IN, hot_archive_dir=Path(tmp) / 'hot')
        self.assertFalse(report['fallback_fixture'])
        self.assertGreater(report['news'], 0)


if __name__ == '__main__':
    unittest.main()


class RevisionBuildTests(unittest.TestCase):
    """热搜按日归档、博主分页、频道不嵌热搜。"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)
        self.inp = self.dir / 'in'
        self.inp.mkdir()
        patcher = mock.patch.object(site, '_run_archive', lambda items, out, report: None)
        patcher.start()
        self.addCleanup(patcher.stop)

    def post(self, platform, handle, name, n, **extra):
        item = {'id': f'{handle}:{n}', 'kind': 'post', 'channel': None, 'source_id': handle, 'source_name': name,
                'title': f'标题{n}', 'summary': '摘要', 'url': '', 'lang': 'zh',
                'published_at': f'2026-11-15T{10 + n // 60:02d}:{n % 60:02d}:00+08:00',
                'blogger': {'platform': platform, 'handle': handle, 'display_name': name, 'media': []}}
        item.update(extra)
        return item

    def test_blogger_preview_pages_exclude_removed_platform(self):
        posts = [self.post('x', 'dotey', '宝玉', n) for n in range(45)] + [self.post('x', 'simonw', 'Simon Willison', 1)]
        posts.append(self.post('grok', 'world', '环球要闻', 1))  # 仍在磁盘上的旧输入不能进入新站
        (self.inp / 'ingest.json').write_text(json.dumps(envelope([news('tnews365', 'current', 1)] + posts)), encoding='utf-8')
        (self.inp / 'hotsearch.json').write_text(json.dumps(hotsearch()), encoding='utf-8')
        out = self.dir / 'site'
        site.build(out, self.inp, now=NOW, hot_archive_dir=self.dir / 'hot')
        data = out / 'data'
        bl = json.loads((data / 'bloggers.json').read_text(encoding='utf-8'))
        self.assertFalse(any(p['id'] == 'grok' for p in bl['platforms']))
        self.assertFalse((data / 'blogger/grok').exists())
        self.assertFalse((out / 'icons/grok.svg').exists())
        x = next(p for p in bl['platforms'] if p['id'] == 'x')
        self.assertEqual((x['name'], x['count'], x['icon']), ('X', 46, 'icons/x.svg'))
        dotey = next(a for a in x['accounts'] if a['handle'] == 'dotey')
        self.assertEqual((dotey['total'], dotey['key']), (45, site.blogger_key('dotey')))
        self.assertLessEqual(sum(1 for i in bl['items'] if i['blogger']['handle'] == 'dotey'), site.BLOGGER_PREVIEW)
        p1 = json.loads((data / 'blogger/x' / dotey['key'] / 'page-1.json').read_text(encoding='utf-8'))
        p2 = json.loads((data / 'blogger/x' / dotey['key'] / 'page-2.json').read_text(encoding='utf-8'))
        self.assertEqual((len(p1['items']), p1['has_more'], len(p2['items']), p2['has_more']), (30, True, 15, False))
        allp = json.loads((data / 'blogger/x/all/page-2.json').read_text(encoding='utf-8'))
        self.assertEqual(allp['total'], 46)
        idx = json.loads((data / 'id-index.json').read_text(encoding='utf-8'))
        self.assertNotIn('world:1', idx)
        self.assertEqual(idx['dotey:0'], 'blogger/x/all/page-2.json', '不在预览里的帖子深链也能找到')
        meta = json.loads((data / 'meta.json').read_text(encoding='utf-8'))
        self.assertFalse(any('hotsearch' in c for c in meta['channels']))

    def test_hotsearch_archive_written_per_day(self):
        (self.inp / 'ingest.json').write_text(json.dumps(envelope([news('tnews365', 'current', 1)])), encoding='utf-8')
        hot_dir = self.dir / 'hot'
        hot_dir.mkdir()
        old = hotsearch()
        old['generated_at'] = '2026-11-14T22:00:00+08:00'
        (hot_dir / '2026-11-14.json').write_text(json.dumps(old), encoding='utf-8')
        (self.inp / 'hotsearch.json').write_text(json.dumps(hotsearch()), encoding='utf-8')
        out = self.dir / 'site'
        report = site.build(out, self.inp, now=NOW, hot_archive_dir=hot_dir)
        index = json.loads((out / 'data/hotsearch/index.json').read_text(encoding='utf-8'))
        dates = [d['date'] for d in index['dates']]
        self.assertIn('2026-11-14', dates)
        self.assertEqual(report['hotsearch_archive']['days'], dates)
        day = json.loads((out / 'data/hotsearch/2026-11-14.json').read_text(encoding='utf-8'))
        self.assertEqual((day['date'], day['generated_at']), ('2026-11-14', '2026-11-14T22:00:00+08:00'))
