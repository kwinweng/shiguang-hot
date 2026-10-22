"""Offline v0.3 acceptance: 48 screens, both themes, production renderer.

Uses the approved prototype's content/images as deterministic visual fixtures.
No network requests leave Chromium. Production data is checked separately.
"""
import argparse
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
import mimetypes
from pathlib import Path
import threading
from urllib.parse import urlsplit

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
MOBILE = 'today today-bottom news news-quick news-bottom hot play play-bottom buy buy-bottom fav fav-bottom mag detail-img detail-text search-init search-result search-empty loading empty error cal cal-empty columns columns-tag src-github src-x src-world src-channel drawer capsule history lightbox ptr-pull ptr-loading toast-action toast-error offline offline-none first pwa'.split()
DESKTOP = 'd-today d-news d-hot d-play d-buy d-fav d-pwa'.split()


def fixture(reference):
    raw = (reference / 'data.js').read_text().split('window.D=', 1)[1].strip().rstrip(';')
    content = json.loads(raw)
    result = dict(today='2026-10-22', updated='2026-10-22T17:10:00+08:00',
                  days=[f'2026-10-{i:02}' for i in range(3, 23)], news=[], cards=[], magazines=[], sources=[])
    for key, kind in [('news', 'news'), ('gh', 'play'), ('buy', 'buy'), ('mag', 'mag')]:
        for i, item in enumerate(content[key]):
            record = dict(id=f'{kind}-{i}', title=item['t'], summary=item.get('x', ''),
                          source=item.get('s', '每日精选'), source_id='github' if kind == 'play' else 'world' if i % 3 == 0 else 'x' if i % 3 == 1 else 'channel',
                          category=item.get('c', '科技'), time=f'2026-10-22T{item.get("tm", "17:10")}:00+08:00' if len(item.get('tm', '17:10')) == 5 else '2026-10-22T17:10:00+08:00',
                          day='2026-10-22', image='qa-img/' + item['img'] if item.get('img') else '',
                          url='https://example.test/original', kind=kind,
                          heat=1000-i*7, change=-1 if i % 3 == 0 else 1,
                          spark='0,5 12,10 24,8 36,16 48,12 60,20 70,18' if i % 3 == 0 else '0,20 12,17 24,19 36,10 48,14 60,4 70,8',
                          stars='2.8k', language='Python')
            result['news' if kind == 'news' else 'magazines' if kind == 'mag' else 'cards'].append(record)
    # Preserve all seven already approved no-image palettes in the visual catalogue.
    for kind, category, title in [('play','exhibitions','「流动的边界」群展（10.24–2027.2.28）'),('play','apps','Raycast 2.0 测评'),('play','stargazing','金星合月：日落后西南方低空'),('play','shows','本周剧集精选'),('play','games','周末游戏精选'),('buy','apple','Apple Store 到店体验预约'),('buy','3d-printing','拓竹多色打印入门指南')]:
        result['cards'].insert(1,dict(id=category,title=title,summary='发现值得留住的日常。',source='每日精选',source_id='github',category=category,time=result['updated'],day=result['today'],image='',url='https://example.test/original',kind=kind))
    result['sources'] = [dict(id=s, name=n, description='每日精选', type='telegram' if s == 'channel' else 'inbox') for s,n in [('github','GitHub 热门'),('x','推特爆款'),('world','环球要闻'),('channel','Telegram 频道')]]
    result['markets'] = [dict(name=n,value=v,change=c) for n,v,c in [('道琼斯','52,856.09',.69),('标普 500','7,757.17',.41),('纳斯达克','26,702.86',-.22),('上证指数','3,658.03',-1.48),('恒生指数','22,934.68',-3.03),('美元/人民币','6.6634',.05),('黄金','4,098.30',.87),('布伦特原油','112.02',2.94),('比特币','81,674.72',-1.12)]]
    return result


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *_):
        pass


