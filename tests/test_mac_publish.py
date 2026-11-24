"""Offline publication exercises real Git, the packer and the receiver."""
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import plistlib
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest


ROOT = Path(__file__).resolve().parents[1]
GIT = shutil.which('git')
FLOCK = shutil.which('flock')

PIPELINE = '''\
import json, shutil, sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
with sqlite3.connect('tg.db') as db:
    db.execute("insert or ignore into messages values ('old-pipeline')")
site = Path('site')
shutil.copytree('packed-fixture', site, dirs_exist_ok=True)
now = datetime.now(timezone.utc)
day = now.astimezone(timezone(timedelta(hours=8))).date().isoformat()
(site / 'data/live.json').write_text(json.dumps(dict(updated=now.isoformat(),
    sample=Path('.git/reject-candidate').exists(), messages=[dict(id='fixture')])))
'''

INGEST = '''\
import json, sqlite3, sys
from pathlib import Path
with sqlite3.connect('tg.db') as db:
    db.execute("insert or ignore into messages values ('after-rebang-ingest')")
Path(sys.argv[sys.argv.index('--out') + 1]).write_text('{}')
'''

SITE = '''\
import json, sys
from pathlib import Path
out = Path(sys.argv[sys.argv.index('--out') + 1])
(out / 'data').mkdir(parents=True)
(out / 'index.html').write_text('<h1>New public site</h1>')
(out / 'data/meta.json').write_text(json.dumps(dict(fixture=False, counts=dict(news=1))))
if Path('.git/leave-journal').exists():
    Path('tg.db-journal').touch()
'''


