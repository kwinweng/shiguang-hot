"""Publish live, source, and daily-review surfaces inside the atomic site build."""
import hashlib
import json
import os
import shutil
from pathlib import Path

from shiguang.config import ROOT, WEB
from shiguang.site.news_data import MockProvider, daily_documents, messages, source_stats, write_json


def publish(content, out):
    sources = content.sources
    items = list(content.stream)
    for sid, issues in content.issues.items():
        for issue in issues:
            items.extend(content.issue_cards(sid, issue))
    rows = messages(items, sources)
    live = [r for r in rows if r['type'] == 'telegram']
    sample = os.getenv('SAMPLE_DATA') == '1' or bool(live) and all(r['title'].startswith('[示例]') for r in live)
    stats = source_stats(rows, sources, content.now, float(os.getenv('SOURCE_STALE_HOURS', '24')))
    history = out / 'history'
    # Scope and input authorization are reapplied every build, including copied old archives.
    stored = {}
    for base in (history, ROOT / 'history'):
        for path in base.glob('????-??-??.json'):
            try:
                doc = json.loads(path.read_text())
            except (ValueError, OSError):
                continue
            allowed = {sid for sid, s in sources.items() if s['visibility'] == 'public'}
            snapshot = doc.get('messages', [])
            if (snapshot and all(r.get('source') in allowed and r.get('day') == path.stem for r in snapshot)
                    and doc.get('provider') == 'mock' and path.stem < content.today
                    and all(r['title'].startswith('[示例]') for r in snapshot) == sample):
                # Reconstruct derived fields so stale/private nested event metadata cannot survive.
                stored[path.stem] = MockProvider().summarize(path.stem, snapshot)
    documents = daily_documents(rows, content.now)
    # Completed documents remain fixed until tools/daily_summary.py is explicitly rerun.
    for day, doc in documents.items():
        stored.setdefault(day, doc)
    shutil.rmtree(history, ignore_errors=True)
    history.mkdir()
    for day, doc in stored.items():
        write_json(history / f'{day}.json', doc)
    write_json(history / 'index.json', dict(days=sorted(stored), sample=sample))
    groups = []
    for row in live:
        if not groups or groups[-1]['hour'] != row['hour']:
            groups.append(dict(hour=row['hour'], messages=[]))
        groups[-1]['messages'].append(row)
    write_json(out / 'data/live.json', dict(sample=sample, updated=content.now.isoformat(), messages=live, hours=groups))
    write_json(out / 'data/sources.json', dict(sources=stats))
    names = {}
    for name in ('news-tokens.css', 'news.css', 'news-icons.js', 'news.js'):
        data = (WEB / name).read_bytes()
        path = Path(name)
        hashed = f'{path.stem}.{hashlib.sha256(data).hexdigest()[:10]}{path.suffix}'
        (out / hashed).write_bytes(data)
        names[name] = hashed
    html = '''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>拾光热榜 · 实时流与历史回顾</title>'''
    html += ''.join(f'<link rel="stylesheet" href="{names[name]}">' for name in ('news-tokens.css', 'news.css'))
    html += '''</head><body><header class="brand"><a href="index.html">拾光热榜</a>
<button id="theme" aria-label="切换明暗模式">明暗</button></header><main class="pg" id="news" aria-live="polite">
<p>正在加载消息…</p></main><noscript>请启用 JavaScript 查看实时流。
<a href="archive/''' + content.today + '''.html">查看静态文字页</a></noscript>
<nav class="news-nav" aria-label="主导航"><a href="#feed">实时流</a><a href="#history">历史回顾</a><a href="#sources">来源</a></nav>'''
    html += ''.join(f'<script src="{names[name]}"></script>' for name in ('news-icons.js', 'news.js'))
    for name in ('index.html', 'today.html'):
        (out / name).write_text(html + '</body></html>')
