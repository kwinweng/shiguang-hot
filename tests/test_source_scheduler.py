"""Offline acceptance for #16 / approved Spec r2. Never contact real sources."""
import io
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import threading
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch

from PIL import Image
import pipeline
from shiguang.ingest import http, scheduler, telegram, web
from shiguang.model import BEIJING
from tests.test_telegram_ingest import page, URL

NOW = datetime(2026, 10, 21, 10, 59, tzinfo=BEIJING)
FEED = dict(id='feed-a', type='feed', visibility='public', name='A', url='https://example.com/feed?edition=1')
TG = dict(id='channel', type='telegram', visibility='public', name='Channel', channel='chan')


def response(body=b'<rss><channel/></rss>', headers=None, status=200):
    return http.Response(status, headers or {}, body)


def rss(image=False):
    image = '&lt;img src="https://example.com/pic.jpg"&gt;' if image else ''
    return f'''<rss><channel><item><guid>one</guid><title>Story</title><link>https://example.com/one</link>
    <pubDate>Wed, 21 Oct 2026 02:00:00 GMT</pubDate><description>Text {image}</description></item></channel></rss>'''.encode()


def png():
    out = io.BytesIO()
    Image.new('RGB', (20, 20)).save(out, format='PNG')
    return out.getvalue()


class SchedulerTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        for name, value in [('D', str(self.root)), ('MEDIA', str(self.root / 'media'))]:
            p = patch.object(telegram, name, value); p.start(); self.addCleanup(p.stop)
        self.db, _ = telegram.open_db(True); self.db.commit()
        self.addCleanup(lambda: self.db.close())
        p = patch.object(http, 'request', side_effect=AssertionError('Unexpected network'))
        self.network = p.start(); self.addCleanup(p.stop)
        p = patch.object(scheduler.time, 'sleep'); self.sleep = p.start(); self.addCleanup(p.stop)
        p = patch.object(sys, 'stderr', new_callable=io.StringIO)
        self.log = p.start(); self.addCleanup(p.stop)

    def run_sources(self, now=NOW, sources=None):
        with scheduler.collection_lock(self.root / 'tg.db') as held:
            self.assertTrue(held)
            scheduler.run(self.db, sources or [FEED], clock=lambda: now)

    def state(self, field='status'):
        return self.db.execute('select ' + field + ' from source_fetch_state').fetchone()[0]

    def test_aliases_same_hour_and_persisted_database_have_one_batch(self):
        self.network.return_value = response(rss()); self.network.side_effect = None
        self.run_sources(sources=[FEED, dict(FEED, id='feed-b')])
        self.run_sources(NOW + timedelta(seconds=10))
        self.db.close(); self.db, _ = telegram.open_db(True)
        self.run_sources(NOW + timedelta(seconds=20))
        self.assertEqual(self.network.call_count, 1)
        self.assertEqual(self.db.execute('select count(*) from source_fetch_batch').fetchone()[0], 1)
        self.assertEqual(len(web.entries(self.db)), 1)
        self.assertIn('hour_used', self.log.getvalue())

    def test_natural_hour_boundary_and_59_minutes_40_seconds(self):
        self.network.return_value = response(); self.network.side_effect = None
        self.run_sources()
        self.run_sources(NOW.replace(hour=11, minute=0))
        self.run_sources(NOW.replace(hour=11, minute=59))
        self.assertEqual(self.network.call_count, 2)
        self.run_sources(NOW.replace(hour=12, minute=7, second=30))
        self.run_sources(NOW.replace(hour=13, minute=7, second=10))
        self.assertEqual(self.network.call_count, 4)
        self.assertEqual(self.db.execute('select hour_key from source_fetch_batch order by hour_key').fetchall()[0], ('2026-10-21T10',))

    def test_cross_midnight_uses_beijing_not_utc(self):
        self.network.return_value = response(); self.network.side_effect = None
        self.run_sources(NOW.replace(hour=23, minute=59))
        self.run_sources(NOW.replace(hour=0, minute=0) + timedelta(days=1))
        self.assertEqual(self.db.execute('select hour_key from source_fetch_batch order by hour_key').fetchall(),
                         [('2026-10-21T23',), ('2026-10-22T00',)])

    def test_long_run_samples_each_sources_claim_time_and_failure_cooldown_starts_on_finish(self):
        self.network.side_effect = [response(status=503), response()]
        times = iter([NOW, NOW + timedelta(minutes=2), NOW + timedelta(minutes=3), NOW + timedelta(minutes=4)])
        # HTTP Retry-After also samples the clock, so use a separate consistent response-time value.
        def clock(): return next(times)
        with patch.object(scheduler.Batch, 'get', side_effect=http.FetchFailure('network')):
            scheduler.run(self.db, [FEED, dict(FEED, id='z', url='https://example.org/feed')], clock=clock)
        states = self.db.execute('select last_attempt_at,next_eligible_at from source_fetch_state order by last_attempt_at').fetchall()
        self.assertEqual(states, [(scheduler.stamp(NOW), scheduler.stamp(NOW + timedelta(hours=1, minutes=2))),
                                  (scheduler.stamp(NOW + timedelta(minutes=3)), scheduler.stamp(NOW + timedelta(hours=1, minutes=4)))])
        self.assertEqual(self.db.execute('select hour_key from source_fetch_batch order by hour_key').fetchall(),
                         [('2026-10-21T10',), ('2026-10-21T11',)])

    def test_endpoint_queries_are_distinct_and_sources_are_staggered(self):
        self.network.return_value = response(); self.network.side_effect = None
        self.run_sources(sources=[FEED, dict(FEED, id='edition2', url=FEED['url'].replace('=1', '=2'))])
        self.assertEqual(self.network.call_count, 2)
        self.sleep.assert_called_once_with(1)

    def test_telegram_duplicate_channel_registration_is_one_plan(self):
        self.network.side_effect = [response(page(100, at=NOW).encode()), response(page(at=NOW).encode())]
        self.run_sources(sources=[TG, dict(TG, id='duplicate', channel='CHAN')])
        self.assertEqual(self.network.call_count, 2)  # Entrance + end of history, both in ONE batch.
        self.assertEqual(self.db.execute('select count(*) from source_fetch_batch').fetchone()[0], 1)
        self.assertEqual(self.db.execute('select count(*) from msg').fetchone()[0], 1)

    def test_conditional_304_retains_content_and_success_time(self):
        self.network.side_effect = [response(rss(), {'etag': '"v1"', 'last-modified': 'Wed, 21 Oct 2026 02:00:00 GMT'}), response(status=304)]
        self.run_sources()
        old = self.db.execute('select * from entry').fetchall()
        self.run_sources(NOW + timedelta(hours=1))
        self.assertEqual(self.network.call_args.args[1]['If-None-Match'], '"v1"')
        self.assertIn('If-Modified-Since', self.network.call_args.args[1])
        self.assertEqual(self.db.execute('select * from entry').fetchall(), old)
        self.assertEqual(self.state(), 'ok')
        self.assertEqual(self.state('last_success_at'), scheduler.stamp(NOW + timedelta(hours=1)))

    def test_empty_feed_has_valid_materialization(self):
        self.network.side_effect = [response(headers={'etag': '"empty"'}), response(status=304)]
        self.run_sources(); self.run_sources(NOW + timedelta(hours=1))
        self.assertEqual(self.network.call_args.args[1], {'If-None-Match': '"empty"'})
        self.assertEqual(web.entries(self.db), [])
        self.assertEqual(self.state(), 'ok')

    def test_deleted_projection_clears_validators_and_unsolicited_304_is_not_retried(self):
        self.network.side_effect = [response(rss(), {'etag': '"one"'}), response(status=304), response(rss())]
        self.run_sources()
        self.db.execute('delete from entry'); self.db.commit()
        self.run_sources(NOW + timedelta(hours=1))
        self.assertEqual(self.network.call_args.args[1], {})
        self.assertEqual(self.state('error_code'), 'materialization_missing')
        self.run_sources(NOW + timedelta(hours=1, minutes=1))
        self.assertEqual(self.network.call_count, 2)
        self.run_sources(NOW + timedelta(hours=2))
        self.assertEqual(len(web.entries(self.db)), 1)

    def test_bad_200_does_not_install_validator_or_store_raw_response(self):
        self.network.side_effect = [response(b'<html>secret response marker</html>', {'etag': '"bad"'})]
        self.run_sources()
        self.assertEqual(self.state(), 'error')
        self.assertEqual(self.db.execute('select etag,representation_valid from fetch_resource_state').fetchone(), (None, 0))
        self.assertNotIn('secret response marker', '\n'.join(self.db.iterdump()))

    def test_failed_parse_keeps_old_projection_and_never_installs_bad_validator(self):
        self.network.side_effect = [response(rss(), {'etag': '"good"'}), response(b'<rss/>', {'etag': '"bad"'})]
        self.run_sources(); old = self.db.execute('select * from entry').fetchall()
        self.run_sources(NOW + timedelta(hours=1))
        self.assertEqual(self.db.execute('select * from entry').fetchall(), old)
        self.assertEqual(self.db.execute('select etag,error_code from fetch_resource_state').fetchone(), ('"good"', 'invalid_content'))
        self.assertEqual(self.state(), 'error')

    def test_failure_backoff_sequence_and_success_reset(self):
        self.network.side_effect = lambda *a: response(status=503)
        now = NOW
        for delay in (1, 2, 4, 8, 12, 24, 24):
            self.run_sources(now)
            self.assertEqual(self.state('next_eligible_at'), scheduler.stamp(now + timedelta(hours=delay)))
            calls = self.network.call_count
            self.run_sources(now + timedelta(seconds=1))
            self.assertEqual(self.network.call_count, calls)
            now += timedelta(hours=delay)
        self.network.side_effect = None; self.network.return_value = response()
        self.run_sources(now)
        self.assertEqual(self.state('consecutive_failures'), 0)
        self.assertEqual(self.state(), 'ok')

    def test_failed_source_does_not_clear_old_entries_or_block_another_source(self):
        self.network.side_effect = [response(rss()), response(status=503), response()]
        self.run_sources()
        success = self.state('last_success_at')
        self.run_sources(NOW + timedelta(hours=1), [FEED, dict(FEED, id='z-other', url='https://example.org/feed')])
        self.assertEqual(len(web.entries(self.db)), 1)
        self.assertEqual(self.db.execute('select last_success_at from source_fetch_state where source_id=?', (scheduler.plans([FEED])[0][0],)).fetchone()[0], success)
        self.assertEqual(sorted(r[0] for r in self.db.execute('select status from source_fetch_state')), ['error', 'ok'])

    def test_blocked_has_no_automatic_retry_and_logs_no_body_or_url(self):
        self.network.side_effect = [response(b'private body', status=403)]
        self.run_sources(); self.run_sources(NOW + timedelta(days=3))
        self.assertEqual(self.network.call_count, 1)
        self.assertEqual(self.state(), 'blocked')
        self.assertIn('"source_status": "blocked"', self.log.getvalue())
        self.assertNotIn(FEED['url'], self.log.getvalue())
        self.assertNotIn('private body', self.log.getvalue())

    def test_retry_after_is_respected_and_never_before_next_natural_hour(self):
        self.network.side_effect = [response(headers={'retry-after': '7200'}, status=429)]
        self.run_sources()
        self.assertEqual(self.state('next_eligible_at'), scheduler.stamp(NOW + timedelta(hours=2)))
        self.run_sources(NOW + timedelta(hours=1))
        self.assertEqual(self.network.call_count, 1)
        self.network.side_effect = [response(headers={'retry-after': '0'}, status=429)]
        self.run_sources(NOW + timedelta(hours=2))
        self.assertEqual(self.state('next_eligible_at'), scheduler.stamp(scheduler.next_hour(NOW + timedelta(hours=2))))
        for value in ('0', 'Wed, 21 Oct 2026 03:00:00 GMT'):
            error = None
            try: http.check(response(headers={'retry-after': value}, status=429), NOW)
            except http.FetchFailure as caught: error = caught
            self.assertEqual(error.code, 'rate_limited')
            self.assertIsNotNone(error.retry_at.tzinfo)

    def test_image_failure_then_feed_304_retries_only_missing_image(self):
        self.network.side_effect = [response(rss(True), {'etag': '"one"'}), http.FetchFailure('network'),
                                    response(status=304), response(png())]
        self.run_sources()
        self.assertEqual(self.state(), 'partial')
        self.assertEqual(self.db.execute('select images from entry').fetchone()[0], '[]')
        self.run_sources(NOW + timedelta(hours=1))
        self.assertEqual(self.network.call_count, 4)
        [image] = json.loads(self.db.execute('select images from entry').fetchone()[0])
        self.assertTrue((self.root / image).is_file())
        self.assertEqual(self.state(), 'ok')
        self.assertEqual(self.db.execute('select count(*) from fetch_resource_state where image_refs!=?', ('[]',)).fetchone()[0], 1)
        # The DB has the parsed content; the runner's separate media cache can disappear.
        (self.root / image).unlink()
        self.network.side_effect = [response(status=304), response(png())]
        self.run_sources(NOW + timedelta(hours=2))
        self.assertTrue((self.root / image).is_file())
        self.assertEqual(self.network.call_count, 6)

    def test_repeated_resource_has_one_request_and_half_image_is_not_cache(self):
        scheduler.ensure_schema(self.db); self.db.commit()
        batch, _ = scheduler.claim(self.db, 'test', NOW)
        target = self.root / 'media/c/1_1.webp.tmp'; target.parent.mkdir(parents=True); target.write_bytes(b'half')
        self.network.return_value = response(png()); self.network.side_effect = None
        paths = telegram.download_images('c', 1, ['https://example.com/pic', 'https://example.com/pic'], batch=batch, owner=('msg', 'c', 1))
        self.assertEqual(len(paths), 2)
        self.assertEqual(self.network.call_count, 1)
        for path in paths:
            with Image.open(self.root / path) as image: image.verify()
        self.assertEqual(sum(len(r.body) for r in batch.responses.values() if isinstance(r, http.Response)), 0)

    def test_blocked_first_image_keeps_later_image_work_for_manual_recovery(self):
        # Both photo nodes belong to the same message.
        two_images = page(104, at=NOW, photo=True).replace('</a></div>',
            '</a><a class="tgme_widget_message_photo_wrap" style="background-image:url(https://example.com/second.jpg)"></a></div>')
        self.network.side_effect = [response(two_images.encode()), response(status=403)]
        self.run_sources(sources=[TG])
        refs = self.db.execute("select image_refs from fetch_resource_state where resource_key like 'image:%'").fetchall()
        self.assertEqual(sum(len(json.loads(r[0])) for r in refs), 2)
        # Simulate a separately approved manual recovery ONLY in this temporary fixture DB.
        self.db.execute("update source_fetch_state set status='interrupted',error_code=null,next_eligible_at=?", (scheduler.stamp(scheduler.next_hour(NOW)),))
        self.db.commit()
        self.network.side_effect = [response(page(104, at=NOW).encode()), response(page(at=NOW).encode()), response(png()), response(png())]
        self.run_sources(NOW + timedelta(hours=1), [TG])
        images = json.loads(self.db.execute('select images from msg where id=104').fetchone()[0])
        self.assertEqual(images, ['media/chan/104_1.webp', 'media/chan/104_2.webp'])
        self.assertEqual(self.state(), 'ok')

    def test_image_retry_restores_original_image_order(self):
        scheduler.ensure_schema(self.db); self.db.commit()
        batch, _ = scheduler.claim(self.db, 'test', NOW)
        self.network.side_effect = [http.FetchFailure('network'), response(png())]
        images = telegram.download_images('c', 1, ['https://example.com/first', 'https://example.com/second'], batch=batch, owner=('msg', 'c', 1))
        self.db.execute('insert into msg values(?,?,?,?,?,?,?)', ('c', 1, NOW.isoformat(), 'text', '[]', '', json.dumps(images)))
        batch.finish()
        next_batch, _ = scheduler.claim(self.db, 'test', NOW + timedelta(hours=1))
        self.network.side_effect = [response(png())]
        next_batch.retry_images(); next_batch.finish()
        self.assertEqual(json.loads(self.db.execute('select images from msg where id=1').fetchone()[0]),
                         ['media/c/1_1.webp', 'media/c/1_2.webp'])

    def test_expired_image_resource_metadata_is_pruned_without_dropping_feed_validator(self):
        self.network.side_effect = [response(rss(True), {'etag': '"one"'}), response(png()), response(status=304)]
        self.run_sources(); self.run_sources(NOW + timedelta(days=15))
        self.assertEqual(self.db.execute("select count(*) from fetch_resource_state where resource_key like 'image:%'").fetchone()[0], 0)
        self.assertEqual(self.db.execute("select etag from fetch_resource_state where resource_key like 'feed:%'").fetchone()[0], '"one"')
        self.assertEqual(len(web.entries(self.db)), 1)

    def test_no_fetch_old_database_is_byte_and_mtime_unchanged_and_hides_private(self):
        database = self.root / 'tg.db'
        before = (database.read_bytes(), database.stat().st_mtime_ns)
        (self.root / 'media').rmdir()
        cfg = dict(topics={}, sources=[dict(FEED, visibility='private'), TG])
        with patch.dict(os.environ, {'NO_FETCH': '1', 'SITE_MODE': 'public', 'MAIL_DIGEST': '0'}):
            self.assertEqual(pipeline.collect(cfg, NOW), ([], []))
        self.assertEqual((database.read_bytes(), database.stat().st_mtime_ns), before)
        self.assertFalse((self.root / 'media').exists())
        self.network.assert_not_called()
        self.assertFalse(self.db.execute("select 1 from sqlite_master where name='source_fetch_state'").fetchone())

    def test_public_fetch_filters_private_before_planning(self):
        self.network.return_value = response(); self.network.side_effect = None
        cfg = dict(topics={}, sources=[FEED, dict(TG, visibility='private')])
        with patch.dict(os.environ, {'NO_FETCH': '0', 'SITE_MODE': 'public', 'MAIL_DIGEST': '0'}):
            pipeline.collect(cfg, NOW)
        self.assertEqual(self.network.call_count, 1)
        self.assertNotIn('channel', self.log.getvalue())

    def test_interrupted_claim_survives_process_exit_and_same_hour_is_not_reopened(self):
        code = '''
import os, sqlite3, sys
from pathlib import Path
from datetime import datetime
from shiguang.ingest import scheduler
db = sqlite3.connect(sys.argv[1])
with scheduler.collection_lock(Path(sys.argv[1])) as held:
    assert held
    scheduler.ensure_schema(db)
    scheduler.claim(db, scheduler.plans([%r])[0][0], datetime.fromisoformat(sys.argv[2]))
    os._exit(0)
''' % FEED
        subprocess.run([sys.executable, '-c', code, str(self.root / 'tg.db'), NOW.isoformat()], check=True)
        self.run_sources()
        self.network.assert_not_called()
        self.assertEqual(self.state(), 'interrupted')
        self.assertEqual(self.db.execute('select status from source_fetch_batch').fetchone()[0], 'interrupted')
        self.network.return_value = response(); self.network.side_effect = None
        self.run_sources(NOW + timedelta(minutes=1))
        self.assertEqual(self.network.call_count, 1)

    def test_another_process_holds_lock_busy_build_is_read_only(self):
        code = '''
import sys
from pathlib import Path
from shiguang.ingest.scheduler import collection_lock
with collection_lock(Path(sys.argv[1])) as held:
    assert held
    print('held', flush=True)
    sys.stdin.readline()
'''
        child = subprocess.Popen([sys.executable, '-c', code, str(self.root / 'tg.db')], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
        try:
            self.assertEqual(child.stdout.readline().strip(), 'held')
            before = (self.root / 'tg.db').read_bytes()
            with patch.dict(os.environ, {'NO_FETCH': '0', 'SITE_MODE': 'public', 'MAIL_DIGEST': '0'}):
                pipeline.collect(dict(topics={}, sources=[FEED]), NOW)
            self.assertEqual((self.root / 'tg.db').read_bytes(), before)
            self.assertIn('busy', self.log.getvalue())
            self.network.assert_not_called()
        finally:
            child.communicate('\n', timeout=5)

    def test_partial_schema_is_not_silently_rebuilt(self):
        scheduler.ensure_schema(self.db); self.db.execute('drop table fetch_resource_state'); self.db.commit()
        with self.assertRaisesRegex(RuntimeError, 'incomplete'):
            self.run_sources()
        self.network.assert_not_called()

    def test_content_and_old_entry_id_survive_migration_and_expired_batches_are_bounded(self):
        self.db.execute('insert into msg values(?,?,?,?,?,?,?)', ('chan', 100, NOW.isoformat(), 'old', '[]', '', '[]'))
        self.db.execute('insert into gap values(?,?,?,?)', ('chan', 90, 80, NOW.isoformat()))
        self.db.commit()
        self.network.return_value = response(); self.network.side_effect = None
        self.run_sources()
        self.assertEqual(self.db.execute('select id,text from msg').fetchall(), [(100, 'old')])
        self.assertEqual(self.db.execute('select before,newest from gap').fetchall(), [(90, 80)])
        self.run_sources(NOW + timedelta(days=8))
        self.assertEqual(self.db.execute('select count(*) from source_fetch_batch').fetchone()[0], 1)

    def test_unknown_schema_and_bad_state_stop_before_http(self):
        scheduler.ensure_schema(self.db)
        self.db.execute('update source_fetch_meta set version=99'); self.db.commit()
        with self.assertRaisesRegex(RuntimeError, 'unsupported'):
            self.run_sources()
        self.network.assert_not_called()

    def test_corrupt_resource_state_stops_before_any_source_request(self):
        scheduler.ensure_schema(self.db)
        self.db.execute('insert into fetch_resource_state(source_id,resource_key,image_refs) values(?,?,?)', ('source', 'image:bad', '{broken'))
        self.db.commit()
        with self.assertRaisesRegex(RuntimeError, 'damaged resource'):
            self.run_sources()
        self.network.assert_not_called()

    def test_telegram_budget_exhaustion_keeps_a_resumable_gap(self):
        self.network.side_effect = [response(page(1000 - i, at=NOW).encode()) for i in range(200)]
        self.run_sources(sources=[TG])
        self.assertEqual(self.network.call_count, 200)
        self.assertEqual(self.state(), 'partial')
        self.assertEqual(self.db.execute('select before,newest from gap').fetchall(), [(801, None)])
        self.network.side_effect = [response(page(1000, at=NOW).encode()), response(page(800, at=NOW - timedelta(hours=73)).encode())]
        self.run_sources(NOW + timedelta(hours=1), [TG])
        self.assertEqual(self.db.execute('select * from gap').fetchall(), [])
        self.assertEqual(self.state(), 'ok')

    def test_image_block_during_first_telegram_page_preserves_history_gap(self):
        self.network.side_effect = [response(page(104, 103, at=NOW, photo=True).encode()), response(status=403)]
        self.run_sources(sources=[TG])
        self.assertEqual(self.network.call_count, 2)
        self.assertEqual(self.state(), 'blocked')
        self.assertEqual(self.db.execute('select before from gap').fetchall(), [(103,)])

    def test_telegram_gap_is_preserved_and_recovered_without_duplicate_page_requests(self):
        self.db.execute('insert into msg values(?,?,?,?,?,?,?)', ('chan', 100, NOW.isoformat(), 'old', '[]', '', '[]')); self.db.commit()
        self.network.side_effect = [response(page(104, 103, at=NOW).encode()), http.FetchFailure('network')]
        self.run_sources(sources=[TG])
        self.assertEqual(self.db.execute('select before,newest from gap').fetchall(), [(103, 100)])
        self.assertEqual(self.state(), 'partial')
        self.network.side_effect = [response(page(104, at=NOW).encode()), response(page(102, 101, 100, at=NOW).encode())]
        self.run_sources(NOW + timedelta(hours=1), [TG])
        self.assertEqual(self.db.execute('select * from gap').fetchall(), [])
        self.assertEqual(self.state(), 'ok')
        self.assertEqual(self.db.execute('select id from msg order by id').fetchall(), [(100,), (101,), (102,), (103,), (104,)])


class HttpTests(unittest.TestCase):
    def test_real_curl_transport_reads_redirect_headers_and_conditional_304(self):
        requests = []
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                requests.append((self.path, self.headers.get('If-None-Match')))
                if self.path == '/start':
                    self.send_response(302); self.send_header('Location', '/feed'); self.end_headers()
                elif self.headers.get('If-None-Match') == '"fixture"':
                    self.send_response(304); self.send_header('ETag', '"fixture"'); self.end_headers()
                else:
                    self.send_response(200); self.send_header('ETag', '"fixture"'); self.end_headers(); self.wfile.write(b'<rss><channel/></rss>')
            def log_message(self, *args): pass
        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.addCleanup(server.server_close); self.addCleanup(server.shutdown)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        origin = 'http://127.0.0.1:' + str(server.server_port)
        first = http.request(origin + '/start')
        self.assertEqual((first.status, first.headers['etag'], first.body), (200, '"fixture"', b'<rss><channel/></rss>'))
        second = http.request(origin + '/feed', {'If-None-Match': first.headers['etag']})
        self.assertEqual((second.status, second.body), (304, b''))
        self.assertEqual(requests, [('/start', None), ('/feed', None), ('/feed', '"fixture"')])

    def test_challenge_and_login_are_blocked_but_feed_news_is_not(self):
        for body in (b'<html><title>Captcha</title></html>', b'<html><title>Sign in</title></html>'):
            with self.assertRaises(http.FetchFailure) as caught:
                http.check(response(body), NOW)
            self.assertEqual(caught.exception.code, 'blocked')
        http.check(response(b'<rss><channel><title>Captcha news</title></channel></rss>'), NOW)

    def test_http_headers_follow_final_redirect_response_without_logging_body(self):
        def curl(args, **kwargs):
            fd = int(args[args.index('-D') + 1].rsplit('/', 1)[1])
            os.write(fd, b'HTTP/1.1 301 Moved\r\nETag: old\r\n\r\nHTTP/2 200 OK\r\nETag: "new"\r\n\r\n')
            return subprocess.CompletedProcess(args, 0, b'body', b'')
        with patch.object(http.subprocess, 'run', side_effect=curl):
            result = http.request('https://example.com/feed')
        self.assertEqual((result.status, result.headers, result.body), (200, {'etag': '"new"'}, b'body'))


if __name__ == '__main__':
    unittest.main()
