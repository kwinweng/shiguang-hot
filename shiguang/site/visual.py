"""v0.3 presentation data. Uses only the already privacy-filtered publication pool."""
import hashlib
import json
import re
from collections import Counter
from datetime import timedelta
from shiguang.site.history import uid


def write(out, content):
    # Mini charts show observed source mentions over 72 hours, never fabricated market movement.
    start = content.now - timedelta(hours=71)
    mentions = {}
    for item in content.stream:
        if item.moment and start <= item.moment <= content.now:
            title = re.sub(r'\W', '', item.title).casefold()
            hour = min(71, max(0, int((item.moment - start).total_seconds() // 3600)))
            mentions.setdefault(title, Counter())[hour] += 1

    def record(item):
        source = content.sources.get(item.source_id, {})
        samples = mentions.get(re.sub(r'\W', '', item.title).casefold(), {})
        peak = max(samples.values(), default=1)
        spark = ' '.join(f'{i * 70 / 71:.1f},{22 - samples.get(i, 0) * 20 / peak:.1f}' for i in range(72))
        stars = re.search(r'(?:★|[Ss]tars?[:：]?|星标[:：]?)\s*([\d,.]+[kKmM]?)', item.body or '')
        language = re.search(r'(?:语言|[Ll]anguage)[:：]\s*([^\n·|]+)', item.body or '')
        return dict(id=uid(item),
                    title=item.title, summary=item.body or '', source=source.get('name', item.source_id),
                    source_id=item.source_id, category=item.category, time=item.ts, day=item.day,
                    image=item.images[0] if item.images else '', url=item.url, kind='news',
                    stars=stars[1] if stars else None, language=language[1].strip() if language else '',
                    spark=spark, change=samples.get(71, 0)-samples.get(70, 0),
                    heat=content.heat.get((item.source_id, item.native_id), (0, 0))[0] or sum(samples.values()))
    news = [record(i) for i in sorted(content.stream, key=lambda i: i.ts, reverse=True)]
    magazines = []
    for sid, issues in content.issues.items():
        for issue in issues:
            cards = content.issue_cards(sid, issue)
            news.extend(record(i) for i in cards)
            if cards:
                cover = next((i.images[0] for i in cards if i.images), '')
                magazines.append(dict(record(cards[0]), id=f'issue-{sid}-{issue["date"]}', kind='mag',
                                      title=issue.get('title') or content.sources[sid]['name'] + ' · ' + issue['date'],
                                      image=cover, summary=cards[0].body,
                                      url=f'{sid}/{issue["date"]}.html'))
    news = sorted({item['id']: item for item in news}.values(), key=lambda item: (item['day'], item['time']), reverse=True)
    trials = []
    for item in content.trials:
        trials.append(dict(id='trial-' + hashlib.sha256(item['url'].encode()).hexdigest(),
                           title=item['title'], summary=item['summary'], source=item['name'],
                           source_id=item['source_id'], category=item['category'],
                           time=item['sort_time'].isoformat(), day=item['sort_time'].date().isoformat(),
                           image=item['image_url'], url=item['url'],
                           kind='play' if item['section'] == '好玩' else 'buy', tags=item['tags'],
                           date_label=item['date_label']))
    sources = [dict(id=sid, name=s['name'], description=s.get('note', ''),
                    type=s['type'], path=f'{sid}/index.html') for sid, s in content.sources.items()]
    markets = next((block.get('items', [])[:9] for issues in content.issues.values()
                    for issue in issues[:1] for block in issue.get('blocks', [])
                    if block.get('type') == 'markets'), [])
    data = dict(scope='private' if content.private else 'public', today=content.today, updated=content.now.isoformat(), news=news, markets=markets,
                cards=trials, magazines=magazines, sources=sources, days=content.days)
    (out / 'visual-data.json').write_text(json.dumps(data, ensure_ascii=False).replace('</', '<\\/'))
