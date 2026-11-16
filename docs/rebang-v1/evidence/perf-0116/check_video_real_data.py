# 热榜站内视频播放：真实数据 + 本地构建，手机视口真触摸核对
import json, re, sys, time
from playwright.sync_api import sync_playwright
BASE = 'http://localhost:8787/'
OUT = '/workspace/rebang-v1-briefs/video-0116/'
res = []
def ok(name, cond, extra=''):
    res.append((name, bool(cond), extra)); print(('PASS ' if cond else 'FAIL ') + name, extra, flush=True)

def swipe(page, cdp, dx, dy=0, y=None):
    x0, y0 = 195, y or 360
    pts = lambda x, y: [{'x': x, 'y': y}]
    cdp.send('Input.dispatchTouchEvent', {'type': 'touchStart', 'touchPoints': pts(x0, y0)})
    for k in range(1, 9):
        cdp.send('Input.dispatchTouchEvent', {'type': 'touchMove', 'touchPoints': pts(x0 + dx * k / 8, y0 + dy * k / 8)})
        time.sleep(0.015)
    cdp.send('Input.dispatchTouchEvent', {'type': 'touchEnd', 'touchPoints': []})
    time.sleep(0.4)

def tap(page, cdp, x, y):
    cdp.send('Input.dispatchTouchEvent', {'type': 'touchStart', 'touchPoints': [{'x': x, 'y': y}]})
    cdp.send('Input.dispatchTouchEvent', {'type': 'touchEnd', 'touchPoints': []})
    time.sleep(0.5)

def open_dotey(page):
    page.goto(BASE); page.wait_for_selector('.tabbar button[data-view=blogger]')
    page.tap('.tabbar button[data-view=blogger]'); page.wait_for_selector('[data-plat=x]')
    page.tap('[data-plat=x]'); page.wait_for_selector('[data-person=dotey]')
    page.tap('[data-person=dotey]')
    card = page.locator('article.tweet[data-id^="x-dotey:2122106906814935475"]').first
    card.wait_for(); card.scroll_into_view_if_needed(); time.sleep(0.8)
    return card

def ctx(pw, b, scheme):
    c = b.new_context(viewport={'width': 390, 'height': 844}, device_scale_factor=2, is_mobile=True, has_touch=True, color_scheme=scheme,
                      user_agent='Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Mobile/15E148 Safari/604.1')
    return c

def vstate(page):
    return page.evaluate("""() => { const v = document.querySelector('#zoomStage video'); if (!v) return null;
      return {paused: v.paused, muted: v.muted, controls: v.controls, poster: v.poster, src: v.currentSrc || v.src, t: v.currentTime, rs: v.readyState, autoplay: v.autoplay, inline: v.playsInline, loop: v.loop}; }""")

