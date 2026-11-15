"""按北京日期增量归档，并写出站点搜索索引。

2026-11-15 21:26 阿欢定：底栏「历史」改成「热搜」，按日期翻新闻的历史页去掉，所以不再写 data/history/。
归档本身（var/rebang/archive/）照旧保留，供搜索与 8:30 私聊稿补漏。
"""
from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

TIMEZONE = 'Asia/Shanghai'
BEIJING = ZoneInfo(TIMEZONE)
ARCHIVE_DAY_SCHEMA = 'rebang.archive-day/1'
ARCHIVE_INDEX_SCHEMA = 'rebang.archive-index/1'
HISTORY_INDEX_SCHEMA = 'rebang.history-index/1'
HISTORY_DAY_SCHEMA = 'rebang.history-day/1'
SEARCH_INDEX_SCHEMA = 'rebang.search-index/1'
EMPTY_MESSAGE = '这天没有内容'
DAY_NAME = re.compile(r'^\d{4}-\d{2}-\d{2}\.json$')

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ARCHIVE_DIR = REPO_ROOT / 'var' / 'rebang' / 'archive'


def beijing_date(value) -> str:
    """把带时区的时间落到 Asia/Shanghai 的日历日（YYYY-MM-DD）。"""
    if isinstance(value, datetime):
        moment = value
    else:
        moment = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    if moment.tzinfo is None:
        raise ValueError('published_at 必须带时区')
    return moment.astimezone(BEIJING).date().isoformat()


def empty_day_payload(date: str) -> dict:
    return {
        'schema': HISTORY_DAY_SCHEMA,
        'date': date,
        'timezone': TIMEZONE,
        'count': 0,
        'empty': True,
        'message': EMPTY_MESSAGE,
        'items': [],
    }


def _now_iso(generated_at=None) -> str:
    if generated_at is None:
        return datetime.now(BEIJING).isoformat(timespec='seconds')
    if isinstance(generated_at, datetime):
        moment = generated_at
        if moment.tzinfo is None:
            moment = moment.replace(tzinfo=BEIJING)
        return moment.astimezone(BEIJING).isoformat(timespec='seconds')
    return str(generated_at)


def _items_from(items) -> list:
    if items is None:
        return []
    if isinstance(items, dict):
        return list(items.get('items') or [])
    return list(items)


