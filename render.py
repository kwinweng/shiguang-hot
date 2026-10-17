"""HTML components of the 「光」 design system, applied to 拾光热点.

Class names follow the spec's components (g-light, g-lead, g-card, g-sheet, g-wash, g-pill, g-btn,
g-round, g-topbar, g-tabbar, g-seg, g-panel); style.css implements them from the spec's tokens.
Pure functions of (page context, data) -> markup; no file or network access. Every user-visible
string is escaped with E(). Paths inside the site are site-root-relative and become page-relative
through Page.url(), so pages work under /tg-digest/ and from file://. app.js hooks only ids and
data-* attributes.
"""
import hashlib, html, json, re
from dataclasses import dataclass
from datetime import datetime
from typing import Callable
from items import BEIJING
from icons import icon, sprite, status_icon

E = lambda v: html.escape(str(v or ''), quote=True)


# ---------- Context ----------

@dataclass
class Site:
    """Everything shared by all pages of one build."""
    sources: dict            # id -> source config (visible sources only)
    entries: list            # (key, path, label, icon) for every navigable page
    tabs: list               # the five bottom-bar slot keys, home in the middle
    favorites: dict
    private: bool
    now: datetime
    categories: list         # configured topic names, plus 综合
    assets: dict             # css / js / version file names
    is_photo: Callable = lambda path: False   # site-relative image path -> bool

    @property
    def today(self):
        return self.now.astimezone(BEIJING).date().isoformat()


@dataclass
class Page:
    site: Site
    rel: str                 # prefix back to the site root: '' or '../'
    active: str              # nav key of this page

    @property
    def section(self):
        """Key of the 3D status icon in the lead block."""
        source = self.site.sources.get(self.active)
        if source:
            return source.get('icon', 'all')
        return {'daily': 'archive', 'news': 'hot', 'favorites': 'bookmark'}.get(self.active, self.active)

    def url(self, path):
        """Site-root-relative path -> link from this page. External URLs pass through."""
        return path if re.match(r'https?://', path) else self.rel + path


SLOT_LABELS = {'mail': '邮件', 'all': '全部', 'daily': '日报', 'home': '首页', 'news': '资讯', 'x': '推特爆款'}
BLOCK_TITLES = {'oneliner': '一句话速览', 'markets': '市场看板', 'chart': '一张图', 'tomorrow': '明日看点'}
EXTERNAL = 'target="_blank" rel="noopener noreferrer"'


# ---------- Lead block and headings (placed on the light, never in a card) ----------

def heading(page, title, description):
    """Lead block: 58 3D icon, one sentence in `lead`, one line of `note`."""
    return (f'<div class="g-lead">{status_icon(page.section, "lead")}'
            f'<div class="g-lead__text"><h1 class="g-lead__title">{E(title)}</h1>'
            f'<p class="g-lead__note">{E(description)}</p></div></div>')


def section_label(title, note=''):
    """Small `section` label above a run of content, with a `note` on the right."""
    return (f'<div class="section-label"><h2>{E(title)}</h2>'
            + (f'<span>{E(note)}</span>' if note else '') + '</div>')


def group(parts, content, level=2, source_id=None, cls='group', light=None):
    """A titled group of cards. One part reads as a `subhead`; several parts become pills.

    `light` is this group's (light, dark) image pair: when the reader scrolls into the group the
    page's light cross-fades to it, as the spec asks for a list moving to another group.
    """
    parts = [p for p in parts if p]
    title = E(parts[0]) if len(parts) == 1 else ''.join(f'<span class="g-pill">{E(p)}</span>' for p in parts)
    data = f' data-source="{E(source_id)}"' if source_id else ''
    if light:
        data += f' data-light="{E(light[0])}" data-light-dark="{E(light[1])}"'
    return f'<section class="{cls}"{data}><h{level} class="group__title">{title}</h{level}>{content}</section>'


# ---------- Cards ----------

