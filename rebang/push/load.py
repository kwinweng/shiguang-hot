"""从已上站数据读取条目与博主平台状态。只认 site-v11/data 与归档，不读未上站产物。"""
import json
from datetime import timedelta
from pathlib import Path

from .timeutil import BEIJING, WINDOW, parse_now


def _read_json(path):
    try:
        return json.loads(Path(path).read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError):
        return None


def _extract_items(payload):
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if not isinstance(payload, dict):
        return []
    items = payload.get('items')
    if isinstance(items, list):
        return [item for item in items if isinstance(item, dict)]
    return []


def _iter_site_item_files(data_dir):
    channel_root = data_dir / 'channel'
    if channel_root.is_dir():
        for path in sorted(channel_root.glob('*/page-*.json')):
            yield path
    items_path = data_dir / 'items.json'
    if items_path.is_file():
        yield items_path


def _iter_archive_files(archive_dir, now, window=WINDOW):
    if archive_dir is None or not archive_dir.is_dir():
        return
    start = (now - window).astimezone(BEIJING).date()
    end = now.astimezone(BEIJING).date()
    day = start
    while day <= end:
        path = archive_dir / f'{day.isoformat()}.json'
        if path.is_file():
            yield path
        day += timedelta(days=1)


def _merge(items_by_id, paths):
    for path in paths:
        payload = _read_json(path)
        for item in _extract_items(payload):
            item_id = item.get('id')
            if item_id:
                items_by_id[item_id] = item


def default_archive_dir(site_dir):
    site = Path(site_dir)
    # --site 指向 site-v11 时，归档在仓库根 var/rebang/archive
    candidates = [
        site.parent / 'var/rebang/archive',
        site / 'archive',
    ]
    for path in candidates:
        if path.is_dir():
            return path
    return candidates[0]


def load_published_items(site_dir, now=None, archive_dir=None):
    """已上站条目：频道分页为主，窗口内归档补漏，同 id 以站点页为准。"""
    site = Path(site_dir)
    data_dir = site / 'data' if (site / 'data').is_dir() else site
    now = now or parse_now(None)
    archive = Path(archive_dir) if archive_dir is not None else default_archive_dir(site_dir)
    from_archive = {}
    _merge(from_archive, _iter_archive_files(archive, now))
    from_site = {}
    _merge(from_site, _iter_site_item_files(data_dir))
    merged = dict(from_archive)
    merged.update(from_site)
    return list(merged.values())


def load_meta(site_dir):
    site = Path(site_dir)
    for path in (site / 'data' / 'meta.json', site / 'meta.json'):
        payload = _read_json(path)
        if isinstance(payload, dict):
            return payload
    return {}


def load_blogger_platforms(site_dir):
    """读站点或生产者输出里的 platforms 状态；没有则空列表。"""
    site = Path(site_dir)
    candidates = [
        site / 'data' / 'bloggers.json',
        site / 'bloggers.json',
        site.parent / 'var/rebang/in/bloggers.json',
    ]
    for path in candidates:
        payload = _read_json(path)
        if not isinstance(payload, dict):
            continue
        platforms = payload.get('platforms')
        if isinstance(platforms, list):
            return [row for row in platforms if isinstance(row, dict)]
    return []
