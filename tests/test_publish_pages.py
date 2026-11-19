"""Exercise publishing against local bare remotes only."""
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


class PublishPagesTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'checkout'
        self.root.mkdir()
        self.remote = self.root.parent / 'remote.git'
        self.git('init', '--bare', str(self.remote))
        self.git('init', '-b', 'main')
        self.git('config', 'user.name', 'Test')
        self.git('config', 'user.email', 'test@localhost')
        (self.root / 'tools').mkdir()
        shutil.copy2(Path(__file__).resolve().parents[1] / 'tools/publish_pages.sh', self.root / 'tools')
        (self.root / 'tracked').write_text('source')
        self.git('add', '.')
        tree = self.git('write-tree')
        self.head = self.git('commit-tree', tree, '-m', 'fixture')
        self.git('update-ref', 'refs/heads/main', self.head)
        self.git('remote', 'add', 'origin', str(self.remote))
        self.git('--git-dir', str(self.remote), 'fetch', str(self.root), 'main:main')
        (self.root / 'site').mkdir()
        (self.root / 'site/index.html').write_text('public')
        (self.root / 'site/build-info.json').write_text('{}')
        self.live_path = self.root / 'site/data/live.json'
        self.live_path.parent.mkdir()
        self.write_live(datetime.now(timezone.utc) - timedelta(minutes=10))
        # Preserve staged source changes as well as main.
        (self.root / 'tracked').write_text('pending')
        self.git('add', 'tracked')
        self.index = self.git('write-tree')

    def git(self, *args):
        return subprocess.check_output(['git', *args], cwd=self.root, stderr=subprocess.DEVNULL, text=True).strip()

    def publish(self, *args, cname=None):
        env = dict(os.environ)
        env['BOX_PYTHON'] = sys.executable
        env.pop('PAGES_CNAME', None)
        if cname:
            env['PAGES_CNAME'] = cname
        return subprocess.run(['sh', 'tools/publish_pages.sh', '--already-built', *args],
                              cwd=self.root, env=env, capture_output=True, text=True)

    def write_live(self, updated):
        self.live_path.write_text(json.dumps({'updated': updated.isoformat(),
                                             'sample': False, 'messages': [{'id': 'news'}]}))

    def test_stale_legacy_live_refused_even_with_fresh_rebang(self):
        now = datetime.now(timezone.utc)
        # Match the observed lag of the legacy live data in the 21:19 package.
        self.write_live(now - timedelta(hours=21, minutes=32, seconds=58))
        rebang = self.root / 'site-v11'
        (rebang / 'data').mkdir(parents=True)
        (rebang / 'index.html').write_text('rebang')
        (rebang / 'data/meta.json').write_text(json.dumps({'built_at': now.isoformat()}))
        for args in ((), ('--dry-run',)):
            with self.subTest(args=args):
                result = self.publish(*args)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn('site/data/live.json', result.stderr)
                self.assertIn('older than 2 hours', result.stderr)
                self.assertNotIn('Pages prepared', result.stdout)
                self.assertEqual(self.git('--git-dir', str(self.remote), 'for-each-ref', 'refs/heads/gh-pages'), '')
        self.assertEqual(self.git('worktree', 'list', '--porcelain').count('worktree '), 1)

    def test_missing_invalid_or_future_live_updated_refused(self):
        cases = (
            (None, 'missing or non-regular file'),
            ('{', 'invalid updated timestamp'),
            ('{"updated":"2026-11-19T00:00:00"}', 'timestamp must include a timezone'),
            (json.dumps({'updated': (datetime.now(timezone.utc) + timedelta(minutes=11)).isoformat()}),
             'more than 10 minutes in the future'),
        )
        for body, reason in cases:
            with self.subTest(reason=reason):
                if body is None:
                    self.live_path.unlink()
                else:
                    self.live_path.write_text(body)
                result = self.publish('--dry-run')
                self.assertNotEqual(result.returncode, 0)
                self.assertIn('publish refused: site/data/live.json:', result.stderr)
                self.assertIn(reason, result.stderr)
                self.assertNotIn('Pages prepared', result.stdout)

    def test_publish_replaces_history_and_preserves_source(self):
        for _ in range(2):
            result = self.publish()
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(self.git('--git-dir', str(self.remote), 'rev-list', '--count', 'gh-pages'), '1')
        files = self.git('--git-dir', str(self.remote), 'ls-tree', '-r', '--name-only', 'gh-pages').splitlines()
        self.assertEqual(files, ['.nojekyll', 'build-info.json', 'data/live.json', 'index.html'])
        self.assertEqual(self.git('rev-parse', 'main'), self.head)
        self.assertEqual(self.git('--git-dir', str(self.remote), 'rev-parse', 'main'), self.head)
        self.assertEqual(self.git('write-tree'), self.index)
        self.assertEqual(self.git('worktree', 'list', '--porcelain').count('worktree '), 1)

    def test_dry_run_does_not_push(self):
        result = self.publish('--dry-run')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertRegex(result.stdout, r'files=4 sha=[0-9a-f]+ dry-run=1')
        self.assertEqual(self.git('--git-dir', str(self.remote), 'for-each-ref', 'refs/heads/gh-pages'), '')

    def test_default_dry_run_builds_with_box_python(self):
        (self.root / 'site/index.html').unlink()
        (self.root / 'site/build-info.json').unlink()
        (self.root / 'pipeline.py').write_text(
            "import os\nfrom pathlib import Path\n"
            "assert [os.environ[k] for k in ('SITE_MODE', 'MAIL_DIGEST', 'TZ')] == "
            "['public', '0', 'Asia/Shanghai']\n"
            "Path('site/index.html').write_text('built')\n")
        (self.root / 'tools/write_build_info.py').write_text(
            "from pathlib import Path\nassert Path('site/index.html').is_file()\n"
            "Path('site/build-info.json').write_text('{}')\n")
        result = subprocess.run(['sh', 'tools/publish_pages.sh', '--dry-run'], cwd=self.root,
                                env=dict(os.environ, BOX_PYTHON=sys.executable), capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.root / 'site/index.html').read_text(), 'built')
        self.assertEqual(self.git('--git-dir', str(self.remote), 'for-each-ref', 'refs/heads/gh-pages'), '')

    def test_env_files_refused(self):
        nested = self.root / 'site/nested'
        nested.mkdir()
        (nested / '.env.production').write_text('fixture')
        result = self.publish()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('publish refused: .env*', result.stderr)

    def test_missing_outputs_refused(self):
        for name in ('index.html', 'build-info.json'):
            path = self.root / 'site' / name
            path.unlink()
            self.assertNotEqual(self.publish().returncode, 0)
            path.write_text('fixture')

    def test_rebang_site_published_under_subdirectory(self):
        """v11（拾光热榜）site-v11/ 一并发到 gh-pages 的 rebang/；REBANG_PUBLISH=0 或没构建时不带。"""
        rb = self.root / 'site-v11'
        (rb / 'data').mkdir(parents=True)
        (rb / 'index.html').write_text('rebang')
        (rb / 'data/meta.json').write_text('{}')
        files = lambda: self.git('--git-dir', str(self.remote), 'ls-tree', '-r', '--name-only', 'gh-pages').splitlines()
        result = self.publish()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(files(), ['.nojekyll', 'build-info.json', 'data/live.json', 'index.html', 'rebang/data/meta.json', 'rebang/index.html'])
        env = dict(os.environ, REBANG_PUBLISH='0', BOX_PYTHON=sys.executable)
        env.pop('PAGES_CNAME', None)
        result = subprocess.run(['sh', 'tools/publish_pages.sh', '--already-built'], cwd=self.root, env=env, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(files(), ['.nojekyll', 'build-info.json', 'data/live.json', 'index.html'])
        (rb / '.env').write_text('x')
        self.assertIn('.env* found in rebang site', self.publish().stderr)

    def test_cname_only_from_environment(self):
        (self.root / 'site/CNAME').write_text('stale.example')
        self.assertEqual(self.publish().returncode, 0)
        self.assertNotIn('CNAME', self.git('--git-dir', str(self.remote), 'ls-tree', '--name-only', 'gh-pages'))
        self.assertEqual(self.publish(cname='public.example').returncode, 0)
        self.assertEqual(self.git('--git-dir', str(self.remote), 'show', 'gh-pages:CNAME'), 'public.example')
