"""HTML templates. Pure functions of (page context, data) -> markup; no file or network access.

Every user-visible string is escaped with E(). Paths inside the site are site-root-relative and
are turned into page-relative links by Page.url(), so pages work under /tg-digest/ and file://.
"""
import hashlib, html, json, re
from dataclasses import dataclass
from datetime import datetime
from typing import Callable
from items import BEIJING

E = lambda v: html.escape(str(v or ''), quote=True)


# ---------- Icons ----------

ICONS = {'home':'<path d="m3 10 9-7 9 7v11H6V10M9 21v-8h6v8"/>','hot':'<path d="M13 3c2 6-3 6-1 10 2-1 3-3 3-4 7 7 4 12-3 12S3 14 8 8c0 4 2 4 2 4-1-5 3-6 3-9Z"/>','all':'<rect x="4" y="4" width="16" height="16" rx="3"/><path d="M8 8h8m-8 4h8m-8 4h5"/>','archive':'<rect x="4" y="5" width="16" height="16" rx="3"/><path d="M8 3v4m8-4v4M4 10h16"/>','mail':'<rect x="3" y="5" width="18" height="14" rx="3"/><path d="m3 7 9 6 9-6"/>','world':'<circle cx="12" cy="12" r="9"/><ellipse cx="12" cy="12" rx="4" ry="9"/><path d="M3 12h18"/>'}
ICONS['bookmark'] = '<path d="M6 4h12v17l-6-4-6 4Z"/>'
ICONS['code'] = '<path d="m8 8-4 4 4 4m8-8 4 4-4 4m-6 3 4-14"/>'
ICONS['x'] = '<path d="M5 4h14a3 3 0 0 1 3 3v9a3 3 0 0 1-3 3h-8l-6 3 1-4a3 3 0 0 1-3-3V7a3 3 0 0 1 3-3Z"/><path d="M7 9h10M7 13h6"/>'
def icon(key): return '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'+ICONS.get(key, ICONS['all'])+'</svg>'