def run(output, reference):
    output.mkdir(parents=True, exist_ok=True)
    catalogue = fixture(reference)
    server = ThreadingHTTPServer(('127.0.0.1', 0), partial(QuietHandler, directory=str(ROOT / 'site')))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    origin = f'http://127.0.0.1:{server.server_port}'
    checks = 0
    try:
        with sync_playwright() as p:
            executable = next((str(path) for path in [Path('/opt/ungoogled-chromium/chrome'), Path('/usr/bin/google-chrome')] if path.is_file()), None)
            browser = p.chromium.launch(executable_path=executable, args=['--no-sandbox'])
            for theme in ['light', 'dark']:
                for sid in MOBILE + DESKTOP:
                    desktop = sid.startswith('d-')
                    context = browser.new_context(viewport=dict(width=1440 if desktop else 402, height=900 if desktop else 874),
                                                  device_scale_factor=1 if desktop else 3, color_scheme=theme,
                                                  is_mobile=not desktop, has_touch=not desktop,
                                                  service_workers='block')
                    page = context.new_page()
                    errors = []
                    page.on('pageerror', lambda error: errors.append(str(error)))

                    def serve(route):
                        request = urlsplit(route.request.url)
                        if request.path.endswith('/visual-data.json'):
                            route.fulfill(json=catalogue)
                        elif request.path.startswith('/qa-img/'):
                            image = reference / 'img' / Path(request.path).name
                            route.fulfill(body=image.read_bytes(), content_type=mimetypes.guess_type(image)[0])
                        elif not desktop and request.path in ['/visual.css', '/style.css']:
                            # Headless Chromium reports zero safe-area insets. Substitute the two
                            # env() inputs at transport time to exercise the exact production calc
                            # with iPhone 17 Pro's 59/34pt safe areas; source CSS stays unchanged.
                            css = (ROOT / 'site' / request.path.lstrip('/')).read_text()
                            css = css.replace('env(safe-area-inset-top)', '59px').replace('env(safe-area-inset-bottom)', '34px')
                            route.fulfill(body=css, content_type='text/css')
                        elif route.request.url.startswith(origin):
                            route.continue_()
                        else:
                            route.abort()

                    page.route('**/*', serve)
                    page.add_init_script("localStorage.setItem('rebang-onboarded','true')")
                    page.goto(origin + '/index.html#screens/today')
                    page.wait_for_function('window.rebang !== undefined')
                    page.evaluate("""data => {
                        const bookmarks=[data.news[0],data.cards[0],data.cards.find(x=>x.kind==='buy'),data.news.find(x=>x.image)];
                        localStorage.setItem('shiguang-favorites-public',JSON.stringify(bookmarks));
                        localStorage.setItem('rebang-history-public',JSON.stringify(bookmarks.map(x=>({...x,viewed:data.updated}))));
                    }""", catalogue)
                    screen = sid.removeprefix('d-').removesuffix('-bottom')
                    target = {'news-quick':'news','detail-img':'detail','detail-text':'detail','search-init':'search','search-result':'search','search-empty':'search','loading':'news','empty':'news','error':'news','cal':'today','cal-empty':'today','drawer':'today','capsule':'today','lightbox':'detail','ptr-pull':'today','ptr-loading':'today','toast-action':'today','toast-error':'today','offline':'today','offline-none':'news','pwa':'today'}.get(screen, screen)
                    state = dict(page=target, status=screen if screen in ['loading','empty','error'] else 'normal')
                    if screen.startswith('search-'):
                        state['query'] = 'iPhone' if screen == 'search-result' else 'zzzz-no-match' if screen == 'search-empty' else ''
                    if screen in ['detail-img','lightbox']:
                        state['item'] = next(x['id'] for x in catalogue['news'] if x['image'])
                    if screen == 'detail-text':
                        state['item'] = next(x['id'] for x in catalogue['news'] if not x['image'])
                    if screen == 'capsule':
                        state['day'] = '2026-10-18'
                    page.evaluate('state => rebang.setState(state)', state)
                    if screen in ['cal','cal-empty','drawer','pwa','lightbox']:
                        page.evaluate('kind => rebang.showModal(kind)', 'cal' if screen == 'cal-empty' else screen)
                    if screen == 'cal-empty':
                        page.locator('[data-date="2026-10-01"]').click()
                        assert page.locator('#visual-toast').inner_text() == '这一天没有存档'
                    if screen.startswith('toast-'):
                        page.evaluate("error => rebang.toast(error?'没更新成功':'已取消收藏',error?'重试':'撤销',()=>{})", screen == 'toast-error')
                    if screen.startswith('ptr-'):
                        page.evaluate("label => {const node=document.createElement('div');node.className='ptr';node.textContent=label;document.querySelector('.visual-main').prepend(node)}", '下拉刷新' if screen == 'ptr-pull' else '正在更新…')
                    if screen.startswith('offline'):
                        context.set_offline(True)
                        if screen == 'offline-none':
                            page.evaluate("rebang.setState({data:{...rebang.data,news:[],cards:[],magazines:[]},page:'news',status:'empty'})")
                    page.evaluate('document.fonts.ready')
                    broken = page.evaluate("""async () => {
                        const images=[...document.querySelectorAll('#visual-app img')];
                        images.forEach(x=>x.loading='eager');
                        await Promise.all(images.map(x=>x.decode().catch(()=>{})));
                        return images.filter(x=>!x.naturalWidth).map(x=>x.src);
                    }""")
                    assert not broken, (sid, 'broken images', broken)
                    page.wait_for_timeout(80)
                    # Token and geometry assertions run against computed production CSS.
                    values = page.evaluate("""() => {
                        const root=getComputedStyle(document.documentElement), main=getComputedStyle(document.querySelector('.visual-main'));
                        return {brand:root.getPropertyValue('--c-brand').trim(),bg:getComputedStyle(document.body).backgroundColor,
                          padding:main.paddingBottom,overflow:document.documentElement.scrollWidth>innerWidth,
                          bar:getComputedStyle(document.querySelector('.bar')).height,
                          title:getComputedStyle(document.querySelector('.ph h1')||document.querySelector('h1')).fontSize};
                    }""")
                    assert values['brand'] == ('#F05A5F' if theme == 'dark' else '#D7282F'), (sid, values)
                    assert values['bg'] == ('rgb(17, 18, 20)' if theme == 'dark' else 'rgb(255, 255, 255)'), (sid, values)
                    assert not values['overflow'], (sid, 'horizontal overflow')
                    if not desktop:
                        assert values['padding'] == '136px', (sid, values)
                        assert values['bar'] == '70px', (sid, values)
                    scrollable = screen in ['today','news','news-quick','hot','play','buy','fav','mag','columns','columns-tag','history'] or screen.startswith('src-')
                    if scrollable:
                        page.evaluate('scrollTo(0,document.documentElement.scrollHeight)')
                        page.wait_for_timeout(80)
                        geometry = page.evaluate("""() => {
                          const rows=[...document.querySelectorAll('.visual-main [data-item]')];
                          return {count:rows.length,bottom:Math.max(...rows.map(x=>x.getBoundingClientRect().bottom)),top:document.querySelector('.bar').getBoundingClientRect().top};
                        }""")
                        if not desktop and geometry['count']:
                            assert geometry['bottom'] <= geometry['top'] - 16 + 1, (sid, geometry)
                        if not sid.endswith('-bottom'):
                            page.evaluate('scrollTo(0,0)')
                    assert not errors, (sid, errors)
                    page.screenshot(path=str(output / f'{sid}-{theme}.png'))
                    checks += 1
                    context.close()
                print(f'{theme}: 48 screens passed', flush=True)
            browser.close()
    finally:
        server.shutdown()
        server.server_close()
    print(f'{checks} screenshots: {output}')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, default=Path('/workspace/shiguang-rebang/v03-shots'))
    parser.add_argument('--reference', type=Path, default=Path('/workspace/proto-bot/rebang-visual/deploy'))
    args = parser.parse_args()
    run(args.out, args.reference)