def time_tag(page, item):
    """Visible time plus an ISO datetime that app.js turns into "N 小时前" for the last day."""
    if not item.has_clock:
        return f'<time>{E("今天" if item.day == page.site.today else item.day[5:])}</time>'
    moment = item.moment
    local = moment.astimezone(BEIJING)
    text = local.strftime('%H:%M') if local.date().isoformat() == page.site.today else local.strftime('%m-%d %H:%M')
    return f'<time datetime="{E(moment.isoformat())}">{E(text)}</time>'


def bookmark_button(item, source):
    # The identity must stay stable across builds, or saved bookmarks lose their state.
    identity = json.dumps([item.source_id, item.native_id or item.url or item.title, item.ts], ensure_ascii=False)
    saved = dict(id=hashlib.sha256(identity.encode()).hexdigest(), title=item.title, url=item.url,
                 source=source['name'], time=item.ts, snippet=item.body[:500])
    return (f'<button class="icon-btn bookmark" type="button" data-bookmark="{E(json.dumps(saved, ensure_ascii=False))}" '
            f'aria-pressed="false" aria-label="收藏">{icon("bookmark")}</button>')


def card_media(page, item):
    images = item.images[:3]
    if not images:
        return 'text'
    if len(images) > 1:
        return 'multi'
    # Photos sit beside the text; screenshots (e.g. GitHub previews) keep their own shape below it.
    return 'side' if page.site.is_photo(images[0]) else 'wide'


def card(page, item, kind=None, reading=False, rank=None):
    """One news item as a glass card (`g-card`); long mail reading goes on paper (`g-sheet`).

    kind: hero | side | wide | multi | text (derived from the images when omitted).
    """
    source = page.site.sources[item.source_id]
    kind = kind or card_media(page, item)
    surface = 'g-sheet card--reading' if reading and source.get('adapter') == 'mail' else 'g-card'

    if item.url:
        title = f'<a href="{E(item.url)}" {EXTERNAL}>{E(item.title)}</a>'
    elif item.page:
        title = f'<a href="{E(page.url(item.page))}">{E(item.title)}</a>'
    else:
        title = E(item.title)

    label = f'<span class="rank">{rank:02}</span>' if rank else ''
    label += f'<span class="source" data-source="{E(source["id"])}">{E(source["name"])}</span>'
    label += ''.join(f'<span class="sub">{E(part)}</span>' for part in item.via)
    if item.topic:
        label += f'<span class="cat">{E(item.topic)}</span>'

    if kind == 'multi':
        # Photo strip: each photo keeps its own shape at one height, a dot per photo below.
        prints = ''.join(
            f'<button class="g-print photo" type="button" data-image="{E(page.url(path))}" aria-label="放大图片">'
            f'<img src="{E(page.url(path))}" alt="{E(item.title)}" loading="lazy" decoding="async"></button>'
            for path in item.images[:7])
        dots = ''.join('<i aria-current="true"></i>' if n == 0 else '<i></i>' for n in range(len(item.images[:7])))
        media = f'<div class="card__media"><div class="g-strip">{prints}</div><div class="g-dots" aria-hidden="true">{dots}</div></div>'
    else:
        photos = ''.join(
            f'<button class="photo" type="button" data-image="{E(page.url(path))}" aria-label="放大图片">'
            f'<img src="{E(page.url(path))}" alt="{E(item.title)}" loading="lazy" decoding="async"></button>'
            for path in item.images[:1])
        media = f'<div class="card__media">{photos}</div>' if photos else ''
    body = f'<p class="card__body">{E(item.body)}</p>' if item.body else ''
    expand = (f'<button class="g-btn g-btn--text expand" type="button" aria-expanded="false"><span>展开全文</span>'
              f'{icon("chevron")}</button>') if item.body else ''
    original = (f'<a class="g-btn g-btn--text" href="{E(item.url)}" {EXTERNAL}><span>阅读原文</span>{icon("external")}</a>'
                if item.url else '')

    return (f'<article class="{surface} card news card--{kind}" data-cat="{E(item.category)}" data-ch="{E(item.filter_key)}">'
            f'<div class="g-card__label"><span class="g-card__who">{label}</span>{time_tag(page, item)}</div>'
            f'<h2 class="card__title">{title}</h2>'
            f'{body}{media}'
            f'<div class="card__actions">{expand}{original}{bookmark_button(item, source)}</div>'
            f'</article>')


