"""一直往下刷 + 去掉卡片横滑：真实数据端到端验收（Chromium 与 WebKit，白天/暗黑，iPhone 主屏幕 / iPhone 浏览器 / 电脑）。
用法：python3 capture.py <BASE> [PREFIX]   截图与 result.json 写在本目录。
iPhone 主屏幕模式按 ios-standalone-fullheight/capture.py 的办法模拟（navigator.standalone + display-mode + 安全区变量）。"""
import json, sys, time
from pathlib import Path
from playwright.sync_api import sync_playwright

BASE = sys.argv[1].rstrip('/') + '/'
PREFIX = sys.argv[2] if len(sys.argv) > 2 else 'e2e'
OUT = Path(__file__).resolve().parent
UA = 'Mozilla/5.0 (iPhone; CPU iPhone OS 27_2 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) CriOS/143.0 Mobile/15E148 Safari/604.1'
STANDALONE = """
window.__rebangTestInsets = {top: 62, bottom: 34};
Object.defineProperty(navigator, 'standalone', {get: () => true});
const _mm = window.matchMedia.bind(window);
window.matchMedia = q => /display-mode:\\s*standalone/.test(q) ? {matches: true, media: q, addEventListener() {}, removeEventListener() {}} : _mm(q);
document.addEventListener('DOMContentLoaded', () => { const s = document.createElement('style');
  s.textContent = ':root{--safe-top:62px!important;--safe-bot:34px}'; document.head.appendChild(s); });
"""
checks = []
def check(name, ok, **extra):
    checks.append({'name': name, 'ok': bool(ok), **extra}); print(('PASS ' if ok else 'FAIL ') + name, json.dumps(extra, ensure_ascii=False)[:200], flush=True)

def touch(page, cdp, a, b, steps=10, dt=0.016):
    if cdp is None:   # WebKit：没有 CDP，用页面里合成的 TouchEvent
        page.evaluate("""([a, b, steps]) => new Promise(res => {
          const el = document.elementFromPoint(a[0], a[1]);
          const mk = (x, y) => new Touch({identifier: 1, target: el, clientX: x, clientY: y});
          const fire = (type, x, y) => el.dispatchEvent(new TouchEvent(type, {bubbles: true, cancelable: true, touches: type === 'touchend' ? [] : [mk(x, y)], changedTouches: [mk(x, y)]}));
          fire('touchstart', a[0], a[1]); let i = 0;
          const step = () => { i++; fire('touchmove', a[0] + (b[0] - a[0]) * i / steps, a[1] + (b[1] - a[1]) * i / steps); if (i < steps) setTimeout(step, 16); else { fire('touchend', b[0], b[1]); res(); } };
          setTimeout(step, 16); })""", [a, b, steps])
        time.sleep(0.4); return
    cdp.send('Input.dispatchTouchEvent', {'type': 'touchStart', 'touchPoints': [{'x': a[0], 'y': a[1]}]})
    for i in range(1, steps + 1):
        cdp.send('Input.dispatchTouchEvent', {'type': 'touchMove', 'touchPoints': [{'x': a[0] + (b[0] - a[0]) * i / steps, 'y': a[1] + (b[1] - a[1]) * i / steps}]}); time.sleep(dt)
    cdp.send('Input.dispatchTouchEvent', {'type': 'touchEnd', 'touchPoints': []}); time.sleep(0.4)

def long_press(page, cdp, x, y):
    if cdp is None:
        page.evaluate("""([x, y]) => new Promise(res => { const el = document.elementFromPoint(x, y);
          const t = new Touch({identifier: 2, target: el, clientX: x, clientY: y});
          el.dispatchEvent(new TouchEvent('touchstart', {bubbles: true, cancelable: true, touches: [t], changedTouches: [t]}));
          setTimeout(() => { el.dispatchEvent(new TouchEvent('touchend', {bubbles: true, cancelable: true, touches: [], changedTouches: [t]})); res(); }, 650); })""", [x, y])
    else:
        cdp.send('Input.dispatchTouchEvent', {'type': 'touchStart', 'touchPoints': [{'x': x, 'y': y}]}); time.sleep(0.65)
        cdp.send('Input.dispatchTouchEvent', {'type': 'touchEnd', 'touchPoints': []})
    time.sleep(0.4)

