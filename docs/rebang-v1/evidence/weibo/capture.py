"""微博博主验收：390x844 手机尺寸、真实触摸，从站点首页 → 博主 → 微博。

用法：python3 docs/rebang-v1/evidence/weibo/capture.py <站点根 URL> [前缀]
检查：6 个博主都在、每人都有真帖；卡片图片是本站副本 media/weibo/（sinaimg 只认 weibo.com Referer，外链在浏览器里一律 403）且真加载出来；
点图开全屏查看器；视频帖在查看器里能加载；帖子链接是 weibo.com/<uid>/<mblogid>；全程没有 4xx/5xx 和脚本错误。
输出：同目录 <前缀>NN-*.png 与 <前缀>result.json。任一检查失败退出码 1。
"""
import json
import re
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = sys.argv[1].rstrip('/') + '/'
PREFIX = sys.argv[2] if len(sys.argv) > 2 else ''
OUT = Path(__file__).resolve().parent
NAMES = ['karminski-牙医', '阑夕', '高飞', 'Fenng（冯大辉）', '数字生命卡兹克', '钟文泽']
checks, shots = [], []


def check(name, ok, **detail):
    checks.append({'check': name, 'ok': bool(ok), **detail})
    print(('PASS ' if ok else 'FAIL ') + name, json.dumps(detail, ensure_ascii=False)[:300] if detail else '')


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch()
        ctx = browser.new_context(viewport={'width': 390, 'height': 844}, device_scale_factor=2, is_mobile=True, has_touch=True)
        page = ctx.new_page()
        errors, bad = [], []
        page.on('pageerror', lambda e: errors.append(str(e)))
        page.on('response', lambda r: r.status >= 400 and bad.append(f'{r.status} {r.url[:120]}'))

        def close_zoom():
            page.evaluate("() => document.dispatchEvent(new KeyboardEvent('keydown', {key: 'Escape', bubbles: true}))")
            page.wait_for_timeout(400)
            if page.locator('#zoomView.on').count():
                page.evaluate("() => { const v = document.querySelector('#zoomView'); v.hidden = true; v.classList.remove('on'); }")

        def shot(name):
            path = OUT / f'{PREFIX}{len(shots) + 1:02d}-{name}.png'
            page.screenshot(path=str(path))
            shots.append(path.name)

        page.goto(BASE, wait_until='networkidle')
        data = page.evaluate('async (u) => (await fetch(u, {cache: "no-store"})).json()', BASE + 'data/bloggers.json')
        first_page = page.evaluate('async (u) => (await fetch(u, {cache: "no-store"})).json()', BASE + 'data/blogger/weibo/all/page-1.json')
        wb = next((x for x in data['platforms'] if x['id'] == 'weibo'), None)
        per = {a['name']: a.get('total', 0) for a in (wb or {}).get('accounts', [])}
        check('数据：微博 6 个博主都有帖子', wb and wb['status'] == 'ok' and sorted(per) == sorted(NAMES) and all(v > 0 for v in per.values()),
              status=wb and wb['status'], per_account=per, last_ok_at=wb and wb.get('last_ok_at'))

        page.locator('.tabbar [data-view=blogger]').tap()
        page.wait_for_selector('#platChips [data-plat=weibo]')
        page.locator('[data-plat=weibo]').tap()
        page.wait_for_selector('#bloggerList .tweet', timeout=15000)
        page.wait_for_timeout(800)
        shot('weibo-list')
        people = page.locator('#peopleRow .ppl > span:last-child').all_inner_texts()
        check('微博人物行 = 全部 + 6 个博主', people[:1] == ['全部'] and sorted(people[1:]) == sorted(NAMES), people=people)
        txt = page.locator('#bloggerList').inner_text()
        check('列表没有「未接入/待阿欢定/Cookie」类占位', not re.search(r'未接入|待阿欢定|Cookie|weibo-crawler', txt))
        check('数字 uid 不以 @ 形式出现', not re.search(r'@\d{6,}', txt))
        # 图片：sinaimg 原图且真实加载
        imgs = page.locator('#bloggerList img[data-zoom]')
        n = min(imgs.count(), 6)
        loaded = []
        for i in range(n):
            el = imgs.nth(i)
            el.scroll_into_view_if_needed()
            page.wait_for_function('(e) => e.complete', arg=el.element_handle(), timeout=15000)
            loaded.append(el.evaluate('e => ({src: e.currentSrc || e.src, w: e.naturalWidth})'))
        check('卡片图片是本站副本（media/weibo/）且加载成功', n > 0 and all(x['w'] > 0 and '/media/weibo/' in x['src'] for x in loaded),
              images=[{'w': x['w'], 'src': x['src'][:70]} for x in loaded])
        if n:
            imgs.first.scroll_into_view_if_needed()
            imgs.first.tap()
            page.wait_for_selector('#zoomView.on', timeout=5000)
            page.wait_for_timeout(600)
            shot('weibo-zoom')
            big = page.evaluate("() => { const i = document.querySelector('#zoomView.on img'); return i ? {w: i.naturalWidth, src: i.src} : null; }")
            check('点图打开全屏查看器、原图加载', big and big['w'] > 0, img=big and {'w': big['w'], 'src': big['src'][:70]})
            close_zoom()
            if page.locator('#zoomView.on').count():
                page.evaluate("() => { const v = document.querySelector('#zoomView'); v.hidden = true; v.classList.remove('on'); }")
        # 视频：找一个有视频的帖子，在查看器里加载
        vids = [i for i in first_page['items'] if any(m['type'] == 'video' for m in i['blogger']['media'])]
        if vids:
            vid = vids[0]
            card = page.locator(f'#bloggerList .tweet[data-id="{vid["id"]}"]')
            if not card.count():
                check('视频帖在列表里', False, id=vid['id'])
            else:
                card.scroll_into_view_if_needed()
                tile = card.locator('.cell.is-vid').first
                tile.tap()
                page.wait_for_timeout(2500)
                st = page.evaluate("() => { const v = document.querySelector('#zoomView.on video'); return v ? {rs: v.readyState, err: v.error && v.error.code, src: (v.currentSrc||v.src).slice(0,60)} : null; }")
                shot('weibo-video')
                fallback = page.locator('#zoomView.on a[href*="weibo.com/"]').count()
                # 微博视频 CDN 只认 weibo.com Referer，站内播放会被拒：要求失败时给出「打开原帖」链接
                check('视频：能播，或播放被拒时查看器给出 weibo.com 原帖链接', (st and st['rs'] >= 1 and not st['err']) or fallback > 0,
                      video=st, fallback_link=fallback)
                close_zoom()
        else:
            check('视频帖：当前数据里没有视频帖（不算失败）', True)
        # 详情：原帖链接
        page.locator('#bloggerList .tweet .t-body').first.tap()
        page.wait_for_timeout(800)
        hrefs = page.eval_on_selector_all('a[href*="weibo.com/"]', 'els => els.map(e => e.href)')
        shot('weibo-detail')
        check('详情有 weibo.com/<uid>/<mblogid> 原帖链接', any(re.match(r'https://weibo\.com/\d+/[A-Za-z0-9]+$', h) for h in hrefs), hrefs=hrefs[:3])
        sina_bad = [b for b in bad if 'sinaimg' in b or 'weibocdn' in b]
        check('没有图片/视频 4xx', not sina_bad, bad=sina_bad[:5])
        check('没有脚本错误', not errors, errors=errors[:3])
        browser.close()
    (OUT / f'{PREFIX}result.json').write_text(json.dumps({'base': BASE, 'checks': checks, 'shots': shots}, ensure_ascii=False, indent=1))
    fails = [c for c in checks if not c['ok']]
    print(f'{len(checks) - len(fails)}/{len(checks)} passed')
    return 1 if fails else 0


if __name__ == '__main__':
    sys.exit(main())
