"""Exercise real Git rejection paths and external-trigger success/failure reporting."""
import contextlib
import hashlib
import io
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from tools import dispatch_hourly
from tools.write_build_info import write_info

ROOT = Path(__file__).resolve().parent.parent


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

    def test_changed_database_is_pushed_without_unrelated_staged_files(self):
        (self.repo / 'tg.db').write_bytes(b'new data')
        (self.repo / 'unrelated').write_text('do not publish')
        self.run_git(self.repo, 'add', 'unrelated')
        self.assertEqual(self.persist().returncode, 0)
        self.assertEqual(self.run_git(self.remote, 'show', 'main:tg.db'), 'new data')
        self.assertNotIn('unrelated', self.run_git(self.remote, 'ls-tree', '--name-only', 'main'))
        self.assertEqual(self.run_git(self.repo, 'diff', '--cached', '--name-only'), 'unrelated')

    def test_remote_advance_is_reported_without_force_pushing(self):
        other = self.base / 'other'
        self.run_git(self.base, 'clone', str(self.remote), str(other))
        self.run_git(other, 'config', 'core.hooksPath', '.git/hooks')
        self.run_git(other, 'config', 'user.name', 'test')
        self.run_git(other, 'config', 'user.email', 'test@local.invalid')
        (other / 'public-feeds/sample.json').write_text('{"new":true}')
        self.run_git(other, 'commit', '-am', 'new feed')
        self.run_git(other, 'push', 'origin', 'main')
        remote_head = self.run_git(self.remote, 'rev-parse', 'main')
        (self.repo / 'tg.db').write_bytes(b'collected data')
        result = self.persist()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.run_git(self.remote, 'rev-parse', 'main'), remote_head)
        self.assertIn('rejected', result.stderr)

    def test_commit_hook_failure_is_not_ignored(self):
        hook = self.repo / '.git/hooks/pre-commit'
        hook.write_text('#!/bin/sh\nexit 1\n')
        hook.chmod(0o755)
        (self.repo / 'tg.db').write_bytes(b'collected data')
        self.assertNotEqual(self.persist().returncode, 0)
        self.assertEqual(self.run_git(self.remote, 'show', 'main:tg.db'), 'original')

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
