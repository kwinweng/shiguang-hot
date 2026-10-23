"""Public, day-sized news archives. No collector state or private inputs cross this boundary."""
import hashlib
import json
import re
from datetime import datetime
from pathlib import Path

from shiguang.model import BEIJING
from shiguang.site import render

SCHEMA = 3
# 已停用来源，只为旧归档保留
ALLOWED = frozenset(('CE_Observe FinanceNewsDaily HuaErJie1 NewlearnerChannel TimeHorizonX '
                     'freechinese liangjiahepost pelosi3 scitech_fans titan_pain tnews365 '
                     'xhqcankao zaihuapd world x github hot-daily').split())
PHOSPHOR = json.loads(Path(__file__).with_name('phosphor.json').read_text())
RETIRED = {sid: dict(id=sid, channel=sid, name=name, order=order, type='telegram',
                     visibility='public', icon='all', home={'weight': 1, 'cap': 4})
           for sid, name, order in [('pelosi3', '敏感经济信息分享', 56),
                                    ('liangjiahepost', '梁家河邮报', 60),
                                    ('titan_pain', '某科学的一个频道', 61)]}


def icon(name):
    return PHOSPHOR[name].replace('<svg ', '<svg class="phosphor" aria-hidden="true" ')


def card(page, item):
    markup = render.card(page, item, kind='side' if item.images else 'text')
    glyph = '<span class="ph-bookmark">' + icon('bookmark-simple') + icon('bookmark-fill') + '</span>'
    markup = markup.replace(render.icon('bookmark'), glyph)
    if not publication(item):
        markup = re.sub(r'<time[^>]*>.*?</time>', '<time>仅日期</time>', markup)
    return markup


def uid(item):
    """Exactly the existing bookmark identity, independent of display day and sort order."""
    identity = json.dumps([item.source_id, item.native_id or item.url or item.title, item.ts], ensure_ascii=False)
    return hashlib.sha256(identity.encode()).hexdigest()


def publication(item):
    """Only timezone-qualified timestamps establish a clock; never infer a missing timezone."""
    try:
        moment = datetime.fromisoformat(item.ts.replace('Z', '+00:00'))
        if len(item.ts) > 10 and moment.tzinfo:
            return moment.astimezone(BEIJING)
    except (ValueError, TypeError):
        pass
    return None


def day_of(item):
    moment = publication(item)
    return moment.date().isoformat() if moment else (item.ts[:10] or item.day)


def topic(category):
    return '国际' if category in ('全球', '环球') else category


def ordered(items, sources):
    def key(item):
        moment = publication(item)
        native = str(item.native_id or '')
        return (-int(day_of(item).replace('-', '')), moment is None,
                -moment.timestamp() if moment else 0, sources[item.source_id]['order'],
                -int(native) if native.isdigit() else 0, uid(item))
    seen = set()
    result = []
    for item in sorted(items, key=key):
        if uid(item) not in seen:
            seen.add(uid(item))
            result.append(item)
    return result


