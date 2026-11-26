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
    if Path('.git/extra-row').exists():
        db.execute("insert or ignore into messages values (?)", (Path('.git/extra-row').read_text(),))
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
        self.git('checkout', '--detach')
        self.code = self.git('rev-parse', 'HEAD')
        # Production main contains the running code; data commits sit on top of it.
        self.git('push', 'origin', 'HEAD:refs/heads/main')
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

    def cycle(self, env=None):
        return subprocess.run(self.plist['ProgramArguments'], cwd=self.plist['WorkingDirectory'],
                              env=self.env if env is None else env, timeout=30, capture_output=True, text=True)

    def install_hook(self, name, script):
        hook = self.remote / 'hooks' / name
        hook.write_text('#!/bin/sh\nset -eu\n' + script + '\n')
        hook.chmod(0o755)

    def remote_git(self, *args, index=None, input=None):
        env = dict(self.env, GIT_INDEX_FILE=str(index)) if index else self.env
        result = subprocess.run([GIT, '--git-dir', str(self.remote), '-c', 'user.name=Other', '-c',
                                 'user.email=other@localhost', *args], env=env, check=True,
                                capture_output=True, input=input)
        return result.stdout.decode().strip()

    def remote_commit(self, parent, entries, message='Merge docs change', update=True):
        """Someone else's commit on top of parent; entries map path -> (mode, bytes or blob id)."""
        index = self.root / 'other-index'
        self.remote_git('read-tree', parent, index=index)
        for path, (mode, data) in entries.items():
            blob = self.remote_git('hash-object', '-w', '--stdin', input=data) if isinstance(data, bytes) else data
            self.remote_git('update-index', '--add', '--cacheinfo', f'{mode},{blob},{path}', index=index)
        tree = self.remote_git('write-tree', index=index)
        index.unlink()
        commit = self.remote_git('commit-tree', tree, '-p', parent, '-m', message)
        if update:
            self.remote_git('update-ref', 'refs/heads/main', commit)
        return commit

    def docs_merge(self, parent, update=True):
        return self.remote_commit(parent, {'docs/note.md': ('100644', b'docs only\n')}, update=update)

    def on_first(self, command, script):
        """Wrap git: the first `git <command>` runs script first (exec real git unless it exits)."""
        wrapper = self.bin / 'git'
        wrapper.write_text(f'''#!/bin/sh
set -eu
if [ "$1" = {command} ] && [ ! -e '{self.root}/fired' ]; then
    touch '{self.root}/fired'
    {script}
fi
exec '{GIT}' "$@"
''')
        wrapper.chmod(0o755)

    def checkpoint(self):
        return json.loads((self.state / 'refs.json').read_text())

    def assert_halted(self, result):
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue((self.state / 'HALT').is_file(), result.stdout + result.stderr)
        self.assertIn('HALT exists', self.cycle().stderr)

    def assert_skipped(self, result):
        self.assertEqual(result.returncode, 75, result.stdout + result.stderr)
        self.assertIn('Mac publish skipped', result.stderr)
        self.assertFalse((self.state / 'HALT').exists())

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
        # No DB change: still a new (empty) data commit, so both refs go into one atomic push.
        self.install_hook('pre-receive', 'while read -r old new ref; do printf "%s %s\\n" "$ref" "$old" >> pushed; done')
        self.assert_success(self.cycle())
        main2, pages2 = self.heads()
        self.assertEqual(self.git('rev-parse', f'{main2}^'), main)
        self.assertEqual(self.git('rev-parse', f'{main2}^{{tree}}'), self.git('rev-parse', f'{main}^{{tree}}'))
        self.assertEqual(self.git('log', '-1', '--format=%s', main2), 'Refresh public collection data')
        self.assertEqual(self.git('rev-parse', f'{pages2}^'), pages)
        self.assertCountEqual((self.remote / 'pushed').read_text().splitlines(),
                              [f'refs/heads/main {main}', f'refs/heads/gh-pages {pages}'])
        self.assertEqual(self.checkpoint(), dict(zip(('refs/heads/main', 'refs/heads/gh-pages'), (main2, pages2))))
        # The empty data commit is recognised as ours next round (no "advanced normally", no HALT).
        third = self.cycle()
        self.assert_success(third)
        self.assertNotIn('main advanced normally', third.stdout)
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
        self.assertIn('[remote rejected] (atomic push failure)', result.stdout)  # porcelain receipt
        self.assertIn('HALT kept', result.stderr)
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

    # --- main moves on while the code stays pinned -------------------------------------

    def test_docs_merge_on_main_keeps_publishing_with_pinned_code(self):
        self.assert_success(self.cycle())
        main1, pages1 = self.heads()
        docs = self.docs_merge(main1)
        (self.checkout / '.git/extra-row').write_text('after-docs-merge')
        result = self.cycle()
        self.assert_success(result)
        self.assertIn('main advanced normally', result.stdout)
        main2, pages2 = self.heads()
        self.assertEqual(self.git('rev-parse', f'{main2}^'), docs)
        self.assertEqual(self.git('diff-tree', '--no-commit-id', '--name-only', '-r', docs, main2), 'tg.db')
        self.assertEqual(self.git('rev-parse', f'{pages2}^'), pages1)
        self.assertEqual(json.loads(self.git('show', f'{pages2}:build-info.json'))['source_commit'], self.code)
        self.assertEqual(self.checkpoint(), dict(zip(('refs/heads/main', 'refs/heads/gh-pages'), (main2, pages2))))
        self.assertEqual(self.git('rev-parse', 'HEAD'), self.code)
        # Another docs merge with no database change: an empty data commit on it, Pages advances.
        docs2 = self.docs_merge(main2)
        self.assert_success(self.cycle())
        self.assertEqual(self.git('rev-parse', f'{self.heads()[0]}^'), docs2)
        self.assertEqual(self.git('rev-parse', f'{self.heads()[0]}^{{tree}}'), self.git('rev-parse', f'{docs2}^{{tree}}'))
        self.assertEqual(self.git('rev-parse', f'{self.heads()[1]}^'), pages2)

    def test_merge_after_ls_remote_without_db_change_skips_round_then_recovers(self):
        self.assert_success(self.cycle())
        main1, pages1 = self.heads()
        docs = self.docs_merge(main1, update=False)
        self.on_first('push', f"'{GIT}' --git-dir '{self.remote}' update-ref refs/heads/main {docs}")
        result = self.cycle()
        self.assert_skipped(result)
        self.assertIn('[rejected] (stale info)', result.stdout)
        self.assertEqual(self.heads(), (docs, pages1), 'gh-pages must not advance on a stale main')
        self.assertEqual(self.checkpoint(), dict(zip(('refs/heads/main', 'refs/heads/gh-pages'), (main1, pages1))))
        self.assert_success(self.cycle())
        self.assertEqual(self.git('rev-parse', f'{self.heads()[0]}^'), docs)
        self.assertEqual(self.git('rev-parse', f'{self.heads()[1]}^'), pages1)

    def test_lease_rejection_with_db_change_and_normal_merge_skips_round(self):
        docs = self.docs_merge(self.before[0], update=False)
        self.on_first('push', f"'{GIT}' --git-dir '{self.remote}' update-ref refs/heads/main {docs}")
        result = self.cycle()
        self.assert_skipped(result)
        self.assertIn('checkpoint unchanged', result.stderr)
        self.assertEqual(self.heads(), (docs, self.before[1]))
        # First round: the skip leaves the initial checkpoint (the refs it built on), not the candidates.
        self.assertEqual(self.checkpoint(), dict(zip(('refs/heads/main', 'refs/heads/gh-pages'), self.before)))
        self.assert_success(self.cycle())
        self.assertEqual(self.git('rev-parse', f'{self.heads()[0]}^'), docs)
        self.assertEqual(self.git('rev-parse', f'{self.heads()[1]}^'), self.before[1])

    def test_merge_during_collection_skips_without_push(self):
        docs = self.docs_merge(self.before[0], update=False)
        self.on_first('ls-remote', f"'{GIT}' --git-dir '{self.remote}' update-ref refs/heads/main {docs}")
        self.install_hook('pre-receive', 'touch push-attempt')
        self.assert_skipped(self.cycle())
        self.assertFalse((self.remote / 'push-attempt').exists())
        self.assertEqual(self.heads(), (docs, self.before[1]))
        self.assertEqual(self.checkpoint(), dict(zip(('refs/heads/main', 'refs/heads/gh-pages'), self.before)))

    def test_pages_rewound_to_ancestor_between_ls_remote_and_push_halts(self):
        self.assert_success(self.cycle())
        main1, pages1 = self.heads()
        # Without the explicit lease this would be a fast-forward and would clear HALT.
        self.on_first('push', f"'{GIT}' --git-dir '{self.remote}' update-ref refs/heads/gh-pages {self.before[1]}")
        self.assert_halted(self.cycle())
        self.assertEqual(self.heads(), (main1, self.before[1]))

    def test_pages_rewound_to_ancestor_before_round_halts(self):
        self.assert_success(self.cycle())
        main1, _ = self.heads()
        self.remote_git('update-ref', 'refs/heads/gh-pages', self.before[1])
        self.assert_halted(self.cycle())
        self.assertEqual(self.heads(), (main1, self.before[1]))

    def test_push_disconnect_with_concurrent_merge_keeps_halt(self):
        docs = self.docs_merge(self.before[0], update=False)
        self.on_first('push', f"'{GIT}' --git-dir '{self.remote}' update-ref refs/heads/main {docs}\n"
                              "    echo 'fatal: the remote end hung up unexpectedly' >&2\n    exit 128")
        self.assert_halted(self.cycle())
        self.assertEqual(self.heads(), (docs, self.before[1]))

    def test_main_history_rewrite_halts(self):
        self.assert_success(self.cycle())
        main1, pages1 = self.heads()
        rewritten = self.remote_git('commit-tree', f'{main1}^{{tree}}', '-p', f'{main1}^', '-m', 'Rewritten')
        self.remote_git('update-ref', 'refs/heads/main', rewritten)
        self.assert_halted(self.cycle())
        self.assertEqual(self.heads(), (rewritten, pages1))

    def test_someone_else_changing_tg_db_halts(self):
        self.assert_success(self.cycle())
        main1, pages1 = self.heads()
        other = self.remote_commit(main1, {'tg.db': ('100644', b'not our database')})
        self.assert_halted(self.cycle())
        self.assertEqual(self.heads(), (other, pages1))

    def test_tg_db_mode_only_change_halts(self):
        self.assert_success(self.cycle())
        main1, pages1 = self.heads()
        other = self.remote_commit(main1, {'tg.db': ('100755', self.git('rev-parse', f'{main1}:tg.db'))})
        self.assert_halted(self.cycle())
        self.assertEqual(self.heads(), (other, pages1))

    def test_first_start_refuses_when_main_lacks_code_sha(self):
        self.remote_git('update-ref', 'refs/heads/main', f'{self.code}^')
        heads = self.heads()
        database = (self.checkout / 'tg.db').read_bytes()
        result = self.cycle()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('remote main must contain --code-sha', result.stderr)
        self.assertFalse((self.state / 'refs.json').exists())
        self.assertFalse((self.state / 'HALT').exists())
        self.assertEqual(self.heads(), heads)
        self.assertEqual((self.checkout / 'tg.db').read_bytes(), database)

    # --- review round 2: boundary cases ------------------------------------------------
    #  1. no DB change still yields a main data commit; both refs in one atomic push
    #     (covered in test_two_cycles_in_plist_environment_with_pinned_code_and_exact_parent_trees)
    #  2. main's tg.db changed after the server advertised refs (inside the push) -> rejected, HALT kept
    #  3. gh-pages seen rewound at ls-remote, restored before the re-read -> HALT, never skip
    #  4. receipt shows gh-pages stale (even if restored before the re-read) -> HALT
    #  5. checkpoint SHAs well-formed but missing / not a commit -> HALT, file and DB preserved
    #  6. remote reachable but gh-pages (or main) missing -> HALT; remote unreachable -> exit 1, no HALT
    #  7. receipt truncated (no Done) / only one ref line / push timeout -> HALT

    def run_then(self, after, filter_output='cat'):
        """Shell for on_first: run the real command, then `after`, then replay its stdout through filter."""
        return (f"out=$('{GIT}' \"$@\") && code=0 || code=$?\n    {after}\n"
                f"    printf '%s\\n' \"$out\" | {filter_output}\n    exit $code")

    def test_tg_db_change_on_main_inside_push_is_rejected_and_halts(self):
        self.assert_success(self.cycle())
        main1, pages1 = self.heads()
        other = self.remote_commit(main1, {'tg.db': ('100644', b'not our database')}, update=False)
        # Runs after the server advertised main1, before its ref transaction: only a real main
        # update in the same atomic transaction notices it. This round has no DB change.
        self.install_hook('pre-receive', f'cat >/dev/null\nenv -u GIT_QUARANTINE_PATH git update-ref refs/heads/main {other}')
        result = self.cycle()
        self.assertIn('[remote rejected] (atomic transaction failed)', result.stdout)
        self.assert_halted(result)
        self.assertEqual(self.heads(), (other, pages1), 'old-database pages must not be published')
        self.assertEqual(self.checkpoint(), dict(zip(('refs/heads/main', 'refs/heads/gh-pages'), (main1, pages1))))

    def test_pages_rewound_at_ls_remote_then_restored_halts(self):
        self.assert_success(self.cycle())
        main1, pages1 = self.heads()
        docs = self.docs_merge(main1, update=False)
        rgit = f"'{GIT}' --git-dir '{self.remote}' update-ref"
        self.on_first('ls-remote', f"{rgit} refs/heads/main {docs}; {rgit} refs/heads/gh-pages {self.before[1]}\n    "
                      + self.run_then(f'{rgit} refs/heads/gh-pages {pages1}'))
        self.install_hook('pre-receive', 'touch push-attempt')
        self.assert_halted(self.cycle())
        self.assertFalse((self.remote / 'push-attempt').exists())
        self.assertEqual(self.heads(), (docs, pages1))

    def test_receipt_with_pages_stale_halts_even_if_restored(self):
        self.assert_success(self.cycle())
        main1, pages1 = self.heads()
        docs = self.docs_merge(main1, update=False)
        rgit = f"'{GIT}' --git-dir '{self.remote}' update-ref"
        self.on_first('push', f"{rgit} refs/heads/main {docs}; {rgit} refs/heads/gh-pages {self.before[1]}\n    "
                      + self.run_then(f'{rgit} refs/heads/gh-pages {pages1}'))
        result = self.cycle()
        self.assertIn('refs/heads/gh-pages\t[rejected] (stale info)', result.stdout)
        self.assert_halted(result)
        self.assertEqual(self.heads(), (docs, pages1))

    def test_checkpoint_with_missing_or_non_commit_sha_halts(self):
        for value in ('0' * 40, None):
            with self.subTest(value=value):
                self.setUp()
                self.assert_success(self.cycle())
                main1, pages1 = self.heads()
                if value is None:
                    value = self.git('rev-parse', f'{main1}^{{tree}}')  # exists, but is a tree
                text = json.dumps({'refs/heads/main': value, 'refs/heads/gh-pages': pages1}) + '\n'
                (self.state / 'refs.json').write_text(text)
                database = (self.checkout / 'tg.db').read_bytes()
                result = self.cycle()
                self.assertIn('is unreadable (not a usable local commit', result.stderr)
                self.assert_halted(result)
                self.assertEqual((self.state / 'refs.json').read_text(), text)
                self.assertEqual((self.checkout / 'tg.db').read_bytes(), database)
                self.assertEqual(self.heads(), (main1, pages1))

    def test_missing_remote_branch_halts(self):
        for branch in ('gh-pages', 'main'):
            with self.subTest(branch=branch):
                self.setUp()
                self.assert_success(self.cycle())
                self.remote_git('update-ref', '-d', f'refs/heads/{branch}')
                heads = self.git('--git-dir', str(self.remote), 'for-each-ref')
                result = self.cycle()
                self.assertIn('lacks', result.stderr)
                self.assert_halted(result)
                self.assertEqual(self.git('--git-dir', str(self.remote), 'for-each-ref'), heads)

    def test_unreachable_remote_fails_without_halt(self):
        self.assert_success(self.cycle())
        self.git('remote', 'set-url', 'origin', (self.root / 'gone.git').as_uri())
        result = self.cycle()
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertFalse((self.state / 'HALT').exists())
        self.git('remote', 'set-url', 'origin', self.remote.as_uri())
        self.assert_success(self.cycle())

    def test_unclear_push_receipt_keeps_halt(self):
        for name, flt in (('truncated', "grep -v '^Done$'"), ('one ref', 'grep -v gh-pages')):
            with self.subTest(name):
                self.setUp()
                rgit = f"'{GIT}' --git-dir '{self.remote}' update-ref"
                docs = self.docs_merge(self.before[0], update=False)
                self.on_first('push', f'{rgit} refs/heads/main {docs}\n    ' + self.run_then(':', flt))
                result = self.cycle()
                self.assertIn('[rejected] (stale info)', result.stdout)
                self.assert_halted(result)
                self.assertEqual(self.heads(), (docs, self.before[1]))

    # --- review round 3: a failed initial fetch, and receipts with stray lines ----------
    #  8. fetch reports gh-pages missing, branch restored before any re-check -> HALT
    #  9. fetch reports a missing ref, then the remote disconnects -> HALT (no network excuse)
    # 10. fetch fails like a network error, ls-remote then shows gh-pages rewound -> HALT
    # 11. fetch fails like a network error, ls-remote shows nothing odd -> HALT (cause unknown)
    # 12. fetch and ls-remote both fail on the network -> exit 1, no HALT, then publishes normally
    #     (test_unreachable_remote_fails_without_halt)
    # 13. receipt matches but carries one extra, incomplete status line -> HALT

    NETWORK_ERROR = "echo 'fatal: unable to access remote: Could not resolve host' >&2\n    exit 128"

    def test_fetch_reports_missing_pages_then_restored_halts(self):
        self.assert_success(self.cycle())
        main1, pages1 = self.heads()
        rgit = f"'{GIT}' --git-dir '{self.remote}' update-ref"
        self.on_first('fetch', f'{rgit} -d refs/heads/gh-pages\n    '
                      + self.run_then(f'{rgit} refs/heads/gh-pages {pages1}'))
        result = self.cycle()
        self.assertIn("couldn't find remote ref", result.stderr)
        self.assertIn('lacks', result.stderr)
        self.assert_halted(result)
        self.assertEqual(self.heads(), (main1, pages1))

    def test_fetch_reports_missing_ref_then_remote_disconnects_halts(self):
        self.assert_success(self.cycle())
        gone = self.root / 'gone.git'
        self.on_first('fetch', f"'{GIT}' --git-dir '{self.remote}' update-ref -d refs/heads/gh-pages\n    "
                      + self.run_then(f"mv '{self.remote}' '{gone}'"))
        result = self.cycle()
        self.assertIn("couldn't find remote ref", result.stderr)
        self.assert_halted(result)
        self.assertFalse(self.remote.exists())

    def test_fetch_failure_then_pages_rewound_at_ls_remote_halts(self):
        self.assert_success(self.cycle())
        main1, _ = self.heads()
        self.on_first('fetch', f"'{GIT}' --git-dir '{self.remote}' update-ref refs/heads/gh-pages {self.before[1]}\n"
                               f'    {self.NETWORK_ERROR}')
        result = self.cycle()
        self.assertIn('differs from the checkpoint', result.stderr)
        self.assert_halted(result)
        self.assertEqual(self.heads(), (main1, self.before[1]))

    def test_fetch_failure_with_reachable_consistent_remote_halts(self):
        self.assert_success(self.cycle())
        heads = self.heads()
        self.on_first('fetch', self.NETWORK_ERROR)
        result = self.cycle()
        self.assertIn('cause unknown', result.stderr)
        self.assert_halted(result)
        self.assertEqual(self.heads(), heads)

    def test_receipt_with_extra_incomplete_status_line_halts(self):
        rgit = f"'{GIT}' --git-dir '{self.remote}' update-ref"
        docs = self.docs_merge(self.before[0], update=False)
        extra = "awk 'NR==1{print; print \"!\\trefs/heads/main\"; next} {print}'"
        self.on_first('push', f'{rgit} refs/heads/main {docs}\n    ' + self.run_then(':', extra))
        result = self.cycle()
        self.assertIn('[rejected] (stale info)', result.stdout)
        self.assertIn('!\trefs/heads/main\n', result.stdout)
        self.assert_halted(result)
        self.assertEqual(self.heads(), (docs, self.before[1]))

    def test_push_timeout_keeps_halt(self):
        self.on_first('push', 'exec sleep 30')
        driver = ("import sys; sys.path.insert(0, 'tools'); import mac_publish; mac_publish.PUSH_TIMEOUT = 2; "
                  f"sys.argv = ['mac_publish.py', '--code-sha', '{self.code}']; sys.exit(mac_publish.main())")
        result = subprocess.run([sys.executable, '-c', driver], cwd=self.checkout, env=self.env,
                                timeout=60, capture_output=True, text=True)
        self.assertIn('timed out', result.stderr)
        self.assert_halted(result)
        self.assertEqual(self.heads(), self.before)

    def test_corrupt_checkpoint_halts_and_preserves_state(self):
        self.assert_success(self.cycle())
        heads = self.heads()
        (self.state / 'refs.json').write_text('{"refs/heads/main": ')
        database = (self.checkout / 'tg.db').read_bytes()
        self.assert_halted(self.cycle())
        self.assertEqual((self.state / 'refs.json').read_text(), '{"refs/heads/main": ')
        self.assertEqual((self.checkout / 'tg.db').read_bytes(), database)
        self.assertEqual(self.heads(), heads)

    # --- optional X inbox (REBANG_X_INBOX_REPO) ------------------------------------------------

    def pin_inbox_code(self):
        """Pin a code commit that also carries the receiver and the real X reader it validates with."""
        for path in ('tools/x_inbox.py', 'rebang/bloggers/__init__.py', 'rebang/bloggers/x.py',
                     'rebang/bloggers/common.py'):
            shutil.copyfile(ROOT / path, self.checkout / path)
        # The stub collector records which X batches it could see when it ran.
        (self.checkout / 'rebang/bloggers/__main__.py').write_text(
            "import os, pathlib\nroot = pathlib.Path('var/rebang/x-dump')\n"
            "pathlib.Path('.git/bloggers-saw').write_text(' '.join(sorted(os.listdir(root))) if root.is_dir() else '')\n")
        self.git('add', '.')
        self.git('commit', '-m', 'Pin X inbox receiver')
        self.code = self.git('rev-parse', 'HEAD')
        self.git('push', 'origin', 'HEAD:refs/heads/main')
        self.plist['ProgramArguments'][3] = self.code
        self.before = self.heads()

    def inbox_leftovers(self):
        var = self.checkout / 'var/rebang'
        return [p.name for p in var.iterdir() if p.name.startswith('.x-inbox')] if var.is_dir() else []

    def test_x_inbox_unset_changes_nothing(self):
        result = self.cycle()
        self.assert_success(result)
        self.assertNotIn('x_inbox', result.stdout + result.stderr)
        self.assertFalse((self.checkout / 'var/rebang/x-dump').exists())
        self.assertEqual(self.inbox_leftovers(), [])

    def test_x_inbox_batch_is_installed_before_collection(self):
        from tests.test_x_inbox import InboxRepo, batch
        self.pin_inbox_code()
        repo = InboxRepo(self.root)
        dump_id, *_ = new = batch()
        repo.publish(new)
        result = self.cycle(dict(self.env, REBANG_X_INBOX_REPO=repo.url))
        self.assert_success(result)
        self.assertIn(f'x_inbox=ok installed={dump_id}', result.stdout)
        self.assertNotIn(repo.url, result.stdout + result.stderr)
        self.assertEqual((self.checkout / '.git/bloggers-saw').read_text(), dump_id)
        self.assertEqual(self.inbox_leftovers(), [])
        self.assertEqual(self.git('rev-parse', 'HEAD'), self.code)

    def test_x_inbox_failure_still_publishes_without_halt(self):
        self.pin_inbox_code()
        missing = (self.root / 'missing-inbox.git').as_uri()
        result = self.cycle(dict(self.env, REBANG_X_INBOX_REPO=missing))
        self.assert_success(result)
        self.assertIn('x_inbox=error code=x_inbox_fetch_failed installed=none', result.stdout)
        self.assertNotIn('missing-inbox', result.stdout + result.stderr)
        self.assertEqual(self.inbox_leftovers(), [])
