"""底栏贴底验收（Playwright WebKit iPhone 模拟 + 桌面 Chromium），深色/浅色各一遍。

用法：python3 docs/rebang-v1/evidence/ios-tabbar/capture.py <站点根 URL> [前缀]
场景：
  safari-tab      iPhone 13 Safari 标签页（视口 390x664，屏幕 390x844）
  standalone-full 主屏幕 web app，视口 = 整屏 844，安全区 47/34
  standalone-ios26 主屏幕 web app，iOS 26 的情况：视口只有 812（底下 32px 归系统，网页画不进去），安全区仍报 47/34
  desktop         桌面 Chromium 1280x800
每个场景断言：底栏下沿 = 视口高度（贴底）。standalone-ios26 另断言底栏不再「垫两次」安全区（高度 ≤ 58+2+1），
并把截图贴到 844 高的画布上、底部 32px 用 html 背景色补齐，模拟真机看到的样子（<前缀><场景>-<主题>-device.png）。
模拟器里 env(safe-area-inset-*) 恒为 0：用 window.__rebangTestInsets 和一段 :root 样式模拟真机安全区。
真机 standalone 的视口几何模拟器复现不了，这里验的是逻辑；真机请开 https://news.kwinweng.com/?diag=1 看实测数。
"""
import json
import sys
from pathlib import Path

from PIL import Image
from playwright.sync_api import sync_playwright

BASE = sys.argv[1].rstrip('/') + '/'
PREFIX = sys.argv[2] if len(sys.argv) > 2 else ''
OUT = Path(__file__).resolve().parent
TAB = 58
checks = []
INSET = """
window.__rebangTestInsets = {top: 47, bottom: 34};
Object.defineProperty(navigator, 'standalone', {get: () => %s});
document.addEventListener('DOMContentLoaded', () => { const s = document.createElement('style');
  s.textContent = ':root{--safe-top:47px!important}' + %s; document.head.appendChild(s); });
"""


def check(name, ok, **detail):
    checks.append({'check': name, 'ok': bool(ok), **detail})
    print(('PASS ' if ok else 'FAIL ') + name, json.dumps(detail, ensure_ascii=False)[:260])


def measure(page):
    page.wait_for_selector('.tabbar button')
    page.wait_for_timeout(500)
    return page.evaluate("""() => { const r = document.querySelector('.tabbar').getBoundingClientRect();
      return {bottom: r.bottom, height: r.height, innerH: innerHeight, cls: document.documentElement.className,
              bg: getComputedStyle(document.documentElement).backgroundColor, bar: getComputedStyle(document.querySelector('.tabbar')).backgroundColor,
              vp: window.__rebangViewport || null}; }""")


def run(p, name, scheme, engine, ctx_kw, standalone=None, device_h=None):
    browser = (p.webkit if engine == 'webkit' else p.chromium).launch()
    ctx = browser.new_context(color_scheme=scheme, **ctx_kw)
    if standalone is not None:
        # 安全区底部：标签页里由 Safari 工具栏占着（0）；standalone 里系统报 34
        ctx.add_init_script(INSET % ('true' if standalone else 'false', "':root{--safe-bot:34px}'" if standalone else "''"))
    page = ctx.new_page()
    page.goto(BASE, wait_until='networkidle')
    m = measure(page)
    shot = OUT / f'{PREFIX}{name}-{scheme}.png'
    page.screenshot(path=str(shot))
    check(f'{name}/{scheme}：底栏下沿 = 视口高度', abs(m['bottom'] - m['innerH']) <= 1, **{k: m[k] for k in ('bottom', 'innerH', 'height')})
    if device_h:
        check(f'{name}/{scheme}：不再垫两次安全区（底栏高 ≤ {TAB + 3}）', m['height'] <= TAB + 3, height=m['height'], vp=m['vp'])
        img = Image.open(shot)
        w, h = img.size
        scale = w / ctx_kw['viewport']['width']
        canvas = Image.new('RGB', (w, int(device_h * scale)), tuple(int(x) for x in m['bg'][m['bg'].index('(') + 1:-1].split(',')[:3]))
        canvas.paste(img, (0, 0))
        canvas.save(OUT / f'{PREFIX}{name}-{scheme}-device.png')
    browser.close()
    return m


def main():
    iphone = {'viewport': {'width': 390, 'height': 664}, 'screen': {'width': 390, 'height': 844}, 'device_scale_factor': 2,
              'is_mobile': True, 'has_touch': True,
              'user_agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 26_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) CriOS/142.0 Mobile/15E148 Safari/604.1'}
    with sync_playwright() as p:
        for scheme in ('dark', 'light'):
            run(p, 'safari-tab', scheme, 'webkit', iphone, standalone=False)
            run(p, 'standalone-full', scheme, 'webkit', {**iphone, 'viewport': {'width': 390, 'height': 844}}, standalone=True)
            run(p, 'standalone-ios26', scheme, 'webkit', {**iphone, 'viewport': {'width': 390, 'height': 812}}, standalone=True, device_h=844)
            run(p, 'desktop', scheme, 'chromium', {'viewport': {'width': 1280, 'height': 800}})
    (OUT / f'{PREFIX}result.json').write_text(json.dumps({'base': BASE, 'checks': checks}, ensure_ascii=False, indent=1))
    fails = [c for c in checks if not c['ok']]
    print(f'{len(checks) - len(fails)}/{len(checks)} passed')
    return 1 if fails else 0


if __name__ == '__main__':
    sys.exit(main())
