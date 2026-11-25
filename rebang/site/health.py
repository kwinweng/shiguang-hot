"""Project collection snapshots into public, allowlisted diagnostics."""
from collections import Counter
from datetime import datetime, timedelta

from rebang.bloggers import X_STALE_HOURS
from rebang.contract import HEALTH_SCHEMA, load_bloggers, load_channels
from rebang.health_time import observation_time

STALE_HOURS = 48
SUCCESS = ('ok', 'empty', 'cached')
UNCONFIGURED = (None, 'not_configured', 'not_fetched')
PRIORITY = ('login_expired', 'failed', 'stale', 'not_configured', 'unknown', 'ok')
REASONS = {
    'blocked': '来源拒绝访问',
    'network': '网络连接失败',
    'OSError': '网络或本地缓存不可用',
    'http_5xx': '来源服务暂时不可用',
    'http_status': '来源返回异常状态',
    'invalid_content': '来源内容无法解析',
    'parse': '来源内容无法解析',
    'rate_limited': '来源限制了请求频率',
    'jike_rsshub_unset': '即刻订阅尚未配置',
    'jike_mirrors_down': '即刻订阅服务暂时不可用',
    'weibo_cookie_unset': '微博登录尚未配置',
    'weibo_cookie_expired': '微博需要重新登录',
    'weibo_fetch_failed': '微博本轮采集失败',
    'wechat_weread_qr': '微信读书尚未扫码登录',
    'wechat_weread_expired': '微信读书需要重新登录',
    'wechat_book_not_found': '微信读书未找到此公众号',
    'x_dump_missing': '未收到 X 导出数据',
    'x_dump_error': 'X 导出响应报告错误',
    'x_dump_time_invalid': 'X 导出时间无效或缺失',
    'youtube_unreachable': 'YouTube 订阅和频道页均不可用',
}


def _time(value, now):
    if not isinstance(value, str):
        return None
    try:
        moment = datetime.fromisoformat(value.replace('Z', '+00:00'))
        return observation_time(moment, now)
    except (ValueError, OverflowError):
        return None


def _iso(moment):
    return moment.isoformat(timespec='seconds') if moment else None


def _count(value, fallback=None):
    return value if type(value) is int and value >= 0 else fallback


def _sort(row):
    return (PRIORITY.index(row['status']), row['issue_since'] is None, row['issue_since'] or '')


def _row(source, observed, group, now, visible_count, *, kind):
    raw = observed.get('status')
    code = observed.get('error')
    reason = REASONS.get(code) if isinstance(code, str) else None
    is_tg = kind == 'telegram'
    is_news = kind != 'blogger' and kind != 'x'
    tg_failed = is_tg and (observed.get('collection_ok') is False or bool(code))
    last_value = observed.get('last_ok_at')
    last_ok = _time(last_value, now)
    fetched_value = observed.get('fetched_at') if is_news and not tg_failed else None
    fetched_at = _time(fetched_value, now)
    if last_value is None:
        # Ingest feeds use fetched_at for the cache timestamp even on network failure.
        last_ok = fetched_at
    dump_value = observed.get('dump_at') if kind == 'x' else None
    dump_at = _time(dump_value, now)
    invalid_time = ((last_value is not None and last_ok is None)
                    or (fetched_value is not None and fetched_at is None)
                    or (dump_value is not None and dump_at is None))
    freshness_at = dump_at if kind == 'x' else last_ok
    max_age = X_STALE_HOURS if kind == 'x' else STALE_HOURS
    count = _count(observed.get('count'), visible_count)
    run_count = None
    if not is_tg:
        inferred = _count(observed.get('new'), count) if raw in ('ok', 'empty') else None
        if raw in ('error', 'login_expired'):
            inferred = 0
        run_count = _count(observed.get('run_count', inferred))
    overdue = freshness_at is not None and now - freshness_at > timedelta(hours=max_age)
    if raw == 'login_expired':
        status, reason = 'login_expired', reason or '登录已失效，需要重新登录'
    elif kind == 'x' and code == 'x_dump_stale':
        status, reason = ('stale', 'X 导出数据超过 36 小时未更新') if overdue else ('failed', REASONS['x_dump_time_invalid'])
    elif tg_failed or raw == 'error' or (kind == 'x' and code == 'x_dump_missing' and last_ok):
        status, reason = 'failed', reason or ('Telegram 本轮采集失败' if is_tg else '本轮采集失败')
    elif raw in SUCCESS and invalid_time:
        status, reason = 'failed', '采集时间无效'
    elif raw in SUCCESS and overdue:
        status, reason = 'stale', f'超过 {max_age} 小时未更新采集数据'
    elif raw in SUCCESS and last_ok:
        status = 'ok'
        reason = '本轮数据已采集，缓存写入失败' if observed.get('cache_warning') == 'write_failed' else None
    elif raw in SUCCESS or raw in UNCONFIGURED:
        status, reason = 'not_configured', reason or '尚无采集记录'
    else:
        status, reason = 'unknown', '采集状态无法识别'
    issue_since = freshness_at if status == 'stale' else last_ok if status in ('failed', 'login_expired', 'unknown') else None
    return {'id': source['id'], 'name': source['name'], 'group': group, 'status': status,
            'last_ok_at': _iso(last_ok), 'count': count, 'run_count': run_count, 'reason': reason,
            'issue_since': _iso(issue_since)}


def _platform(config, observed, now, counts):
    platform_id = config['id']
    records = {a['handle']: a for a in observed.get('accounts') or [] if isinstance(a, dict) and isinstance(a.get('handle'), str)}
    accounts = []
    for account in config['accounts']:
        handle = account['handle']
        source = {'id': f'{platform_id}-{handle}', 'name': account['name']}
        accounts.append(_row(source, records.get(handle, {}), config['name'], now, counts[source['id']],
                             kind='x' if platform_id == 'x' else 'blogger'))
    accounts.sort(key=_sort)
    worst = accounts[0] if accounts else None
    affected = [a for a in accounts if a['status'] != 'ok']
    reasons = {a['reason'] for a in affected}
    reason = f'{len(affected)} 个账号待检查' if len(reasons) > 1 else next(iter(reasons), None)
    run_counts = [a['run_count'] for a in accounts if a['run_count'] is not None]
    return {'id': platform_id, 'name': config['name'], 'group': '博主', 'accounts': accounts,
            'status': worst['status'] if worst else 'not_configured',
            'last_ok_at': max((a['last_ok_at'] for a in accounts if a['last_ok_at']), default=None),
            'issue_since': min((a['issue_since'] for a in affected if a['issue_since']), default=None),
            'count': sum(a['count'] for a in accounts), 'run_count': sum(run_counts) if run_counts else None,
            'reason': reason if worst else '尚未配置账号'}


def build_health(envelopes, items, now):
    observations = {'sources': {}, 'platforms': {}}
    for _, envelope in envelopes:
        for key, rows in observations.items():
            for observed in envelope.get(key) or []:
                if isinstance(observed, dict) and isinstance(observed.get('id'), str):
                    rows[observed['id']] = observed
    counts = Counter(i['source_id'] for i in items)
    news = [_row(source, observations['sources'].get(source['id'], {}), channel['name'], now, counts[source['id']],
                 kind=source['type'])
            for channel in load_channels()['channels'] for source in channel['sources']]
    platforms = [_platform(platform, observations['platforms'].get(platform['id'], {}), now, counts)
                 for platform in load_bloggers()['platforms']]
    return {'schema': HEALTH_SCHEMA, 'generated_at': _iso(now), 'sources': sorted(news + platforms, key=_sort)}
