"""汇总各提供方为 rebang.hotsearch/1。一家失败只让那一家为空，不影响其他。"""
import importlib
from datetime import datetime
from zoneinfo import ZoneInfo

from rebang.contract import HOTSEARCH_SCHEMA, load_hotsearch

from .http import LiveHttp, ProviderError

BEIJING = ZoneInfo('Asia/Shanghai')


def iso(moment):
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=BEIJING)
    return moment.astimezone(BEIJING).isoformat(timespec='seconds')


def collect(now, http=None):
    """抓取已启用的提供方，返回热搜信封。http 缺省为真实请求。"""
    http = http or LiveHttp()
    config = load_hotsearch()
    cap = config['max_items_per_provider']
    generated_at = iso(now)
    providers = []
    for spec in sorted(config['providers'], key=lambda item: item['order']):
        if not spec.get('enabled', True):
            continue
        providers.append(_one(spec, http, now, cap))
    return {
        'schema': HOTSEARCH_SCHEMA,
        'generated_at': generated_at,
        'providers': providers,
    }


def _one(spec, http, now, cap):
    fetched_at = iso(now)
    base = {'id': spec['id'], 'name': spec['name'], 'fetched_at': fetched_at, 'items': []}
    try:
        module = importlib.import_module(f"rebang.hotsearch.providers.{spec['id']}")
        items = module.fetch(http, now)
    except ProviderError as exc:
        return {**base, 'status': 'error', 'error': exc.code, 'items': []}
    except Exception:
        return {**base, 'status': 'error', 'error': 'unexpected', 'items': []}
    if not isinstance(items, list):
        return {**base, 'status': 'error', 'error': 'bad_structure', 'items': []}
    cleaned = []
    for item in items[:cap]:
        if not isinstance(item, dict):
            continue
        cleaned.append(item)
    if not cleaned:
        return {**base, 'status': 'empty', 'items': []}
    return {**base, 'status': 'ok', 'items': cleaned}
