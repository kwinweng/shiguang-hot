"""Sources v1 acceptance: all persistence and builds stay inside temporary directories."""
import copy
import hashlib
import io
import json
import re
import sqlite3
import tempfile
import unittest
from contextlib import closing
from contextlib import redirect_stdout
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit
from unittest.mock import patch

import pipeline
from shiguang.config import ROOT, config
from shiguang.ingest import http, scheduler, telegram, trial
from shiguang.model import BEIJING
from shiguang.site import history, pages
from shiguang.site.build import build
from tools import trial_report

FIXTURES = Path(__file__).parent / 'fixtures'
NOW = datetime(2026, 10, 22, 18, tzinfo=BEIJING)


class TrialTests(unittest.TestCase):
    def test_config_and_retired(self):
        cfg = trial.load()
        self.assertEqual(len(cfg['sources']), 13)
        self.assertEqual(len(cfg['categories']), 7)
        sources = {s['id']: s for s in config()['sources']}
        self.assertEqual(sources['pelosi3']['order'], 56)
        self.assertNotIn('liangjiahepost', sources)
        self.assertEqual(set(history.RETIRED), {'liangjiahepost', 'titan_pain'})
        self.assertFalse(set(history.RETIRED) & sources.keys())
        self.assertTrue(set(history.RETIRED) <= history.ALLOWED)

    def test_config_rejects_invalid(self):
        original = trial.load()
        cases = []
        value = copy.deepcopy(original); value['categories'] *= 2; cases.append(value)
        value = copy.deepcopy(original); value['sources'] *= 2; cases.append(value)
        value = copy.deepcopy(original); value['sources'][0]['category'] = 'missing'; cases.append(value)
        value = copy.deepcopy(original); value['sources'][0]['section'] = '好买'; cases.append(value)
        value = copy.deepcopy(original)
        value['categories'] = [dict(id=f'c-{n}', name=str(n), section='好玩') for n in range(9)]
        cases.append(value)
        value = copy.deepcopy(original)
        value['categories'] = [dict(id=f'c-{n}', name=str(n), section='好玩' if n < 8 else '好买') for n in range(17)]
        cases.append(value)
        for value in cases:
            with self.subTest(value=value), self.assertRaises(ValueError):
                trial.prepare(value)

    def test_fixture_collection_dedup_and_isolation(self):
        cfg = trial.load()
        for sid, fixture, expected in [('earthsky', 'rss.xml', 1), ('steam', 'steam-rdf.xml', 2), ('ucca', 'ucca.html', 1),
                                       ('douban-events', 'douban.html', 2), ('sspai', 'telegram.html', 1)]:
            with self.subTest(source=sid), tempfile.TemporaryDirectory() as folder:
                root = Path(folder)
                db = sqlite3.connect(root / 'tg.db')
                source = next(s for s in cfg['sources'] if s['id'] == sid)
                response = http.Response(200, {}, (FIXTURES / ('trial-' + fixture)).read_bytes())
                with db, patch.object(http, 'request', return_value=response) as request, \
                     patch.object(trial.time, 'sleep'), \
                     patch.object(telegram, 'download_images', side_effect=AssertionError('image download')):
                    trial.run(db, [source], clock=lambda: NOW)
                    trial.run(db, [source], clock=lambda: NOW)
                    self.assertEqual(request.call_count, 1)
                    trial.run(db, [source], clock=lambda: NOW + timedelta(hours=1))
                    self.assertEqual(request.call_count, 2)
                    self.assertEqual(db.execute('select count(*) from trial_item').fetchone()[0], expected)
                    tables = {r[0] for r in db.execute("select name from sqlite_master where type='table'")}
                    self.assertFalse({'msg', 'entry', 'status', 'gap'} & tables)
                    self.assertEqual(list(root.iterdir()), [root / 'tg.db'])
                    row = db.execute('select summary,published_at,fetched_at,image_url from trial_item limit 1').fetchone()
                    self.assertLessEqual(len(row[0]), 500)
                    self.assertTrue(row[2].endswith('+00:00'))
                    if sid == 'douban-events':
                        self.assertIsNone(row[3])
                db.close()

    def test_backoff_blocked_and_other_source_continues(self):
        sources = trial.load()['sources'][:2]
        with tempfile.TemporaryDirectory() as folder, closing(sqlite3.connect(Path(folder) / 'tg.db')) as db:
            responses = [http.Response(200, {}, b'<html>changed layout</html>'), http.Response(403, {}, b'')]
            with patch.object(http, 'request', side_effect=responses), patch.object(trial.time, 'sleep'):
                trial.run(db, sources, clock=lambda: NOW)
            state = db.execute('select status,consecutive_failures,last_success_at from source_fetch_state order by source_id').fetchall()
            self.assertEqual(state, [('error', 1, None), ('blocked', 1, None)])
            with patch.object(http, 'request', side_effect=AssertionError('cooldown')):
                trial.run(db, sources, clock=lambda: NOW + timedelta(minutes=10))

    def test_page_parser_failure(self):
        for source in (s for s in trial.load()['sources'] if s['fetch'] == 'page'):
            with self.assertRaises(http.FetchFailure):
                trial.parse_page(b'<html>changed layout</html>', source)

    def test_douban_domains_canonical_urls_and_missing_titles(self):
        source = next(s for s in trial.load()['sources'] if s['id'] == 'douban-events')
        body = (FIXTURES / 'trial-douban.html').read_text() + '''
            <a href="http://douban.com/event/37604670?from=weekly#details">Duplicate</a>
            <a href="https://beijing.douban.com/event/37604670/">Duplicate</a>
            <a href="https://events.beijing.douban.com/event/37604670/">Duplicate</a>
            <a href="/event/789012/?from=weekly">Duplicate</a>
            <a href="https://douban.com/event/456/" title="Title attribute"></a>
            <a href="https://www.douban.com/event/567/"><img alt="Poster title"></a>
            <a href="https://www.douban.com/event/888/"><img src="poster.jpg"></a>
            <a href="https://www.douban.com/event/999/">   </a>
            <a href="https://notdouban.com/event/123/">Wrong host</a>
            <a href="https://douban.com.evil.example/event/123/">Wrong suffix</a>
            <a href="https://www.douban.com/event/not-a-number/">Wrong path</a>
            <a href="https://www.douban.com/event/123/photos/">Wrong path</a>
        '''
        items = trial.parse_page(body, source)
        self.assertEqual({i['url'] for i in items}, {
            'https://www.douban.com/event/37604670/', 'https://www.douban.com/event/789012/',
            'https://www.douban.com/event/456/', 'https://www.douban.com/event/567/'})
        self.assertTrue(all(i['title'].strip() and not i['images'] for i in items))

    def test_ucca_keeps_original_host_restriction(self):
        source = next(s for s in trial.load()['sources'] if s['id'] == 'ucca')
        body = '''<a href="/exhibition/offline-show/">Local</a>
            <a href="https://ucca.org.cn/exhibition/other/">Other host</a>
            <a href="https://www.douban.com/event/123/">Douban</a>'''
        items = trial.parse_page(body, source)
        self.assertEqual([i['url'] for i in items], ['https://www.ucca.org.cn/exhibition/offline-show/'])

    def test_summary_cap_and_feed_keep(self):
        source = trial.load()['sources'][0]
        xml = ('<rss><channel>' + ''.join(
            f'<item><title>Story {n}</title><link>https://example.org/{n}</link>'
            '<pubDate>Thu, 22 Oct 2026 09:00:00 GMT</pubDate><description>' + '字' * 700 +
            '</description></item>' for n in range(60)) + '</channel></rss>').encode()
        with tempfile.TemporaryDirectory() as folder, closing(sqlite3.connect(Path(folder) / 'tg.db')) as db, \
             patch.object(http, 'request', return_value=http.Response(200, {}, xml)), patch.object(trial.time, 'sleep'):
            trial.run(db, [source], clock=lambda: NOW)
            self.assertEqual(db.execute('select count(*),min(length(summary)),max(length(summary)) from trial_item').fetchone(),
                             (50, 500, 500))

    def test_report_beijing_first_fetch_and_empty_success(self):
        cfg = trial.load()
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); database = root / 'tg.db'
            with closing(sqlite3.connect(database)) as db:
                trial.ensure_table(db); scheduler.ensure_schema(db)
                for n, fetched in enumerate(['2026-10-21T15:59:59+00:00', '2026-10-21T16:00:00+00:00']):
                    db.execute('insert into trial_item values(?,?,?,?,?,?,?,?,?)',
                               ('earthsky', '好玩', 'stargazing', f'https://example.org/{n}', 'story', '', None,
                                '2020-01-01', fetched))
                db.commit()
                batch, _ = scheduler.claim(db, 'trial:earthsky', NOW)
                batch.finish(NOW)
                text = trial_report.report(db, cfg, 2, NOW)
                self.assertIn('| 2026-10-21 | 1 |', text)
                self.assertIn('| 2026-10-22 | 1 |', text)
                self.assertIn('| EarthSky | 2026-10-22T18:00:00+08:00 |', text)
                self.assertIn('尚无成功记录', text)
            with redirect_stdout(io.StringIO()) as output:
                trial_report.main(['--db', str(database), '--output', str(root / 'reports'), '--days', '2'])
            self.assertEqual(next((root / 'reports').glob('*.md')).read_text(), output.getvalue())

    def test_build_archives_and_trial_privacy_both_modes(self):
        cfg = config()
        trial_cfg = trial.load()
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            with patch.object(telegram, 'D', str(root)), patch.object(telegram, 'MEDIA', str(root / 'media')):
                db, _ = telegram.open_db(True)
                for sid in ['pelosi3', 'liangjiahepost', 'titan_pain']:
                    for day in ['2026-10-21', '2026-10-22']:
                        db.execute('insert into msg values(?,?,?,?,?,?,?)',
                                   (sid, int(day[-2:]), day + 'T12:00:00+08:00', f'{sid} archived story', '[]', '', '[]'))
                trial.ensure_table(db)
                for source in trial_cfg['sources']:
                    db.execute('insert into trial_item values(?,?,?,?,?,?,?,?,?)',
                               (source['id'], source['section'], source['category'], source['url'],
                                source['id'], source['url'], None, None, NOW.isoformat()))
                db.commit(); db.close()
                before = hashlib.sha256((root / 'tg.db').read_bytes()).digest()
                for mode in ['public', 'private']:
                    out = root / mode
                    with patch.dict('os.environ', {'NO_FETCH': '1', 'SITE_MODE': mode, 'SITE_OUT': str(out), 'MAIL_DIGEST': '0'}), \
                         patch.object(pages, 'ROOT', root), patch.object(pages, 'load_issues', return_value=[]), \
                         patch.object(http, 'request', side_effect=AssertionError('network')):
                        rows, entries = pipeline.collect(cfg, NOW)
                        build(rows, [], NOW, entries)
                    old = (out / 'archive/data/2026-10-21.json').read_text()
                    old_html = (out / 'archive/2026-10-21.html').read_text()
                    old_items = json.loads(old)['items']
                    for sid in ['pelosi3']:
                        self.assertEqual(sum(item['source'] == sid for item in old_items), 1)
                        self.assertIn(sid + ' archived story', old_html)
                        self.assertIn(sid + ' archived story', (out / sid / 'index.html').read_text())
                    for sid in history.RETIRED:
                        self.assertIn(sid + ' archived story', old)
                        self.assertIn(sid + ' archived story', old_html)
                        self.assertFalse((out / sid).exists())
                        for path in ['index.html', 'columns.html', 'hot.html']:
                            self.assertNotIn(sid, (out / path).read_text())
                    for path in list(out.rglob('*')) + list((ROOT / 'public-feeds').rglob('*')):
                        if path.is_file() and path.suffix in ('.html', '.json', '.js', '.css', '.md'):
                            if path == out / 'data/explore.json':
                                explore = json.loads(path.read_text())['messages']
                                self.assertEqual(len(explore), len(trial_cfg['sources']))
                                self.assertEqual({r['section'] for r in explore}, {'play', 'buy'})
                                continue
                            text = path.read_text()
                            for source in trial_cfg['sources']:
                                self.assertNotIn(source['id'], path.relative_to(out).as_posix() if path.is_relative_to(out) else path.name)
                                # Shared Telegram host is already used by published channels.
                                self.assertNotIn(source['url'], text)
                                self.assertNotIn('"source_id": "' + source['id'] + '"', text)
                                self.assertNotRegex(text, r'data-source=[\"\']' + re.escape(source['id']) + r'[\"\']')
                                domain = urlsplit(source['url']).hostname
                                if domain != 't.me':
                                    self.assertNotIn(domain, text)
                self.assertEqual(before, hashlib.sha256((root / 'tg.db').read_bytes()).digest())