def section_icon(key):
    shapes = {
        'x':'<path d="M16 16h31a9 9 0 0 1 9 9v17a9 9 0 0 1-9 9H29L17 57l2-9a9 9 0 0 1-9-9V25a9 9 0 0 1 6-9Z" fill="var(--icon-shade)"/><path d="M16 11h29a9 9 0 0 1 9 9v17a9 9 0 0 1-9 9H27L14 53l3-10a9 9 0 0 1-9-9V20a9 9 0 0 1 8-9Z" fill="url(#status-paper)"/><path d="M18 23h17m-17 8h12"/><path d="M43 22c3 5-3 6-1 10 2-1 3-3 3-4 6 6 3 11-2 11s-8-5-4-9c0 3 1 3 1 3-1-5 2-6 3-11Z" fill="url(#status-sun)" stroke="none"/>',
        'code':'<rect x="9" y="14" width="46" height="38" rx="8" fill="url(#status-paper)"/><path d="m25 25-9 8 9 8m14-16 9 8-9 8m-4-20-6 24" stroke="var(--sun)" stroke-width="3"/>',
        'home':'<circle cx="46" cy="19" r="10" fill="url(#status-sun)" stroke="none"/><path d="M46 5V2m11 10 3-2M33 10l-2-2m27 16 3 1" stroke="var(--sun)"/><path d="m14 20 35 4 5 27-34 3Z" fill="var(--icon-shade)"/><path d="M10 19 43 16 46 49 15 53a4 4 0 0 1-4-4Z" fill="url(#status-paper)"/><path d="m43 16 7 7-6 1Z" fill="var(--icon-light)"/><path d="m16 26 21-2m-20 6 21-2" stroke="var(--sun)" stroke-width="3"/><path d="m17 36 8-1 1 9-8 1Z" fill="var(--sun)" stroke="none"/><path d="m30 35 8-1m-8 6 8-1m-8 6 8-1m-22 5 23-2"/><path d="m46 30 2 18c0 3 4 3 5 1" stroke="var(--icon-light)"/>',
        'hot':'<path d="M35 8c4 15-12 17-5 28 5-2 9-8 9-13 18 18 12 32-7 32C12 55 9 37 21 24c-1 9 4 11 4 11-3-13 6-18 10-27Z" fill="var(--sun)"/><path d="M30 46c-5-6 1-12 4-15-1 8 8 9 5 15-2 5-7 5-9 0Z" fill="url(#status-paper)" stroke="none"/>',
        'mail':'<rect x="11" y="19" width="43" height="34" rx="7" fill="url(#status-paper)"/><path d="m12 23 20 16 21-16M12 50l14-15m27 15L39 36"/><rect x="37" y="10" width="17" height="16" rx="5" fill="var(--sun)" stroke="none"/>',
        'world':'<circle cx="32" cy="31" r="23" fill="url(#status-paper)"/><ellipse cx="32" cy="31" rx="11" ry="23"/><path d="M10 31h44M14 18c11 6 25 6 36 0M14 44c11-6 25-6 36 0"/><path d="m24 16 8-5 7 7-4 10-10-3-5 9-7-6 3-11Zm16 18 10 4-8 11-5-6Z" fill="var(--sun)" stroke="none"/>',
        'archive':'<rect x="12" y="14" width="40" height="40" rx="8" fill="url(#status-paper)"/><path d="M12 24h40"/><path d="M13 23v-3a6 6 0 0 1 6-6h26a6 6 0 0 1 6 6v3Z" fill="var(--sun)" stroke="none"/><path d="M23 9v10m18-10v10M22 34h5m10 0h5m-20 9h5"/><rect x="35" y="39" width="9" height="9" rx="3" fill="var(--sun)" stroke="none"/>',
        'bookmark':'<rect x="12" y="12" width="40" height="42" rx="8" fill="url(#status-paper)"/><path d="M24 8h16v26l-8-6-8 6Z" fill="var(--sun)" stroke="none"/><path d="M21 42h22m-22 6h14"/>',
        'all':'<rect x="17" y="12" width="34" height="38" rx="7" transform="rotate(10 34 31)" fill="var(--wash)"/><rect x="11" y="18" width="35" height="36" rx="7" transform="rotate(-7 29 36)" fill="url(#status-paper)"/><path d="M19 37h19m-18 8h13"/><rect x="19" y="24" width="19" height="6" rx="3" fill="var(--sun)" stroke="none"/>'
    }
    return '<svg class="status-icon" data-section="'+key+'" viewBox="0 0 64 64" aria-hidden="true"><defs><linearGradient id="status-sun" x2=".6" y2="1"><stop stop-color="#ffe6a2"/><stop offset="1" stop-color="var(--sun)"/></linearGradient><linearGradient id="status-paper" x2=".7" y2="1"><stop stop-color="var(--icon-light)"/><stop offset="1" stop-color="var(--icon-shade)"/></linearGradient></defs><ellipse cx="32" cy="56" rx="22" ry="4" fill="var(--wash)"/><g fill="none" stroke="var(--ink-2)" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round">'+shapes.get(key,shapes['all'])+'</g></svg>'


def color_style(source):
    color = str(source.get('color') or '')
    return f' style="--source:{color}"' if re.fullmatch(r'#[0-9a-fA-F]{3,8}', color) else ''


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
        """Key of the large illustrated icon in the page intro."""
        source = self.site.sources.get(self.active)
        if source:
            return source.get('icon', 'all')
        return {'daily': 'archive', 'news': 'hot', 'favorites': 'bookmark'}.get(self.active, self.active)

    def url(self, path):
        """Site-root-relative path -> link from this page. External URLs pass through."""
        return path if re.match(r'https?://', path) else self.rel + path


