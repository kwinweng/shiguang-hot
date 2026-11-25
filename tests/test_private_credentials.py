"""Collectors open credentials themselves, safely, and never carry them across origins. Offline only.

Edge cases:
- the file passes the publisher preflight, then is swapped for a symlink or a 0644 file before the
  collector opens it; a component is swapped while the collector walks the path;
- WeRead session content `[]`, `null`, a string, `{}`, missing or non-string vid/skey, characters that
  would change the curl config; unsafe session file: all "not configured", the round does not crash,
  and earlier WeChat items are kept;
- saving the session: random exclusive temp name (a planted fixed `.tmp` symlink is not followed),
  a symlinked directory is refused, an existing shared directory is tightened;
- Weibo redirects: cross-origin (another port) sends nothing there; https→http and cross-host are not
  followed; same https origin is followed with the Cookie; a cross-origin login redirect = expired;
- WeRead redirects: curl never follows anything; every 3xx (same origin, relative, cross-origin,
  https→http) is a failed request after exactly one call; a login-page redirect = login_expired;
- WeRead curl config: only safe https://weread.qq.com/ URLs (quote, space, newline, backslash, `@`,
  other host, http → bad_url, curl never runs); `globoff` always on;
- WeRead session folder that cannot be entered: the round does not crash, accounts are not configured,
  and `status` reports no session;
- WeRead HTTP 401/403 with an ordinary JSON body → login_expired; 500 with JSON → http_500; a non-zero
  errCode → failure; cover with nothing → failure. In the round: status is not ok, last_ok_at stays at
  the previous value, old items are kept (stale) and the health board shows a problem;
- `weread status`: valid only when the user API confirms this account's userVid; API errors, 401,
  a redirect, an empty or a different user are all invalid;
- `weibo save-cookie`: 0600 atomic write, no contents printed, refuses root and symlinked folders;
  over 64 KiB (UTF-8 bytes incl. newline) is refused before any folder or the old file is touched;
  `save-cookie`/`check` ignore REBANG_WEIBO_COOKIE and use only the account-home fixed path.
"""
from datetime import datetime, timezone
import http.server
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import urllib.request

import pytest

from rebang import private_file
from rebang.bloggers import run as runmod
from rebang.bloggers import weibo, weread

NOW = datetime(2026, 11, 25, 12, 0, tzinfo=timezone.utc)
_REAL_SUBPROCESS_RUN = subprocess.run


@pytest.fixture(autouse=True)
def no_real_curl(monkeypatch):
    """Offline guard: any WeRead call that would run the real curl fails the test instead."""
    def refuse(*args, **kwargs):
        raise AssertionError(f'offline test tried to run a subprocess: {args[:1]}')
    monkeypatch.setattr(weread.subprocess, 'run', refuse)


def offline(*args, **kwargs):
    raise OSError('offline test: no network')
SECRET = 'SUB=fake-cookie-value; XSRF=fake'


@pytest.fixture
def folder(tmp_path):
    path = tmp_path.resolve() / 'cfg' / 'rebang'
    path.mkdir(parents=True, mode=0o700)
    path.chmod(0o700)
    return path


def put(path, text=SECRET, mode=0o600):
    path.write_text(text)
    path.chmod(mode)
    return path


# ---------- open-time checks (TOCTOU) ----------

def test_swapped_for_symlink_after_preflight_is_refused(folder):
    cookie = put(folder / 'weibo-cookie.txt')
    assert private_file.check_private(cookie)          # what the publisher saw
    attacker = put(folder.parent / 'attacker.txt', 'ATTACKER')
    cookie.unlink()
    cookie.symlink_to(attacker)                        # swapped before the collector opens
    with pytest.raises(weibo.WeiboError) as exc:
        weibo.read_cookie(cookie)
    assert exc.value.code == 'cookie_unreadable'


def test_swapped_for_shared_file_after_preflight_is_refused(folder):
    cookie = put(folder / 'weibo-cookie.txt')
    assert private_file.check_private(cookie)
    replacement = put(folder / 'new', 'OTHER', 0o644)
    os.replace(replacement, cookie)
    with pytest.raises(weibo.WeiboError):
        weibo.read_cookie(cookie)


def test_directory_swapped_during_the_walk_cannot_redirect_the_open(folder, monkeypatch):
    cookie = put(folder / 'weibo-cookie.txt')
    evil = folder.parent / 'evil'
    evil.mkdir(mode=0o700)
    put(evil / 'weibo-cookie.txt', 'ATTACKER')
    real_open = os.open
    swapped = []

    def racing_open(path, flags, mode=0o777, *, dir_fd=None):
        fd = real_open(path, flags, mode, dir_fd=dir_fd)
        if path == 'rebang' and not swapped:           # right after the holding directory was opened
            os.rename(folder, folder.parent / 'moved')
            os.symlink(evil, folder)
            swapped.append(True)
        return fd
    monkeypatch.setattr(private_file.os, 'open', racing_open)
    # The verified descriptor still points at the original directory: never the attacker's file.
    assert weibo.read_cookie(cookie) == SECRET
    assert swapped


