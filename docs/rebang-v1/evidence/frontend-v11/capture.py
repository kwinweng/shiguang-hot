"""frontend-v11 证据截图：手机 390×844（另 1280 宽一张），对着设计检查点预览包（真实数据）逐项操作并截图。
用法：python3 capture.py <站点目录> <输出目录>；站点用 /workspace/rebang-v1-preview/make.sh 构建。
页面里的网络图（BBC/卫报/X 头像等）走真实网络加载；站内文件由 Playwright 路由直接读目录，不起服务器。"""
import json
import mimetypes
import sys
from pathlib import Path
from urllib.parse import unquote, urlsplit

from playwright.sync_api import sync_playwright

SITE, OUT = Path(sys.argv[1]), Path(sys.argv[2])
OUT.mkdir(parents=True, exist_ok=True)
V10 = Path('/workspace/deliverables/daily-site/mocks/rebang-v10.html')
log = []


def serve(page, root, host):
    def handle(route):
        u = urlsplit(route.request.url)
        if u.netloc != host:
            return route.continue_()
        p = root / (unquote(u.path).lstrip('/') or 'index.html')
        if p.is_file():
            route.fulfill(status=200, body=p.read_bytes(), content_type=mimetypes.guess_type(str(p))[0] or 'application/octet-stream')
        else:
            route.fulfill(status=404, body=b'missing')
    page.route('**/*', handle)


def swipe(ctx, page, x0, y0, x1, y1, steps=10):
    cdp = ctx.new_cdp_session(page)
    cdp.send('Input.dispatchTouchEvent', {'type': 'touchStart', 'touchPoints': [{'x': x0, 'y': y0}]})
    for i in range(1, steps + 1):
        cdp.send('Input.dispatchTouchEvent', {'type': 'touchMove', 'touchPoints': [{'x': x0 + (x1 - x0) * i / steps, 'y': y0 + (y1 - y0) * i / steps}]})
        page.wait_for_timeout(16)
    cdp.send('Input.dispatchTouchEvent', {'type': 'touchEnd', 'touchPoints': []})
    page.wait_for_timeout(700)


def shot(page, name, note):
    page.wait_for_timeout(400)
    page.screenshot(path=str(OUT / f'{name}.png'))
    log.append({'file': f'{name}.png', 'check': note})
    print(name, '-', note)


