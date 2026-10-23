"""Exercise real Git rejection paths and external-trigger success/failure reporting."""
import contextlib
import hashlib
import io
import json
import os
import shlex
import subprocess
import sqlite3
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from tools import dispatch_hourly
from tools import box_scrape
from tools.write_build_info import write_info

ROOT = Path(__file__).resolve().parent.parent


class PersistenceEnvironmentTests(unittest.TestCase):
    def test_publish_permission_is_scoped_to_main_push(self):
        script = (ROOT / 'tools/persist_action_data.sh').read_text()
        lines = [line.strip() for line in script.splitlines() if 'ALLOW_MAIN_PUSH' in line]
        self.assertEqual(len(lines), 2)
        for line in lines:
            self.assertIn('ALLOW_MAIN_PUSH=publish git push origin HEAD:refs/heads/main', line)
            self.assertNotIn('export', line)


class DatabasePersistenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.remote = self.base / 'remote.git'
        self.run_git(self.base, 'init', '--bare', '--initial-branch=main', str(self.remote))
        self.repo = self.base / 'checkout'
        self.run_git(self.base, 'clone', str(self.remote), str(self.repo))
        # Local fixtures must use their own hooks, independent of host policy hooks.
        self.run_git(self.repo, 'config', 'core.hooksPath', '.git/hooks')
        self.run_git(self.repo, 'config', 'user.name', 'test')
        self.run_git(self.repo, 'config', 'user.email', 'test@local.invalid')
        (self.repo / '.git/info/exclude').write_text('/site/\n')
        (self.repo / 'tg.db').write_bytes(b'original')
        (self.repo / 'public-feeds').mkdir()
        (self.repo / 'public-feeds/sample.json').write_text('{}')
        self.run_git(self.repo, 'add', '.')
        self.run_git(self.repo, 'commit', '-m', 'seed')
        self.run_git(self.repo, 'push', 'origin', 'main')

    def run_git(self, directory, *args):
        return subprocess.check_output(['git', '-C', str(directory), *args], stderr=subprocess.PIPE, text=True).strip()

    def persist(self):
        return subprocess.run(['sh', str(ROOT / 'tools/persist_action_data.sh')],
                              cwd=self.repo, capture_output=True, text=True)

    def test_no_change_does_not_commit_or_contact_remote(self):
        before = self.run_git(self.repo, 'rev-parse', 'HEAD')
        self.run_git(self.repo, 'remote', 'set-url', 'origin', str(self.base / 'missing.git'))
        self.assertEqual(self.persist().returncode, 0)
        self.assertEqual(self.run_git(self.repo, 'rev-parse', 'HEAD'), before)

    def test_unrelated_staged_files_prevent_reset(self):
        (self.repo / 'tg.db').write_bytes(b'new data')
        (self.repo / 'unrelated').write_text('do not publish')
        self.run_git(self.repo, 'add', 'unrelated')
        self.assertNotEqual(self.persist().returncode, 0)
        self.assertEqual(self.run_git(self.remote, 'show', 'main:tg.db'), 'original')
        self.assertNotIn('unrelated', self.run_git(self.remote, 'ls-tree', '--name-only', 'main'))
        self.assertEqual(self.run_git(self.repo, 'diff', '--cached', '--name-only'), 'unrelated')

    def other_writer(self):
        other = self.base / 'other'
        self.run_git(self.base, 'clone', str(self.remote), str(other))
        self.run_git(other, 'config', 'core.hooksPath', '.git/hooks')
        self.run_git(other, 'config', 'user.name', 'test')
        self.run_git(other, 'config', 'user.email', 'test@local.invalid')
        return other

    def test_remote_feed_advance_is_preserved(self):
        other = self.other_writer()
        (other / 'public-feeds/sample.json').write_text('{"new":true}')
        self.run_git(other, 'commit', '-am', 'new feed')
        self.run_git(other, 'push', 'origin', 'main')
        remote_head = self.run_git(self.remote, 'rev-parse', 'main')
        (self.repo / 'tg.db').write_bytes(b'collected data')
        result = self.persist()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.run_git(self.remote, 'rev-parse', 'main^'), remote_head)
        self.assertEqual(self.run_git(self.remote, 'show', 'main:tg.db'), 'collected data')

    def race_hook(self, db=False, twice=False):
        other = self.other_writer()
        # A local pre-push hook advances the bare remote before send-pack runs.
        hook = self.repo / '.git/hooks/pre-push'
        target = 'tg.db' if db else 'public-feeds/sample.json'
        hook.write_text(f'''#!/bin/sh
set -eu
if [ -f .git/raced ] && [ "{int(twice)}" = 0 ]; then exit 0; fi
touch .git/raced
printf x >> '{other / target}'
git -C '{other}' commit -am race >/dev/null
git -C '{other}' push origin main >/dev/null
''')
        hook.chmod(0o755)
        return other

    def test_concurrent_feed_push_retries_once_with_linear_history(self):
        self.race_hook()
        (self.repo / 'tg.db').write_bytes(b'collected data')
        result = self.persist()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('rejected', result.stderr)
        self.assertEqual(self.run_git(self.remote, 'rev-list', '--count', 'main'), '3')
        self.assertEqual(self.run_git(self.remote, 'rev-list', '--merges', 'main'), '')
        self.assertEqual(self.run_git(self.remote, 'show', 'main:public-feeds/sample.json'), '{}x')
        self.assertEqual(self.run_git(self.remote, 'show', 'main:tg.db'), 'collected data')

    def test_both_push_attempts_scope_publish_permission_at_runtime(self):
        import shutil
        real_git = shutil.which('git')
        self.race_hook()
        (self.repo / 'tg.db').write_bytes(b'collected data')
        commands = self.base / 'commands'
        commands.mkdir()
        calls = self.base / 'calls'
        wrapper = commands / 'git'
        # Ignore the concurrent writer's explicit -C calls inside the test hook.
        wrapper.write_text(f'''#!/bin/sh
if [ "$1" != -C ]; then
    printf '%s|%s\\n' "$*" "${{ALLOW_MAIN_PUSH-unset}}" >> {shlex.quote(str(calls))}
fi
exec {shlex.quote(real_git)} "$@"
''')
        wrapper.chmod(0o755)
        env = dict(os.environ, PATH=str(commands) + os.pathsep + os.environ['PATH'])
        env.pop('ALLOW_MAIN_PUSH', None)
        result = subprocess.run(
            ['sh', '-c', '. "$1"; git status --short', 'test', str(ROOT / 'tools/persist_action_data.sh')],
            cwd=self.repo, env=env, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        recorded = [line.rsplit('|', 1) for line in calls.read_text().splitlines()]
        pushes = [args for args, value in recorded if value == 'publish']
        self.assertEqual(pushes, ['push origin HEAD:refs/heads/main'] * 2)
        self.assertTrue(all(value == 'unset' for args, value in recorded
                            if args != 'push origin HEAD:refs/heads/main'))
        self.assertEqual(recorded[-1], ['status --short', 'unset'])

    def test_second_rejection_stops_without_force(self):
        self.race_hook(twice=True)
        (self.repo / 'tg.db').write_bytes(b'collected data')
        self.assertNotEqual(self.persist().returncode, 0)
        self.assertEqual(self.run_git(self.remote, 'show', 'main:tg.db'), 'original')
        self.assertEqual(self.run_git(self.remote, 'rev-list', '--count', 'main'), '3')
        self.assert_backup()

    def assert_backup(self):
        backups = list((self.repo / '.git').glob('persist-db.*/tg.db'))
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_bytes(), b'collected data')

    def test_remote_db_writer_aborts_and_keeps_backup(self):
        self.race_hook(db=True)
        (self.repo / 'tg.db').write_bytes(b'collected data')
        result = self.persist()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Remote changed tg.db', result.stderr)
        self.assertEqual(self.run_git(self.remote, 'show', 'main:tg.db'), 'originalx')
        self.assert_backup()

    def test_remote_sqlite_change_before_fetch_keeps_binary_backup(self):
        (self.repo / 'tg.db').unlink()
        with contextlib.closing(sqlite3.connect(self.repo / 'tg.db')) as db, db:
            db.execute('create table sample(value text)')
        self.run_git(self.repo, 'commit', '-am', 'sqlite seed')
        self.run_git(self.repo, 'push', 'origin', 'main')
        other = self.other_writer()
        with contextlib.closing(sqlite3.connect(other / 'tg.db')) as db, db:
            db.execute("insert into sample values ('remote')")
        self.run_git(other, 'commit', '-am', 'remote database')
        self.run_git(other, 'push', 'origin', 'main')
        remote_head = self.run_git(self.remote, 'rev-parse', 'main')
        with contextlib.closing(sqlite3.connect(self.repo / 'tg.db')) as db, db:
            db.execute("insert into sample values ('local')")
        snapshot = (self.repo / 'tg.db').read_bytes()
        result = self.persist()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Remote changed tg.db', result.stderr)
        backups = list((self.repo / '.git').glob('persist-db.*/tg.db'))
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_bytes(), snapshot)
        self.assertEqual(self.run_git(self.remote, 'rev-parse', 'main'), remote_head)

    def test_initial_sync_recovers_data_commit_with_backup_branch(self):
        other = self.other_writer()
        (other / 'public-feeds/sample.json').write_text('new feed')
        self.run_git(other, 'commit', '-am', 'feed')
        self.run_git(other, 'push', 'origin', 'main')
        (self.repo / 'tg.db').write_bytes(b'leftover')
        self.run_git(self.repo, 'commit', '-am', 'leftover data')
        old = self.run_git(self.repo, 'rev-parse', 'HEAD')
        with patch.object(box_scrape, 'run_pipeline', side_effect=RuntimeError('stop before scrape')):
            with self.assertRaisesRegex(RuntimeError, 'stop before scrape'):
                box_scrape.execute(SimpleNamespace(checkout=self.repo, test_dir=None))
        self.assertEqual(self.run_git(self.repo, 'rev-parse', f'backup/{old}'), old)
        self.assertEqual(self.run_git(self.repo, 'show', f'backup/{old}:tg.db'), 'leftover')
        self.assertEqual(self.run_git(self.repo, 'rev-parse', 'HEAD'),
                         self.run_git(self.remote, 'rev-parse', 'main'))

    def test_initial_sync_refuses_unpushed_non_db_commit(self):
        (self.repo / 'public-feeds/sample.json').write_text('local feed')
        self.run_git(self.repo, 'commit', '-am', 'local feed')
        old = self.run_git(self.repo, 'rev-parse', 'HEAD')
        with patch.object(box_scrape, 'run_pipeline') as pipeline:
            with self.assertRaisesRegex(RuntimeError, 'outside tg.db'):
                box_scrape.execute(SimpleNamespace(checkout=self.repo, test_dir=None))
        pipeline.assert_not_called()
        self.assertEqual(self.run_git(self.repo, 'rev-parse', 'HEAD'), old)

    def test_commit_hook_failure_is_not_ignored(self):
        hook = self.repo / '.git/hooks/pre-commit'
        hook.write_text('#!/bin/sh\nexit 1\n')
        hook.chmod(0o755)
        (self.repo / 'tg.db').write_bytes(b'collected data')
        self.assertNotEqual(self.persist().returncode, 0)
        self.assertEqual(self.run_git(self.remote, 'show', 'main:tg.db'), 'original')
        self.assert_backup()

    def snapshot(self):
        return (self.run_git(self.repo, 'rev-parse', 'HEAD'),
                (self.repo / '.git/index').read_bytes(),
                {str(path.relative_to(self.repo)): path.read_bytes()
                 for path in self.repo.rglob('*')
                 if path.is_file() and '.git' not in path.relative_to(self.repo).parts})

    def test_dirty_checkout_refused_at_sync_and_persist(self):
        for stage in ('sync', 'persist'):
            for dirty in ('unstaged', 'untracked'):
                for db_changed in (False, True):
                    with self.subTest(stage=stage, dirty=dirty, db_changed=db_changed):
                        path = self.repo / ('public-feeds/sample.json' if dirty == 'unstaged' else 'untracked')
                        path.write_bytes(b'keep this file')
                        if db_changed:
                            (self.repo / 'tg.db').write_bytes(b'collected data')
                        before = self.snapshot()
                        if stage == 'sync':
                            with patch.object(box_scrape, 'run_pipeline') as pipeline:
                                with self.assertRaisesRegex(RuntimeError, 'clean worktree'):
                                    box_scrape.execute(SimpleNamespace(checkout=self.repo, test_dir=None))
                            pipeline.assert_not_called()
                        else:
                            result = self.persist()
                            self.assertNotEqual(result.returncode, 0, result.stdout)
                            self.assertIn('changes outside tg.db', result.stderr)
                        self.assertEqual(self.snapshot(), before)
                        if dirty == 'untracked':
                            path.unlink()
                        else:
                            path.write_text('{}')
                        (self.repo / 'tg.db').write_bytes(b'original')

    def test_initial_sync_refuses_merge_even_when_only_db_differs(self):
        self.check_local_merge_refused(change_code=False)

    def test_initial_sync_refuses_merge_with_code_change(self):
        self.check_local_merge_refused(change_code=True)

    def check_local_merge_refused(self, change_code):
        self.run_git(self.repo, 'checkout', '-b', 'side')
        (self.repo / 'tg.db').write_bytes(b'side data')
        self.run_git(self.repo, 'commit', '-am', 'side database')
        self.run_git(self.repo, 'checkout', 'main')
        self.run_git(self.repo, 'merge', '--no-ff', '--no-commit', 'side')
        if change_code:
            (self.repo / 'pipeline.py').write_text('# merge-only code change\n')
            self.run_git(self.repo, 'add', 'pipeline.py')
        self.run_git(self.repo, 'commit', '-m', 'local merge')
        before = self.snapshot()
        with patch.object(box_scrape, 'run_pipeline') as pipeline:
            with self.assertRaisesRegex(RuntimeError, 'refusing reset'):
                box_scrape.execute(SimpleNamespace(checkout=self.repo, test_dir=None))
        pipeline.assert_not_called()
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(self.run_git(self.repo, 'branch', '--list', 'backup/*'), '')

    def test_initial_sync_backup_collision_does_not_overwrite(self):
        original = self.run_git(self.repo, 'rev-parse', 'HEAD')
        (self.repo / 'tg.db').write_bytes(b'leftover')
        self.run_git(self.repo, 'commit', '-am', 'leftover data')
        head = self.run_git(self.repo, 'rev-parse', 'HEAD')
        backup = f'backup/{head}'
        self.run_git(self.repo, 'branch', backup, original)
        before = self.snapshot()
        with patch.object(box_scrape, 'run_pipeline') as pipeline:
            with self.assertRaisesRegex(RuntimeError, 'already exists at another commit'):
                box_scrape.execute(SimpleNamespace(checkout=self.repo, test_dir=None))
        pipeline.assert_not_called()
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(self.run_git(self.repo, 'rev-parse', backup), original)

    def test_build_info_identifies_real_inputs_before_database_commit(self):
        source = self.run_git(self.repo, 'rev-parse', 'HEAD')
        (self.repo / 'site').mkdir()
        (self.repo / 'site/index.html').write_text('public build')
        (self.repo / 'tg.db').write_bytes(b'fresh collected data')
        with patch.dict(os.environ, {'GITHUB_EVENT_NAME': 'workflow_dispatch', 'GITHUB_RUN_ID': '123'}):
            info = write_info(self.repo)
        self.assertEqual(info['source_commit'], source)
        self.assertEqual(info['public_feeds_tree'], self.run_git(self.repo, 'rev-parse', 'HEAD:public-feeds'))
        self.assertEqual(info['database_sha256'], hashlib.sha256(b'fresh collected data').hexdigest())
        self.assertEqual(self.persist().returncode, 0)
        self.assertNotEqual(info['source_commit'], self.run_git(self.repo, 'rev-parse', 'HEAD'))
        self.assertEqual(info, json.loads((self.repo / 'site/build-info.json').read_text()))