def test_file_swapped_between_walk_and_open_is_refused(folder, monkeypatch):
    cookie = put(folder / 'weibo-cookie.txt')
    attacker = put(folder.parent / 'attacker.txt', 'ATTACKER')
    real_open = os.open

    def racing_open(path, flags, mode=0o777, *, dir_fd=None):
        if path == 'weibo-cookie.txt':
            cookie.unlink()
            cookie.symlink_to(attacker)
        return real_open(path, flags, mode, dir_fd=dir_fd)
    monkeypatch.setattr(private_file.os, 'open', racing_open)
    with pytest.raises(weibo.WeiboError):
        weibo.read_cookie(cookie)


def test_unsafe_cookie_reports_not_configured_and_keeps_old_items(folder, tmp_path):
    cookie = put(folder / 'weibo-cookie.txt', mode=0o644)
    o = runmod.Options(weibo_cookie_file=str(cookie), weibo_output=str(tmp_path / 'out'), pause=0)
    o.weibo_get = lambda *a, **k: pytest.fail('must not request with an unsafe cookie')
    env = runmod.run(('weibo',), http=offline, now=NOW, opts=o, sleep=lambda s: None)
    platform = env['platforms'][0]
    assert platform['status'] == 'not_configured'
    assert {a['error'] for a in platform['accounts']} == {'weibo_cookie_unset'}


# ---------- WeRead session content ----------

@pytest.mark.parametrize('content', ['[]', 'null', '"text"', '{}', '{"vid": "1"}', '{"vid": 1, "skey": "k"}',
                                     '{"vid": "1", "skey": ""}', '{"vid": "1", "skey": null}',
                                     '{"vid": "1", "skey": "a\\" output = \\"/tmp/x"}', '{"vid": "1", "skey": "a\\nb"}',
                                     'not json', '[[[[[[[[[['])
def test_bad_session_content_is_only_a_weread_error(folder, content):
    session = put(folder / 'weread-session.json', content)
    with pytest.raises(weread.WereadError):
        weread.load_session(session)


def wechat_previous():
    item = {'id': 'wechat-MacTalk:old', 'kind': 'post', 'channel': None, 'source_id': 'wechat-MacTalk',
            'source_name': 'MacTalk', 'title': '上次的文章', 'summary': '', 'body': '', 'url': 'https://mp.weixin.qq.com/s/OLD',
            'image': None, 'published_at': '2026-11-24T00:00:00+00:00', 'fetched_at': '2026-11-24T00:00:00+00:00',
            'lang': 'zh', 'blogger': {'platform': 'wechat', 'handle': 'MacTalk', 'display_name': 'MacTalk',
                                      'media': [], 'quote': None}}
    return item


@pytest.mark.parametrize('content,mode', [('[]', 0o600), ('null', 0o600), ('{"vid": "1"}', 0o600),
                                          ('{"vid": "1", "skey": "k"}', 0o644)])
def test_bad_or_unsafe_session_is_not_configured_and_keeps_wechat_items(folder, tmp_path, content, mode):
    session = put(folder / 'weread-session.json', content, mode)
    o = runmod.Options(pause=0)
    o.weread_session = str(session)
    o.weread_books = tmp_path / 'books.json'
    o.weread_get = lambda *a, **k: pytest.fail('must not request without a usable session')
    first = runmod.run(('wechat',), http=offline, now=NOW, opts=o, sleep=lambda s: None)
    platform = first['platforms'][0]
    mac = next(a for a in platform['accounts'] if a['handle'] == 'MacTalk')
    assert (mac['status'], mac['error']) == ('not_configured', 'wechat_weread_qr')

    previous = dict(first, items=first['items'] + [wechat_previous()])
    for row in previous['platforms'][0]['accounts']:
        if row['handle'] == 'MacTalk':
            row['last_ok_at'] = '2026-11-24T00:00:00+00:00'
    later = runmod.run(('wechat',), http=offline, now=NOW, previous=previous,
                       opts=o, sleep=lambda s: None)
    assert [i['title'] for i in later['items'] if i['source_id'] == 'wechat-MacTalk'] == ['上次的文章']
    row = next(a for a in later['platforms'][0]['accounts'] if a['handle'] == 'MacTalk')
    assert row['stale'] is True and row['last_ok_at'] == '2026-11-24T00:00:00+00:00'


# ---------- saving the session ----------

def test_save_session_uses_a_fresh_exclusive_temp_file(folder):
    session = folder / 'weread-session.json'
    target = put(folder.parent / 'victim.txt', 'UNTOUCHED', 0o644)
    (folder / 'weread-session.json.tmp').symlink_to(target)    # the old fixed temp name, planted
    weread.save_session('12345', 'TOKEN', session)
    assert target.read_text() == 'UNTOUCHED' and oct(target.stat().st_mode & 0o777) == '0o644'
    assert oct(session.stat().st_mode & 0o777) == '0o600'
    assert weread.load_session(session)['skey'] == 'TOKEN'
    assert sorted(p.name for p in folder.iterdir()) == ['weread-session.json', 'weread-session.json.tmp']


