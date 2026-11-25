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
# Include object starts cut off even before the first key or colon.
_BLOB_START = re.compile(r'\{\s*(?="|$)')


def _object(value):
    return value if isinstance(value, dict) else {}


def _array(value):
    return value if isinstance(value, list) else []


def _nonempty(value):
    return isinstance(value, str) and bool(value.strip())


def dump_files(path):
    return sorted(f for pattern in ('*.json', '*.txt') for f in path.glob(pattern)
                  if f.is_file() and f.name != '_dump.json')


def _decode_blobs(text, *, json_file):
    """Find export responses in logs and keep track of decoding failures."""
    try:
        value = json.loads(text)
    except (ValueError, RecursionError):
        pass
    else:
        return (value if isinstance(value, list) else [value]), False
    dec = json.JSONDecoder()
    out, pos = [], 0
    broken = json_file or text.lstrip().startswith('[')
    while match := _BLOB_START.search(text, pos):
        try:
            obj, pos = dec.raw_decode(text, match.start())
        except (ValueError, RecursionError):
            broken = True
            pos = match.end()
        else:
            out.append(obj)
    return out, broken


def _merge_rows(target, rows, key):
    for row in _array(rows):
        if isinstance(row, dict) and _nonempty(row.get(key)):
            target.setdefault(row[key], {}).update(row)


def _merge_posts(posts, rows):
    for row in _array(rows):
        if not (isinstance(row, dict) and _nonempty(row.get('id'))):
            continue
        merged = posts.setdefault(row['id'], {})
        for key, value in row.items():
            if key == 'text':
                if isinstance(value, str) and len(value) > len(merged.get(key, '')):
                    merged[key] = value
            else:
                merged.setdefault(key, value)


def _merge_users(users, rows):
    _merge_rows(users, [u for u in _array(rows) if _nonempty(_object(u).get('username'))], 'id')


def _failed_handles(file, errors, handles, users):
    def known(value):
        return handles.get(value.strip().lstrip('@').lower()) if isinstance(value, str) else None

    file_handle = known(file.stem.lower().removeprefix('search-').removeprefix('posts-'))
    failed = set()
    for error in _array(errors) or [{}]:
        error = _object(error)
        handle = known(error.get('username')) or known(error.get('handle')) or file_handle
        if error.get('parameter') == 'username':
            handle = known(error.get('value')) or handle
        if error.get('resource_type') == 'user':
            handle = known(users.get(str(error.get('resource_id')), {}).get('username')) or handle
        if not handle:
            return set(handles.values())
        failed.add(handle)
    return failed


def _valid_post(row, users):
    row = _object(row)
    author = row.get('author_id')
    return (_nonempty(row.get('id')) and _nonempty(author) and author in users
            and parse_time(row.get('created_at')) is not None and bool(_full_text(row)))


def read_export(path, account_handles):
    """Read a complete export and preserve recognized account errors on parse failure."""
    path = Path(path)
    files = dump_files(path) if path.is_dir() else [path]
    posts, users, media = {}, {}, {}
    responses, errors = [], []
    broken = not files
    for file in files:
        try:
            blobs, malformed = _decode_blobs(file.read_text(encoding='utf-8'), json_file=file.suffix == '.json')
        except (OSError, UnicodeError):
            blobs, malformed = [], True
        broken |= malformed or not blobs
        for blob in blobs:
            if not isinstance(blob, dict):
                broken = True
                continue
            if blob.get('errors'):
                errors.append((file, blob['errors']))
            responses.append((file, blob))

    for _, blob in responses:
        includes = _object(blob.get('includes'))
        _merge_users(users, includes.get('users'))
        _merge_rows(media, includes.get('media'), 'media_key')

    handles = {handle.lower(): handle for handle in account_handles}
    failures = {handle: 'x_dump_error' for file, rows in errors
                for handle in _failed_handles(file, rows, handles, users)}
    main_ids, valid_main = set(), False
    for file, blob in responses:
        data = blob.get('data')
        meta = _object(blob.get('meta'))
        count = meta.get('result_count')
        if data is None and type(count) is int and count == 0:
            data = []
        if data is None and ('data' not in blob and 'meta' not in blob) and ('includes' in blob or blob.get('errors')):
            continue
        if (('meta' in blob and not isinstance(blob['meta'], dict)) or not isinstance(data, list)
                or not all(_valid_post(row, users) for row in data)
                or ('result_count' in meta and (type(count) is not int or count != len(data)))):
            broken = True
            continue
        if not file.name.startswith(REF_PREFIXES):
            valid_main |= bool(data) or not blob.get('errors')
            main_ids.update(row['id'] for row in data)
        _merge_posts(posts, data)

    if broken or not valid_main:
        for handle in handles.values():
            failures.setdefault(handle, 'parse')
        return ({}, {}, {}), failures
    for _, blob in responses:
        includes = _object(blob.get('includes'))
        for key in ('posts', 'tweets'):
            _merge_posts(posts, [row for row in _array(includes.get(key)) if _valid_post(row, users)])
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
    except (OSError, ValueError, RecursionError):
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
        inc = _object(blob.get('includes'))
        _merge_users(users, inc.get('users'))
        for rows in (blob.get('data'), inc.get('posts'), inc.get('tweets')):
            _merge_posts(posts, rows)
    return posts, users