class ExternalDispatchTests(unittest.TestCase):
    def invoke(self, fake, args=()):
        output = io.StringIO()
        with patch.object(dispatch_hourly, 'gh', side_effect=fake), \
             patch.object(dispatch_hourly.uuid, 'uuid4', return_value=SimpleNamespace(hex='test-id')), \
             contextlib.redirect_stdout(output):
            code = dispatch_hourly.main(list(args))
        return code, [json.loads(line) for line in output.getvalue().splitlines()]

    def matching_run(self, **extra):
        return dict(databaseId=99, displayTitle='hourly / workflow_dispatch / bot-test-id',
                    url='https://github.com/kwinweng/shiguang-hot/actions/runs/99',
                    status='in_progress', conclusion='', **extra)

    def test_read_check_does_not_dispatch_or_claim_write_permission(self):
        calls = []
        def fake(*args, **kw):
            calls.append(args)
            return json.dumps(dict(state='active', html_url='https://github.com/kwinweng/shiguang-hot/actions'))
        code, output = self.invoke(fake, ['--check'])
        self.assertEqual(code, 0)
        self.assertEqual(calls[0][0], 'api')
        self.assertEqual(len(calls), 1)
        self.assertEqual(output[0]['actions_write'], 'not_verified_by_read_check')

    def test_403_is_not_retried_or_replaced_with_other_credentials(self):
        calls = []
        def fake(*args, **kw):
            calls.append(args)
            raise RuntimeError('HTTP 403 Resource not accessible by personal access token')
        code, output = self.invoke(fake)
        self.assertEqual(code, 1)
        self.assertEqual(len(calls), 1)
        self.assertEqual(output[-1]['status'], 'error')
        self.assertIn('403', output[-1]['message'])

    def test_run_identifier_ignores_someone_elses_newer_manual_run(self):
        wrong = self.matching_run()
        wrong.update(databaseId=100, displayTitle='hourly / workflow_dispatch / someone-else')
        def fake(*args, **kw):
            return json.dumps([wrong, self.matching_run()]) if args[:2] == ('run', 'list') else ''
        code, output = self.invoke(fake)
        self.assertEqual(code, 0)
        self.assertEqual(output[1]['run_id'], 99)
        self.assertEqual(output[-1]['status'], 'not_waited')
        self.assertNotIn('workflow_succeeded', [o['status'] for o in output])

    def test_success_is_only_reported_after_completed_success(self):
        def fake(*args, **kw):
            if args[:2] == ('run', 'list'):
                return json.dumps([self.matching_run()])
            if args[:2] == ('run', 'view'):
                return json.dumps(dict(status='completed', conclusion='success'))
            return ''
        code, output = self.invoke(fake, ['--wait'])
        self.assertEqual(code, 0)
        self.assertEqual(output[-1]['status'], 'workflow_succeeded')

    def test_canceled_or_failed_run_never_counts_as_success(self):
        for conclusion in ['cancelled', 'failure', 'skipped']:
            with self.subTest(conclusion=conclusion):
                def fake(*args, **kw):
                    if args[:2] == ('run', 'list'):
                        return json.dumps([self.matching_run()])
                    if args[:2] == ('run', 'view'):
                        return json.dumps(dict(status='completed', conclusion=conclusion))
                    return ''
                code, output = self.invoke(fake, ['--wait'])
                self.assertEqual(code, 1)
                self.assertEqual(output[-1]['status'], 'error')

    def test_unindexed_run_times_out_without_duplicate_dispatch(self):
        calls, clock = [], [0.0]
        def fake(*args, **kw):
            calls.append(args)
            return '[]' if args[:2] == ('run', 'list') else ''
        with patch.object(dispatch_hourly.time, 'monotonic', side_effect=lambda: clock[0]), \
             patch.object(dispatch_hourly.time, 'sleep', side_effect=lambda seconds: clock.__setitem__(0, clock[0] + seconds)):
            code, output = self.invoke(fake, ['--timeout', '1'])
        self.assertEqual(code, 1)
        self.assertEqual(sum(args[:2] == ('workflow', 'run') for args in calls), 1)
        self.assertIn('not canceled', output[-1]['message'])


if __name__ == '__main__':
    unittest.main()
