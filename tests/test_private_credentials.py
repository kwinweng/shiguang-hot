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
- WeRead redirects: curl never auto-follows; same https origin followed with the Cookie; cross-origin
  and https→http not followed;
- `weibo save-cookie`: 0600 atomic write, no contents printed, refuses root and symlinked folders.
"""
from datetime import datetime, timezone
import http.server
import io
import json
import os
from pathlib import Path
import subprocess
import threading
import urllib.request

import pytest

from rebang import private_file
from rebang.bloggers import run as runmod
from rebang.bloggers import weibo, weread

NOW = datetime(2026, 11, 25, 12, 0, tzinfo=timezone.utc)


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


def test_weread_follows_same_origin_redirect_with_cookie():
    curl = FakeCurl({'https://weread.qq.com/a': ('302', 'https://weread.qq.com/b', ''),
                     'https://weread.qq.com/b': ('200', '', '{"ok": 1}')})
    assert weread.http_json('https://weread.qq.com/a', SESSION, run=curl) == {'ok': 1}
    assert curl.calls == [('https://weread.qq.com/a', True), ('https://weread.qq.com/b', True)]


@pytest.mark.parametrize('location', ['https://evil.example/b', 'http://weread.qq.com/b', 'https://weread.qq.com:444/b'])
def test_weread_does_not_follow_cross_origin_or_downgrade(location):
    curl = FakeCurl({'https://weread.qq.com/a': ('302', location, ''),
                     location: ('200', '', '{"stolen": true}')})
    for call in (weread.http_json, weread.http_text):
        with pytest.raises(weread.WereadError) as exc:
            call('https://weread.qq.com/a', SESSION, run=curl)
        assert exc.value.code == 'redirect_blocked'
    assert {url for url, _ in curl.calls} == {'https://weread.qq.com/a'}


def test_weread_redirect_loop_stops():
    curl = FakeCurl({'https://weread.qq.com/a': ('302', '/a', '')})
    with pytest.raises(weread.WereadError) as exc:
        weread.http_json('https://weread.qq.com/a', SESSION, run=curl)
    assert exc.value.code == 'too_many_redirects'


# ---------- weibo save-cookie ----------

def test_save_cookie_writes_owner_only_and_prints_no_contents(folder, monkeypatch, capsys):
    monkeypatch.setattr(private_file, 'account_problem', lambda: None)
    cookie = folder / 'weibo-cookie.txt'
    put(cookie, 'OLD', 0o644)                         # an existing loose file is replaced, not truncated in place
    old_inode = cookie.stat().st_ino
    assert weibo.main(['save-cookie', '--cookie-file', str(cookie)], stdin=io.StringIO('Cookie: ' + SECRET + '\n')) == 0
    out = capsys.readouterr().out
    assert SECRET not in out and json.loads(out)['saved'] is True
    assert oct(cookie.stat().st_mode & 0o777) == '0o600' and cookie.stat().st_ino != old_inode
    assert weibo.read_cookie(cookie) == SECRET
    assert weibo.main(['check', '--cookie-file', str(cookie)]) == 0


def test_save_cookie_refuses_symlinked_folder_root_and_empty_input(folder, tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(private_file, 'account_problem', lambda: None)
    link = tmp_path.resolve() / 'link'
    link.symlink_to(folder)
    assert weibo.main(['save-cookie', '--cookie-file', str(link / 'weibo-cookie.txt')], stdin=io.StringIO(SECRET)) == 1
    assert weibo.main(['save-cookie', '--cookie-file', str(folder / 'c.txt')], stdin=io.StringIO('\n')) == 1
    assert not list(folder.iterdir())
    monkeypatch.undo()
    monkeypatch.setattr(private_file.os, 'getuid', lambda: 0)
    assert private_file.account_problem() == 'run_as_root'
    monkeypatch.undo()
    assert private_file.account_problem(str(tmp_path / 'missing')) == 'no_checkout'
    assert SECRET not in capsys.readouterr().out
