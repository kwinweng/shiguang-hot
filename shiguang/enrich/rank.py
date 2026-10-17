"""Home ordering: freshness-weighted ranking, then round-robin across sources."""
from shiguang.model import BEIJING


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