def test_save_session_tightens_existing_folder_and_refuses_symlinked_folder(tmp_path):
    base = tmp_path.resolve()
    shared = base / 'shared'
    shared.mkdir(mode=0o755)
    shared.chmod(0o755)
    weread.save_session('1', 'k', shared / 's.json')
    assert oct(shared.stat().st_mode & 0o777) == '0o700'

    real = base / 'real'
    real.mkdir(mode=0o700)
    (base / 'link').symlink_to(real)
    with pytest.raises(weread.WereadError):
        weread.save_session('1', 'k', base / 'link' / 's.json')
    assert not list(real.iterdir())


def test_save_session_refuses_unsafe_tokens(folder):
    with pytest.raises(weread.WereadError):
        weread.save_session('1', 'a" output = "/tmp/x', folder / 's.json')
    assert not (folder / 's.json').exists()


def test_login_cli_defaults_qr_to_a_private_temp_folder(monkeypatch, tmp_path):
    seen = {}

    def fake_login(qr_png, wait, uid, otp, session_path, **_):
        seen.update(qr=Path(qr_png), session=session_path)
        return True
    monkeypatch.setattr(weread, 'login', fake_login)
    monkeypatch.setattr(private_file, 'account_problem', lambda: None)
    assert weread.main(['login', '--session', str(tmp_path / 's.json')]) == 0
    assert seen['session'] == tmp_path / 's.json'
    assert not str(seen['qr']).startswith('/tmp/weread-login-qr')
    assert oct(seen['qr'].parent.stat().st_mode & 0o777) == '0o700'
    seen['qr'].parent.rmdir()


# ---------- Weibo redirects ----------

class Recorder(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        self.server.seen.append((self.path, self.headers.get('Cookie')))
        if self.server.redirect:
            self.send_response(302)
            self.send_header('Location', self.server.redirect)
            self.end_headers()
            return
        body = b'{"ok": 1, "data": {}}'
        self.send_response(200)
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


def serve(redirect=None):
    server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Recorder)
    server.seen, server.redirect = [], redirect
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def test_weibo_cross_origin_redirect_never_reaches_the_other_origin():
    other = serve()
    first = serve(redirect=f'http://127.0.0.1:{other.server_port}/steal')
    try:
        with pytest.raises(weibo.WeiboError) as exc:
            weibo.http_json(f'http://127.0.0.1:{first.server_port}/ajax/x', SECRET)
        assert exc.value.code == 'redirect_blocked' and SECRET not in str(exc.value)
        assert first.seen == [('/ajax/x', SECRET)]
        assert other.seen == []
    finally:
        first.shutdown()
        other.shutdown()


def redirect(handler, url, newurl):
    req = urllib.request.Request(url, headers={'Cookie': SECRET})
    return handler.redirect_request(req, io.BytesIO(), 302, 'Found', {}, newurl)


@pytest.mark.parametrize('newurl', ['https://evil.example/ajax', 'http://weibo.com/ajax/y',
                                    'https://weibo.com:8443/ajax/y', 'https://weibo.com.evil.example/'])
def test_weibo_redirect_handler_blocks_other_origins_and_downgrades(newurl):
    with pytest.raises(weibo.RedirectBlocked):
        redirect(weibo.SameOriginRedirect(), 'https://weibo.com/ajax/x', newurl)


def test_weibo_redirect_handler_follows_same_https_origin_with_cookie():
    new = redirect(weibo.SameOriginRedirect(), 'https://weibo.com/ajax/x', 'https://WEIBO.com:443/ajax/y')
    assert new.full_url == 'https://WEIBO.com:443/ajax/y' and new.get_header('Cookie') == SECRET
    with pytest.raises(weibo.RedirectBlocked):   # a plain-http original never carries the Cookie on
        redirect(weibo.SameOriginRedirect(), 'http://weibo.com/ajax/x', 'http://weibo.com/ajax/y')


def test_weibo_cross_origin_login_redirect_is_login_expired(monkeypatch):
    class Opener:
        def open(self, req, timeout=0):
            raise weibo.RedirectBlocked('https://passport.weibo.com/visitor/visitor?entry=miniblog')
    monkeypatch.setattr(weibo, '_OPENER', Opener())
    with pytest.raises(weibo.WeiboError) as exc:
        weibo.http_json('https://weibo.com/ajax/x', SECRET)
    assert exc.value.code == 'login_expired'


# ---------- WeRead redirects ----------

class FakeCurl:
    """Stands in for subprocess.run: answers by URL and records whether a Cookie was configured."""

    def __init__(self, replies):
        self.replies, self.calls = replies, []

    def __call__(self, args, input, **kwargs):
        lines = input.splitlines()
        assert 'location' not in lines and '-L' not in args
        url = next(line for line in lines if line.startswith('url = '))[7:-1]
        self.calls.append((url, any(line.startswith('cookie = ') for line in lines)))
        code, location, body = self.replies[url]
        return subprocess.CompletedProcess(args, 0, stdout=f'{body}\n{code} {location}', stderr='')


SESSION = {'vid': '1', 'skey': 'k'}


@pytest.mark.parametrize('location', ['https://weread.qq.com/b', '/b', 'https://evil.example/b',
                                      'http://weread.qq.com/b', 'https://weread.qq.com:444/b', ''])
