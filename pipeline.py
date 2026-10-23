#!/usr/bin/env python3
"""拾光热榜：收内容 → 统一 → 加工 → 出页。Box cron 负责采集，GitHub Actions 只读建站；本机 run.sh 也调用它。

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


def main(now=None):
    now = now or datetime.now(BEIJING)
    cfg = config()
    rows, entries = collect(cfg, now)
    active = [row for row in rows if row['ch'] not in RETIRED]
    build(rows, hot_stream(active, now, cfg['hot']['keywords']), now, entries)


if __name__ == '__main__':
    main()
