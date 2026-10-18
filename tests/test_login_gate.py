import http.client, sys, tempfile, threading, time, unittest, unittest.mock
from pathlib import Path
from urllib.parse import urlencode

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'tools'))
import login_gate as gate


class LoginGateTests(unittest.TestCase):
    def setUp(self):
        quiet = unittest.mock.patch.object(gate.Handler, 'log_message', lambda *a: None); quiet.start(); self.addCleanup(quiet.stop)
        fast = unittest.mock.patch.object(gate, 'ITERATIONS', 1000); fast.start(); self.addCleanup(fast.stop)
        self.folder = Path(tempfile.mkdtemp())
        gate.set_password(self.folder, 'kwin', 'correct horse')
        self.server = gate.make_server(self.folder, port=0, days=180)
        self.port = self.server.server_address[1]
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)

    def request(self, method, path, body=None, headers=None):
        conn = http.client.HTTPConnection('127.0.0.1', self.port, timeout=10)
        conn.request(method, path, body, headers or {})
        r = conn.getresponse(); r.read(); conn.close()
        return r

    def login(self, password='correct horse', next_='/mail/'):
        body = urlencode({'user': 'kwin', 'password': password, 'next': next_})
        return self.request('POST', '/__login/', body, {'Content-Type': 'application/x-www-form-urlencoded'})

    def cookie_of(self, response):
        return response.getheader('Set-Cookie').split(';')[0]

    def test_login_sets_a_180_day_cookie_and_check_accepts_it(self):
        self.assertEqual(self.request('GET', '/__login/check').status, 401)
        r = self.login()
        self.assertEqual(r.status, 303)
        self.assertEqual(r.getheader('Location'), '/mail/')
        header = r.getheader('Set-Cookie')
        for part in ('Max-Age=15552000', 'HttpOnly', 'SameSite=Lax', 'Path=/'):
            self.assertIn(part, header)
        self.assertEqual(self.request('GET', '/__login/check', headers={'Cookie': self.cookie_of(r)}).status, 204)

    def test_wrong_password_tampered_or_expired_cookie_are_refused(self):
        self.assertEqual(self.login('wrong password').status, 401)
        cookie = self.cookie_of(self.login())
        tampered = cookie[:-2] + ('A' if cookie[-2] != 'A' else 'B') + cookie[-1]
        self.assertEqual(self.request('GET', '/__login/check', headers={'Cookie': tampered}).status, 401)
        key, users = gate.secret_key(self.folder), gate.load_users(self.folder)
        old = gate.make_token(key, 'kwin', users['kwin'], 180, now=time.time() - 181 * 86400)
        self.assertIsNone(gate.read_token(key, old, users))
        self.assertEqual(self.request('GET', '/__login/check', headers={'Cookie': f'{gate.COOKIE}={old}'}).status, 401)

    def test_changing_the_password_signs_every_device_out(self):
        cookie = self.cookie_of(self.login())
        gate.set_password(self.folder, 'kwin', 'a new password')
        self.assertEqual(self.request('GET', '/__login/check', headers={'Cookie': cookie}).status, 401)

    def test_cookie_renews_after_a_day(self):
        key, users = gate.secret_key(self.folder), gate.load_users(self.folder)
        day_old = gate.make_token(key, 'kwin', users['kwin'], 180, now=time.time() - 2 * 86400)
        r = self.request('GET', '/__login/check', headers={'Cookie': f'{gate.COOKIE}={day_old}'})
        self.assertEqual(r.status, 204)
        self.assertIn('Max-Age=15552000', r.getheader('Set-Cookie'))
        fresh = self.cookie_of(self.login())
        self.assertIsNone(self.request('GET', '/__login/check', headers={'Cookie': fresh}).getheader('Set-Cookie'))

    def test_next_stays_on_this_site(self):
        for target in ('https://evil.example/', '//evil.example/', '/\\evil.example', ''):
            self.assertEqual(gate.safe_next(target), '/')
        self.assertEqual(self.login(next_='//evil.example/').getheader('Location'), '/')
        self.assertEqual(gate.safe_next('/archive/2026-10-17.html?x=1&y=2'), '/archive/2026-10-17.html?x=1&y=2')

    def test_caddy_forward_auth_is_sent_to_the_login_page(self):
        r = self.request('GET', '/__login/check', headers={'X-Forwarded-Uri': '/mail/2026-10-17.html'})
        self.assertEqual(r.status, 302)
        self.assertEqual(r.getheader('Location'), '/__login/?next=/mail/2026-10-17.html')

    def test_login_page_and_repeated_failures(self):
        page = self.request('GET', '/__login/?next=/mail/')
        self.assertEqual(page.status, 200)
        self.assertEqual(page.getheader('Cache-Control'), 'no-store')
        for _ in range(gate.MAX_FAILURES):
            self.server.RequestHandlerClass.gate.failed('127.0.0.1', time.time())
        self.assertEqual(self.login().status, 429)

    def test_secrets_are_owner_only(self):
        for name in ('users.json', 'secret.key'):
            self.assertEqual((self.folder / name).stat().st_mode & 0o777, 0o600, name)
        self.assertNotIn('correct horse', (self.folder / 'users.json').read_text())


if __name__ == '__main__':
    unittest.main()