SLOT_LABELS = {'mail': '邮件', 'all': '全部', 'daily': '日报', 'home': '首页', 'news': '资讯', 'x': '推特爆款'}
BLOCK_TITLES = {'oneliner': '一句话速览', 'markets': '市场看板', 'chart': '一张图', 'tomorrow': '明日看点'}


# ---------- Small parts ----------

def heading(page, title, description):
    return (f'<div class="page-intro">{section_icon(page.section)}'
            f'<h1>{E(title)}</h1><p>{E(description)}</p></div>')


def section_label(title, note=''):
    return f'<div class="section-label"><b>{E(title)}</b>' + (f'<span>{E(note)}</span>' if note else '') + '</div>'


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
    return (f'<button class="bookmark" data-bookmark="{E(json.dumps(saved, ensure_ascii=False))}" '
            f'aria-pressed="false" aria-label="收藏">{icon("bookmark")}</button>')


# ---------- Cards ----------

def card_kind(page, item):
    images = item.images[:3]
    if not images:
        return 'text'
    if len(images) > 1:
        return 'multi'
    # Photos sit beside the text; screenshots (e.g. GitHub previews) need a full-width banner.
    return 'side' if page.site.is_photo(images[0]) else 'wide'


def card(page, item, kind=None, reading=False):
    source = page.site.sources[item.source_id]
    kind = kind or card_kind(page, item)
    surface = 'g-sheet mail-reading' if reading and source.get('adapter') == 'mail' else 'g-card'

    if item.url:
        title = f'<a href="{E(item.url)}" target="_blank" rel="noopener noreferrer">{E(item.title)}</a>'
    elif item.page:
        title = f'<a href="{E(page.url(item.page))}">{E(item.title)}</a>'
    else:
        title = E(item.title)

    meta = f'<span class="source" data-source="{E(source["id"])}"{color_style(source)}>{E(source["name"])}</span>'
    meta += ''.join(f'<span class="sub">{E(part)}</span>' for part in item.via)
    if item.topic:
        meta += f'<span class="cat">{E(item.topic)}</span>'

    pictures = ''.join(
        f'<button class="photo" data-image="{E(page.url(path))}" aria-label="放大图片">'
        f'<img src="{E(page.url(path))}" alt="{E(item.title)}" loading="lazy"></button>'
        for path in item.images[:3])
    gallery = f'<div class="pictures">{pictures}</div>' if pictures else ''
    original = (f'<a href="{E(item.url)}" target="_blank" rel="noopener noreferrer">阅读原文 ↗</a>'
                if item.url else '')

    return (f'<article class="card news {surface} {kind}" data-cat="{E(item.category)}" data-ch="{E(item.filter_key)}">'
            f'<div class="copy">'
            f'<div class="meta">{meta}{time_tag(page, item)}</div>'
            f'<h2>{title}</h2>'
            f'<p>{E(item.body)}</p>'
            f'</div>'
            f'{gallery}'
            f'<div class="foot"><button class="expand" aria-expanded="false">展开全文</button>'
            f'{original}{bookmark_button(item, source)}</div>'
            f'</article>')


def cards(page, items):
    return ''.join(card(page, item) for item in items)


# ---------- Page sections ----------

def filters(page, items):
    """Sticky category tabs plus search and source select, limited to sources present on the page."""
    site = page.site
    present = {item.source_id for item in items}
    inbox_names = [s['name'] for s in site.sources.values() if s['type'] == 'inbox' and s['id'] in present]
    tabs = ['推荐'] + site.categories + inbox_names
    buttons = ''.join(
        f'<button class="pill{" selected" if i == 0 else ""}" data-value="{E(name if i else "")}" '
        f'aria-pressed="{"true" if i == 0 else "false"}">{E(name)}</button>'
        for i, name in enumerate(tabs))
    options = ''.join(
        f'<option value="{E(s["channel"] if s["type"] == "telegram" else s["id"])}">{E(s["name"])}</option>'
        for s in site.sources.values() if s['id'] in present)
    return (f'<div class="filters">{buttons}</div>'
            f'<div class="searchline"><input id="q" type="search" placeholder="搜索资讯" aria-label="搜索资讯">'
            f'<select id="channel" aria-label="筛选来源"><option value="">全部来源</option>{options}</select></div>')


