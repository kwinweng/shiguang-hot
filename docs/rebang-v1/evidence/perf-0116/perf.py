"""热榜 v11 卡顿测量：390×844 手机视口、真触摸、CPU 4 倍降速。
每个场景记录：rAF 帧间隔（>34ms 记为掉帧、最长帧）、长任务（>50ms）总数与总时长、布局偏移 CLS。"""
import json, sys, time, statistics
from playwright.sync_api import sync_playwright
BASE = sys.argv[1]; LABEL = sys.argv[2]; RUNS = int(sys.argv[3]) if len(sys.argv) > 3 else 3
INIT = """
window.__perf = {frames: [], lt: [], cls: 0, on: false};
new PerformanceObserver(l => { for (const e of l.getEntries()) if (window.__perf.on) window.__perf.lt.push(e.duration); }).observe({type: 'longtask', buffered: false});
new PerformanceObserver(l => { for (const e of l.getEntries()) if (window.__perf.on && !e.hadRecentInput) window.__perf.cls += e.value; }).observe({type: 'layout-shift', buffered: false});
(function loop(t) { if (window.__perf.on) window.__perf.frames.push(t); requestAnimationFrame(loop); })(performance.now());
"""
def start(page): page.evaluate("window.__perf.frames = []; window.__perf.lt = []; window.__perf.cls = 0; window.__perf.on = true")
def stop(page):
    d = page.evaluate("(() => { window.__perf.on = false; return window.__perf; })()")
    f = d['frames']; gaps = [b - a for a, b in zip(f, f[1:])]
    return {'frames': len(gaps), 'janky': sum(g > 34 for g in gaps), 'max_frame': round(max(gaps) if gaps else 0, 1),
            'longtasks': len(d['lt']), 'lt_ms': round(sum(d['lt'])), 'cls': round(d['cls'], 4)}
def touch(cdp, pts, steps=12, dt=0.016):
    (x0, y0), (x1, y1) = pts
    cdp.send('Input.dispatchTouchEvent', {'type': 'touchStart', 'touchPoints': [{'x': x0, 'y': y0}]})
    for i in range(1, steps + 1):
        cdp.send('Input.dispatchTouchEvent', {'type': 'touchMove', 'touchPoints': [{'x': x0 + (x1 - x0) * i / steps, 'y': y0 + (y1 - y0) * i / steps}]}); time.sleep(dt)
    cdp.send('Input.dispatchTouchEvent', {'type': 'touchEnd', 'touchPoints': []})
def scenario(page, cdp, name):
    start(page)
    if name == 'scroll':   # 频道列表上下滚动：手指快速上划 4 次、下划 2 次（真触摸，交给浏览器原生滚动）
        for _ in range(4): touch(cdp, ((200, 700), (200, 250)), steps=10, dt=0.012); time.sleep(0.6)
        for _ in range(2): touch(cdp, ((200, 250), (200, 700)), steps=10, dt=0.012); time.sleep(0.6)
    elif name == 'channel':   # 左右换频道 3 次
        for _ in range(3): touch(cdp, ((340, 520), (60, 520))); time.sleep(0.6)
        for _ in range(3): touch(cdp, ((60, 520), (340, 520))); time.sleep(0.6)
    elif name == 'detail':   # 打开详情、返回 ×3（点当前屏幕里的卡片）
        for k in range(3):
            xy = page.evaluate('''k => { const rows = [...document.querySelectorAll('#channelRoot .feed-row')].filter(r => { const b = r.getBoundingClientRect(); return b.left >= 0 && b.left < 100 && b.top > 120 && b.bottom < 760; });
              const r = rows[k % rows.length]; if (!r) return null; const b = r.getBoundingClientRect(); return [b.left + b.width / 2, b.top + b.height / 2]; }''', k)
            if not xy: break
            cdp.send('Input.dispatchTouchEvent', {'type': 'touchStart', 'touchPoints': [{'x': xy[0], 'y': xy[1]}]}); cdp.send('Input.dispatchTouchEvent', {'type': 'touchEnd', 'touchPoints': []})
            page.wait_for_selector('#articleView.on'); time.sleep(0.7)
            page.locator('#btnBack').tap(); time.sleep(0.7)
    elif name == 'zoom':   # 博主页：打开图片全屏、左右滑、关闭
        page.locator('.media-grid .cell').first.tap(); time.sleep(0.6)
        touch(cdp, ((330, 420), (60, 420))); time.sleep(0.5); touch(cdp, ((60, 420), (330, 420))); time.sleep(0.5)
        page.locator('#zoomClose, #zoomView').first.press('Escape'); time.sleep(0.4)
    elif name == 'tabs':   # 底栏切换
        for v in ('blogger', 'hot', 'favorites', 'channels', 'blogger', 'channels'):
            page.locator(f'.tabbar button[data-view={v}]').tap(); time.sleep(0.5)
    return stop(page)
out = {}
with sync_playwright() as pw:
    b = pw.chromium.launch(channel='chrome', args=['--disable-features=OverscrollHistoryNavigation'])
    for run in range(RUNS):
        c = b.new_context(viewport={'width': 390, 'height': 844}, device_scale_factor=3, is_mobile=True, has_touch=True, color_scheme='dark')
        c.add_init_script(INIT); page = c.new_page(); cdp = c.new_cdp_session(page)
        page.goto(BASE); page.wait_for_selector('#app:not([aria-busy])'); time.sleep(1.5)
        cdp.send('Emulation.setCPUThrottlingRate', {'rate': 4})
        for name in ('scroll', 'channel', 'detail', 'tabs'):
            out.setdefault(name, []).append(scenario(page, cdp, name))
        page.locator('.tabbar button[data-view=blogger]').tap(); time.sleep(1.2)
        page.locator('[data-plat=x]').tap(); time.sleep(0.8)
        out.setdefault('zoom', []).append(scenario(page, cdp, 'zoom'))
        c.close()
    b.close()
summary = {k: {m: round(statistics.median(r[m] for r in v), 4) for m in v[0]} for k, v in out.items()}
print(json.dumps({'label': LABEL, 'median_of': RUNS, 'summary': summary}, ensure_ascii=False, indent=1))
json.dump({'label': LABEL, 'runs': out, 'summary': summary}, open(f'/workspace/rebang-v1-briefs/perf-0116/{LABEL}.json', 'w'), ensure_ascii=False, indent=1)
