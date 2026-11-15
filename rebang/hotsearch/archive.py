"""热搜按北京日期归档：每天只留当天最后一次成功抓取（至少一家 ok）。只用标准库。

底栏「热搜」页默认显示当前热搜，切日期看 data/hotsearch/<YYYY-MM-DD>.json（站点构建时从这里写出）。
失败/全空的一次抓取不入档，不拿旧榜冒充当天，也不覆盖当天已有的成功快照。
"""
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

from rebang.contract import schema

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DIR = ROOT / 'var' / 'rebang' / 'hotsearch-archive'
BEIJING = timezone(timedelta(hours=8))
DAY_FILE = re.compile(r'^(\d{4}-\d{2}-\d{2})\.json$')
KEEP_DAYS = 60


def _time(value):
    try:
        moment = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    except ValueError:
        return None
    return moment if moment.tzinfo else None


def snapshot_date(payload):
    moment = _time((payload or {}).get('generated_at'))
    return moment.astimezone(BEIJING).date().isoformat() if moment else None


def usable(payload):
    return not schema.validate_hotsearch(payload) and any(
        p.get('status') == 'ok' and p.get('items') for p in payload.get('providers') or [])


def save_snapshot(payload, archive_dir=DEFAULT_DIR):
    """合格快照写进 <北京日期>.json；当天已有更新的快照就不动。返回写入的日期或 None。"""
    if not usable(payload):
        return None
    day = snapshot_date(payload)
    archive_dir = Path(archive_dir)
    path = archive_dir / f'{day}.json'
    if path.is_file():
        try:
            old = json.loads(path.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            old = None
        if old and _time(old.get('generated_at')) and _time(old['generated_at']) >= _time(payload['generated_at']):
            return None
    archive_dir.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + '.tmp')
    tmp.write_text(json.dumps(payload, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
    tmp.replace(path)
    return day


def load_days(archive_dir=DEFAULT_DIR, keep_days=KEEP_DAYS, today=None):
    """[(date, payload)]，新→旧，只取最近 keep_days 天、能通过校验的快照。"""
    archive_dir = Path(archive_dir)
    if not archive_dir.is_dir():
        return []
    out = []
    for path in sorted(archive_dir.iterdir(), reverse=True):
        match = DAY_FILE.match(path.name)
        if not match:
            continue
        if today and match.group(1) > today:
            continue
        try:
            payload = json.loads(path.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            continue
        if usable(payload) and snapshot_date(payload) == match.group(1):
            out.append((match.group(1), payload))
        if len(out) >= keep_days:
            break
    return out
