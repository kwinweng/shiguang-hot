"""What goes on which page. Every page takes items from one pool; none is written for one source.

  index.html            今日: today's page (archive/<date>.html for other days, via the time machine)
  hot.html              热点: stories over the heat threshold, in time order, with a 24-hour timeline
  columns.html          栏目: every source by channel, and every tag
  tag/<slug>.html       one tag over the last few days
  <id>/index.html       a Telegram channel or feed over the last few days
  favorites.html        收藏 (rendered by app.js from this device's storage)
  <id>/<date>.html      one issue of one source (<id>/index.html is the latest)

Merged pages keep their addresses as redirects (all.html, archive/index.html, the hot source's
index). Markup lives in render.py; build.py stages and swaps the output.
"""
import re, shutil
from datetime import date, datetime, time, timedelta
from shiguang.config import PLATFORMS, ROOT, WEB, config, private_mode
from shiguang.enrich.rank import rank_home
from shiguang.enrich.topics import assign
from shiguang.ingest.feeds import load_issues, compress_images
from shiguang.model import BEIJING, OTHER, from_entry, from_telegram, home_candidates, section_items
from shiguang.site import render
from shiguang.site.light import ambient_uris, light_css, photo_like
from shiguang.site.render import Page, Site

TABS = ['today', 'hot', 'columns', 'favorites']
FAVORITES = {'enabled': True, 'label': '收藏', 'path': 'favorites.html'}
CORE = [('today', 'index.html', '今日', 'home'), ('hot', 'hot.html', '热点', 'hot'),
        ('columns', 'columns.html', '栏目', 'all'), ('favorites', 'favorites.html', '收藏', 'bookmark')]
DIGEST_ITEMS = 3   # cards per issue in a day's 各栏目 section; the rest is one tap away on the issue page
EARLY = 6          # before this hour, today's page also shows yesterday
HOT_DAYS = 3       # days on the 热点 timeline
TAG_DAYS = 3       # days on a tag page
TAG_LIMIT = 150
TAG_ICONS = {'全球': 'world', '开发者': 'code', 'AI': 'code', '财经': 'hot'}


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


def end_of(day):
    return datetime.combine(date.fromisoformat(day), time(23, 59), BEIJING)


class Content:
    """Everything loaded for one build, and the views pages ask of it."""

    def __init__(self, cfg, private, rows, hot, entries, now, out):
        self.cfg, self.private, self.now = cfg, private, now
        self.today = now.astimezone(BEIJING).date().isoformat()
        self.topics = cfg['topics']
        self.sources = {s['id']: s for s in cfg['sources'] if private or s['visibility'] == 'public'}
        self.hot_source = cfg['hot']['source'] if cfg['hot']['source'] in self.sources else None
        by_channel = {s['channel']: s for s in self.sources.values() if s['type'] == 'telegram'}
        self.channels = by_channel
        self.telegram = [from_telegram(r, by_channel[r['ch']], not private) for r in rows if r['ch'] in by_channel]
        self.hot, self.heat = [], {}
        for r in hot:
            if r['ch'] in by_channel:
                item = from_telegram(r, by_channel[r['ch']], not private)
                item.reach = r.get('sources', 0)
                self.hot.append(item)
                self.heat[(item.source_id, item.native_id)] = (r.get('heat', 0), item.reach)
        for item in self.telegram:   # the same badge on the day pages
            item.reach = self.heat.get((item.source_id, item.native_id), (0, 0))[1]
        self.feed = [self.tagged([from_entry(e, self.sources[e['source']])], self.sources[e['source']])[0]
                     for e in entries if e['source'] in self.sources]
        self.stream = self.telegram + self.feed
        # Inbox issues, newest first; images are recompressed into <id>/img/.
        self.issues = {}
        for s in sorted(self.sources.values(), key=lambda s: (s['order'], s['id'])):
            if s['type'] != 'inbox': continue
            loaded = load_issues(s, private)
            # Preserve adapter-owned media and other files; regenerate only pages.
            for page in (out / s['id']).glob('*.html'): page.unlink()
            if loaded:
                self.issues[s['id']] = [compress_images(d, base, out / s['id'] / 'img', s['id'] + '/img/') for d, base in loaded]
        self.days = sorted({i.day for i in self.stream} | {d['date'] for loaded in self.issues.values() for d in loaded},
                           reverse=True)

    def tagged(self, items, s):
        """Topic for every item of source `s`: its own, a matching pattern, the source default, or 其他."""
        return assign(items, self.topics, s.get('topic', ''))

    def issue_on(self, sid, day):
        return next((d for d in self.issues.get(sid, []) if d['date'] == day), None)

    def issue_cards(self, sid, issue):
        s = self.sources[sid]
        return self.tagged([i for sec in issue.get('sections', []) for i in section_items(sec, issue, s)], s)

    def pool(self, day):
        """Every item of one day: stream messages and the cards of that day's issues (the hot source's
        issue is shown on its own at the top of the page)."""
        items = [i for i in self.stream if i.day == day]
        for sid in self.issues:
            issue = self.issue_on(sid, day)
            if issue and sid != self.hot_source:
                items += self.tagged(home_candidates(issue, self.sources[sid]), self.sources[sid])
        return items

    def recent(self, days):
        """Stream items and issue cards of the last `days` days, newest first."""
        floor = (date.fromisoformat(self.today) - timedelta(days=days - 1)).isoformat()
        items = [i for i in self.stream if i.day >= floor]
        for sid, loaded in self.issues.items():
            if sid == self.hot_source: continue
            items += [i for issue in loaded if issue['date'] >= floor for i in self.issue_cards(sid, issue)]
        return sorted(items, key=lambda i: i.moment or end_of(i.day), reverse=True)


