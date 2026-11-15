"""X 博主：读「公开 X 读取工具」的原始响应（X API v2 结构：data / includes.users / includes.media /
includes.posts|tweets），转成博主卡片。

不在这里联网、不登录、不硬爬网页。原始响应由 Grok Bot 用自带的公开 X 读取工具写到 dump 目录
（每次运行一个子目录，里面任意多个 *.json / *.txt）。.txt 兼容中文圈早报 raw/<日>/*.txt
（文本里嵌一段 JSON）。文件名以 quotes / replies / refs 开头的只当参考（补引用、评论），
其中的帖子不会作为博主自己的卡片出现；可选 _dump.json 写 generated_at。
"""
import html
import json
import re
from pathlib import Path

from .common import BODY_CHARS, clip, detect_lang, iso, normalize_text, parse_time, source_id, summary_of

METRIC_MAP = {
    'reply_count': 'reply', 'retweet_count': 'repost', 'repost_count': 'repost', 'like_count': 'like',
    'quote_count': 'quote', 'bookmark_count': 'bookmark', 'impression_count': 'view',
}
MAX_COMMENTS = 3
REF_PREFIXES = ('quotes', 'replies', 'refs')
_TCO = re.compile(r'\s*https://t\.co/\w+\s*$')


def _decode_blobs(text):
    """从一段文本里取出所有顶层 X 响应 JSON 对象。"""
    dec = json.JSONDecoder()
    out, pos = [], 0
    while True:
        starts = [i for i in (text.find('{"data"', pos), text.find('{"meta"', pos), text.find('{"includes"', pos)) if i >= 0]
        if not starts:
            return out
        start = min(starts)
        try:
            obj, end = dec.raw_decode(text[start:])
        except ValueError:
            pos = start + 1
            continue
        if isinstance(obj, dict):
            out.append(obj)
        pos = start + end


def load_dump(path):
    """合并一个 dump 目录（或单个文件）里的所有响应 → (posts, users, media)。"""
    path = Path(path)
    files = (sorted(f for f in path.glob('*.json') if f.name != '_dump.json') + sorted(path.glob('*.txt'))) if path.is_dir() else [path]
    posts, users, media = {}, {}, {}
    main_ids = set()
    for f in files:
        reference_only = f.name.startswith(REF_PREFIXES)
        text = f.read_text(encoding='utf-8', errors='replace')
        blobs = []
        if f.suffix == '.json':
            try:
                data = json.loads(text)
                blobs = data if isinstance(data, list) else [data]
            except ValueError:
                blobs = _decode_blobs(text)
        else:
            blobs = _decode_blobs(text)
        for blob in blobs:
            if not isinstance(blob, dict):
                continue
            inc = blob.get('includes') or {}
            for u in inc.get('users') or []:
                users.setdefault(u['id'], {}).update(u)
            for m in inc.get('media') or []:
                media.setdefault(m['media_key'], {}).update(m)
            data = [p for p in blob.get('data') or [] if isinstance(p, dict)]
            if not reference_only:
                main_ids.update(p['id'] for p in data if p.get('id'))
            for p in data + list(inc.get('posts') or []) + list(inc.get('tweets') or []):
                if isinstance(p, dict) and p.get('id'):
                    # 后读到的字段补齐先读到的（例如搜索结果缺 note_tweet，按 id 详情补上）
                    merged = posts.setdefault(p['id'], {})
                    for k, v in p.items():
                        if k not in merged or (k == 'text' and len(v) > len(merged.get(k, ''))):
                            merged[k] = v
    for pid in main_ids:
        posts[pid]['_main'] = True
    return posts, users, media


def _full_text(post):
    note = post.get('note_tweet') or post.get('note_post') or {}
    text = note.get('text') or post.get('text') or ''
    return normalize_text(html.unescape(text))


def _avatar(user):
    url = user.get('profile_image_url')
    if not url or not url.startswith('https://'):
        return None
    return re.sub(r'_normal(\.\w+)$', r'_400x400\1', url)


def _media(post, media):
    out = []
    for key in (post.get('attachments') or {}).get('media_keys') or []:
        m = media.get(key)
        if not m:
            continue
        if m.get('type') == 'photo' and m.get('url'):
            entry = {'type': 'image', 'url': m['url']}
        elif m.get('type') in ('video', 'animated_gif') and m.get('preview_image_url'):
            mp4 = sorted((v for v in m.get('variants') or [] if v.get('content_type') == 'video/mp4' and v.get('url')),
                         key=lambda v: v.get('bit_rate') or 0)
            entry = {'type': 'video' if m['type'] == 'video' else 'gif',
                     'url': mp4[-1]['url'] if mp4 else m['preview_image_url'],
                     'preview_url': m['preview_image_url']}
            if isinstance(m.get('duration_ms'), int):
                entry['duration_ms'] = m['duration_ms']
        else:
            continue
        for dim in ('width', 'height'):
            if isinstance(m.get(dim), int) and m[dim] > 0:
                entry[dim] = m[dim]
        if m.get('alt_text'):
            entry['alt'] = m['alt_text']
        out.append(entry)
    return out


def _metrics(post):
    out = {}
    for key, value in (post.get('public_metrics') or {}).items():
        if key in METRIC_MAP and isinstance(value, int) and value >= 0:
            out[METRIC_MAP[key]] = value
    return out


