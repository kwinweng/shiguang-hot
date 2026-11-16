"""v16 新视觉（少数派红 · 白底 · 缩略图一律在右）+ PR #73 一直往下刷/只长按：真实数据端到端验收（Chromium 与 WebKit，白天/暗黑，iPhone 主屏幕 / iPhone 浏览器 / 电脑）。
用法：python3 capture.py <BASE> [PREFIX]   截图与 result.json 写在本目录。
iPhone 主屏幕模式按 ios-standalone-fullheight/capture.py 的办法模拟（navigator.standalone + display-mode + 安全区变量）。"""
import json, os, sys, time
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

THUMB_RIGHT = """(sel) => { const bad = []; let n = 0;
  for (const r of document.querySelectorAll(sel)) { const t = r.querySelector(':scope > .thumb, :scope > img, :scope > .thumb-wrap');
    if (!t || !t.getBoundingClientRect().width) continue; n++;
    const main = [...r.children].find(c => c !== t && c.getBoundingClientRect().width);
    if (!main || t.getBoundingClientRect().left < main.getBoundingClientRect().right - 1) bad.push(r.dataset.id || r.dataset.itemId); }
  return {n, bad: bad.slice(0, 5)}; }"""

def v16(p, tag, scheme, shot, cdp):
    """v16 视觉验收：配色跟系统、无 logo、顶栏、缩略图在右、红圈、已读灰、热搜三列+日期、详情字号/半屏、全屏看图"""
    css = lambda sel, prop: p.evaluate(f"getComputedStyle(document.querySelector('{sel}')).{prop}")
    bg = css('body', 'backgroundColor')
    check(f'{tag}：白天/暗黑跟系统（背景 {bg}）', bg == ('rgb(255, 255, 255)' if scheme == 'light' else 'rgb(0, 0, 0)'))
    red = p.evaluate("getComputedStyle(document.documentElement).getPropertyValue('--primary').trim().toLowerCase()")
    check(f'{tag}：少数派红 {red}', red == ('#d71a1b' if scheme == 'light' else '#f0403c'))
    check(f'{tag}：没有任何 logo', p.locator('.logo, .brand img, .brand svg:not(.lucide-chevron-down), img[src*=logo], [class*=watermark]').count() == 0)
    check(f'{tag}：顶栏是「频道名 + 下拉」', p.inner_text('#chName') == '时事' and p.locator('#chBtn .chev svg.lucide-chevron-down').count() == 1)
    check(f'{tag}：只用 Lucide 一套图标', p.evaluate("[...document.querySelectorAll('svg')].every(s => s.classList.contains('lucide'))"))
    r = p.evaluate(THUMB_RIGHT, '#channelRoot .feed-row:not(.noimg)')
    check(f'{tag}：频道列表缩略图全在右边', r['n'] > 0 and not r['bad'], **r)
    p.locator('#chBtn').click(); time.sleep(0.45); shot('v01-drop')
    check(f'{tag}：下拉列出 6 个频道 + 两种刷法 + 刷新时间', p.locator('#dropList [data-drop-ch]').count() == 6 and p.locator('#drop #modeLR').is_visible() and '刷新于' in p.inner_text('#refreshed'))
    p.keyboard.press('Escape'); time.sleep(0.35)
    # 详情：资讯
    row = p.locator('#channelRoot .feed-row').nth(1); rid = row.get_attribute('data-id')
    row.click(); p.wait_for_selector('#articleView.on'); time.sleep(0.5); shot('v02-detail-news')
    fs = lambda: p.evaluate("parseFloat(getComputedStyle(document.querySelector('#articleBody .art-text, #articleBody .t-body')).fontSize)")
    f0 = fs()
    p.locator('#dFont').click(); time.sleep(0.45); shot('v03-font-sheet')
    p.locator('#fontRange').fill('22'); time.sleep(0.15)
    check(f'{tag}：详情字号可调（{f0}→{fs()}）', f0 == 18 and fs() == 22)
    p.locator('#fontRange').fill('18'); p.locator('#actSheet [data-act=x]').click(); time.sleep(0.4)
    p.locator('#dCmt').click(); time.sleep(0.45); shot('v04-comments-sheet')
    check(f'{tag}：评论是底部半屏', p.evaluate("(() => { const b = document.querySelector('#actSheet .act-box').getBoundingClientRect(); return document.querySelector('#actSheet').classList.contains('on') && b.bottom >= innerHeight - 2 && b.top > 80; })()"))
    p.keyboard.press('Escape'); time.sleep(0.35)
    p.locator('#dShare').click(); time.sleep(0.45); shot('v05-share-sheet')
    check(f'{tag}：分享是底部半屏（系统分享/复制链接）', p.locator('#actSheet [data-act]').all_inner_texts()[:2] == ['系统分享', '复制链接'])
    p.keyboard.press('Escape'); time.sleep(0.35)
    p.locator('#btnBack').click(); time.sleep(0.5)
    check(f'{tag}：读过变灰', p.evaluate(f"(() => {{ const r = document.querySelector('#channelRoot .feed-row[data-id=\"{rid}\"]'), o = document.querySelector('#channelRoot .feed-row:not(.read)'); return r.classList.contains('read') && getComputedStyle(r.querySelector('h3')).color !== getComputedStyle(o.querySelector('h3')).color; }})()"))
    shot('v06-channel-read')
    # 博主
    p.locator('.tabbar button[data-view=blogger]').click(); p.wait_for_selector('#bloggerList .brow'); time.sleep(1); shot('v07-blogger-band')
    band = css('#blBand', 'backgroundImage') + ' ' + css('#blBand', 'backgroundColor')
    check(f'{tag}：博主头部色带（暗黑青灰 / 白天暖灰黑字）', ('rgb(34, 52, 58)' in band and 'rgb(14, 23, 26)' in band) if scheme == 'dark' else ('rgb(24' in band or 'rgb(23' in band), band=band[:160])
    if scheme == 'light': check(f'{tag}：白天色带上是黑字', css('#blBand h1', 'color') in ('rgb(0, 0, 0)', 'rgb(17, 17, 17)', 'rgb(10, 10, 10)', 'rgb(20, 20, 20)'), c=css('#blBand h1', 'color'))
    check(f'{tag}：博主头部没有「16」水印', '16' not in p.inner_text('#blBand').split('·')[0])
    ring = p.evaluate("(() => { const e = document.querySelector('#platChips .avb.on .avc'), s = getComputedStyle(e); return [s.borderTopWidth, s.outlineStyle, s.boxShadow]; })()")
    check(f'{tag}：选中的 X 头像不加红圈', ring[0] == '0px' and ring[1] == 'none' and ring[2] == 'none', ring=ring)
    check(f'{tag}：头像行最后是「全部」', p.inner_text('#view-blogger .avall').strip() == '全部')
    dh = p.inner_text('#bloggerList .dayh').replace('\n', ' ')
    check(f'{tag}：日期头「今天 · 更新 N 篇」（{dh}）', bool(__import__('re').match(r'^\d+\.\d+ 今天 更新 \d+ 篇$', dh)))
    r = p.evaluate(THUMB_RIGHT, '#bloggerList .brow:not(.noimg)')
    check(f'{tag}：博主列表缩略图全在右边', r['n'] > 0 and not r['bad'], **r)
    clamp = p.evaluate("""(() => { const lh = e => parseFloat(getComputedStyle(e).lineHeight); const o = {};
      const t = document.querySelector('#bloggerList .b-text'); if (t) o.text = Math.round(t.getBoundingClientRect().height / lh(t));
      const s = document.querySelector('#bloggerList .b-sum'); if (s) o.sum = Math.round(s.getBoundingClientRect().height / lh(s)); return o; })()""")
    check(f'{tag}：无标题帖 ≤4 行、有标题摘要 ≤3 行', clamp.get('text', 0) <= 4 and clamp.get('sum', 0) <= 3, **clamp)
    p.evaluate("document.querySelector('#view-blogger .sub').scrollTop = 900"); time.sleep(0.6); shot('v08-blogger-scrolled')
    check(f'{tag}：滚过色带后顶栏出现、写当前平台', p.evaluate("document.querySelector('#app').classList.contains('top-show')") and p.inner_text('#chName') == 'X', cur_name=p.inner_text('#chName'))
    p.evaluate("document.querySelector('#view-blogger .sub').scrollTop = 0"); time.sleep(0.4)
    p.locator('#view-blogger [data-b=all]').click(); time.sleep(0.5); shot('v09-blogger-all')
    check(f'{tag}：「全部」列出各平台的博主', p.locator('#actSheet [data-all-plat]').count() >= 5 and p.locator('#actSheet [data-person]').count() >= 20)
    p.keyboard.press('Escape'); time.sleep(0.35)
    # 博主详情（X：互动数、热门回复、引用卡）
    xid = p.evaluate("fetch('data/blogger/x/all/page-1.json').then(r => r.json()).then(d => (d.items.find(i => i.blogger && i.blogger.quote && (i.blogger.comments || []).length) || d.items.find(i => i.blogger && i.blogger.quote) || d.items[0]).id)")
    p.locator(f'#bloggerList .brow[data-id="{xid}"]').first.evaluate('e => e.scrollIntoView({block: "center"})'); time.sleep(0.3)
    p.locator(f'#bloggerList .brow[data-id="{xid}"]').first.click(); p.wait_for_selector('#articleView.on'); time.sleep(0.6); shot('v10-detail-x')
    check(f'{tag}：X 详情保留互动数和引用卡', p.locator('#articleBody .tweet .metrics em').count() >= 2 and p.locator('#articleBody .quote').count() == 1)
    p.evaluate("document.querySelector('#articleBody').scrollTop = 1e6"); time.sleep(0.4); shot('v11-detail-x-lower')
    hasc = p.locator('#articleBody .x-comments, #articleBody .comments, #articleBody [data-comments]').count()
    p.locator('#dCmt').click(); time.sleep(0.5); shot('v12-x-comments-sheet')
    check(f'{tag}：X 热门回复在详情和评论半屏里', p.locator('#actSheet .act-body').inner_text().strip() != '' and (hasc or '暂时没有' in p.inner_text('#actSheet')), inline=hasc)
    p.keyboard.press('Escape'); time.sleep(0.3); p.locator('#btnBack').click(); time.sleep(0.5)
    # 热搜
    p.locator('.tabbar button[data-view=hot]').click(); p.wait_for_selector('#view-hot .hot-list li'); time.sleep(0.8); shot('v13-hot')
    check(f'{tag}：热搜三列 百度/知乎/B站', p.locator('#view-hot .hot-tabs [role=tab] b').all_inner_texts() == ['百度', '知乎', 'B站'])
    chips = p.locator('#hotDates .chip').all_inner_texts()
    check(f'{tag}：热搜日期从「今天」开始可切换（{"/".join(chips)}）', chips[:1] == ['今天'] and len(chips) >= 2)
    first_today = p.inner_text('#view-hot .hot-list li .t')
    p.locator('#hotDates .chip').nth(1).click(); time.sleep(1.2)
    p.locator('#view-hot [data-hot=zhihu]').click(); time.sleep(0.6); shot('v14-hot-zhihu-past')
    check(f'{tag}：切到过去某天的知乎', p.locator('#hotDates .chip.on').inner_text() == chips[1] and p.locator('#view-hot .hot-tabs .on b').inner_text() == '知乎' and p.locator('#view-hot .hot-list li').count() > 0)
    p.locator('#hotDates .chip').first.click(); time.sleep(0.8)
    # 收藏 / 搜索：缩略图在右
    ids = p.evaluate("fetch('data/channel/current/page-1.json').then(r => r.json()).then(d => d.items.filter(i => i.image && i.image.url).slice(0, 3).map(i => ({id: i.id, title: i.title, source_name: i.source_name, url: i.url, image: i.image, published_at: i.published_at})))")
    p.evaluate("x => RebangFavorites.save(x)", ids)
    p.locator('.tabbar button[data-view=favorites]').click(); time.sleep(0.8); shot('v15-favorites')
    r = p.evaluate(THUMB_RIGHT, '[data-favorites-list] .row-item:not(.noimg)')
    check(f'{tag}：收藏列表缩略图在右边', r['n'] > 0 and not r['bad'], **r)
    p.evaluate("localStorage.removeItem('rebang.favorites.v1')")
    p.locator('#btnSearch').click(); time.sleep(0.4); p.fill('[data-search-input]', 'AI'); time.sleep(1.5); shot('v16-search')
    r = p.evaluate(THUMB_RIGHT, '#search-panel .row-item:not(.noimg)')
    check(f'{tag}：搜索结果缩略图在右边', r['n'] > 0 and not r['bad'], **r)

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
        a = p.evaluate("(() => { const r = document.querySelector('#app').getBoundingClientRect(); return {top: Math.round(r.top), bottom: Math.round(r.bottom)}; })()")
        check(f'{tag}：外壳仍撑满整屏（PR #72 不回退），悬浮底栏在安全区之上', a['top'] == 0 and a['bottom'] == m['h'] and m['h'] - 34 - 40 <= m['bottom'] <= m['h'] - 34 + 2, **m, app=a)
    # 1 时事刷到底 →「下一个：环球」→ 环球接着出现
    ok = scroll_until(p, '#channelRoot', "!document.querySelector('.ch-sec[data-ch=world]').hidden && document.querySelector('.ch-sec[data-ch=world]').getBoundingClientRect().top < innerHeight - 200")
    p.evaluate("""(() => { const r = document.querySelector('#channelRoot'), d = document.querySelector('.ch-sec[data-ch=current] [data-next-div]'); r.scrollTop += d.getBoundingClientRect().top - r.getBoundingClientRect().top - 260; })()"""); time.sleep(0.5)
    shot('02-next-divider')
    check(f'{tag}：时事刷完出「下一个：环球」，环球紧接着', ok and p.locator('.ch-sec[data-ch=current] [data-next-div]').inner_text().strip() == '下一个：环球')
    # 2 吸顶标题跟着内容
    p.evaluate("""(() => { const r = document.querySelector('#channelRoot'), s = document.querySelector('.ch-sec[data-ch=world]'); r.scrollTop += s.getBoundingClientRect().top - r.getBoundingClientRect().top + 600; })()"""); time.sleep(0.4)
    check(f'{tag}：滚进环球后顶栏写「环球」', p.get_attribute('#channelRoot', 'data-cur') == 'world' and p.inner_text('#chName') == '环球', cur_name=p.inner_text('#chName'))
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
        p.locator('#chBtn').click(); time.sleep(0.3); p.locator('#modeUD').click(); time.sleep(0.4)
        bb = row.bounding_box()
        touch(p, cdp, (bb['x'] + bb['width'] - 10, bb['y'] + 30), (bb['x'] + 10, bb['y'] + 30))
        check(f'{tag}：上下模式卡片左滑不收藏、不换频道', p.evaluate("localStorage.getItem('rebang.favorites.v1')") is None and p.get_attribute('#channelRoot', 'data-cur') == 'world')
        long_press(p, cdp, bb['x'] + 40, bb['y'] + 30)
        menu = p.locator('#cardMenu.on').count() == 1
        if menu: shot('05-longpress-menu')
        check(f'{tag}：长按卡片出菜单（收藏/分享/复制链接）', menu and p.locator('#cardMenu [data-menu]').all_inner_texts()[:3] == ['收藏', '分享', '复制链接'])
        if menu: p.locator('#cardMenu [data-menu=fav]').click(); time.sleep(0.3)
        check(f'{tag}：菜单里收藏成功', len(p.evaluate("RebangFavorites.load()")) == 1)
        p.locator('#chBtn').click(); time.sleep(0.3); p.locator('#modeLR').click(); time.sleep(0.4)
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
    check(f'{tag}：读过的变灰（标 read）', p.locator(f'#channelRoot .feed-row.read[data-id="{vis}"]').count() == 1)
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
    sticky = p.evaluate("document.querySelector('#top').offsetHeight")
    check(f'{tag}：点微博图标跳到微博开头', abs(at_top_of(p, '#view-blogger .sub', '#bloggerList .bl-group[data-group=weibo]', sticky)) <= 2 and p.evaluate("document.querySelector('#platChips .on').dataset.plat") == 'weibo')
    shot('10-blogger-weibo')
    p.locator('#bloggerList .people[data-people=weibo] [data-person]').nth(2).click(); time.sleep(1.2)
    cur = p.get_attribute('#bloggerList', 'data-cur')
    h = p.evaluate(f"document.querySelector('#bloggerList .bl-seg[data-seg=\"{cur}\"]').dataset.handle")
    want = p.evaluate("document.querySelectorAll('#bloggerList .people[data-people=weibo] [data-person]')[2].dataset.person")
    check(f'{tag}：点微博第 2 个人，从这个人开始，刷完接下一个人', h == want, cur=cur, h=h)
    shot('11-blogger-person')
    # 图片全屏查看
    cell = p.locator('#bloggerList .bl-seg:not([hidden]) .brow .thumb').first
    if cell.count():
        cell.evaluate('e => e.scrollIntoView({block: "center"})'); time.sleep(0.3); cell.click(); time.sleep(0.6)
        check(f'{tag}：博主长流里点图片打开全屏查看', p.locator('#zoomView.on').count() == 1, id=cell.evaluate('e => e.closest("[data-id]").dataset.id'), html=cell.evaluate('e => e.outerHTML.slice(0, 300)'))
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
    # 9 v16 视觉（放在最后：它会留下「前进」历史，模拟器里横滑会被浏览器当成前进手势）
    n0 = len(errs)
    p.goto(BASE); p.reload(); p.wait_for_selector('#app:not([aria-busy])'); time.sleep(1.0)
    errs[n0:] = [e for e in errs[n0:] if 'access control checks' not in e]   # WebKit：重载时中断还在下的搜索索引会报这句（main 上一样），不是页面错误
    v16(p, tag, scheme, shot, cdp)
    check(f'{tag}：页面无报错', not errs, errs=errs[:3])
    c.close(); b.close()

with sync_playwright() as pw:
    for engine in ('chromium', 'webkit'):
        for device in ('ios-standalone', 'ios-browser', 'desktop'):
            for scheme in ('dark', 'light'):
                if engine == 'webkit' and device == 'desktop' and scheme == 'light': continue
                if os.environ.get('ONLY') and os.environ['ONLY'] != f'{engine}-{device}-{scheme}': continue
                try: run(pw, engine, device, scheme)
                except Exception as e: check(f'{engine}-{device}-{scheme}：脚本异常', False, err=str(e)[:1500])
res = {'base': BASE, 'pass': sum(c['ok'] for c in checks), 'total': len(checks), 'checks': checks}
json.dump(res, open(OUT / f'{PREFIX}-result.json', 'w'), ensure_ascii=False, indent=1)
print(f"{res['pass']}/{res['total']}")
