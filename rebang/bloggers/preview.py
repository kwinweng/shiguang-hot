"""只给验收截图用的静态预览（不是 v11 前端）：python3 -m rebang.bloggers.preview IN.json OUT.html

把 bloggers.json 按平台渲染成手机宽度的卡片页，证明字段（头像/名字/时间/正文/译文/图片/引用/互动/评论/
平台空状态）都是真数据。正式「博主」页由 frontend-v11 分支实现。
"""
import html
import json
import sys
from datetime import datetime

from .common import BJT

E = html.escape


def _time(value):
    return datetime.fromisoformat(value).astimezone(BJT).strftime('%m-%d %H:%M')


def _card(item):
    b = item['blogger']
    t = item.get('translation') if item.get('translated') else None
    avatar = f'<img class="av" src="{E(b["avatar"])}">' if b.get('avatar') else '<div class="av ph"></div>'
    head = (f'<div class="hd">{avatar}<div><b>{E(b["display_name"])}</b>'
            f'{" <i>✓</i>" if b.get("verified") else ""}<span> @{E(b["handle"])} · {_time(item["published_at"])}</span></div></div>')
    title = (t or {}).get('title') or item['title']
    text = (t or {}).get('body') or (t or {}).get('summary') or item.get('body') or item['summary']
    if b['platform'] == 'blog':
        text = (t or {}).get('summary') or item['summary']
    parts = [head]
    if title:
        parts.append(f'<h3>{E(title)}</h3>')
    parts.append(f'<p>{E(text[:400]) or "<em>无正文</em>"}</p>')
    if t:
        orig = (item['title'] + '\n' if item['title'] else '') + (item.get('body') if b['platform'] != 'blog' else item['summary'])
        parts.append(f'<details><summary>机器翻译 · 看原文</summary><p class="orig">{E(orig[:400])}</p></details>')
    media = b.get('media') or []
    if media:
        imgs = ''.join(f'<div class="m"><img src="{E(m.get("preview_url") or m["url"])}">{"<span>▶</span>" if m["type"] != "image" else ""}</div>'
                       for m in media[:4])
        parts.append(f'<div class="ms n{min(len(media), 4)}">{imgs}</div>')
    q = b.get('quote')
    if q:
        parts.append(f'<div class="q"><b>@{E(q["handle"])}</b> {E(q["text"][:160])}</div>')
    m = b.get('metrics') or {}
    nums = [(k, m[k]) for k in ('reply', 'repost', 'like') if m.get(k)]
    if nums:
        names = {'reply': '评论', 'repost': '转发', 'like': '赞'}
        parts.append('<div class="mt">' + ' · '.join(f'{names[k]} {v}' for k, v in nums) + '</div>')
    for c in (b.get('comments') or [])[:2]:
        parts.append(f'<div class="c"><b>@{E(c["handle"])}</b> {E(c["text"][:120])}</div>')
    return '<article>' + ''.join(parts) + '</article>'


def render(envelope, per_platform=6):
    sections = []
    for p in envelope['platforms']:
        items = [i for i in envelope['items'] if i['blogger']['platform'] == p['id']]
        items.sort(key=lambda i: i['published_at'], reverse=True)
        body = ''.join(_card(i) for i in items[:per_platform])
        if not items:
            body = f'<div class="empty">{E(p["name"])}的内容还没接上<br><small>{E(p.get("reason") or "本期名单为空")}</small></div>'
        ok = sum(1 for a in p['accounts'] if a['status'] == 'ok')
        sections.append(f'<section id="{p["id"]}"><h2>{E(p["name"])} <small>{p["status"]} · {ok}/{len(p["accounts"])} 个账号有内容 · {len(items)} 条</small></h2>{body}</section>')
    css = '''body{margin:0;background:#111;color:#e9e4d8;font:14px/1.55 -apple-system,"PingFang SC",sans-serif}
header{padding:12px 14px;color:#d6b36a;font-weight:600;border-bottom:1px solid #2a2a2a}
h2{color:#d6b36a;font-size:16px;margin:18px 14px 6px}h2 small{color:#a39e93;font-weight:400;font-size:12px}
article{margin:8px 12px;padding:12px;background:#1a1a1a;border-radius:10px}
.hd{display:flex;gap:8px;align-items:center}.hd span{color:#a39e93;font-size:12px}.hd i{color:#d6b36a;font-style:normal}
.av{width:36px;height:36px;border-radius:50%;object-fit:cover}.ph{background:#333}
h3{font-size:15px;margin:8px 0 4px}p{margin:6px 0;white-space:pre-wrap;display:-webkit-box;-webkit-line-clamp:6;-webkit-box-orient:vertical;overflow:hidden}
details summary{color:#a39e93;font-size:12px}.orig{color:#a39e93}
.ms{display:grid;gap:4px;grid-template-columns:repeat(2,1fr)}.ms.n1{grid-template-columns:1fr}
.m{position:relative}.m img{width:100%;height:140px;object-fit:cover;border-radius:6px}.m span{position:absolute;left:8px;bottom:8px;background:#000a;padding:2px 6px;border-radius:4px}
.q{border:1px solid #333;border-radius:8px;padding:8px;margin-top:6px;color:#cfc9bc;font-size:13px}
.mt{color:#a39e93;font-size:12px;margin-top:6px}.c{font-size:12px;color:#cfc9bc;border-top:1px solid #262626;padding-top:4px;margin-top:4px}
.empty{margin:8px 12px;padding:22px;text-align:center;color:#a39e93;background:#161616;border-radius:10px}'''
    return (f'<!doctype html><html lang="zh"><meta charset="utf-8"><meta name="viewport" content="width=device-width">'
            f'<style>{css}</style><header>博主（验收预览，非正式前端） · 生成于 {_time(envelope["generated_at"])} 北京时间</header>'
            + ''.join(sections) + '</html>')


def main(argv=None):
    argv = argv or sys.argv[1:]
    envelope = json.load(open(argv[0], encoding='utf-8'))
    open(argv[1], 'w', encoding='utf-8').write(render(envelope))
    return 0


if __name__ == '__main__':
    sys.exit(main())
