"""Public trial catalogue, derived from the existing table without writing collector state."""
import logging
from contextlib import closing
import re
import sqlite3
import unicodedata
from datetime import date, datetime, timedelta
from difflib import SequenceMatcher
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit, unquote

from shiguang.config import ROOT
from shiguang.ingest.trial import load
from shiguang.model import BEIJING
from shiguang.site.render import E, EXTERNAL
from shiguang.site.icons import phosphor

CATEGORIES = {
    'apps': ('app', 'app-window', '应用'),
    'shows': ('show', 'television-simple', '剧集'),
    'games': ('game', 'game-controller', '游戏'),
    'exhibitions': ('expo', 'ticket', '展览演出'),
    'stargazing': ('star', 'moon-stars', '观星'),
    'apple': ('apple', 'apple-logo', '苹果'),
    '3d-printing': ('print', 'cube', '3D 打印'),
}
PATHS = {'好玩': 'play.html', '好买': 'buy.html'}


def canonical(url):
    parts = urlsplit(url)
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path.rstrip('/'),
                      urlencode([(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True)
                                 if not k.lower().startswith('utm_')]), ''))


def normalized(title):
    return ''.join(c for c in unicodedata.normalize('NFKC', title).lower() if c.isalnum())


def moment(value):
    parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    return parsed.replace(tzinfo=BEIJING) if parsed.tzinfo is None else parsed.astimezone(BEIJING)


def event_dates(text, now):
    """Full dates and common Chinese/month-day ranges; end dates are inclusive in Beijing."""
    pattern = r'(?:(\d{4})\s*[年./-]\s*)?(\d{1,2})\s*[月./-]\s*(\d{1,2})日?'
    matches = list(re.finditer(pattern, text))
    for index, match in enumerate(matches):
        try:
            year = int(match[1] or now.year)
            start = date(year, int(match[2]), int(match[3]))
            end = start
            if index + 1 < len(matches):
                following = matches[index + 1]
                between = text[match.end():following.start()].strip()
                if re.fullmatch(r'[-–—~～至到]+', between):
                    end_year = int(following[1] or year)
                    if not following[1] and (int(following[2]), int(following[3])) < (start.month, start.day):
                        end_year += 1
                    end = date(end_year, int(following[2]), int(following[3]))
            if end >= start:
                return start, end
        except ValueError:
            continue
    return None


def app_title(title, summary, url):
    if not re.match(r'^标签\s*[:：]', title):
        return title, []
    tags = [x.strip() for x in re.split(r'[、,，]', re.split(r'[:：]', title, maxsplit=1)[1]) if x.strip()][:3]
    for line in summary.splitlines():
        line = line.strip()
        if not line or re.match(r'^(标签|备注|推荐|链接|群组)\s*[:：]', line):
            continue
        line = re.sub(r'^(?:App 名|应用名称|名称)\s*[:：]\s*', '', line)
        if re.fullmatch(r'(?:应用下载|下载链接|App Store|立即下载)(?:\s*[（(].*[）)])?', line, re.I):
            continue
        if not re.match(r'https?://|@', line):
            return line[:200], tags
    match = re.search(r'https?://apps\.apple\.com/[^\s]*/app/([^/\s?]+)', summary + ' ' + url)
    if match and not re.fullmatch(r'id\d+', match[1]):
        return unquote(match[1]).replace('-', ' ')[:200], tags
    logging.getLogger(__name__).info('apps_share_untitled')
    return '', tags


def steam_title(title):
    if re.search(r'新品|促销|发售|折扣|特惠|\bsale\b|discount|now available|pre[- ]?order|free weekend|%\s*off|new\s+(?:game|arrival|release)', title, re.I):
        return True
    return bool(re.search(r'\b(?:release[ds]?|launch(?:ed)?)\b', title, re.I) and
                not re.search(r'\b(?:update|patch|maintenance)\b', title, re.I))


