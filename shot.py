from playwright.sync_api import sync_playwright
import sys
with sync_playwright() as p:
  b=p.chromium.launch()
  for scheme,url,out in [("light","site/index.html","screenshot.png"),("light","site/archive/2026-10-14.html","/tmp/a.png"),("dark","site/archive/2026-10-14.html","/tmp/d.png")]:
    pg=b.new_page(viewport={"width":1440,"height":900},color_scheme=scheme)
    pg.goto("file:///workspace/tg-site/"+url); pg.screenshot(path=out)
