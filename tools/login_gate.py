#!/usr/bin/env python3
"""内网版登录：用登录页 + 长效 Cookie 代替浏览器的 Basic Auth 弹窗。

Basic Auth 的账号密码由浏览器记在内存里，关掉浏览器就没了，服务器设不了有效期。
这个小服务签发一个 Cookie（默认 180 天，每天访问时自动续期），nginx 用 auth_request、
Caddy 用 forward_auth 向它确认。只用标准库。

  python3 tools/login_gate.py passwd <账号>      设置或修改密码（改密码后所有设备需重新登录）
  python3 tools/login_gate.py serve [--port 8780] [--days 180]

账号和签名密钥存在 $LOGIN_GATE_DIR（默认 ~/.config/shiguang-login），不进 git。
接入方法见 PRIVATE_LOGIN.md。
"""
import argparse, base64, getpass, hashlib, hmac, html, json, os, secrets, sys, threading, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote

PREFIX = '/__login/'
COOKIE = 'sg_login'
ITERATIONS = 310_000
REFRESH_AFTER = 86400          # re-issue the cookie once it is a day old, so 180 days run from the last visit
MAX_FAILURES, FAILURE_WINDOW = 10, 900


def state_dir():
    return Path(os.getenv('LOGIN_GATE_DIR') or Path.home() / '.config' / 'shiguang-login')


def _write_private(path, data):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    tmp = path.with_suffix('.tmp')
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, 'wb') as f: f.write(data)
    os.replace(tmp, path)


def secret_key(folder):
    path = folder / 'secret.key'
    if not path.exists(): _write_private(path, secrets.token_bytes(32))
    return path.read_bytes()


def load_users(folder):
    path = folder / 'users.json'
    return json.loads(path.read_text()) if path.exists() else {}


def hash_password(password, salt=None):
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac('sha256', password.encode(), salt, ITERATIONS)
    return f'pbkdf2_sha256${ITERATIONS}${salt.hex()}${digest.hex()}'


def check_password(password, stored):
    try:
        scheme, rounds, salt, digest = stored.split('$')
        assert scheme == 'pbkdf2_sha256'
        got = hashlib.pbkdf2_hmac('sha256', password.encode(), bytes.fromhex(salt), int(rounds))
    except (ValueError, AssertionError):
        return False
    return hmac.compare_digest(got.hex(), digest)


def set_password(folder, user, password):
    users = load_users(folder)
    users[user] = hash_password(password)
    _write_private(folder / 'users.json', json.dumps(users, indent=2).encode())


def _b64(data): return base64.urlsafe_b64encode(data).rstrip(b'=').decode()
def _unb64(text): return base64.urlsafe_b64decode(text + '=' * (-len(text) % 4))


def _version(stored):
    """Changes whenever the password changes, so a new password signs every device out."""
    return hashlib.sha256(stored.encode()).hexdigest()[:12]


def make_token(key, user, stored, days, now=None):
    now = int(now or time.time())
    body = _b64(json.dumps({'u': user, 'v': _version(stored), 'iat': now, 'exp': now + days * 86400}).encode())
    return body + '.' + _b64(hmac.new(key, body.encode(), hashlib.sha256).digest())


def read_token(key, token, users, now=None):
    """The token's claims if it is genuine, unexpired and its password is unchanged; else None."""
    try:
        body, signature = token.split('.')
        if not hmac.compare_digest(_unb64(signature), hmac.new(key, body.encode(), hashlib.sha256).digest()): return None
        claims = json.loads(_unb64(body))
    except (ValueError, TypeError):
        return None
    stored = users.get(claims.get('u'))
    if not stored or claims.get('v') != _version(stored) or claims.get('exp', 0) <= (now or time.time()): return None
    return claims


def safe_next(target):
    """Only local paths, so the login page cannot bounce anyone to another site."""
    target = (target or '').strip()
    if not target.startswith('/') or target.startswith('//') or target.startswith('/\\') or target.startswith(PREFIX):
        return '/'
    return target


