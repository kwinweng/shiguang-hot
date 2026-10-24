"""Publish live, source, and daily-review surfaces inside the atomic site build."""
import hashlib
import json
import os
import shutil
from pathlib import Path

from shiguang.config import ROOT, WEB
from shiguang.model import home_candidates
from shiguang.site.news_data import MockProvider, daily_documents, messages, source_stats, write_json


def publish(content, out):
    sources = content.sources
    items = list(content.stream)
    for sid, issues in content.issues.items():
        for issue in issues:
            items.extend(content.tagged(home_candidates(issue, sources[sid]), sources[sid]))
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
    # Presentation-only documents: reuse authorized input, never trigger ingestion.
    focus = {}
    for sid, issues in content.issues.items():
        if sid == getattr(content, 'hot_source', None):
            for issue in issues:
                focus[issue['date']] = messages(content.tagged(home_candidates(issue, sources[sid]), sources[sid]), sources)
    write_json(out / 'data/focus.json', dict(days=focus))
    explore = []
    for sid, issues in content.issues.items():
        if sid == getattr(content, 'hot_source', None) or not issues:
            continue
        for item in content.tagged(home_candidates(issues[0], sources[sid]), sources[sid]):
            category = item.category
            source_name = sources[sid]['name']
            section = ('buy' if any(w in source_name for w in ('好买', '购物')) else
                       'kan' if category in ('剧', '电影', '小说', '展览') else
                       'play' if category in ('吃喝', '美食', '新店', '出行', '温泉', '游戏', '风景', '北京周末') else None)
            if section is None:
                continue
            for row in messages([item], sources):
                row['category'] = item.category
                row['section'] = section
                explore.append(row)
    write_json(out / 'data/explore.json', dict(messages=explore))
    names = {}
    for name in ('news-tokens.css', 'news.css', 'news-icons.js', 'news.js', 'modules.js'):
        data = (WEB / name).read_bytes()
        path = Path(name)
        hashed = f'{path.stem}.{hashlib.sha256(data).hexdigest()[:10]}{path.suffix}'
        (out / hashed).write_bytes(data)
        names[name] = hashed
    html = '''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>拾光热榜 · 资讯与探索</title>'''
    html += ''.join(f'<link rel="stylesheet" href="{names[name]}">' for name in ('news-tokens.css', 'news.css'))
    html += '''<link rel="icon" href="favicon.svg"><link rel="apple-touch-icon" href="apple-touch-icon.png"><link rel="manifest" href="manifest.webmanifest"></head><body><header class="brand"><a href="index.html">拾光热榜</a>
<button id="theme" aria-label="切换明暗模式">明暗</button></header><main class="pg" id="news" aria-live="polite">
<div class="skeleton" aria-label="加载中"></div></main><div id="refresh-status" role="status" aria-live="polite"></div><noscript>请启用 JavaScript 查看实时流。
<a href="archive/''' + content.today + '''.html">查看静态文字页</a></noscript>
<nav class="news-nav" aria-label="主导航"><a href="#feed" data-nav="news">资讯</a><a href="#explore/play" data-nav="explore">探索</a><a href="#me" data-nav="me">我的</a></nav>'''
    html += ''.join(f'<script src="{names[name]}"></script>' for name in ('news-icons.js', 'news.js', 'modules.js'))
    scope = 'private' if getattr(content, 'private', False) else 'public'
    html = html.replace('<body>', f'<body data-bookmark-scope="{scope}">')
    for name in ('index.html', 'today.html'):
        (out / name).write_text(html + '</body></html>')
    missing = html.replace('id="news"', 'id="news" data-not-found="true"').replace(
        '<div class="skeleton" aria-label="加载中"></div>',
        '<p class="empty">404 · 这个页面不存在</p><a class="btn pri" href="index.html#feed">回到资讯</a>')
    (out / '404.html').write_text(missing + '</body></html>')
    for name, target in (('hot.html', '#focus'),):
        (out / name).write_text(f'<!doctype html><meta charset="utf-8"><meta http-equiv="refresh" content="0;url=index.html{target}"><a href="index.html{target}">继续浏览</a>')
