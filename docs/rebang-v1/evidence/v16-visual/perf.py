"""频道/博主一直往下刷的卡顿测量：390×844 手机视口、真触摸（CDP touch）、CPU 4 倍降速、暗色。
场景：
  deep      频道页左滑两次到「财经」（1000+ 条），然后手指快速上划 40 次
  blogger   博主页 X，手指快速上划 25 次
每个场景记录：rAF 帧间隔 >34ms 的掉帧数、最长帧、长任务（>50ms）数与总时长、CLS、
以及上划过程中滚动位置有没有往回跳（back_jumps：某次上划后 scrollTop 比上一次小）。
用法：python3 perf.py <BASE> <LABEL> [RUNS]"""
import json, sys, time, statistics
from pathlib import Path
from playwright.sync_api import sync_playwright
BASE = sys.argv[1]; LABEL = sys.argv[2]; RUNS = int(sys.argv[3]) if len(sys.argv) > 3 else 3
OUT = Path(__file__).parent
INIT = """
window.__perf = {frames: [], lt: [], cls: 0, on: false, shifts: []};
new PerformanceObserver(l => { for (const e of l.getEntries()) if (window.__perf.on) window.__perf.lt.push(e.duration); }).observe({type: 'longtask', buffered: false});
new PerformanceObserver(l => { for (const e of l.getEntries()) if (window.__perf.on && !e.hadRecentInput) { window.__perf.cls += e.value; window.__perf.shifts.push([Math.round(e.value * 1e4) / 1e4, (e.sources || []).map(s => s.node && s.node.nodeType === 1 ? s.node.tagName + '.' + s.node.className : String(s.node && s.node.nodeName)).join(' | ')]); } }).observe({type: 'layout-shift', buffered: false});
(function loop(t) { if (window.__perf.on) window.__perf.frames.push(t); requestAnimationFrame(loop); })(performance.now());
"""
SCROLLER = {'deep': """(() => { const r = document.querySelector('#channelRoot');
  if (r.classList.contains('pager-b')) { const i = Math.round(r.scrollLeft / r.clientWidth); return r.querySelectorAll('.page-b')[i]; } return r; })()""",
            'blogger': "document.querySelector('#view-blogger .sub')"}
def start(page): page.evaluate("window.__perf.frames = []; window.__perf.lt = []; window.__perf.cls = 0; window.__perf.shifts = []; window.__perf.on = true")
def stop(page):
    d = page.evaluate("(() => { window.__perf.on = false; return window.__perf; })()")
    f = d['frames']; gaps = [b - a for a, b in zip(f, f[1:])]
    return {'frames': len(gaps), 'janky': sum(g > 34 for g in gaps), 'max_frame': round(max(gaps) if gaps else 0, 1),
            'longtasks': len(d['lt']), 'lt_ms': round(sum(d['lt'])), 'cls': round(d['cls'], 4), 'shifts': d['shifts'][:5]}
def touch(cdp, pts, steps=10, dt=0.012):
    (x0, y0), (x1, y1) = pts
    cdp.send('Input.dispatchTouchEvent', {'type': 'touchStart', 'touchPoints': [{'x': x0, 'y': y0}]})
    for i in range(1, steps + 1):
        cdp.send('Input.dispatchTouchEvent', {'type': 'touchMove', 'touchPoints': [{'x': x0 + (x1 - x0) * i / steps, 'y': y0 + (y1 - y0) * i / steps}]}); time.sleep(dt)
    cdp.send('Input.dispatchTouchEvent', {'type': 'touchEnd', 'touchPoints': []})
def flicks(page, cdp, name, n):
    ys, back = [], 0
    for _ in range(n):
        touch(cdp, ((200, 700), (200, 200))); time.sleep(0.5)
        y = page.evaluate(f"{SCROLLER[name]}.scrollTop")
        if ys and y < ys[-1] - 2: back += 1
        ys.append(y)
    return ys, back
out = {}
with sync_playwright() as pw:
    b = pw.chromium.launch(channel='chrome', args=['--disable-features=OverscrollHistoryNavigation'])
    for run in range(RUNS):
        c = b.new_context(viewport={'width': 390, 'height': 844}, device_scale_factor=3, is_mobile=True, has_touch=True, color_scheme='dark')
        c.add_init_script(INIT); c.add_init_script("localStorage.setItem('rebang-v11-mode', 'lr')")
        page = c.new_page(); cdp = c.new_cdp_session(page)
        page.goto(BASE); page.wait_for_selector('#app:not([aria-busy])'); time.sleep(1.5)
        for _ in range(2): touch(cdp, ((340, 520), (60, 520)), steps=12, dt=0.016); time.sleep(0.8)
        cdp.send('Emulation.setCPUThrottlingRate', {'rate': 4})
        start(page); ys, back = flicks(page, cdp, 'deep', 40); r = stop(page)
        r.update(scroll_end=round(ys[-1]), back_jumps=back); out.setdefault('deep', []).append(r)
        cdp.send('Emulation.setCPUThrottlingRate', {'rate': 1})
        page.screenshot(path=str(OUT / f'perf-{LABEL}-deep-end.png'))
        page.evaluate("document.querySelector('.tabbar button[data-view=blogger]').click()")
        page.wait_for_selector('#platChips [data-plat=x]', state='attached'); time.sleep(1.0)
        page.evaluate("document.querySelector('#platChips [data-plat=x]').click()"); time.sleep(1.0)
        cdp.send('Emulation.setCPUThrottlingRate', {'rate': 4})
        start(page); ys, back = flicks(page, cdp, 'blogger', 25); r = stop(page)
        r.update(scroll_end=round(ys[-1]), back_jumps=back); out.setdefault('blogger', []).append(r)
        c.close()
    b.close()
summary = {k: {m: round(statistics.median(r[m] for r in v), 4) for m in v[0] if m != 'shifts'} for k, v in out.items()}
print(json.dumps({'label': LABEL, 'median_of': RUNS, 'summary': summary}, ensure_ascii=False, indent=1))
json.dump({'label': LABEL, 'runs': out, 'summary': summary}, open(OUT / f'perf-{LABEL}.json', 'w'), ensure_ascii=False, indent=1)
