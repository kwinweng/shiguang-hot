"""Runner checks use synthetic sources and local Git only."""
import contextlib
from datetime import datetime, timezone
import fcntl
import hashlib
import io
import os
import json
from pathlib import Path
import shutil
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
        self.base = Path(self.temp.name).resolve()
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
                      ['--test-dir', str(self.checkout / 'nested')],
                      ['--no-publish', '--test-dir', str(self.base / 'trial')]):
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

    def test_no_publish_stage_failure_is_reported_and_stops(self):
        for stage, expected in (
            ('pipeline', ['fetch', 'merge', 'pipeline']),
            ('tools/persist_action_data.sh', ['fetch', 'merge', 'pipeline', 'tools/persist_action_data.sh']),
            ('tools/write_build_info.py', ['fetch', 'merge', 'pipeline', 'tools/persist_action_data.sh',
                                           'tools/write_build_info.py']),
        ):
            with self.subTest(stage=stage):
                calls = []

                def run(name):
                    calls.append(name)
                    if name == stage:
                        raise RuntimeError('fixture failure')

                with patch.object(box_scrape.subprocess, 'check_output', side_effect=['main', '', '']), \
                     patch.object(box_scrape.subprocess, 'run', side_effect=lambda cmd, **kw: run(cmd[1])), \
                     patch.object(box_scrape, 'run_pipeline', side_effect=lambda root: run('pipeline')), \
                     contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(box_scrape.main(['--checkout', str(self.checkout), '--no-publish']), 1)
                self.assertEqual(calls, expected)

    def test_no_publish_collects_and_prepares_live_data_for_pages(self):
        root = self.checkout
        source = Path(box_scrape.__file__).resolve().parents[1]
        for name in ('shiguang', 'web'):
            shutil.copytree(source / name, root / name, ignore=shutil.ignore_patterns('__pycache__'))
        shutil.copy2(source / 'pipeline.py', root / 'actual_pipeline.py')
        shutil.copy2(source / '.gitignore', root)
        (root / 'public-feeds').mkdir()
        (root / 'public-feeds/.gitkeep').touch()
        (root / 'tools').mkdir()
        for name in ('persist_action_data.sh', 'write_build_info.py', 'publish_pages.sh'):
            shutil.copy2(source / 'tools' / name, root / 'tools')
        (root / 'trial-sources.json').write_text('{"categories": [], "sources": []}')
        (root / 'sources.json').write_text(json.dumps({'sources': [dict(
            id='CE_Observe', name='Fixture', type='telegram', channel='CE_Observe', visibility='public',
        )]}))
        # Stub the HTTP boundary; the collector, database, site builder and publisher are real.
        (root / 'pipeline.py').write_text('''
from datetime import datetime, timezone
from actual_pipeline import main
from shiguang.ingest import http

def request(url, headers=None):
    assert url == 'https://t.me/s/CE_Observe', url
    now = datetime.now(timezone.utc).replace(second=0, microsecond=0).isoformat()
    body = ('<div class="tgme_widget_message" data-post="CE_Observe/101">'
            f'<time datetime="{now}"></time>'
            '<div class="tgme_widget_message_text">Fresh fixture story</div></div>')
    return http.Response(200, {}, body.encode())

http.request = request
main()
''')
        remote = self.base / 'remote.git'

        def git(*args):
            return subprocess.check_output(['git', *args], cwd=root, text=True).strip()

        git('init', '--bare', str(remote))
        git('init', '-b', 'main')
        git('config', 'user.name', 'Fixture')
        git('config', 'user.email', 'fixture@localhost')
        git('add', '.')
        git('commit', '-m', 'Synthetic checkout')
        git('remote', 'add', 'origin', str(remote))
        git('push', 'origin', 'main')
        env = dict(os.environ, BOX_PYTHON=sys.executable, SAMPLE_DATA='0')

        def collect():
            result = subprocess.run(['sh', str(source / 'tools/box_scrape.sh'), '--checkout', str(root), '--no-publish'],
                                    cwd=root, env=env, capture_output=True, text=True)
            if result.returncode != 0:
                self.fail((result.stdout, result.stderr,
                           [p.read_text() for p in (root / 'logs/box-scrape').glob('*.log')]))
            return json.loads((root / 'site/data/live.json').read_text())

        before = datetime.now(timezone.utc)
        live = collect()
        self.assertIs(live['sample'], False)
        self.assertGreaterEqual(datetime.fromisoformat(live['updated']), before)
        self.assertEqual([message['title'] for message in live['messages']], ['Fresh fixture story'])
        info = json.loads((root / 'site/build-info.json').read_text())
        self.assertEqual(info['source_commit'], git('--git-dir', str(remote), 'rev-parse', 'main'))
        self.assertEqual(info['database_sha256'], hashlib.sha256((root / 'tg.db').read_bytes()).hexdigest())
        self.assertFalse(git('ls-remote', '--heads', 'origin', 'gh-pages'))

        # No new source item on the next cycle: same live content, new build time.
        # macOS can do a first build, but an in-place exchange needs Linux renameat2.
        if sys.platform != 'linux':
            (root / 'site').rename(self.base / 'first-site')
        again = collect()
        self.assertEqual(again['messages'], live['messages'])
        self.assertGreater(datetime.fromisoformat(again['updated']), datetime.fromisoformat(live['updated']))

        result = subprocess.run(['sh', 'tools/publish_pages.sh', '--already-built', '--dry-run'],
                                cwd=root, env=env, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('dry-run=1', result.stdout)
        self.assertFalse(git('ls-remote', '--heads', 'origin', 'gh-pages'))

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
                self.assertEqual(box_scrape.main(['--checkout', str(self.checkout), '--no-publish']), 1)
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
