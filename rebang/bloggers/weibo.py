"""微博：用副号 Cookie 直接读 weibo.com 桌面版 ajax 接口（不走 m.weibo.cn，不装 weibo-crawler）。

- Cookie：``~/.config/rebang/weibo-cookie.txt``（``REBANG_WEIBO_COOKIE`` / ``--weibo-cookie-file`` 可改），仓库外、0600，
  一行浏览器 Cookie 值（从 weibo.com 请求头复制，不带 ``Cookie:`` 前缀）。代码只在发请求时读进内存，
  不打印、不写日志、不放进异常信息或输出文件。
- 接口：``/ajax/statuses/mymblog?uid=…&page=1`` 取主页第一页；``isLongText`` 的帖再调 ``/ajax/statuses/longtext?id=<mblogid>``
  补全文（按 mblogid 缓存，同一条只取一次）。请求之间至少隔 ``PAUSE`` 秒，只抓 bloggers.json 里的账号。
- Cookie 失效：``ok`` 不是 1、跳到登录页或回的不是 JSON → ``WeiboError('login_expired')``；编排层把整平台标 login_expired，
  后面的账号不再请求，站上沿用上次成功的内容（run.py 通用逻辑）。
- 输出目录（默认 ``var/rebang/weibo-crawler/``，``--weibo-output`` 可改）：放 longtext 缓存和每个账号最近一次原始回包（不含 Cookie）。
"""
import json
import os
import re
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

from .common import BODY_CHARS, clip, detect_lang, iso, normalize_text, source_id, summary_of

DEFAULT_COOKIE = Path(os.environ.get("REBANG_WEIBO_COOKIE") or Path.home() / ".config" / "rebang" / "weibo-cookie.txt")
DEFAULT_OUTPUT = Path(__file__).resolve().parents[2] / "var" / "rebang" / "weibo-crawler"
BASE = 'https://weibo.com'
UA = ('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) '
      'Chrome/130.0.0.0 Safari/537.36')
PAUSE = 3.0
CACHE_NAME = 'longtext-cache.json'
CACHE_KEEP = 400
_ZW = re.compile(r'[\u200b\u200c\u200d\ufeff]')
_VIDEO_KEYS = ('mp4_720p_mp4', 'mp4_hd_url', 'stream_url_hd', 'mp4_sd_url', 'stream_url')


class WeiboError(Exception):
    def __init__(self, code):
        super().__init__(code)
        self.code = code


def cookie_configured(cookie_file):
    """只看路径是否指向一个存在的普通文件；不读内容。"""
    return bool(cookie_file) and os.path.isfile(cookie_file)


def read_cookie(cookie_file):
    """读进内存给请求用；空文件当未配置。出错只报代码，不带内容。"""
    try:
        value = Path(cookie_file).read_text(encoding='utf-8').strip()
    except (OSError, UnicodeDecodeError):
        raise WeiboError('cookie_unreadable') from None
    for prefix in ('Cookie:', 'cookie:'):
        if value.startswith(prefix):
            value = value[len(prefix):].strip()
    if not value or '\n' in value:
        raise WeiboError('cookie_unreadable')
    return value


def http_json(url, cookie, timeout=25):
    """GET weibo.com ajax → dict；登录失效抛 login_expired，其它网络问题抛 network/http_xxx。异常里不带 Cookie。"""
    req = urllib.request.Request(url, headers={
        'Cookie': cookie, 'User-Agent': UA, 'Referer': BASE + '/', 'Accept': 'application/json, text/plain, */*',
        'X-Requested-With': 'XMLHttpRequest'})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            final, body = resp.geturl(), resp.read()
    except urllib.error.HTTPError as exc:
        raise WeiboError('login_expired' if exc.code in (401, 403) else f'http_{exc.code}') from None
    except (urllib.error.URLError, OSError, ValueError):
        raise WeiboError('network') from None
    if 'passport.weibo' in final or '/login' in final or 'login.sina' in final:
        raise WeiboError('login_expired')
    try:
        data = json.loads(body)
    except ValueError:
        raise WeiboError('login_expired') from None   # 失效时回的是登录/访客页 HTML
    check(data)
    return data


