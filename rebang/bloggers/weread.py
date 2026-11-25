"""微信读书（weread.qq.com 网页版）读公众号文章列表：5 个没有公开订阅的公众号走这里。

登录：微信读书网页版自己的扫码登录（不经第三方中转）。
  python3 -m rebang.bloggers.weread login --session <会话路径> [--qr-png <私有目录里的 png>] [--wait 600]
    1. GET  /api/auth/getLoginUid            → uid
    2. 二维码内容 = https://weread.qq.com/web/confirm?uid=<uid>（用微信扫，或在微信里打开这个链接）
    3. GET  /api/auth/getLoginInfo?uid=…    长轮询，扫码确认后返回 webLoginVid + accessToken
    4. 存成会话文件（默认 ~/.config/rebang/weread-session.json，权限 0600，仓库外），只写 vid/skey 和时间。
  需要验证码（NEED_OTP）时命令会提示，用 `login --uid <同一个 uid> --otp <手机上显示的码>` 接着等。

读取：优先 GET /web/mp/articles?bookId=MP_WXS_…&offset=0（列表）。2026-11-16 实测新鲜会话上这个接口仍回 -2041（不是登录失效，/api/userInfo 与 /api/mp/cover 都正常），所以失败时改走 /api/mp/cover（最新一篇：标题、封面、reviewId）再读 /web/mp/content 补发布时间和原文链接。
bookId 优先用 bloggers.json 的 `book_id`（由公众号公开 __biz Base64 解码得到 MP_WXS_<数字>，并用 cover 返回的名字核对过）。没写才登录后用站内搜索；网页搜索经常搜不到公众号本身。
Cookie 只通过 curl 的标准输入配置传给 curl（不进命令行参数、不进日志），任何输出都不打印会话内容。
curl 不跟任何跳转：任何 3xx 都当这次请求失败（跳去登录页记 login_expired，其它记 redirect_blocked）。
写进 curl 配置的 URL 只能是 https://weread.qq.com/ 下由代码拼出的地址（只含安全字符，否则 bad_url，不发请求），并加 globoff。
任何非 2xx（含 401/403）都当失败，401/403 记 login_expired；回包里非 0 的 errCode 也当失败。
会话文件用 rebang/private_file.py 安全打开和原子写入（不跟软链接、只本人可用、无 ACL、单一硬链接）。
错误码：-2010 没登录 / -2012 登录超时 → login_expired，站上保留旧内容。-2041 在列表接口上当「这次列表不可用」处理，改走 cover，不把整次登录判死。
"""
import argparse
import json
import re
import os
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote, urlencode

from .. import private_file
from .common import detect_lang, iso, normalize_text, source_id, summary_of

BASE = 'https://weread.qq.com'
UA = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0 Safari/537.36'
DEFAULT_SESSION = Path(os.environ.get('REBANG_WEREAD_SESSION')
                       or Path(private_file.default_home()) / '.config' / 'rebang' / 'weread-session.json')
BOOKS_CACHE = Path(__file__).resolve().parents[2] / 'var' / 'rebang' / 'cache' / 'weread-books.json'
LOGIN_ERRORS = {-2010, -2012}  # -2041 在列表接口上常见，不一定是登录失效
# vid/skey 会写进 curl 配置的引号里：只收不会改变配置语义的字符。
_TOKEN = re.compile(r'[A-Za-z0-9_.+/=:-]{1,512}')
# 能写进 curl 配置的 URL：固定站点 + 路径/查询里只有 urlencode/quote 会产出的字符（没有引号、空白、反斜杠、@、#）。
_SAFE_URL = re.compile(r'https://weread\.qq\.com/[A-Za-z0-9/_.~%?=&+-]*')
AUTH_FAILED = ('401', '403')


class WereadError(Exception):
    def __init__(self, code):
        super().__init__(code)
        self.code = code


# ---------- 会话 ----------

def load_session(path=DEFAULT_SESSION):
    """安全打开（见 rebang/private_file.py）并校验：必须是 JSON 对象，vid/skey 是非空的安全字符串。
    任何不合格（权限、软链接、`[]`、`null`、缺字段……）都只抛 WereadError，编排层当作未配置。"""
    try:
        data = json.loads(private_file.read_private(path))
    except private_file.PrivateFileError:
        raise WereadError('session_unsafe') from None
    except (OSError, ValueError, TypeError, RecursionError):
        raise WereadError('session_invalid') from None
    if not isinstance(data, dict) or not all(isinstance(data.get(k), str) and _TOKEN.fullmatch(data[k])
                                             for k in ('vid', 'skey')):
        raise WereadError('session_incomplete')
    return data


