"""8:30 今日重点私聊稿：窗口、挑选、排除、提醒、dry-run 输出。不联网。"""
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from rebang.push import pick_highlights, render_brief, window_items
from rebang.push.cli import generate, main
from rebang.push.load import load_blogger_platforms, load_published_items
from rebang.push.render import EMPTY_MESSAGE, item_url, login_reminders
from rebang.push.select import is_excluded
from rebang.push.timeutil import parse_iso, parse_now

ROOT = Path(__file__).resolve().parents[1]
FIX = ROOT / 'tests/fixtures/rebang/push'
NOW = parse_now('2026-11-15T08:30:00+08:00')
BASE = 'https://news.example.test'


def fixture_items(name):
    return json.loads((FIX / name).read_text(encoding='utf-8'))['items']


def write_site(directory, items_name, bloggers_name=None, meta=True, archive_items=None, archive_date='2026-11-15'):
    """搭一套最小 site-v11/data 目录，供 CLI 与加载测试使用。"""
    site = Path(directory)
    data = site / 'data'
    if items_name:
        envelope = json.loads((FIX / items_name).read_text(encoding='utf-8'))
        by_channel = {}
        for item in envelope['items']:
            if item.get('kind') != 'news' or not item.get('channel'):
                # 未上站的资讯频道分页里不会出现；放进 side 文件也不被加载
                continue
            by_channel.setdefault(item['channel'], []).append(item)
        for slug, rows in by_channel.items():
            folder = data / 'channel' / slug
            folder.mkdir(parents=True, exist_ok=True)
            (folder / 'page-1.json').write_text(
                json.dumps({'items': rows, 'has_more': False}, ensure_ascii=False), encoding='utf-8')
    if archive_items:
        archive = site.parent / 'var' / 'rebang' / 'archive'
        archive.mkdir(parents=True, exist_ok=True)
        (archive / f'{archive_date}.json').write_text(
            json.dumps({'schema': 'rebang.items/1', 'producer': 'archive', 'generated_at': '2026-11-15T08:00:00+08:00',
                        'items': archive_items}, ensure_ascii=False), encoding='utf-8')
    if bloggers_name:
        data.mkdir(parents=True, exist_ok=True)
        shutil.copy(FIX / bloggers_name, data / 'bloggers.json')
    if meta:
        data.mkdir(parents=True, exist_ok=True)
        shutil.copy(FIX / 'meta.json', data / 'meta.json')
    return site


class WindowTests(unittest.TestCase):
    def test_boundary_beijing_and_utc(self):
        items = fixture_items('items-boundary.json')
        kept = {item['id'] for item in window_items(items, NOW)}
        self.assertIn('tnews365:eq-now', kept)
        self.assertIn('FinanceNewsDaily:just-in', kept)
        self.assertIn('apple-newsroom:utc-in', kept)
        self.assertIn('CE_Observe:midnight', kept)
        self.assertNotIn('bbc-world:eq-start', kept)
        self.assertNotIn('google-blog:future', kept)
        self.assertNotIn('github-trending:utc-out', kept)

    def test_naive_now_is_beijing(self):
        now = parse_now('2026-11-15T08:30:00')
        self.assertEqual(now, NOW)
        # 24 小时前整点（北京）排除
        items = fixture_items('items-boundary.json')
        kept = {item['id'] for item in window_items(items, now)}
        self.assertNotIn('bbc-world:eq-start', kept)


class PickCountTests(unittest.TestCase):
    def test_zero_candidates(self):
        self.assertEqual(pick_highlights(fixture_items('items-zero.json'), now=NOW), [])

    def test_two_candidates_keeps_both(self):
        selected = pick_highlights(fixture_items('items-two.json'), now=NOW)
        self.assertEqual([item['id'] for item in selected], ['tnews365:101', 'bbc-world:202'])

    def test_seven_candidates_caps_at_five_highlights_then_rotate(self):
        selected = pick_highlights(fixture_items('items-seven.json'), now=NOW)
        ids = [item['id'] for item in selected]
        # 3 条 highlight 按频道顺序先出，再从剩余频道轮转补 2 条（科技、数码；工具和「时事补位」轮不上）
        self.assertEqual(ids, [
            'tnews365:1',
            'bbc-world:2',
            'FinanceNewsDaily:3',
            'google-blog:4',
            'apple-newsroom:5',
        ])
        self.assertEqual(len(ids), 5)
        self.assertNotIn('github-trending:6', ids)
        self.assertNotIn('myBigCharacterPoster:7', ids)


class ExclusionTests(unittest.TestCase):
    def test_mail_excluded_sources_blocked_clip_private_and_posts(self):
        items = fixture_items('items-exclusions.json')
        excluded = [item['id'] for item in items if is_excluded(item)]
        self.assertEqual(excluded, [
            'mail:m1', 'reorx_share:r1', 'liangjiahepost:l1', 'titan_pain:t1',
            'tnews365:clip', 'tnews365:priv', 'x:p1',
        ])
        selected = pick_highlights(items, now=NOW)
        self.assertEqual([item['id'] for item in selected], ['tnews365:ok'])


class ReminderTests(unittest.TestCase):
    def test_login_expired_once_per_platform(self):
        platforms = json.loads((FIX / 'bloggers-expired.json').read_text(encoding='utf-8'))['platforms']
        lines = login_reminders(platforms)
        self.assertEqual(lines, [
            '微博登录已失效，待重新登录。',
            '微信读书登录已失效，待重新登录。',
        ])
        self.assertEqual(len(lines), 2)

    def test_no_reminder_for_error_or_not_configured(self):
        self.assertEqual(login_reminders([
            {'id': 'weibo', 'status': 'error'},
            {'id': 'wechat', 'status': 'not_configured'},
            {'id': 'jike', 'status': 'empty'},
        ]), [])