def dumps(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def digest(value):
    return hashlib.sha256(dumps(value).encode()).hexdigest()


def prepare(c, site, out):
    """Build the new sidecar contract from authorized input, without migrating old HTML or DBs."""
    sources = {sid: s for sid, s in c.sources.items() if c.private or sid in ALLOWED}
    items = [i for i in c.stream if i.source_id in sources]
    retired = getattr(c, 'retired', [])
    sources.update({i.source_id: RETIRED[i.source_id] for i in retired})
    items.extend(retired)
    from dataclasses import replace
    site = replace(site, sources=sources)
    for sid, issues in c.issues.items():
        if sid in sources:
            items.extend(i for issue in issues for i in c.issue_cards(sid, issue))
    by_day = {day: [] for day in c.days if day <= c.today}
    for item in ordered(items, sources):
        day = day_of(item)
        if day <= c.today:
            by_day.setdefault(day, []).append(item)
    scope = 'private' if c.private else 'public'
    source_index = [dict(id=sid, name=s['name'], alias=s.get('channel', sid)) for sid, s in
                    sorted(sources.items(), key=lambda pair: pair[1]['order'])]
    path = out / 'archive/manifest.json'
    try:
        previous = json.loads(path.read_text())
    except (OSError, ValueError):
        previous = {}
    # The schema, templates, visible source contract and shared assets are one compatibility key.
    code = ''.join(p.read_text() for p in (Path(__file__), Path(render.__file__),
                                         Path(__file__).with_name('pages.py'), Path(__file__).with_name('phosphor.json')))
    compatibility = digest([SCHEMA, scope, sources, site.assets, code])
    compatible = previous.get('compatibility') == compatibility
    # Inputs are the complete retained store; a removed last item must clear its owning day.
    if previous.get('scope') == scope and previous.get('sources') == source_index:
        for day in previous.get('days', {}):
            if day <= c.today:
                by_day.setdefault(day, [])
    elif previous:
        # A differently scoped baseline cannot contribute even an empty private date.
        for pattern in ('archive/data/????-??-??.json', 'archive/????-??-??.html'):
            for stale in out.glob(pattern):
                if stale.stem not in by_day:
                    stale.unlink()
    days, changed = {}, set()
    for day, members in by_day.items():
        fingerprint = digest([vars(i) for i in members])
        old = previous.get('days', {}).get(day, {})
        data_path = out / f'archive/data/{day}.json'
        if (not compatible or old.get('input') != fingerprint or not data_path.is_file()
                or hashlib.sha256(data_path.read_bytes()).hexdigest() != old.get('version')
                or not (out / f'archive/{day}.html').is_file()):
            page = render.Page(site, '../../', 'today')
            records = []
            for item in members:
                moment = publication(item)
                markup = card(page, item)
                records.append(dict(uid=uid(item), source=item.source_id, alias=item.filter_key,
                                    topic=topic(item.category), day=day, raw_time=item.ts,
                                    moment=moment.isoformat() if moment else None,
                                    precision='instant' if moment else 'date', html=markup))
            data_path.parent.mkdir(parents=True, exist_ok=True)
            data_path.write_text(dumps(dict(schema=SCHEMA, scope=scope, day=day, items=records)))
            changed.add(day)
        else:
            records = json.loads(data_path.read_text())['items']
        # Joint tuples, never independent per-source and per-topic counts.
        joint = sorted({(r['source'], r['alias'], r['topic']) for r in records})
        days[day] = dict(input=fingerprint, version=hashlib.sha256(data_path.read_bytes()).hexdigest(), joint=joint)
    manifest = dict(schema=SCHEMA, scope=scope, compatibility=compatibility,
                    earliest=min(days, default=None), days=days,
                    sources=source_index)
    manifest['version'] = digest(manifest)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(dumps(manifest))
    return by_day, changed


def shell(page, day):
    E = render.E
    return (f'<section id="news-history" data-day="{E(day)}" data-root="{E(page.rel)}">'
            f'<nav aria-label="资讯视图"><a href="{E(page.url("index.html#feed"))}">实时流</a> · '
            f'<a href="{E(page.url("hot.html"))}">热点</a></nav>'
            '<div class="news-controls"><button type="button" id="news-source-toggle" aria-label="筛选来源" '
            f'aria-expanded="false">{icon("sliders-horizontal")}</button><select id="news-source" aria-label="来源" hidden></select>'
            f'<button type="button" id="news-date-toggle" aria-label="时光机：选择日期">{icon("calendar-blank")}</button>'
            f'<span id="news-current"></span><button type="button" id="news-search-toggle" aria-label="搜索">{icon("magnifying-glass")}</button>'
            '<input id="news-query" type="search" aria-label="仅搜索已加载日期" placeholder="仅搜索已加载日期" hidden>'
            '<button type="button" id="news-clear">清筛选</button></div>'
            '<div id="news-topics" role="toolbar" aria-label="主题"></div>'
            '<div id="news-tech" role="toolbar" aria-label="科技细分" hidden></div>'
            f'<dialog id="news-calendar"><h2>时光机</h2><button type="button" id="news-calendar-close" aria-label="关闭">{icon("x")}</button>'
            '<button type="button" id="news-today">今天</button><div id="news-dates"></div></dialog>'
            '<p id="news-status" role="status"></p><div id="news-list"></div>'
            '<div id="news-sentinel"><button type="button" id="news-retry">上一匹配存档日</button>'
            '<button type="button" id="news-newer">下一匹配存档日</button></div>'
            '<button type="button" id="news-capsule" role="slider" aria-label="按北京时间日期定位" '
            'aria-orientation="vertical"><span></span><i></i></button></section>')