def save_session(vid, skey, path=DEFAULT_SESSION):
    """独占创建同目录随机名 0600 临时文件，写完 fsync 再原子改名；目录链有软链接或共享权限就拒绝。"""
    vid, skey = str(vid), str(skey)
    if not (_TOKEN.fullmatch(vid) and _TOKEN.fullmatch(skey)):
        raise WereadError('session_incomplete')
    body = json.dumps({'vid': vid, 'skey': skey, 'saved_at': datetime.now(timezone.utc).isoformat(timespec='seconds')})
    try:
        private_file.write_private(path, body)
    except private_file.PrivateFileError as exc:
        raise WereadError(f'session_save_{exc.code}') from None


# ---------- HTTP（curl；Cookie 走标准输入） ----------

def _looks_like_login(location):
    return 'login' in location.lower()


def _curl(url, session, timeout, accept, extra=(), run=None):
    """一次请求，curl 不跟跳转（不开 location，加 globoff 关掉 URL 展开）。返回 (body, http_code, 跳转目标)。
    URL 不是固定站点下的安全地址就不发请求。"""
    if not isinstance(url, str) or not _SAFE_URL.fullmatch(url):
        raise WereadError('bad_url')
    config = [f'url = "{url}"', 'globoff', f'user-agent = "{UA}"', f'header = "Accept: {accept}"',
              f'header = "Referer: {BASE}/"', f'max-time = {int(timeout)}', 'silent', 'proto = "=https"', *extra]
    if session:
        config.append(f'cookie = "wr_vid={session["vid"]}; wr_skey={session["skey"]}"')
    try:
        r = (run or subprocess.run)(['curl', '-q', '-K', '-', '-w', '\n%{http_code} %{redirect_url}'],
                                    input='\n'.join(config) + '\n', capture_output=True, text=True,
                                    encoding='utf-8', errors='strict', timeout=timeout + 15)
    except (OSError, subprocess.TimeoutExpired):
        raise WereadError('network') from None
    except UnicodeDecodeError:
        raise WereadError('bad_encoding') from None
    if r.returncode:
        raise WereadError('network')
    body, _, tail = r.stdout.rpartition('\n')
    code, _, location = tail.partition(' ')
    return body, code, location.strip()


def _parse_err_code(value):
    if isinstance(value, bool):
        return 'api_error'
    if isinstance(value, int):
        num = value
    elif isinstance(value, str):
        text = value.strip()
        if re.fullmatch(r'[+-]?\d{1,18}', text):
            num = int(text)
        else:
            return 'api_error'
    else:
        return 'api_error'
    if num == 0:
        return None
    if num in LOGIN_ERRORS:
        return 'login_expired'
    return f'api_{num}'


def _check_api_error(data):
    """检查顶层与嵌套 data 里的 errCode/errcode（含整数与数字字符串）；bool 一律按 api_error。"""
    if not isinstance(data, dict):
        return
    nested = data.get('data') if isinstance(data.get('data'), dict) else None
    for container in (data, nested):
        if not container:
            continue
        for key in ('errCode', 'errcode'):
            if key in container and container[key] is not None:
                code = _parse_err_code(container[key])
                if code:
                    raise WereadError(code)


def _fetch(url, session, timeout, accept, extra=(), run=None):
    """只认 2xx。任何 3xx 都不跟（登录页跳转 = 会话失效），401/403 = 会话失效，其它非 2xx = http_<码>。"""
    body, code, location = _curl(url, session, timeout, accept, extra, run=run)
    if code.startswith('3'):
        raise WereadError('login_expired' if _looks_like_login(location) else 'redirect_blocked')
    if code in AUTH_FAILED:
        raise WereadError('login_expired')
    if not (len(code) == 3 and code.startswith('2') and code.isdigit()):
        raise WereadError(f'http_{code}' if code.isdigit() else 'http_unknown')
    return body, code


def http_json(url, session=None, timeout=25, run=None):
    body, code = _fetch(url, session, timeout, 'application/json, text/plain, */*', run=run)
    try:
        data = json.loads(body) if body.strip() else {}
    except (ValueError, RecursionError):
        raise WereadError(f'http_{code}_not_json') from None
    if not isinstance(data, dict):
        raise WereadError(f'http_{code}_not_object')
    _check_api_error(data)
    return data


