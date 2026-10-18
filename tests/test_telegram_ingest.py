"""Telegram paging failures retain a cursor for later backfill; all network calls are mocked."""
import io
import json
import os
import subprocess
import tempfile
import unittest
from datetime import datetime, timedelta
from unittest.mock import call, patch

from shiguang.ingest import telegram
from shiguang.model import BEIJING


NOW = datetime(2026, 10, 18, 12, tzinfo=BEIJING)
URL = 'https://t.me/s/chan'


def page(*ids, at=NOW, photo=False):
    messages = []
    for i in ids:
        image = '<a class="tgme_widget_message_photo_wrap" style="background-image:url(https://example.com/photo.jpg)"></a>' if photo else ''
        messages.append(f'''<div class="tgme_widget_message" data-post="chan/{i}">
<time datetime="{at.isoformat()}"></time>
<div class="tgme_widget_message_text">Message {i}<br><a href="https://example.com/story">link</a></div>{image}</div>''')
    return '<main class="tgme_channel_history">' + ''.join(messages) + '</main>'


class GetTests(unittest.TestCase):
    def test_rejects_curl_failure_empty_and_non_telegram_bodies(self):
        for rc, body in [(28, page(1)), (0, ''), (0, ' \n'), (0, '<html>Bad gateway</html>')]:
            with self.subTest(rc=rc, body=body), patch.object(telegram.subprocess, 'run', return_value=subprocess.CompletedProcess([], rc, body, 'timeout')):
                with self.assertRaises(telegram.FetchError):
                    telegram.get(URL)

    def test_accepts_valid_end_of_history(self):
        for body in [page(), page(1), '<div class="tgme_widget_message_wrap"></div>']:
            with self.subTest(body=body), patch.object(telegram.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0, body, '')):
                self.assertEqual(telegram.get(URL), body)


class FetchTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        for name, value in [('D', temp.name), ('MEDIA', os.path.join(temp.name, 'media'))]:
            patcher = patch.object(telegram, name, value)
            patcher.start(); self.addCleanup(patcher.stop)
        network = patch.object(telegram.subprocess, 'run', side_effect=AssertionError('Unexpected network access'))
        self.curl = network.start(); self.addCleanup(network.stop)
        images = patch.object(telegram, 'download_images', return_value=[])
        self.images = images.start(); self.addCleanup(images.stop)
        stderr = patch.object(telegram.sys, 'stderr', new_callable=io.StringIO)
        self.stderr = stderr.start(); self.addCleanup(stderr.stop)
        self.db, _ = telegram.open_db(True)
        self.addCleanup(self.db.close)

    def seed(self, i):
        self.db.execute('insert into msg values(?,?,?,?,?,?,?)', ('chan', i, NOW.isoformat(), 'stored', '[]', '', '[]'))

    def gaps(self):
        return self.db.execute('select before,newest,at from gap where ch=? order by before', ('chan',)).fetchall()

    def status(self):
        return self.db.execute('select ok,err from status where ch=?', ('chan',)).fetchone()

    def ids(self):
        return [row[0] for row in self.db.execute('select id from msg where ch=? order by id', ('chan',))]

    def fetch_pages(self, pages, now=NOW):
        with patch.object(telegram, 'get', side_effect=lambda url: pages[url]) as get:
            telegram.fetch(self.db, ['chan'], now, False)
        return get

    def fail_mid_paging(self):
        self.seed(100)
        self.curl.side_effect = [subprocess.CompletedProcess([], 0, page(104, 103), ''), subprocess.CompletedProcess([], 28, '', 'timeout')]
        telegram.fetch(self.db, ['chan'], NOW, False)

    def test_curl_failure_mid_paging_records_gap_and_error(self):
        self.fail_mid_paging()
        self.assertEqual(self.ids(), [100, 103, 104])
        self.assertEqual(self.gaps(), [(103, 100, NOW.isoformat())])
        ok, err = self.status()
        self.assertEqual(ok, 0)
        self.assertTrue(err)
        self.assertIn('28', err)
        self.assertIn('gap', self.stderr.getvalue())

    def test_next_run_backfills_gap_and_clears_it(self):
        self.fail_mid_paging()
        self.db.commit(); self.db.close()
        self.db, _ = telegram.open_db(True)
        self.addCleanup(self.db.close)
        get = self.fetch_pages({URL: page(106, 104), URL + '?before=103': page(102, 101, 100, photo=True)})
        self.assertEqual(get.call_args_list, [call(URL), call(URL + '?before=103')])
        self.assertEqual(self.ids(), [100, 101, 102, 103, 104, 106])
        self.assertEqual(self.gaps(), [])
        self.assertEqual(self.status(), (1, None))
        text, links, html = self.db.execute('select text,links,html from msg where id=102').fetchone()
        self.assertEqual(text, 'Message 102\nlink')
        self.assertEqual(json.loads(links), ['https://example.com/story'])
        self.assertIn('<a href=', html)
        self.images.assert_any_call('chan', 102, ['https://example.com/photo.jpg'])

    def test_genuine_end_of_history_has_no_gap_or_error(self):
        self.fetch_pages({URL: page(3, 2), URL + '?before=2': page()})
        self.assertEqual(self.ids(), [2, 3])
        self.assertEqual(self.gaps(), [])
        self.assertEqual(self.status(), (1, None))

    def test_invalid_mid_page_is_not_end_of_history(self):
        for body in ['', '<html>Bad gateway</html>']:
            with self.subTest(body=body):
                self.curl.side_effect = [subprocess.CompletedProcess([], 0, page(3, 2), ''), subprocess.CompletedProcess([], 0, body, '')]
                telegram.fetch(self.db, ['chan'], NOW, False)
                self.assertEqual(self.gaps(), [(2, None, NOW.isoformat())])
                self.assertEqual(self.status()[0], 0)
                self.assertTrue(self.status()[1])
                self.db.execute('delete from gap')
                self.db.execute('delete from msg')

    def test_first_page_failure_keeps_existing_error_message(self):
        for result in [telegram.FetchError('timeout'), page()]:
            with self.subTest(result=result), patch.object(telegram, 'get', side_effect=[result]):
                telegram.fetch(self.db, ['chan'], NOW, False)
                self.assertEqual(self.gaps(), [])
                self.assertEqual(self.status(), (0, '页面无消息/打不开'))

    def test_gap_is_recorded_even_when_first_page_inserts_no_messages(self):
        undated = page(104).replace(f'<time datetime="{NOW.isoformat()}"></time>', '')
        with patch.object(telegram, 'get', side_effect=[undated, telegram.FetchError('timeout')]):
            telegram.fetch(self.db, ['chan'], NOW, False)
        self.assertEqual(self.ids(), [])
        self.assertEqual(self.gaps(), [(104, None, NOW.isoformat())])
        self.assertEqual(self.status(), (0, 'timeout'))

    def test_gap_retry_failure_saves_progress_and_original_bound(self):
        self.fail_mid_paging()
        with patch.object(telegram, 'get', side_effect=[page(104), page(102), telegram.FetchError('timeout')]) as get:
            telegram.fetch(self.db, ['chan'], NOW + timedelta(hours=1), False)
        self.assertEqual(get.call_args_list, [call(URL), call(URL + '?before=103'), call(URL + '?before=102')])
        self.assertEqual(self.gaps(), [(102, 100, NOW.isoformat())])
        self.assertEqual(self.status(), (0, 'timeout'))
        self.fetch_pages({URL: page(104), URL + '?before=102': page(101, 100)})
        self.assertEqual(self.ids(), [100, 101, 102, 103, 104])
        self.assertEqual(self.gaps(), [])

    def test_gap_page_budget_saves_progress(self):
        self.seed(300)
        self.db.execute('insert into gap values(?,?,?,?)', ('chan', 200, 100, NOW.isoformat()))
        with patch.object(telegram, 'GAP_PAGES', 2):
            get = self.fetch_pages({URL: page(300), URL + '?before=200': page(199), URL + '?before=199': page(198)})
        self.assertEqual(get.call_count, 3)
        self.assertEqual(self.gaps(), [(198, 100, NOW.isoformat())])
        self.fetch_pages({URL: page(300), URL + '?before=198': page(197, 100)})
        self.assertEqual(self.gaps(), [])
        self.assertIn(197, self.ids())

    def test_first_run_gap_preserves_original_72_hour_floor(self):
        with patch.object(telegram, 'get', side_effect=[page(104), telegram.FetchError('timeout')]):
            telegram.fetch(self.db, ['chan'], NOW, False)
        self.assertEqual(self.gaps(), [(104, None, NOW.isoformat())])
        self.fetch_pages({URL: page(104), URL + '?before=104': page(103, at=NOW - timedelta(hours=60)), URL + '?before=103': page(102, at=NOW - timedelta(hours=73))}, now=NOW + timedelta(days=2))
        self.assertEqual(self.ids(), [103, 104])
        self.assertEqual(self.gaps(), [])
        self.assertEqual(self.status(), (1, None))

    def test_gap_can_end_at_genuine_end_of_history(self):
        self.seed(300)
        self.db.execute('insert into gap values(?,?,?,?)', ('chan', 200, 100, NOW.isoformat()))
        self.fetch_pages({URL: page(300), URL + '?before=200': page()})
        self.assertEqual(self.gaps(), [])
        self.assertEqual(self.status(), (1, None))

    def test_overlapping_gaps_keep_both_bounds_when_cursors_collide(self):
        self.seed(300)
        self.db.executemany('insert into gap values(?,?,?,?)', [('chan', 200, 100, NOW.isoformat()), ('chan', 150, 50, NOW.isoformat())])
        with patch.object(telegram, 'GAP_PAGES', 1):
            get = self.fetch_pages({URL: page(300), URL + '?before=200': page(150), URL + '?before=150': page(149)})
        self.assertEqual(get.call_args_list, [call(URL), call(URL + '?before=200'), call(URL + '?before=150')])
        # 200 collides with the still-existing 150 cursor, so UPDATE OR IGNORE keeps 200.
        self.assertEqual(self.gaps(), [(149, 50, NOW.isoformat()), (200, 100, NOW.isoformat())])

    def test_images_migration_still_revisits_stored_messages(self):
        self.seed(100)
        with patch.object(telegram, 'get', side_effect=[page(101, 100, photo=True), page(99, at=NOW - timedelta(days=15))]) as get:
            telegram.fetch(self.db, ['chan'], NOW, True)
        self.assertEqual(get.call_args_list, [call(URL), call(URL + '?before=100')])
        self.assertEqual(self.ids(), [100, 101])
        self.images.assert_any_call('chan', 100, ['https://example.com/photo.jpg'])
        self.assertEqual(self.status(), (1, None))

    def test_normal_paging_keeps_200_page_cap(self):
        with patch.object(telegram, 'get', side_effect=[page(1000 - i) for i in range(200)]) as get:
            telegram.fetch(self.db, ['chan'], NOW, False)
        self.assertEqual(get.call_count, 200)
        self.assertEqual(len(self.ids()), 200)
        self.assertEqual(self.status(), (0, '达到翻页上限，历史回填未完成'))


if __name__ == '__main__':
    unittest.main()