@pytest.mark.parametrize('code', ['301', '302', '303', '307', '308'])
def test_weread_never_follows_any_redirect(location, code):
    curl = FakeCurl({'https://weread.qq.com/a': (code, location, '{"ok": 1}')})
    for call in (weread.http_json, weread.http_text):
        with pytest.raises(weread.WereadError) as exc:
            call('https://weread.qq.com/a', SESSION, run=curl)
        assert exc.value.code == 'redirect_blocked'
    assert curl.calls == [('https://weread.qq.com/a', True)] * 2


@pytest.mark.parametrize('location', ['https://weread.qq.com/#login', 'https://weread.qq.com/web/login?x=1',
                                      'https://open.weixin.qq.com/connect/qrconnect?redirect=LOGIN'])
def test_weread_login_redirect_is_login_expired_and_not_followed(location):
    curl = FakeCurl({'https://weread.qq.com/a': ('302', location, '')})
    with pytest.raises(weread.WereadError) as exc:
        weread.http_json('https://weread.qq.com/a', SESSION, run=curl)
    assert exc.value.code == 'login_expired'
    assert len(curl.calls) == 1


@pytest.mark.parametrize('url', ['https://weread.qq.com/a"\noutput = "/tmp/x', 'https://weread.qq.com/a b',
                                 'https://weread.qq.com/a\nb', 'https://weread.qq.com/a\\b',
                                 'https://user@weread.qq.com/a', 'https://weread.qq.com@evil.example/a',
                                 'https://evil.example/a', 'http://weread.qq.com/a', 'https://weread.qq.com.evil/a',
                                 'https://weread.qq.com/a#frag', "https://weread.qq.com/a'b", 'https://weread.qq.com/a\x7f',
                                 'https://weread.qq.com/a{1,2}', 'https://weread.qq.com/a[1-2]'])
def test_weread_unsafe_url_never_reaches_curl(url):
    def curl(*args, **kwargs):
        pytest.fail('curl must not run for an unsafe URL')
    for call in (weread.http_json, weread.http_text):
        with pytest.raises(weread.WereadError) as exc:
            call(url, SESSION, run=curl)
        assert exc.value.code == 'bad_url'


def test_weread_curl_config_has_globoff_and_no_location():
    seen = []

    def curl(args, input, **kwargs):
        seen.append(input.splitlines())
        return subprocess.CompletedProcess(args, 0, stdout='{"ok": 1}\n200 ', stderr='')
    url = 'https://weread.qq.com/web/mp/content?' + weread.urlencode({'reviewId': 'MP_WXS_1_a"b c'})
    assert weread.http_text(url, SESSION, run=curl) == '{"ok": 1}'
    lines = seen[0]
    assert 'globoff' in lines and 'location' not in lines
    assert lines[0] == f'url = "{url}"' and '"' not in url


@pytest.mark.parametrize('code,body,error', [('401', '{"errMsg": "unauthorized"}', 'login_expired'),
                                             ('403', '{"data": {}}', 'login_expired'),
                                             ('401', '', 'login_expired'),
                                             ('500', '{"reviewId": "MP_WXS_1_T", "title": "x"}', 'http_500'),
                                             ('404', '{}', 'http_404'),
                                             ('000', '', 'http_000'),
                                             ('200', '{"errCode": -2013, "errMsg": "x"}', 'api_-2013'),
                                             ('200', '{"errcode": "bad"}', 'api_error')])
def test_weread_non_2xx_or_api_error_is_a_failure(code, body, error):
    curl = FakeCurl({'https://weread.qq.com/a': (code, '', body)})
    with pytest.raises(weread.WereadError) as exc:
        weread.http_json('https://weread.qq.com/a', SESSION, run=curl)
    assert exc.value.code == error
    if code != '200':
        with pytest.raises(weread.WereadError):
            weread.http_text('https://weread.qq.com/a', SESSION, run=curl)


def test_weread_2xx_json_is_returned():
    curl = FakeCurl({'https://weread.qq.com/a': ('200', '', '{"ok": 1, "errCode": 0}')})
    assert weread.http_json('https://weread.qq.com/a', SESSION, run=curl) == {'ok': 1, 'errCode': 0}


def wechat_round(tmp_path, folder, curl, previous=None):
    session = folder / 'weread-session.json'
    if not session.exists():
        weread.save_session('1', 'k', session)
    o = runmod.Options(pause=0)
    o.weread_session = str(session)
    o.weread_books = tmp_path / 'books.json'
    o.weread_get = lambda url, session=None, timeout=25: weread.http_json(url, session, timeout, run=curl)
    o.weread_get_text = lambda url, session=None, timeout=40: weread.http_text(url, session, timeout, run=curl)
    return runmod.run(('wechat',), http=offline, now=NOW, previous=previous, opts=o, sleep=lambda s: None)


def wechat_previous_round(tmp_path, folder):
    first = wechat_round(tmp_path / 'first', folder, AnyCurl('500', '{}'))
    previous = dict(first, items=first['items'] + [wechat_previous()])
    for row in previous['platforms'][0]['accounts']:
        if row['handle'] == 'MacTalk':
            row.update(status='ok', last_ok_at='2026-11-24T00:00:00+00:00')
            row.pop('error', None)
            row.pop('reason', None)
    return previous