def http_text(url, session=None, timeout=40, run=None):
    """正文页可达数 MB，请求压缩减少传输超时；Cookie 仍走标准输入，不打印。
    若 200 正文实际是 JSON 错误回包，复用同一套 errCode 检查。"""
    body, _ = _fetch(url, session, timeout, 'text/html,application/xhtml+xml', extra=('compressed',), run=run)
    if body.lstrip().startswith('{'):
        try:
            data = json.loads(body)
        except (ValueError, RecursionError):
            data = None
        if isinstance(data, dict):
            _check_api_error(data)
    return body


# ---------- 登录 ----------

def confirm_url(uid):
    return f'{BASE}/web/confirm?uid={quote(uid)}'


def write_qr(text, png_path):
    """有 segno 就出二维码图；没有返回 False，调用方只给链接。"""
    try:
        import segno
    except ImportError:
        return False
    segno.make(text, error='m').save(str(png_path), scale=10, border=3)
    return True


def _log(line):
    print(line, flush=True)     # 输出常被重定向到文件，不 flush 的话二维码链接要等进程退出才看得到


def login(qr_png=None, wait=600, uid=None, otp='', session_path=DEFAULT_SESSION, get=http_json, log=_log, clock=time.monotonic):
    """扫码登录。getLoginInfo 是长轮询，约 56 秒回一次 {logicCode: LOGIN_TIMEOUT, canRetry: true}：这只是这一轮等完了，
    同一个二维码仍然有效，用同一个 uid 接着轮询，直到 wait 秒用完（2026-11-16 前两次扫码失败就是把它当成过期退出了）。
    只有服务端回 LOGIN_TIMEOUT 且没有 canRetry 时才换新二维码（覆盖同一个 PNG、打印 refreshed）。带 --otp 重试时不换。"""
    fixed = bool(uid)

    def new_qr(step):
        nonlocal uid
        uid = (get(f'{BASE}/api/auth/getLoginUid') or {}).get('uid')
        if not uid:
            raise WereadError('no_uid')
        url = confirm_url(uid)
        made = write_qr(url, qr_png) if qr_png else False
        log(json.dumps({'step': step, 'uid': uid, 'confirm_url': url, 'qr_png': str(qr_png) if made else None,
                        'how': '二维码约 1 分钟就失效：用微信扫二维码（或在微信里打开 confirm_url），在手机上点确认登录'}, ensure_ascii=False))

    if fixed:
        log(json.dumps({'step': 'otp', 'uid': uid}, ensure_ascii=False))
    else:
        new_qr('scan')
    deadline = clock() + wait
    while clock() < deadline:
        try:
            info = get(f'{BASE}/api/auth/getLoginInfo?' + urlencode({'uid': uid, 'otp': otp}), timeout=65)
        except WereadError as exc:
            if exc.code == 'network':
                continue      # 长轮询超时：接着等
            raise
        if info.get('accessToken') and info.get('webLoginVid'):
            save_session(info['webLoginVid'], info['accessToken'], session_path)
            log(json.dumps({'step': 'done', 'session': str(session_path)}, ensure_ascii=False))
            return True
        code = info.get('logicCode')
        if code == 'NEED_OTP':
            log(json.dumps({'step': 'need_otp', 'uid': uid,
                            'how': f'手机上会显示验证码；拿到后运行 login --uid {uid} --otp <验证码>'}, ensure_ascii=False))
            return False
        if code == 'LOGIN_TIMEOUT' and info.get('canRetry'):
            continue          # 长轮询约 56 秒回一次 {LOGIN_TIMEOUT, canRetry:true}：同一个二维码仍有效，接着等
        if code == 'LOGIN_TIMEOUT' and not fixed and clock() < deadline:
            new_qr('refreshed')   # 服务端说不能再等这个码了，才换新码
            continue
        if code in ('LOGIN_TIMEOUT', 'OTP_EXPIRED'):
            log(json.dumps({'step': 'expired', 'how': '二维码过期了，重新运行 login 生成新的'}, ensure_ascii=False))
            return False
        if code == 'OTP_NOT_MATCH':
            log(json.dumps({'step': 'otp_wrong'}, ensure_ascii=False))
            return False
    log(json.dumps({'step': 'timeout', 'how': '等太久没扫，重新运行 login'}, ensure_ascii=False))
    return False


# ---------- 公众号 bookId 与文章 ----------

def _find_mp_books(node, out):
    if isinstance(node, dict):
        bid = node.get('bookId')
        if isinstance(bid, str) and bid.startswith('MP_WXS_'):
            out.append({'book_id': bid, 'title': str(node.get('title') or node.get('name') or ''),
                        'cover': node.get('cover') or ''})
        for v in node.values():
            _find_mp_books(v, out)
    elif isinstance(node, list):
        for v in node:
            _find_mp_books(v, out)
    return out


