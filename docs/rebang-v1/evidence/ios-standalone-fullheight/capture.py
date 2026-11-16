"""iOS 主屏幕 web app 底栏贴底验收（第二轮）：按阿欢 iPhone 17 Pro 真机几何模拟。深色/浅色各一遍。

用法：python3 capture.py <站点根 URL> <前缀 before-|after->
真机几何（WebKit bug 313800，iOS 26/27 standalone）：屏幕 402x874，innerHeight/100dvh 只有 812（少了状态栏 62），
安全区 62/34；网页其实铺满整屏，812 以下那 62px 照样画 html 背景。
场景：
  ios-standalone-812   CSS 视口 812（复现真机排版）。截图贴到 874 高画布、底部用 html 背景色补齐 = 真机看到的样子（*-device.png）。
                       断言（after）：外壳和底栏下沿 = 874（撑到整屏）、底栏 padding-bottom = 34。
  ios-standalone-paint 画布 874、innerHeight 报 812（真机「报矮、画满」）→ 截图看底栏是否贴到屏幕底、图标在 Home 条上方。
  ios-browser-tab      iOS Chrome 标签页 402x683（阿欢浏览器里实测 vv 683）：底栏下沿 = 683。
  android-standalone   Chromium Pixel 412x915 display-mode standalone：底栏下沿 = 视口。
  desktop              桌面 Chromium 1280x800：底栏下沿 = 800。
  diag（after）        长按左上角日期 1.1 秒 → 出诊断浮层并记在 localStorage；刷新仍在；再长按关闭。
模拟器里 env(safe-area-inset-*) 恒为 0：用 window.__rebangTestInsets + :root 变量模拟真机安全区。
"""
import json
import sys
from pathlib import Path

from PIL import Image
from playwright.sync_api import sync_playwright

BASE = sys.argv[1].rstrip('/') + '/'
PREFIX = sys.argv[2] if len(sys.argv) > 2 else ''
AFTER = PREFIX.startswith('after')
OUT = Path(__file__).resolve().parent
SCREEN_H, SHORT_H, TOP, BOT, TAB = 874, 812, 62, 34, 58
checks = []
UA = 'Mozilla/5.0 (iPhone; CPU iPhone OS 27_2 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) CriOS/143.0 Mobile/15E148 Safari/604.1'
IOS_STANDALONE = """
window.__rebangTestInsets = {top: %d, bottom: %d};
Object.defineProperty(navigator, 'standalone', {get: () => true});
const _mm = window.matchMedia.bind(window);
window.matchMedia = q => /display-mode:\\s*standalone/.test(q) ? {matches: true, media: q, addEventListener() {}, removeEventListener() {}} : _mm(q);
%s
document.addEventListener('DOMContentLoaded', () => { const s = document.createElement('style');
  s.textContent = ':root{--safe-top:%dpx!important;--safe-bot:%dpx}'; document.head.appendChild(s); });
""" 
IOS_TAB = "Object.defineProperty(navigator, 'standalone', {get: () => false});"


def check(name, ok, **detail):
    checks.append({'check': name, 'ok': bool(ok), **detail})
    print(('PASS ' if ok else 'FAIL ') + name, json.dumps(detail, ensure_ascii=False)[:300])


def measure(page):
    page.wait_for_selector('.tabbar button')
    page.wait_for_timeout(600)
    return page.evaluate("""() => { const bar = document.querySelector('.tabbar'), r = bar.getBoundingClientRect(), a = document.querySelector('#app').getBoundingClientRect();
      return {tabBottom: r.bottom, tabTop: r.top, tabH: r.height, padBot: getComputedStyle(bar).paddingBottom, appBottom: a.bottom,
              innerH: innerHeight, cls: document.documentElement.className, bg: getComputedStyle(document.documentElement).backgroundColor,
              geom: (window.__rebangViewport || {}).geom || null}; }""")


def rgb(css):
    return tuple(int(float(x)) for x in css[css.index('(') + 1:-1].split(',')[:3])


def ctx_for(p, engine, scheme, **kw):
    browser = (p.webkit if engine == 'webkit' else p.chromium).launch()
    return browser, browser.new_context(color_scheme=scheme, **kw)


def iphone(h):
    return dict(viewport={'width': 402, 'height': h}, screen={'width': 402, 'height': SCREEN_H}, device_scale_factor=3,
                is_mobile=True, has_touch=True, user_agent=UA)


