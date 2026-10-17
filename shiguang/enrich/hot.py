"""The live ranking: Telegram stories of the last 48 hours that several channels are covering."""
import re
from datetime import datetime, timedelta

KW = ['美联储','降息','关税','停火','战争','GDP','财报','AI','苹果','英伟达','OpenAI','特朗普','央行','芯片']
SIZE = 10


def grams(t):
    t = re.sub(r'\W', '', t.lower())[:180]
    return {t[i:i+3] for i in range(len(t)-2)}


def hot_list(rows, now):
    """Score = channels covering the story × 4 + keyword hits + length bonus; near-duplicates collapse."""
    recent = [r for r in rows if datetime.fromisoformat(r['ts']) >= now-timedelta(hours=48) and not re.search(r'早餐|新闻汇总|要闻汇总|日报|收评', r['title'])]
    G = [grams(r['text']) for r in recent]
    for i, r in enumerate(recent):
        sources = {r['ch']} | {recent[j]['ch'] for j in range(len(recent)) if len(G[i] & G[j]) >= 8}
        r['sources'] = len(sources)
        r['score'] = len(sources)*4 + sum(k.lower() in r['text'].lower() for k in KW) + min(len(r['text'])/240, 2)
    hot = []
    for r in sorted(recent, key=lambda r: r['score'], reverse=True):
        if any(len(grams(r['title']) & grams(x['title'])) >= 6 for x in hot): continue
        hot.append(r)
        if len(hot) == SIZE: break
    return hot