with sync_playwright() as pw:
    b = pw.chromium.launch(channel='chrome', args=['--autoplay-policy=no-user-gesture-required'])
    # ---------- 1. 暗色：真数据，dotey 两段视频 ----------
    c = ctx(pw, b, 'dark'); page = c.new_page(); cdp = c.new_cdp_session(page)
    errs = []; page.on('pageerror', lambda e: errs.append(str(e)))
    card = open_dotey(page)
    ok('列表有视频封面+播放标', card.locator('.media-grid .cell.is-vid .vid-mark').count() == 2)
    card.screenshot(path=OUT + '01-dark-blogger-video-card.png')
    page.tap('article.tweet[data-id^="x-dotey:2122106906814935475"] .media-grid .cell.is-vid >> nth=0')
    page.wait_for_selector('#zoomView.on #zoomStage video')
    s = vstate(page)
    ok('点封面进全屏播放器，原生控件、playsinline、有封面', s and s['controls'] and s['inline'] and s['poster'].startswith('https://'), json.dumps(s)[:200])
    time.sleep(0.6)
    ok('不自动出声播放', vstate(page)['paused'] and not vstate(page)['autoplay'])
    ok('对话框标签是「查看图片和视频」', page.get_attribute('#zoomView', 'aria-label') == '查看图片和视频')
    ok('计数 1 / 2', page.inner_text('#zoomCount') == '1 / 2')
    page.screenshot(path=OUT + '02-dark-player-poster.png')
    # 点视频中部：交给原生控件 → 播放；不关闭查看器
    box = page.locator('#zoomStage video').bounding_box()
    tap(page, cdp, box['x'] + box['width'] / 2, box['y'] + box['height'] / 2)
    viewer_open = page.is_visible('#zoomView.on')
    played_by_tap = False
    for _ in range(40):
        s = vstate(page)
        if s and not s['paused'] and s['t'] > 0.5 and s['rs'] >= 2: played_by_tap = True; break
        time.sleep(0.25)
    if not played_by_tap:   # 中间点按只唤出控件时，点控件条左下的播放键（真触摸）
        tap(page, cdp, box['x'] + 24, box['y'] + box['height'] - 31)
        for _ in range(40):
            s = vstate(page)
            if s and not s['paused'] and s['t'] > 0.5 and s['rs'] >= 2: played_by_tap = True; break
            time.sleep(0.25)
    viewer_open = viewer_open and page.is_visible('#zoomView.on')
    ok('点视频不关闭查看器', viewer_open)
    if not played_by_tap:
        page.evaluate("document.querySelector('#zoomStage video').play()")
        for _ in range(40):
            s = vstate(page)
            if s and s['t'] > 0.5 and s['rs'] >= 2: break
            time.sleep(0.25)
    s = vstate(page)
    ok('视频真的在播（currentTime 前进、readyState≥2）', s['t'] > 0.5 and s['rs'] >= 2, f"t={s['t']:.2f} rs={s['rs']} 由点按触发={played_by_tap}")
    page.screenshot(path=OUT + '03-dark-player-playing.png')
    page.evaluate("window._v1 = document.querySelector('#zoomStage video')")
    swipe(page, cdp, -200)
    ok('左滑到第 2 段', page.inner_text('#zoomCount') == '2 / 2')
    ok('离开时上一段暂停', page.evaluate("window._v1.paused"))
    ok('第 2 段不自动播', vstate(page)['paused'])
    # 关闭按钮
    page.tap('#zoomClose'); time.sleep(0.3)
    ok('× 关闭查看器', not page.is_visible('#zoomView'))
    # 下滑关闭（视频上）
    page.tap('article.tweet[data-id^="x-dotey:2122106906814935475"] .media-grid .cell.is-vid >> nth=0'); page.wait_for_selector('#zoomView.on video')
    swipe(page, cdp, 0, 160, y=300)
    ok('视频上下滑关闭', not page.is_visible('#zoomView'))
    # 详情页
    page.tap('article.tweet[data-id^="x-dotey:2122106906814935475"] .t-body')
    page.wait_for_selector('#articleBody .media-grid .cell.is-vid'); time.sleep(0.5)
    page.tap('#articleBody .media-grid .cell.is-vid >> nth=1')
    page.wait_for_selector('#zoomView.on video')
    ok('详情页点视频同样进播放器（从第 2 段开始）', page.inner_text('#zoomCount') == '2 / 2')
    page.screenshot(path=OUT + '04-dark-detail-player.png')
    page.tap('#zoomClose')
    ok('无页面脚本错误', not errs, '; '.join(errs)[:200])
    c.close()

    # ---------- 2. 浅色 + 混排（拦截数据，在 dotey 这条里插一张真实图片在最前，再加一个 GIF） ----------
    c = ctx(pw, b, 'light'); page = c.new_page(); cdp = c.new_cdp_session(page)
    def patch(route):
        r = route.fetch(); d = r.json()
        for it in d.get('items', []):
            if it['id'].startswith('x-dotey:2122106906814935475'):
                m = it['blogger']['media']
                it['blogger']['media'] = [{'type': 'image', 'url': m[0]['preview_url']}, m[0],
                                          {'type': 'gif', 'url': m[1]['url'], 'preview_url': m[1]['preview_url']}]
        print('patched', route.request.url[-60:])
        route.fulfill(response=r, body=json.dumps(d), headers={**r.headers, 'content-type': 'application/json'})
    page.route(re.compile(r'/data/(bloggers\.json|blogger/x/.*page-\d+\.json)'), patch)
    card = open_dotey(page)
    card.screenshot(path=OUT + '05-light-mixed-card.png')
    page.tap('article.tweet[data-id^="x-dotey:2122106906814935475"] .media-grid .cell >> nth=1')
    page.wait_for_selector('#zoomView.on video')
    page.evaluate("document.querySelector('#zoomStage video').play()"); time.sleep(1.5)
    page.evaluate("window._v1 = document.querySelector('#zoomStage video')")
    ok('混排：从视频（2/3）开始', page.inner_text('#zoomCount') == '2 / 3')
    swipe(page, cdp, 200)
    ok('右滑到图片 1/3，舞台是 <img>', page.inner_text('#zoomCount') == '1 / 3' and page.locator('#zoomStage > img').count() == 1)
    ok('离开视频时已暂停', page.evaluate("window._v1.paused"))
    page.screenshot(path=OUT + '06-light-mixed-image.png')
    swipe(page, cdp, -200); swipe(page, cdp, -200)
    time.sleep(1.5)
    s = vstate(page)
    ok('GIF（3/3）静音循环自动播', page.inner_text('#zoomCount') == '3 / 3' and s['muted'] and s['loop'] and not s['controls'] and s['t'] > 0.3, json.dumps(s)[:160])
    page.screenshot(path=OUT + '07-light-gif.png')
    c.close()

    # ---------- 3. 播放出错：拦掉视频地址 ----------
    c = ctx(pw, b, 'dark'); page = c.new_page()
    page.route('https://video.twimg.com/**', lambda r: r.abort())
    open_dotey(page)
    page.tap('article.tweet[data-id^="x-dotey:2122106906814935475"] .media-grid .cell.is-vid >> nth=0')
    page.wait_for_selector('#zoomView.on')
    try:
        page.wait_for_selector('#zoomStage .zoom-fail a', timeout=8000)
    except Exception:
        page.evaluate("document.querySelector('#zoomStage video') && document.querySelector('#zoomStage video').play().catch(()=>{})")
        page.wait_for_selector('#zoomStage .zoom-fail a', timeout=8000)
    href = page.get_attribute('#zoomStage .zoom-fail a', 'href')
    ok('播放失败：保留封面 + 「打开原帖」链接', href == 'https://x.com/dotey/status/2122106906814935475' and page.locator('#zoomStage .zoom-fail img').count() == 1, href)
    page.screenshot(path=OUT + '08-dark-error-fallback.png')
    c.close()

    # ---------- 4. 回归：普通图片查看仍可用（点图关闭） ----------
    c = ctx(pw, b, 'dark'); page = c.new_page(); cdp = c.new_cdp_session(page)
    page.goto(BASE); page.tap('.tabbar button[data-view=blogger]'); page.tap('[data-plat=x]'); time.sleep(1)
    img = page.locator('.media-grid .cell:not(.is-vid) img[data-zoom]').first
    img.scroll_into_view_if_needed(); img.tap(); page.wait_for_selector('#zoomView.on #zoomStage > img')
    ok('图片查看仍打开 <img>', True)
    tap(page, cdp, 195, 420)
    ok('点图片仍关闭查看器', not page.is_visible('#zoomView'))
    c.close()
    b.close()

fails = [r for r in res if not r[1]]
print(f'\n{len(res) - len(fails)}/{len(res)} passed')
sys.exit(1 if fails else 0)
