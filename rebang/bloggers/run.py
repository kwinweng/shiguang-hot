"""编排：按 bloggers.json 逐平台、逐账号抓取 → items 信封 + platforms 状态；失败账号沿用上次成功内容。"""
import json
import os
import time
from datetime import timedelta
from pathlib import Path

from rebang.contract.schema import ITEMS_SCHEMA, load_bloggers, validate_items_envelope

from . import jike as jike_mod
from . import weibo as weibo_mod
from . import x as x_mod
from .common import apply_translation, iso, parse_time, translate_comments
from .feed import FeedError, feed_posts

PRODUCER = 'bloggers'
ALL_PLATFORMS = ('blog', 'x', 'jike', 'weibo', 'wechat', 'zhihu')
X_STALE_HOURS = 36

REASONS = {
    'jike_rsshub_unset': '即刻的公共 RSSHub 地址未配置',
    'jike_mirrors_down': '公共 RSSHub 实例这次都没取到即刻',
    'weibo_cookie_unset': '微博的公开方式（公共 RSSHub、免登录接口）都要登录或游客验证，取不到；要接需副号 Cookie 文件（待阿欢定）',
    'weibo_crawler_output_missing': '已有 Cookie 文件路径，但还没有 weibo-crawler 输出（安装/运行另批）',
    'wechat_weread_qr': '需要微信读书副号扫码登录（第一期不做）',
    'x_dump_missing': '还没有公开 X 读取工具写入的原始数据',
    'x_dump_stale': '公开 X 读取数据超过 36 小时未更新',
    'no_accounts': '本期名单为空',
}


def default_http():
    from shiguang.ingest.http import FetchFailure, check, request
    from datetime import datetime, timezone

    def fetch(url):
        try:
            response = request(url, {'Accept': 'application/rss+xml, application/atom+xml, application/xml;q=0.9, */*;q=0.5'})
            check(response, datetime.now(timezone.utc))
        except FetchFailure as exc:
            raise FeedError(exc.code) from None
        return response.body
    return fetch


class Options:
    def __init__(self, x_dump=None, jike_rsshub=None, weibo_cookie_file=None, weibo_output=None,
                 limit=10, pause=1.0, translator=None):
        self.x_dump = x_dump
        self.jike_rsshub = (jike_rsshub or '').rstrip('/') or None
        self.weibo_cookie_file = weibo_cookie_file
        self.weibo_output = weibo_output
        self.limit = limit
        self.pause = pause
        self.translator = translator


def _account(platform, account, status, items=(), error=None):
    row = {'handle': account['handle'], 'name': account['name'], 'status': status, 'count': len(items)}
    if error:
        row['error'] = error
    return row, list(items)


def _fetch_feeds(platform, accounts, http, fetched_at, opts, url_of, sleep):
    rows, items = [], []
    for index, account in enumerate(accounts):
        url = url_of(account)
        if index:
            sleep(opts.pause)
        try:
            posts = feed_posts(http(url), platform, account, fetched_at, opts.limit)
        except FeedError as exc:
            row, got = _account(platform, account, 'login_expired' if exc.code == 'blocked' and platform.get('login') else 'error',
                                error=exc.code)
        except Exception:  # 解析器意外：记为 error，不中断其它账号
            row, got = _account(platform, account, 'error', error='parse')
        else:
            row, got = _account(platform, account, 'ok' if posts else 'empty', posts)
        rows.append(row)
        items += got
    return rows, items


def _platform_blog(platform, http, fetched_at, opts, sleep):
    return _fetch_feeds(platform, platform['accounts'], http, fetched_at, opts, lambda a: a['feed'], sleep)