def column_row(page, columns):
    """Shortcut cards to favorites and every inbox column. `columns` is [(source, lead text)]."""
    favorites = page.site.favorites
    entries = []
    if favorites.get('enabled') and favorites.get('column'):
        entries.append((page.url(favorites['path']), 'bookmark', favorites['label'], '留住想再读的内容'))
    entries += [(page.url(s['id'] + '/index.html'), s['icon'], s['name'], lead) for s, lead in columns]
    if not entries:
        return ''
    links = ''.join(
        f'<a class="column-entry g-card" href="{E(href)}">{section_icon(key)}'
        f'<span class="column-copy"><b>{E(name)}</b><span>{E(lead)}</span></span></a>'
        for href, key, name, lead in entries)
    return f'<section class="columns" aria-label="栏目">{section_label("栏目")}<div class="column-row">{links}</div></section>'


def date_chips(dates, current, suffix=''):
    links = ''.join(f'<a href="{d}.html"' + (' aria-current="page"' if d == current else '') + f'>{d}{suffix}</a>'
                    for d in dates)
    return f'<nav class="archives" aria-label="往期列表">{links}</nav>'


def blocks(page, issue):
    """Summary blocks of an inbox issue: one-liners, markets, chart, tomorrow."""
    result = ''
    for block in issue.get('blocks', []):
        kind = block.get('type')
        title = block.get('title') or BLOCK_TITLES.get(kind, '')
        if kind in ('oneliner', 'tomorrow'):
            content = '<ul>' + ''.join(
                '<li>' + E(x if isinstance(x, str) else x.get('title') or x.get('body')) + '</li>'
                for x in block.get('items', [])) + '</ul>'
        elif kind == 'markets':
            def market(m):
                down = str(m.get('change', '')).startswith('-')
                return (f'<div class="market">{E(m.get("name"))}<strong>{E(m.get("value"))}</strong>'
                        f'<span class="{"down" if down else "up"}">{"↓" if down else "↑"} {E(m.get("change"))}</span>'
                        f'<small>{E(m.get("note"))}</small></div>')
            content = '<div class="markets">' + ''.join(market(m) for m in block.get('items', [])) + '</div>'
        elif kind == 'chart':
            image = block.get('image')
            image = image.get('file') if isinstance(image, dict) else image
            content = (f'<img src="{E(page.url(image))}" alt="{E(title)}">' if image else '') + f'<p>{E(block.get("caption"))}</p>'
        else:
            continue
        result += f'<section class="block"><h2>{E(title)}</h2>{content}</section>'
    return result


def chart_images(issue):
    for block in issue.get('blocks', []):
        if block.get('type') == 'chart':
            image = block.get('image')
            image = image.get('file') if isinstance(image, dict) else image
            if image:
                yield image


# ---------- Navigation ----------

def nav_slots(page):
    """The five fixed slots, shared by the mobile tab bar and the desktop nav."""
    site = page.site
    lookup = {entry[0]: entry for entry in site.entries}
    labels = dict(SLOT_LABELS, favorites=site.favorites.get('label', '收藏'))
    result = ''
    for key in site.tabs:
        name = labels.get(key, site.sources.get(key, {}).get('name', key))
        if key not in lookup:
            result += f'<span class="nav-unavailable" aria-disabled="true">{E(name)}</span>'
            continue
        _, path, _, glyph = lookup[key]
        active = page.active == key
        classes = ' '.join(c for c in ('active' if active else '', 'home-slot' if key == 'home' else '') if c)
        content = icon(glyph) if key == 'home' else f'{icon(glyph)}<span>{E(name)}</span>'
        result += (f'<a href="{page.url(path)}" class="{classes}"' + (' aria-label="首页"' if key == 'home' else '')
                   + (' aria-current="page"' if active else '') + f'>{content}</a>')
    return result


