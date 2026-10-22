#!/usr/bin/env python3
"""Print and save trial counts by first collection day in Beijing time."""
import argparse
import sqlite3
import sys
from contextlib import closing
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from shiguang.config import ROOT
from shiguang.ingest import trial
from shiguang.model import BEIJING


def report(db, cfg, days=7, now=None):
    if days < 1:
        raise ValueError('days 必须为正整数')
    now = now or datetime.now(BEIJING)
    today = now.astimezone(BEIJING).date()
    dates = [(today - timedelta(days=n)).isoformat() for n in reversed(range(days))]
    counts = Counter()
    if db.execute("select 1 from sqlite_master where type='table' and name='trial_item'").fetchone():
        for source, section, category, fetched in db.execute('select source_id,section,category,fetched_at from trial_item'):
            day = datetime.fromisoformat(fetched).astimezone(BEIJING).date().isoformat()
            if dates[0] <= day <= dates[-1]:
                for kind, key in [('source', source), ('section', section), ('category', category)]:
                    counts[day, kind, key] += 1
    lines = [f'# 试跑数量报告 {today}', '', '新增按首次 fetched_at（北京时间）计数，非发布时间。', '']
    def table(label, kind, columns):
        lines.extend([f'## {label}', '', '| 日期 | ' + ' | '.join(name for key, name in columns) + ' |',
                      '| --- | ' + ' | '.join('---' for _ in columns) + ' |'])
        for day in dates:
            lines.append('| ' + day + ' | ' + ' | '.join(str(counts[day, kind, key]) for key, name in columns) + ' |')
        lines.append('')
    table('按源', 'source', [(s['id'], s['name']) for s in cfg['sources']])
    table('按栏目', 'section', [(s, s) for s in dict.fromkeys(c['section'] for c in cfg['categories'])])
    table('按分类', 'category', [(c['id'], c['name']) for c in cfg['categories']])
    success = {}
    if db.execute("select 1 from sqlite_master where type='table' and name='source_fetch_state'").fetchone():
        success = dict(db.execute('select source_id,last_success_at from source_fetch_state'))
    lines.extend(['## 最近成功抓取（北京时间）', '', '| 来源 | 最近成功 |', '| --- | --- |'])
    for source in cfg['sources']:
        last = success.get('trial:' + source['id'])
        shown = datetime.fromisoformat(last).astimezone(BEIJING).isoformat() if last else '尚无成功记录'
        lines.append(f"| {source['name']} | {shown} |")
    return '\n'.join(lines) + '\n'


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--days', type=int, default=7)
    parser.add_argument('--db', type=Path, default=ROOT / 'tg.db')
    parser.add_argument('--output', type=Path, default=ROOT / 'reports/trial')
    args = parser.parse_args(argv)
    if args.days < 1:
        parser.error('--days 必须为正整数')
    now = datetime.now(BEIJING)
    with closing(sqlite3.connect(args.db.resolve().as_uri() + '?mode=ro', uri=True)) as db:
        text = report(db, trial.load(), args.days, now)
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / f'{now.date()}.md').write_text(text, encoding='utf-8')
    print(text, end='')


if __name__ == '__main__':
    main()