def _write_json(path: Path, payload) -> bool:
    """原子写入；内容相同则不改文件，返回是否写了新内容。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, ensure_ascii=False, indent=1) + '\n'
    if path.is_file() and path.read_text(encoding='utf-8') == text:
        return False
    tmp = path.with_name(path.name + '.tmp')
    tmp.write_text(text, encoding='utf-8')
    tmp.replace(path)
    return True


def _load_json(path: Path, default=None):
    if not path.is_file():
        return default
    return json.loads(path.read_text(encoding='utf-8'))


def _day_path(archive_dir: Path, date: str) -> Path:
    return archive_dir / f'{date}.json'


def _load_id_index(archive_dir: Path) -> dict:
    payload = _load_json(archive_dir / 'index.json') or {}
    ids = payload.get('ids') if isinstance(payload, dict) else None
    if isinstance(ids, dict):
        return dict(ids)
    # 旧文件或缺失时，从现有日文件重建，避免把已有历史丢掉。
    rebuilt = {}
    for path in _day_files(archive_dir):
        day = _load_json(path) or {}
        date = day.get('date') or path.stem
        for record in day.get('items') or []:
            ident = record.get('id')
            if ident:
                rebuilt[ident] = date
    return rebuilt


def _day_files(archive_dir: Path) -> list[Path]:
    if not archive_dir.is_dir():
        return []
    return sorted(path for path in archive_dir.iterdir() if path.is_file() and DAY_NAME.match(path.name))


def _load_day(archive_dir: Path, date: str, cache: dict) -> dict:
    if date not in cache:
        payload = _load_json(_day_path(archive_dir, date))
        if not payload:
            payload = {'schema': ARCHIVE_DAY_SCHEMA, 'date': date, 'timezone': TIMEZONE, 'items': []}
        records = {}
        for record in payload.get('items') or []:
            ident = record.get('id')
            if not ident:
                continue
            first = record.get('first') or record.get('latest') or record
            latest = record.get('latest') or first
            records[ident] = {'id': ident, 'first': first, 'latest': latest}
        cache[date] = records
    return cache[date]


def _search_entry(item: dict) -> dict:
    translation = item.get('translation') if item.get('translated') else None
    entry = {
        'id': item['id'],
        'kind': item.get('kind'),
        'channel': item.get('channel'),
        'source_id': item.get('source_id'),
        'source_name': item.get('source_name') or '',
        'title': item.get('title') or '',
        'summary': item.get('summary') or '',
        'published_at': item.get('published_at'),
        'lang': item.get('lang'),
        'translated': bool(item.get('translated')),
    }
    if item.get('image') and isinstance(item['image'], dict) and item['image'].get('url'):
        entry['image'] = {'url': item['image']['url']}
        if isinstance(item['image'].get('width'), int):
            entry['image']['width'] = item['image']['width']
        if isinstance(item['image'].get('height'), int):
            entry['image']['height'] = item['image']['height']
    else:
        entry['image'] = None
    if translation and isinstance(translation, dict):
        # 译文优先展示，原文单独保留供搜索命中；不写任何 AI 摘要字段。
        entry['display_title'] = translation.get('title') or entry['title'] or entry['summary']
        entry['display_summary'] = translation.get('summary') if translation.get('summary') is not None else entry['summary']
        entry['translation_title'] = translation.get('title') or ''
        entry['translation_summary'] = translation.get('summary') or ''
        entry['original_title'] = entry['title']
        entry['original_summary'] = entry['summary']
    else:
        entry['display_title'] = entry['title'] or entry['summary']
        entry['display_summary'] = entry['summary']
        entry['translation_title'] = ''
        entry['translation_summary'] = ''
        entry['original_title'] = ''
        entry['original_summary'] = ''
    return entry


def _history_item(record: dict) -> dict:
    item = dict(record['latest'])
    first = record.get('first') or item
    item['first_published_at'] = first.get('published_at')
    return item


def build(items, out_dir, archive_dir=None, generated_at=None):
    """把已上站条目按北京日期合并进归档，并写出 search-index（历史页已去掉，不写 data/history）。

    items: 条目列表，或 rebang.items/1 信封。
    out_dir: 站点根目录（写出 data/search-index.json）。
    archive_dir: 默认为仓库 var/rebang/archive/；测试请显式传入。
    只增量改动有新条目的日期文件，已有历史全部保留。
    同一 id 保留首次与最新版本。
    """
    archive_dir = Path(archive_dir) if archive_dir is not None else DEFAULT_ARCHIVE_DIR
    out_dir = Path(out_dir)
    incoming = _items_from(items)
    generated = _now_iso(generated_at)
    archive_dir.mkdir(parents=True, exist_ok=True)

    id_index = _load_id_index(archive_dir)
    cache = {}
    dirty = set()

    for item in incoming:
        if not isinstance(item, dict) or not item.get('id') or not item.get('published_at'):
            continue
        ident = item['id']
        try:
            date = beijing_date(item['published_at'])
        except (ValueError, TypeError):
            continue
        old_date = id_index.get(ident)
        if old_date and old_date != date:
            old_records = _load_day(archive_dir, old_date, cache)
            previous = old_records.pop(ident, None)
            dirty.add(old_date)
            first = previous['first'] if previous else item
            records = _load_day(archive_dir, date, cache)
            records[ident] = {'id': ident, 'first': first, 'latest': item}
        else:
            records = _load_day(archive_dir, date, cache)
            if ident in records:
                records[ident]['latest'] = item
            else:
                records[ident] = {'id': ident, 'first': item, 'latest': item}
        id_index[ident] = date
        dirty.add(date)

    written_archive = []
    for date in sorted(dirty):
        records = cache.get(date) or _load_day(archive_dir, date, cache)
        path = _day_path(archive_dir, date)
        if not records:
            if path.is_file():
                path.unlink()
                written_archive.append(date)
            for ident, mapped in list(id_index.items()):
                if mapped == date:
                    del id_index[ident]
            continue
        payload = {
            'schema': ARCHIVE_DAY_SCHEMA,
            'date': date,
            'timezone': TIMEZONE,
            'items': [records[ident] for ident in sorted(records)],
        }
        if _write_json(path, payload):
            written_archive.append(date)

    _write_json(archive_dir / 'index.json', {
        'schema': ARCHIVE_INDEX_SCHEMA,
        'timezone': TIMEZONE,
        'ids': {ident: id_index[ident] for ident in sorted(id_index)},
    })

    dates = []
    search_entries = []
    for path in _day_files(archive_dir):
        day = _load_json(path)
        if not day:
            continue
        date = day.get('date') or path.stem
        records = []
        for record in day.get('items') or []:
            ident = record.get('id')
            latest = record.get('latest') or record.get('first')
            if not ident or not latest:
                continue
            records.append({'id': ident, 'first': record.get('first') or latest, 'latest': latest})
        if not records:
            continue
        items_out = sorted((_history_item(r) for r in records),
                           key=lambda it: it.get('published_at') or '', reverse=True)
        dates.append({'date': date, 'count': len(items_out)})
        for item in items_out:
            search_entries.append(_search_entry(item))

    dates.sort(key=lambda row: row['date'], reverse=True)
    search_entries.sort(key=lambda row: row.get('published_at') or '', reverse=True)
    _write_json(out_dir / 'data' / 'search-index.json', {
        'schema': SEARCH_INDEX_SCHEMA,
        'timezone': TIMEZONE,
        'generated_at': generated,
        'entries': search_entries,
    })
    return {
        'archive_dir': str(archive_dir),
        'out_dir': str(out_dir),
        'dates': dates,
        'updated_dates': written_archive,
        'item_count': sum(row['count'] for row in dates),
        'search_entries': len(search_entries),
        'generated_at': generated,
    }
