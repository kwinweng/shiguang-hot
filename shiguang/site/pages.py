"""What goes on which page. Every page takes items from the same pool; none is written for one source.

  favorites.html     收藏 (rendered by app.js from this device's storage)
  archive/           日报: one day across every source
  index.html         首页: lead story and the mixed stream, filtered by topic and source
  hot.html           热点: tonight's hot-topics issue on top, the live ranking below
  columns.html       栏目: every source; issue sources link to <id>/, channels to a filtered home
  <id>/<date>.html   one issue of one source (<id>/index.html is the latest)

Pages that were merged away (all.html, Telegram channel pages, the hot source's index) become
redirects so old links and shared URLs keep working. Markup lives in render.py; build.py stages
the output and swaps it in.
"""
import re, shutil
from shiguang.config import ROOT, WEB, config, private_mode
from shiguang.enrich.rank import rank_home
from shiguang.enrich.topics import assign
from shiguang.ingest.feeds import load_issues, compress_images
from shiguang.model import OTHER, from_telegram, home_candidates, section_items
from shiguang.site import render
from shiguang.site.light import ambient_uris, light_css, photo_like
from shiguang.site.render import Page, Site

TABS = ['favorites', 'daily', 'home', 'hot', 'columns']
FAVORITES = {'enabled': True, 'label': '收藏', 'path': 'favorites.html'}
CORE = [('favorites', 'favorites.html', '收藏', 'bookmark'), ('daily', 'archive/index.html', '日报', 'archive'),
        ('home', 'index.html', '首页', 'home'), ('hot', 'hot.html', '热点', 'hot'), ('columns', 'columns.html', '栏目', 'all')]
DIGEST_ITEMS = 3   # cards per issue on a 日报 page; the rest is one tap away on the issue page
CHANNEL_DEPTH = 30 # latest messages per channel the home page keeps for its source filter


class Writer:
    """Writes pages into the staging tree and works out each page's light."""

    def __init__(self, site, out):
        self.site, self.out = site, out

    def image_path(self, path):
        return self.out / path if (self.out / path).is_file() else ROOT / path

    def is_photo(self, path):
        return photo_like(str(self.image_path(path)))

    def group_light(self, paths):
        """Light of a group's first photo, or None to keep the page's light."""
        photo = next((p for p in paths if self.is_photo(p)), None)
        return ambient_uris(str(self.image_path(photo))) if photo else None

    def write(self, path, active, title, body, light_from=(), tab=''):
        """Render one page. `light_from` lists candidate images; the first photo tints the background."""
        page = Page(self.site, '../' * path.count('/'), active, tab)
        light = next((p for p in light_from if self.is_photo(p)), '')
        illumination = light_css(str(self.image_path(light)) if light else '')
        target = self.out / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(render.document(page, title, body(page), illumination, light))

    def redirect(self, path, target, title):
        """`target` is site-root-relative; the redirect page links to it from its own folder."""
        file = self.out / path
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text(render.redirect('../' * path.count('/') + target, title))


def shown_images(items):
    return [p for item in items for p in item.images[:3]]


def all_images(items):
    return [p for item in items for p in item.images]


def count_items(issue):
    return sum(len(section.get('items', [])) for section in issue.get('sections', []))


def one_line(issue):
    """The issue's first one-line summary, if it has one."""
    return next((x if isinstance(x, str) else x.get('title') or x.get('body')
                 for b in issue.get('blocks', []) if b.get('type') == 'oneliner' for x in b.get('items', []) if x), None)


