"""Runner checks use mocks only: no scraping and no remote Git operations."""
import contextlib
import fcntl
import io
import os
import json
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
        with contextlib.closing(sqlite3.connect(self.checkout / 'tg.db')) as db, db:
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
            with contextlib.closing(sqlite3.connect(root / 'tg.db')) as db, db:
                db.execute("update fixture set value='isolated'")
            (root / 'site').mkdir()
        with patch.object(box_scrape, 'run_pipeline', side_effect=fake_pipeline), \
             patch.object(box_scrape.subprocess, 'run') as run, \
             patch.object(box_scrape.subprocess, 'check_output') as git:
            box_scrape.execute(self.args('--test-dir', str(target), '--limit', '2'))
        run.assert_not_called()
        git.assert_not_called()
        self.assertTrue((target / 'site').is_dir())
        with contextlib.closing(sqlite3.connect(self.checkout / 'tg.db')) as db, db:
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
        with patch.object(box_scrape.subprocess, 'check_output', side_effect=['main', '', '']), \
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

    def test_publish_failure_preserves_persistence_success(self):
        calls = []
        def run(command, **kwargs):
            calls.append(command)
            if 'tools/publish_pages.sh' in command:
                raise subprocess.CalledProcessError(1, command)
        with patch.object(box_scrape.subprocess, 'check_output', side_effect=['main', '', '']), \
             patch.object(box_scrape.subprocess, 'run', side_effect=run), \
             patch.object(box_scrape, 'run_pipeline'), \
             contextlib.redirect_stdout(io.StringIO()) as output:
            box_scrape.execute(self.args())
        self.assertIn('data persistence succeeded', output.getvalue())
        self.assertEqual(calls[-3][1], 'tools/persist_action_data.sh')
        self.assertEqual(calls[-1][1:], ['tools/publish_pages.sh', '--already-built'])

    def test_persistence_failure_never_publishes(self):
        def run(command, **kwargs):
            if 'tools/persist_action_data.sh' in command:
                raise subprocess.CalledProcessError(1, command)
        with patch.object(box_scrape.subprocess, 'check_output', side_effect=['main', '', '']), \
             patch.object(box_scrape.subprocess, 'run', side_effect=run) as runner, \
             patch.object(box_scrape, 'run_pipeline'):
            with self.assertRaises(subprocess.CalledProcessError):
                box_scrape.execute(self.args())
        self.assertEqual(len(runner.call_args_list), 3)

    def test_busy_lock_skips_execution(self):
        with open(self.checkout / '.box-scrape.lock', 'a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            with patch.object(box_scrape, 'execute') as execute, contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(box_scrape.main(['--checkout', str(self.checkout)]), 0)
            execute.assert_not_called()

    def test_limit_saves_first_page_and_counts_only_http_attempts_offline(self):
        # Exercise the real adapters and scheduler inside the runner's fresh interpreter.
        import shutil
        shutil.copytree(Path(box_scrape.__file__).resolve().parents[1] / 'shiguang',
                        self.checkout / 'shiguang')
        (self.checkout / 'pipeline.py').write_text('''
import subprocess
from datetime import datetime, timezone
from shiguang.ingest import http, scheduler, telegram, trial
subprocess.run = lambda *a, **k: (_ for _ in ()).throw(AssertionError('network forbidden'))
now = datetime.now(timezone.utc)
def request(url, headers=None):
    with open('requests.txt', 'a') as out: out.write(url + '\\n')
    if url == 'https://t.me/s/first':
        body = ('<div class="tgme_widget_message" data-post="first/101">'
                '<time datetime="' + now.isoformat() + '"></time>'
                '<div class="tgme_widget_message_text">Fresh message</div>'
                '<a class="tgme_widget_message_photo_wrap" '
                'style="background-image:url(https://example.com/image.jpg)"></a></div>')
        return http.Response(200, {}, body.encode())
    if url == 'https://example.com/feed':
        body = ('<rss><channel><item><guid>fresh</guid><title>Fresh entry</title>'
                '<pubDate>' + now.isoformat() + '</pubDate><description>'
                '&lt;img src="https://example.com/feed.jpg"/&gt;</description></item></channel></rss>')
        return http.Response(200, {}, body.encode())
    raise AssertionError('unexpected request: ' + url)
http.request = request
db, migrated = telegram.open_db(True)
db.execute('insert into gap values(?,?,?,?)', ('first', 90, None, now.isoformat()))
db.commit()
sources = [dict(id='z-third', type='telegram', channel='third', visibility='public'),
           dict(id='a-first', type='telegram', channel='first', visibility='public'),
           dict(id='b-alias', type='telegram', channel='first', visibility='public'),
           dict(id='c-feed', type='feed', url='https://example.com/feed', visibility='public'),
           dict(id='0-private', type='telegram', channel='private', visibility='private')]
scheduler.run(db, sources, images_migrated=migrated)
trial.run(db, [])
assert db.execute('select count(*) from gap').fetchone()[0] == 1
db.close()
''')
        target = self.base / 'trial'
        # Capture child diagnostics without bypassing run_pipeline's subprocess setup.
        real_run = subprocess.run
        def captured_run(*args, **kwargs):
            kwargs['check'] = False
            result = real_run(*args, **kwargs, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            statuses.extend(json.loads(line.removeprefix('fetch_status '))
                            for line in result.stderr.splitlines() if line.startswith('fetch_status '))
            return result
        statuses = []
        with patch.object(box_scrape.subprocess, 'run', side_effect=captured_run):
            box_scrape.execute(self.args('--test-dir', str(target), '--limit', '2'))
        self.assertEqual((target / 'requests.txt').read_text().splitlines(),
                         ['https://t.me/s/first', 'https://example.com/feed'])
        self.assertEqual([(s['source'], s['requests'], s['result'], s['new'], s['error_code'])
                          for s in statuses], [('a-first', 1, 'ok', 1, None), ('c-feed', 1, 'ok', 1, None)])
        with contextlib.closing(sqlite3.connect(target / 'tg.db')) as db, db:
            self.assertEqual(db.execute('select ch,id,text,images from msg').fetchall(),
                             [('first', 101, 'Fresh message', '[]')])
            self.assertEqual(db.execute('select source,id,images from entry').fetchall(),
                             [('c-feed', 'fresh', '[]')])
        self.assertFalse(list((target / 'media').rglob('*.webp')))
        with contextlib.closing(sqlite3.connect(self.checkout / 'tg.db')) as db, db:
            self.assertIsNone(db.execute("select name from sqlite_master where name='msg'").fetchone())


if __name__ == '__main__':
    unittest.main()
