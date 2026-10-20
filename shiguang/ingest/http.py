"""One public HTTP attempt, with bounded curl time and safe, structured errors."""
import re
import subprocess
import tempfile
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime


class FetchFailure(Exception):
    def __init__(self, code, retry_at=None):
        super().__init__(code)  # Never include response bodies, URLs or curl stderr in diagnostics.
        self.code = code
        self.retry_at = retry_at


@dataclass
class Response:
    status: int
    headers: dict
    body: bytes


def request(url, headers=None):
    with tempfile.TemporaryFile() as header_file:
        args = ['curl', '-q', '-sS', '-L', '--max-redirs', '5', '--max-time', '25',
                '--proto', '=http,https', '--proto-redir', '=http,https',
                '-A', 'Mozilla/5.0', '-D', '/dev/fd/' + str(header_file.fileno())]
        for name, value in (headers or {}).items():
            if '\r' in value or '\n' in value:
                raise FetchFailure('invalid_validator')
            args.extend(['-H', name + ': ' + value])
        try:
            result = subprocess.run(args + [url], capture_output=True, pass_fds=(header_file.fileno(),))
        except OSError:
            raise FetchFailure('network') from None
        if result.returncode:
            raise FetchFailure('network')
        header_file.seek(0)
        blocks = re.split(rb'\r?\n\r?\n', header_file.read())
    parsed = None
    for block in blocks:
        lines = block.splitlines()
        if not lines or not re.match(rb'HTTP/\S+ \d{3}', lines[0]):
            continue
        status = int(lines[0].split()[1])
        fields = {}
        for line in lines[1:]:
            if b':' in line:
                name, value = line.split(b':', 1)
                fields[name.decode('latin1').lower()] = value.decode('latin1').strip()
        parsed = Response(status, fields, result.stdout)
    if parsed is None:
        raise FetchFailure('invalid_http')
    return parsed


def check(response, now):
    if response.status in (401, 403):
        raise FetchFailure('blocked')
    if response.status == 429:
        value = response.headers.get('retry-after', '')
        try:
            retry = now + timedelta(seconds=int(value)) if value.isdigit() else parsedate_to_datetime(value)
            if retry.tzinfo is None:
                retry = retry.replace(tzinfo=timezone.utc)
        except (ValueError, TypeError, OverflowError):
            retry = now + timedelta(hours=1)
        raise FetchFailure('rate_limited', retry)
    if response.status >= 500:
        raise FetchFailure('http_5xx')
    if response.status not in (200, 304):
        raise FetchFailure('http_status')
    # Inspect HTML challenge/login markers, not ordinary words inside news/feed content.
    if (response.status == 200 and
            re.search(rb'<(?:html|!doctype html)\b', response.body[:1024], re.I) and
            re.search(rb'<title[^>]*>[^<]*(?:captcha|sign in|log in|access denied)|'
                      rb'cf-chl-|g-recaptcha|id=["\x27]login_form|type=["\x27]password', response.body, re.I)):
        raise FetchFailure('blocked')
