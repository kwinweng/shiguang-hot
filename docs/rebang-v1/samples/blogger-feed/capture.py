# 博主信息流样页截图（只截样页，不连网、不跑采集）。用法见同目录 index.html 末尾。
import sys, pathlib
from playwright.sync_api import sync_playwright
d = pathlib.Path(sys.argv[1]).resolve()
base = (d / 'feed.html').as_uri()
shots = [
  ('a-feed-light', '?v=a', '', 'light', None),
  ('a-feed-scrolled-light', '?v=a', '', 'light', 'scroll'),
  ('a-profile-light', '?v=a', '#u=a1', 'light', None),
  ('a-longpress-light', '?v=a', '', 'light', 'menu'),
  ('b-feed-light', '?v=b', '', 'light', None),
  ('b-feed-scrolled-light', '?v=b', '', 'light', 'scroll'),
  ('b-profile-light', '?v=b', '#u=a1', 'light', None),
  ('a-feed-dark', '?v=a', '', 'dark', None),
  ('b-feed-dark', '?v=b', '', 'dark', None),
]
with sync_playwright() as p:
  br = p.chromium.launch()
  for name, qs, h, scheme, act in shots:
    ctx = br.new_context(viewport={'width': 390, 'height': 844}, device_scale_factor=2, color_scheme=scheme, is_mobile=True, has_touch=True)
    pg = ctx.new_page()
    errs = []
    pg.on('pageerror', lambda e: errs.append(str(e)))
    pg.goto(base + qs + h)
    pg.wait_for_timeout(300)
    if act == 'scroll':
      pg.evaluate("document.getElementById('scroller').scrollTop = document.querySelector('[data-id=p3]').offsetTop - 110")
    if act == 'menu':
      pg.evaluate("window.__openMenu('p1')")
    pg.wait_for_timeout(400)
    pg.screenshot(path=str(d / f'shot-{name}.png'))
    if errs: print(name, 'ERR', errs)
    ctx.close()
  br.close()
print('ok')
