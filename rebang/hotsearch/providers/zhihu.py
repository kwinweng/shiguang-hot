"""知乎热榜：api.zhihu.com/topstory/hot-lists/total。链接改写为 www.zhihu.com/question/<id>。"""
import re
from urllib.parse import urlsplit

from rebang.contract import load_hotsearch

from rebang.hotsearch.http import ProviderError, TIMEOUT

REFERER = 'https://www.zhihu.com/'
API_QUESTION = re.compile(r'^https?://api\.zhihu\.com/questions/(\d+)/?$', re.I)


def fetch(http, now):
    spec, cap = _spec()
    response = http.get(spec['endpoint'], timeout=TIMEOUT, headers={'Referer': REFERER})
    if response.status != 200:
        raise ProviderError(f'http_{response.status}')
    return parse(response.json(), cap=cap)


def parse(payload, cap=50):
    if not isinstance(payload, dict) or not isinstance(payload.get('data'), list):
        raise ProviderError('bad_structure')
    rows = payload['data']
    items = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        item = _entry(row)
        if item is None:
            continue
        items.append(item)
    if rows and not items:
        raise ProviderError('bad_structure')
    for index, item in enumerate(items[:cap], start=1):
        item['rank'] = index
    return items[:cap]


def _spec():
    config = load_hotsearch()
    spec = next(item for item in config['providers'] if item['id'] == 'zhihu')
    return spec, config['max_items_per_provider']


def _entry(row):
    target = row.get('target') or {}
    if not isinstance(target, dict):
        return None
    title = (target.get('title') or '').strip()
    url = _question_url(target)
    if not title or not url:
        return None
    item = {'title': title, 'url': url, 'pinned': False}
    label = (row.get('detail_text') or '').strip()
    if label:
        item['hot_label'] = label
    summary = (target.get('excerpt') or '').strip()
    if summary:
        item['summary'] = summary
    image = _thumbnail(row.get('children'))
    if image:
        item['image'] = image
    return item


def _question_url(target):
    typ = target.get('type')
    ident = target.get('id')
    if typ == 'question' and ident is not None and str(ident).isdigit():
        return f'https://www.zhihu.com/question/{ident}'
    raw = target.get('url') or ''
    matched = API_QUESTION.match(raw.strip())
    if matched:
        return f'https://www.zhihu.com/question/{matched.group(1)}'
    if isinstance(raw, str) and _is_url(raw) and 'zhihu.com' in urlsplit(raw).netloc:
        # 非问题类型不编造路径，只有已经是 www 网页才保留
        host = urlsplit(raw).netloc
        if host == 'www.zhihu.com' or host.endswith('.zhihu.com') and not host.startswith('api.'):
            return raw
    return None


def _thumbnail(children):
    if not isinstance(children, list):
        return None
    for child in children:
        if not isinstance(child, dict):
            continue
        url = child.get('thumbnail')
        if _is_url(url):
            return url
    return None


def _is_url(value):
    if not isinstance(value, str):
        return False
    parts = urlsplit(value)
    return parts.scheme in ('http', 'https') and bool(parts.netloc)
