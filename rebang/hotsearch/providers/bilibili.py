"""B 站热搜：wbi/search/square。不破解 wbi；强制签名时该家失败并空着。链接为站内搜索页。"""
from urllib.parse import quote, urlsplit

from rebang.contract import load_hotsearch

from rebang.hotsearch.http import ProviderError, TIMEOUT

REFERER = 'https://www.bilibili.com/'
SEARCH = 'https://search.bilibili.com/all?keyword='


def fetch(http, now):
    spec, cap = _spec()
    response = http.get(spec['endpoint'], timeout=TIMEOUT, headers={'Referer': REFERER})
    if response.status != 200:
        raise ProviderError(f'http_{response.status}')
    return parse(response.json(), cap=cap)


def parse(payload, cap=50):
    if not isinstance(payload, dict):
        raise ProviderError('bad_structure')
    code = payload.get('code')
    if code != 0:
        raise ProviderError(f'code_{code}' if code is not None else 'code_missing')
    data = payload.get('data')
    if not isinstance(data, dict):
        raise ProviderError('bad_structure')
    trending = data.get('trending')
    if not isinstance(trending, dict) or not isinstance(trending.get('list'), list):
        raise ProviderError('bad_structure')
    pinned = _entries(trending.get('top_list') or [], pinned=True)
    regular = _entries(trending['list'], pinned=False)
    seen = {item['title'] for item in pinned}
    items = pinned + [item for item in regular if item['title'] not in seen]
    if trending['list'] and not items and not pinned:
        raise ProviderError('bad_structure')
    for index, item in enumerate(items[:cap], start=1):
        item['rank'] = index
    return items[:cap]


def _spec():
    config = load_hotsearch()
    spec = next(item for item in config['providers'] if item['id'] == 'bilibili')
    return spec, config['max_items_per_provider']


def _entries(rows, pinned):
    items = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        keyword = (row.get('keyword') or row.get('show_name') or '').strip()
        title = (row.get('show_name') or keyword).strip()
        if not title or not keyword:
            continue
        url = _search_url(row, keyword)
        if not url:
            continue
        item = {'title': title, 'url': url, 'pinned': bool(pinned)}
        score = row.get('heat_score')
        if isinstance(score, int) and score >= 0:
            item['hot_score'] = score
        elif isinstance(score, str) and score.isdigit():
            item['hot_score'] = int(score)
        items.append(item)
    return items


def _search_url(row, keyword):
    raw = row.get('uri') or ''
    if isinstance(raw, str) and raw.strip():
        parts = urlsplit(raw)
        if parts.scheme in ('http', 'https') and parts.netloc:
            return raw
    return SEARCH + quote(keyword, safe='')