with sync_playwright() as p:
    b = p.chromium.launch()
    ctx = b.new_context(viewport={'width': 390, 'height': 844}, device_scale_factor=2, is_mobile=True, has_touch=True)
    page = ctx.new_page()
    errors = []
    page.on('pageerror', lambda e: errors.append(str(e)))
    serve(page, SITE, 'rebang.test')
    page.goto('https://rebang.test/index.html')
    page.wait_for_selector('#app:not([aria-busy])')
    page.wait_for_timeout(1500)
    root = page.locator('#channelRoot')
    idx = lambda: root.evaluate('e => Math.round(e.scrollLeft / e.clientWidth)')
    shot(page, '01-lr-current-top', '顶栏日期/刷新时间/滑法/刷新/搜索；时事 banner + 热搜块（百度）')
    page.locator('#previewNote button').click()
    cur = page.locator('.page-b[data-ch=current]')
    cur.evaluate('e => e.scrollTop = 330')
    page.locator('.page-b[data-ch=current] [data-hot=zhihu]').click()
    shot(page, '02-hot-zhihu', '热搜分家 tab：知乎')
    page.locator('.page-b[data-ch=current] [data-hot=bilibili]').click()
    shot(page, '03-hot-bilibili', '热搜分家 tab：B 站')
    cur.evaluate('e => e.scrollTop = 0')
    swipe(ctx, page, 340, 760, 30, 750)
    shot(page, '04-swipe-to-world', f'真触摸左滑换到下一频道（当前频道序号 {idx()}）')
    rail = page.locator('.page-b[data-ch=world] .banner-rail').bounding_box()
    y = rail['y'] + rail['height'] / 2
    swipe(ctx, page, rail['x'] + rail['width'] - 20, y, rail['x'] + 20, y)
    shot(page, '05-banner-swiped', f'banner 内左滑只换 banner（频道仍是 {idx()}，页码 {page.locator(".page-b[data-ch=world] .banner-pager").inner_text()}）')
    page.locator('.page-b[data-ch=world]').evaluate('e => e.scrollTop = 520')
    shot(page, '06-feed-thumb-and-text', '信息流：有图左图右文、无图标题 + 3 行摘要 + 来源时间')
    root.evaluate('e => e.scrollLeft = e.clientWidth * 4')
    page.wait_for_timeout(300)
    dig = page.locator('.page-b[data-ch=digital]')
    for _ in range(12):
        dig.evaluate('e => e.scrollTop = e.scrollHeight')
        page.wait_for_timeout(350)
    shot(page, '07-digital-end', f'数码频道无限加载到底：{dig.locator(".feed-row").count()} 条后显示「{dig.locator(".end-hint").inner_text()}」')
    root.evaluate('e => e.scrollLeft = e.clientWidth * 2')
    fin = page.locator('.page-b[data-ch=finance]')
    fin.evaluate('e => e.scrollTop = 700')
    page.wait_for_timeout(300)
    row = fin.locator('.feed-row').nth(4)
    row.scroll_into_view_if_needed()
    before = (idx(), fin.evaluate('e => e.scrollTop'))
    row.click()
    page.wait_for_timeout(500)
    shot(page, '08-article', f'整页正文（地址 {page.evaluate("location.hash")}），收藏按钮只在这里')
    page.locator('#articleBody [data-favorite-button]').click()
    shot(page, '09-favorited', '点收藏后提示只存本机浏览器')
    page.go_back()
    page.wait_for_timeout(600)
    after = (idx(), fin.evaluate('e => e.scrollTop'))
    shot(page, '10-back-restored', f'系统返回：回到原频道原位置（前 {before} → 后 {after}）')
    page.locator('.tabbar [data-view=favorites]').click()
    shot(page, '11-favorites-tab', '底栏「收藏」能看到刚收藏的条目')
    page.reload()
    page.wait_for_selector('#app:not([aria-busy])')
    page.locator('.tabbar [data-view=favorites]').click()
    shot(page, '12-favorites-after-reload', '刷新页面后收藏仍在（localStorage）')
    page.locator('.tabbar [data-view=channels]').click()
    page.locator('#modeUD').click()
    page.wait_for_timeout(600)
    shot(page, '13-ud-top', '切到「上下看频道」：频道上下排列，频道内 banner 左右滑')
    blk = page.locator('.block-a[data-ch=current]')
    blk.locator('[data-more]').scroll_into_view_if_needed()
    shot(page, '14-ud-more', '上下模式每频道先放 6 条，「继续看」按钮，下面接下一频道')
    page.locator('#modeLR').click()
    page.locator('.tabbar [data-view=blogger]').click()
    page.wait_for_selector('#bloggerList .tweet')
    page.wait_for_timeout(1500)
    shot(page, '15-blogger-x', '博主：平台 logo + 24 小时新帖数、头像行、真实推文卡')
    tr = page.locator('#bloggerList .tweet:has(.t-badge)').first
    if tr.count():
        tr.scroll_into_view_if_needed()
        shot(page, '16-blogger-translated', '英文推文：译文优先、标「机器翻译」、可看原文')
    withc = page.evaluate("""() => fetch('data/bloggers.json').then(r => r.json()).then(d => (d.items.find(i => (i.blogger.comments || []).length) || {}).id)""")
    if withc:
        page.evaluate('id => window.Rebang.openItem(id)', withc)
        page.wait_for_timeout(1200)
        page.locator('#articleBody .comments').scroll_into_view_if_needed()
        shot(page, '17-tweet-detail-comments', '推文详情：评论预览 + 收藏 + 打开原文')
        page.go_back()
        page.wait_for_timeout(500)
    page.locator('[data-plat=jike]').click()
    shot(page, '18-blogger-jike-empty', '即刻未配置：显示真实原因与抓取状态，不编内容')
    page.locator('[data-plat=wechat]').click()
    page.wait_for_timeout(800)
    shot(page, '19-blogger-wechat', '公众号：夕小瑶有内容，其他需登录（第一期不接）')
    page.locator('.tabbar [data-view=history]').click()
    page.wait_for_timeout(1200)
    shot(page, '20-history', '底栏「历史」：按北京日期翻（history 分支模块）')
    page.locator('#btnSearch').click()
    page.fill('#search-panel input', 'OpenAI')
    page.wait_for_timeout(800)
    shot(page, '21-search', '顶部搜索：纯前端匹配，没有 AI 摘要')
    first_id = page.evaluate("() => fetch('data/channel/tech-ai/page-3.json').then(r => r.json()).then(d => d.items[0].id)")
    page.goto('https://rebang.test/index.html#/item/' + __import__('urllib.parse').parse.quote(first_id, safe=''))
    page.wait_for_selector('#articleView.on')
    shot(page, '22-deeplink', f'8:30 私聊稿深链 #/item/<id> 直接打开第 3 页条目（{first_id}）')
    page.locator('#btnBack').click()
    page.wait_for_timeout(500)
    shot(page, '23-deeplink-back', '深链详情返回到首页频道')
    desk = b.new_context(viewport={'width': 1280, 'height': 900})
    dp = desk.new_page()
    serve(dp, SITE, 'rebang.test')
    dp.goto('https://rebang.test/index.html')
    dp.wait_for_selector('#app:not([aria-busy])')
    dp.wait_for_timeout(1500)
    dp.screenshot(path=str(OUT / '24-desktop-1280.png'))
    log.append({'file': '24-desktop-1280.png', 'check': '1280 宽：居中手机栏宽，深色杂志风'})
    vp = ctx.new_page()
    vp.goto('file://' + str(V10))
    vp.wait_for_timeout(2500)
    vp.screenshot(path=str(OUT / 'v10-reference.png'))
    log.append({'file': 'v10-reference.png', 'check': 'v10 设计稿同尺寸截图（对照用）'})
    b.close()
    (OUT / 'capture-log.json').write_text(json.dumps({'errors': errors, 'shots': log}, ensure_ascii=False, indent=1), encoding='utf-8')
    print('page errors:', errors)