def _quote(post, posts, users):
    for ref in post.get('referenced_tweets') or []:
        if ref.get('type') != 'quoted':
            continue
        q = posts.get(ref.get('id'))
        author = users.get((q or {}).get('author_id')) or {}
        text = _full_text(q) if q else ''
        if not (q and author.get('username') and text):
            return None  # 拿不全就不画引用框
        return {'handle': author['username'], 'display_name': author.get('name', author['username']),
                'text': _TCO.sub('', text) or text, 'url': f'https://x.com/{author["username"]}/status/{q["id"]}',
                'published_at': iso(parse_time(q['created_at'])) if parse_time(q.get('created_at')) else None}
    return None


def _comments(post, posts, users):
    def is_reply(p):
        if p['id'] == post['id'] or p.get('author_id') == post.get('author_id'):
            return False
        if p.get('conversation_id') == post['id']:
            return True
        return any(r.get('type') == 'replied_to' and r.get('id') == post['id'] for r in p.get('referenced_tweets') or [])
    replies = [p for p in posts.values() if is_reply(p)]
    replies.sort(key=lambda p: -((p.get('public_metrics') or {}).get('like_count') or 0))
    out = []
    for r in replies[:MAX_COMMENTS]:
        author = users.get(r.get('author_id')) or {}
        moment = parse_time(r.get('created_at'))
        text = re.sub(r'^(?:@\w+\s+)+', '', _full_text(r)).strip()
        if not (author.get('username') and text and moment):
            continue
        out.append({'handle': author['username'], 'display_name': author.get('name', author['username']),
                    'avatar': _avatar(author), 'text': text, 'published_at': iso(moment),
                    'url': f'https://x.com/{author["username"]}/status/{r["id"]}',
                    'like': (r.get('public_metrics') or {}).get('like_count')})
    return out


def x_posts(dump, platform, fetched_at, limit=10):
    """返回 {handle: [items]}，名单里每人都有键（没帖子就是空列表）。"""
    posts, users, media = dump
    by_name = {u.get('username', '').lower(): u for u in users.values()}
    result = {}
    for account in platform['accounts']:
        handle = account['handle']
        user = by_name.get(handle.lower())
        items = []
        if user:
            own = [p for p in posts.values() if p.get('_main') and p.get('author_id') == user['id']
                   and p.get('conversation_id', p['id']) == p['id']
                   and not any(r.get('type') in ('retweeted', 'replied_to') for r in p.get('referenced_tweets') or [])]
            for p in own:
                moment = parse_time(p.get('created_at'))
                text = _full_text(p)
                if not moment or not text:
                    continue
                media_list = _media(p, media)
                display = _TCO.sub('', text) if media_list or p.get('referenced_tweets') else text
                if not display and not media_list and not p.get('referenced_tweets'):
                    continue
                sid = source_id(platform['id'], handle)
                blogger = {
                    'platform': platform['id'], 'handle': user['username'],
                    'display_name': user.get('name') or account['name'],
                    'media': [{k: v for k, v in m.items() if k in ('type', 'url', 'preview_url', 'duration_ms')} for m in media_list],
                    'quote': _quote(p, posts, users),
                }
                avatar = _avatar(user)
                if avatar:
                    blogger['avatar'] = avatar
                if isinstance(user.get('verified'), bool):
                    blogger['verified'] = user['verified']
                metrics = _metrics(p)
                if metrics:
                    blogger['metrics'] = metrics
                comments = _comments(p, posts, users)
                if comments:
                    blogger['comments'] = comments
                first = next((m for m in media_list if m['type'] == 'image'), None) or \
                    next((m for m in media_list if m.get('preview_url')), None)
                image = None
                if first:
                    image = {'url': first.get('preview_url') or first['url']}
                    for dim in ('width', 'height'):
                        if first.get(dim):
                            image[dim] = first[dim]
                lang = p['lang'] if p.get('lang') in ('zh', 'en') else (detect_lang(display) if display.strip() else 'und')
                items.append((moment, {
                    'id': f'{sid}:{p["id"]}', 'kind': 'post', 'channel': None,
                    'source_id': sid, 'source_name': blogger['display_name'],
                    'title': '', 'summary': summary_of(display), 'body': clip(display, BODY_CHARS),
                    'url': f'https://x.com/{user["username"]}/status/{p["id"]}',
                    'image': image, 'published_at': iso(moment), 'fetched_at': fetched_at,
                    'lang': lang, 'blogger': blogger,
                }))
        items.sort(key=lambda pair: pair[0], reverse=True)
        result[handle] = [it for _, it in items[:limit]]
    return result


def latest_dump(root):
    """dump 根目录下最新的子目录（按名字排序，名字用 YYYYMMDDTHHMM）；没有返回 None。"""
    root = Path(root)
    if not root.is_dir():
        return None
    subdirs = sorted(d for d in root.iterdir() if d.is_dir() and (any(d.glob('*.json')) or any(d.glob('*.txt'))))
    return subdirs[-1] if subdirs else None


def dump_time(path):
    """dump 生成时间：优先 _dump.json 的 generated_at，否则取文件最新修改时间。"""
    from datetime import datetime, timezone
    path = Path(path)
    meta = path / '_dump.json' if path.is_dir() else None
    if meta and meta.exists():
        try:
            moment = parse_time(json.loads(meta.read_text(encoding='utf-8')).get('generated_at'))
            if moment:
                return moment
        except ValueError:
            pass
    files = list(path.glob('*')) if path.is_dir() else [path]
    newest = max((f.stat().st_mtime for f in files if f.is_file()), default=None)
    return datetime.fromtimestamp(newest, timezone.utc) if newest else None
