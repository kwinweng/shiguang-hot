"""Build the static site: load sources, normalize items, rank, render pages, verify privacy.

Data shapes live in items.py and all markup in render.py; this module only decides what goes on
which page. Output is staged in a temporary tree and swapped in atomically.
"""
import ctypes, fcntl, hashlib, os, re, shutil, signal, tempfile, threading
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from feeds import ROOT, config, private_mode, load_issues, compress_images
from light import ambient_uris, light_css, photo_like
from items import BEIJING, from_telegram, home_candidates, issue_items, section_items
import render
from render import E, Page, Site

@contextmanager
def staged_output(destination):
    """Keep live output untouched until a complete tree passes validation."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    with open(destination.with_name(destination.name+'.build.lock'), 'a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        # SIGKILL cannot run cleanup; reclaim abandoned staging trees next build.
        for stale in destination.parent.glob(destination.name+'.tmp-*'):
            if stale.is_dir() and not stale.is_symlink(): shutil.rmtree(stale)
        temporary=Path(tempfile.mkdtemp(prefix=destination.name+'.tmp-', dir=destination.parent))
        handlers={}
        def interrupted(signum, frame):
            raise SystemExit(128+signum)
        if threading.current_thread() is threading.main_thread():
            for sig in (signal.SIGTERM, signal.SIGINT):
                handlers[sig]=signal.signal(sig, interrupted)
        try:
            if destination.exists():
                shutil.copytree(destination, temporary, dirs_exist_ok=True, symlinks=True)
            yield temporary
            if destination.exists():
                # Linux RENAME_EXCHANGE keeps the served path present throughout.
                libc=ctypes.CDLL(None, use_errno=True)
                exchange=libc.renameat2
                exchange.argtypes=[ctypes.c_int,ctypes.c_char_p,ctypes.c_int,ctypes.c_char_p,ctypes.c_uint]
                exchange.restype=ctypes.c_int
                if exchange(-100,os.fsencode(temporary),-100,os.fsencode(destination),2):
                    error=ctypes.get_errno()
                    raise OSError(error,os.strerror(error),str(destination))
            else:
                os.rename(temporary,destination)
        finally:
            shutil.rmtree(temporary, ignore_errors=True)
            for sig,handler in handlers.items(): signal.signal(sig,handler)

def build(rows, hot, now, inbox_only=False):
    out = Path(os.getenv('SITE_OUT', ROOT/'site')).resolve()
    if out == ROOT or ROOT.is_relative_to(out): raise ValueError('SITE_OUT 不能覆盖仓库')
    with staged_output(out) as temporary:
        _build(rows, hot, now, temporary, inbox_only)
    print(f'built site -> {out}')


DEFAULT_FAVORITES = {'enabled': True, 'label': '收藏', 'path': 'favorites.html', 'column': True}


def nav_tabs(cfg, private):
    tabs = cfg.get('nav', {}).get('tabs', {}).get('private' if private else 'public',
                                                   ['mail' if private else 'all', 'daily', 'home', 'news', 'x'])
    if len(tabs) != 5 or tabs[2] != 'home' or len(set(tabs)) != 5:
        raise ValueError('nav.tabs 必须为五个不同槽位，首页居中')
    return tabs


def publish_assets(out, full):
    """Copy style.css / app.js under content-hashed names so browsers can cache them safely.

    Inbox-only builds keep older hashed files: pages from the last full build still point at them.
    """
    names = {}
    for kind, source in (('css', ROOT / 'style.css'), ('js', ROOT / 'app.js')):
        data = source.read_bytes()
        names[kind] = f'{source.stem}.{hashlib.sha256(data).hexdigest()[:10]}{source.suffix}'
        if full:
            for stale in out.glob(f'{source.stem}.*{source.suffix}'):
                if stale.name != names[kind]: stale.unlink()
        (out / names[kind]).write_bytes(data)
    icons = hashlib.sha256()
    for asset in sorted((ROOT / 'assets').iterdir()):
        if asset.is_file(): icons.update(asset.read_bytes())
    names['version'] = icons.hexdigest()[:10]
    return names


def rank_home(candidates, sources, now):
    """Freshness-weighted ranking, then round-robin so every source gets a turn before any repeats."""
    local_now = now.astimezone(BEIJING)

    def score(item):
        age = max(0, (local_now - item.moment).total_seconds() / 3600)
        return sources[item.source_id].get('home_weight', 1) / (1 + age / 24)

    buckets = []
    for s in sources.values():
        own = [item for item in candidates if item.source_id == s['id']]
        cap = s.get('home_cap', 4 if s['type'] == 'telegram' else 8)
        buckets.append(sorted(own, key=lambda item: (score(item), item.ts), reverse=True)[:cap])
    ranked = []
    for n in range(max((len(b) for b in buckets), default=0)):
        ranked.extend(sorted((b[n] for b in buckets if len(b) > n), key=score, reverse=True))
    return ranked


def verify_public(out, cfg):
    """Refuse to publish if anything from a private source leaked into the public tree."""
    forbidden = [s for s in cfg['sources'] if s['visibility'] == 'private']
    for s in forbidden:
        if (out / s['id']).exists(): raise RuntimeError('公开产物存在 private 目录')
    private_text = []
    for source in forbidden:
        if source['type'] == 'inbox':
            for data, base in load_issues(source, True):
                for section in data.get('sections', []):
                    for item in section.get('items', []):
                        private_text.extend(E(item.get(field)) for field in ('title', 'body') if len(item.get(field) or '') >= 16)
                for block in data.get('blocks', []):
                    values = [block.get('title'), block.get('caption')]
                    for item in block.get('items', []) or []:
                        values.extend([item] if isinstance(item, str) else [item.get('title'), item.get('body')])
                    private_text.extend(E(value) for value in values if isinstance(value, str) and len(value) >= 16)
    for p in out.rglob('*'):
        if p.suffix in ('.html', '.json', '.webmanifest', '.svg', '.css', '.js'):
            text = p.read_text()
            if any(s['name'] in text or f'{s["id"]}/' in text for s in forbidden): raise RuntimeError('公开产物存在 private 标记: ' + str(p))
            if '邮件' in text: raise RuntimeError('公开产物存在私有栏目字样')
            if any(value in text for value in private_text): raise RuntimeError('公开产物存在 private 内容: ' + str(p))


def _build(rows, hot, now, out, inbox_only=False):
    cfg = config(); private = private_mode()
    sources = {s['id']: s for s in cfg['sources'] if private or s['visibility'] == 'public'}
    by_channel = {s['channel']: s for s in sources.values() if s['type'] == 'telegram'}
    telegram = [from_telegram(r, by_channel[r['ch']], not private) for r in rows if r['ch'] in by_channel]
    hot = [from_telegram(r, by_channel[r['ch']], not private) for r in hot if r['ch'] in by_channel]
    if not private:
        for source in cfg['sources']:
            if source['visibility'] == 'private': shutil.rmtree(out / source['id'], ignore_errors=True)

    def image_path(path):
        return out / path if (out / path).is_file() else ROOT / path

    def is_photo(path):
        return photo_like(str(image_path(path)))

    # Inbox issues, newest first; images are recompressed into <id>/img/.
    issues = {}
    for s in sources.values():
        if s['type'] != 'inbox': continue
        loaded = load_issues(s, private)
        # Preserve adapter-owned media and other files; regenerate only pages.
        for page in (out / s['id']).glob('*.html'): page.unlink()
        if loaded:
            issues[s['id']] = [compress_images(d, base, out / s['id'] / 'img', s['id'] + '/img/') for d, base in loaded]
    latest = [item for sid, loaded in issues.items() for item in home_candidates(loaded[0], sources[sid])]

    # Navigation: core pages, favorites, Telegram channels with messages, enabled inbox columns.
    favorites = cfg.get('nav', {}).get('favorites', DEFAULT_FAVORITES)
    columns = [s for s in sorted(sources.values(), key=lambda s: s['nav'].get('order', 100))
               if s['id'] in issues and s['nav'].get('enabled')]
    entries = [('home', 'index.html', '首页', 'home'), ('news', 'hot.html', '资讯', 'hot'),
               ('all', 'all.html', '全部', 'all'), ('daily', 'archive/index.html', '日报', 'archive')]
    if favorites.get('enabled'):
        entries.append(('favorites', favorites['path'], favorites['label'], 'bookmark'))
    entries += [(s['id'], s['id'] + '/index.html', s['name'], s['icon']) for s in sources.values()
                if s['type'] == 'telegram' and any(item.source_id == s['id'] for item in telegram)]
    entries += [(s['id'], s['id'] + '/index.html', s['name'], s['icon']) for s in columns]

    site = Site(sources=sources, entries=entries, tabs=nav_tabs(cfg, private), favorites=favorites,
                private=private, now=now, categories=list(cfg['categories']) + ['综合'],
                assets=publish_assets(out, not inbox_only), is_photo=is_photo)

    def write(path, active, title, body, light_from=()):
        """Render one page. `light_from` lists candidate images; the first photo tints the background."""
        page = Page(site, '../' * path.count('/'), active)
        light = next((p for p in light_from if is_photo(p)), '')
        illumination = light_css(str(image_path(light)) if light else '')
        target = out / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(render.document(page, title, body(page), illumination, light))

    def group_light(paths):
        """Light of a group's first photo, or None to keep the page's light."""
        photo = next((p for p in paths if is_photo(p)), None)
        return ambient_uris(str(image_path(photo))) if photo else None

    def shown_images(items):
        return [p for item in items for p in item.images[:3]]

    def all_images(items):
        return [p for item in items for p in item.images]

    # Inbox column pages: <id>/<date>.html for every issue, <id>/index.html for the latest.
    for sid, loaded in issues.items():
        s = sources[sid]
        dates = [d['date'] for d in loaded]
        for n, issue in enumerate(loaded):
            count = sum(len(section['items']) for section in issue.get('sections', []))
            lead = (f'今天邮箱里 {count} 封值得看' if s.get('adapter') == 'mail'
                    else '看看今天世界发生了什么' if s.get('adapter') == 'world' else s['name'])
            note = issue['date'] + ' · ' + s['name'] + ' · ' + ('仅内网可见' if s['visibility'] == 'private' else '每日精选')
            if s.get('adapter') == 'x':
                count = sum(len(section['items']) for section in issue.get('sections', []) if section['title'] == '推特爆款')
                lead = f'今天推特上 {count} 条爆款'; note = issue['date'] + ' · 来自 X 公开帖'

            def body(page, issue=issue, lead=lead, note=note):
                content = render.heading(page, lead, note)
                content += render.date_chips(dates, issue['date'], today=site.today) if len(dates) > 1 else ''
                if s.get('adapter') == 'mail':
                    content += render.reading_switch()
                content += render.blocks(page, issue)
                for section in issue.get('sections', []):
                    parts = [part.strip() for part in re.split(r'[|｜]', section.get('title') or '')]
                    members = section_items(section, issue, s)
                    content += render.group(parts, ''.join(render.card(page, item, reading=True) for item in members),
                                            light=group_light(all_images(members)))
                return content
            light = all_images(issue_items(issue, s))
            write(f'{sid}/{issue["date"]}.html', sid, s['name'], body, light)
            if n == 0: write(f'{sid}/index.html', sid, s['name'], body, light)

    if not inbox_only:
        if favorites.get('enabled'):
            write(favorites['path'], 'favorites', favorites['label'], render.favorites_body)
        shutil.copytree(ROOT / 'media', out / 'media', dirs_exist_ok=True)
        for asset in (ROOT / 'assets').iterdir():
            if asset.is_file(): shutil.copyfile(asset, out / asset.name)

        # Home: one lead story, column shortcuts, then the mixed stream.
        ranked = rank_home(telegram + latest, sources, now)
        hero, stream = (ranked[0], ranked[1:]) if ranked else (None, [])
        today = now.date().isoformat()
        count = sum(item.day == today for item in telegram + latest)
        note = (f'{now.month}月{now.day}日 周{"一二三四五六日"[now.weekday()]} · 更新于 {now:%H:%M} · '
                f'{len({item.source_id for item in telegram + latest})} 个来源')
        leads = []
        for s in columns:
            issue = issues[s['id']][0]
            count_items = sum(len(section['items']) for section in issue.get('sections', []))
            one = next((x if isinstance(x, str) else x.get('title') or x.get('body')
                        for b in issue.get('blocks', []) if b.get('type') == 'oneliner' for x in b.get('items', []) if x), None)
            leads.append((s, one or f'{issue["date"]} · {count_items} 条'))

        def home(page):
            content = render.heading(page, f'今天 {count} 条要闻', note)
            if hero: content += render.section_label('此刻要闻', '精选') + render.card(page, hero, 'hero')
            content += render.column_row(page, leads)
            content += render.filters(page, stream + ([hero] if hero else []))
            content += render.section_label('最新动态', '实时收录 · 持续更新')
            return content + render.cards(page, stream)
        write('index.html', 'home', '首页', home, all_images([hero] if hero else []))

        everything = telegram + latest
        write('all.html', 'all', '全部', lambda page:
              render.heading(page, '全部动态', '完整收录，按来源和分类查找。')
              + render.filters(page, everything) + render.cards(page, everything), shown_images(everything))
        write('hot.html', 'news', '资讯', lambda page:
              render.heading(page, '这几条大家都在说', '过去 48 小时 · 多个来源共同关注')
              + render.ranked(page, hot),
              shown_images(hot))
        for s in sources.values():
            own = [item for item in telegram if item.source_id == s['id']]
            if s['type'] == 'telegram' and own:
                write(s['id'] + '/index.html', s['id'], s['name'], lambda page, s=s, own=own:
                      render.heading(page, '看看' + s['name'] + '的新消息', 'Telegram 频道资讯') + render.cards(page, own),
                      all_images(sorted(own, key=lambda item: item.ts, reverse=True)))

        # Daily digests: inbox sources by daily_order, then Telegram grouped by topic.
        days = sorted({item.day for item in telegram} | {d['date'] for loaded in issues.values() for d in loaded}, reverse=True)
        ordered = sorted(sources.values(), key=lambda s: (s.get('daily_order', 50 if s['type'] == 'telegram' else 45),
                                                          s.get('nav', {}).get('order', 100), s['id']))

        def digest_parts(day):
            """[(source or None, issue or None, items, topic groups)] in page order."""
            parts = []
            for s in ordered:
                if s['type'] != 'inbox': continue
                issue = next((d for d in issues.get(s['id'], []) if d['date'] == day), None)
                if issue: parts.append((s, issue, issue_items(issue, s)))
            tg = [item for s in ordered if s['type'] == 'telegram' for item in telegram
                  if item.source_id == s['id'] and item.day == day]
            return parts, [(topic, [item for item in tg if item.category == topic]) for topic in site.categories]

        def digest(page, day):
            parts, topics = digest_parts(day)
            content = ''
            for s, issue, items in parts:
                content += render.group([s['name']], render.blocks(page, issue) + render.cards(page, items),
                                        source_id=s['id'], cls='group digest-source',
                                        light=group_light(list(render.chart_images(issue)) + all_images(items)))
            if any(group for _, group in topics):
                inner = ''.join(render.group([topic], render.cards(page, group), level=3, cls='group group--sub',
                                             light=group_light(all_images(group)))
                                for topic, group in topics if group)
                content += render.group(['TG 资讯'], inner, cls='group digest-source')
            return content

        def digest_images(day):
            parts, topics = digest_parts(day)
            images = [p for _, issue, items in parts for p in list(render.chart_images(issue)) + shown_images(items)]
            return images + [p for _, group in topics for p in shown_images(group)]

        for day in days:
            write(f'archive/{day}.html', 'daily', day + ' 日报', lambda page, day=day:
                  render.heading(page, day + ' 日报', '按北京时间汇集各来源精选')
                  + render.date_chips(days, day, today=site.today) + digest(page, day), digest_images(day))
        write('archive/index.html', 'daily', '日报', lambda page:
              render.heading(page, '每一天，都有迹可循', '回看世界变化的每个切片。')
              + (render.date_chips(days, days[0], ' 日报', today=site.today) + digest(page, days[0]) if days else ''),
              digest_images(days[0]) if days else [])
        (out / '.nojekyll').write_text('')

    if not private:
        verify_public(out, cfg)
    print(f'built {len(telegram)} TG, {len(issues)} inbox sources -> {out}')


if __name__ == '__main__':
    build([], [], datetime.now(BEIJING), inbox_only=True)