def check(data):
    if not isinstance(data, dict) or data.get('ok') != 1:
        raise WeiboError('login_expired')
    return data


def parse_time(value):
    try:
        return datetime.strptime(str(value).strip(), '%a %b %d %H:%M:%S %z %Y')
    except (TypeError, ValueError):
        return None


def _https(url):
    if not isinstance(url, str) or not url.startswith(('http://', 'https://')):
        return None
    return 'https://' + url.split('://', 1)[1]


def _avatar(user):
    """头像地址带 ~2 小时过期的签名（Expires/ssig）；sinaimg 去掉查询串照样能取，存不过期的那份。"""
    url = _https((user or {}).get('avatar_hd') or (user or {}).get('profile_image_url'))
    if url and '.sinaimg.cn/' in url:
        url = url.split('?', 1)[0]
    return url


def _clean(text):
    return normalize_text(_ZW.sub('', text or ''))


def _int(value):
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None


def _pic(info):
    """图：取原图（largest → mw2000 → original → large）；gif/实况带视频地址的按 gif。"""
    if not isinstance(info, dict):
        return None
    best = next((info[k] for k in ('largest', 'mw2000', 'original', 'large') if isinstance(info.get(k), dict) and _https(info[k].get('url'))), None)
    if not best:
        return None
    entry = {'type': 'image', 'url': _https(best['url'])}
    for dim in ('width', 'height'):
        v = best.get(dim)
        if isinstance(v, str) and v.isdigit():
            v = int(v)
        if isinstance(v, int) and v > 0:
            entry[dim] = v
    if info.get('type') == 'gif' and _https(info.get('video')):
        entry = {'type': 'gif', 'url': _https(info['video']), 'preview_url': entry['url']}
    return entry


def _video(page_info):
    if not isinstance(page_info, dict) or page_info.get('object_type') != 'video':
        return None
    mi = page_info.get('media_info') or {}
    url = next((_https(mi.get(k)) for k in _VIDEO_KEYS if _https(mi.get(k))), None)
    if not url:
        return None
    entry = {'type': 'video', 'url': url}
    cover = page_info.get('page_pic')
    cover = cover.get('url') if isinstance(cover, dict) else cover
    if _https(cover):
        entry['preview_url'] = _https(cover)
    if isinstance(mi.get('duration'), (int, float)) and mi['duration'] > 0:
        entry['duration_ms'] = int(mi['duration'] * 1000)
    return entry


def media_of(w):
    out = []
    infos = w.get('pic_infos') or {}
    for pid in w.get('pic_ids') or list(infos):
        m = _pic(infos.get(pid))
        if m:
            out.append(m)
    for it in (w.get('mix_media_info') or {}).get('items') or []:
        m = _pic(it.get('data')) if it.get('type') == 'pic' else _video(it.get('data')) if it.get('type') == 'video' else None
        if m:
            out.append(m)
    v = _video(w.get('page_info'))
    if v:
        out.append(v)
    seen, unique = set(), []
    for m in out:
        if m['url'] not in seen:
            seen.add(m['url'])
            unique.append(m)
    return unique


def _quote(rt):
    user = (rt or {}).get('user') or {}
    text = _clean(rt.get('text_raw') if rt else '')
    if not (rt and user.get('screen_name') and user.get('idstr') and text and rt.get('mblogid')):
        return None   # 原帖被删 / 拿不全：不画引用框
    moment = parse_time(rt.get('created_at'))
    q = {'handle': user['idstr'], 'display_name': user['screen_name'], 'text': text,
         'url': f'{BASE}/{user["idstr"]}/{rt["mblogid"]}', 'published_at': iso(moment) if moment else None}
    return q   # 不带原帖作者头像：sinaimg 拒绝外站引用，只给博主本人头像存本地副本