def write_pages(rows, hot, now, out, assets, inbox_only=False):
    """Write every page into `out`; returns the config used (build.py checks the public tree with it)."""
    cfg = config(); private = private_mode()
    topics = cfg['topics']
    sources = {s['id']: s for s in cfg['sources'] if private or s['visibility'] == 'public'}
    hot_source = cfg['hot']['source'] if cfg['hot']['source'] in sources else None
    by_channel = {s['channel']: s for s in sources.values() if s['type'] == 'telegram'}
    telegram = [from_telegram(r, by_channel[r['ch']], not private) for r in rows if r['ch'] in by_channel]
    hot = [from_telegram(r, by_channel[r['ch']], not private) for r in hot if r['ch'] in by_channel]
    if not private:
        for source in cfg['sources']:
            if source['visibility'] == 'private': shutil.rmtree(out / source['id'], ignore_errors=True)

    def tagged(items, s):
        """Topic for every item of source `s`: its own, a matching pattern, the source default, or 其他."""
        return assign(items, topics, s.get('topic', ''))

    # Inbox issues, newest first; images are recompressed into <id>/img/.
    issues = {}
    for s in sorted(sources.values(), key=lambda s: (s['order'], s['id'])):
        if s['type'] != 'inbox': continue
        loaded = load_issues(s, private)
        # Preserve adapter-owned media and other files; regenerate only pages.
        for page in (out / s['id']).glob('*.html'): page.unlink()
        if loaded:
            issues[s['id']] = [compress_images(d, base, out / s['id'] / 'img', s['id'] + '/img/') for d, base in loaded]
    latest = [item for sid, loaded in issues.items() for item in tagged(home_candidates(loaded[0], sources[sid]), sources[sid])]
    columns = [sources[sid] for sid in issues if sid != hot_source]
    channels = sorted((s for s in by_channel.values() if any(item.source_id == s['id'] for item in telegram)),
                      key=lambda s: (s['order'], s['id']))

    entries = CORE + [(s['id'], s['id'] + '/index.html', s['name'], s['icon']) for s in columns]
    site = Site(sources=sources, entries=entries, tabs=TABS, favorites=FAVORITES, private=private, now=now,
                topics=list(topics) + [OTHER], assets=assets)
    w = Writer(site, out)
    site.is_photo = w.is_photo

    for sid, loaded in issues.items():
        issue_pages(w, sources[sid], loaded, tagged, tab='hot' if sid == hot_source else 'columns')
        if sid == hot_source:
            w.redirect(f'{sid}/index.html', 'hot.html', '热点')

    if not inbox_only:
        w.write(FAVORITES['path'], 'favorites', FAVORITES['label'], render.favorites_body)
        shutil.copytree(ROOT / 'media', out / 'media', dirs_exist_ok=True)
        for asset in (WEB / 'assets').iterdir():
            if asset.is_file(): shutil.copyfile(asset, out / asset.name)
        home_page(w, telegram, latest, now)
        hot_page(w, hot, issues.get(hot_source, [None])[0], sources.get(hot_source), tagged)
        columns_page(w, columns, issues, channels, telegram)
        daily_pages(w, telegram, issues, tagged)
        # Merged pages keep their addresses.
        w.redirect('all.html', 'index.html', '首页')
        for s in channels:
            w.redirect(f'{s["id"]}/index.html', f'index.html?source={s["channel"]}', s['name'])
        (out / '.nojekyll').write_text('')

    print(f'built {len(telegram)} TG, {len(issues)} inbox sources -> {out}')
    return cfg


def issue_pages(w, s, loaded, tagged, tab):
    """<id>/<date>.html for every issue of an inbox source, <id>/index.html for the latest."""
    dates = [d['date'] for d in loaded]
    for n, issue in enumerate(loaded):
        lead = s.get('lead', s['name']).replace('{count}', str(count_items(issue)))
        note = ' · '.join([issue['date'], s['name'], s.get('note') or ('仅内网可见' if s['visibility'] == 'private' else '每日精选')])

        def body(page, issue=issue, lead=lead, note=note):
            content = render.heading(page, lead, note)
            content += render.date_chips(dates, issue['date'], today=w.site.today) if len(dates) > 1 else ''
            if s.get('reading'):
                content += render.reading_switch()
            content += render.blocks(page, issue)
            for section in issue.get('sections', []):
                parts = [part.strip() for part in re.split(r'[|｜]', section.get('title') or '')]
                members = tagged(section_items(section, issue, s), s)
                content += render.group(parts, ''.join(render.card(page, item, reading=True) for item in members),
                                        light=w.group_light(all_images(members)))
            return content
        light = [p for section in issue.get('sections', []) for p in all_images(section_items(section, issue, s))]
        w.write(f'{s["id"]}/{issue["date"]}.html', s['id'], s['name'], body, light, tab)
        if n == 0 and tab != 'hot':
            w.write(f'{s["id"]}/index.html', s['id'], s['name'], body, light, tab)


def home_page(w, telegram, latest, now):
    """首页: the lead story, then the ranked stream, filtered in the page by topic and source.

    The stream is capped per source. So that a source filter (栏目 links to index.html?source=…)
    shows more than a handful, the page also carries each channel's latest messages and every
    card of each latest issue, hidden until a filter or a search is chosen.
    """
    pool = telegram + latest
    ranked = rank_home(pool, w.site.sources, now)
    hero, stream = (ranked[0], ranked[1:]) if ranked else (None, [])
    shown = {id(item) for item in ranked}
    recent = {}
    for item in sorted(telegram, key=lambda item: item.ts, reverse=True):
        recent.setdefault(item.source_id, [])
        if len(recent[item.source_id]) < CHANNEL_DEPTH: recent[item.source_id].append(item)
    more = [item for item in [i for group in recent.values() for i in group] + latest if id(item) not in shown]
    today = now.date().isoformat()
    count = sum(item.day == today for item in pool)
    note = (f'{now.month}月{now.day}日 周{"一二三四五六日"[now.weekday()]} · 更新于 {now:%H:%M} · '
            f'{len({item.source_id for item in pool})} 个来源')

    def body(page):
        content = render.heading(page, f'今天 {count} 条要闻', note)
        if hero: content += render.section_label('此刻要闻', '精选') + render.card(page, hero, 'hero')
        content += render.filters(page, ranked + more)
        content += render.section_label('最新动态', '实时收录 · 持续更新')
        return content + render.cards(page, stream) + render.cards(page, more, more=True)
    w.write('index.html', 'home', '首页', body, all_images([hero] if hero else []))