@unittest.skipUnless(FLOCK, 'flock is required by the Mac publisher')
class MacPublishTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='mac-publish-test-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.checkout = self.root / 'checkout'
        self.remote = self.root / 'remote.git'
        self.state = self.checkout / '.git/mac-publish'
        self.checkout.mkdir()
        self.bin = self.root / 'bin'
        self.bin.mkdir()
        (self.bin / 'flock').symlink_to(FLOCK)
        (self.bin / 'python3').symlink_to(sys.executable)
        self.plist = plistlib.loads((ROOT / 'tools/mac_publish.launchd.plist.example').read_bytes())
        self.assertEqual(self.plist['StartCalendarInterval'], {'Minute': 5})
        self.assertNotIn('RunAtLoad', self.plist)
        self.assertTrue(all(Path(p).is_absolute() for p in self.plist['EnvironmentVariables']['PATH'].split(':')))
        self.assertTrue(Path(self.plist['EnvironmentVariables']['BOX_PYTHON']).is_absolute())
        # Fill the template with this dedicated checkout's absolute paths. No GUI session env.
        self.plist['EnvironmentVariables'].update(PATH=f'{self.bin}:/usr/bin:/bin',
                                                   BOX_PYTHON=sys.executable, HOME=str(self.root))
        self.plist['WorkingDirectory'] = str(self.checkout)
        self.env = self.plist['EnvironmentVariables']
        self.git('init', '--bare', str(self.remote))
        self.git('init', '-b', 'main')
        self.git('config', 'user.name', 'Fixture')
        self.git('config', 'user.email', 'fixture@localhost')
        self.git('remote', 'add', 'origin', self.remote.as_uri())
        (self.checkout / 'public-feeds').mkdir()
        (self.checkout / 'public-feeds/.gitkeep').touch()
        shutil.copyfile(ROOT / '.gitignore', self.checkout / '.gitignore')
        with sqlite3.connect(self.checkout / 'tg.db') as db:
            db.execute('create table messages (id text primary key)')
        self.git('add', '.')
        self.git('commit', '-m', 'Main baseline')
        self.main_root = self.git('rev-parse', 'HEAD')
        for directory, names in (('tools', ('mac_publish.py', 'mac_publish.sh', 'publish_pages.sh',
                                           'rebang_refresh.sh', 'write_build_info.py')),
                                 ('deploy', ('news-sync.sh',))):
            (self.checkout / directory).mkdir()
            for name in names:
                shutil.copyfile(ROOT / directory / name, self.checkout / directory / name)
        (self.checkout / 'pipeline.py').write_text(PIPELINE)
        for name, program in (('tgmeta', ''), ('hotsearch', ''), ('bloggers', ''), ('ingest', INGEST), ('site', SITE)):
            module = self.checkout / 'rebang' / name
            module.mkdir(parents=True)
            (module / '__main__.py').write_text(program)
        self.site_fixture = self.checkout / 'packed-fixture'
        self.make_site(self.site_fixture)
        self.git('add', '.')
        self.git('commit', '-m', 'Publisher code')
        self.git('push', 'origin', 'main')
        self.git('checkout', '--detach')
        self.code = self.git('rev-parse', 'HEAD')
        self.plist['ProgramArguments'][1] = str(self.checkout / 'tools/mac_publish.sh')
        self.plist['ProgramArguments'][3] = self.code
        baseline = self.root / 'baseline'
        self.make_site(baseline)
        self.git('-C', str(baseline), 'init', '-b', 'gh-pages')
        self.git('-C', str(baseline), 'add', '.')
        self.git('-C', str(baseline), '-c', 'user.name=Fixture', '-c', 'user.email=fixture@localhost',
                 'commit', '-m', 'Pages baseline')
        self.git('-C', str(baseline), 'push', self.remote.as_uri(), 'gh-pages')
        self.before = self.heads()

    def make_site(self, site):
        (site / 'data').mkdir(parents=True)
        (site / 'archive/data').mkdir(parents=True)
        now = datetime.now(timezone.utc)
        for offset in (0, 1):  # Leave the fixture valid even if a run crosses midnight in Beijing.
            day = (now.astimezone(timezone(timedelta(hours=8))) - timedelta(days=offset)).date().isoformat()
            record = dict(uid='item', source='world', day=day, html='<article>Story</article>')
            raw = json.dumps(dict(schema=3, scope='public', day=day, items=[record])).encode()
            (site / f'archive/data/{day}.json').write_bytes(raw)
            (site / f'archive/{day}.html').write_text('<body data-bookmark-scope="public">'
                                                    '<div id="news-fallback">' + record['html'] + '</div>')
        manifest = dict(schema=3, scope='public', days={p.stem: dict(version=hashlib.sha256(p.read_bytes()).hexdigest())
                                                       for p in (site / 'archive/data').glob('*.json')})
        (site / 'archive/manifest.json').write_text(json.dumps(manifest))
        (site / 'index.html').write_text('<body data-bookmark-scope="public">Site</body>')
        for i in range(95):
            (site / f'asset-{i}.css').write_text('/* fixture */')

    def git(self, *args, binary=False):
        result = subprocess.run([GIT, *args], cwd=self.checkout, env=self.env, check=True, capture_output=True)
        return result.stdout if binary else result.stdout.decode().strip()

    def heads(self):
        return tuple(self.git('--git-dir', str(self.remote), 'rev-parse', branch) for branch in ('main', 'gh-pages'))

    def cycle(self, env=None, *, legacy_args=True):
        arguments = self.plist['ProgramArguments']
        return subprocess.run(arguments if legacy_args else arguments[:2], cwd=self.plist['WorkingDirectory'],
                              env=self.env if env is None else env, timeout=30, capture_output=True, text=True)

    def advance_main(self, path, contents):
        parent = self.heads()[0]
        replacement = self.root / 'replacement'
        replacement.write_bytes(contents)
        bare = ('--git-dir', str(self.remote))
        blob = self.git(*bare, 'hash-object', '-w', str(replacement))
        self.git(*bare, 'read-tree', parent)
        self.git(*bare, 'update-index', '--cacheinfo', f'100644,{blob},{path}')
        tree = self.git(*bare, 'write-tree')
        commit = self.git(*bare, '-c', 'user.name=Fixture', '-c', 'user.email=fixture@localhost',
                          'commit-tree', tree, '-p', parent, '-m', f'Update {path}')
        self.git(*bare, 'update-ref', 'refs/heads/main', commit, parent)
        return commit

    def install_hook(self, name, script):
        hook = self.remote / 'hooks' / name
        hook.write_text('#!/bin/sh\nset -eu\n' + script + '\n')
        hook.chmod(0o755)

    def assert_success(self, result):
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('validation=passed', result.stdout)
        self.assertIn('dry_run=true target_unchanged=true', result.stdout)
        self.assertIn('published main=', result.stdout)
        self.assertFalse((self.state / 'HALT').exists())

    def test_two_cycles_in_plist_environment_with_exact_parent_trees(self):
        index = self.checkout / '.git/index'
        original_index = index.read_bytes()
        result = self.cycle()
        self.assert_success(result)
        main, pages = self.heads()
        self.assertEqual(self.git('rev-parse', f'{main}^'), self.before[0])
        self.assertEqual(self.git('rev-parse', f'{pages}^'), self.before[1])
        self.assertEqual(self.git('diff-tree', '--no-commit-id', '--name-only', '-r', self.before[0], main), 'tg.db')
        prepared = next(part[4:] for line in result.stdout.splitlines() if line.startswith('Pages prepared:')
                        for part in line.split() if part.startswith('sha='))
        self.assertEqual(self.git('rev-parse', f'{pages}^{{tree}}'), self.git('rev-parse', f'{prepared}^{{tree}}'))
        info = json.loads(self.git('show', f'{pages}:build-info.json'))
        db = self.git('show', f'{main}:tg.db', binary=True)
        self.assertEqual(info['database_sha256'], hashlib.sha256(db).hexdigest())
        self.assertEqual(info['source_commit'], self.code)
        self.assertEqual(db, (self.checkout / 'tg.db').read_bytes())
        self.assertEqual(index.read_bytes(), original_index)
        with sqlite3.connect(self.checkout / 'tg.db') as connection:
            self.assertEqual(connection.execute('select id from messages order by id').fetchall(),
                             [('after-rebang-ingest',), ('old-pipeline',)])
        self.assert_success(self.cycle())
        self.assertEqual(self.heads()[0], main, 'no DB change must not produce a data commit')
        self.assertEqual(self.git('rev-parse', self.heads()[1] + '^'), pages)
        self.assertEqual(self.git('rev-parse', 'HEAD'), main)
        self.assertEqual(self.git('diff', '--cached', '--name-only'), '')

    def test_fast_forward_runs_new_publisher_and_builds_from_new_main(self):
        self.assert_success(self.cycle())
        old_pages = self.heads()[1]
        publisher = (self.checkout / 'tools/mac_publish.py').read_bytes()
        publisher = publisher.replace(b'    sys.exit(main())',
                                      b'    print("new publisher", flush=True)\n    sys.exit(main())')
        self.advance_main('tools/mac_publish.py', publisher)
        new_main = self.advance_main('pipeline.py', PIPELINE.replace('old-pipeline', 'new-pipeline').encode())

        result = self.cycle(legacy_args=False)
        self.assert_success(result)
        self.assertIn('new publisher', result.stdout)
        main, pages = self.heads()
        self.assertEqual(self.git('rev-parse', 'HEAD'), new_main)
        self.assertEqual(self.git('rev-parse', f'{main}^'), new_main)
        self.assertEqual(self.git('rev-parse', f'{pages}^'), old_pages)
        self.assertEqual(self.git('diff-tree', '--no-commit-id', '--name-only', '-r', new_main, main), 'tg.db')
        self.assertEqual(json.loads(self.git('show', f'{pages}:build-info.json'))['source_commit'], new_main)
        with sqlite3.connect(self.checkout / 'tg.db') as connection:
            self.assertEqual(connection.execute("select count(*) from messages where id='new-pipeline'").fetchone(), (1,))
        self.assert_success(self.cycle())  # The original plist SHA still works after switching.

    def test_non_fast_forward_main_halts(self):
        self.assert_success(self.cycle())
        self.git('--git-dir', str(self.remote), 'update-ref', 'refs/heads/main', self.main_root)
        before = self.heads()
        result = self.cycle()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('main is not a fast-forward', result.stderr)
        self.assertEqual(self.heads(), before)
        self.assertTrue((self.state / 'HALT').exists())
        self.assertIn('HALT exists', self.cycle().stderr)

    def test_unexpected_pages_fast_forward_halts(self):
        self.assert_success(self.cycle())
        _, parent = self.heads()
        bare = ('--git-dir', str(self.remote))
        pages = self.git(*bare, '-c', 'user.name=Fixture', '-c', 'user.email=fixture@localhost',
                         'commit-tree', f'{parent}^{{tree}}', '-p', parent, '-m', 'Other publisher')
        self.git(*bare, 'update-ref', 'refs/heads/gh-pages', pages, parent)
        before = self.heads()
        result = self.cycle()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('gh-pages changed since the last local checkpoint', result.stderr)
        self.assertEqual(self.heads(), before)
        self.assertTrue((self.state / 'HALT').exists())

    def test_failed_build_from_new_main_preserves_old_site_and_retries_new_code(self):
        self.assert_success(self.cycle())
        program = b'raise SystemExit("new code build failed")\n'
        self.advance_main('rebang/site/__main__.py', program)
        before = self.heads()
        self.install_hook('pre-receive', 'touch push-attempt')
        for _ in range(2):
            result = self.cycle()
            self.assertNotEqual(result.returncode, 0)
            refresh_log = Path(json.loads((self.checkout / 'var/rebang/logs/last-refresh.json').read_text())['log'])
            self.assertIn('new code build failed', (self.checkout / refresh_log).read_text())
            self.assertIn(f'failed at source_commit={before[0]}', result.stderr)
            self.assertEqual(self.heads(), before)
            self.assertFalse((self.remote / 'push-attempt').exists())
            self.assertFalse((self.state / 'HALT').exists())
        self.assertEqual(self.git('rev-parse', 'HEAD'), before[0])

    def test_checkout_preserves_unstaged_database_and_ignored_cache(self):
        self.assert_success(self.cycle())
        database = self.checkout / 'tg.db'
        with sqlite3.connect(database) as connection:
            connection.execute("insert into messages values ('unpublished-local')")
        local = database.read_bytes()
        cache = self.checkout / 'site/cache-only.txt'
        cache.write_text('local cache')
        self.advance_main('pipeline.py', b'\n' + PIPELINE.encode())

        self.assert_success(self.cycle())
        self.assertEqual(database.read_bytes(), local)
        self.assertEqual(self.git('show', self.heads()[0] + ':tg.db', binary=True), local)
        self.assertEqual(cache.read_text(), 'local cache')
        self.assertEqual(self.git('diff', '--cached', '--name-only'), '')

    def test_fast_forward_during_code_switch_halts_before_collection(self):
        self.assert_success(self.cycle())
        first = self.advance_main('pipeline.py', b'raise SystemExit("should not collect")\n')
        second = self.advance_main('pipeline.py', b'\n' + PIPELINE.encode())
        _, pages = self.heads()
        self.git('--git-dir', str(self.remote), 'update-ref', 'refs/heads/main', first, second)
        wrapper = self.bin / 'git'
        wrapper.write_text(f'''#!/bin/sh
set -eu
if [ "$1" = checkout ]; then
    '{GIT}' --git-dir '{self.remote}' update-ref refs/heads/main '{second}' '{first}'
fi
exec '{GIT}' "$@"
''')
        wrapper.chmod(0o755)
        self.install_hook('pre-receive', 'touch push-attempt')

        result = self.cycle()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('remote refs moved during code switch', result.stderr)
        self.assertNotIn('building source_commit=', result.stdout)
        self.assertEqual(self.heads(), (second, pages))
        self.assertFalse((self.remote / 'push-attempt').exists())
        self.assertTrue((self.state / 'HALT').exists())

    def test_interrupted_checkout_restores_saved_database(self):
        self.assert_success(self.cycle())
        database = self.checkout / 'tg.db'
        with sqlite3.connect(database) as connection:
            connection.execute("insert into messages values ('before-interruption')")
        local = database.read_bytes()
        saved = self.state / 'checkout-tg.db'
        database.rename(saved)
        database.write_bytes(self.git('show', 'HEAD:tg.db', binary=True))

        result = self.cycle()
        self.assert_success(result)
        self.assertIn('restored local tg.db', result.stdout)
        self.assertEqual(database.read_bytes(), local)
        self.assertFalse(saved.exists())

    def test_initial_checkout_seeds_database_from_fetched_main(self):
        # Move only the fixture remote's main, keeping the publisher's checkout pinned.
        db = self.root / 'newer.db'
        db.write_bytes((self.checkout / 'tg.db').read_bytes())
        with sqlite3.connect(db) as connection:
            connection.execute("insert into messages values ('remote-seed')")
        blob = self.git('--git-dir', str(self.remote), 'hash-object', '-w', str(db))
        self.git('--git-dir', str(self.remote), 'read-tree', 'main')
        self.git('--git-dir', str(self.remote), 'update-index', '--cacheinfo', f'100644,{blob},tg.db')
        tree = self.git('--git-dir', str(self.remote), 'write-tree')
        newer = self.git('--git-dir', str(self.remote), '-c', 'user.name=Fixture', '-c', 'user.email=fixture@localhost',
                         'commit-tree', tree, '-p', self.before[0], '-m', 'Newer database seed')
        self.git('--git-dir', str(self.remote), 'update-ref', 'refs/heads/main', newer)
        self.assert_success(self.cycle())
        self.assertEqual(self.git('rev-parse', self.heads()[0] + '^'), newer)
        with sqlite3.connect(self.checkout / 'tg.db') as connection:
            self.assertEqual(connection.execute("select count(*) from messages where id='remote-seed'").fetchone(), (1,))

    def test_receiver_rejection_never_pushes(self):
        (self.checkout / '.git/reject-candidate').touch()
        self.install_hook('pre-receive', 'touch push-attempt')
        result = self.cycle()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('REFUSED empty or sample live data', result.stderr)
        self.assertEqual(self.heads(), self.before)
        self.assertFalse((self.remote / 'push-attempt').exists())
        self.assertFalse((self.state / 'HALT').exists())
        (self.checkout / '.git/reject-candidate').unlink()
        self.assert_success(self.cycle())

    def test_atomic_rejection_preserves_both_remote_refs_and_stops_retry(self):
        self.install_hook('pre-receive', 'while read -r old new ref; do printf "%s\\n" "$ref" >> attempts; done')
        self.install_hook('update', '[ "$1" != refs/heads/gh-pages ]')
        result = self.cycle()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('validation=passed', result.stdout)
        self.assertIn('atomic push failure', result.stderr)
        self.assertEqual(self.heads(), self.before)
        self.assertTrue((self.state / 'HALT').exists())
        self.assertNotEqual((self.checkout / 'tg.db').read_bytes(), self.git('show', 'HEAD:tg.db', binary=True))
        attempts = (self.remote / 'attempts').read_text()
        self.assertCountEqual(attempts.splitlines(), ['refs/heads/main', 'refs/heads/gh-pages'])
        self.assertIn('HALT exists', self.cycle().stderr)
        self.assertEqual((self.remote / 'attempts').read_text(), attempts)

    def test_old_box_rewrite_between_preflight_and_push_is_rejected(self):
        replacement = self.git('--git-dir', str(self.remote), '-c', 'user.name=Old box', '-c', 'user.email=fixture@localhost',
                               'commit-tree', self.before[1] + '^{tree}', '-m', 'Unrelated Pages root')
        # Simulate the old box's forced ref update without using a force push anywhere in the tests.
        wrapper = self.bin / 'git'
        wrapper.write_text(f'''#!/bin/sh
set -eu
if [ "$1" = push ]; then
    printf 'one attempt\\n' >> '{self.remote}/races'
    '{GIT}' --git-dir '{self.remote}' update-ref refs/heads/gh-pages '{replacement}'
fi
exec '{GIT}' "$@"
''')
        wrapper.chmod(0o755)
        result = self.cycle()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('validation=passed', result.stdout)
        self.assertEqual(self.heads(), (self.before[0], replacement))
        self.assertTrue((self.state / 'HALT').is_file())
        self.assertIn('HALT exists', self.cycle().stderr)
        self.assertEqual((self.remote / 'races').read_text(), 'one attempt\n')

    def test_second_instance_fails_while_first_holds_lock_through_push(self):
        self.install_hook('pre-receive', 'touch entered\nwhile [ ! -e release ]; do sleep 0.1; done')
        first = subprocess.Popen(self.plist['ProgramArguments'], cwd=self.checkout, env=self.env,
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            until = time.monotonic() + 15
            while not (self.remote / 'entered').exists() and time.monotonic() < until and first.poll() is None:
                time.sleep(0.02)
            self.assertTrue((self.remote / 'entered').exists(), 'first instance did not reach receive hook')
            second = self.cycle()
            self.assertNotEqual(second.returncode, 0)
            self.assertIn('already running', second.stderr)
            self.assertEqual(self.heads(), self.before)
        finally:
            (self.remote / 'release').touch()
            stdout, stderr = first.communicate(timeout=15)
        self.assert_success(subprocess.CompletedProcess([], first.returncode, stdout, stderr))

    def test_no_flock_in_path_fails_at_start(self):
        (self.bin / 'flock').unlink()
        result = self.cycle()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('flock is required', result.stderr)
        self.assertFalse(self.state.exists())

    def test_leftover_database_journal_prevents_packing_and_push(self):
        (self.checkout / '.git/leave-journal').touch()
        result = self.cycle()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('no SQLite journal/WAL/SHM', result.stderr)
        self.assertNotIn('Pages prepared:', result.stdout)
        self.assertEqual(self.heads(), self.before)
        self.assertTrue((self.checkout / 'tg.db-journal').exists())