def cards(page, items):
    return ''.join(card(page, item) for item in items)


def ranked(page, items):
    """The 资讯 ranking. The order is the information, so each card carries its ordinal in `ink-3`."""
    return '<ol class="ranked">' + ''.join(f'<li>{card(page, item, rank=n)}</li>' for n, item in enumerate(items, 1)) + '</ol>'


# ---------- Page sections ----------

def filters(page, items):
    """Category pills plus search and source select, limited to sources present on the page."""
    site = page.site
    present = {item.source_id for item in items}
    inbox_names = [s['name'] for s in site.sources.values() if s['type'] == 'inbox' and s['id'] in present]
    names = ['推荐'] + site.categories + inbox_names
    pills = ''.join(
        f'<button class="g-pill pill{" selected" if i == 0 else ""}" type="button" data-value="{E(name if i else "")}" '
        f'aria-pressed="{"true" if i == 0 else "false"}">{E(name)}</button>'
        for i, name in enumerate(names))
    options = ''.join(
        f'<option value="{E(s["channel"] if s["type"] == "telegram" else s["id"])}">{E(s["name"])}</option>'
        for s in site.sources.values() if s['id'] in present)
    return (f'<div class="filterbar"><div class="filters" role="toolbar" aria-label="分类">{pills}</div></div>'
            '<div class="searchline">'
            f'<label class="g-field g-field--search">{icon("search")}'
            '<input id="q" type="search" placeholder="搜索资讯" aria-label="搜索资讯" autocomplete="off"></label>'
            f'<label class="g-field g-field--select"><select id="channel" aria-label="筛选来源"><option value="">全部来源</option>{options}</select>'
            f'{icon("chevron")}</label></div>')


def column_row(page, columns):
    """Entry cards to favorites and every inbox column. `columns` is [(source, lead text)]."""
    favorites = page.site.favorites
    entries = []
    if favorites.get('enabled') and favorites.get('column'):
        entries.append((page.url(favorites['path']), 'bookmark', favorites['label'], '留住想再读的内容'))
    entries += [(page.url(s['id'] + '/index.html'), s['icon'], s['name'], lead) for s, lead in columns]
    if not entries:
        return ''
    links = ''.join(
        f'<a class="g-card entry column-entry" href="{E(href)}">{status_icon(key, "list")}'
        f'<span class="entry__text"><b>{E(name)}</b><span>{E(lead)}</span></span></a>'
        for href, key, name, lead in entries)
    return f'<section class="columns" aria-label="栏目">{section_label("栏目")}<div class="column-row">{links}</div></section>'


def date_chips(dates, current, suffix='', today=None):
    """Issue dates as pills; the one shown is ink, today carries the sun 「今天」 mark."""
    def chip(d):
        mark = '<span class="g-pill g-pill--sun">今天</span>' if d == today else ''
        return (f'<a class="g-pill" href="{d}.html"' + (' aria-current="page"' if d == current else '')
                + f'>{d}{suffix}{mark}</a>')
    return f'<nav class="archives" aria-label="往期列表">{"".join(chip(d) for d in dates)}</nav>'


def blocks(page, issue):
    """Summary blocks of an inbox issue. They are editorial / AI writing, so they carry the sun wash."""
    result = ''
    for block in issue.get('blocks', []):
        kind = block.get('type')
        title = block.get('title') or BLOCK_TITLES.get(kind, '')
        if kind in ('oneliner', 'tomorrow'):
            content = '<ul class="brief">' + ''.join(
                '<li>' + E(x if isinstance(x, str) else x.get('title') or x.get('body')) + '</li>'
                for x in block.get('items', [])) + '</ul>'
        elif kind == 'markets':
            def market(m):
                down = str(m.get('change', '')).startswith('-')
                return (f'<div class="g-wash market"><span>{E(m.get("name"))}</span><strong>{E(m.get("value"))}</strong>'
                        f'<span>{"↓" if down else "↑"} {E(m.get("change"))}</span><small>{E(m.get("note"))}</small></div>')
            content = '<div class="markets">' + ''.join(market(m) for m in block.get('items', [])) + '</div>'
        elif kind == 'chart':
            image = block.get('image')
            image = image.get('file') if isinstance(image, dict) else image
            content = (f'<img class="chart" src="{E(page.url(image))}" alt="{E(title)}" loading="lazy">' if image else '') + f'<p>{E(block.get("caption"))}</p>'
        else:
            continue
        result += f'<section class="g-card g-card--sun block"><h2 class="g-card__label">{E(title)}</h2>{content}</section>'
    return result