def write_pages(rows, hot, now, out, assets, entries=(), inbox_only=False):
    """Write every page into `out`; returns the config used (build.py checks the public tree with it)."""
    cfg = config(); private = private_mode()
    if not private:
        for source in cfg['sources']:
            if source['visibility'] == 'private': shutil.rmtree(out / source['id'], ignore_errors=True)
    c = Content(cfg, private, rows, hot, entries, now, out)
    columns = [c.sources[sid] for sid in c.issues]
    entries_nav = CORE + [(s['id'], s['id'] + '/index.html', s['name'], s['icon']) for s in columns if s['id'] != c.hot_source]
    site = Site(sources=c.sources, entries=entries_nav, tabs=TABS, favorites=FAVORITES, private=private, now=now,
                topics=list(c.topics) + [OTHER], assets=assets)
    w = Writer(site, out)
    site.is_photo = w.is_photo

    for sid, loaded in c.issues.items():
        issue_pages(w, c, sid, loaded)
        if sid == c.hot_source:
            w.redirect(f'{sid}/index.html', 'index.html', '今日')

    if not inbox_only:
        w.write(FAVORITES['path'], 'favorites', FAVORITES['label'], render.favorites_body)
        shutil.copytree(ROOT / 'media', out / 'media', dirs_exist_ok=True)
        for asset in (WEB / 'assets').iterdir():
            if asset.is_file(): shutil.copyfile(asset, out / asset.name)
        for day in c.days:
            day_page(w, c, day)
        if c.today not in c.days:
            day_page(w, c, c.today)
        hot_page(w, c)
        columns_page(w, c)
        tag_pages(w, c)
        stream_source_pages(w, c)
        # Merged pages keep their addresses.
        w.redirect('all.html', 'index.html', '今日')
        w.redirect('archive/index.html', 'index.html', '今日')
        (out / '.nojekyll').write_text('')

    print(f'built {len(c.telegram)} TG, {len(c.feed)} feed, {len(c.issues)} inbox sources -> {out}')
    return cfg


def issue_pages(w, c, sid, loaded):
    """<id>/<date>.html for every issue of an inbox source, <id>/index.html for the latest."""
    s = c.sources[sid]
    tab = 'today' if sid == c.hot_source else 'columns'
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
                members = c.tagged(section_items(section, issue, s), s)
                content += render.group(parts, ''.join(render.card(page, item, reading=True) for item in members),
                                        light=w.group_light(all_images(members)))
            return content
        light = all_images(c.issue_cards(sid, issue))
        w.write(f'{sid}/{issue["date"]}.html', sid, s['name'], body, light, tab)
        if n == 0 and sid != c.hot_source:
            w.write(f'{sid}/index.html', sid, s['name'], body, light, tab)