def _platform_jike(platform, http, fetched_at, opts, sleep):
    roots = jike_mod.roots_of(opts.jike_rsshub, platform)
    if not roots:
        return [_account(platform, a, 'not_configured', error='jike_rsshub_unset')[0] for a in platform['accounts']], []
    rows, items = [], []
    for index, account in enumerate(platform['accounts']):
        if index:
            sleep(opts.pause)
        try:
            body, root = jike_mod.fetch_account(http, roots, account, start=index)   # 账号错开起点，分摊到各实例
            posts = jike_mod.jike_posts(body, platform, account, fetched_at, opts.limit)
        except FeedError as exc:
            row, got = _account(platform, account, 'error', error='jike_mirrors_down')
            row['detail'] = exc.code
        except Exception:  # 解析器意外：记为 error，不中断其它账号
            row, got = _account(platform, account, 'error', error='parse')
        else:
            row, got = _account(platform, account, 'ok' if posts else 'empty', posts)
            row['via'] = root.split('://', 1)[-1]
        rows.append(row)
        items += got
    return rows, items


def _platform_wechat(platform, http, fetched_at, opts, sleep):
    public = [a for a in platform['accounts'] if a.get('feed') and a.get('login') is False]
    rows, items = _fetch_feeds(platform, public, http, fetched_at, opts, lambda a: a['feed'], sleep)
    for account in platform['accounts']:
        if account not in public:
            rows.append(_account(platform, account, 'not_configured', error='wechat_weread_qr')[0])
    order = [a['handle'] for a in platform['accounts']]
    rows.sort(key=lambda r: order.index(r['handle']))
    return rows, items


def _platform_weibo(platform, http, fetched_at, opts, sleep):
    if not weibo_mod.cookie_configured(opts.weibo_cookie_file):
        return [_account(platform, a, 'not_configured', error='weibo_cookie_unset')[0] for a in platform['accounts']], []
    rows, items = [], []
    for account in platform['accounts']:
        path = weibo_mod.find_output(opts.weibo_output, account)
        if path is None:
            rows.append(_account(platform, account, 'not_configured', error='weibo_crawler_output_missing')[0])
            continue
        try:
            posts = weibo_mod.map_crawler_json(weibo_mod.load_output(path), platform, account, fetched_at, opts.limit)
        except (ValueError, OSError, KeyError, TypeError):
            rows.append(_account(platform, account, 'error', error='parse')[0])
            continue
        row, got = _account(platform, account, 'ok' if posts else 'empty', posts)
        rows.append(row)
        items += got
    return rows, items


def _platform_x(platform, http, fetched_at, opts, sleep, now):
    dump = None
    if opts.x_dump:
        path = Path(opts.x_dump)
        dump = path if path.is_file() or (path.is_dir() and any(path.glob('*.json'))) else x_mod.latest_dump(path)
    if dump is None:
        return [_account(platform, a, 'not_configured', error='x_dump_missing')[0] for a in platform['accounts']], []
    made = x_mod.dump_time(dump)
    if made is None or now - made > timedelta(hours=X_STALE_HOURS):
        return [_account(platform, a, 'error', error='x_dump_stale')[0] for a in platform['accounts']], []
    try:
        by_handle = x_mod.x_posts(x_mod.load_dump(dump), platform, fetched_at, opts.limit)
    except (ValueError, OSError, KeyError, TypeError):
        return [_account(platform, a, 'error', error='parse')[0] for a in platform['accounts']], []
    rows, items = [], []
    for account in platform['accounts']:
        got = by_handle.get(account['handle'], [])
        row, got = _account(platform, account, 'ok' if got else 'empty', got)
        rows.append(row)
        items += got
    return rows, items


def _aggregate(rows):
    statuses = {r['status'] for r in rows}
    if not rows:
        return 'empty'
    if 'ok' in statuses:
        return 'ok'
    if statuses == {'not_configured'}:
        return 'not_configured'
    if 'login_expired' in statuses:
        return 'login_expired'
    if 'error' in statuses:
        return 'error'
    if statuses <= {'empty', 'not_configured'}:
        return 'empty'
    return 'error'


