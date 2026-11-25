"""编排：按 bloggers.json 逐平台、逐账号抓取 → items 信封 + platforms 状态；失败账号沿用上次成功内容。"""
import json
import os
import sys
import time
from datetime import timedelta
from pathlib import Path

from rebang.contract.schema import ITEMS_SCHEMA, load_bloggers, validate_items_envelope
from rebang.health_time import observation_time

from . import X_STALE_HOURS
from . import jike as jike_mod
from . import weibo as weibo_mod
from . import youtube as yt_mod
from . import weread as weread_mod
from . import x as x_mod
from .common import apply_translation, iso, parse_time, translate_comments
from .feed import FeedError, feed_posts

PRODUCER = 'bloggers'
ALL_PLATFORMS = ('blog', 'x', 'jike', 'weibo', 'wechat', 'youtube', 'zhihu')
YOUTUBE_CACHE = Path(__file__).resolve().parents[2] / 'var' / 'rebang' / 'cache' / 'youtube-watch.json'

REASONS = {
    'jike_rsshub_unset': '即刻的公共 RSSHub 地址未配置',
    'jike_mirrors_down': '公共 RSSHub 实例这次都没取到即刻',
    'weibo_cookie_unset': '微博登录尚未配置',
    'weibo_cookie_expired': '微博 Cookie 已失效（接口不再返回 ok=1 或跳到登录页），站上保留上次内容；需重新登录副号换 Cookie',
    'weibo_fetch_failed': '微博接口这次没取到（网络或接口错误），站上保留上次内容',
    'wechat_weread_qr': '需要微信读书扫码登录，已准备好、等扫码',
    'wechat_weread_expired': '微信读书登录已失效，待重新扫码',
    'wechat_book_not_found': '微信读书里没搜到这个公众号',
    'x_dump_missing': '这次没有收到 X 博主的原始数据',
    'x_dump_stale': '公开 X 读取数据超过 36 小时未更新',
    'x_dump_error': 'X 导出响应报告错误',
    'x_dump_time_invalid': 'X 导出时间无效或缺失',
    'no_accounts': '本期名单为空',
    'youtube_pending_confirm': '频道名单待确认，确认前不抓',
    'youtube_unreachable': 'YouTube 订阅和频道页这次都没取到',
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
        if error in REASONS:
            row['reason'] = REASONS[error]
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
    session_path = getattr(opts, 'weread_session', None)
    session = None
    if session_path and weread_mod.session_exists(session_path):
        try:
            session = weread_mod.load_session(session_path)
        except (OSError, ValueError, weread_mod.WereadError):
            session = None
    books = weread_mod.load_books(getattr(opts, 'weread_books', None) or weread_mod.BOOKS_CACHE) if session else {}
    get = getattr(opts, 'weread_get', None) or weread_mod.http_json
    expired = False
    for account in platform['accounts']:
        if account in public:
            continue
        if session is None:
            rows.append(_account(platform, account, 'not_configured', error='wechat_weread_qr')[0])
            continue
        if expired:
            rows.append(_account(platform, account, 'login_expired', error='wechat_weread_expired')[0])
            continue
        sleep(max(opts.pause, 2.0))   # 微信读书有频率限制，号与号之间至少隔 2 秒
        try:
            posts, via = weread_mod.wechat_posts(account, platform, fetched_at, session, get=get,
                                            get_text=getattr(opts, 'weread_get_text', None), limit=opts.limit, cache=books)
        except weread_mod.WereadError as exc:
            if exc.code == 'login_expired':
                expired = True
                rows.append(_account(platform, account, 'login_expired', error='wechat_weread_expired')[0])
            elif exc.code == 'book_not_found':
                rows.append(_account(platform, account, 'error', error='wechat_book_not_found')[0])
            else:
                row = _account(platform, account, 'error', error='parse')[0]
                row['detail'] = exc.code
                rows.append(row)
            continue
        except Exception:
            rows.append(_account(platform, account, 'error', error='parse')[0])
            continue
        row, got = _account(platform, account, 'ok' if posts else 'empty', posts)
        row['via'] = via
        rows.append(row)
        items += got
    if session is not None:
        weread_mod.save_books(books, getattr(opts, 'weread_books', None) or weread_mod.BOOKS_CACHE)
    order = [a['handle'] for a in platform['accounts']]
    rows.sort(key=lambda r: order.index(r['handle']))
    return rows, items


def _platform_weibo(platform, http, fetched_at, opts, sleep):
    """weibo.com ajax + 副号 Cookie。Cookie 失效：本平台全部标 login_expired（后面的号不再请求），沿用上次内容。"""
    if not weibo_mod.cookie_configured(opts.weibo_cookie_file):
        return [_account(platform, a, 'not_configured', error='weibo_cookie_unset')[0] for a in platform['accounts']], []
    try:
        cookie = weibo_mod.read_cookie(opts.weibo_cookie_file)
    except weibo_mod.WeiboError:
        return [_account(platform, a, 'not_configured', error='weibo_cookie_unset')[0] for a in platform['accounts']], []
    get = getattr(opts, 'weibo_get', None) or weibo_mod.http_json
    out_dir = Path(opts.weibo_output) if opts.weibo_output else None
    cache_path = out_dir / weibo_mod.CACHE_NAME if out_dir else None
    cache = weibo_mod.load_cache(cache_path) if cache_path else {}
    pause = max(opts.pause, weibo_mod.PAUSE)
    rows, items, expired = [], [], False
    for index, account in enumerate(platform['accounts']):
        if expired:
            rows.append(_account(platform, account, 'login_expired', error='weibo_cookie_expired')[0])
            continue
        if index:
            sleep(pause)
        try:
            posts, cache = weibo_mod.fetch_account(account, cookie, get=get, sleep=sleep, cache=cache,
                                                   limit=opts.limit, raw_dir=out_dir, pause=pause)
            got = weibo_mod.map_posts(posts, platform, account, fetched_at, cache, opts.limit)
        except weibo_mod.WeiboError as exc:
            if exc.code == 'login_expired':
                expired = True
                print('weibo cookie expired: 微博 Cookie 已失效，本轮不更新微博，站上保留上次内容', file=sys.stderr)
                rows.append(_account(platform, account, 'login_expired', error='weibo_cookie_expired')[0])
            else:
                row = _account(platform, account, 'error', error='weibo_fetch_failed')[0]
                row['detail'] = exc.code
                rows.append(row)
            continue
        except Exception:  # 解析器意外：记为 error，不中断其它账号
            rows.append(_account(platform, account, 'error', error='parse')[0])
            continue
        row, got = _account(platform, account, 'ok' if got else 'empty', got)
        rows.append(row)
        items += got
    if cache_path:
        try:
            weibo_mod.save_cache(cache_path, cache)
        except OSError:
            pass
    return rows, items


def _platform_youtube(platform, http, fetched_at, opts, sleep):
    cache_path = getattr(opts, 'youtube_cache', None) or YOUTUBE_CACHE
    cache = yt_mod.load_cache(cache_path)
    rows, items = [], []
    for index, account in enumerate(platform['accounts']):
        if index:
            sleep(opts.pause)
        if not yt_mod.valid_channel_id(account.get('handle')):
            rows.append(_account(platform, account, 'error', error='parse')[0])
            continue
        try:
            posts, via = yt_mod.channel_posts(http, platform, account, fetched_at, opts.limit, cache=cache, sleep=sleep)
        except FeedError as exc:
            row, got = _account(platform, account, 'error', error='youtube_unreachable')
            row['detail'] = exc.code
        except Exception:
            row, got = _account(platform, account, 'error', error='parse')
        else:
            row, got = _account(platform, account, 'ok' if posts else 'empty', posts)
            row['via'] = via
        rows.append(row)
        items += got
    if platform['accounts']:
        yt_mod.save_cache(cache_path, cache)
    return rows, items


def _platform_x(platform, http, fetched_at, opts, sleep, now):
    dump = None
    if opts.x_dump:
        path = Path(opts.x_dump)
        dump = path if path.is_file() or (path.is_dir() and any(path.glob('*.json'))) else x_mod.latest_dump(path)
    if dump is None:
        return [_account(platform, a, 'not_configured', error='x_dump_missing')[0] for a in platform['accounts']], []
    made = observation_time(x_mod.dump_time(dump), now)
    accounts = platform['accounts']
    if made is None:
        return [_account(platform, a, 'error', error='x_dump_time_invalid')[0] for a in accounts], []
    if now - made > timedelta(hours=X_STALE_HOURS):
        rows = [_account(platform, a, 'error', error='x_dump_stale')[0] for a in accounts]
        for row in rows:
            row['dump_at'] = iso(made)
        return rows, []
    handles = [a['handle'] for a in accounts]
    try:
        data, failures = x_mod.read_export(dump, handles)
        by_handle = x_mod.x_posts(data, platform, fetched_at, opts.limit)
    except (ValueError, OSError, KeyError, TypeError, AttributeError, OverflowError):
        return [_account(platform, a, 'error', error='parse')[0] for a in accounts], []
    # 同目录下其它已写完、未过期的旧 dump 也读进来补：例程每 2 小时只搜最近 24 小时，旧 dump 里还有一天前的帖
    root = dump.parent if opts.x_dump and Path(opts.x_dump).is_dir() and dump != Path(opts.x_dump) else None
    for older in sorted(root.iterdir()) if root else []:
        if older == dump or not older.is_dir() or not (older / '_dump.json').exists():
            continue
        made_old = observation_time(x_mod.dump_time(older), now)
        if made_old is None or now - made_old > timedelta(hours=X_STALE_HOURS):
            continue
        try:
            data, old_failures = x_mod.read_export(older, handles)
            extra = x_mod.x_posts(data, platform, fetched_at, opts.limit)
        except (ValueError, OSError, KeyError, TypeError, AttributeError, OverflowError):
            continue
        for handle, posts in extra.items():
            if handle in old_failures:
                continue
            have = {i['id'] for i in by_handle.get(handle, [])}
            by_handle[handle] = by_handle.get(handle, []) + [i for i in posts if i['id'] not in have]
    for handle, posts in by_handle.items():
        by_handle[handle] = sorted(posts, key=lambda i: i.get('published_at') or '', reverse=True)[:opts.limit]
    rows, items = [], []
    for account in accounts:
        handle = account['handle']
        error = failures.get(handle)
        if error:
            row, got = _account(platform, account, 'error', error=error)
        else:
            got = by_handle.get(handle, [])
            row, got = _account(platform, account, 'ok' if got else 'empty', got)
        row['dump_at'] = iso(made)
        rows.append(row)
        items += got
    return rows, items


def _keep_recent(pid, rows, got, prev_items, limit):
    """X / YouTube：X 的 dump 只搜最近 24 小时：一天没发帖的博主会被刷成空、旧帖从站上消失。
    这里把上次的帖子并回来（同 id 用新抓的，按发布时间取最新 limit 条），有帖子就是 ok，`new` 记这次 dump 里的新帖数。只对 dump 正常读到的行做（status ok/empty）；stale/错误行由通用逻辑处理。"""
    fresh = {}
    for item in got:
        fresh.setdefault(item['source_id'], []).append(item)
    out = []
    for row in rows:
        sid = f'{pid}-{row["handle"]}'
        mine = fresh.get(sid, [])
        if row['status'] in ('ok', 'empty'):
            ids = {i['id'] for i in mine}
            old = [i for i in prev_items.get(sid, []) if i['id'] not in ids]
            merged = sorted(mine + old, key=lambda i: i.get('published_at') or '', reverse=True)[:limit]
            row['new'] = len(mine)
            row['count'] = len(merged)
            row['status'] = 'ok' if merged else 'empty'
            mine = merged
        out += mine
    return out


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
    weibo_attempted = False
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
                              'reason': REASONS.get(platform.get('empty_reason'), REASONS['no_accounts']), 'accounts': []})
            continue
        handler = {'blog': _platform_blog, 'jike': _platform_jike, 'wechat': _platform_wechat,
                   'weibo': _platform_weibo, 'youtube': _platform_youtube}.get(pid)
        if pid == 'x':
            rows, got = _platform_x(platform, http, fetched_at, opts, sleep, now)
            got = _keep_recent(pid, rows, got, prev_items, opts.limit)
        else:
            rows, got = handler(platform, http, fetched_at, opts, sleep)
            if pid == 'weibo':
                weibo_attempted = any(row['status'] != 'not_configured' for row in rows)
            if pid in ('youtube', 'wechat', 'weibo'):   # 微博只取第一页；YouTube 公开页一轮只补得出几条；公众号 cover 兜底每次只有最新一篇：上次的留着
                got = _keep_recent(pid, rows, got, prev_items, opts.limit)
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
                keep = row['status'] in ('error', 'login_expired') or row.get('error') in ('x_dump_missing', 'weibo_cookie_unset')
                kept = prev_items.get(sid, []) if keep else []
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
    if weibo_attempted and getattr(opts, 'localize_media', False):
        from . import media as media_mod
        weibo_items = [i for i in items if i['blogger']['platform'] == 'weibo']
        if weibo_items:   # 一条都没有（如 Cookie 没配）就不动已有文件
            mdir = getattr(opts, 'media_dir', None) or media_mod.MEDIA_DIR
            opts.weibo_media_stats = media_mod.localize_weibo(
                weibo_items, mdir, **({'get': opts.weibo_media_get} if getattr(opts, 'weibo_media_get', None) else {}))
            media_mod.prune(weibo_items, mdir, platform='weibo')
    translator = opts.translator
    for item in items:
        if item.get('fetched_at') == fetched_at:  # 只翻本次新抓的；沿用的旧条目保持原样
            apply_translation(item, translator, ('title', 'summary') if item['blogger']['platform'] in ('blog', 'youtube') else ('title', 'summary', 'body'))
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