def day_page(w, c, day):
    """今日 for one day: the hot-topics issue, the day's lead story and stream, then each column's
    summary. Today is index.html; every day is also archive/<date>.html for the time machine."""
    is_today = day == c.today
    pool = c.pool(day)
    ranked = rank_home(pool, c.sources, c.now if is_today else end_of(day))
    # The lead story is the day's hottest (today: the newest hot one), not merely the newest post.
    hot_today = [i for i in pool if (i.source_id, i.native_id) in c.heat]
    if hot_today:
        lead = (max(hot_today, key=lambda i: i.ts) if is_today
                else max(hot_today, key=lambda i: c.heat[(i.source_id, i.native_id)][0]))
        ranked = [lead] + [i for i in ranked if i is not lead]
    hero, stream = (ranked[0], ranked[1:]) if ranked else (None, [])
    shown = {id(i) for i in ranked}
    more = sorted((i for i in pool if id(i) not in shown), key=lambda i: i.ts, reverse=True)
    hot_issue = c.issue_on(c.hot_source, day) if c.hot_source else None
    digests = [(c.sources[sid], c.issue_on(sid, day)) for sid in c.issues if sid != c.hot_source and c.issue_on(sid, day)]
    yesterday = (date.fromisoformat(day) - timedelta(days=1)).isoformat()
    early = is_today and c.now.astimezone(BEIJING).hour < EARLY and yesterday in c.days
    when = render.day_label(day)
    sources_count = len({i.source_id for i in pool})

    def body(page):
        if is_today:
            content = render.heading(page, f'今天 {len(pool)} 条要闻',
                                     f'{when} · 更新于 {c.now.astimezone(BEIJING):%H:%M} · {sources_count} 个来源')
        else:
            content = render.heading(page, when, f'{len(pool)} 条 · {sources_count} 个来源')
        content += render.time_machine(page, c.days if day in c.days else [day] + c.days, day, c.today)
        if hot_issue:
            s = c.sources[c.hot_source]
            members = c.issue_cards(c.hot_source, hot_issue)
            link = (render.more_link(page, f'{s["id"]}/{day}.html', f'看完整的{s["name"]} · 共 {len(members)} 条')
                    if len(members) > DIGEST_ITEMS else '')
            content += render.group([s['name']], render.blocks(page, hot_issue) + render.cards(page, members[:DIGEST_ITEMS]) + link,
                                    source_id=s['id'], cls='group digest-source today-top', light=w.group_light(all_images(members)))
        if hero:
            content += render.section_label('此刻要闻' if is_today else '当日要闻', '精选') + render.card(page, hero, 'hero')
        if ranked:
            content += render.filters(page, ranked + more)
            content += render.section_label('最新动态' if is_today else '当天动态', '实时收录 · 持续更新' if is_today else '')
            content += render.cards(page, stream) + render.cards(page, more, more=True)
            if more:
                content += render.show_all(len(pool))
        elif not hot_issue:
            content += render.empty('home', '这一天还没有内容。')
        if digests:
            content += render.section_label('各栏目今天' if is_today else '各栏目当天')
            for s, issue in digests:
                items = c.issue_cards(s['id'], issue)
                shown_items = items[:DIGEST_ITEMS]
                link = (render.more_link(page, f'{s["id"]}/{day}.html', f'看完整一期 · 共 {len(items)} 条')
                        if len(items) > len(shown_items) else '')
                content += render.group([s['name']], render.blocks(page, issue) + render.cards(page, shown_items) + link,
                                        source_id=s['id'], cls='group digest-source',
                                        light=w.group_light(list(render.chart_images(issue)) + all_images(shown_items)))
        if early:
            before = rank_home(c.pool(yesterday), c.sources, end_of(yesterday))[:10]
            content += render.group(['昨天'], render.cards(page, before)
                                    + render.more_link(page, f'archive/{yesterday}.html', '看昨天全部'), cls='group yesterday')
        return content

    images = (list(render.chart_images(hot_issue)) if hot_issue else []) + all_images([hero] if hero else [])
    title = '今日' if is_today else when
    if is_today:
        w.write('index.html', 'today', title, body, images)
    w.write(f'archive/{day}.html', 'today', title, body, images, tab='today')


def hot_page(w, c):
    """热点: stories over the heat threshold, newest first, grouped by hour under a 24-hour timeline."""
    now = c.now.astimezone(BEIJING)
    first = (now.date() - timedelta(days=HOT_DAYS - 1)).isoformat()
    stories = [i for i in c.hot if i.day >= first and i.moment <= c.now]
    key = lambda i: i.moment.astimezone(BEIJING).strftime('%Y-%m-%d-%H')
    buckets = {}
    for item in stories:
        buckets.setdefault(key(item), []).append(item)
    days = [(now.date() - timedelta(days=n)).isoformat() for n in reversed(range(HOT_DAYS))]

    def body(page):
        content = render.heading(page, '此刻，大家在说什么', f'过去 {HOT_DAYS} 天 · {len(stories)} 条 · 每 30 分钟更新')
        content += render.timeline(page, {k: len(v) for k, v in buckets.items()}, days, now.strftime('%Y-%m-%d-%H'))
        if not stories:
            return content + render.empty('hot', '这几天还没有多个频道同时关注的消息。')
        content += '<div class="hot-list">'
        for hour in sorted(buckets, reverse=True):
            content += render.hour_heading(hour) + render.cards(page, buckets[hour])
        return content + '</div>'
    w.write('hot.html', 'hot', '热点', body, shown_images(stories[:10]))