def reading_switch():
    """The three reading sizes for text on paper (16.5/31, 18/33, 19.5/36); app.js remembers the choice."""
    sizes = [('1', '标准'), ('2', '大'), ('3', '特大')]
    items = ''.join(f'<button class="g-seg__item" type="button" data-reading="{n}" aria-pressed="{"true" if n == "1" else "false"}">{label}</button>'
                    for n, label in sizes)
    return f'<div class="g-seg reading-size" role="group" aria-label="正文字号">{items}</div>'


def chart_images(issue):
    for block in issue.get('blocks', []):
        if block.get('type') == 'chart':
            image = block.get('image')
            image = image.get('file') if isinstance(image, dict) else image
            if image:
                yield image


def empty(key, text, element_id='', hidden=False):
    """A quiet message on the light: the 3D icon and one sentence."""
    ident = f' id="{element_id}"' if element_id else ''
    return f'<div class="empty"{ident}{" hidden" if hidden else ""}>{status_icon(key, "lead")}<p>{E(text)}</p></div>'


def favorites_body(page):
    """Favorites are rendered by app.js from this device's storage; the page ships only containers."""
    return (heading(page, '留住想再读的内容', '收藏保存在这台设备上。')
            + '<div id="favorites-list" class="stack"></div>'
            + empty('bookmark', '还没有收藏，点卡片上的书签收藏', 'favorites-empty')
            + '<p id="favorites-status" class="visually-hidden" role="status" aria-live="polite"></p>')


# ---------- Navigation ----------

def nav_slots(page):
    """The five fixed slots, shared by the mobile tab bar and the desktop switch.

    Words only, as the spec asks. The selected slot's bright-glass block is its own element so it
    can slide between pages.
    """
    site = page.site
    lookup = {entry[0]: entry for entry in site.entries}
    labels = dict(SLOT_LABELS, favorites=site.favorites.get('label', '收藏'))
    result = ''
    for n, key in enumerate(site.tabs, 1):
        name = labels.get(key, site.sources.get(key, {}).get('name', key))
        if key not in lookup:
            result += f'<span class="tab slot-{n} nav-unavailable" aria-disabled="true">{E(name)}</span>'
            continue
        _, path, _, _ = lookup[key]
        active = page.active == key
        classes = ' '.join(c for c in ('tab', f'slot-{n}', 'active' if active else '', 'home-slot' if key == 'home' else '') if c)
        result += (f'<a href="{page.url(path)}" class="{classes}"'
                   + (' aria-current="page"' if active else '') + f'>{E(name)}</a>')
        if active:
            result = f'<span class="tab__pill slot-{n}" aria-hidden="true"></span>' + result
    return result


def more_menu(page):
    """Full navigation on an opaque panel, grouped as pages / inbox columns / Telegram channels."""
    site = page.site
    core = {'home', 'news', 'all', 'daily', 'favorites'}
    telegram = {key for key, s in site.sources.items() if s['type'] == 'telegram'}
    groups = [('页面', [e for e in site.entries if e[0] in core]),
              ('栏目', [e for e in site.entries if e[0] not in core | telegram]),
              ('TG 频道', [e for e in site.entries if e[0] in telegram])]

    def mark(key, glyph_key):
        return icon('telegram') if key in telegram else icon(glyph_key)

    body = ''.join(
        f'<h3 class="sheet__group">{E(label)}</h3><div class="sheet__grid">'
        + ''.join(f'<a class="g-wash sheet__link" href="{page.url(path)}"' + (' aria-current="page"' if key == page.active else '')
                  + f'>{mark(key, glyph_key)}<span>{E(name)}</span></a>' for key, path, name, glyph_key in group)
        + '</div>'
        for label, group in groups if group)
    return ('<dialog class="g-panel sheet more-nav" id="more-nav" aria-labelledby="more-title">'
            '<div class="sheet__head"><h2 id="more-title">全部导航</h2>'
            f'<button class="g-round" type="button" data-close aria-label="关闭">{icon("close")}</button></div>'
            + body + '</dialog>')