class RenderAndCliTests(unittest.TestCase):
    def test_empty_message_exact_and_reminder_still_appended(self):
        platforms = json.loads((FIX / 'bloggers-expired.json').read_text(encoding='utf-8'))['platforms']
        text = render_brief([], NOW, base_url=BASE, platforms=platforms)
        self.assertIn(EMPTY_MESSAGE, text)
        self.assertTrue(text.startswith('今日重点 · 11月15日\n'))
        self.assertIn('微博登录已失效，待重新登录。', text)
        self.assertEqual(text.count('微博登录已失效，待重新登录。'), 1)
        self.assertEqual(text.count('微信读书登录已失效，待重新登录。'), 1)

    def test_translated_title_used(self):
        selected = pick_highlights(fixture_items('items-two.json'), now=NOW)
        text = render_brief(selected, NOW, base_url=BASE)
        self.assertIn('【环球】环球一条', text)
        self.assertIn('环球摘要。', text)
        self.assertNotIn('World story', text)
        self.assertIn(item_url(selected[0], BASE), text)

    def test_dry_run_fixture_output_stable(self):
        golden = (FIX / 'golden-seven.txt').read_text(encoding='utf-8')
        with tempfile.TemporaryDirectory() as tmp:
            site = write_site(Path(tmp) / 'site-v11', 'items-seven.json', bloggers_name='bloggers-expired.json')
            text = generate(str(site), NOW, base_url=BASE)
            self.assertEqual(text, golden)

    def test_cli_dry_run_stdout_and_output_file(self):
        golden = (FIX / 'golden-seven.txt').read_text(encoding='utf-8')
        with tempfile.TemporaryDirectory() as tmp:
            site = write_site(Path(tmp) / 'site-v11', 'items-seven.json', bloggers_name='bloggers-expired.json')
            out = Path(tmp) / 'brief.txt'
            from io import StringIO
            import sys
            buf = StringIO()
            old = sys.stdout
            try:
                sys.stdout = buf
                code = main([
                    '--site', str(site),
                    '--now', '2026-11-15T08:30:00+08:00',
                    '--dry-run',
                    '--output', str(out),
                    '--base-url', BASE,
                ])
            finally:
                sys.stdout = old
            self.assertEqual(code, 0)
            self.assertEqual(buf.getvalue(), golden)
            self.assertEqual(out.read_text(encoding='utf-8'), golden)

    def test_cli_zero_candidates(self):
        with tempfile.TemporaryDirectory() as tmp:
            site = write_site(Path(tmp) / 'site-v11', 'items-zero.json')
            from io import StringIO
            import sys
            buf = StringIO()
            old = sys.stdout
            try:
                sys.stdout = buf
                code = main(['--site', str(site), '--now', '2026-11-15T08:30:00+08:00', '--dry-run', '--base-url', BASE])
            finally:
                sys.stdout = old
            self.assertEqual(code, 0)
            self.assertIn(EMPTY_MESSAGE, buf.getvalue())
            self.assertNotIn('昨天更早', buf.getvalue())
            self.assertNotIn('邮件不该出现', buf.getvalue())

    def test_load_uses_site_pages_not_unpublished_side_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            site = write_site(Path(tmp) / 'site-v11', 'items-two.json')
            unpublished = {
                'id': 'tnews365:hidden',
                'kind': 'news',
                'channel': 'current',
                'source_id': 'tnews365',
                'source_name': '竹新社',
                'title': '未上站',
                'summary': '不该出现。',
                'url': 'https://t.me/tnews365/hidden',
                'published_at': '2026-11-15T07:30:00+08:00',
                'lang': 'zh',
                'highlight': True,
            }
            (Path(tmp) / 'unpublished.json').write_text(json.dumps({'items': [unpublished]}), encoding='utf-8')
            loaded = load_published_items(site, now=NOW)
            self.assertTrue(all(item['id'] != 'tnews365:hidden' for item in loaded))
            selected = pick_highlights(loaded, now=NOW)
            self.assertEqual([item['id'] for item in selected], ['tnews365:101', 'bbc-world:202'])

    def test_archive_fills_gap_and_site_wins_on_duplicate_id(self):
        archive_only = fixture_items('items-two.json')[1]  # world
        site_version = dict(fixture_items('items-two.json')[0])
        older = dict(site_version)
        older['title'] = '归档旧标题'
        with tempfile.TemporaryDirectory() as tmp:
            site = write_site(Path(tmp) / 'site-v11', 'items-two.json', archive_items=[older, archive_only])
            # site already has both; rewrite site to only have current, archive has both
            shutil.rmtree(site / 'data' / 'channel' / 'world', ignore_errors=True)
            loaded = load_published_items(site, now=NOW)
            by_id = {item['id']: item for item in loaded}
            self.assertEqual(by_id['tnews365:101']['title'], '时事一条')
            self.assertIn('bbc-world:202', by_id)

    def test_base_url_from_meta(self):
        with tempfile.TemporaryDirectory() as tmp:
            site = write_site(Path(tmp) / 'site-v11', 'items-two.json')
            text = generate(str(site), NOW)
            self.assertIn('https://news.example.test#/item/tnews365%3A101', text)

    def test_platforms_loaded_from_site(self):
        with tempfile.TemporaryDirectory() as tmp:
            site = write_site(Path(tmp) / 'site-v11', 'items-two.json', bloggers_name='bloggers-expired.json')
            platforms = load_blogger_platforms(site)
            self.assertEqual(sum(1 for row in platforms if row.get('status') == 'login_expired'), 3)


if __name__ == '__main__':
    unittest.main()
