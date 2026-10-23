"""Exercise publishing against local bare remotes only."""
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
        # Preserve staged source changes as well as main.
        (self.root / 'tracked').write_text('pending')
        self.git('add', 'tracked')
        self.index = self.git('write-tree')

    def git(self, *args):
        return subprocess.check_output(['git', *args], cwd=self.root, stderr=subprocess.DEVNULL, text=True).strip()

    def publish(self, *args, cname=None):
        env = dict(os.environ)
        env.pop('PAGES_CNAME', None)
        if cname:
            env['PAGES_CNAME'] = cname
        return subprocess.run(['sh', 'tools/publish_pages.sh', '--already-built', *args],
                              cwd=self.root, env=env, capture_output=True, text=True)

    def test_publish_replaces_history_and_preserves_source(self):
        for _ in range(2):
            result = self.publish()
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(self.git('--git-dir', str(self.remote), 'rev-list', '--count', 'gh-pages'), '1')
        files = self.git('--git-dir', str(self.remote), 'ls-tree', '-r', '--name-only', 'gh-pages').splitlines()
        self.assertEqual(files, ['.nojekyll', 'build-info.json', 'index.html'])
        self.assertEqual(self.git('rev-parse', 'main'), self.head)
        self.assertEqual(self.git('--git-dir', str(self.remote), 'rev-parse', 'main'), self.head)
        self.assertEqual(self.git('write-tree'), self.index)
        self.assertEqual(self.git('worktree', 'list', '--porcelain').count('worktree '), 1)

    def test_dry_run_does_not_push(self):
        result = self.publish('--dry-run')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertRegex(result.stdout, r'files=3 sha=[0-9a-f]+ dry-run=1')
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

    def test_cname_only_from_environment(self):
        (self.root / 'site/CNAME').write_text('stale.example')
        self.assertEqual(self.publish().returncode, 0)
        self.assertNotIn('CNAME', self.git('--git-dir', str(self.remote), 'ls-tree', '--name-only', 'gh-pages'))
        self.assertEqual(self.publish(cname='public.example').returncode, 0)
        self.assertEqual(self.git('--git-dir', str(self.remote), 'show', 'gh-pages:CNAME'), 'public.example')
