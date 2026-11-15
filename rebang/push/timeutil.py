"""北京时间与带时区 ISO 解析。"""
from datetime import datetime, timedelta, timezone

BEIJING = timezone(timedelta(hours=8))
WINDOW = timedelta(hours=24)


def parse_iso(value):
    if not isinstance(value, str) or not value:
        return None
    try:
        moment = datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError:
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=BEIJING)
    return moment


def parse_now(value):
    """命令行 --now；缺省为当前北京时间。无时区时按北京时间。"""
    if value is None or value == '':
        return datetime.now(BEIJING)
    moment = parse_iso(value)
    if moment is None:
        raise ValueError(f'无法解析 --now: {value}')
    return moment.astimezone(BEIJING)


def in_window(published_at, now, window=WINDOW):
    start = now - window
    return start < published_at <= now