def more_menu(page):
    """Full navigation dialog, grouped as pages / inbox columns / Telegram channels."""
    site = page.site
    core = {'home', 'news', 'all', 'daily', 'favorites'}
    telegram = {key for key, s in site.sources.items() if s['type'] == 'telegram'}
    groups = [('页面', [e for e in site.entries if e[0] in core]),
              ('栏目', [e for e in site.entries if e[0] not in core | telegram]),
              ('TG 频道', [e for e in site.entries if e[0] in telegram])]

    def mark(key, glyph):
        return f'<i class="dot"{color_style(site.sources[key])}></i>' if key in telegram else icon(glyph)

    body = ''.join(
        f'<div class="more-group">{E(label)}</div><div class="more-grid">'
        + ''.join(f'<a href="{page.url(path)}"' + (' aria-current="page"' if key == page.active else '')
                  + f'>{mark(key, glyph)}<span>{E(name)}</span></a>' for key, path, name, glyph in group)
        + '</div>'
        for label, group in groups if group)
    return ('<dialog class="more-nav" id="more-nav" aria-label="全部导航"><div class="more-head"><b>全部导航</b>'
            '<button class="more-close" data-close aria-label="关闭">×</button></div>' + body + '</dialog>')


# ---------- Document ----------

SEARCH_ICON = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75"><circle cx="10" cy="10" r="6"/><path d="m15 15 6 6"/></svg>'
MENU_ICON = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75"><path d="M5 7h14M5 12h14M5 17h14"/></svg>'
THEME_SCRIPT = "const t=new URLSearchParams(location.search).get('theme');if(t==='light'||t==='dark')document.documentElement.dataset.theme=t;"


def document(page, title, body, illumination, light_source):
    """Full HTML page. `illumination` is the per-page ambient light CSS from light.py."""
    site, assets = page.site, page.site.assets
    version = assets['version']
    slots = nav_slots(page)
    return (
        '<!doctype html><html lang="zh-CN"><head>'
        '<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
        '<meta name="color-scheme" content="light dark">'
        '<meta name="theme-color" content="#f8f4ee" media="(prefers-color-scheme: light)">'
        '<meta name="theme-color" content="#18171c" media="(prefers-color-scheme: dark)">'
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
        f'<body data-bookmark-scope="{"private" if site.private else "public"}" data-light-source="{E(light_source or "fallback-sky")}">'
        '<div class="g-light" aria-hidden="true"></div>'
        '<header><div class="top g-column">'
        f'<a class="brand" href="{page.url("index.html")}"><img class="brand-mark" src="{page.url("favicon.svg")}?v={version}" alt="" width="28" height="28">拾光热点</a>'
        f'<nav class="desktop-nav" aria-label="主导航">{slots}</nav>'
        f'<div class="tools"><button id="search-toggle" aria-label="搜索">{SEARCH_ICON}</button>'
        f'<button id="more-toggle" aria-label="菜单" aria-expanded="false">{MENU_ICON}</button></div>'
        '</div></header>'
        '<div class="layout g-column"><main>'
        f'{body}'
        '<p id="none" hidden>换个词，再找找。</p>'
        f'<footer><span>今日信息，留一份清晰。</span><span>更新于 {site.now.strftime("%m-%d %H:%M")} 北京时间</span></footer>'
        '</main></div>'
        f'<nav class="bottom" aria-label="主导航">{slots}</nav>'
        f'{more_menu(page)}'
        '<dialog class="lightbox" aria-label="图片查看器"><button class="lightbox-close" aria-label="关闭">×</button><img alt="放大图片"></dialog>'
        '</body></html>')