def _norm(name):
    return ''.join(str(name).lower().split())


def resolve_book_id(account, session, get=http_json, cache=None):
    if account.get('book_id'):
        return account['book_id']
    cache = cache if cache is not None else {}
    if cache.get(account['handle']):
        return cache[account['handle']]
    data = get(f'{BASE}/api/store/search?' + urlencode({'keyword': account['handle'], 'count': 20}), session=session)
    want = _norm(account['handle'])
    for book in _find_mp_books(data, []):
        if _norm(book['title']) == want:
            cache[account['handle']] = book['book_id']
            return book['book_id']
    raise WereadError('book_not_found')


def short_url(review_id):
    """reviewId 形如 MP_WXS_<id>_<token>，token 就是 mp.weixin.qq.com/s/ 短链。"""
    token = str(review_id or '').rsplit('_', 1)[-1]
    return f'https://mp.weixin.qq.com/s/{token}' if token else ''


def cover_row(data):
    """/api/mp/cover 回包 → article_rows 同形，发布时间要另读正文页。"""
    rid = data.get('reviewId')
    title = str(data.get('title') or '').strip()
    if not rid or not title:
        return None
    pic = data.get('pic') if str(data.get('pic') or '').startswith('http') else ''
    avatar = data.get('avatar') if str(data.get('avatar') or '').startswith('http') else ''
    return {'review_id': rid, 'title': title, 'published': None, 'cover': pic, 'summary': '',
            'url': short_url(rid), 'avatar': avatar, 'display_name': str(data.get('name') or '').strip()}


def content_meta(html):
    """从 /web/mp/content 的 HTML 里取发布时间（unix 秒）和原文链接。没有时间就返回 published=None。"""
    out = {'published': None, 'url': ''}
    if not html:
        return out
    m = re.search(r'property="og:url" content="([^"]+)"', html) or re.search(r'og:url" content="([^"]+)"', html)
    if m:
        out['url'] = (m.group(1).replace('&amp;', '&').split('#')[0])
    for pat in (r"ori_create_time:\s*'(\d+)'", r"create_timestamp:\s*'(\d+)'",
                r'"publish_time"\s*:\s*(\d+)', r'publish_time%22%3A(\d+)', r'\bct\s*=\s*"(\d+)"'):
        m = re.search(pat, html)
        if m:
            out['published'] = int(m.group(1))
            break
    if out['published'] is None:
        m = re.search(r"create_time:\s*'(\d{4}-\d{2}-\d{2} \d{2}:\d{2})'", html)
        if m:
            out['published'] = int(datetime.strptime(m.group(1), '%Y-%m-%d %H:%M').replace(tzinfo=timezone(timedelta(hours=8))).timestamp())
    return out


def article_rows(data):
    """/web/mp/articles 的回包 → [{review_id, title, published(epoch), cover, summary, url}]"""
    rows = []
    for group in data.get('reviews') or []:
        subs = group.get('subReviews') or [group]
        for sub in subs:
            review = (sub or {}).get('review') or {}
            mp = review.get('mpInfo') or {}
            rid = review.get('reviewId')
            when = mp.get('time') or review.get('createTime')
            if not rid or not mp.get('title') or not isinstance(when, (int, float)):
                continue
            url = next((mp.get(k) for k in ('doc_url', 'url', 'link') if str(mp.get(k) or '').startswith('https://')), '') or short_url(rid)
            rows.append({'review_id': rid, 'title': str(mp['title']).strip(), 'published': int(when),
                         'cover': mp.get('pic_url') if str(mp.get('pic_url') or '').startswith('https://') else '',
                         'summary': normalize_text(str(mp.get('content') or mp.get('abstract') or '')), 'url': url})
    return rows


def _to_posts(rows, account, platform, fetched_at):
    sid = source_id(platform['id'], account['handle'])
    out = []
    for row in sorted((r for r in rows if r.get('published')), key=lambda r: r['published'], reverse=True):
        moment = datetime.fromtimestamp(row['published'], tz=timezone.utc)
        item = {
            'id': f'{sid}:{row["review_id"]}',
            'kind': 'post', 'channel': None, 'source_id': sid, 'source_name': account['name'],
            'title': row['title'], 'summary': summary_of(row['summary']), 'body': row['summary'],
            'url': row['url'] or short_url(row['review_id']),
            'image': {'url': row['cover']} if row['cover'] else None,
            'published_at': iso(moment), 'fetched_at': fetched_at,
            'lang': detect_lang(row['title'], row['summary']),
            'blogger': {'platform': platform['id'], 'handle': account['handle'],
                        'display_name': row.get('display_name') or account['name'],
                        'media': [], 'quote': None},
        }
        if row.get('avatar'):
            item['blogger']['avatar'] = row['avatar']
        out.append(item)
    return out


