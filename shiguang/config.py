"""sources.json, the build mode and where each source's files live.

config() returns the file checked and filled with defaults, so the rest of the code reads one
shape. Field names from before the restructure (categories, daily_order, nav.order, home_weight,
home_cap) are still understood, so an older override file keeps working.
"""
import json, math, os, re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent   # repository root
WEB = ROOT / 'web'                               # style.css, app.js, assets/
RESERVED = ('archive', 'media', 'assets', 'img', 'index', 'hot', 'all', 'columns', 'favorites', 'tag')
TYPES = ('telegram', 'inbox', 'feed')
# 栏目「按渠道」: platform key -> label, in display order. A source names its platform; the default
# follows its type (telegram -> telegram, feed -> rss, inbox -> brief).
PLATFORMS = {'brief': '每日简报', 'x': 'X（推特）', 'youtube': 'YouTube', 'rss': 'RSS 订阅',
             'newsletter': '电邮订阅', 'github': 'GitHub', 'telegram': 'Telegram', 'mail': '邮件'}


def private_mode():
    return os.getenv('SITE_MODE') == 'private' or os.getenv('MAIL_DIGEST') == '1'


def _number(value, name, minimum=None):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or (minimum is not None and value < minimum):
        raise ValueError(f'{name} 必须为有效数值' + ('，且不得为负' if minimum is not None else ''))
    return value


def prepare(data):
    """Check a parsed sources.json and fill in every default.

    `topics` is a list of {name, slug, pattern} in display order (the first pattern that matches
    wins); the older form {name: pattern} still works and gets slugs t1, t2…
    """
    raw_topics = data.get('topics', data.get('categories', {}))
    if isinstance(raw_topics, dict):
        raw_topics = [dict(name=name, slug=f't{n}', pattern=pattern) for n, (name, pattern) in enumerate(raw_topics.items(), 1)]
    topics, slugs = {}, {}
    for t in raw_topics:
        re.compile(t['pattern'])
        if not re.fullmatch(r'[a-z0-9-]+', t['slug']) or t['slug'] in slugs.values() or t['name'] in topics:
            raise ValueError('话题 slug 非法或重复')
        topics[t['name']] = t['pattern']; slugs[t['name']] = t['slug']
    hot = dict(data.get('hot', {}))
    hot.setdefault('keywords', [])
    hot.setdefault('source', None)
    sources, ids = [], set()
    for raw in data['sources']:
        s = dict(raw)
        if not re.fullmatch(r'[a-zA-Z0-9_-]+', s['id']) or s['id'] in ids or s['id'] in RESERVED:
            raise ValueError('来源 id 非法或重复')
        ids.add(s['id'])
        if s['visibility'] not in ('public', 'private') or s['type'] not in TYPES:
            raise ValueError('来源类型或 visibility 非法')
        if s['type'] == 'feed' and not re.match(r'https?://', s.get('url', '')):
            raise ValueError('feed 来源需要 http(s) url')
        s.setdefault('platform', {'telegram': 'telegram', 'feed': 'rss'}.get(s['type'], 'brief'))
        if s['platform'] not in PLATFORMS:
            raise ValueError('未知 platform: ' + s['platform'])
        if s['type'] == 'inbox' and s.get('adapter', 'native') not in ('native', 'mail', 'world', 'x'):
            raise ValueError('未知 adapter')
        stream = s['type'] != 'inbox'
        s['order'] = _number(s.get('order', s.get('daily_order', 50 if stream else 45)), 'order')
        home = dict(s.get('home', {}))
        home.setdefault('weight', s.get('home_weight', 1))
        home.setdefault('cap', s.get('home_cap', 4 if stream else 8))
        _number(home['weight'], 'home.weight', 0)
        if isinstance(home['cap'], bool) or not isinstance(home['cap'], int) or home['cap'] < 0:
            raise ValueError('home.cap 必须为非负整数')
        s['home'] = home
        s.setdefault('icon', 'all')
        for old in ('daily_order', 'home_weight', 'home_cap', 'nav', 'color'):
            s.pop(old, None)
        sources.append(s)
    if hot['source'] and hot['source'] not in ids:
        raise ValueError('hot.source 必须是已注册的来源')
    return dict(topics=topics, topic_slugs=slugs, hot=hot, sources=sources)


def config():
    return prepare(json.loads(Path(os.getenv('SOURCES_OVERRIDE', ROOT / 'sources.json')).read_text()))


def directory(source):
    return Path(os.getenv(source.get('env', source['id'].upper() + '_FEED_DIR'), source.get('directory', '/workspace/feeds-inbox/' + source['id'])))
