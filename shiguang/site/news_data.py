"""Public news contracts and deterministic, offline daily sample summaries."""
import hashlib
import json
import os
import re
from collections import Counter
from datetime import date, datetime, timedelta

from shiguang.model import BEIJING, safe_link

CATEGORIES = ('全球', '财经', '科技AI', '社会', '其他')


def category(value):
    if value in ('AI', '科技', '数码', '开发者', '科技 AI', '科技AI'):
        return '科技AI'
    return value if value in CATEGORIES else '其他'


def messages(items, sources):
    """Filter before serialization, convert Beijing timestamps, then deduplicate exactly."""
    rows = []
    for item in items:
        source = sources.get(item.source_id)
        if not source or source['visibility'] != 'public':
            continue
        moment = item.moment
        if moment is None:
            continue
        moment = moment.astimezone(BEIJING)
        text = (item.body or item.title).strip()
        rows.append(dict(id=hashlib.sha256((item.source_id + str(item.native_id) + item.ts + item.title).encode()).hexdigest()[:20],
                         source=item.source_id, source_name=source['name'], type=source['type'],
                         time=moment.isoformat(), day=moment.date().isoformat(), hour=moment.strftime('%Y-%m-%d %H:00'),
                         title=item.title, text=text, summary=text[:500], category=category(item.category),
                         link=safe_link(item.url), image=next((p for p in item.images if safe_link(p) or
                         (re.fullmatch(r'[a-zA-Z0-9_/-]+\.(webp|png|jpg|jpeg|gif|avif)', p) and '..' not in p.split('/'))), '')))
    rows.sort(key=lambda r: (r['time'], r['id']), reverse=True)
    seen, result = set(), []
    for row in rows:
        key = (row['link'], row['text'][:50])
        if key not in seen:
            seen.add(key)
            result.append(row)
    return result


def source_stats(rows, sources, now, stale_hours=24):
    now = now.astimezone(BEIJING)
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week = start - timedelta(days=6)
    result = []
    for source in sorted(sources.values(), key=lambda s: (s['order'], s['id'])):
        if source['visibility'] != 'public':
            continue
        own = [r for r in rows if r['source'] == source['id'] and datetime.fromisoformat(r['time']) <= now]
        last = own[0]['time'] if own else None
        result.append(dict(id=source['id'], name=source['name'], type=source['type'],
                           today_count=sum(datetime.fromisoformat(r['time']) >= start for r in own),
                           seven_day_count=sum(datetime.fromisoformat(r['time']) >= week for r in own),
                           last_update=last, status='stale' if not last or
                           (now - datetime.fromisoformat(last)).total_seconds() > stale_hours * 3600 else 'ok',
                           stale_hours=stale_hours, messages=own))
    return result


class MockProvider:
    """Extractive sample only: no model, key, or network access."""
    name = 'mock'

    def summarize(self, day, rows):
        # Identical headlines form sample clusters; this is not semantic AI clustering.
        clusters = {}
        for row in rows:
            clusters.setdefault(row['title'], []).append(row)
        groups = sorted(clusters.values(), key=lambda group: (-len({r['source'] for r in group}), group[0]['title']))[:10]
        events = []
        for group in groups:
            first = group[0]
            sentences = [s.strip('。！？.!? \n') for s in re.split(r'[。！？.!?]+', first['summary']) if s.strip()]
            excerpt = '。'.join(sentences[:2])[:300]
            events.append(dict(title=first['title'], summary=f'{excerpt}。本事件整理自当天 {len(group)} 条原消息，请结合原文核对。',
                               category=first['category'], source_count=len({r['source'] for r in group}),
                               original_links=[r['link'] for r in group if r['link']], messages=group))
        return dict(schema=1, date=day, provider=self.name, sample=True,
                    summary='；'.join(e['title'] for e in events)[:60], events=events,
                    stats=dict(total=len(rows), sources=dict(Counter(r['source'] for r in rows)),
                               categories=dict(Counter(r['category'] for r in rows))), messages=rows)


class FlashProvider:
    """真实 AI 总结未验证，等新 key. Explicit future integration seam only."""
    def __init__(self):
        self.key = os.environ.get('FLASH_API_KEY')

    def summarize(self, day, rows):
        raise NotImplementedError('真实 AI 总结未验证，等新 key')


def daily_documents(rows, now, backfill_from=None):
    """Only completed Beijing days with actual authorized input get an archive."""
    today = now.astimezone(BEIJING).date().isoformat()
    floor = date.fromisoformat(backfill_from).isoformat() if backfill_from else '0001-01-01'
    return {day: MockProvider().summarize(day, [r for r in rows if r['day'] == day])
            for day in sorted({r['day'] for r in rows}) if floor <= day < today}


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + '\n')
