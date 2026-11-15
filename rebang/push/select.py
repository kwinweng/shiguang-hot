"""从已上站条目中筛 24 小时窗口，并按 highlight + 频道轮转挑 3–5 条。"""
from .timeutil import BEIJING, WINDOW, in_window, parse_iso, parse_now
from rebang.contract import channel_slugs, load_channels

MIN_ITEMS = 3
MAX_ITEMS = 5
EXCLUDED_VISIBILITY = frozenset({'private', 'blocked', 'held', 'rejected'})
EXCLUDED_CLIP_STATUS = frozenset({'blocked', 'rejected', 'held', 'dropped'})


def excluded_source_ids():
    return set(load_channels().get('excluded_sources') or ())


def _looks_like_mail(source_id):
    text = (source_id or '').lower()
    return text == 'mail' or text.startswith('mail-') or 'mail-digest' in text or text.endswith('-mail')


def is_excluded(item):
    """排除邮件、被挡下的剪藏、非资讯，以及契约里点名剔除的来源。"""
    if not isinstance(item, dict):
        return True
    if item.get('kind') != 'news':
        return True
    source_id = item.get('source_id') or ''
    if source_id in excluded_source_ids() or _looks_like_mail(source_id):
        return True
    if item.get('visibility') in EXCLUDED_VISIBILITY:
        return True
    if item.get('blocked') is True or item.get('held') is True:
        return True
    if item.get('clip_blocked') is True or item.get('clip_status') in EXCLUDED_CLIP_STATUS:
        return True
    return False


def window_items(items, now, window=WINDOW):
    kept = []
    for item in items:
        if is_excluded(item):
            continue
        published = parse_iso(item.get('published_at'))
        if published is None:
            continue
        if in_window(published, now, window):
            kept.append(item)
    return kept


def _newer_key(item):
    published = parse_iso(item.get('published_at'))
    stamp = published.timestamp() if published else 0
    return (stamp, item.get('id') or '')


def rotate_pick(items, limit, slugs=None, later_slugs=None):
    """按频道官方顺序一轮一轮取，每轮取该频道剩余里最新的一条。

    later_slugs 里的频道靠后，用来补足时优先覆盖还没出现过的频道。
    """
    if limit <= 0 or not items:
        return []
    slugs = slugs or channel_slugs()
    later = set(later_slugs or ())
    order = [slug for slug in slugs if slug not in later] + [slug for slug in slugs if slug in later]
    buckets = {slug: [] for slug in slugs}
    leftover = []
    for item in sorted(items, key=_newer_key, reverse=True):
        slug = item.get('channel')
        if slug in buckets:
            buckets[slug].append(item)
        else:
            leftover.append(item)
    picked = []
    while len(picked) < limit:
        progressed = False
        for slug in order:
            if buckets[slug] and len(picked) < limit:
                picked.append(buckets[slug].pop(0))
                progressed = True
        if not progressed:
            break
    for item in leftover:
        if len(picked) >= limit:
            break
        picked.append(item)
    return picked


def pick_highlights(items, now=None, limit=MAX_ITEMS):
    """优先 highlight=true，再按频道轮转补足到最多 5 条；不足 3 条有几条出几条。"""
    now = now or parse_now(None)
    candidates = window_items(items, now)
    highlights = [item for item in candidates if item.get('highlight') is True]
    others = [item for item in candidates if item.get('highlight') is not True]
    selected = rotate_pick(highlights, limit)
    if len(selected) < limit:
        used = {item.get('channel') for item in selected}
        selected.extend(rotate_pick(others, limit - len(selected), later_slugs=used))
    return selected
