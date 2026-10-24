#!/usr/bin/env python3
"""拾光热榜：收内容 → 统一 → 加工 → 出页。Box bot routine 负责采集并发布 gh-pages。

NO_FETCH=1 跳过 Telegram 抓取（只读 tg.db）；SITE_MODE=private 构建含邮件的内网版。
"""
import os
from contextlib import nullcontext
from datetime import datetime
from pathlib import Path
from shiguang.config import config, private_mode
from shiguang.model import BEIJING
from shiguang.ingest import telegram, web, scheduler, trial
from shiguang.site.history import RETIRED
from shiguang.enrich.clean import clean, headline
from shiguang.enrich.topics import classify
from shiguang.enrich.hot import hot_stream
from shiguang.site.build import build


def collect(cfg, now):
    """Fetch (unless NO_FETCH=1), then every visible stored Telegram message as a cleaned row, and
    every stored feed entry (RSS / YouTube)."""
    visible = [s for s in cfg['sources'] if private_mode() or s['visibility'] == 'public']
    channels = {s['channel']: s['name'] for s in visible if s['type'] == 'telegram'}
    feeds = [s for s in visible if s['type'] == 'feed']
    fetch = os.getenv('NO_FETCH') != '1'
    database = Path(telegram.D) / 'tg.db'
    if not fetch and (os.getenv('SAMPLE_DATA') == '1' or not database.is_file()):
        return sample_rows(cfg, now), []
    if fetch and not database.is_file():
        raise RuntimeError('tg.db missing; restore known state before collecting')
    with scheduler.collection_lock(database) if fetch else nullcontext(True) as acquired:
        if fetch and not acquired:
            for source in visible:
                if source['type'] in ('telegram', 'feed'):
                    scheduler.emit(source, result='skip', skip_reason='busy', requests=0)
        db, images_migrated = telegram.open_db(fetch and acquired)
        try:
            if fetch and acquired:
                trial_sources = trial.load()['sources']
                scheduler.run(db, visible, images_migrated=images_migrated)
                trial.run(db, trial_sources)
                telegram.expire_media(db, now)
                db.commit()
            rows = []
            for ch, i, ts, t, raw, images in telegram.messages(db):
                if ch not in channels and ch not in RETIRED: continue
                t = clean(t)
                if not t: continue
                title, body = headline(t, raw)
                rows.append(dict(images=images, ch=ch, id=i, ts=ts, text=t, title=title, body=body,
                                 cat=classify(t, cfg['topics'], title), day=ts[:10], url=f'https://t.me/{ch}/{i}'))
            ids = {s['id'] for s in feeds}
            return rows, [e for e in web.entries(db) if e['source'] in ids]
        finally:
            db.close()


def telegram_rows(cfg, now):
    return collect(cfg, now)[0]


def sample_rows(cfg, now):
    """Synthetic offline preview; never accesses the database or remote services."""
    import json
    from datetime import timedelta
    from shiguang.config import ROOT
    fixture = json.loads((ROOT / 'tests/fixtures/news-sample.json').read_text())
    sources = [s for s in cfg['sources'] if s['type'] == 'telegram' and s['visibility'] == 'public']
    rows = []
    for offset in range(8):
        for index, (cat, title, text) in enumerate(fixture['headlines']):
            source = sources[index % len(sources)]
            moment = (now.astimezone(BEIJING) - timedelta(days=offset)).replace(hour=index + 1, minute=0, second=0, microsecond=0)
            native_id = 100000 + offset * 10 + index
            rows.append(dict(ch=source['channel'], id=native_id, ts=moment.isoformat(), text=text,
                             title='[示例] ' + title, body=text, cat=cat, day=moment.date().isoformat(),
                             images=[], url=f'https://t.me/{source["channel"]}/{native_id}'))
    return rows


def main(now=None):
    now = now or datetime.now(BEIJING)
    cfg = config()
    rows, entries = collect(cfg, now)
    active = [row for row in rows if row['ch'] not in RETIRED]
    build(rows, hot_stream(active, now, cfg['hot']['keywords']), now, entries)


if __name__ == '__main__':
    main()
