"""One shape for every piece of content, whether it came from Telegram or an inbox feed.

Pages and templates only read `Item` fields, so a new source never needs template changes.
"""
import re
from dataclasses import dataclass, field
from datetime import datetime
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

BEIJING = ZoneInfo('Asia/Shanghai')


def safe_link(url):
    """Only http(s) links are ever rendered."""
    url = str(url or '')
    return url if urlsplit(url).scheme in ('http', 'https') else ''


def parse_moment(ts, day):
    """Aware datetime for ranking: the item's own timestamp, else midnight of its issue day."""
    for value in (str(ts or '').replace('Z', '+00:00'), str(day or '')):
        try:
            moment = datetime.fromisoformat(value)
        except ValueError:
            continue
        return moment if moment.tzinfo else moment.replace(tzinfo=BEIJING)
    return None


@dataclass
class Item:
    source_id: str          # registered source (sources.json id)
    filter_key: str         # value matched by the 来源 select: Telegram channel or inbox id
    category: str           # value matched by the category tabs (TG topic, or the inbox name)
    title: str
    body: str
    day: str                # YYYY-MM-DD the item belongs to
    ts: str                 # raw timestamp string; part of the bookmark identity
    url: str = ''           # external original (http/https only)
    page: str = ''          # internal page this card stands for, site-root-relative
    topic: str = ''         # category label shown on the card; empty when it adds nothing
    via: list = field(default_factory=list)   # sub-sources shown after the source name
    images: list = field(default_factory=list)  # site-root-relative paths
    native_id: object = None  # Telegram message id; part of the bookmark identity

    @property
    def moment(self):
        return parse_moment(self.ts, self.day)

    @property
    def has_clock(self):
        """Date-only items have no meaningful time of day to show."""
        return len(self.ts) > 10 and parse_moment(self.ts, None) is not None


def from_telegram(row, source, public):
    """A pipeline.py row: dict(ch, id, ts, title, body, cat, day, url, images)."""
    title, body = row['title'], row['body']
    if public:
        # Public copy says 电邮 so the private column's name never appears in public pages.
        title, body = (text.replace('电子邮件', '电邮').replace('邮件', '电邮') for text in (title, body))
    return Item(source_id=source['id'], filter_key=row['ch'], category=row['cat'], title=title, body=body,
                topic='' if row['cat'] == '综合' else row['cat'],
                day=row['day'], ts=row['ts'], url=safe_link(row.get('url')), images=list(row.get('images', [])),
                native_id=row.get('id'))


def _via(entry, source):
    name = entry.get('source') or ' / '.join(str(x) for x in entry.get('sources', []) or [])
    if not name or name == source['name']:
        return []
    return [part.strip() for part in re.split(r'[|｜]', name) if part.strip()]


def section_items(section, issue, source):
    """Cards for one inbox section."""
    return [Item(source_id=source['id'], filter_key=source['id'], category=source['name'],
                 title=entry.get('title') or '未命名条目', body=entry.get('body') or '',
                 day=issue['date'], ts=entry.get('date') or issue['date'], url=safe_link(entry.get('link')),
                 via=_via(entry, source),
                 images=[im['file'] for im in entry.get('images', []) or [] if isinstance(im, dict) and im.get('file')])
            for entry in section.get('items', [])]


def issue_items(issue, source):
    """Every section card of an inbox issue, in order."""
    return [item for section in issue.get('sections', []) for item in section_items(section, issue, source)]


def home_candidates(issue, source):
    """Section cards, or for block-only issues, cards built from the summary blocks."""
    items = issue_items(issue, source)
    if items:
        return items
    simple = dict(source_id=source['id'], filter_key=source['id'], category=source['name'], day=issue['date'], ts=issue['date'])
    for block in issue.get('blocks', []):
        if block.get('type') not in ('oneliner', 'tomorrow'):
            continue
        for entry in block.get('items', []):
            title = entry if isinstance(entry, str) else entry.get('title') or entry.get('body')
            if title:
                items.append(Item(title=title, body='' if isinstance(entry, str) else entry.get('body', ''), **simple))
    if not items and issue.get('blocks'):
        names = {'markets': '市场看板', 'chart': '一张图'}
        body = ' · '.join(b.get('title') or names.get(b.get('type'), '') for b in issue['blocks'])
        items.append(Item(title=issue.get('title') or source['name'], body=body,
                          page=f'{source["id"]}/{issue["date"]}.html', **simple))
    return items