class AnyCurl:
    """Every WeRead URL gets the same reply."""

    def __init__(self, code, body):
        self.code, self.body, self.calls = code, body, 0

    def __call__(self, args, input, **kwargs):
        self.calls += 1
        return subprocess.CompletedProcess(args, 0, stdout=f'{self.body}\n{self.code} ', stderr='')


@pytest.mark.parametrize('code,body,status', [('401', '{"errMsg": "unauthorized"}', 'login_expired'),
                                              ('403', '{"reviewId": "MP_WXS_1_T", "title": "x"}', 'login_expired'),
                                              ('500', '{"reviewId": "MP_WXS_1_T", "title": "x"}', 'error'),
                                              ('200', '{}', 'error'),
                                              ('200', '{"errCode": -2041}', 'error')])
def test_weread_failure_keeps_old_items_but_is_not_ok(tmp_path, folder, code, body, status):
    from rebang.site.health import build_health
    previous = wechat_previous_round(tmp_path, folder)
    folder.chmod(0o700)
    curl = AnyCurl(code, body)
    env = wechat_round(tmp_path, folder, curl, previous=previous)
    assert curl.calls
    platform = env['platforms'][0]
    mac = next(a for a in platform['accounts'] if a['handle'] == 'MacTalk')
    assert mac['status'] == status and mac['status'] != 'ok'
    assert mac['last_ok_at'] == '2026-11-24T00:00:00+00:00'
    assert mac['stale'] is True
    assert [i['title'] for i in env['items'] if i['source_id'] == 'wechat-MacTalk'] == ['上次的文章']
    snapshot = build_health([('bloggers.json', env)], env['items'], NOW)
    wechat = next(r for r in snapshot['sources'] if r['id'] == 'wechat')
    row = next(a for a in wechat['accounts'] if a['id'] == 'wechat-MacTalk')
    assert row['status'] in ('failed', 'login_expired') and row['last_ok_at'] == '2026-11-24T00:00:00+00:00'


# ---------- WeRead session folder that cannot be entered ----------

@pytest.fixture
def locked(folder):
    weread.save_session('1', 'k', folder / 'weread-session.json')
    folder.chmod(0)
    yield folder
    folder.chmod(0o700)


@pytest.mark.skipif(os.getuid() == 0, reason='root can enter any folder')
def test_session_folder_not_enterable_does_not_crash_the_round(locked, tmp_path):
    o = runmod.Options(pause=0)
    o.weread_session = str(locked / 'weread-session.json')
    o.weread_books = tmp_path / 'books.json'
    o.weread_get = lambda *a, **k: pytest.fail('must not request without a readable session')
    env = runmod.run(('wechat',), http=offline, now=NOW, opts=o, sleep=lambda s: None)
    mac = next(a for a in env['platforms'][0]['accounts'] if a['handle'] == 'MacTalk')
    assert (mac['status'], mac['error']) == ('not_configured', 'wechat_weread_qr')


@pytest.mark.skipif(os.getuid() == 0, reason='root can enter any folder')
def test_status_with_unenterable_folder_reports_no_session(locked, capsys):
    assert weread.main(['status', '--session', str(locked / 'weread-session.json')]) == 1
    out = json.loads(capsys.readouterr().out)
    assert out['session'] is False


# ---------- weread status ----------

def status_with(folder, monkeypatch, capsys, curl):
    session = folder / 'weread-session.json'
    weread.save_session('1', 'k', session)
    real = weread.http_json
    monkeypatch.setattr(weread, 'http_json', lambda url, session=None, timeout=25: real(url, session, timeout, run=curl))
    code = weread.main(['status', '--session', str(session)])
    return code, json.loads(capsys.readouterr().out)


@pytest.mark.parametrize('code,location,body', [('200', '', '{"errCode": -2013, "errMsg": "x"}'),
                                                ('200', '', '{"errcode": -1}'),
                                                ('200', '', '{}'),
                                                ('200', '', '{"userVid": 2, "name": "someone else"}'),
                                                ('200', '', '{"data": {"errcode": -2041}}'),
                                                ('401', '', '{"userVid": 1}'),
                                                ('500', '', '{"userVid": 1}'),
                                                ('302', 'https://weread.qq.com/b', '{"userVid": 1}')])
def test_status_reports_invalid_for_api_errors(folder, monkeypatch, capsys, code, location, body):
    url = 'https://weread.qq.com/api/userInfo?userVid=1'
    rc, out = status_with(folder, monkeypatch, capsys, FakeCurl({url: (code, location, body)}))
    assert rc == 1 and out['session'] is True and out['valid'] is False


def test_status_valid_only_when_user_confirmed(folder, monkeypatch, capsys):
    url = 'https://weread.qq.com/api/userInfo?userVid=1'
    rc, out = status_with(folder, monkeypatch, capsys, FakeCurl({url: ('200', '', '{"userVid": 1, "name": "me"}')}))
    assert rc == 0 and out['valid'] is True