PAGE = '''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><meta name="robots" content="noindex">
<title>登录 · 拾光热点</title><style>
:root{{color-scheme:light dark;--ground:#EEE8DF;--ink:#1D1B18;--ink-2:rgba(29,27,24,.64);--glass:rgba(255,255,255,.55);--field:rgba(29,27,24,.055);--warn:#B5621A}}
@media (prefers-color-scheme:dark){{:root{{--ground:#0F0E12;--ink:#F6F3EC;--ink-2:rgba(246,243,236,.66);--glass:rgba(255,255,255,.10);--field:rgba(255,255,255,.07);--warn:#F0A54A}}}}
*{{box-sizing:border-box}}body{{margin:0;min-height:100vh;display:grid;place-items:center;padding:16px;background:var(--ground);color:var(--ink);
font:16px/1.5 -apple-system,BlinkMacSystemFont,"PingFang SC","Noto Sans SC",sans-serif}}
form{{width:100%;max-width:360px;padding:28px 24px;border-radius:28px;background:var(--glass);
box-shadow:inset 0 1px 0 rgba(255,255,255,.6),0 0 0 1px rgba(60,52,40,.10),0 12px 32px -14px rgba(72,52,22,.28)}}
h1{{margin:0 0 4px;font-size:22px;font-weight:600}}p{{margin:0 0 20px;color:var(--ink-2);font-size:14px}}
label{{display:block;margin:12px 0 6px;font-size:14px;color:var(--ink-2)}}
input{{width:100%;height:44px;padding:0 14px;border:0;border-radius:999px;background:var(--field);color:var(--ink);font-size:16px}}
input:focus{{outline:2px solid var(--ink)}}button{{width:100%;height:46px;margin-top:22px;border:0;border-radius:999px;
background:var(--ink);color:var(--ground);font-size:16px;font-weight:600;cursor:pointer}}.error{{color:var(--warn);margin:14px 0 0}}
</style></head><body><form method="post" action="{action}">
<h1>拾光热点 · 内网</h1><p>登录后这台设备 {days} 天内免登录。</p>
<input type="hidden" name="next" value="{next}">
<label for="u">账号</label><input id="u" name="user" autocomplete="username" autocapitalize="none" required autofocus>
<label for="p">密码</label><input id="p" name="password" type="password" autocomplete="current-password" required>
<button type="submit">登录</button>{error}</form></body></html>'''


class Gate:
    def __init__(self, folder, days=180, secure=None):
        self.folder, self.days, self.secure = Path(folder), days, secure
        self.key = secret_key(self.folder)
        self.failures, self.lock = {}, threading.Lock()

    def users(self): return load_users(self.folder)

    def cookie(self, token, request_secure, max_age=None):
        secure = self.secure if self.secure is not None else request_secure
        age = self.days * 86400 if max_age is None else max_age
        return f'{COOKIE}={token}; Max-Age={age}; Path=/; HttpOnly; SameSite=Lax' + ('; Secure' if secure else '')

    def blocked(self, ip, now):
        with self.lock:
            recent = [t for t in self.failures.get(ip, []) if now - t < FAILURE_WINDOW]
            self.failures[ip] = recent
            return len(recent) >= MAX_FAILURES

    def failed(self, ip, now):
        with self.lock: self.failures.setdefault(ip, []).append(now)