def run(platform_ids=ALL_PLATFORMS, http=None, now=None, previous=None, opts=None, sleep=time.sleep):
    from .common import now_bjt
    now = now or now_bjt()
    opts = opts or Options()
    http = http or default_http()
    fetched_at = iso(now)
    config = load_bloggers()
    prev_items = {}
    prev_accounts = {}
    for item in (previous or {}).get('items') or []:
        prev_items.setdefault(item['source_id'], []).append(item)
    for p in (previous or {}).get('platforms') or []:
        for a in p.get('accounts') or []:
            prev_accounts[(p['id'], a['handle'])] = a
    platforms, items = [], []
    for platform in config['platforms']:
        pid = platform['id']
        if pid not in platform_ids:
            # 未选的平台：原样沿用上次结果（若有），保证 --platform 局部刷新不清空其它平台
            for prev in (previous or {}).get('platforms') or []:
                if prev['id'] == pid:
                    platforms.append(prev)
                    for a in prev.get('accounts') or []:
                        items += prev_items.get(f'{pid}-{a["handle"]}', [])
            continue
        if not platform['accounts']:
            platforms.append({'id': pid, 'name': platform['name'], 'status': 'empty', 'last_ok_at': None,
                              'reason': REASONS['no_accounts'], 'accounts': []})
            continue
        handler = {'blog': _platform_blog, 'jike': _platform_jike, 'wechat': _platform_wechat,
                   'weibo': _platform_weibo}.get(pid)
        if pid == 'x':
            rows, got = _platform_x(platform, http, fetched_at, opts, sleep, now)
        else:
            rows, got = handler(platform, http, fetched_at, opts, sleep)
        got_by_source = {}
        for item in got:
            got_by_source.setdefault(item['source_id'], []).append(item)
        for row in rows:
            sid = f'{pid}-{row["handle"]}'
            prev = prev_accounts.get((pid, row['handle'])) or {}
            if row['status'] in ('ok', 'empty'):
                row['last_ok_at'] = fetched_at
            else:
                row['last_ok_at'] = prev.get('last_ok_at')
                kept = prev_items.get(sid, []) if row['status'] in ('error', 'login_expired') else []
                if kept:
                    row['stale'] = True  # 站上保留上次成功内容，并按 last_ok_at 标日期
                    row['count'] = len(kept)
                    got_by_source[sid] = kept
        for row in rows:
            items += got_by_source.get(f'{pid}-{row["handle"]}', [])
        status = _aggregate(rows)
        oks = [r['last_ok_at'] for r in rows if r.get('last_ok_at')]
        entry = {'id': pid, 'name': platform['name'], 'status': status,
                 'last_ok_at': max(oks) if oks else None, 'accounts': rows}
        reasons = sorted({r['error'] for r in rows if r.get('error') in REASONS})
        if reasons and status != 'ok':
            entry['reason'] = '；'.join(REASONS[r] for r in reasons)
        platforms.append(entry)
    if 'wechat' in platform_ids and getattr(opts, 'localize_media', False):
        from . import media as media_mod
        fresh = [i for i in items if i.get('fetched_at') == fetched_at]
        opts.media_stats = media_mod.localize(fresh, getattr(opts, 'media_dir', None) or media_mod.MEDIA_DIR,
                                              **({'get': opts.media_get} if getattr(opts, 'media_get', None) else {}))
        media_mod.prune(items, getattr(opts, 'media_dir', None) or media_mod.MEDIA_DIR)
    translator = opts.translator
    for item in items:
        if item.get('fetched_at') == fetched_at:  # 只翻本次新抓的；沿用的旧条目保持原样
            apply_translation(item, translator, ('title', 'summary') if item['blogger']['platform'] == 'blog' else ('title', 'summary', 'body'))
            translate_comments(item, translator)
    if translator is not None:
        translator.save()
    seen, unique = set(), []
    for item in items:
        if item['id'] not in seen:
            seen.add(item['id'])
            unique.append(item)
    envelope = {'schema': ITEMS_SCHEMA, 'producer': PRODUCER, 'generated_at': fetched_at,
                'platforms': platforms, 'items': unique}
    return envelope


def write_atomic(path, envelope):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + '.tmp')
    tmp.write_text(json.dumps(envelope, ensure_ascii=False, indent=1), encoding='utf-8')
    os.replace(tmp, path)


def load_previous(path):
    try:
        data = json.loads(Path(path).read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return None
    return data if not validate_items_envelope(data) else None