# ---------- weibo save-cookie ----------

@pytest.fixture
def home(tmp_path, monkeypatch):
    """A fake account home (as pwd would report it); the fixed cookie path lives under it."""
    path = tmp_path.resolve() / 'home'
    (path / '.config' / 'rebang').mkdir(parents=True, mode=0o700)
    for p in (path, path / '.config', path / '.config' / 'rebang'):
        p.chmod(0o700)
    monkeypatch.setattr(private_file, 'account_home', lambda: str(path))
    monkeypatch.setattr(private_file, 'account_problem', lambda: None)
    return path


def test_save_cookie_writes_owner_only_and_prints_no_contents(home, capsys):
    cookie = home / '.config' / 'rebang' / 'weibo-cookie.txt'
    put(cookie, 'OLD', 0o644)                         # an existing loose file is replaced, not truncated in place
    old_inode = cookie.stat().st_ino
    assert weibo.main(['save-cookie'], stdin=io.StringIO('Cookie: ' + SECRET + '\n')) == 0
    out = capsys.readouterr().out
    assert SECRET not in out and json.loads(out) == {'saved': True, 'cookie_file': str(cookie)}
    assert oct(cookie.stat().st_mode & 0o777) == '0o600' and cookie.stat().st_ino != old_inode
    assert weibo.read_cookie(cookie) == SECRET
    assert weibo.main(['check']) == 0
    assert json.loads(capsys.readouterr().out) == {'cookie_file': str(cookie), 'usable': True}


def test_save_cookie_and_check_ignore_the_environment_override(home, tmp_path, monkeypatch, capsys):
    elsewhere = tmp_path.resolve() / 'elsewhere'
    elsewhere.mkdir(mode=0o700)
    elsewhere.chmod(0o700)
    other = elsewhere / 'weibo-cookie.txt'
    monkeypatch.setenv('REBANG_WEIBO_COOKIE', str(other))
    monkeypatch.setenv('HOME', str(elsewhere))
    monkeypatch.setattr(weibo, 'DEFAULT_COOKIE', other)   # as if imported with the variable set
    assert weibo.main(['save-cookie'], stdin=io.StringIO(SECRET)) == 0
    fixed = home / '.config' / 'rebang' / 'weibo-cookie.txt'
    assert json.loads(capsys.readouterr().out)['cookie_file'] == str(fixed)
    assert weibo.read_cookie(fixed) == SECRET and not other.exists()
    put(other, SECRET)                                  # a usable file at the override does not count
    fixed.unlink()
    assert weibo.main(['check']) == 1
    assert json.loads(capsys.readouterr().out) == {'cookie_file': str(fixed), 'usable': False}
    with pytest.raises(SystemExit):                     # no way to point it elsewhere
        weibo.main(['save-cookie', '--cookie-file', str(other)], stdin=io.StringIO(SECRET))


@pytest.mark.parametrize('size', [private_file.MAX_BYTES, private_file.MAX_BYTES + 1, private_file.MAX_BYTES * 3])
def test_oversized_cookie_does_not_touch_the_old_file(home, capsys, size):
    cookie = home / '.config' / 'rebang' / 'weibo-cookie.txt'
    put(cookie, SECRET)
    before = (cookie.stat().st_ino, cookie.read_text())
    assert weibo.main(['save-cookie'], stdin=io.StringIO('a' * size)) == 1   # MAX_BYTES + newline is too big too
    assert json.loads(capsys.readouterr().out)['error'] == 'too_large'
    assert (cookie.stat().st_ino, cookie.read_text()) == before
    assert sorted(p.name for p in cookie.parent.iterdir()) == ['weibo-cookie.txt']