def hot_page(w, hot, issue, s, tagged):
    """热点: the latest hot-topics issue (tonight's once it is out at 22:00), then the live ranking."""
    def body(page):
        when = f'{s["name"]}{s.get("note", "")} · ' if s else ''
        content = render.heading(page, '这几件事，大家都在说', when + '实时热榜每小时更新')
        if issue:
            title = s['name'] if issue['date'] == w.site.today else f'{s["name"]}（{issue["date"][5:]}）'
            members = tagged([item for section in issue.get('sections', []) for item in section_items(section, issue, s)], s)
            content += render.group([title], render.blocks(page, issue) + render.cards(page, members),
                                    source_id=s['id'], cls='group digest-source', light=w.group_light(all_images(members)))
        if hot:
            content += render.group(['实时热榜'], render.section_label('过去 48 小时', '多个频道共同关注') + render.ranked(page, hot),
                                    cls='group live-ranking')
        return content
    images = list(render.chart_images(issue)) if issue else []
    w.write('hot.html', 'hot', '热点', body, images + shown_images(hot))


def columns_page(w, columns, issues, channels, telegram):
    """栏目: issue sources first (they link to their latest issue), then the Telegram channels."""
    def issue_entry(s):
        latest = issues[s['id']][0]
        line = one_line(latest) or f'{latest["date"]} · {count_items(latest)} 条'
        return (s['id'] + '/index.html', s['icon'], s['name'], line)

    def channel_entry(s):
        newest = max((item for item in telegram if item.source_id == s['id']), key=lambda item: item.ts)
        return (f'index.html?source={s["channel"]}', s['icon'], s['name'], '最新：' + newest.title)

    def body(page):
        content = render.heading(page, '所有栏目，一页看全', f'{len(columns)} 个每日栏目 · {len(channels)} 个 TG 频道')
        content += render.column_list(page, '每日栏目', [issue_entry(s) for s in columns])
        content += render.column_list(page, 'TG 频道', [channel_entry(s) for s in channels])
        return content
    w.write('columns.html', 'columns', '栏目', body)


def daily_pages(w, telegram, issues, tagged):
    """日报: one page per day. Each issue source shows its summary and first cards; Telegram comes last, by topic."""
    sources, site = w.site.sources, w.site
    days = sorted({item.day for item in telegram} | {d['date'] for loaded in issues.values() for d in loaded}, reverse=True)
    channels = sorted((s for s in sources.values() if s['type'] == 'telegram'), key=lambda s: (s['order'], s['id']))

    def parts(day):
        """[(source, issue, items)] in page order, then [(topic, Telegram items)]."""
        found = []
        for sid, loaded in issues.items():
            issue = next((d for d in loaded if d['date'] == day), None)
            if issue:
                s = sources[sid]
                found.append((s, issue, tagged([i for sec in issue.get('sections', []) for i in section_items(sec, issue, s)], s)))
        tg = [item for s in channels for item in telegram if item.source_id == s['id'] and item.day == day]
        topic = lambda item: item.category if item.category in site.topics else OTHER
        return found, [(name, [item for item in tg if topic(item) == name]) for name in site.topics]

    def digest(page, day):
        found, topics = parts(day)
        content = ''
        for s, issue, items in found:
            shown = items[:DIGEST_ITEMS]
            more = (render.more_link(page, f'{s["id"]}/{day}.html', f'看完整一期 · 共 {len(items)} 条')
                    if len(items) > len(shown) else '')
            content += render.group([s['name']], render.blocks(page, issue) + render.cards(page, shown) + more,
                                    source_id=s['id'], cls='group digest-source',
                                    light=w.group_light(list(render.chart_images(issue)) + all_images(shown)))
        if any(group for _, group in topics):
            inner = ''.join(render.group([topic], render.cards(page, group), level=3, cls='group group--sub',
                                         light=w.group_light(all_images(group)))
                            for topic, group in topics if group)
            content += render.group(['TG 频道'], inner, cls='group digest-source')
        return content

    def images(day):
        found, topics = parts(day)
        return ([p for _, issue, items in found for p in list(render.chart_images(issue)) + shown_images(items[:DIGEST_ITEMS])]
                + [p for _, group in topics for p in shown_images(group)])

    for day in days:
        w.write(f'archive/{day}.html', 'daily', day + ' 日报', lambda page, day=day:
                render.heading(page, day + ' 日报', '按北京时间汇集各来源精选')
                + render.date_chips(days, day, today=site.today) + digest(page, day), images(day))
    w.write('archive/index.html', 'daily', '日报', lambda page:
            render.heading(page, '每一天，都有迹可循', '回看世界变化的每个切片。')
            + (render.date_chips(days, days[0], ' 日报', today=site.today) + digest(page, days[0]) if days else ''),
            images(days[0]) if days else [])
