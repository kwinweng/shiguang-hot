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
import os, re, shutil
from datetime import date, datetime, time, timedelta
from shiguang.config import PLATFORMS, ROOT, WEB, config, private_mode
from shiguang.site import history
from shiguang.enrich.topics import assign
from shiguang.ingest.feeds import load_issues, compress_images
from shiguang.model import BEIJING, OTHER, from_entry, from_telegram, home_candidates, section_items
from shiguang.site import render
from shiguang.site.light import ambient_uris, light_css, photo_like
from shiguang.site.render import Page, Site

TABS = ['today', 'hot', 'columns', 'favorites']
FAVORITES = {'enabled': True, 'label': '收藏', 'path': 'favorites.html'}
CORE = [('today', 'index.html', '今日', 'home'), ('hot', 'index.html#screens/look', '资讯', 'hot'),
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
        self.sources = {s['id']: s for s in cfg['sources']
                        if private or (s['visibility'] == 'public' and s['id'] in history.ALLOWED)}
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
        self.retired = [from_telegram(r, history.RETIRED[r['ch']], not private)
                        for r in rows if r['ch'] in history.RETIRED and r['day'] < self.today]
        # Inbox issues, newest first; images are recompressed into <id>/img/.
        self.issues = {}
        sample = os.getenv('SAMPLE_DATA') == '1' or bool(rows) and all(r['title'].startswith('[示例]') for r in rows)
        for s in sorted(self.sources.values(), key=lambda s: (s['order'], s['id'])):
            if s['type'] != 'inbox': continue
            loaded = [] if sample else load_issues(s, private)
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
        """Stream items and issue cards of the last `days` days, newest first. Private sources (邮件精华)
        are left out: tag pages have no password, so this holds in the private build too."""
        floor = (date.fromisoformat(self.today) - timedelta(days=days - 1)).isoformat()
        public = lambda sid: self.sources[sid]['visibility'] != 'private'
        items = [i for i in self.stream if i.day >= floor and public(i.source_id)]
        for sid, loaded in self.issues.items():
            if sid == self.hot_source or not public(sid): continue
            items += [i for issue in loaded if issue['date'] >= floor for i in self.issue_cards(sid, issue)]
        return sorted(items, key=lambda i: i.moment or end_of(i.day), reverse=True)


def write_pages(rows, hot, now, out, assets, entries=(), inbox_only=False):
    """Write every page into `out`; returns the config used (build.py checks the public tree with it)."""
    cfg = config(); private = private_mode()
    if not private:
        for source in cfg['sources']:
            if source['visibility'] == 'private' or source['id'] not in history.ALLOWED:
                shutil.rmtree(out / source['id'], ignore_errors=True)
    c = Content(cfg, private, rows, hot, entries, now, out)
    if not inbox_only:
        for sid in history.RETIRED:
            shutil.rmtree(out / sid, ignore_errors=True)
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
        visible_channels = {s['channel'] for s in c.sources.values() if s['type'] == 'telegram'}
        visible_channels.update(i.filter_key for i in c.retired)
        for cached in (out / 'media').iterdir() if (out / 'media').is_dir() else ():
            if not private and cached.name not in visible_channels:
                if cached.is_dir(): shutil.rmtree(cached)
                else: cached.unlink()
        for channel in visible_channels:
            source_media = ROOT / 'media' / channel
            if source_media.is_dir():
                shutil.copytree(source_media, out / 'media' / channel, dirs_exist_ok=True)
        for asset in (WEB / 'assets').iterdir():
            if asset.is_file(): shutil.copyfile(asset, out / asset.name)
        news_days, changed = history.prepare(c, site, out)
        from dataclasses import replace
        archive_site = replace(site, sources={**site.sources, **history.RETIRED})
        archive_writer = Writer(archive_site, out)
        for day in changed | {c.today}:
            news_day_page(w if day == c.today else archive_writer, c, day, news_days.get(day, []))
        hot_page(w, c)
        columns_page(w, c)
        tag_pages(w, c)
        stream_source_pages(w, c)
        # Merged pages keep their addresses.
        w.redirect('all.html', 'index.html', '今日')
        w.redirect('archive/index.html', 'index.html', '今日')
        (out / '.nojekyll').write_text('')

        from shiguang.site.news import publish
        publish(c, out)

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


def news_day_page(w, c, day, members):
    """Uncapped chronological news; column summaries belong only to today's surface."""
    def body(page):
        content = render.heading(page, '今日' if day == c.today else render.day_label(day), '北京时间')
        content += '<div class="today-summaries">'
        if day == c.today:
            for sid in c.issues:
                issue = c.issue_on(sid, day)
                if issue:
                    source = c.sources[sid]
                    content += render.group([source['name']], render.blocks(page, issue)
                                            + render.cards(page, c.issue_cards(sid, issue)[:4])
                                            + render.more_link(page, f'{sid}/{day}.html', '完整期刊'), source_id=sid)
        content += '</div>' + history.shell(page, day)
        # Standalone HTML remains readable when sidecars or JavaScript are absent.
        content += '<div id="news-fallback">' + ''.join(history.card(page, item) for item in members) + '</div>'
        return content
    if day == c.today:
        w.write('index.html', 'today', '今日', body)
    w.write(f'archive/{day}.html', 'today', render.day_label(day), body, tab='today')




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