def test_oversized_multibyte_cookie_is_counted_in_utf8_bytes(home, capsys):
    cookie = home / '.config' / 'rebang' / 'weibo-cookie.txt'
    put(cookie, SECRET)
    value = '饼' * (private_file.MAX_BYTES // 3 + 1)          # fewer characters than MAX_BYTES, more bytes
    assert len(value) < private_file.MAX_BYTES
    assert weibo.main(['save-cookie'], stdin=io.StringIO(value)) == 1
    assert json.loads(capsys.readouterr().out)['error'] == 'too_large'
    assert cookie.read_text() == SECRET


def test_cookie_just_under_the_limit_is_saved(home, capsys):
    value = 'a' * (private_file.MAX_BYTES - 1)                # plus the newline = exactly MAX_BYTES
    assert weibo.main(['save-cookie'], stdin=io.StringIO(value)) == 0
    assert weibo.read_cookie(home / '.config' / 'rebang' / 'weibo-cookie.txt') == value


def test_write_private_refuses_oversized_before_creating_folders(tmp_path):
    target = tmp_path.resolve() / 'new' / 'deeper' / 'c.txt'
    with pytest.raises(private_file.PrivateFileError) as exc:
        private_file.write_private(target, 'x' * (private_file.MAX_BYTES + 1))
    assert exc.value.code == 'too_large' and not (tmp_path / 'new').exists()


def test_save_cookie_reads_bytes_from_a_binary_stdin(home, capsys):
    class Stdin:
        buffer = io.BytesIO(b'a' * (private_file.MAX_BYTES * 4))
    assert weibo.main(['save-cookie'], stdin=Stdin()) == 1
    assert Stdin.buffer.tell() == private_file.MAX_BYTES + 1   # never reads more than the limit + 1


def test_save_cookie_refuses_symlinked_folder_root_and_empty_input(home, folder, tmp_path, monkeypatch, capsys):
    rebang_dir = home / '.config' / 'rebang'
    rebang_dir.rmdir()
    rebang_dir.symlink_to(folder)
    assert weibo.main(['save-cookie'], stdin=io.StringIO(SECRET)) == 1
    rebang_dir.unlink()
    rebang_dir.mkdir(mode=0o700)
    assert weibo.main(['save-cookie'], stdin=io.StringIO('\n')) == 1
    assert not list(folder.iterdir()) and not list(rebang_dir.iterdir())
    monkeypatch.undo()
    monkeypatch.setattr(private_file.os, 'getuid', lambda: 0)
    assert private_file.account_problem() == 'run_as_root'
    monkeypatch.undo()
    assert private_file.account_problem(str(tmp_path / 'missing')) == 'no_checkout'
    assert SECRET not in capsys.readouterr().out


# ---------- Blocker 1: explicit empty env disables credentials without fallback ----------

def test_empty_env_disables_credentials_in_bloggers_cli(home, tmp_path, monkeypatch):
    from rebang.bloggers import __main__ as cli
    cookie = home / '.config' / 'rebang' / 'weibo-cookie.txt'
    session = home / '.config' / 'rebang' / 'weread-session.json'
    put(cookie, SECRET)
    weread.save_session('1', 'k', session)
    monkeypatch.setenv('REBANG_WEIBO_COOKIE', '')
    monkeypatch.setenv('REBANG_WEREAD_SESSION', '')
    monkeypatch.setattr(weibo, 'DEFAULT_COOKIE', cookie)
    monkeypatch.setattr(weread, 'DEFAULT_SESSION', session)
    seen = {}

    def fake_run(platforms, previous=None, opts=None):
        seen['weibo'] = opts.weibo_cookie_file
        seen['weread'] = opts.weread_session
        return {'schema': 'rebang.items/1', 'producer': 'bloggers', 'generated_at': '2026-11-25T00:00:00+08:00',
                'platforms': [], 'items': []}

    monkeypatch.setattr(cli, 'run', fake_run)
    out = tmp_path / 'bloggers.json'
    assert cli.main(['--out', str(out), '--platform', 'weibo,wechat', '--translate-engine', 'none', '--no-media']) == 0
    assert seen == {'weibo': '', 'weread': ''}


# ---------- Blocker 2: save-cookie --pbpaste fails before touching existing cookie ----------

def test_save_cookie_pbpaste_failure_after_partial_output_preserves_old_cookie(home, monkeypatch, capsys):
    cookie = home / '.config' / 'rebang' / 'weibo-cookie.txt'
    put(cookie, SECRET)
    before = (cookie.stat().st_ino, cookie.read_text())

    class FailingProc:
        def __init__(self, *args, **kwargs):
            self.stdout = io.BytesIO(b'SUB=partial-new-cookie\n')

        def wait(self, timeout=None):
            return 1

        def kill(self):
            pass

    monkeypatch.setattr(weibo.subprocess, 'Popen', FailingProc)
    assert weibo.main(['save-cookie', '--pbpaste']) == 1
    out = json.loads(capsys.readouterr().out)
    assert out == {'saved': False, 'error': 'clipboard_failed'}
    assert (cookie.stat().st_ino, cookie.read_text()) == before


def test_save_cookie_pbpaste_oversized_kills_and_preserves_old_cookie(home, monkeypatch, capsys):
    cookie = home / '.config' / 'rebang' / 'weibo-cookie.txt'
    put(cookie, SECRET)
    before = (cookie.stat().st_ino, cookie.read_text())
    killed = []

    class HugeProc:
        def __init__(self, *args, **kwargs):
            self.stdout = io.BytesIO(b'x' * (private_file.MAX_BYTES * 2))

        def kill(self):
            killed.append(True)

        def wait(self, timeout=None):
            return -9

    monkeypatch.setattr(weibo.subprocess, 'Popen', HugeProc)
    assert weibo.main(['save-cookie', '--pbpaste']) == 1
    assert json.loads(capsys.readouterr().out) == {'saved': False, 'error': 'too_large'}
    assert killed == [True]
    assert (cookie.stat().st_ino, cookie.read_text()) == before


def test_save_cookie_pbpaste_success_saves_owner_only(home, monkeypatch, capsys):
    cookie = home / '.config' / 'rebang' / 'weibo-cookie.txt'

    class OkProc:
        def __init__(self, *args, **kwargs):
            self.stdout = io.BytesIO(('Cookie: ' + SECRET + '\n').encode('utf-8'))

        def wait(self, timeout=None):
            return 0

        def kill(self):
            pass

    monkeypatch.setattr(weibo.subprocess, 'Popen', OkProc)
    assert weibo.main(['save-cookie', '--pbpaste']) == 0
    out = capsys.readouterr().out
    assert SECRET not in out and json.loads(out) == {'saved': True, 'cookie_file': str(cookie)}
    assert weibo.read_cookie(cookie) == SECRET


# ---------- Blocker 3: WeRead HTTP 200 JSON errors, nested data.errCode, numeric strings ----------

@pytest.mark.parametrize('body,expected', [
    ('{"errCode": -2010}', 'login_expired'),
    ('{"errCode": "-2012"}', 'login_expired'),
    ('{"data": {"errCode": -2010}}', 'login_expired'),
    ('{"data": {"errCode": "-2012"}}', 'login_expired'),
    ('{"errCode": 0, "data": {"errCode": -2013}}', 'api_-2013'),
    ('{"errCode": "-2013"}', 'api_-2013'),
    ('{"errCode": "' + '9' * 5000 + '"}', 'api_error'),
    ('{"errCode": false}', 'api_error'),
    ('{"errCode": true}', 'api_error'),
])
def test_weread_http_json_and_text_share_api_error_detection(body, expected):
    curl = FakeCurl({'https://weread.qq.com/a': ('200', '', body)})
    for call in (weread.http_json, weread.http_text):
        with pytest.raises(weread.WereadError) as exc:
            call('https://weread.qq.com/a', SESSION, run=curl)
        assert exc.value.code == expected


def test_weread_numeric_string_zero_is_accepted():
    curl = FakeCurl({'https://weread.qq.com/a': ('200', '', '{"ok": 1, "errCode": "0"}')})
    assert weread.http_json('https://weread.qq.com/a', SESSION, run=curl) == {'ok': 1, 'errCode': '0'}
    assert weread.http_text('https://weread.qq.com/a', SESSION, run=curl) == '{"ok": 1, "errCode": "0"}'


def test_save_cookie_pbpaste_stalled_stdout_times_out_and_preserves_old_cookie(home):
    import time
    cookie = home / '.config' / 'rebang' / 'weibo-cookie.txt'
    put(cookie, SECRET)
    before = (cookie.stat().st_ino, cookie.read_text())

    def slow_popen(cmd, **kwargs):
        return subprocess.Popen([sys.executable, '-c',
                                 'import sys, time; sys.stdout.write("SUB=a"); sys.stdout.flush(); time.sleep(5)'],
                                **kwargs)

    t0 = time.monotonic()
    with pytest.raises(weibo.WeiboError) as exc:
        weibo.read_pbpaste(popen=slow_popen, timeout=0.1)
    assert exc.value.code == 'clipboard_failed'
    assert time.monotonic() - t0 < 2.0
    assert (cookie.stat().st_ino, cookie.read_text()) == before


# ---------- Blocker 4: weread status handles non-UTF-8 and deeply nested JSON without traceback ----------

def test_weread_status_handles_non_utf8_response_even_under_latin1_locale(folder, monkeypatch, capsys):
    def non_utf8_run(cmd, **kwargs):
        assert kwargs.get('encoding') == 'utf-8' and kwargs.get('errors') == 'strict'
        return _REAL_SUBPROCESS_RUN([sys.executable, '-c',
                                     'import sys; sys.stdout.buffer.write(b\'{"userVid": 1, "name": "\\xff"}\\n200 \')'],
                                    capture_output=True, text=True, encoding=kwargs['encoding'], errors=kwargs['errors'])

    rc, out = status_with(folder, monkeypatch, capsys, non_utf8_run)
    assert rc == 1 and out['session'] is True and out['valid'] is False and out['error'] == 'bad_encoding'


def test_weread_status_handles_deep_json_response(folder, monkeypatch, capsys):
    url = 'https://weread.qq.com/api/userInfo?userVid=1'
    real_loads = weread.json.loads

    def boom(text, *a, **k):
        if text == '{"deep": 1}':
            raise RecursionError('maximum recursion depth exceeded')
        return real_loads(text, *a, **k)

    monkeypatch.setattr(weread.json, 'loads', boom)
    rc, out = status_with(folder, monkeypatch, capsys, FakeCurl({url: ('200', '', '{"deep": 1}')}))
    assert rc == 1 and out['session'] is True and out['valid'] is False and out['error'] == 'http_200_not_json'


def test_weread_status_handles_non_utf8_and_deep_json_session_file(folder, monkeypatch, capsys):
    session = folder / 'weread-session.json'
    session.write_bytes(b'\xff\xfe\x00')
    session.chmod(0o600)
    assert weread.main(['status', '--session', str(session)]) == 1
    out = json.loads(capsys.readouterr().out)
    assert out['session'] is False

    session.write_text('{"deep": 1}')
    session.chmod(0o600)
    real_loads = weread.json.loads
    monkeypatch.setattr(weread.json, 'loads', lambda text, *a, **k: (_ for _ in ()).throw(RecursionError('deep'))
                        if text == '{"deep": 1}' else real_loads(text, *a, **k))
    assert weread.main(['status', '--session', str(session)]) == 1
    out = real_loads(capsys.readouterr().out)
    assert out['session'] is False and out['error'] == 'session_invalid'
