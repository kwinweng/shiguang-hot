"""百度热搜：top.baidu.com/api/board?tab=realtime（官方公开 JSON）。"""
from urllib.parse import urlsplit

from rebang.contract import load_hotsearch

from rebang.hotsearch.http import ProviderError, TIMEOUT

REFERER = 'https://top.baidu.com/board?tab=realtime'


def fetch(http, now):
    spec, cap = _spec()
    response = http.get(spec['endpoint'], timeout=TIMEOUT, headers={'Referer': REFERER})
    if response.status != 200:
        raise ProviderError(f'http_{response.status}')
    return parse(response.json(), cap=cap)


def parse(payload, cap=50):
    if not isinstance(payload, dict):
        raise ProviderError('bad_structure')
    if payload.get('success') is not True:
        raise ProviderError('success_false')
    data = payload.get('data')
    if not isinstance(data, dict) or not isinstance(data.get('cards'), list):
        raise ProviderError('bad_structure')
    card = _hot_card(data['cards'])
    if card is None:
        raise ProviderError('bad_structure')
    pinned = _entries(card.get('topContent') or [], pinned=True)
    regular = _entries(card.get('content') or [], pinned=False)
    seen = {item['title'] for item in pinned}
    items = pinned + [item for item in regular if item['title'] not in seen]
    for index, item in enumerate(items[:cap], start=1):
        item['rank'] = index
    return items[:cap]


def _spec():
    config = load_hotsearch()
    spec = next(item for item in config['providers'] if item['id'] == 'baidu')
    return spec, config['max_items_per_provider']


def _hot_card(cards):
    for card in cards:
        if not isinstance(card, dict):
            continue
        if card.get('component') == 'hotList' or card.get('typeName') == 'realtime':
            return card
    return None


def _entries(rows, pinned):
    items = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        title = (row.get('word') or row.get('query') or '').strip()
        url = _url(row.get('url') or row.get('rawUrl') or row.get('appUrl'))
        if not title or not url:
            continue
        item = {'title': title, 'url': url, 'pinned': bool(pinned)}
        score = _score(row.get('hotScore'))
        if score is not None:
            item['hot_score'] = score
        summary = (row.get('desc') or '').strip()
        if summary:
            item['summary'] = summary
        image = _url(row.get('img'))
        if image:
            item['image'] = image
        items.append(item)
    return items


def _score(value):
    if isinstance(value, int) and value >= 0:
        return value
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return None


def _url(value):
    if not isinstance(value, str):
        return None
    parts = urlsplit(value)
    if parts.scheme in ('http', 'https') and parts.netloc:
        return value
    return None
