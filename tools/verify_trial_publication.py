#!/usr/bin/env python3
"""Capture offline public-build proof at 402×874, without collectors or external requests.

Run pipeline.py separately with NO_FETCH=1 and SITE_OUT pointing at a temporary directory.
Then pass that directory here. Remote covers intentionally fail to exercise text-card fallback.
"""
import argparse
import mimetypes
from pathlib import Path
from urllib.parse import unquote, urlsplit

from playwright.sync_api import sync_playwright


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--site', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    executable = next((p for p in ['/opt/ungoogled-chromium/chrome', '/usr/bin/google-chrome']
                       if Path(p).is_file()), None)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(executable_path=executable, headless=True,
            args=['--no-sandbox', '--disable-crash-reporter', '--disable-breakpad'])
        try:
            for theme in ['light', 'dark']:
                context = browser.new_context(viewport={'width': 402, 'height': 874},
                    device_scale_factor=2, color_scheme=theme, is_mobile=True, has_touch=True)
                errors = []
                page = context.new_page()
                page.on('pageerror', lambda error: errors.append(str(error)))
                def serve(route):
                    url = urlsplit(route.request.url)
                    path = (args.site / (unquote(url.path).lstrip('/') or 'index.html')).resolve()
                    if url.hostname == 'offline.test' and path.is_relative_to(args.site.resolve()) and path.is_file():
                        route.fulfill(body=path.read_bytes(), content_type=mimetypes.guess_type(path)[0] or 'application/octet-stream')
                    else:
                        route.fulfill(status=404, body='offline cover')
                page.route('**/*', serve)
                for path in ['play.html', 'buy.html', 'index.html']:
                    page.goto('https://offline.test/' + path)
                    page.wait_for_timeout(250)
                    assert not page.evaluate('document.documentElement.scrollWidth > innerWidth'), path
                    assert not errors, errors
                    if path == 'index.html':
                        assert page.locator('.trial-home').count() == 2
                        assert page.locator('.trial-home').nth(0).locator('article').count() == 5
                        assert page.locator('.trial-home').nth(1).locator('article').count() == 5
                    assert page.locator('.trial-card:visible').count(), path
                    page.screenshot(path=str(args.out / f'{Path(path).stem}-{theme}.png'))
                    print(f'{path} {theme}: no overflow, no JS errors, {page.locator(".trial-card:visible").count()} cards')
                page.set_viewport_size({'width': 1440, 'height': 900})
                page.goto('https://offline.test/play.html')
                assert not page.evaluate('document.documentElement.scrollWidth > innerWidth')
                context.close()
        finally:
            browser.close()


if __name__ == '__main__':
    main()