def scroll_until(page, sel, cond_js, step=1500, rounds=1200):
    for _ in range(rounds):
        if page.evaluate(cond_js): return True
        page.evaluate(f"document.querySelector('{sel}').scrollTop += {step}"); time.sleep(0.04)
    return page.evaluate(cond_js)

def at_top_of(page, scroller, el_sel, sticky=0):
    return page.evaluate(f"""(() => {{ const r = document.querySelector('{scroller}'), e = document.querySelector('{el_sel}');
      return Math.round(e.getBoundingClientRect().top - r.getBoundingClientRect().top - {sticky}); }})()""")

def run(pw, engine, device, scheme):
    tag = f'{engine}-{device}-{scheme}'
    b = pw.chromium.launch(channel='chrome') if engine == 'chromium' else pw.webkit.launch()
    mobile = device != 'desktop'
    kw = dict(color_scheme=scheme, device_scale_factor=2)
    if device == 'ios-standalone': kw.update(viewport={'width': 402, 'height': 874}, is_mobile=engine == 'chromium', has_touch=True, user_agent=UA)
    elif device == 'ios-browser': kw.update(viewport={'width': 390, 'height': 844}, is_mobile=engine == 'chromium', has_touch=True, user_agent=UA)
    else: kw.update(viewport={'width': 1280, 'height': 900})
    c = b.new_context(**kw)
    c.add_init_script("localStorage.setItem('rebang-v11-mode', 'lr')")
    if device == 'ios-standalone': c.add_init_script(STANDALONE)
    p = c.new_page(); errs = []
    p.on('pageerror', lambda e: errs.append(str(e)))
    cdp = c.new_cdp_session(p) if engine == 'chromium' and mobile else None
    gestures = mobile and cdp is not None   # Playwright 的 WebKit 不能合成触摸滑动：WebKit 只验滚动/长流/锚点，手势在 Chromium 真触摸里验
    W = kw['viewport']['width']; H = kw['viewport']['height']
    p.goto(BASE); p.wait_for_selector('#app:not([aria-busy])'); time.sleep(1.2)
    shot = lambda n: p.screenshot(path=str(OUT / f'{PREFIX}-{tag}-{n}.png'))
    shot('01-top')
    check(f'{tag}：没有「查看更多」入口', p.locator('.see-more, [data-see], #moreView').count() == 0)
    if device == 'ios-standalone':
        m = p.evaluate("(() => { const t = document.querySelector('.tabbar').getBoundingClientRect(); return {bottom: Math.round(t.bottom), h: innerHeight}; })()")
        check(f'{tag}：底栏仍贴底（PR #72 不回退）', m['bottom'] == m['h'], **m)
    # 1 时事刷到底 →「下一个：环球」→ 环球接着出现
    ok = scroll_until(p, '#channelRoot', "!document.querySelector('.ch-sec[data-ch=world]').hidden && document.querySelector('.ch-sec[data-ch=world]').getBoundingClientRect().top < innerHeight - 200")
    p.evaluate("""(() => { const r = document.querySelector('#channelRoot'), d = document.querySelector('.ch-sec[data-ch=current] [data-next-div]'); r.scrollTop += d.getBoundingClientRect().top - r.getBoundingClientRect().top - 260; })()"""); time.sleep(0.5)
    shot('02-next-divider')
    check(f'{tag}：时事刷完出「下一个：环球」，环球紧接着', ok and p.locator('.ch-sec[data-ch=current] [data-next-div]').inner_text().strip() == '下一个：环球')
    # 2 吸顶标题跟着内容
    p.evaluate("""(() => { const r = document.querySelector('#channelRoot'), s = document.querySelector('.ch-sec[data-ch=world]'); r.scrollTop += s.getBoundingClientRect().top - r.getBoundingClientRect().top + 600; })()"""); time.sleep(0.4)
    check(f'{tag}：滚进环球后标题是环球', p.get_attribute('#channelRoot', 'data-cur') == 'world' and at_top_of(p, '#channelRoot', '.ch-sec[data-ch=world] .ch-head') <= 0)
    shot('03-header-follows')
    # 3 左右滑 / 回顶
    if gestures:
        p.evaluate("document.querySelector('#channelRoot').scrollTop = 0"); time.sleep(0.4)
        touch(p, cdp, (W - 40, 600), (40, 590)); time.sleep(0.4)
        check(f'{tag}：左滑跳到下一个频道开头', p.get_attribute('#channelRoot', 'data-cur') == 'world' and abs(at_top_of(p, '#channelRoot', '.ch-sec[data-ch=world]')) <= 1,
              cur=p.get_attribute('#channelRoot', 'data-cur'), top=at_top_of(p, '#channelRoot', '.ch-sec[data-ch=world]'))
        touch(p, cdp, (W - 40, 600), (40, 590)); time.sleep(0.4)
        check(f'{tag}：再左滑到财经', p.get_attribute('#channelRoot', 'data-cur') == 'finance')
        shot('04-swiped-finance')
        touch(p, cdp, (40, 600), (W - 40, 590)); time.sleep(0.4)
        check(f'{tag}：右滑回环球开头', p.get_attribute('#channelRoot', 'data-cur') == 'world' and abs(at_top_of(p, '#channelRoot', '.ch-sec[data-ch=world]')) <= 1)
        # 卡片横滑不收藏
        row = p.locator('.ch-sec[data-ch=world] .feed-row').nth(1); bb = row.bounding_box()
        p.evaluate("localStorage.removeItem('rebang.favorites.v1')")
        p.locator('#modeUD').click(); time.sleep(0.2)
        bb = row.bounding_box()
        touch(p, cdp, (bb['x'] + bb['width'] - 10, bb['y'] + 30), (bb['x'] + 10, bb['y'] + 30))
        check(f'{tag}：上下模式卡片左滑不收藏、不换频道', p.evaluate("localStorage.getItem('rebang.favorites.v1')") is None and p.get_attribute('#channelRoot', 'data-cur') == 'world')
        long_press(p, cdp, bb['x'] + 40, bb['y'] + 30)
        menu = p.locator('#cardMenu.on').count() == 1
        if menu: shot('05-longpress-menu')
        check(f'{tag}：长按卡片出菜单（收藏/分享/复制链接）', menu and p.locator('#cardMenu [data-menu]').all_inner_texts()[:3] == ['收藏', '分享', '复制链接'])
        if menu: p.locator('#cardMenu [data-menu=fav]').click(); time.sleep(0.3)
        check(f'{tag}：菜单里收藏成功', len(p.evaluate("RebangFavorites.load()")) == 1)
        p.locator('#modeLR').click(); time.sleep(0.2)
    # 4 一路刷到最后「内容已结束」（中途不跳回顶部）
    p.evaluate("document.querySelector('#channelRoot').scrollTop = 0"); time.sleep(0.2)
    ys = []; back = 0
    for _ in range(1500):
        y = p.evaluate("(() => { const r = document.querySelector('#channelRoot'); r.scrollTop += 1500; return r.scrollTop; })()"); time.sleep(0.03)
        if ys and y < ys[-1] - 2: back += 1
        ys.append(y)
        if p.evaluate("(() => { const r = document.querySelector('#channelRoot'), e = r.querySelector('[data-end=all]'); return e && !e.closest('[hidden]') && r.scrollTop + r.clientHeight >= r.scrollHeight - 4; })()"): break
    time.sleep(0.4)
    counts = p.evaluate("[...document.querySelectorAll('#channelRoot > .ch-sec')].map(s => [s.dataset.ch, s.querySelectorAll('.feed-row').length])")
    totals = p.evaluate("fetch('data/meta.json').then(r => r.json()).then(m => m.channels.map(c => [c.slug, c.feed_total]))")
    check(f'{tag}：从第一个频道刷到最后一个，条数齐全、顺序对、没跳回顶部', counts == totals and back == 0, counts=counts, back=back)
    check(f'{tag}：最后写「内容已结束」，标题是最后一个频道', p.locator('#channelRoot [data-end=all]').inner_text() == '内容已结束' and p.get_attribute('#channelRoot', 'data-cur') == totals[-1][0])
    shot('06-channels-end')
    # 5 详情、返回原位
    p.evaluate("document.querySelector('#channelRoot').scrollTop -= 3000"); time.sleep(0.4)
    y0 = p.evaluate("document.querySelector('#channelRoot').scrollTop")
    vis = p.evaluate("(() => { const r = [...document.querySelectorAll('#channelRoot .feed-row')].find(e => { const b = e.getBoundingClientRect(); return b.top > 200 && b.bottom < innerHeight - 100; }); return r && r.dataset.id; })()")
    p.locator(f'#channelRoot .feed-row[data-id="{vis}"]').click(); p.wait_for_selector('#articleView.on'); time.sleep(0.3)
    p.locator('#btnBack').click(); time.sleep(0.5)
    check(f'{tag}：点开详情再返回，回到原位置', abs(p.evaluate("document.querySelector('#channelRoot').scrollTop") - y0) <= 2)
    # 6 博主长流
    p.locator('.tabbar button[data-view=blogger]').click(); p.wait_for_selector('#bloggerList .bl-seg'); time.sleep(1)
    shot('07-blogger-top')
    order = p.evaluate("[...document.querySelectorAll('#platChips [data-plat]')].map(e => e.dataset.plat)")
    ok = scroll_until(p, '#view-blogger .sub', "(() => { const s = document.querySelector('#bloggerList .bl-seg[data-plat=\"" + order[1] + "\"]'); return s && !s.hidden && s.getBoundingClientRect().top < innerHeight - 250; })()")
    p.evaluate("""(() => { const r = document.querySelector('#view-blogger .sub'), d = document.querySelector('#bloggerList .bl-seg [data-next-div]'); r.scrollTop += d.getBoundingClientRect().top - r.getBoundingClientRect().top - 320; })()"""); time.sleep(0.5)
    shot('08-blogger-next')
    check(f'{tag}：博主 X 刷完出「下一个：Grok bot」', ok and p.locator('#bloggerList .bl-seg').first.locator('[data-next-div]').inner_text().strip() == '下一个：Grok bot')
    check(f'{tag}：平台图标高亮跟着当前段', p.evaluate("(document.querySelector('#platChips .on') || {}).dataset.plat") in order[:2])
    ok = scroll_until(p, '#view-blogger .sub', "(() => { const r = document.querySelector('#view-blogger .sub'), e = r.querySelector('#bloggerList [data-end=all]'); return e && !e.closest('[hidden]') && r.scrollTop + r.clientHeight >= r.scrollHeight - 4; })()")
    segs = p.evaluate("[...document.querySelectorAll('#bloggerList .bl-seg')].map(s => [s.dataset.plat, s.querySelectorAll('[data-id]').length])")
    counts_bl = p.evaluate("fetch('data/bloggers.json').then(r => r.json()).then(b => b.platforms.map(p => [p.id, p.count]))")
    check(f'{tag}：博主一路刷到最后「内容已结束」，各平台条数齐全', ok and segs == counts_bl, segs=segs)
    shot('09-blogger-end')
    # 点平台图标 / 人物
    p.locator('#platChips [data-plat=weibo]').click(); time.sleep(1.2)
    sticky = p.evaluate("document.querySelector('#view-blogger .sticky-hd').offsetHeight")
    check(f'{tag}：点微博图标跳到微博开头', abs(at_top_of(p, '#view-blogger .sub', '#bloggerList .bl-group[data-group=weibo]', sticky)) <= 2 and p.evaluate("document.querySelector('#platChips .on').dataset.plat") == 'weibo')
    shot('10-blogger-weibo')
    p.locator('#bloggerList .people[data-people=weibo] [data-person]').nth(2).click(); time.sleep(1.2)
    cur = p.get_attribute('#bloggerList', 'data-cur')
    h = p.evaluate(f"document.querySelector('#bloggerList .bl-seg[data-seg=\"{cur}\"]').dataset.handle")
    want = p.evaluate("document.querySelectorAll('#bloggerList .people[data-people=weibo] [data-person]')[2].dataset.person")
    check(f'{tag}：点微博第 2 个人，从这个人开始，刷完接下一个人', h == want, cur=cur, h=h)
    shot('11-blogger-person')
    # 图片全屏查看
    cell = p.locator('#bloggerList .bl-seg:not([hidden]) .media-grid .cell:not(.is-vid)').first
    if cell.count():
        cell.scroll_into_view_if_needed(); cell.click(); time.sleep(0.6)
        check(f'{tag}：博主长流里点图片打开全屏查看', p.locator('#zoomView.on').count() == 1)
        shot('12-zoom'); p.keyboard.press('Escape'); time.sleep(0.3)
    # 7 热搜 / 收藏到底
    p.locator('.tabbar button[data-view=hot]').click(); time.sleep(1)
    p.evaluate("document.querySelector('#view-hot .sub').scrollTop = 1e6"); time.sleep(0.3)
    check(f'{tag}：热搜到底「内容已结束」', p.locator('#hotHost [data-end=hot]').inner_text() == '内容已结束')
    shot('13-hot-end')
    if gestures:
        li = p.locator('#view-hot .hot-list li').last; bb = li.bounding_box()
        long_press(p, cdp, bb['x'] + 60, bb['y'] + bb['height'] / 2)
        check(f'{tag}：热搜长按出同一个菜单', p.locator('#cardMenu.on').count() == 1)
        if p.locator('#cardMenu.on').count(): p.locator('#cardMenu [data-menu=cancel]').click(); time.sleep(0.3)
    p.evaluate("RebangFavorites.save(Array.from({length: 70}, (_, i) => ({id: 'e2e-' + i, title: '验收用收藏 ' + (i + 1), source_name: '验收'})))")
    p.locator('.tabbar button[data-view=favorites]').click(); time.sleep(0.6)
    for _ in range(6): p.evaluate("document.querySelector('#view-favorites .rebang-favorites').scrollTop = 1e6"); time.sleep(0.25)
    check(f'{tag}：收藏一直往下刷到「内容已结束」', p.locator('[data-favorites-list] [data-item-id]').count() == 70 and p.locator('[data-end=favorites]').inner_text() == '内容已结束')
    shot('14-favorites-end')
    p.evaluate("localStorage.removeItem('rebang.favorites.v1')")
    # 8 深链
    p.goto(BASE + '#/more/ch%3Atech-ai'); p.wait_for_selector('#app:not([aria-busy])'); time.sleep(1)
    check(f'{tag}：旧「查看更多」链接跳到长流里那个频道', p.get_attribute('#channelRoot', 'data-cur') == 'tech-ai')
    iid = p.evaluate("fetch('data/channel/finance/page-3.json').then(r => r.json()).then(d => d.items[0].id)")
    p.goto(BASE + '#/item/' + iid.replace(':', '%3A')); p.wait_for_selector('#articleView.on', timeout=15000)
    check(f'{tag}：#/item 深链直达详情', p.locator('#articleView.on').count() == 1)
    check(f'{tag}：页面无报错', not errs, errs=errs[:3])
    c.close(); b.close()

with sync_playwright() as pw:
    for engine in ('chromium', 'webkit'):
        for device in ('ios-standalone', 'ios-browser', 'desktop'):
            for scheme in ('dark', 'light'):
                if engine == 'webkit' and device == 'desktop' and scheme == 'light': continue
                try: run(pw, engine, device, scheme)
                except Exception as e: check(f'{engine}-{device}-{scheme}：脚本异常', False, err=str(e)[:300])
noindex = None
res = {'base': BASE, 'pass': sum(c['ok'] for c in checks), 'total': len(checks), 'checks': checks}
json.dump(res, open(OUT / f'{PREFIX}-result.json', 'w'), ensure_ascii=False, indent=1)
print(f"{res['pass']}/{res['total']}")
