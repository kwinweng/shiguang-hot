"""Pure presentation components, initially exercised only by the design playground."""
from html import escape
from urllib.parse import urlsplit
from .phosphor import icon

KINDS = {'look': '好看', 'play': '好玩', 'buy': '好买'}


def e(value):
    return escape(str(value), quote=True)


def safe_url(value):
    """Allow local demo assets and public HTTPS origins, never executable links."""
    value = str(value or '')
    parts = urlsplit(value)
    if parts.scheme == 'https' and parts.netloc:
        return e(value)
    if value.startswith('/design/assets/') and '..' not in parts.path and not parts.scheme:
        return e(value)
    return '#'



def bookmark(item):
    return f'<button type="button" class="save icon-button" data-save="{e(item["id"])}" aria-label="收藏：{e(item["title"])}" aria-pressed="false">{icon("bookmark")}</button>'


def source_link(item):
    return f'<a class="source-link" href="{safe_url(item.get("url"))}" target="_blank" rel="noopener noreferrer">{e(item.get("source", "格式样例"))}{icon("external-link")}</a>'


def news_card(item, *, hero=False):
    badge = '<span class="eyebrow warm">此刻要闻</span>' if hero else ''
    cls = 'news-card hero-card' if hero else 'news-card'
    return f'''<article class="{cls}" data-item="{e(item['id'])}">
      <div class="news-meta">{badge}<span>{e(item.get('topic','资讯'))}</span><span>{e(item.get('time','仅日期'))}</span></div>
      <button class="title-button" data-detail="{e(item['id'])}"><h3>{e(item['title'])}</h3></button>
      <p class="news-summary">{e(item.get('reason',''))}</p>
      <footer>{source_link(item)}<span class="reach">{e(item.get('reach',1))} 个频道</span>{bookmark(item)}</footer>
    </article>'''


def media_card(item):
    image = item.get('image')
    if image:
        media = f'<img src="{safe_url(image)}" alt="{e(item.get("alt", item["title"]))}" loading="lazy" width="{int(item.get("width",800))}" height="{int(item.get("height",600))}">'
    elif item.get('fixture') and item.get('art'):
        media = f'<span class="object-art art-{e(item.get("art","lamp"))}" aria-label="虚构物件形态示意"><svg viewBox="0 0 240 240" aria-hidden="true"><use href="/design/assets/objects.svg#{e(item.get("art","lamp"))}"/></svg></span>'
    else:
        media = f'<span class="placeholder">{icon("image")}配图待核实 · 查看出处</span>'
    price = item.get('price')
    price_line = f'<p class="price"><strong>{e(price["amount"])}</strong><span>官方价 · {e(price["region"])}</span></p>' if price else ''
    if price and price.get("fictional"):
        price_line += '<small class="fixture-label">虚构价格格式示例</small>'
    status = f'<span class="status-label">{e(item["status"])}</span>' if item.get('status') else ''
    dog = '<span class="dog-label">带狗</span>' if item.get('dog') else ''
    return f'''<article class="media-card" data-item="{e(item['id'])}" data-kind="{e(item['kind'])}">
      <div class="media-wrap"><button class="media-open" data-detail="{e(item['id'])}" aria-label="查看：{e(item['title'])}">{media}</button>{bookmark(item)}<span class="image-label">{e(item.get('image_label','形态示意'))}</span></div>
      <div class="media-body"><div class="card-labels"><span>{e(item['group'])}</span>{dog}{status}</div>
      <button class="title-button" data-detail="{e(item['id'])}"><h3>{e(item['title'])}</h3></button>
      <p class="reason">{e(item['reason'])}</p>{price_line}<footer>{source_link(item)}</footer></div>
    </article>'''


def render_card(item, **kwargs):
    return news_card(item, **kwargs) if item['kind'] == 'look' else media_card(item)


def bottom_nav():
    names = [('today','今日','home'), ('look','好看','news'), ('play','好玩','compass'), ('buy','好买','spark'), ('saved','收藏','bookmark')]
    return '<nav class="bottom-nav" aria-label="主导航">' + ''.join(f'<button data-page="{key}" aria-current="{"page" if key == "today" else "false"}">{icon(ico)}<span>{label}</span></button>' for key,label,ico in names) + '</nav>'


def fold_run(items):
    visible = ''.join(news_card(i) for i in items[:3])
    if len(items) <= 3:
        return visible
    return visible + f'<details class="source-fold"><summary>{e(items[0]["source"])} 连续 {len(items)} 条 <span>其余 {len(items)-3} 条 · 展开</span>{icon("chevron-down")}</summary><div>{"".join(news_card(i) for i in items[3:])}</div></details>'
