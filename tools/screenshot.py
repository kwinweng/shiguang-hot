#!/usr/bin/env python3
"""Screenshot a built page of site/: a full-page phone shot by default, split past 30000 px.

  python3 tools/screenshot.py                     # site/index.html, phone, light
  python3 tools/screenshot.py hot.html --dark     # another page, dark theme
  python3 tools/screenshot.py --desktop           # 1440 x 900 viewport only
  python3 tools/screenshot.py --build             # run pipeline.py first (fetches Telegram)

Files go to shots/ (ignored by git). CHROMIUM_PATH points Playwright at a browser binary when
its own download is not installed.
"""
import argparse, math, os, subprocess, sys
from datetime import datetime
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
MAX = 30000

parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
parser.add_argument('page', nargs='?', default='index.html', help='path under site/')
parser.add_argument('--desktop', action='store_true', help='1440 x 900, viewport only')
parser.add_argument('--dark', action='store_true', help='dark colour scheme')
parser.add_argument('--build', action='store_true', help='run pipeline.py before the shot')
parser.add_argument('--out', default=str(ROOT / 'shots'), help='output folder')
args = parser.parse_args()

if args.build:
    subprocess.run([sys.executable, str(ROOT / 'pipeline.py')], cwd=ROOT, check=True)
page_file = ROOT / 'site' / args.page
if not page_file.is_file():
    raise SystemExit(f'{page_file} 不存在，先运行 pipeline.py 或加 --build')
out = Path(args.out); out.mkdir(parents=True, exist_ok=True)
prefix = out / f'{"desktop" if args.desktop else "mobile"}-{Path(args.page).stem}-{datetime.now():%Y%m%d-%H%M%S}'

with sync_playwright() as p:
    browser = p.chromium.launch(**({'executable_path': os.environ['CHROMIUM_PATH']} if os.getenv('CHROMIUM_PATH') else {}))
    scheme = 'dark' if args.dark else 'light'
    if args.desktop:
        page = browser.new_page(viewport={'width': 1440, 'height': 900}, color_scheme=scheme)
    else:
        page = browser.new_page(viewport={'width': 390, 'height': 844}, device_scale_factor=2, is_mobile=True,
                                has_touch=True, color_scheme=scheme)
    page.goto(page_file.as_uri(), wait_until='networkidle')
    page.wait_for_timeout(1000)
    if args.desktop:
        page.screenshot(path=f'{prefix}.png'); print(f'{prefix}.png')
    else:
        height = page.evaluate('document.documentElement.scrollHeight')
        parts = max(1, math.ceil(height / MAX)); size = math.ceil(height / parts)
        for i in range(parts):
            name = f'{prefix}.png' if parts == 1 else f'{prefix}-{i + 1}.png'
            page.screenshot(path=name, full_page=True, clip={'x': 0, 'y': i * size, 'width': 390, 'height': min(size, height - i * size)})
            print(name)
    browser.close()
