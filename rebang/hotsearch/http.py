"""热搜 HTTP：明确 UA、超时 ≤10s、不存 cookie。失败抛 ProviderError（短错误码）。"""
import json
import socket
import urllib.error
import urllib.request
from pathlib import Path

from rebang.contract import load_hotsearch

TIMEOUT = 10
UA = (
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
    'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36'
)
DEFAULT_HEADERS = {
    'User-Agent': UA,
    'Accept': 'application/json,text/plain,*/*;q=0.8',
    'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
}


class ProviderError(Exception):
    """一家适配器的失败。code 是写入信封的短错误码，如 timeout、http_403、bad_structure。"""

    def __init__(self, code):
        self.code = str(code)
        super().__init__(self.code)


class HttpResponse:
    def __init__(self, status, text):
        self.status = int(status)
        self.text = text or ''

    def json(self):
        try:
            return json.loads(self.text)
        except json.JSONDecodeError as exc:
            raise ProviderError('not_json') from exc


class LiveHttp:
    """每家每轮由适配器调用一次 get。不跟随写入 cookie。"""

    def get(self, url, timeout=TIMEOUT, headers=None):
        merged = {**DEFAULT_HEADERS, **(headers or {})}
        request = urllib.request.Request(url, headers=merged, method='GET')
        try:
            with urllib.request.urlopen(request, timeout=min(timeout, TIMEOUT)) as resp:
                return HttpResponse(getattr(resp, 'status', 200), _read_body(resp))
        except urllib.error.HTTPError as exc:
            body = ''
            try:
                body = exc.read().decode('utf-8', errors='replace')
            except Exception:
                body = ''
            return HttpResponse(exc.code, body)
        except (TimeoutError, socket.timeout) as exc:
            raise ProviderError('timeout') from exc
        except urllib.error.URLError as exc:
            reason = exc.reason
            if isinstance(reason, (TimeoutError, socket.timeout)):
                raise ProviderError('timeout') from exc
            raise ProviderError('network') from exc


class FixtureHttp:
    """把提供方 endpoint 映射到目录里的 <id>.json，供离线单测与 --fixtures 使用。"""

    def __init__(self, directory, overrides=None):
        self.directory = Path(directory)
        self.overrides = dict(overrides or {})
        self._by_url = {}
        for provider in load_hotsearch()['providers']:
            path = self.directory / f"{provider['id']}.json"
            if path.is_file():
                self._by_url[provider['endpoint']] = path

    def get(self, url, timeout=TIMEOUT, headers=None):
        if url in self.overrides:
            value = self.overrides[url]
            if isinstance(value, Exception):
                raise value
            return value
        path = self._by_url.get(url)
        if path is None or not path.is_file():
            raise ProviderError('missing_fixture')
        return HttpResponse(200, path.read_text(encoding='utf-8'))


def _read_body(resp):
    raw = resp.read()
    encoding = 'utf-8'
    ctype = resp.headers.get('Content-Type', '') if resp.headers else ''
    if 'charset=' in ctype.lower():
        encoding = ctype.split('charset=', 1)[1].split(';')[0].strip() or 'utf-8'
    return raw.decode(encoding, errors='replace')
