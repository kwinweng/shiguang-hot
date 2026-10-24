"""Capture local 393x852 acceptance evidence using the existing optional Playwright."""
import json
import mimetypes
import os
from pathlib import Path
from urllib.parse import unquote, urlsplit

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / 'docs/qa/two-modules-20261024'


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    checks = []
    messages = json.loads((ROOT / 'site/data/live.json').read_text())['messages']
    with sync_playwright() as p:
        executable = os.getenv('NEWS_TEST_CHROME') or next((s for s in
            ['/opt/ungoogled-chromium/chrome', '/usr/bin/google-chrome'] if Path(s).is_file()), None)
        browser = p.chromium.launch(executable_path=executable, headless=True, args=['--no-sandbox'])
        context = browser.new_context(viewport=dict(width=393, height=852))
        page = context.new_page()
        errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))
        def serve(route):
            url = urlsplit(route.request.url)
            if url.netloc != 'local.test':
                route.abort()
                return
            path = ROOT / 'site' / (unquote(url.path).lstrip('/') or 'index.html')
            route.fulfill(status=200 if path.is_file() else 404,
                          body=path.read_bytes() if path.is_file() else b'missing',
                          content_type=mimetypes.guess_type(path)[0] or 'application/octet-stream')
        page.route('**/*', serve)
        for theme in ('light', 'dark'):
            page.emulate_media(color_scheme=theme, reduced_motion='reduce')
            for name, route in [('live', 'feed'), ('focus', 'focus'), ('review', 'review'),
                                ('play', 'explore/play'), ('kan', 'explore/kan'), ('buy', 'explore/buy'),
                                ('me', 'me'), ('favorites', 'favorites'), ('settings', 'settings'),
                                ('detail-noimg', 'message/' + next(r['id'] for r in messages if not r.get('image'))),
                                ('about', 'about'), ('404', '404')]:
                page.goto('https://local.test/index.html#' + route)
                page.wait_for_selector('#news:not([aria-busy])')
                page.screenshot(path=str(OUT / f'{name}-{theme}.png'))
                checks.append(dict(page=name, theme=theme, **page.evaluate("""() => ({
                    noOverflow:document.documentElement.scrollWidth<=innerWidth,
                    tabs:[...document.querySelectorAll('.news-nav a')].map(a=>a.textContent),
                    barHeight:document.querySelector('.news-nav').offsetHeight,
                    rowTitleWeight:document.querySelector('.row b')?getComputedStyle(document.querySelector('.row b')).fontWeight:null
                })""")))
        assert not errors, errors
        assert all(c['noOverflow'] and c['barHeight'] == 70 and c['tabs'] == ['资讯', '探索', '我的'] for c in checks)
        (OUT / 'checks.json').write_text(json.dumps(dict(viewport=[393,852], errors=errors, checks=checks), ensure_ascii=False, indent=2) + '\n')
        browser.close()
    print(f'{len(checks)} screenshots; no overflow or page errors; output: {OUT.relative_to(ROOT)}')


if __name__ == '__main__':
    main()
