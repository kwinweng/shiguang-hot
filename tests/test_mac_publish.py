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
(site / 'data').mkdir(exist_ok=True)  # Git does not keep the fixture's empty data/ in a fresh clone.
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
        self.git('push', 'origin', 'main')
        self.git('checkout', '-b', 'code')
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
        self.git('commit', '-m', 'Pinned publisher')
        self.git('push', 'origin', 'HEAD:main')  # Approved code is on main, as in production.
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

    def cycle(self, env=None, extra=()):
        return subprocess.run([*self.plist['ProgramArguments'], *extra], cwd=self.plist['WorkingDirectory'],
                              env=self.env if env is None else env, timeout=60, capture_output=True, text=True)

    def merge_on_main(self, files, ref='main'):
        """A reviewed change merged on GitHub: a normal descendant of remote main from another clone."""
        dev = self.root / 'dev'
        if not dev.exists():
            self.git('clone', '--quiet', self.remote.as_uri(), str(dev))
        self.git('-C', str(dev), 'fetch', '--quiet', 'origin')
        self.git('-C', str(dev), 'checkout', '--quiet', '--detach', 'origin/main')
        for name, content in files.items():
            (dev / name).parent.mkdir(parents=True, exist_ok=True)
            (dev / name).write_bytes(content) if isinstance(content, bytes) else (dev / name).write_text(content)
        self.git('-C', str(dev), 'add', '.')
        self.git('-C', str(dev), '-c', 'user.name=Dev', '-c', 'user.email=dev@localhost', 'commit', '-qm', 'Merge PR')
        sha = self.git('-C', str(dev), 'rev-parse', 'HEAD')
        self.git('-C', str(dev), 'push', '--quiet', 'origin', f'HEAD:{ref}')
        return sha

    def wrap_git(self, condition, action):
        """Run a shell action once, the first time a Git invocation matches the condition."""
        wrapper = self.bin / 'git'
        wrapper.write_text(f'''#!/bin/sh
if {condition} && [ ! -e '{self.root}/wrapped' ]; then
    touch '{self.root}/wrapped'
    {action}
fi
exec '{GIT}' "$@"
''')
        wrapper.chmod(0o755)
        self.addCleanup(lambda: wrapper.unlink(missing_ok=True))

    def published_code(self):
        return json.loads(self.git('show', f'{self.heads()[1]}:build-info.json'))['source_commit']

    def messages(self):
        with sqlite3.connect(self.checkout / 'tg.db') as connection:
            return connection.execute('select id from messages order by id').fetchall()

    def contains(self, ancestor, commit):
        return subprocess.run([GIT, 'merge-base', '--is-ancestor', ancestor, commit], cwd=self.checkout).returncode == 0

    def add_local_row(self, value):
        with sqlite3.connect(self.checkout / 'tg.db') as connection:
            connection.execute('insert into messages values (?)', (value,))

    def state_json(self, name):
        path = self.state / name
        return json.loads(path.read_text()) if path.exists() else None

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

    def test_two_cycles_in_plist_environment_with_pinned_code_and_exact_parent_trees(self):
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
        with sqlite3.connect(self.checkout / 'tg.db') as connection:
            self.assertEqual(connection.execute('select id from messages order by id').fetchall(),
                             [('after-rebang-ingest',), ('old-pipeline',)])
        self.assert_success(self.cycle())
        self.assertEqual(self.heads()[0], main, 'no DB change must not produce a data commit')
        self.assertEqual(self.git('rev-parse', self.heads()[1] + '^'), pages)
        self.assertEqual(self.git('rev-parse', 'HEAD'), self.code)
        self.assertEqual(index.read_bytes(), original_index)

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

    # Following main by trial-then-switch. Boundary cases and the expected conservative behaviour:
    #  1. normal merge (docs only)      -> publish with old code + trial; next round switches; tg.db kept
    #  2. trial build fails             -> keep publishing old code, reason in trial.json, max 3 tries per code
    #  3. trial exceeds its time limit  -> trial process group killed, recorded as failed, no stuck lock
    #  4. publisher stopped mid-trial   -> trial group killed, attempt counted, next round runs normally
    #  5. main rewritten (not a descendant) or tg.db written by others -> HALT
    #  6. merge lands during the round (before our push check or between it and push) -> no push, no HALT
    #  7. switch interrupted at any step -> next start puts the local tg.db back and continues
    #  8. switch checkout fails          -> tg.db restored, candidate dropped, old code keeps publishing
    #  9. first start where main lacks the checked-out code -> refuse without writing state
    NEW_DOCS = {'docs/NOTE.md': 'merged docs-only change\n'}

    def test_normal_merge_is_trialled_then_switched_next_round(self):
        self.assert_success(self.cycle())
        merged = self.merge_on_main(self.NEW_DOCS)
        self.add_local_row('collected-before-switch')
        first = self.cycle()
        self.assert_success(first)
        self.assertIn('follow: main advanced normally', first.stdout)
        self.assertIn(f'follow: trial passed for {merged}', first.stdout)
        self.assertEqual(self.git('rev-parse', 'HEAD'), self.code)
        self.assertEqual(self.published_code(), self.code, 'this round still publishes the running version')
        self.assertEqual(self.git('rev-parse', self.heads()[0] + '^'), merged, 'data commit sits on the merge')
        self.assertEqual(self.state_json('candidate.json')['sha'], merged)
        self.assertFalse((self.state / 'trial').exists())

        second = self.cycle()
        self.assert_success(second)
        self.assertIn(f'follow: switched code {self.code} -> {merged}', second.stdout)
        self.assertEqual(self.git('rev-parse', 'HEAD'), merged)
        self.assertEqual(self.published_code(), merged)
        self.assertTrue((self.checkout / 'docs/NOTE.md').is_file())
        self.assertIn(('collected-before-switch',), self.messages(),
                      'the switch keeps the local database, not the copy in the merge commit')
        self.assertEqual(self.git('show', f'{self.heads()[0]}:tg.db', binary=True),
                         (self.checkout / 'tg.db').read_bytes())
        for name in ('candidate.json', 'switch.json', 'tg.db.switching'):
            self.assertFalse((self.state / name).exists(), name)

        third = self.cycle()
        self.assert_success(third)
        self.assertNotIn('follow:', third.stdout, 'only our own data commits since the switch')

    def test_failed_trial_keeps_old_code_publishing_and_stops_after_three_attempts(self):
        broken = self.merge_on_main({'pipeline.py': 'raise SystemExit("broken new code")\n'})
        for attempt in (1, 2, 3):
            result = self.cycle()
            self.assert_success(result)
            self.assertIn('follow: trial FAILED', result.stdout)
            trial = self.state_json('trial.json')
            self.assertEqual((trial['ok'], trial['attempts']), (False, attempt))
            self.assertTrue(self.contains(broken, trial['sha']))
            self.assertIn('pipeline.py exited', trial['reason'])
            self.assertIn('broken new code', (self.state / 'trial.log').read_text())
        result = self.cycle()
        self.assert_success(result)
        self.assertIn('failed 3 times', result.stdout)
        self.assertNotIn('trial 4', result.stdout)
        self.assertEqual(self.git('rev-parse', 'HEAD'), self.code)
        self.assertEqual(self.published_code(), self.code)
        self.assertFalse((self.state / 'candidate.json').exists())
        fixed = self.merge_on_main({'pipeline.py': PIPELINE + '# fixed\n'})
        result = self.cycle()
        self.assertIn('follow: trial 1/3', result.stdout, 'different code is tried again')
        self.assertIn('follow: trial passed', result.stdout)
        self.assertTrue(self.contains(fixed, self.state_json('candidate.json')['sha']))

    def slow_pipeline(self):
        pid = self.root / 'trial.pid'
        return pid, PIPELINE + f'import os, time\nopen({str(pid)!r}, "w").write(str(os.getpid()))\ntime.sleep(60)\n'

    def assert_gone(self, pid):
        until = time.monotonic() + 5
        while time.monotonic() < until:
            try:
                os.kill(int(pid.read_text()), 0)
            except ProcessLookupError:
                return
            time.sleep(0.05)
        self.fail('trial process still running')

    def test_trial_timeout_kills_the_trial_and_keeps_publishing(self):
        pid, slow = self.slow_pipeline()
        merged = self.merge_on_main({'pipeline.py': slow})
        result = self.cycle(extra=('--trial-timeout', '3'))
        self.assert_success(result)
        self.assertIn('timed out after 3s', self.state_json('trial.json')['reason'])
        self.assert_gone(pid)
        self.assertFalse((self.state / 'trial').exists())
        self.assertEqual(self.published_code(), self.code)
        self.assertTrue(self.contains(merged, self.state_json('trial.json')['sha']))

    def test_stopping_the_publisher_mid_trial_kills_it_and_counts_the_attempt(self):
        pid, slow = self.slow_pipeline()
        self.merge_on_main({'pipeline.py': slow})
        publisher = subprocess.Popen(self.plist['ProgramArguments'], cwd=self.checkout, env=self.env,
                                     stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        until = time.monotonic() + 30
        while not pid.exists() and time.monotonic() < until and publisher.poll() is None:
            time.sleep(0.05)
        self.assertTrue(pid.exists(), 'trial did not start')
        published = self.heads()
        self.assertNotEqual(published, self.before, 'the real publish finishes before the trial')
        publisher.terminate()  # launchd stops jobs with SIGTERM
        publisher.communicate(timeout=15)
        self.assertNotEqual(publisher.returncode, 0)
        self.assert_gone(pid)
        self.assertEqual(self.state_json('trial.json')['reason'], 'interrupted before finishing')
        self.assertFalse((self.state / 'HALT').exists())
        pid.unlink()
        result = self.cycle(extra=('--trial-timeout', '2'))
        self.assert_success(result)
        self.assertIn('trial 2/3', result.stdout)

    def test_rewritten_main_or_foreign_database_write_halts(self):
        self.assert_success(self.cycle())
        main = self.heads()[0]
        cases = {
            'rewrite': lambda: self.git('--git-dir', str(self.remote), 'update-ref', 'refs/heads/main',
                                        self.git('--git-dir', str(self.remote), '-c', 'user.name=X', '-c',
                                                 'user.email=x@localhost', 'commit-tree', f'{main}^{{tree}}',
                                                 '-m', 'Unrelated root')),
            'database': lambda: self.merge_on_main({'tg.db': b'not ours'}),
        }
        for label, change in cases.items():
            with self.subTest(label):
                self.git('--git-dir', str(self.remote), 'update-ref', 'refs/heads/main', main)
                (self.state / 'HALT').unlink(missing_ok=True)
                change()
                result = self.cycle()
                self.assertNotEqual(result.returncode, 0)
                self.assertIn('remote refs changed since the last local checkpoint', result.stderr)
                self.assertTrue((self.state / 'HALT').exists())

    def test_merge_landing_during_the_round_skips_the_push_without_halting(self):
        self.assert_success(self.cycle())
        for label, condition in (('before-check', '[ "$1" = ls-remote ]'), ('before-push', '[ "$1" = push ]')):
            with self.subTest(label):
                (self.root / 'wrapped').unlink(missing_ok=True)
                self.add_local_row(label)  # a data commit, so main is part of the atomic push
                before = self.heads()
                merged = self.merge_on_main({f'docs/{label}.md': label}, ref=f'refs/heads/pending-{label}')
                self.wrap_git(condition, f"'{GIT}' --git-dir '{self.remote}' update-ref refs/heads/main {merged}")
                result = self.cycle()
                self.assertNotEqual(result.returncode, 0)
                self.assertIn('main advanced normally during this round', result.stderr)
                self.assertFalse((self.state / 'HALT').exists())
                self.assertEqual(self.heads(), (merged, before[1]), 'nothing of ours was published')
                (self.bin / 'git').unlink()
                result = self.cycle()
                self.assert_success(result)
                self.assertTrue(self.contains(merged, self.heads()[0]))
                self.assertEqual(self.git('show', f'{self.heads()[0]}:tg.db', binary=True),
                                 (self.checkout / 'tg.db').read_bytes(), 'the skipped data is published later')

    def test_interrupted_switch_restores_the_local_database(self):
        self.assert_success(self.cycle())
        merged = self.merge_on_main(self.NEW_DOCS)
        self.add_local_row('collected-before-switch')
        self.assert_success(self.cycle())
        self.assertEqual(self.state_json('candidate.json')['sha'], merged)
        # Killed after moving the database aside, then before or after Git's checkout finished.
        (self.state / 'switch.json').write_text(json.dumps({'from': self.code, 'to': merged}))
        (self.checkout / 'tg.db').replace(self.state / 'tg.db.switching')
        subprocess.run([GIT, 'checkout', '--quiet', '--detach', merged], cwd=self.checkout, check=True)
        result = self.cycle()
        self.assert_success(result)
        self.assertIn('closed at HEAD=' + merged, result.stdout)
        self.assertIn(('collected-before-switch',), self.messages())
        self.assertEqual(self.published_code(), merged)
        self.assertFalse((self.state / 'candidate.json').exists())
        self.assertFalse((self.state / 'tg.db.switching').exists())

    def test_switch_interrupted_before_checkout_retries_the_switch(self):
        self.assert_success(self.cycle())
        merged = self.merge_on_main(self.NEW_DOCS)
        self.add_local_row('collected-before-switch')
        self.assert_success(self.cycle())
        candidate = self.state_json('candidate.json')['sha']
        (self.state / 'switch.json').write_text(json.dumps({'from': self.code, 'to': merged}))
        (self.checkout / 'tg.db').replace(self.state / 'tg.db.switching')
        result = self.cycle()
        self.assert_success(result)
        self.assertIn('closed at HEAD=' + self.code, result.stdout)
        self.assertIn('follow: switched code', result.stdout)
        self.assertIn(('collected-before-switch',), self.messages())
        self.assertEqual(self.published_code(), candidate)
        self.assertTrue(self.contains(merged, candidate))

    def test_unexpected_database_beside_switch_is_kept_for_inspection(self):
        merged = self.merge_on_main(self.NEW_DOCS)
        self.assert_success(self.cycle())
        (self.state / 'switch.json').write_text(json.dumps({'from': self.code, 'to': merged}))
        (self.checkout / 'tg.db').replace(self.state / 'tg.db.switching')
        (self.checkout / 'tg.db').write_bytes(b'something else')
        result = self.cycle()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('unexpected tg.db', result.stderr)
        self.assertTrue((self.state / 'tg.db.switching').exists())
        self.assertEqual((self.checkout / 'tg.db').read_bytes(), b'something else')

    def test_failed_switch_checkout_keeps_old_code(self):
        merged = self.merge_on_main(self.NEW_DOCS)
        self.assert_success(self.cycle())
        database = (self.checkout / 'tg.db').read_bytes()
        self.wrap_git('[ "$3" = checkout ]', 'exit 1')
        result = self.cycle()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(f'code switch to {merged} failed', result.stderr)
        self.assertEqual((self.checkout / 'tg.db').read_bytes(), database)
        self.assertEqual(self.git('rev-parse', 'HEAD'), self.code)
        self.assertFalse((self.state / 'candidate.json').exists())
        self.assertFalse((self.state / 'switch.json').exists())
        (self.bin / 'git').unlink()
        result = self.cycle()
        self.assert_success(result)
        self.assertIn('failed 3 times', result.stdout)
        self.assertEqual(self.published_code(), self.code)

    def test_first_start_requires_main_to_contain_the_code(self):
        (self.checkout / 'local-only.txt').write_text('not on main')
        self.git('add', 'local-only.txt')
        self.git('commit', '-qm', 'Unmerged code')
        unmerged = self.git('rev-parse', 'HEAD')
        result = self.cycle(extra=())
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('remote main must contain the checked-out code', result.stderr)
        self.assertFalse((self.state / 'refs.json').exists())
        self.assertEqual(self.heads(), self.before)
        self.assertNotEqual(unmerged, self.code)