def run(p, scheme):
    # 1) 真机排版：CSS 视口 812
    b, c = ctx_for(p, 'webkit', scheme, **iphone(SHORT_H))
    c.add_init_script(IOS_STANDALONE % (TOP, BOT, '', TOP, BOT))
    pg = c.new_page(); pg.goto(BASE, wait_until='networkidle'); m = measure(pg)
    shot = OUT / f'{PREFIX}ios-standalone-812-{scheme}.png'; pg.screenshot(path=str(shot))
    img = Image.open(shot); w, h = img.size
    canvas = Image.new('RGB', (w, SCREEN_H * 3), rgb(m['bg'])); canvas.paste(img, (0, 0))
    canvas.save(OUT / f'{PREFIX}ios-standalone-device-{scheme}.png')
    gap = SCREEN_H - m['tabBottom']
    check(f'ios-standalone-812/{scheme}：底栏下沿到屏幕底的空白', (gap <= 1) if AFTER else True, gap=gap, **m)
    if AFTER:
        check(f'ios-standalone-812/{scheme}：外壳撑到整屏 874', abs(m['appBottom'] - SCREEN_H) <= 1, appBottom=m['appBottom'])
        check(f'ios-standalone-812/{scheme}：底栏 padding-bottom = 安全区 34', m['padBot'] == f'{BOT}px', padBot=m['padBot'])
        # 诊断：长按日期
        box = pg.locator('.when-wrap').bounding_box()
        pg.mouse.move(box['x'] + 20, box['y'] + box['height'] / 2); pg.mouse.down(); pg.wait_for_timeout(1150); pg.mouse.up()
        pg.wait_for_timeout(300)
        on = pg.evaluate("() => ({box: !!document.getElementById('diagBox'), ls: localStorage.getItem('rebang-v11-diag'), txt: (document.getElementById('diagBox')||{}).textContent || ''})")
        pg.screenshot(path=str(OUT / f'{PREFIX}diag-{scheme}.png'))
        keys = ['standalone', 'displayMode', 'innerH', 'outerH', 'screen', 'vvH', 'vvTop', 'docClientH', 'safeTop', 'safeBot', 'tabbar', 'tabbarPadBot', 'body', 'app', 'ua']
        check(f'diag/{scheme}：长按 1 秒打开、记在本机、字段齐', on['box'] and on['ls'] == '1' and all(f'"{k}"' in on['txt'] for k in keys), ls=on['ls'])
        pg.reload(wait_until='networkidle'); pg.wait_for_timeout(800)
        check(f'diag/{scheme}：刷新后仍开着', pg.evaluate("() => !!document.getElementById('diagBox')"))
        pg.mouse.move(box['x'] + 20, box['y'] + box['height'] / 2); pg.mouse.down(); pg.wait_for_timeout(300); pg.mouse.up(); pg.wait_for_timeout(200)
        check(f'diag/{scheme}：短按不切换', pg.evaluate("() => !!document.getElementById('diagBox')"))
        pg.mouse.down(); pg.wait_for_timeout(1150); pg.mouse.up(); pg.wait_for_timeout(200)
        check(f'diag/{scheme}：再长按关闭', pg.evaluate("() => !document.getElementById('diagBox') && localStorage.getItem('rebang-v11-diag') === null"))
    b.close()
    # 2) 报矮画满：画布 874、innerHeight 报 812
    b, c = ctx_for(p, 'webkit', scheme, **iphone(SCREEN_H))
    c.add_init_script(IOS_STANDALONE % (TOP, BOT, "Object.defineProperty(window, 'innerHeight', {get: () => %d});" % SHORT_H, TOP, BOT))
    pg = c.new_page(); pg.goto(BASE, wait_until='networkidle'); m = measure(pg)
    pg.screenshot(path=str(OUT / f'{PREFIX}ios-standalone-paint-{scheme}.png'))
    if AFTER:
        check(f'ios-standalone-paint/{scheme}：底栏贴屏幕底、图标在 Home 条上方', abs(m['tabBottom'] - SCREEN_H) <= 1 and m['padBot'] == f'{BOT}px', **m)
    b.close()
    # 3) iOS 浏览器标签页
    b, c = ctx_for(p, 'webkit', scheme, **iphone(683)); c.add_init_script(IOS_TAB)
    pg = c.new_page(); pg.goto(BASE, wait_until='networkidle'); m = measure(pg)
    pg.screenshot(path=str(OUT / f'{PREFIX}ios-browser-tab-{scheme}.png'))
    check(f'ios-browser-tab/{scheme}：底栏下沿 = 683、无 app-fullscreen', abs(m['tabBottom'] - 683) <= 1 and 'app-fullscreen' not in m['cls'], **m)
    b.close()
    # 4) 安卓 standalone
    b, c = ctx_for(p, 'chromium', scheme, viewport={'width': 412, 'height': 915}, device_scale_factor=2.6, is_mobile=True, has_touch=True,
                   user_agent='Mozilla/5.0 (Linux; Android 15; PJZ110) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0 Mobile Safari/537.36')
    c.add_init_script("const _mm = window.matchMedia.bind(window); window.matchMedia = q => /display-mode:\\s*standalone/.test(q) ? {matches: true, media: q, addEventListener() {}, removeEventListener() {}} : _mm(q);")
    pg = c.new_page(); pg.goto(BASE, wait_until='networkidle'); m = measure(pg)
    pg.screenshot(path=str(OUT / f'{PREFIX}android-standalone-{scheme}.png'))
    check(f'android-standalone/{scheme}：底栏下沿 = 视口、不改外壳', abs(m['tabBottom'] - m['innerH']) <= 1 and 'app-fullscreen' not in m['cls'], **m)
    b.close()
    # 5) 桌面
    b, c = ctx_for(p, 'chromium', scheme, viewport={'width': 1280, 'height': 800})
    pg = c.new_page(); pg.goto(BASE, wait_until='networkidle'); m = measure(pg)
    pg.screenshot(path=str(OUT / f'{PREFIX}desktop-{scheme}.png'))
    check(f'desktop/{scheme}：底栏下沿 = 800', abs(m['tabBottom'] - 800) <= 1, **m)
    b.close()


def main():
    with sync_playwright() as p:
        for scheme in ('dark', 'light'):
            run(p, scheme)
    (OUT / f'{PREFIX}result.json').write_text(json.dumps({'base': BASE, 'checks': checks}, ensure_ascii=False, indent=1))
    fails = [c for c in checks if not c['ok']]
    print(f'{len(checks) - len(fails)}/{len(checks)} passed')
    return 1 if fails else 0


if __name__ == '__main__':
    sys.exit(main())