def map_posts(posts, platform, account, fetched_at, longtext=None, limit=10):
    """mymblog 的 data.list → 博主条目（按发布时间倒序取 limit 条）。longtext: {mblogid: 全文}。"""
    longtext = longtext or {}
    sid = source_id(platform['id'], account['handle'])
    items = []
    for w in posts or []:
        moment = parse_time(w.get('created_at'))
        mblogid = w.get('mblogid')
        user = w.get('user') or {}
        uid = str(user.get('idstr') or user.get('id') or account.get('uid') or account['handle'])
        if not moment or not mblogid:   # isAd 在自己主页上多是作者推广自己的文章，不是第三方广告，不过滤
            continue
        text = _clean(longtext.get(mblogid) or w.get('text_raw') or '')
        rt = w.get('retweeted_status')
        quote = _quote(rt) if rt else None
        media = media_of(w)
        if not media and rt:
            media = media_of(rt)   # 纯转发图片帖：图挂在原帖上，跟微博里一样展示出来
        if not (text or media or quote):
            continue
        name = user.get('screen_name') or account['name']
        # handle 必须是名单里的 handle（建站按它把帖子归到人）；数字 uid 前端不显示「@」
        blogger = {'platform': platform['id'], 'handle': account['handle'], 'display_name': name, 'media': media, 'quote': quote}
        avatar = _avatar(user)
        if avatar:
            blogger['avatar'] = avatar
        if isinstance(user.get('verified'), bool):
            blogger['verified'] = user['verified']
        metrics = {k: v for k, v in (('like', _int(w.get('attitudes_count'))), ('reply', _int(w.get('comments_count'))),
                                     ('repost', _int(w.get('reposts_count')))) if v is not None}
        if metrics:
            blogger['metrics'] = metrics
        first = next((m for m in media if m['type'] == 'image'), None) or next((m for m in media if m.get('preview_url')), None)
        image = None
        if first:
            image = {'url': first.get('preview_url') or first['url']}
            for dim in ('width', 'height'):
                if first.get(dim):
                    image[dim] = first[dim]
        items.append((moment, {
            'id': f'{sid}:{w.get("idstr") or w.get("id") or mblogid}', 'kind': 'post', 'channel': None,
            'source_id': sid, 'source_name': account['name'], 'title': '',
            'summary': summary_of(text), 'body': clip(text, BODY_CHARS),
            'url': f'{BASE}/{uid}/{mblogid}', 'image': image,
            'published_at': iso(moment), 'fetched_at': fetched_at,
            'lang': detect_lang(text) if text else 'zh', 'blogger': blogger,
        }))
    items.sort(key=lambda pair: pair[0], reverse=True)
    return [it for _, it in items[:limit]]


def account_uid(account):
    uid = str(account.get('uid') or account['handle'])
    if not uid.isdigit():
        raise WeiboError('uid_missing')
    return uid


def fetch_account(account, cookie, get=http_json, sleep=None, cache=None, limit=10, raw_dir=None, pause=PAUSE):
    """取一个账号的第一页 + 需要的长文。返回 (posts, longtext 映射)。登录失效直接往上抛。"""
    uid = account_uid(account)
    data = check(get(f'{BASE}/ajax/statuses/mymblog?uid={uid}&page=1&feature=0', cookie))
    posts = (data.get('data') or {}).get('list') or []
    if raw_dir:
        save_json(Path(raw_dir) / f'raw-{uid}.json', data)
    cache = cache if cache is not None else {}
    recent = sorted((w for w in posts if parse_time(w.get('created_at'))), key=lambda w: parse_time(w['created_at']), reverse=True)[:limit]
    for w in recent:
        mid = w.get('mblogid')
        if not (w.get('isLongText') and mid) or mid in cache:
            continue
        if sleep:
            sleep(pause)
        try:
            lt = check(get(f'{BASE}/ajax/statuses/longtext?id={mid}', cookie))
        except WeiboError as exc:
            if exc.code == 'login_expired':
                raise
            continue   # 长文取不到就用列表里的截断正文，下轮再试
        # 空串也记下：接口说没有长文就不再每轮重问，正文用列表里的 text_raw
        cache[mid] = ((lt.get('data') or {}).get('longTextContent') or '').strip()
    return posts, cache


def load_cache(path):
    try:
        data = json.loads(Path(path).read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {}
    return {k: v for k, v in data.items() if isinstance(k, str) and isinstance(v, str)} if isinstance(data, dict) else {}


def save_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + '.tmp')
    tmp.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
    os.replace(tmp, path)


def save_cache(path, cache):
    keep = dict(list(cache.items())[-CACHE_KEEP:])
    save_json(path, keep)
