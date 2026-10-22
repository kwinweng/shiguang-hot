#!/usr/bin/env python3
"""Measure r3 using synthetic 30/365-day archives, never a database or production output."""
import json
import shutil
import statistics
import sys
import tempfile
import time
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from shiguang.config import config
from shiguang.model import BEIJING, Item
from shiguang.site import history, pages, render
from shiguang.site.build import publish_assets, verify_public


def measure(count):
    samples = []
    for _ in range(3):
        with tempfile.TemporaryDirectory(prefix='news-offline-benchmark-') as folder:
            root = Path(folder)
            baseline = root / 'baseline'
            baseline.mkdir()
            now = datetime(2026, 10, 22, 12, tzinfo=BEIJING)
            sources = {s['id']: s for s in config()['sources'] if s['visibility'] == 'public'}
            items = []
            for n in range(1, count + 1):
                ts = (now - timedelta(days=n)).isoformat()
                items.append(Item('CE_Observe', 'CE_Observe', '科技', f'Offline {n}', 'Synthetic retained text',
                                  ts[:10], ts, native_id=n, url=f'https://example.invalid/{n}'))
            content = SimpleNamespace(sources=sources, stream=items, issues={}, private=False,
                                      today='2026-10-22', days=[i.day for i in items])
            site = render.Site(sources, pages.CORE, pages.TABS, pages.FAVORITES, False, now, [],
                               publish_assets(baseline, True))
            started = time.perf_counter()
            by_day, changed = history.prepare(content, site, baseline)
            writer = pages.Writer(site, baseline)
            for day in changed:
                pages.news_day_page(writer, content, day, by_day[day])
            full_seconds = time.perf_counter() - started
            hashes = {p.relative_to(baseline): history.hashlib.sha256(p.read_bytes()).hexdigest()
                      for p in (baseline/'archive').rglob('*') if p.suffix in ('.html', '.json') and p.name != 'manifest.json'}
            started = time.perf_counter()
            staged = root / 'staged'
            shutil.copytree(baseline, staged)
            copied = time.perf_counter()
            content.stream.append(Item('CE_Observe', 'CE_Observe', '科技', 'New day', 'Synthetic text',
                                       '2026-10-22', now.isoformat(), native_id=1000))
            content.days.append('2026-10-22')
            by_day, changed = history.prepare(content, site, staged)
            indexed = time.perf_counter()
            writer = pages.Writer(site, staged)
            for day in changed:
                pages.news_day_page(writer, content, day, by_day[day])
            rendered = time.perf_counter()
            verify_public(staged, config())
            verified = time.perf_counter()
            assert changed == {'2026-10-22'}, changed
            assert all(history.hashlib.sha256((staged/p).read_bytes()).hexdigest() == sha for p, sha in hashes.items())
            samples.append(dict(full_render_and_index_s=full_seconds, copy_s=copied-started,
                index_and_day_data_s=indexed-copied, render_s=rendered-indexed, verify_s=verified-rendered,
                total_s=verified-started, archive_days_rendered=len(changed), unchanged_days_rendered=0,
                bytes=sum(p.stat().st_size for p in staged.rglob('*') if p.is_file())))
    return dict(days=count, runs=3, median={key: statistics.median(row[key] for row in samples) for key in samples[0]},
                transfer='not performed (offline)', unchanged_hashes='all equal')


if __name__ == '__main__':
    print(json.dumps([measure(count) for count in (30, 365)], indent=2))
