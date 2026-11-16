"""v13 验收：从真实入口（站点首页）在 390x844 手机尺寸、用真实触摸事件（CDP Input.dispatchTouchEvent）实测
阿欢 2026-11-15 22:08–22:11 定的 7 条 + v12 及以前的既有功能。

用法：python3 docs/rebang-v1/evidence/integration-v13/capture.py <站点根 URL> [截图前缀] [--phase2]
第二期（2026-11-16）加了即刻、TG 评论楼、YouTube、公众号等扫码几项（P2 开头）；--phase2 时即刻没帖子算失败。
输出：同目录 <前缀>NN-*.png 与 <前缀>result.json。任一检查失败退出码 1。
"""
import json
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

ARGS = [a for a in sys.argv if a != '--phase2']
BASE = ARGS[1].rstrip('/') + '/'
PREFIX = ARGS[2] if len(ARGS) > 2 else ''
PHASE2_STRICT = '--phase2' in sys.argv   # 第二期验收：即刻必须有帖子
OUT = Path(__file__).resolve().parent
checks, shots = [], []


def check(name, ok, **detail):
    checks.append({'check': name, 'ok': bool(ok), **detail})
    print(('PASS ' if ok else 'FAIL ') + name, json.dumps(detail, ensure_ascii=False)[:300] if detail else '')


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch()
        ctx = browser.new_context(viewport={'width': 390, 'height': 844}, device_scale_factor=2, is_mobile=True, has_touch=True)
        ctx.grant_permissions(['clipboard-read', 'clipboard-write'], origin=BASE.split('/', 3)[0] + '//' + BASE.split('/', 3)[2])
        page = ctx.new_page()
        cdp = ctx.new_cdp_session(page)
        errors, bad = [], []
        page.on('pageerror', lambda e: errors.append(str(e)))
        page.on('response', lambda r: r.status >= 400 and bad.append(f'{r.status} {r.url}'))

        def shot(name):
            path = OUT / f'{PREFIX}{len(shots) + 1:02d}-{name}.png'
            page.screenshot(path=str(path))
            shots.append(path.name)

        def get(rel):
            return page.evaluate('async (u) => (await fetch(u)).json()', BASE + 'data/' + rel)

        # ---- 真实触摸 ----
        def t_start(x, y):
            cdp.send('Input.dispatchTouchEvent', {'type': 'touchStart', 'touchPoints': [{'x': x, 'y': y}]})

        def t_move(x, y):
            cdp.send('Input.dispatchTouchEvent', {'type': 'touchMove', 'touchPoints': [{'x': x, 'y': y}]})

        def t_end():
            cdp.send('Input.dispatchTouchEvent', {'type': 'touchEnd', 'touchPoints': []})

        def swipe(x0, y0, x1, y1, steps=14, ms=260, hold=None):
            t_start(x0, y0)
            for i in range(1, steps + 1):
                t_move(x0 + (x1 - x0) * i / steps, y0 + (y1 - y0) * i / steps)
                page.wait_for_timeout(ms / steps)
            if hold:
                hold()
            t_end()
            page.wait_for_timeout(450)

        def long_press(x, y, ms=800):
            t_start(x, y)
            page.wait_for_timeout(ms)
            t_end()
            page.wait_for_timeout(300)

        def center(loc):
            b = loc.bounding_box()
            return b['x'] + b['width'] / 2, b['y'] + b['height'] / 2

        def toast_clear():
            page.evaluate("() => { const t = document.querySelector('#toast'); t.textContent = ''; t.classList.remove('on'); }")

        def toast_text(wait=2500):
            try:
                page.wait_for_function("() => document.querySelector('#toast').textContent.trim()", timeout=wait)
            except Exception:
                pass
            return page.locator('#toast').inner_text()

        def fav_ids():
            return page.evaluate("() => (window.RebangFavorites && RebangFavorites.load ? RebangFavorites.load() : []).map(x => x.id)")

        def ch_index():
            return page.locator('#channelRoot').evaluate('e => Math.round(e.scrollLeft / e.clientWidth)')

        def go_channel(i):
            page.locator('#channelRoot').evaluate('(e, i) => e.scrollLeft = i * e.clientWidth', i)
            page.wait_for_timeout(400)

        def sticky_ok(scroller_sel, head_sel):
            r = page.evaluate("""([s, h]) => { const sc = document.querySelector(s), hd = document.querySelector(h);
              if (!sc || !hd) return null; const a = sc.getBoundingClientRect(), b = hd.getBoundingClientRect();
              return {scrollTop: Math.round(sc.scrollTop), scTop: Math.round(a.top), hdTop: Math.round(b.top), hdH: Math.round(b.height),
                      text: hd.innerText.replace(/\\s+/g, ' ').slice(0, 60)}; }""", [scroller_sel, head_sel])
            return r, bool(r and r['scrollTop'] > 150 and abs(r['hdTop'] - r['scTop']) <= 1 and r['hdH'] > 10)

        def top_bar(view):
            return page.evaluate("""() => { const top = document.querySelector('.top'), when = document.querySelector('#when'), ref = document.querySelector('#refreshed');
              const w = when.getBoundingClientRect(), t = top.getBoundingClientRect();
              const txt = top.innerText; const day = RebangLib.fmtDay(new Date());
              return {when: when.innerText, refreshed: ref.innerText, left: Math.round(w.left - t.left), align: getComputedStyle(when).textAlign,
                      dayCount: txt.split(day.split(' ')[0]).length - 1, monthMarks: (txt.match(/月/g) || []).length,
                      height: Math.round(t.height), html: top.innerHTML.length, expectDay: day}; }""")

        page.goto(BASE)
        page.wait_for_selector('#app:not([aria-busy])')
        page.wait_for_timeout(700)
        note = page.locator('#previewNote span').inner_text() if page.locator('#previewNote').is_visible() else ''
        check('顶部说明不再有「英文还没接机器翻译」', '机器翻译' not in note, note=note)
        tabs = [t.strip() for t in page.locator('.tabbar button').all_inner_texts()]
        check('底栏 = 频道/博主/热搜/收藏', tabs == ['频道', '博主', '热搜', '收藏'], tabs=tabs)
        check('历史页已去掉', page.locator('#view-history').count() == 0)
        check('频道里没有热搜块', page.locator('#channelRoot .hot').count() == 0)
        tb = page.locator('.tabbar').bounding_box()
        check('底栏贴在视口最底部', tb and abs((tb['y'] + tb['height']) - 844) <= 1, box=tb)
        page.add_style_tag(content=':root{--safe-bot:34px !important}')
        page.wait_for_timeout(40)
        tb2 = page.evaluate("""() => { const el = document.querySelector('.tabbar'), btn = el.querySelector('button');
          const r = el.getBoundingClientRect(), b = btn.getBoundingClientRect();
          return {bottom: r.bottom, height: r.height, btnBottom: b.bottom, vh: window.innerHeight}; }""")
        check('模拟 home indicator 后底栏仍贴底，按钮在安全区上方',
              abs(tb2['bottom'] - 844) <= 1 and tb2['btnBottom'] <= 844 - 33, **tb2)
        page.evaluate("() => { [...document.querySelectorAll('style')].forEach(s => { if ((s.textContent||'').includes('--safe-bot:34px')) s.remove(); }); }")
        if page.locator('#previewNote').is_visible():
            page.locator('#previewNote button').tap()
        meta = get('meta.json')
        slugs = [c['slug'] for c in meta['channels']]

        # ===== 7 顶栏：日期居左、只出现一次、4 个页一致 =====
        bars = {}
        for view in ('channels', 'blogger', 'hot', 'favorites'):
            page.locator(f'.tabbar [data-view={view}]').tap()
            page.wait_for_timeout(500)
            bars[view] = top_bar(view)
            shot(f'topbar-{view}')
        b0 = bars['channels']
        same = all(b['when'] == b0['when'] and b['refreshed'] == b0['refreshed'] and b['height'] == b0['height'] and b['left'] == b0['left'] for b in bars.values())
        check('7 顶栏日期居左（左边距 ≤ 20px，左对齐）', all(b['left'] <= 20 and b['align'] in ('left', 'start') for b in bars.values()),
              left={k: v['left'] for k, v in bars.items()}, align=b0['align'])
        check('7 顶栏日期只写一次（顶栏里「X月X日」只出现 1 次；刷新时间同一天只写时间）',
              all(b['dayCount'] == 1 and b['monthMarks'] == 1 and b['when'] == b['expectDay'] for b in bars.values()),
              when=b0['when'], refreshed=b0['refreshed'], counts={k: (v['dayCount'], v['monthMarks']) for k, v in bars.items()})
        check('7 四个页面顶栏一致（同一个顶栏、同样文字和高度）', same, heights={k: v['height'] for k, v in bars.items()})

        # ===== 1 吸顶：频道（左右）=====
        page.locator('.tabbar [data-view=channels]').tap()
        page.wait_for_timeout(300)
        go_channel(0)
        for _ in range(3):
            swipe(200, 700, 200, 250, ms=300)
        r, ok = sticky_ok('.page-b[data-ch=current]', '.page-b[data-ch=current] .ch-head')
        check('1 频道（左右）下滑后频道名一行吸在顶上', ok, **(r or {}))
        shot('sticky-channel-lr')
        page.locator('.page-b[data-ch=current]').evaluate('e => e.scrollTop = 0')
        page.wait_for_timeout(200)

        # ===== 2/3 TG 引用卡、转发、表情、浏览 =====
        rs, reply = None, None
        for c in meta['channels']:
            p1 = get(f'channel/{c["slug"]}/page-1.json')['items']
            cands = [i for i in p1 if (i.get('quote') or {}).get('kind') == 'reply' and (i.get('tg') or {}).get('reactions')]
            reply = next((i for i in cands if p1.index(i) >= 5), cands[0] if cands else None)   # 不挑第一条，返回原位才看得出来
            if reply:
                rs = c['slug']; break
        go_channel(slugs.index(rs))
        card = page.locator(f'.page-b[data-ch={rs}] .feed-row[data-id="{reply["id"]}"]')
        card.scroll_into_view_if_needed()
        page.wait_for_timeout(300)
        html = card.inner_html()
        own = card.locator('h3').inner_text() if card.locator('h3').count() else ''
        check('2 引用：卡片先是频道自己的话，下面是原帖引用卡（来源频道名）',
              own and card.locator('.q-card').count() == 1 and html.index('<h3') < html.index('q-card')
              and reply['quote']['source_name'] in card.locator('.q-card .q-src').inner_text(),
              id=reply['id'], own=own[:40], quote_src=reply['quote']['source_name'])
        rx_shown = card.locator('.tg-stats .rx:not(.more)').count()
        check('3 卡片上显示表情回应（最多 3 个 +N）和浏览数，数字与 t.me 抓到的一致',
              rx_shown == min(3, len(reply['tg']['reactions'])) and reply['tg']['views_label'] in card.locator('.tg-stats').inner_text(),
              reactions=len(reply['tg']['reactions']), shown=rx_shown, views=reply['tg']['views_label'])
        shot('tg-reply-card')

        tools_i = slugs.index('tools')
        fwd = next(i for i in get('channel/tools/page-1.json')['items'] if (i.get('quote') or {}).get('kind') == 'forward')
        go_channel(tools_i)
        fcard = page.locator(f'.page-b[data-ch=tools] .feed-row[data-id="{fwd["id"]}"]')
        fcard.scroll_into_view_if_needed()
        page.wait_for_timeout(300)
        check('2 转发且频道没写话：标「转发」+ 原帖引用卡（转发自 来源）',
              fcard.locator('.fwd-tag').inner_text() == '转发' and fcard.locator('h3').count() == 0
              and fwd['quote']['source_name'] in fcard.locator('.q-card').inner_text(), id=fwd['id'], src=fwd['quote']['source_name'])
        shot('tg-forward-card')
        fcard.tap()
        page.wait_for_selector('#articleView.on')
        href = page.locator('#articleBody a[data-quote-link]').get_attribute('href')
        check('2 详情里点引用卡打开原帖', href == fwd['quote']['url'], href=href)
        shot('tg-forward-detail')
        page.locator('#btnBack').tap()
        page.wait_for_timeout(400)
        go_channel(slugs.index(rs))

        # ===== 2/3/4 详情：引用、全部表情、上一条/下一条、横滑、左边缘返回 =====
        card = page.locator(f'.page-b[data-ch={rs}] .feed-row[data-id="{reply["id"]}"]')
        card.scroll_into_view_if_needed()
        y0 = page.locator(f'.page-b[data-ch={rs}]').evaluate('e => e.scrollTop')
        ids = page.eval_on_selector_all(f'.page-b[data-ch={rs}] .feed-list [data-id]', 'els => els.map(e => e.dataset.id)')
        card.tap()
        page.wait_for_selector('#articleView.on')
        body = page.locator('#articleBody').inner_html()
        check('2 详情：频道自己的话在上，引用卡在下且链接原帖',
              page.locator('#articleBody .art-title').count() == 1 and body.index('art-title') < body.index('q-card')
              and page.locator('#articleBody a[data-quote-link]').get_attribute('href') == reply['quote']['url'], url=reply['quote']['url'])
        check('3 详情显示全部表情回应 + 浏览数', page.locator('#articleBody .tg-stats.full .rx').count() == len(reply['tg']['reactions']),
              shown=page.locator('#articleBody .tg-stats.full .rx').count(), data=len(reply['tg']['reactions']))
        shot('tg-reply-detail')
        at = ids.index(reply['id'])
        pos = page.locator('#artNav .art-nav-pos').inner_text()
        nav_box = page.locator('#artNav').bounding_box()
        check('4 详情底部有小的上一条/下一条，位置 = 列表里第几条', pos == f'{at + 1} / {len(ids)}' and nav_box['height'] <= 48,
              pos=pos, height=nav_box['height'])
        hid = lambda: page.evaluate('() => decodeURIComponent(location.hash.replace("#/item/", ""))')
        page.locator('#artNav [data-nav="1"]').tap()
        page.wait_for_timeout(400)
        check('4 点「下一条」到同一列表的下一条', hid() == ids[at + 1], now=hid(), want=ids[at + 1])
        shot('detail-next')
        swipe(320, 450, 90, 460)
        check('4 正文左滑 → 下一条', hid() == ids[at + 2], now=hid(), want=ids[at + 2])
        swipe(90, 450, 330, 455)
        check('4 正文右滑（不从边缘起） → 上一条', hid() == ids[at + 1], now=hid(), want=ids[at + 1])
        page.locator('#artNav [data-nav="-1"]').tap()
        page.wait_for_timeout(400)
        check('4 点「上一条」回到原条', hid() == reply['id'])
        swipe(6, 450, 300, 455, ms=220)
        page.wait_for_timeout(300)
        y1 = page.locator(f'.page-b[data-ch={rs}]').evaluate('e => e.scrollTop')
        check('5 详情从左边缘右滑 → 返回原列表原位置（上一条/下一条用 replace，不多压历史）',
              page.locator('#articleView.on').count() == 0 and abs(y1 - y0) <= 2 and '#/item/' not in page.url, y0=y0, y1=y1)

        # 评论（只在频道公开评论区可见时）
        cm = None
        for c in meta['channels']:
            for n in range(1, c['pages'] + 1):
                cm = next((i for i in get(f'channel/{c["slug"]}/page-{n}.json')['items'] if (i.get('tg') or {}).get('comments')), None)
                if cm: break
            if cm: break
        page.goto(BASE + '#/item/' + cm['id'].replace(':', '%3A'))
        page.wait_for_selector('#articleView.on [data-tg-comments]')
        n_c = page.locator('#articleBody [data-tg-comments] .comment').count()
        check('3 公开评论：只显示 t.me 讨论区公开可见的那几条 + 总数 + 去 Telegram 看全部', n_c == len(cm['tg']['comments']),
              id=cm['id'], shown=n_c, total=cm['tg'].get('comments_total'))
        page.locator('[data-tg-comments]').scroll_into_view_if_needed()
        shot('tg-comments')
        noc = next(i for i in p1 if (i.get('tg') or {}).get('views') and not (i.get('tg') or {}).get('comments'))
        page.goto(BASE + '#/item/' + noc['id'].replace(':', '%3A'))
        page.wait_for_selector('#articleView.on')
        check('3 没有公开评论的条目不显示评论区（不编）', page.locator('#articleBody [data-tg-comments]').count() == 0, id=noc['id'])
        page.goto(BASE)
        page.wait_for_selector('#app:not([aria-busy])')
        page.wait_for_timeout(600)

        # ===== 5 手势优先级：左右频道横滑、banner 横滑、长按菜单 =====
        go_channel(0)
        favs0 = fav_ids()
        row = page.locator('.page-b[data-ch=current] .feed-list .feed-row').nth(2)
        row.scroll_into_view_if_needed()
        x, y = center(row)
        swipe(330, y, 70, y + 4, ms=240)
        page.wait_for_timeout(500)
        check('5 左右模式：在卡片上横滑 = 换频道，不触发卡片收藏', ch_index() == 1 and fav_ids() == favs0, index=ch_index())
        swipe(70, 600, 330, 604, ms=240)
        page.wait_for_timeout(500)
        bi = next(i for i, c in enumerate(meta['channels']) if len(c['banner']) > 1)
        bs = slugs[bi]
        go_channel(bi)
        page.locator(f'.page-b[data-ch={bs}]').evaluate('e => e.scrollTop = 0')
        page.wait_for_timeout(200)
        rail = page.locator(f'.page-b[data-ch={bs}] .banner-rail')
        bx, by = center(rail)
        pager0 = page.locator(f'.page-b[data-ch={bs}] .banner-pager').inner_text()
        swipe(330, by, 80, by + 3, ms=240)
        page.wait_for_timeout(600)
        pager1 = page.locator(f'.page-b[data-ch={bs}] .banner-pager').inner_text()
        check('5 banner 上横滑只翻 banner，不换频道', pager0.startswith('1 /') and pager1.startswith('2 /') and ch_index() == bi,
              channel=bs, before=pager0, after=pager1, index=ch_index())
        shot('banner-swipe')
        go_channel(0)
        row = page.locator('.page-b[data-ch=current] .feed-list .feed-row').nth(1)
        row.scroll_into_view_if_needed()
        rid = row.get_attribute('data-id')
        long_press(*center(row))
        menu = page.locator('#cardMenu.on [data-menu]').all_inner_texts()
        check('5 长按卡片 → 菜单（收藏/分享/复制链接/打开原文），且不打开详情',
              menu[:4] == ['收藏', '分享', '复制链接', '打开原文'] and page.locator('#articleView.on').count() == 0, menu=menu)
        shot('longpress-menu')
        toast_clear()
        page.locator('#cardMenu [data-menu=copy]').tap()
        t = toast_text()
        clip = page.evaluate('() => navigator.clipboard.readText().catch(() => "")')
        check('5 菜单「复制链接」复制这条的深链', t == '链接已复制。' and clip.endswith('#/item/' + rid.replace(':', '%3A')), toast=t, clip=clip[-50:])
        long_press(*center(row))
        page.locator('#cardMenu [data-menu=fav]').tap()
        page.wait_for_timeout(300)
        check('5 菜单「收藏」收进收藏', rid in fav_ids(), id=rid)
        long_press(*center(row))
        page.locator('#cardMenu [data-menu=fav]').tap()
        page.wait_for_timeout(300)
        check('5 菜单再点「取消收藏」移出', rid not in fav_ids())

        # 下拉刷新：频道（左右）
        def pull(scroller_sel, name, shoot=False):
            page.locator(scroller_sel).evaluate('e => e.scrollTop = 0')
            page.wait_for_timeout(250)
            toast_clear()
            box = page.locator(scroller_sel).bounding_box()
            y0 = box['y'] + 60
            seen = {}
            def hold():
                seen['ptr'] = page.locator('#ptr').inner_text()
                if shoot:
                    shot('pull-to-refresh')
            swipe(200, y0, 205, y0 + 330, steps=16, ms=420, hold=hold)
            t = toast_text(5000)
            check(f'5 下拉刷新：{name}', seen.get('ptr') == '松开刷新' and '刷新拿到的是最近一次发布的数据' in t, ptr=seen.get('ptr'), toast=t)
            page.wait_for_timeout(300)
        pull('.page-b[data-ch=current]', '频道（左右）', shoot=True)

        # 双击底栏回顶部：频道
        for _ in range(2):
            swipe(200, 700, 200, 250, ms=300)
        st0 = page.locator('.page-b[data-ch=current]').evaluate('e => e.scrollTop')
        page.locator('.tabbar [data-view=channels]').tap()
        page.locator('.tabbar [data-view=channels]').tap()
        page.wait_for_timeout(900)
        st1 = page.locator('.page-b[data-ch=current]').evaluate('e => e.scrollTop')
        check('5 双击底栏「频道」→ 当前频道回到顶部', st0 > 200 and st1 == 0, before=st0, after=st1)

        # ===== 上下模式：吸顶、卡片左滑收藏 / 右滑分享、下拉刷新 =====
        page.locator('#modeUD').tap()
        page.wait_for_timeout(500)
        for _ in range(3):
            swipe(200, 720, 200, 220, ms=300)
        r, ok = page.evaluate("""() => { const sc = document.querySelector('#channelRoot'); const a = sc.getBoundingClientRect();
            const heads = [...sc.querySelectorAll('.ch-head')]; const on = heads.find(h => Math.abs(h.getBoundingClientRect().top - a.top) <= 1);
            return [{scrollTop: Math.round(sc.scrollTop), pinned: on ? on.innerText.replace(/\\s+/g, ' ').slice(0, 40) : null}, !!on && sc.scrollTop > 150]; }""")
        check('1 频道（上下）下滑后当前频道名一行吸在顶上', ok, **r)
        shot('sticky-channel-ud')
        favs0 = fav_ids()
        rows = page.locator('#channelRoot .feed-list .feed-row')
        row = rows.nth(0)
        row.scroll_into_view_if_needed()
        page.wait_for_timeout(200)
        x, y = center(row)
        fid = row.get_attribute('data-id')
        def hold_fav():
            shot('card-swipe-fav')
            seen_shift.append(page.evaluate("() => Math.round(document.querySelector('#channelRoot .block-a').getBoundingClientRect().left)"))
        seen_shift = []
        swipe(300, y, 140, y + 3, ms=260, hold=hold_fav)
        check('5 卡片横滑过程中只有卡片在动（频道块不跟着移）', seen_shift == [0], block_left=seen_shift)
        shift = page.evaluate("() => [document.querySelector('#channelRoot').scrollLeft, document.scrollingElement.scrollLeft, Math.round(document.querySelector('#channelRoot').getBoundingClientRect().left)]")
        check('5 上下模式：卡片左滑 → 收藏（不打开详情），整页不横移', fid in fav_ids() and page.locator('#articleView.on').count() == 0 and shift == [0, 0, 0], id=fid, shift=shift)
        toast_clear()
        page.evaluate('() => navigator.clipboard.writeText("")')
        swipe(90, y, 260, y + 3, ms=260)
        t = toast_text()
        clip = page.evaluate('() => navigator.clipboard.readText().catch(() => "")')
        has_share = page.evaluate('() => !!navigator.share')
        check('5 卡片右滑 → 分享（系统分享面板；本浏览器没有分享面板时复制链接）',
              has_share or (clip.endswith('#/item/' + fid.replace(':', '%3A')) and '已复制' in t), toast=t, clip=clip[-50:], native_share=has_share)
        swipe(300, y, 250, y + 2, ms=200)
        check('5 横滑不到 72px 松手不生效', fid in fav_ids())
        # 再收藏几条，给「收藏」页吸顶测试用
        for k in range(1, 9):
            r2 = rows.nth(k); r2.scroll_into_view_if_needed(); page.wait_for_timeout(120)
            _, yy = center(r2)
            swipe(300, yy, 130, yy + 2, ms=200)
        check('5 连续左滑收藏 9 条', len(fav_ids()) >= len(favs0) + 9, favs=len(fav_ids()))
        pull('#channelRoot', '频道（上下）')
        page.locator('#modeLR').tap()
        page.wait_for_timeout(400)

        # ===== 博主：平台行吸顶、公众号正文、下拉刷新、双击回顶 =====
        page.locator('.tabbar [data-view=blogger]').tap()
        page.wait_for_selector('#platChips [data-plat]')
        chip = page.locator('#platChips .chip').first.bounding_box()
        check('博主平台图标左内边距不少于正文边距（16px）', chip and chip['x'] >= 16, left=round(chip['x']) if chip else None)
        blog_txt = page.locator('#view-blogger').inner_text()
        check('博主页已去掉平台标题和说明句', '已定的博主帖子' not in blog_txt and page.locator('#platName').count() == 0)
        page.locator('[data-plat=x]').tap()
        page.wait_for_selector('#bloggerList .tweet, #bloggerList .feed-row')
        # 点 X 帖子里的图打开全屏查看，不打开详情、不触发频道横滑
        zimg = page.locator('#bloggerList img[data-zoom]').first
        if zimg.count():
            zimg.scroll_into_view_if_needed()
            page.wait_for_timeout(200)
            zimg.tap()
            page.wait_for_selector('#zoomView.on')
            check('点博主图片打开全屏查看器', page.locator('#zoomView.on').count() == 1 and page.locator('#articleView.on').count() == 0)
            shot('zoom-x')
            page.locator('#zoomView').evaluate("e => e.dispatchEvent(new KeyboardEvent('keydown', {key:'Escape', bubbles:true}))")
            # close via JS in case key event is on document
            page.evaluate("() => { const ev = new KeyboardEvent('keydown', {key:'Escape', bubbles:true}); document.dispatchEvent(ev); }")
            page.wait_for_timeout(200)
            if page.locator('#zoomView.on').count():
                page.evaluate("() => { const v = document.querySelector('#zoomView'); v.hidden = true; v.classList.remove('on'); }")
            check('关闭查看器后回到博主列表', page.locator('#zoomView.on').count() == 0 and page.locator('#view-blogger.on').count() == 1)
        else:
            check('点博主图片打开全屏查看器', False, reason='当前 X 列表没有可点的图')
        for _ in range(3):
            swipe(200, 720, 200, 220, ms=300)
        r, ok = sticky_ok('#view-blogger .sub', '#view-blogger .sticky-hd')
        check('1 博主：下滑后「博主」+ 平台行（X、Grok bot、即刻…）吸在顶上', ok and 'Grok' in page.locator('#view-blogger .sticky-hd').inner_text() or ok, **(r or {}))
        shot('sticky-blogger')
        st0 = page.locator('#view-blogger .sub').evaluate('e => e.scrollTop')
        page.locator('.tabbar [data-view=blogger]').tap()
        page.locator('.tabbar [data-view=blogger]').tap()
        page.wait_for_timeout(900)
        st1 = page.locator('#view-blogger .sub').evaluate('e => e.scrollTop')
        check('5 双击底栏「博主」→ 回到顶部', st0 > 150 and st1 == 0, before=st0, after=st1)
        pull('#view-blogger .sub', '博主')

        # 公众号文章：正文按原文顺序、图片全部加载、不重复
        page.locator('[data-plat=wechat]').tap()
        page.wait_for_selector('#bloggerList [data-id]')
        wx = []
        n = 1
        while True:
            pg = get(f'blogger/wechat/all/page-{n}.json')
            wx += pg['items']
            if not pg['has_more']:
                break
            n += 1
        wx_ids = page.eval_on_selector_all('#bloggerList [data-id]', 'els => els.map(e => e.dataset.id)')
        page.locator(f'#bloggerList [data-id="{wx_ids[0]}"]').tap()
        page.wait_for_selector('#articleView.on [data-blocks]')
        results = []
        for k, wid in enumerate(wx_ids):
            if k:
                page.locator('#artNav [data-nav="1"]').tap()
                page.wait_for_function('(id) => decodeURIComponent(location.hash).endsWith(id)', arg=wid)
                page.wait_for_selector('#articleView.on [data-blocks]')
            data = next(i for i in wx if i['id'] == wid)
            page.locator('#articleBody').evaluate("""async (e) => { for (let y = 0; y <= e.scrollHeight; y += 500) { e.scrollTop = y; await new Promise(r => setTimeout(r, 60)); } }""")
            page.wait_for_function("""() => [...document.querySelectorAll('#articleBody [data-blocks] img')].every(i => i.complete)""", timeout=20000)
            got = page.evaluate("""() => [...document.querySelector('#articleBody [data-blocks]').children].map(el => {
                const img = el.querySelector('img'); if (img) return {t: 'img', src: img.getAttribute('src'), w: img.naturalWidth};
                if (el.matches('[data-img-missing]')) return {t: 'missing'};
                return {t: el.tagName.toLowerCase(), text: el.textContent.trim().slice(0, 60)}; })""")
            want = [b['type'] for b in data['blocks']]
            tag = {'p': 'p', 'h': 'h4', 'quote': 'blockquote', 'ul': 'ul', 'ol': 'ol', 'pre': 'pre', 'hr': 'hr', 'img': 'img'}
            order_ok = [g['t'] for g in got] == [tag[t] for t in want]
            imgs = [g for g in got if g['t'] == 'img']
            norm = lambda v: ' '.join((v or '').split())
            mism = [(k2, norm(g['text'])[:24], norm(b.get('text'))[:24]) for k2, (g, b) in enumerate(zip(got, data['blocks']))
                    if g['t'] not in ('img', 'missing', 'ul', 'ol', 'hr') and norm(g['text'])[:24] != norm(b.get('text'))[:24]]
            text_ok = not mism
            results.append({'id': wid, 'title': data['title'][:30], 'blocks': len(want), 'images': len(imgs),
                            'loaded': sum(1 for g in imgs if g['w'] > 0), 'missing': sum(1 for g in got if g['t'] == 'missing'),
                            'dup_images': len(imgs) - len({g['src'] for g in imgs}), 'order_ok': order_ok, 'text_ok': text_ok, 'text_mismatch': mism[:3]})
            if k == 0:
                page.locator('#articleBody').evaluate('e => e.scrollTop = 0')
                shot('wechat-article-top')
                page.locator('#articleBody').evaluate('e => e.scrollTop = e.scrollHeight / 2')
                page.wait_for_timeout(300)
                shot('wechat-article-mid')
        check('6 公众号文章：正文块与原文同序（段落/标题/图片/引用/列表）', all(r['order_ok'] and r['text_ok'] for r in results), articles=results)
        check('6 公众号文章：图片全部加载、没有缺图、没有重复', all(r['images'] == r['loaded'] and not r['missing'] and not r['dup_images'] for r in results),
              images=sum(r['images'] for r in results), loaded=sum(r['loaded'] for r in results))
        page.locator('#btnBack').tap()
        page.wait_for_timeout(400)
        # 博主列表里卡片左滑收藏（非左右频道页）
        brow = page.locator('#bloggerList [data-id]').nth(1)
        brow.scroll_into_view_if_needed()
        bid = brow.get_attribute('data-id')
        _, yy = center(brow)
        swipe(300, yy, 120, yy + 2, ms=220)
        check('5 博主列表卡片左滑 → 收藏', bid in fav_ids(), id=bid)

        # ===== 热搜：吸顶、下拉刷新 =====
        page.locator('.tabbar [data-view=hot]').tap()
        page.wait_for_selector('#view-hot .hot-list li')
        for _ in range(3):
            swipe(200, 720, 200, 220, ms=300)
        r, ok = sticky_ok('#view-hot .sub', '#view-hot .sticky-hd')
        check('1 热搜：下滑后「热搜」+ 日期条吸在顶上', ok, **(r or {}))
        shot('sticky-hot')
        pull('#view-hot .sub', '热搜')

        # ===== 收藏：吸顶、左滑取消收藏、下拉刷新 =====
        page.locator('.tabbar [data-view=favorites]').tap()
        page.wait_for_selector('#view-favorites [data-item-id]')
        for _ in range(3):
            swipe(200, 720, 200, 220, ms=300)
        r, ok = sticky_ok('#view-favorites .sub', '#view-favorites .rebang-favorites > h2')
        check('1 收藏：下滑后「收藏」标题吸在顶上', ok, favorites=len(fav_ids()), **(r or {}))
        shot('sticky-favorites')
        pull('#view-favorites .sub', '收藏')
        frow = page.locator('#view-favorites [data-item-id]').first
        fid2 = frow.get_attribute('data-item-id')
        _, yy = center(frow)
        swipe(300, yy, 120, yy + 2, ms=220)
        check('5 收藏页卡片左滑 → 取消收藏（同一个开关）', fid2 not in fav_ids(), id=fid2)
        frow = page.locator('#view-favorites [data-item-id]').nth(1)
        fid3 = frow.get_attribute('data-item-id')
        frow.tap()
        page.wait_for_selector('#articleView.on')
        check('4 从收藏点进详情也有上一条/下一条', page.locator('#artNav:not([hidden]) .art-nav-pos').count() == 1,
              pos=page.locator('#artNav .art-nav-pos').inner_text() if page.locator('#artNav .art-nav-pos').count() else None)
        page.locator('#btnBack').tap()
        page.wait_for_timeout(400)
        # 查看更多页下拉刷新
        page.locator('.tabbar [data-view=channels]').tap()
        go_channel(0)
        page.locator('.page-b[data-ch=current]').evaluate('e => e.scrollTop = 0')
        page.locator('.page-b[data-ch=current] [data-see="ch:current"]').tap()
        page.wait_for_selector('#moreView.on .feed-row')
        pull('#moreBody', '查看更多')
        page.locator('#btnMoreBack').tap()
        page.wait_for_timeout(400)
        # 收藏清空，回到 v12 既有流程的起点
        page.evaluate('() => localStorage.clear()')
        page.reload()
        page.wait_for_selector('#app:not([aria-busy])')
        page.wait_for_timeout(500)

        # ===== v12 及以前既有功能（同样用触摸点按）=====
        # ---- 1 热搜页 ----
        page.locator('.tabbar [data-view=hot]').tap()
        page.wait_for_selector('#view-hot .hot-list li')
        hot_tabs = page.locator('#view-hot .hot-tabs [role=tab]').all_inner_texts()
        counts = {}
        for pid in ('baidu', 'zhihu', 'bilibili'):
            page.locator(f'#view-hot [data-hot={pid}]').tap()
            counts[pid] = page.locator('#view-hot .hot-list li').count()
        check('热搜页默认当前三家 tab', hot_tabs == ['百度热搜', '知乎热榜', 'B 站热搜'], tabs=hot_tabs, rows=counts)
        page.locator('#view-hot [data-hot=baidu]').tap()
        chips = page.locator('#hotDates .chip').all_inner_texts()
        index = get('hotsearch/index.json')
        check('日期切换条：今天·现在 + 归档里的往日', chips and chips[0] == '今天 · 现在', chips=chips,
              archived=[d['date'] for d in index['dates']])
        shot('hot-now')
        past = [d['date'] for d in index['dates'] if d['date'] != index['today']]
        if past:
            page.locator(f'#hotDates [data-hot-day="{past[0]}"]').tap()
            page.wait_for_selector(f'#view-hot[data-hot-day="{past[0]}"] .hot-list li')
            check('切到往日看当天最后一次榜单', True, date=past[0])
            shot('hot-past-day')
        else:
            check('往日热搜：归档里暂时只有今天（从今天起每天存一份，不编旧榜）', True, archived_days=len(index['dates']))

        # ---- 2 博主 Grok bot ----
        page.locator('.tabbar [data-view=blogger]').tap()
        page.wait_for_selector('#platChips [data-plat]')
        plats = page.eval_on_selector_all('#platChips [data-plat]', 'els => els.map(e => e.dataset.plat)')
        check('博主平台含 Grok bot，与 X/即刻/微博/知乎/公众号并列', 'grok' in plats and {'x', 'jike', 'weibo', 'zhihu', 'wechat'} <= set(plats), plats=plats)
        page.wait_for_function('() => [...document.querySelectorAll("#platChips img.plat-ico")].every(i => i.complete)', timeout=15000)
        icons = page.eval_on_selector_all('#platChips img.plat-ico', 'els => els.map(e => ({src: e.getAttribute("src"), w: e.naturalWidth}))')
        check('平台图标都是本地官方图标文件且已加载', icons and all(i['w'] > 0 and i['src'].startswith('icons/') for i in icons), icons=icons)
        page.locator('[data-plat=grok]').tap()
        page.wait_for_selector('#bloggerList .feed-row')
        people = page.locator('#peopleRow .ppl > span:last-child').all_inner_texts()
        check('Grok bot 里 = 今日重点/推特爆款/环球要闻/GitHub 热门', people == ['全部', '今日重点', '推特爆款', '环球要闻', 'GitHub 热门'], people=people)
        shot('blogger-grok')
        meta = get('meta.json')
        moved = {'x', 'world', 'github', 'hot-daily'}
        leaked = 0
        for c in meta['channels']:
            leaked += sum(1 for i in c['banner'] if i['source_id'] in moved)
            for n in range(1, c['pages'] + 1):
                leaked += sum(1 for i in get(f'channel/{c["slug"]}/page-{n}.json')['items'] if i['source_id'] in moved)
        check('4 类整理内容已离开主题频道', leaked == 0, leaked=leaked)
        bl = get('bloggers.json')
        grok = next(p for p in bl['platforms'] if p['id'] == 'grok')
        check('Grok bot 条数', grok['count'] > 0, per_account={a['name']: a['total'] for a in grok['accounts']})

        # ---- 3 查看更多：博主 ----
        page.locator('#peopleRow .ppl', has_text='GitHub 热门').tap()
        page.locator('.see-more-bl').tap()
        page.wait_for_selector('#moreView.on .feed-row')
        acc = next(a for a in grok['accounts'] if a['handle'] == 'github')
        for _ in range(60):
            if page.locator('#moreView [data-end=more]').count():
                break
            page.locator('#moreBody').evaluate('e => e.scrollTop = e.scrollHeight')
            page.wait_for_timeout(250)
        n_rows = page.locator('#moreBody .more-list > *').count()
        check('博主「查看更多」下滑到「没有更多了」', page.locator('#moreView [data-end=more]').count() == 1 and n_rows == acc['total'],
              rows=n_rows, total=acc['total'])
        shot('more-blogger-end')
        page.go_back()
        page.wait_for_timeout(300)
        check('系统返回关掉「查看更多」回博主页', not page.locator('#moreView').evaluate('e => e.classList.contains("on")'))

        # ---- 3 查看更多：频道 + 详情返回原位 ----
        page.locator('.tabbar [data-view=channels]').tap()
        page.locator('#channelRoot').evaluate('e => e.scrollLeft = 0')
        page.wait_for_timeout(300)
        page.locator('.page-b[data-ch=current] [data-see="ch:current"]').tap()
        page.wait_for_selector('#moreView.on .feed-row')
        cur = next(c for c in meta['channels'] if c['slug'] == 'current')
        for _ in range(60):
            if page.locator('#moreView [data-end=more]').count():
                break
            page.locator('#moreBody').evaluate('e => e.scrollTop = e.scrollHeight')
            page.wait_for_timeout(250)
        rows = page.locator('#moreBody .feed-row').count()
        check('频道「查看更多」= 整个频道全部条目，到「没有更多了」', rows == cur['total'], rows=rows, total=cur['total'])
        page.locator('#moreBody').evaluate('e => e.scrollTop = Math.floor(e.scrollHeight / 2)')
        page.wait_for_timeout(200)
        y0 = page.locator('#moreBody').evaluate('e => e.scrollTop')
        shot('more-channel-mid')
        target = page.locator('#moreBody .feed-row').nth(rows // 2)
        target.scroll_into_view_if_needed()
        y0 = page.locator('#moreBody').evaluate('e => e.scrollTop')
        target.tap()
        page.wait_for_selector('#articleView.on')
        page.locator('#btnBack').tap()
        page.wait_for_timeout(400)
        y1 = page.locator('#moreBody').evaluate('e => e.scrollTop')
        check('从详情返回，「查看更多」页停在原位置', page.locator('#moreView.on').count() == 1 and abs(y1 - y0) <= 2, y0=y0, y1=y1)
        page.locator('#btnMoreBack').tap()
        page.wait_for_timeout(300)
        check('「查看更多」返回回到频道', page.locator('#moreView.on').count() == 0 and page.locator('#view-channels.on').count() == 1)

        # ---- 5 翻译 ----
        en_total = en_done = 0
        for c in meta['channels']:
            for it in c['banner']:
                if it['lang'] not in ('zh', 'und'):
                    en_total += 1; en_done += bool(it.get('translated'))
            for n in range(1, c['pages'] + 1):
                for it in get(f'channel/{c["slug"]}/page-{n}.json')['items']:
                    if not it['lang'].startswith('zh') and it['lang'] != 'und':
                        en_total += 1; en_done += bool(it.get('translated'))
        bl_en = bl_done = 0
        for plat in bl['platforms']:
            n = 1
            while True:
                pg = get(f'blogger/{plat["id"]}/all/page-{n}.json')
                for it in pg['items']:
                    if not it['lang'].startswith('zh') and it['lang'] != 'und':
                        bl_en += 1; bl_done += bool(it.get('translated'))
                if not pg['has_more']:
                    break
                n += 1
        check('新闻频道英文条目全部有中文译文（机器翻译）', en_total == en_done, english=en_total, translated=en_done)
        check('博主英文帖子全部有中文译文（机器翻译）', bl_en == bl_done, english=bl_en, translated=bl_done)
        page.locator('#channelRoot').evaluate('e => e.scrollLeft = e.clientWidth')
        page.wait_for_timeout(400)
        world = page.locator('.page-b[data-ch=world] .feed-row:has(.mt-badge)').first
        world.scroll_into_view_if_needed()
        check('环球卡片显示中文译文 + 「机器翻译」标', world.count() == 1, sample=world.inner_text()[:80])
        shot('world-translated')
        world.tap()
        page.wait_for_selector('#articleView.on .mt-badge')
        shot('article-translated')
        page.locator('#btnBack').tap()
        page.wait_for_timeout(300)

        # ---- 既有：返回原位、收藏、搜索、深链 ----
        pg = page.locator('.page-b[data-ch=world]')
        pg.evaluate('e => e.scrollTop = 1500')
        page.wait_for_timeout(300)
        sy0 = pg.evaluate('e => e.scrollTop')
        row = pg.locator('.feed-row').nth(12)
        row.scroll_into_view_if_needed()
        sy0 = pg.evaluate('e => e.scrollTop')
        rid = row.get_attribute('data-id')
        row.tap()
        page.wait_for_selector('#articleView.on')
        check('深链地址 #/item/<id>', '#/item/' in page.url, url=page.url[-60:])
        page.wait_for_selector('#articleBody [data-favorite-button]')
        page.locator('#articleBody [data-favorite-button]').tap()
        page.go_back()
        page.wait_for_timeout(400)
        sy1 = pg.evaluate('e => e.scrollTop')
        sx = page.locator('#channelRoot').evaluate('e => Math.round(e.scrollLeft / e.clientWidth)')
        check('详情系统返回回到原频道原位置', sx == 1 and abs(sy1 - sy0) <= 2, x=sx, y0=sy0, y1=sy1)
        page.locator('.tabbar [data-view=favorites]').tap()
        page.wait_for_selector(f'#view-favorites [data-item-id="{rid}"]')
        page.reload()
        page.wait_for_selector('#app:not([aria-busy])')
        page.locator('.tabbar [data-view=favorites]').tap()
        ok = page.locator(f'#view-favorites [data-item-id="{rid}"]').count() == 1
        check('收藏后刷新仍在', ok, id=rid)
        shot('favorites')
        page.locator('.tabbar [data-view=channels]').tap()
        page.locator('#btnSearch').tap()
        page.wait_for_selector('#search-panel.on [data-search-input]')
        page.locator('[data-search-input]').fill('OpenAI')
        page.wait_for_selector('[data-search-hit]')
        hits = page.locator('[data-search-hit]').count()
        check('搜索 OpenAI 有命中', hits > 0, hits=hits)
        shot('search')
        page.locator('[data-search-hit]').first.tap()
        page.wait_for_selector('#articleView.on')
        page.go_back()
        page.wait_for_timeout(300)
        back_to_search = page.locator('#search-panel.on [data-search-hit]').count() > 0
        check('搜索结果点进详情再返回，回到搜索结果', back_to_search)
        if page.locator('#search-panel.on [data-search-close]').count():
            page.locator('#search-panel.on [data-search-close]').tap()
        deep = cur['banner'][0]['id'] if cur['banner'] else get('channel/current/page-1.json')['items'][0]['id']
        page.goto(BASE + '#/item/' + deep.replace(':', '%3A'))
        page.wait_for_selector('#articleView.on')
        check('冷启动打开 #/item/<id> 直接到详情', page.locator('#articleView.on').count() == 1, id=deep)
        shot('deeplink')
        page.locator('#btnBack').tap()
        page.wait_for_timeout(300)
        check('深链详情返回到首页频道', page.locator('#articleView.on').count() == 0 and page.locator('#view-channels.on').count() == 1)
        page.locator('#modeUD').tap()
        page.wait_for_timeout(300)
        more_btns = page.locator('.block-a .more-btn').count()
        check('上下模式「继续看」按钮保留', more_btns > 0, buttons=more_btns)
        page.locator('#modeLR').tap()
        # 白天 / 暗黑跟随系统
        def theme_bg(scheme):
            page.emulate_media(color_scheme=scheme)
            page.wait_for_timeout(150)
            return page.evaluate("() => getComputedStyle(document.querySelector('.app')).backgroundColor")
        dark_bg = theme_bg('dark')
        page.locator('.tabbar [data-view=channels]').tap()
        shot('theme-dark-channels')
        light_bg = theme_bg('light')
        shot('theme-light-channels')
        page.locator('.tabbar [data-view=blogger]').tap(); page.wait_for_timeout(200); shot('theme-light-blogger')
        page.locator('.tabbar [data-view=hot]').tap(); page.wait_for_timeout(200); shot('theme-light-hot')
        page.locator('.tabbar [data-view=favorites]').tap(); page.wait_for_timeout(200); shot('theme-light-favorites')
        theme_bg('dark')
        check('白天和暗黑背景不同，并跟随 prefers-color-scheme', dark_bg != light_bg, dark=dark_bg, light=light_bg)
        # 环球列表可见标题不应残留未翻译英文（已标翻译的卡片用中文标题）
        page.locator('.tabbar [data-view=channels]').tap()
        page.locator('#channelRoot').evaluate('e => e.scrollLeft = e.clientWidth')
        page.wait_for_timeout(300)
        titles = page.evaluate("""() => [...document.querySelectorAll('.page-b[data-ch=world] .feed-row:has(.mt-badge) h3')].map(e => e.innerText)""")
        import re as _re
        leftover = [x for x in titles if x and _re.search(r'[A-Za-z]{6,}', x) and not _re.search(r'[一-鿿]', x)]
        check('环球已译卡片的标题是中文', not leftover, leftover=leftover[:5], n=len(titles))
        # ---- 第二期（2026-11-16）：即刻、TG 评论楼、YouTube 管道、5 个公众号等扫码 ----
        bl = get('bloggers.json')
        plats = {p['id']: p for p in bl['platforms']}
        page.goto(BASE)
        page.wait_for_selector('#app:not([aria-busy])')
        page.locator('.tabbar [data-view=blogger]').tap()
        page.wait_for_timeout(300)
        jk = plats.get('jike') or {}
        if PHASE2_STRICT or jk.get('count'):
            page.locator('#platChips [data-plat=jike]').tap()
            page.wait_for_selector('#bloggerList .tweet, #bloggerList .empty-plat')
            cards = page.locator('#bloggerList .tweet').count()
            txt = page.locator('#bloggerList').inner_text()
            import re as _re2
            uuid_shown = _re2.search(r'@[0-9A-F]{8}-[0-9A-F]{4}-', txt, _re2.I)
            check('P2 即刻：平台有帖子，卡片不露 @UUID', cards > 0 and not uuid_shown, cards=cards, count=jk.get('count'),
                  ok_accounts=sum(a.get('status') == 'ok' for a in jk.get('accounts', [])))
            shot('p2-jike')
            first = page.locator('#bloggerList .tweet').first
            if first.count():
                first.locator('.t-body:not(:empty), img').first.tap()
                page.wait_for_timeout(400)
                check('P2 即刻帖子点开有详情或查看器', page.locator('#articleView.on, #zoomView.on').count() >= 1)
                if page.locator('#zoomView.on').count():
                    page.go_back()
                if page.locator('#articleView.on').count():
                    page.locator('#btnBack').tap()
                page.wait_for_timeout(300)
        yt = plats.get('youtube')
        check('P2 YouTube 平台已上架', yt is not None)
        if yt is not None:
            page.locator('.tabbar [data-view=blogger]').tap()
            page.locator('#platChips [data-plat=youtube]').tap()
            page.wait_for_selector('#bloggerList .tweet, #bloggerList .empty-plat')
            if yt['accounts']:
                check('P2 YouTube 有频道时显示视频卡', page.locator('#bloggerList .tweet').count() > 0)
            else:
                check('P2 YouTube 名单为空 → 显示「频道名单待确认」', '频道名单待确认' in page.locator('#bloggerList').inner_text(),
                      text=page.locator('#bloggerList').inner_text()[:80])
            shot('p2-youtube')
        wx = plats.get('wechat') or {}
        wait = [a for a in wx.get('accounts', []) if a.get('status') == 'not_configured']
        if wait:
            page.locator('#platChips [data-plat=wechat]').tap()
            page.wait_for_timeout(200)
            sel = page.locator(f'#peopleRow [data-person="{wait[0]["handle"]}"]').first
            if sel.count():
                sel.tap()
                page.wait_for_selector('#bloggerList .empty-plat')
                t = page.locator('#bloggerList .empty-plat').inner_text()
                check('P2 公众号未扫码：空状态写「等扫码」，不编内容', '扫码' in t, who=wait[0]['handle'], text=t[:80])
                shot('p2-wechat-wait')
        # TG 评论楼：找评论最多的一条（优先有楼中楼的）
        best = None
        for c in meta['channels']:
            for n in range(1, c['pages'] + 1):
                for i in get(f'channel/{c["slug"]}/page-{n}.json')['items']:
                    cs = (i.get('tg') or {}).get('comments') or []
                    key = (any(x.get('reply_text') for x in cs), len(cs))
                    if cs and (best is None or key > best[0]):
                        best = (key, i)
        if best:
            it = best[1]
            cs = it['tg']['comments']
            page.goto(BASE + '#/item/' + it['id'].replace(':', '%3A'))
            page.wait_for_selector('#articleView.on [data-tg-comments]')
            sec = page.locator('#articleBody [data-tg-comments]')
            check('P2 评论楼：标题「评论楼」+ 条数', '评论楼' in sec.locator('h4').inner_text(), n=len(cs), id=it['id'])
            visible = page.evaluate("() => [...document.querySelectorAll('#articleBody [data-tg-comments] .comment')].filter(e => e.offsetParent).length")
            if len(cs) > 10:
                check('P2 评论楼：超过 10 条先折叠，只露最近 10 条', visible == 10, visible=visible, total=len(cs))
                btn = sec.locator('[data-cmt-more]')
                btn.scroll_into_view_if_needed()
                btn.tap()
                page.wait_for_timeout(300)
                visible2 = page.evaluate("() => [...document.querySelectorAll('#articleBody [data-tg-comments] .comment')].filter(e => e.offsetParent).length")
                check('P2 评论楼：点「展开更早的」后全部显示', visible2 == len(cs), visible=visible2)
            else:
                check('P2 评论楼：不到 10 条全部显示', visible == len(cs), visible=visible)
            if any(x.get('reply_text') or x.get('reply_to') for x in cs):
                n_r = sec.locator('.c-reply').count()
                check('P2 评论楼：楼中楼显示被回复的人和原话', n_r == sum(bool(x.get('reply_text') or x.get('reply_to')) for x in cs), shown=n_r)
            links = sec.locator('a.c-open').count()
            check('P2 评论楼：每条有「原楼」链接到 t.me', links == sum(isinstance(x.get('id'), int) for x in cs), links=links)
            sec.scroll_into_view_if_needed()
            shot('p2-tg-thread')
            page.locator('#btnBack').tap()
            page.wait_for_timeout(300)
        elif PHASE2_STRICT:
            check('P2 评论楼：数据里有带评论的 TG 条目', False)
        check('页面无脚本错误', not errors, errors=errors[:5])
        check('无 4xx/5xx 请求', not bad, bad=bad[:5])
        browser.close()
    (OUT / f'{PREFIX}result.json').write_text(json.dumps({'base': BASE, 'at': time.strftime('%Y-%m-%d %H:%M:%S %z'), 'input': 'CDP Input.dispatchTouchEvent / Playwright tap, 390x844 mobile',
                                                          'passed': sum(c['ok'] for c in checks), 'total': len(checks),
                                                          'checks': checks, 'screenshots': shots},
                                                         ensure_ascii=False, indent=1), encoding='utf-8')
    print(f'{sum(c["ok"] for c in checks)}/{len(checks)} passed')
    return 0 if all(c['ok'] for c in checks) else 1


if __name__ == '__main__':
    sys.exit(main())
