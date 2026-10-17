"""热点: Telegram stories of the last few days, in time order, that clear a heat threshold.

Heat = channels that reported the story × 4 + keyword hits (sources.json hot.keywords) + a length
bonus of up to 2. A story reported by two channels always qualifies; a single report needs keywords
or substance. Each story appears once, at its first report.
"""
import re
from datetime import datetime, timedelta

DIGEST = re.compile(r'早餐|新闻汇总|要闻汇总|日报|收评|数据汇总')
WINDOW = timedelta(hours=12)   # reports further apart than this are separate stories


def grams(t):
    t = re.sub(r'\W', '', t.lower())[:180]
    return {t[i:i+3] for i in range(len(t)-2)}


def heat(row, keywords):
    text = row['text'].lower()
    return row['sources'] * 4 + sum(k.lower() in text for k in keywords) + min(len(row['text']) / 240, 2)


def hot_stream(rows, now, keywords=(), days=30, threshold=6):
    """Newest first. Each returned row carries `sources` (channels that reported it) and `heat`."""
    floor = now - timedelta(days=days)
    recent = sorted((r for r in rows if datetime.fromisoformat(r['ts']) >= floor and not DIGEST.search(r['title'])),
                    key=lambda r: r['ts'])
    G = [grams(r['text']) for r in recent]
    T = [grams(r['title']) for r in recent]
    when = [datetime.fromisoformat(r['ts']) for r in recent]
    kept, channels = [], []
    for i, r in enumerate(recent):
        story = None
        for k in range(len(kept) - 1, -1, -1):   # newest stories first; older than the window cannot match
            j = kept[k]
            if when[i] - when[j] > WINDOW: break
            if len(G[i] & G[j]) >= 8 or len(T[i] & T[j]) >= 6:
                story = k; break
        if story is None:
            kept.append(i); channels.append({r['ch']})
        else:
            channels[story].add(r['ch'])
    stories = []
    for j, reported in zip(kept, channels):
        story = dict(recent[j], sources=len(reported))
        story['heat'] = heat(story, keywords)
        if story['heat'] >= threshold:
            stories.append(story)
    return sorted(stories, key=lambda r: r['ts'], reverse=True)
