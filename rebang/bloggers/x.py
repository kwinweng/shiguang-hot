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
MAX_COMMENTS = 10
REF_PREFIXES = ('quotes', 'replies', 'refs')
_TCO = re.compile(r'\s*https://t\.co/\w+\s*$')
_BLOB_START = re.compile(r'{\s*"(?:data|meta|includes|errors)"\s*:')


def _decode_blobs(text):
    """从一段文本里取出所有顶层 X 响应 JSON 对象。"""
    try:
        value = json.loads(text)
    except ValueError:
        pass  # 兼容文本日志里的嵌入式响应
    else:
        return value if isinstance(value, list) else [value]
    dec = json.JSONDecoder()
    out, pos = [], 0
    while match := _BLOB_START.search(text, pos):
        try:
            obj, pos = dec.raw_decode(text, match.start())
        except ValueError:
            pos = match.end()
        else:
            out.append(obj)
    return out


def _main_data(blob):
    data = blob.get('data')
    if isinstance(data, list) and all(isinstance(p, dict) and p.get('id') for p in data):
        return data
    meta = blob.get('meta')
    if data is None and isinstance(meta, dict) and type(meta.get('result_count')) is int and meta['result_count'] == 0:
        return []
    return None


def _failed_handles(file, errors, handles, users):
    def known(value):
        return handles.get(value.strip().lstrip('@').lower()) if isinstance(value, str) else None

    file_handle = known(file.stem.lower().removeprefix('search-').removeprefix('posts-'))
    if not isinstance(errors, list) or not errors:
        return {file_handle} if file_handle else set(handles.values())
    failed = set()
    for error in errors:
        handle = file_handle
        if isinstance(error, dict):
            handle = known(error.get('username')) or known(error.get('handle')) or handle
            if error.get('parameter') == 'username':
                handle = known(error.get('value')) or handle
            if error.get('resource_type') == 'user':
                user = users.get(str(error.get('resource_id')), {})
                handle = known(user.get('username')) or handle
        if not handle:
            return set(handles.values())
        failed.add(handle)
    return failed


def read_export(path, account_handles):
    """Return the combined dump and fixed error codes for the affected accounts."""
    path = Path(path)
    files = (sorted(f for f in path.glob('*.json') if f.name != '_dump.json') + sorted(path.glob('*.txt'))) if path.is_dir() else [path]
    posts, users, media = {}, {}, {}
    main_ids, problems = set(), []
    valid_main = False
    for f in files:
        reference_only = f.name.startswith(REF_PREFIXES)
        try:
            blobs = _decode_blobs(f.read_text(encoding='utf-8', errors='replace'))
        except OSError:
            blobs = []
        if not blobs and not reference_only:
            problems.append((f, 'parse', None))
        for blob in blobs:
            if not isinstance(blob, dict):
                if not reference_only:
                    problems.append((f, 'parse', None))
                continue
            data = _main_data(blob)
            if not reference_only:
                errors = blob.get('errors')
                if errors:
                    problems.append((f, 'x_dump_error', errors))
                elif data is None and ('data' in blob or 'meta' in blob or 'includes' not in blob):
                    problems.append((f, 'parse', None))
                if data or (data is not None and not errors):
                    valid_main = True
                main_ids.update(p['id'] for p in data or [])
            inc = blob.get('includes') or {}
            for u in inc.get('users') or []:
                users.setdefault(u['id'], {}).update(u)
            for m in inc.get('media') or []:
                media.setdefault(m['media_key'], {}).update(m)
            for p in (data or []) + list(inc.get('posts') or []) + list(inc.get('tweets') or []):
                if isinstance(p, dict) and p.get('id'):
                    # 后读到的字段补齐先读到的（例如搜索结果缺 note_tweet，按 id 详情补上）
                    merged = posts.setdefault(p['id'], {})
                    for k, v in p.items():
                        if k not in merged or (k == 'text' and len(v) > len(merged.get(k, ''))):
                            merged[k] = v
    handles = {handle.lower(): handle for handle in account_handles}
    failures = {}
    for file, code, errors in problems:
        for handle in _failed_handles(file, errors, handles, users):
            if code == 'x_dump_error' or handle not in failures:
                failures[handle] = code
    if not valid_main:
        default = 'x_dump_error' if any(code == 'x_dump_error' for _, code, _ in problems) else 'parse'
        for handle in handles.values():
            failures.setdefault(handle, default)
    for pid in main_ids:
        posts[pid]['_main'] = True
    store = reply_store_near(path)
    if store:
        merge_reply_store(posts, users, store)
    return (posts, users, media), failures