def wechat_posts(account, platform, fetched_at, session, get=http_json, get_text=None, limit=10, cache=None):
    book = resolve_book_id(account, session, get=get, cache=cache)
    try:
        data = get(f'{BASE}/web/mp/articles?' + urlencode({'bookId': book, 'offset': 0}), session=session)
    except WereadError as exc:
        if exc.code == 'login_expired':
            raise
        data = {}     # 列表接口常回 -2041（不是登录失效）：改走 cover
    rows = article_rows(data if isinstance(data, dict) else {})
    via = 'articles'
    if not rows:
        cover = get(f'{BASE}/api/mp/cover?' + urlencode({'bookId': book}), session=session)
        row = cover_row(cover if isinstance(cover, dict) else {})
        if not row:
            raise WereadError('cover_missing')   # 列表和 cover 都没读到：当失败，保留旧文但不算 ok
        via = 'cover'
        text_get = get_text or http_text
        # Let the runner retain both old content and last_ok_at when content cannot be read.
        html = text_get(f'{BASE}/web/mp/content?' + urlencode({'reviewId': row['review_id']}), session=session)
        meta = content_meta(html)
        if not meta.get('published'):
            raise WereadError('content_time_missing')
        row['published'] = meta['published']
        rows = [row]
    posts = _to_posts(rows, account, platform, fetched_at)[:limit]
    return posts, via


def load_books(path=BOOKS_CACHE):
    try:
        return json.loads(Path(path).read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {}


def save_books(cache, path=BOOKS_CACHE):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cache, ensure_ascii=False, indent=1), encoding='utf-8')


def main(argv=None):
    ap = argparse.ArgumentParser(prog='python3 -m rebang.bloggers.weread')
    sub = ap.add_subparsers(dest='cmd', required=True)
    lg = sub.add_parser('login', help='扫码登录微信读书网页版，成功后写会话文件（0600，仓库外）')
    lg.add_argument('--qr-png', default=None, help='二维码图片路径；默认放进新建的私有临时目录（mktemp -d 那种，0700）')
    lg.add_argument('--wait', type=int, default=600, help='最多等几秒')
    lg.add_argument('--uid', default=None, help='接着等同一个二维码（验证码步骤用）')
    lg.add_argument('--otp', default='')
    lg.add_argument('--session', default=str(DEFAULT_SESSION))
    st = sub.add_parser('status', help='只看会话文件在不在、能不能读到书架（不打印内容）')
    st.add_argument('--session', default=str(DEFAULT_SESSION))
    args = ap.parse_args(argv)
    if args.cmd == 'login':
        problem = private_file.account_problem()
        if problem:
            print(json.dumps({'step': 'failed', 'error': problem}, ensure_ascii=False))
            return 1
        qr_png = args.qr_png or str(Path(tempfile.mkdtemp(prefix='weread-qr-')) / 'weread-login-qr.png')
        try:
            return 0 if login(qr_png, args.wait, args.uid, args.otp, Path(args.session)) else 1
        except WereadError as exc:
            print(json.dumps({'step': 'failed', 'error': exc.code}, ensure_ascii=False))
            return 1
    try:
        session = load_session(args.session)
    except Exception as exc:   # 不在、不可进入、不安全、内容不对：一律当没有会话
        print(json.dumps({'session': False, 'error': getattr(exc, 'code', 'session_unreadable'), 'path': str(args.session)}))
        return 1
    try:
        info = http_json(f'{BASE}/api/userInfo?' + urlencode({'userVid': session['vid']}), session=session)
        # 只有用户接口明确回了本人的 userVid 才算有效；其它任何回包都当无效。
        if str(info.get('userVid', '')) != session['vid']:
            raise WereadError('user_unconfirmed')
        print(json.dumps({'session': True, 'valid': True, 'path': str(args.session)}))
        return 0
    except WereadError as exc:
        print(json.dumps({'session': True, 'valid': False, 'error': exc.code, 'path': str(args.session)}))
        return 1
    except Exception:
        print(json.dumps({'session': True, 'valid': False, 'error': 'status_failed', 'path': str(args.session)}))
        return 1


if __name__ == '__main__':
    sys.exit(main())
