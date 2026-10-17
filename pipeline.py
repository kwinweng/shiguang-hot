#!/usr/bin/env python3
"""拾光热点：收内容 → 统一 → 加工 → 出页。每小时由 GitHub Actions 运行，本机 run.sh 也调用它。

NO_FETCH=1 跳过 Telegram 抓取（只读 tg.db）；SITE_MODE=private 构建含邮件的内网版。
"""
import os
from datetime import datetime
from shiguang.config import config, private_mode
from shiguang.model import BEIJING
from shiguang.ingest import telegram
from shiguang.enrich.clean import clean, headline
from shiguang.enrich.topics import classify
from shiguang.enrich.hot import hot_list
from shiguang.site.build import build


def telegram_rows(cfg, now):
    """Fetch (unless NO_FETCH=1), then every visible stored message as a cleaned row."""
    channels = {s['channel']: s['name'] for s in cfg['sources'] if s['type'] == 'telegram' and (private_mode() or s['visibility'] == 'public')}
    fetch = os.getenv('NO_FETCH') != '1'
    db, images_migrated = telegram.open_db(fetch)
    try:
        if fetch:
            telegram.fetch(db, channels, now, images_migrated)
            telegram.expire_media(db, now)
            db.commit()
        rows = []
        for ch, i, ts, t, raw, images in telegram.messages(db):
            if ch not in channels: continue
            t = clean(t)
            if not t: continue
            title, body = headline(t, raw)
            rows.append(dict(images=images, ch=ch, id=i, ts=ts, text=t, title=title, body=body,
                             cat=classify(t, cfg['categories']), day=ts[:10], url=f'https://t.me/{ch}/{i}'))
        return rows
    finally:
        db.close()


def main(now=None):
    now = now or datetime.now(BEIJING)
    cfg = config()
    rows = telegram_rows(cfg, now)
    build(rows, hot_list(rows, now), now)


if __name__ == '__main__':
    main()