def _full_text(post):
    note = _object(post.get('note_tweet')) or _object(post.get('note_post'))
    text = note.get('text')
    if not _nonempty(text):
        text = post.get('text')
    return normalize_text(html.unescape(text)) if _nonempty(text) else ''


def _avatar(user):
    url = user.get('profile_image_url')
    if not isinstance(url, str) or not url.startswith('https://'):
        return None
    return re.sub(r'_normal(\.\w+)$', r'_400x400\1', url)


def _media(post, media):
    out = []
    for key in _array(_object(post.get('attachments')).get('media_keys')):
        m = media.get(key) if isinstance(key, str) else None
        if not m:
            continue
        if m.get('type') == 'photo' and _nonempty(m.get('url')):
            entry = {'type': 'image', 'url': m['url']}
        elif m.get('type') in ('video', 'animated_gif') and _nonempty(m.get('preview_image_url')):
            mp4 = sorted((v for v in _array(m.get('variants')) if isinstance(v, dict)
                          and v.get('content_type') == 'video/mp4' and _nonempty(v.get('url'))),
                         key=lambda v: v.get('bit_rate') if isinstance(v.get('bit_rate'), int) else 0)
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
        if _nonempty(m.get('alt_text')):
            entry['alt'] = m['alt_text']
        out.append(entry)
    return out


def _metrics(post):
    out = {}
    for key, value in _object(post.get('public_metrics')).items():
        if key in METRIC_MAP and isinstance(value, int) and value >= 0:
            out[METRIC_MAP[key]] = value
    return out


def _references(post):
    return [r for r in _array(post.get('referenced_tweets')) if isinstance(r, dict) and _nonempty(r.get('id'))]


def _author(post, users):
    author = _object(post).get('author_id')
    return users.get(author, {}) if isinstance(author, str) else {}


def _display_name(user, fallback):
    return user['name'] if _nonempty(user.get('name')) else fallback


def _quote(post, posts, users):
    for ref in _references(post):
        if ref.get('type') != 'quoted':
            continue
        q = posts.get(ref.get('id'))
        author = _author(q, users)
        text = _full_text(q) if q else ''
        if not (q and author.get('username') and text):
            return None  # 拿不全就不画引用框
        return {'handle': author['username'], 'display_name': _display_name(author, author['username']),
                'text': _TCO.sub('', text) or text, 'url': f'https://x.com/{author["username"]}/status/{q["id"]}',
                'published_at': iso(parse_time(q['created_at'])) if parse_time(q.get('created_at')) else None}
    return None


def _comments(post, posts, users):
    def is_reply(p):
        if p['id'] == post['id'] or p.get('author_id') == post.get('author_id'):
            return False
        if p.get('conversation_id') == post['id']:
            return True
        return any(r.get('type') == 'replied_to' and r.get('id') == post['id'] for r in _references(p))
    replies = [p for p in posts.values() if is_reply(p)]
    replies.sort(key=lambda p: -_metrics(p).get('like', 0))
    out = []
    for r in replies[:MAX_COMMENTS]:
        author = _author(r, users)
        moment = parse_time(r.get('created_at'))
        text = re.sub(r'^(?:@\w+\s+)+', '', _full_text(r)).strip()
        if not (author.get('username') and text and moment):
            continue
        row = {'handle': author['username'], 'display_name': _display_name(author, author['username']),
               'avatar': _avatar(author), 'text': text, 'published_at': iso(moment),
               'url': f'https://x.com/{author["username"]}/status/{r["id"]}'}
        like = _metrics(r).get('like')
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
                   and not any(r.get('type') in ('retweeted', 'replied_to') for r in _references(p))]
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
                    'display_name': _display_name(user, account['name']),
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
    subdirs = sorted(d for d in root.iterdir() if d.is_dir() and dump_files(d))
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