# ---------- Document ----------

THEME_SCRIPT = ("document.documentElement.classList.add('js');"
                "const t=new URLSearchParams(location.search).get('theme');"
                "if(t==='light'||t==='dark')document.documentElement.dataset.theme=t;")


def document(page, title, body, illumination, light_source):
    """Full HTML page. `illumination` is the per-page light (light.py) as CSS custom properties."""
    site, assets = page.site, page.site.assets
    version = assets['version']
    slots = nav_slots(page)
    favorites = site.favorites
    favorites_url = f' data-favorites="{E(page.url(favorites["path"]))}"' if favorites.get('enabled') else ''
    return (
        '<!doctype html><html lang="zh-CN"><head>'
        '<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">'
        '<meta name="color-scheme" content="light dark">'
        '<meta name="theme-color" content="#FAF6EF" media="(prefers-color-scheme: light)">'
        '<meta name="theme-color" content="#0C0B0F" media="(prefers-color-scheme: dark)">'
        f'<title>{E(title)} · 拾光热点</title>'
        f'<link rel="icon" href="{page.url("favicon.ico")}?v={version}">'
        f'<link rel="icon" type="image/svg+xml" href="{page.url("favicon.svg")}?v={version}">'
        f'<link rel="apple-touch-icon" href="{page.url("apple-touch-icon.png")}?v={version}">'
        f'<link rel="manifest" href="{page.url("manifest.webmanifest")}?v={version}">'
        f'<script>{THEME_SCRIPT}</script>'
        f'<link rel="stylesheet" href="{page.url(assets["css"])}">'
        f'<style>{illumination}</style>'
        f'<script src="{page.url(assets["js"])}" defer></script>'
        '</head>'
        f'<body data-bookmark-scope="{"private" if site.private else "public"}"{favorites_url} data-light-source="{E(light_source or "fallback-sky")}">'
        f'{sprite()}'
        '<div class="g-light" aria-hidden="true"><i class="g-light__field"></i></div>'
        '<header class="g-topbar"><div class="g-topbar__inner g-column">'
        f'<a class="g-topbar__brand" href="{page.url("index.html")}">拾光热点</a>'
        f'<span class="g-topbar__where" aria-hidden="true">{E(title)}</span>'
        f'<nav class="g-seg desktop-nav" aria-label="主导航">{slots}</nav>'
        f'<div class="g-topbar__actions"><button class="g-round" type="button" id="search-toggle" aria-label="搜索">{icon("search")}</button>'
        f'<button class="g-round" type="button" id="more-toggle" aria-label="全部导航" aria-expanded="false" aria-controls="more-nav">{icon("menu")}</button></div>'
        '</div></header>'
        '<div class="layout g-column"><main id="main">'
        f'{body}'
        f'{empty("all", "换个词，再找找。", "none", hidden=True)}'
        f'<footer class="footer"><span>今日信息，留一份清晰。</span><span>更新于 {site.now.strftime("%m-%d %H:%M")} 北京时间</span></footer>'
        '</main></div>'
        f'<nav class="g-tabbar bottom" aria-label="主导航">{slots}</nav>'
        f'{more_menu(page)}'
        f'<dialog class="lightbox" aria-label="图片查看器"><button class="g-round lightbox__close" type="button" data-close aria-label="关闭">{icon("close")}</button><img alt=""></dialog>'
        '<div class="toast" id="toast" role="status" aria-live="polite"><span class="toast__text"></span><a class="g-btn g-btn--primary toast__action" hidden></a><button class="g-btn g-btn--primary toast__action" type="button" hidden></button></div>'
        '</body></html>')