def prepare(rows, now, cfg=None):
    cfg = cfg or load()
    sources = {s['id']: s for s in cfg['sources']}
    items = []
    for row in rows:
        item = dict(row)
        source = sources.get(item['source_id'])
        if not source or (item['section'], item['category']) != (source['section'], source['category']):
            continue
        if urlsplit(item['url']).scheme not in ('http', 'https'):
            continue
        item['title'], item['tags'] = (app_title(item['title'], item['summary'], item['url'])
                                        if source['id'] == 'Apps_Share' else (item['title'], []))
        if not item['title']:
            continue
        text = item['title'] + ' ' + item['summary']
        if source['id'] == 'Apps_Share' and re.match(r'^#?(?:互推|广告|频道推荐)', item['title']):
            continue
        if source['id'] == 'steam' and not item['image_url'] and not steam_title(item['title']):
            continue
        if source['id'] == 'appinn' and re.search(r'VPS|优惠|折扣|惠抢|赠送|充值|折起|主机|云服务器|CloudCone', text, re.I):
            continue
        if source['id'] == 'douban-events' and re.search(r'上海|广州|深圳|成都|杭州|天津', text) and '北京' not in text:
            continue
        try:
            item['first_seen'] = moment(item['fetched_at'])
            item['sort_time'] = moment(item['published_at']) if item['published_at'] else item['first_seen']
        except (ValueError, TypeError):
            continue
        if item['sort_time'] > now:
            continue
        item['date_label'] = ''
        if item['category'] == 'exhibitions':
            dates = event_dates(text, now)
            if dates:
                start, end = dates
                if end < now.astimezone(BEIJING).date():
                    continue
                item['date_label'] = f'展期 {start.month}/{start.day}–{end.month}/{end.day}'
            elif now - item['first_seen'] >= timedelta(days=14):
                continue
        item['name'] = source['name']
        item['image_url'] = item['image_url'] if urlsplit(item['image_url'] or '').scheme in ('http', 'https') else ''
        items.append(item)
    # Rank complete records first, then earlier first-seen, so duplicates keep the best representation.
    items.sort(key=lambda i: (bool(i['image_url']), sum(bool(i.get(k)) for k in ('summary', 'published_at')),
                              -i['first_seen'].timestamp()), reverse=True)
    kept = []
    for item in items:
        title = normalized(item['title'])
        if any(item['section'] == old['section'] and (
                canonical(item['url']) == canonical(old['url']) or
                (item['category'] == old['category'] and (
                    title == normalized(old['title']) or
                    (abs((item['sort_time'] - old['sort_time']).total_seconds()) <= 48 * 3600 and
                     SequenceMatcher(None, title, normalized(old['title'])).ratio() >= .9)))) for old in kept):
            continue
        kept.append(item)
    return sorted(kept, key=lambda i: (i['sort_time'], i['url']), reverse=True)


def catalogue(now, path=None):
    path = path or ROOT / 'tg.db'
    if not path.is_file():
        return []
    with closing(sqlite3.connect(f'{path.resolve().as_uri()}?mode=ro', uri=True)) as db:
        if not db.execute("select 1 from sqlite_master where type='table' and name='trial_item'").fetchone():
            return []
        db.row_factory = sqlite3.Row
        return prepare(db.execute('select * from trial_item'), now)


def card(item, now, summary=False):
    key, glyph, label = CATEGORIES.get(item['category'], ('', 'newspaper', '其他'))
    style = f' style="--tc-bg:var(--tc-{key}-bg);--tc-icon:var(--tc-{key}-icon)"' if key else ''
    fallback = (f'<div class="trial-textcard"{style}>'
                f'<span>{E(item["section"])} · {E(label)}</span>{phosphor(glyph)}</div>')
    media = fallback
    if item['image_url']:
        media += f'<img src="{E(item["image_url"])}" alt="" loading="lazy" decoding="async">'
    date_label = item['date_label']
    if not date_label:
        if not item['published_at']:
            date_label = '最近收录'
        else:
            hours = max(0, int((now - item['sort_time']).total_seconds() // 3600))
            date_label = '刚刚' if hours == 0 else f'{hours} 小时前' if hours < 24 else f'{hours // 24} 天前'
    return (f'<article class="trial-card" data-trial-category="{E(item["category"])}">'
            f'<a href="{E(item["url"])}" {EXTERNAL}><div class="trial-media">{media}</div>'
            f'<h3>{E(item["title"])}</h3></a><p class="trial-meta">{E(item["name"])} · {E(date_label)}</p>'
            + ''.join(f'<span class="trial-tag">{E(t)}</span>' for t in item['tags'])
            + (f'<p class="trial-summary">{E(item["summary"][:140])}</p>' if summary else '') + '</article>')


def grid(items, now, summary=False):
    return '<div class="trial-grid">' + ''.join(card(i, now, summary) for i in items) + '</div>'


def home(items, page):
    content = ''
    for section, path in PATHS.items():
        recent = [i for i in items if i['section'] == section and
                  page.site.now - timedelta(days=7) <= i['sort_time'] <= page.site.now][:5]
        if recent:
            content += (f'<section class="trial-home"><h2>{section}</h2>' + grid(recent, page.site.now, True)
                        + f'<a class="trial-more" href="{E(page.url(path))}">更多{section}</a></section>')
    return content


def body(items, section, page):
    members = [i for i in items if i['section'] == section]
    categories = [c for c in load()['categories'] if c['section'] == section and
                  any(i['category'] == c['id'] for i in members)]
    filters = f'<button type="button" data-trial-filter="all" aria-label="全部{section}" aria-pressed="true">{phosphor("squares-four")}</button>'
    for category in categories:
        filters += (f'<button type="button" data-trial-filter="{category["id"]}" aria-label="{E(category["name"])}" '
                    f'aria-pressed="false">{phosphor(CATEGORIES.get(category["id"], ("", "newspaper", "其他"))[1])}</button>')
    return (f'<div class="trial-page"><h1>{section}</h1><nav class="trial-filters" aria-label="分类筛选">{filters}</nav>'
            + grid(members, page.site.now) + '</div>')
