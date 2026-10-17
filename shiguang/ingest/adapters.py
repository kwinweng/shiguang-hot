"""Adapters for sources that still deliver their own format (mail, world, x).

Each turns one delivered file into the shared shiguang.feed/1 shape. Native feeds never come here.
"""
import copy
from datetime import datetime
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo


def adapt(data, source):
    """mail / world / x files -> shiguang.feed/1. Delete once those bots write the shared format."""
    d = copy.deepcopy(data)
    if source.get('adapter') == 'x':
        d = dict(schema='shiguang.feed/1', source=source['id'], date=data.get('date'),
                 generated_at=data.get('generated_at'), sections=[], blocks=[])
        for kind, title in [('kol_posts', '推特爆款'), ('debates', '推特今日吵什么'), ('threads', '值得一读')]:
            items = []
            for post in data.get(kind, []) or []:
                summary = post.get('zh_summary') or ''
                author, handle = post.get('author_name') or '', (post.get('handle') or '').lstrip('@')
                url = post.get('url') or ''
                body = summary
                if kind == 'kol_posts':
                    who = post.get('who') or ('@' + handle if handle else '')
                    name = f'{author}（{who}）' if who else author
                    counts = ' · '.join(f'{symbol} {post[key]:,}' for key, symbol in [('likes', '♥'), ('reposts', '↻')]
                                        if isinstance(post.get(key), (int, float)) and not isinstance(post[key], bool))
                    body = '\n'.join(part for part in (summary, post.get('why_hot'), counts) if part)
                elif kind == 'debates':
                    name = post.get('title') or ''
                    body = '\n'.join(part for part in [summary] + (post.get('sides') or []) if part)
                    url = (post.get('urls') or [''])[0]
                else:
                    name = f'{author}（@{handle}）' if author and handle else author or summary[:30]
                if not name and not body: continue
                item = dict(title=name, body=body, source='X', link=url if urlsplit(url).scheme in ('http', 'https') else '')
                if post.get('created_at'):
                    try:
                        stamp = datetime.fromisoformat(post['created_at'].replace('Z', '+00:00'))
                        item['date'] = stamp.replace(tzinfo=stamp.tzinfo or ZoneInfo('Asia/Shanghai')).astimezone(ZoneInfo('Asia/Shanghai')).strftime('%Y-%m-%d %H:%M')
                    except (ValueError, TypeError): pass
                items.append(item)
            if items: d['sections'].append(dict(title=title, items=items))
        return d
    # mail and world: the summary blocks sit at the top level of the file.
    d['schema'] = 'shiguang.feed/1'
    d['source'] = source['id']
    d['blocks'] = []
    for kind in ('oneliner', 'markets', 'chart', 'tomorrow'):
        if d.get(kind):
            d['blocks'].append(dict(type=kind, **({'items': d[kind]} if kind != 'chart' else d[kind])))
    for kind in ('oneliner', 'markets', 'chart', 'tomorrow'):
        d.pop(kind, None)
    return d
