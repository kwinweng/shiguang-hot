"""集成验收：从真实入口（站点首页）在 390x844 手机尺寸实测 2026-11-15 21:26 的 5 处改版 + 既有功能。

用法：python3 docs/rebang-v1/evidence/integration/capture.py <站点根 URL> [截图前缀]
  本地：先 python3 -m http.server 在构建目录起服务；线上：传预览地址。
输出：同目录 <前缀>NN-*.png 截图与 <前缀>result.json（每项检查真/假与数字）。任一检查失败退出码 1。
"""
import json
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = sys.argv[1].rstrip('/') + '/'
PREFIX = sys.argv[2] if len(sys.argv) > 2 else ''
OUT = Path(__file__).resolve().parent
checks, shots = [], []


def check(name, ok, **detail):
    checks.append({'check': name, 'ok': bool(ok), **detail})
    print(('PASS ' if ok else 'FAIL ') + name, detail if detail else '')


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch()
        ctx = browser.new_context(viewport={'width': 390, 'height': 844}, device_scale_factor=2, is_mobile=True, has_touch=True)
        page = ctx.new_page()
        errors = []
        page.on('pageerror', lambda e: errors.append(str(e)))
        bad = []
        page.on('response', lambda r: r.status >= 400 and bad.append(f'{r.status} {r.url}'))

        def shot(name):
            path = OUT / f'{PREFIX}{len(shots) + 1:02d}-{name}.png'
            page.screenshot(path=str(path))
            shots.append(path.name)

        def get(rel):
            return page.evaluate('async (u) => (await fetch(u)).json()', BASE + 'data/' + rel)

        page.goto(BASE)
        page.wait_for_selector('#app:not([aria-busy])')
        page.wait_for_timeout(600)
        note = page.locator('#previewNote span').inner_text() if page.locator('#previewNote').is_visible() else ''
        check('顶部说明不再有「英文还没接机器翻译」', '机器翻译' not in note, note=note)
        tabs = [t.strip() for t in page.locator('.tabbar button').all_inner_texts()]
        check('底栏 = 频道/博主/热搜/收藏', tabs == ['频道', '博主', '热搜', '收藏'], tabs=tabs)
        check('历史页已去掉', page.locator('#view-history').count() == 0)
        check('频道里没有热搜块（时事 banner 区）', page.locator('#channelRoot .hot').count() == 0)
        shot('home-current')

        # ---- 1 热搜页 ----
        page.locator('.tabbar [data-view=hot]').click()
        page.wait_for_selector('#view-hot .hot-list li')
        hot_tabs = page.locator('#view-hot .hot-tabs [role=tab]').all_inner_texts()
        counts = {}
        for pid in ('baidu', 'zhihu', 'bilibili'):
            page.locator(f'#view-hot [data-hot={pid}]').click()
            counts[pid] = page.locator('#view-hot .hot-list li').count()
        check('热搜页默认当前三家 tab', hot_tabs == ['百度热搜', '知乎热榜', 'B 站热搜'], tabs=hot_tabs, rows=counts)
        page.locator('#view-hot [data-hot=baidu]').click()
        chips = page.locator('#hotDates .chip').all_inner_texts()
        index = get('hotsearch/index.json')
        check('日期切换条：今天·现在 + 归档里的往日', chips and chips[0] == '今天 · 现在', chips=chips,
              archived=[d['date'] for d in index['dates']])
        shot('hot-now')
        past = [d['date'] for d in index['dates'] if d['date'] != index['today']]
        if past:
            page.locator(f'#hotDates [data-hot-day="{past[0]}"]').click()
            page.wait_for_selector(f'#view-hot[data-hot-day="{past[0]}"] .hot-list li')
            check('切到往日看当天最后一次榜单', True, date=past[0])
            shot('hot-past-day')
        else:
            check('往日热搜：归档里暂时只有今天（从今天起每天存一份，不编旧榜）', True, archived_days=len(index['dates']))

        # ---- 2 博主 Grok bot ----
        page.locator('.tabbar [data-view=blogger]').click()
        page.wait_for_selector('#platChips [data-plat]')
        plats = page.eval_on_selector_all('#platChips [data-plat]', 'els => els.map(e => e.dataset.plat)')
        check('博主平台含 Grok bot，与 X/即刻/微博/知乎/公众号并列', 'grok' in plats and {'x', 'jike', 'weibo', 'zhihu', 'wechat'} <= set(plats), plats=plats)
        page.wait_for_function('() => [...document.querySelectorAll("#platChips img.plat-ico")].every(i => i.complete)', timeout=15000)
        icons = page.eval_on_selector_all('#platChips img.plat-ico', 'els => els.map(e => ({src: e.getAttribute("src"), w: e.naturalWidth}))')
        check('平台图标都是本地官方图标文件且已加载', icons and all(i['w'] > 0 and i['src'].startswith('icons/') for i in icons), icons=icons)
        page.locator('[data-plat=grok]').click()
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
        page.locator('#peopleRow .ppl', has_text='GitHub 热门').click()
        page.locator('.see-more-bl').click()
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
        page.locator('.tabbar [data-view=channels]').click()
        page.locator('#channelRoot').evaluate('e => e.scrollLeft = 0')
        page.wait_for_timeout(300)
        page.locator('.page-b[data-ch=current] [data-see="ch:current"]').click()
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
        target.click()
        page.wait_for_selector('#articleView.on')
        page.locator('#btnBack').click()
        page.wait_for_timeout(400)
        y1 = page.locator('#moreBody').evaluate('e => e.scrollTop')
        check('从详情返回，「查看更多」页停在原位置', page.locator('#moreView.on').count() == 1 and abs(y1 - y0) <= 2, y0=y0, y1=y1)
        page.locator('#btnMoreBack').click()
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
        world.click()
        page.wait_for_selector('#articleView.on .mt-badge')
        shot('article-translated')
        page.locator('#btnBack').click()
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
        row.click()
        page.wait_for_selector('#articleView.on')
        check('深链地址 #/item/<id>', '#/item/' in page.url, url=page.url[-60:])
        page.wait_for_selector('#articleBody [data-favorite-button]')
        page.locator('#articleBody [data-favorite-button]').click()
        page.go_back()
        page.wait_for_timeout(400)
        sy1 = pg.evaluate('e => e.scrollTop')
        sx = page.locator('#channelRoot').evaluate('e => Math.round(e.scrollLeft / e.clientWidth)')
        check('详情系统返回回到原频道原位置', sx == 1 and abs(sy1 - sy0) <= 2, x=sx, y0=sy0, y1=sy1)
        page.locator('.tabbar [data-view=favorites]').click()
        page.wait_for_selector(f'#view-favorites [data-item-id="{rid}"]')
        page.reload()
        page.wait_for_selector('#app:not([aria-busy])')
        page.locator('.tabbar [data-view=favorites]').click()
        ok = page.locator(f'#view-favorites [data-item-id="{rid}"]').count() == 1
        check('收藏后刷新仍在', ok, id=rid)
        shot('favorites')
        page.locator('.tabbar [data-view=channels]').click()
        page.locator('#btnSearch').click()
        page.wait_for_selector('#search-panel.on [data-search-input]')
        page.locator('[data-search-input]').fill('OpenAI')
        page.wait_for_selector('[data-search-hit]')
        hits = page.locator('[data-search-hit]').count()
        check('搜索 OpenAI 有命中', hits > 0, hits=hits)
        shot('search')
        page.locator('[data-search-hit]').first.click()
        page.wait_for_selector('#articleView.on')
        page.go_back()
        page.wait_for_timeout(300)
        back_to_search = page.locator('#search-panel.on [data-search-hit]').count() > 0
        check('搜索结果点进详情再返回，回到搜索结果', back_to_search)
        if page.locator('#search-panel.on [data-search-close]').count():
            page.locator('#search-panel.on [data-search-close]').click()
        deep = cur['banner'][0]['id'] if cur['banner'] else get('channel/current/page-1.json')['items'][0]['id']
        page.goto(BASE + '#/item/' + deep.replace(':', '%3A'))
        page.wait_for_selector('#articleView.on')
        check('冷启动打开 #/item/<id> 直接到详情', page.locator('#articleView.on').count() == 1, id=deep)
        shot('deeplink')
        page.locator('#btnBack').click()
        page.wait_for_timeout(300)
        check('深链详情返回到首页频道', page.locator('#articleView.on').count() == 0 and page.locator('#view-channels.on').count() == 1)
        page.locator('#modeUD').click()
        page.wait_for_timeout(300)
        more_btns = page.locator('.block-a .more-btn').count()
        check('上下模式「继续看」按钮保留', more_btns > 0, buttons=more_btns)
        page.locator('#modeLR').click()
        check('页面无脚本错误', not errors, errors=errors[:5])
        check('无 4xx/5xx 请求', not bad, bad=bad[:5])
        browser.close()
    (OUT / f'{PREFIX}result.json').write_text(json.dumps({'base': BASE, 'at': time.strftime('%Y-%m-%d %H:%M:%S %z'),
                                                          'passed': sum(c['ok'] for c in checks), 'total': len(checks),
                                                          'checks': checks, 'screenshots': shots},
                                                         ensure_ascii=False, indent=1), encoding='utf-8')
    print(f'{sum(c["ok"] for c in checks)}/{len(checks)} passed')
    return 0 if all(c['ok'] for c in checks) else 1


if __name__ == '__main__':
    sys.exit(main())