class Handler(BaseHTTPRequestHandler):
    server_version = 'login-gate'
    gate: Gate = None

    def log_message(self, fmt, *args):   # no query strings or cookies in the log
        sys.stderr.write('%s %s %s\n' % (self.client_ip(), self.command, self.path.split('?')[0]))

    def client_ip(self):
        if self.client_address[0] in ('127.0.0.1', '::1'):
            forwarded = self.headers.get('X-Real-IP') or (self.headers.get('X-Forwarded-For') or '').split(',')[0].strip()
            if forwarded: return forwarded
        return self.client_address[0]

    def request_secure(self):
        return self.headers.get('X-Forwarded-Proto', '').lower() == 'https'

    def token(self):
        for part in (self.headers.get('Cookie') or '').split(';'):
            name, _, value = part.strip().partition('=')
            if name == COOKIE: return value
        return ''

    def reply(self, status, body=b'', headers=()):
        self.send_response(status)
        for name, value in headers: self.send_header(name, value)
        self.send_header('Cache-Control', 'no-store')
        if body: self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        if self.command != 'HEAD': self.wfile.write(body)

    def page(self, status, target, error=''):
        body = PAGE.format(action=PREFIX, days=self.gate.days, next=html.escape(target),
                           error=f'<p class="error" role="alert">{html.escape(error)}</p>' if error else '')
        self.reply(status, body.encode(), [('X-Frame-Options', 'DENY'), ('Referrer-Policy', 'no-referrer')])

    def do_GET(self):
        path, _, query = self.path.partition('?')
        if path == PREFIX + 'check': return self.check()
        if path == PREFIX + 'logout':
            return self.reply(303, headers=[('Set-Cookie', self.gate.cookie('', self.request_secure(), 0)), ('Location', PREFIX)])
        if path in (PREFIX, PREFIX.rstrip('/')):
            # next= is taken raw (it may hold its own ? and &), as nginx passes $request_uri unencoded.
            target = safe_next(unquote(query[5:]) if query.startswith('next=') else '/')
            if read_token(self.gate.key, self.token(), self.gate.users()):
                return self.reply(303, headers=[('Location', target)])
            return self.page(200, target)
        self.reply(404)

    do_HEAD = do_GET

    def check(self):
        claims = read_token(self.gate.key, self.token(), self.gate.users())
        if claims:
            headers = []
            if time.time() - claims['iat'] > REFRESH_AFTER:   # sliding: 180 days from the last visit
                users = self.gate.users()
                headers.append(('Set-Cookie', self.gate.cookie(make_token(self.gate.key, claims['u'], users[claims['u']], self.gate.days),
                                                               self.request_secure())))
            return self.reply(204, headers=headers)
        original = self.headers.get('X-Forwarded-Uri')
        if original:   # Caddy forward_auth hands a non-2xx reply straight to the browser: send it to the login page
            return self.reply(302, headers=[('Location', PREFIX + '?next=' + quote(safe_next(original), safe='/?&=%'))])
        self.reply(401)   # nginx auth_request: error_page 401 redirects

    def do_POST(self):
        if self.path.split('?')[0].rstrip('/') != PREFIX.rstrip('/'): return self.reply(404)
        length = int(self.headers.get('Content-Length') or 0)
        if length > 4096: return self.reply(413)
        form = {k: v[0] for k, v in parse_qs(self.rfile.read(length).decode('utf-8', 'replace')).items()}
        target, ip, now = safe_next(form.get('next')), self.client_ip(), time.time()
        if self.gate.blocked(ip, now):
            return self.page(429, target, '尝试次数太多，请 15 分钟后再试。')
        user, stored = form.get('user', '').strip(), self.gate.users().get(form.get('user', '').strip())
        if stored and check_password(form.get('password', ''), stored):
            token = make_token(self.gate.key, user, stored, self.gate.days)
            return self.reply(303, headers=[('Set-Cookie', self.gate.cookie(token, self.request_secure())), ('Location', target)])
        self.gate.failed(ip, now)
        time.sleep(0.5)
        self.page(401, target, '账号或密码不对。')


def make_server(folder, host='127.0.0.1', port=8780, days=180, secure=None):
    handler = type('BoundHandler', (Handler,), {'gate': Gate(folder, days, secure)})
    return ThreadingHTTPServer((host, port), handler)


def main(argv=None):
    p = argparse.ArgumentParser(description='内网版登录服务（长效 Cookie）')
    sub = p.add_subparsers(dest='cmd', required=True)
    pw = sub.add_parser('passwd', help='设置或修改账号密码'); pw.add_argument('user')
    sv = sub.add_parser('serve', help='启动登录服务')
    sv.add_argument('--host', default='127.0.0.1'); sv.add_argument('--port', type=int, default=8780)
    sv.add_argument('--days', type=int, default=180, help='免登录天数（浏览器最多认 400 天）')
    sv.add_argument('--secure', choices=('auto', 'on', 'off'), default='auto', help='Cookie 的 Secure 标记；auto 按 X-Forwarded-Proto')
    args = p.parse_args(argv)
    folder = state_dir()
    if args.cmd == 'passwd':
        first = getpass.getpass('新密码：')
        if len(first) < 8: raise SystemExit('密码至少 8 位')
        if getpass.getpass('再输一次：') != first: raise SystemExit('两次输入不一致')
        set_password(folder, args.user, first)
        print(f'已保存 {args.user}（{folder / "users.json"}）。改过密码后，所有设备需要重新登录一次。')
        return
    if not load_users(folder): raise SystemExit(f'还没有账号，先运行：python3 {sys.argv[0]} passwd <账号>')
    days = max(1, min(args.days, 400))
    server = make_server(folder, args.host, args.port, days, {'auto': None, 'on': True, 'off': False}[args.secure])
    print(f'login gate on http://{args.host}:{args.port}{PREFIX} · {days} 天', flush=True)
    server.serve_forever()


if __name__ == '__main__':
    main()