def columns_page(w, c):
    """栏目 by channel (grouped by platform) and by tag."""
    latest_of = {}
    for item in sorted(c.stream, key=lambda i: i.ts):
        latest_of[item.source_id] = item
    by_platform = {}
    for s in sorted(c.sources.values(), key=lambda s: (s['order'], s['id'])):
        if s['type'] == 'inbox' and s['id'] in c.issues:
            latest = c.issues[s['id']][0]
            path = f'{s["id"]}/{latest["date"]}.html' if s['id'] == c.hot_source else f'{s["id"]}/index.html'
            line = one_line(latest) or f'{latest["date"]} · {count_items(latest)} 条'
        elif s['type'] != 'inbox' and s['id'] in latest_of:
            path, line = f'{s["id"]}/index.html', '最新：' + latest_of[s['id']].title
        else:
            continue
        by_platform.setdefault(s['platform'], []).append((path, s['icon'], s['name'], line))
    recent = c.recent(TAG_DAYS)
    tags = []
    for name in list(c.topics) + [OTHER]:
        items = [i for i in recent if i.category == name]
        if items:
            slug = c.cfg['topic_slugs'].get(name, 'other')
            tags.append((f'tag/{slug}.html', TAG_ICONS.get(name, 'all'), name, f'近 {TAG_DAYS} 天 {len(items)} 条 · {items[0].title}'))

    def body(page):
        content = render.heading(page, '所有栏目，一页看全', f'{sum(len(v) for v in by_platform.values())} 个来源 · {len(tags)} 个标签')
        content += render.view_switch([('channel', '按渠道'), ('tag', '按标签')])
        content += '<div data-panel="channel">' + ''.join(
            render.column_list(page, label, by_platform[key]) for key, label in PLATFORMS.items() if key in by_platform) + '</div>'
        content += '<div data-panel="tag">' + render.column_list(page, '标签', tags) + '</div>'
        return content
    w.write('columns.html', 'columns', '栏目', body)


def tag_pages(w, c):
    """tag/<slug>.html: one tag across every source over the last few days, newest first, by day."""
    recent = c.recent(TAG_DAYS)
    for name in list(c.topics) + [OTHER]:
        items = [i for i in recent if i.category == name][:TAG_LIMIT]
        slug = c.cfg['topic_slugs'].get(name, 'other')

        def body(page, name=name, items=items):
            content = render.heading(page, name, f'近 {TAG_DAYS} 天 · {len(items)} 条 · {len({i.source_id for i in items})} 个来源')
            if not items:
                return content + render.empty('all', '这几天还没有这个标签的内容。')
            return content + render.filters(page, items, topics=False) + by_day(page, items)
        w.write(f'tag/{slug}.html', 'columns', name, body, shown_images(items[:10]), tab='columns')


def by_day(page, items):
    return ''.join(render.section_label(render.day_label(day)) + render.cards(page, [i for i in items if i.day == day])
                   for day in sorted({i.day for i in items}, reverse=True))


def stream_source_pages(w, c):
    """<id>/index.html for a Telegram channel or a feed: its last few days (at least its latest 30)."""
    floor = (date.fromisoformat(c.today) - timedelta(days=TAG_DAYS - 1)).isoformat()
    for s in c.sources.values():
        if s['type'] == 'inbox': continue
        own = sorted((i for i in c.stream if i.source_id == s['id']), key=lambda i: i.ts, reverse=True)
        if not own: continue
        items = [i for i in own if i.day >= floor]
        if len(items) < 30: items = own[:30]

        def body(page, s=s, items=items):
            platform = PLATFORMS.get(s['platform'], '')
            content = render.heading(page, s['name'], f'{platform} · 最近 {len(items)} 条')
            return content + render.filters(page, items) + by_day(page, items)
        w.write(f'{s["id"]}/index.html', s['id'], s['name'], body, shown_images(items[:10]), tab='columns')
