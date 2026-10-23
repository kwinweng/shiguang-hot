"""Runner checks use mocks only: no scraping and no remote Git operations."""
import contextlib
import fcntl
import io
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from tools import box_scrape


class BoxScrapeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.checkout = self.base / 'checkout'
        self.checkout.mkdir()
        (self.checkout / 'pipeline.py').write_text('# fixture')
        with sqlite3.connect(self.checkout / 'tg.db') as db:
            db.execute('create table fixture(value text)')
            db.execute("insert into fixture values ('original')")

    def args(self, *extra):
        return box_scrape.arguments(['--checkout', str(self.checkout), *extra])

    def test_invalid_arguments(self):
        for extra in (['--limit', '0'], ['--limit', '-1'], ['--limit', 'wat'],
                      ['--limit', '1'], ['--unknown'], ['--test-dir'],
                      ['--test-dir', str(self.checkout)],
                      ['--test-dir', str(self.checkout / 'nested')]):
            with self.subTest(extra=extra), contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit):
                    self.args(*extra)

    def test_dry_run_never_executes_or_creates_output(self):
        target = self.base / 'trial'
        with patch.object(box_scrape, 'execute') as execute, contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(box_scrape.main(['--checkout', str(self.checkout), '--dry-run',
                                             '--test-dir', str(target), '--limit', '2']), 0)
        execute.assert_not_called()
        self.assertFalse(target.exists())
        self.assertFalse((self.checkout / 'logs').exists())

    def test_test_dir_copies_database_and_never_calls_git(self):
        target = self.base / 'trial'
        (self.checkout / '.env').write_text('must not copy')
        def fake_pipeline(root, limit):
            self.assertEqual(root, target)
            self.assertEqual(limit, 2)
            self.assertFalse((root / '.env').exists())
            with sqlite3.connect(root / 'tg.db') as db:
                db.execute("update fixture set value='isolated'")
            (root / 'site').mkdir()
        with patch.object(box_scrape, 'run_pipeline', side_effect=fake_pipeline), \
             patch.object(box_scrape.subprocess, 'run') as run, \
             patch.object(box_scrape.subprocess, 'check_output') as git:
            box_scrape.execute(self.args('--test-dir', str(target), '--limit', '2'))
        run.assert_not_called()
        git.assert_not_called()
        self.assertTrue((target / 'site').is_dir())
        with sqlite3.connect(self.checkout / 'tg.db') as db:
            self.assertEqual(db.execute('select value from fixture').fetchone()[0], 'original')

    def test_pipeline_forces_public_fetch_environment(self):
        with patch.dict(os.environ, {'NO_FETCH': '1', 'SITE_MODE': 'private', 'MAIL_DIGEST': '1',
                                     'SITE_OUT': '/wrong', 'SOURCES_OVERRIDE': '/wrong'}), \
             patch.object(box_scrape.subprocess, 'run') as run:
            box_scrape.run_pipeline(self.checkout, 2)
        env = run.call_args.kwargs['env']
        self.assertEqual([env[k] for k in ('NO_FETCH', 'SITE_MODE', 'MAIL_DIGEST', 'TZ')],
                         ['0', 'public', '0', 'Asia/Shanghai'])
        self.assertNotIn('SITE_OUT', env)
        self.assertNotIn('SOURCES_OVERRIDE', env)

    def test_pipeline_failure_stops_persistence(self):
        with patch.object(box_scrape.subprocess, 'check_output', side_effect=['main', '']), \
             patch.object(box_scrape.subprocess, 'run') as run, \
             patch.object(box_scrape, 'run_pipeline', side_effect=RuntimeError('failed')):
            with self.assertRaises(RuntimeError):
                box_scrape.execute(self.args())
        self.assertEqual([call.args[0][1] for call in run.call_args_list], ['fetch', 'merge'])

    def test_shell_entry_point_dry_run_is_offline(self):
        script = Path(box_scrape.__file__).with_suffix('.sh')
        result = subprocess.run(['sh', str(script), '--checkout', str(self.checkout), '--dry-run'],
                                env=dict(os.environ, BOX_PYTHON=sys.executable), capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('dry-run: no execution', result.stdout)

    def test_busy_lock_skips_execution(self):
        with open(self.checkout / '.box-scrape.lock', 'a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            with patch.object(box_scrape, 'execute') as execute, contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(box_scrape.main(['--checkout', str(self.checkout)]), 0)
            execute.assert_not_called()

    def test_limit_caps_sources_and_requests_and_disables_trial_offline(self):
        package = self.checkout / 'shiguang/ingest'
        package.mkdir(parents=True)
        (package / 'http.py').write_text(
            "class FetchFailure(Exception): pass\n"
            "def request(*args, **kwargs):\n"
            "    with open('requests.txt', 'a') as out: out.write('request\\n')\n")
        (package / 'scheduler.py').write_text(
            "from . import http\n"
            "def run(db, sources, **kwargs):\n"
            "    assert len(sources) == 2\n"
            "    for i in range(8):\n"
            "        try: http.request('offline-fixture')\n"
            "        except http.FetchFailure: pass\n")
        (package / 'trial.py').write_text("def run(*args, **kwargs): raise AssertionError('trial ran')\n")
        (self.checkout / 'pipeline.py').write_text(
            "from shiguang.ingest import scheduler, trial\n"
            "scheduler.run(None, [{'type':'inbox'}, {'type':'telegram'}, {'type':'feed'}, {'type':'telegram'}])\n"
            "trial.run(None, [])\n")
        box_scrape.run_pipeline(self.checkout, 2)
        self.assertEqual((self.checkout / 'requests.txt').read_text().splitlines(), ['request', 'request'])


if __name__ == '__main__':
    unittest.main()
