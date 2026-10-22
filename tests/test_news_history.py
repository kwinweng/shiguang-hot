"""Offline r3 acceptance: identity, publication order, public boundaries and archive reuse."""
import hashlib
import json
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from bs4 import BeautifulSoup
from shiguang.config import config
from shiguang.model import BEIJING, Item
from shiguang.site import history, pages, render
from shiguang.site.build import publish_assets, verify_public


def item(native=1, source='CE_Observe', ts='2026-10-22T12:00:00+08:00', category='科技'):
    return Item(source, source, category, f'Story {native}', 'offline text', ts[:10], ts,
                url=f'https://example.org/{native}', native_id=native)


def context(items):
    cfg = config()
    sources = {s['id']: s for s in cfg['sources'] if s['visibility'] == 'public'}
    site = render.Site(sources, [], [], {}, False, datetime(2026, 10, 22, 18, tzinfo=BEIJING), [],
                       {'version': 'offline', 'css': 'style.old.css', 'js': 'app.old.js'})
    content = SimpleNamespace(sources=sources, private=False, stream=items, issues={},
                              today='2026-10-22', days=sorted({i.day for i in items}, reverse=True))
    return content, site


class OrderingTests(unittest.TestCase):
    def test_order_precision_timezone_ties_and_no_cap(self):
        rows = [item(n) for n in range(25)]
        rows += [item(100, ts='2026-10-22'), item(101, ts='2026-10-22T23:59:00'),
                 item(102, ts='2026-10-21T20:30:00Z'), item(103, ts='2026-10-21T23:59:00+08:00')]
        c, _ = context(rows)
        ordered = history.ordered(rows + [rows[0]], c.sources)
        self.assertEqual(len(ordered), len(rows))
        self.assertEqual([r.native_id for r in ordered[:25]], list(reversed(range(25))))
        self.assertEqual(ordered[25].native_id, 102)
        self.assertEqual(history.day_of(ordered[25]), '2026-10-22')
        self.assertEqual({r.native_id for r in ordered[26:28]}, {100, 101})
        self.assertEqual(ordered[-1].native_id, 103)
        self.assertIsNone(history.publication(rows[26]))

    def test_stable_source_order_and_existing_bookmark_identity(self):
        rows = [item(8, 'world'), item(9, 'CE_Observe')]
        c, site = context(rows)
        c.sources['world']['order'] = 0
        c.sources['CE_Observe']['order'] = 100
        self.assertEqual(history.ordered(rows, c.sources), rows)
        for row in rows:
            saved = BeautifulSoup(render.bookmark_button(row, site.sources[row.source_id]), 'html.parser').button
            self.assertEqual(history.uid(row), json.loads(saved['data-bookmark'])['id'])