def load_dump(path):
    """Read posts, users and media from a dump directory or a single file."""
    dump, _ = read_export(path, ())
    return dump


def reply_store_near(dump):
    """x-dump 根目录或某次子目录旁边的持久回复缓存：../x-replies/store.json。"""
    p = Path(dump)
    if p.is_file():
        p = p.parent
    for base in (p, p.parent):
        cand = base.parent / 'x-replies' / 'store.json'
        if cand.is_file():
            return cand
    return None


def merge_reply_store(posts, users, path):
    """把缓存里的原始搜索响应并进 posts/users（只补评论，不加 _main，不会变成博主卡片）。"""
    path = Path(path)
    if not path.is_file():
        return posts, users
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return posts, users
    blobs = []
    if isinstance(data, dict) and isinstance(data.get('posts'), dict):
        for entry in data['posts'].values():
            if isinstance(entry, dict) and isinstance(entry.get('response'), dict):
                blobs.append(entry['response'])
    elif isinstance(data, list):
        blobs = [b for b in data if isinstance(b, dict)]
    elif isinstance(data, dict) and ('data' in data or 'includes' in data):
        blobs = [data]
    for blob in blobs:
        inc = blob.get('includes') or {}
        for u in inc.get('users') or []:
            if isinstance(u, dict) and u.get('id'):
                users.setdefault(u['id'], {}).update(u)
        rows = list(blob.get('data') or []) + list(inc.get('posts') or []) + list(inc.get('tweets') or [])
        for post in rows:
            if not (isinstance(post, dict) and post.get('id')):
                continue
            merged = posts.setdefault(post['id'], {})
            for k, v in post.items():
                if k not in merged or (k == 'text' and len(str(v)) > len(str(merged.get(k) or ''))):
                    merged[k] = v
    return posts, users


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
        row = {'handle': author['username'], 'display_name': author.get('name', author['username']),
               'avatar': _avatar(author), 'text': text, 'published_at': iso(moment),
               'url': f'https://x.com/{author["username"]}/status/{r["id"]}'}
        like = (r.get('public_metrics') or {}).get('like_count')
        if isinstance(like, int) and like >= 0:
            row['like'] = like
        out.append(row)
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
    """dump 根目录下最新的已写完子目录（有 _dump.json；按名字排序，名字用 YYYYMMDDTHHMM）；都没写完就取最新的；没有返回 None。"""
    root = Path(root)
    if not root.is_dir():
        return None
    subdirs = sorted(d for d in root.iterdir() if d.is_dir() and (any(d.glob('*.json')) or any(d.glob('*.txt'))))
    # 例程最后一步才写 _dump.json：有它的才算写完。正在写的目录（比如只有 search-p1.json）不用，免得半份数据把博主刷空
    done = [d for d in subdirs if (d / '_dump.json').exists()]
    return (done or subdirs)[-1] if subdirs else None


def dump_time(path):
    """dump 生成时间：优先 _dump.json 的 generated_at，否则取文件最新修改时间。"""
    from datetime import datetime, timezone
    path = Path(path)
    meta = path / '_dump.json' if path.is_dir() else None
    try:
        if meta and meta.exists():
            metadata = json.loads(meta.read_text(encoding='utf-8'))
            if not isinstance(metadata, dict):
                return None
            if 'generated_at' in metadata:
                return parse_time(metadata['generated_at'])
        files = path.iterdir() if path.is_dir() else [path]
        newest = max((f.stat().st_mtime for f in files if f.is_file()), default=None)
        return datetime.fromtimestamp(newest, timezone.utc) if newest is not None else None
    except (OSError, ValueError, OverflowError):
        return None