class ArchiveTests(unittest.TestCase):
    def test_incremental_new_day_correction_deletion_and_assets(self):
        with tempfile.TemporaryDirectory() as folder:
            out = Path(folder)
            old = item(ts='2025-10-22T12:00:00+08:00')
            c, site = context([old])
            by_day, changed = history.prepare(c, site, out)
            writer = pages.Writer(site, out)
            for day in changed:
                pages.news_day_page(writer, c, day, by_day[day])
            html = out / 'archive/2025-10-22.html'
            data = out / 'archive/data/2025-10-22.json'
            before = [p.read_bytes() for p in (html, data)]
            c.stream.append(item(2)); c.days.append('2026-10-22')
            _, changed = history.prepare(c, site, out)
            self.assertEqual(changed, {'2026-10-22'})
            (out / 'archive/2026-10-22.html').write_text('today baseline')
            self.assertEqual(before, [p.read_bytes() for p in (html, data)])
            old.title = 'corrected old story'
            _, changed = history.prepare(c, site, out)
            self.assertEqual(changed, {'2025-10-22'})
            c.stream.remove(old); c.days.remove('2025-10-22')
            _, changed = history.prepare(c, site, out)
            self.assertEqual(changed, {'2025-10-22'})
            self.assertEqual(json.loads(data.read_text())['items'], [])
            # Sidecars are optional for the original HTML contract, including rollback.
            data.unlink(); (out / 'archive/manifest.json').unlink()
            self.assertIn('Story 1', html.read_text())
            self.assertNotIn('fetch(', html.read_text())
            (out / 'style.old.css').write_text('/* old page */')
            publish_assets(out, True)
            self.assertTrue((out / 'style.old.css').is_file())

    def test_public_contract_excludes_private_unknown_and_internal_status(self):
        rows = [item(), item(2, 'mail'), item(3, 'unknown'),
                item(4, 'world', category='财经')]
        c, site = context(rows)
        # Even accidentally supplied private/unknown input cannot create a date or tuple.
        c.days = ['2026-10-22']
        with tempfile.TemporaryDirectory() as folder:
            out = Path(folder)
            history.prepare(c, site, out)
            manifest = json.loads((out / 'archive/manifest.json').read_text())
            tuples = manifest['days']['2026-10-22']['joint']
            self.assertEqual({r[0] for r in tuples}, {'CE_Observe', 'world'})
            data = json.loads((out / 'archive/data/2026-10-22.json').read_text())
            self.assertEqual(len(data['items']), 2)
            self.assertNotIn('fetch_status', json.dumps(data))
            verify_public(out, config())
            private = next(s for s in config()['sources'] if s['id'] == 'mail')
            (out / 'leak.json').write_text(json.dumps({'source': private['id']}))
            with self.assertRaises(RuntimeError):
                verify_public(out, config())

    def test_year_old_text_and_expired_images_need_no_network(self):
        rows = [item(1, ts='2025-10-22'), item(2, ts='2026-09-22')]
        rows[0].images = ['media/expired.webp']
        c, site = context(rows)
        with tempfile.TemporaryDirectory() as folder, patch('urllib.request.urlopen', side_effect=AssertionError('network')):
            out = Path(folder)
            history.prepare(c, site, out)
            manifest = json.loads((out / 'archive/manifest.json').read_text())
            self.assertEqual(manifest['earliest'], '2025-10-22')
            record = json.loads((out / 'archive/data/2025-10-22.json').read_text())['items'][0]
            self.assertEqual(record['precision'], 'date')
            self.assertIn('仅日期', record['html'])
            self.assertIn('offline text', record['html'])
            self.assertIn('data-bookmark', record['html'])

    def test_private_baseline_cannot_leak_private_dates_into_public_manifest(self):
        c, site = context([item(ts='2026-10-22')])
        c.private = True
        c.stream.append(item(2, ts='2020-01-01'))
        c.days.append('2020-01-01')
        with tempfile.TemporaryDirectory() as folder:
            out = Path(folder)
            history.prepare(c, site, out)
            (out / 'archive/2020-01-01.html').write_text('private historical input')
            c.private = False; c.stream.pop(); c.days.pop()
            history.prepare(c, site, out)
            manifest = json.loads((out / 'archive/manifest.json').read_text())
            self.assertNotIn('2020-01-01', manifest['days'])
            self.assertFalse((out / 'archive/2020-01-01.html').exists())
            self.assertFalse((out / 'archive/data/2020-01-01.json').exists())

    def test_build_excludes_unknown_dates_and_private_media_from_reused_tree(self):
        cfg = config()
        public = next(s for s in cfg['sources'] if s['id'] == 'CE_Observe')
        cfg['sources'].append(dict(public, id='unknown', channel='unknown'))
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); out = root / 'out'; out.mkdir()
            for channel in (public['channel'], 'unknown'):
                (root / 'media' / channel).mkdir(parents=True)
                (root / 'media' / channel / 'sample.webp').write_bytes(b'offline image')
            (out / 'media' / 'private-channel').mkdir(parents=True)
            (out / 'media' / 'private-channel' / 'old.webp').write_bytes(b'private')
            rows = [dict(ch='unknown', id=1, title='unknown story', body='', images=[],
                         ts='2020-01-01T12:00:00+08:00', day='2020-01-01', cat='科技')]
            with patch.object(pages, 'config', return_value=cfg), patch.object(pages, 'ROOT', root), \
                 patch.object(pages, 'load_issues', return_value=[]), patch.object(pages, 'private_mode', return_value=False):
                pages.write_pages(rows, [], datetime(2026, 10, 22, tzinfo=BEIJING), out, publish_assets(out, True))
            self.assertFalse((out / 'media/private-channel').exists())
            self.assertFalse((out / 'media/unknown').exists())
            self.assertTrue((out / 'media' / public['channel'] / 'sample.webp').exists())
            self.assertNotIn('2020-01-01', (out / 'archive/manifest.json').read_text())

    def test_thirty_and_365_day_archive_reuse(self):
        for count in (30, 365):
            with self.subTest(days=count), tempfile.TemporaryDirectory() as folder:
                rows = [item(n, ts=(datetime(2026, 10, 21, tzinfo=BEIJING) - timedelta(days=n)).isoformat())
                        for n in range(count)]
                c, site = context(rows)
                out = Path(folder)
                by_day, changed = history.prepare(c, site, out)
                for day in changed:
                    (out / f'archive/{day}.html').write_text(f'unchanged {day}')
                before = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in (out/'archive/data').iterdir()}
                c.stream.append(item(1000)); c.days.append('2026-10-22')
                _, changed = history.prepare(c, site, out)
                self.assertEqual(changed, {'2026-10-22'})
                for name, sha in before.items():
                    self.assertEqual(hashlib.sha256((out/'archive/data'/name).read_bytes()).hexdigest(), sha)


if __name__ == '__main__':
    unittest.main()
