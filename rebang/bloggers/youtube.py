"""YouTube 频道 → 博主帖子条目。全部是公开页面，不用 API 密钥、不登录、不带 Cookie。

主路：官方频道订阅 https://www.youtube.com/feeds/videos.xml?channel_id=UC…（Atom + media:group）。
这个接口 2026 年经常整段时间对存在的频道回 404/500（不是频道没了），所以：
  1. 订阅失败先隔一会儿重试一次；
  2. 仍失败就退到频道「视频」页（ytInitialData 里的 lockupViewModel：视频号、标题、封面、时长），
     发布时间和简介从视频页的 microformat（publishDate、shortDescription）取，按视频号缓存，
     每个频道每轮最多补 WATCH_BUDGET 个视频页；拿不到发布时间的视频这轮不出，不编时间；
  3. 两条路都失败，这个频道算 error，编排层沿用上次成功的内容并标日期。
播放：站内查看器用 youtube-nocookie 的嵌入播放器（media.type = "youtube"），播不了就给原视频链接。
"""
import json
from datetime import datetime
import re
import xml.etree.ElementTree as ET
from pathlib import Path

from .common import BODY_CHARS, clip, detect_lang, iso, normalize_text, parse_time, source_id, summary_of
from .feed import FeedError

ATOM = '{http://www.w3.org/2005/Atom}'
YT = '{http://www.youtube.com/xml/schemas/2015}'
MEDIA = '{http://search.yahoo.com/mrss/}'
FEED = 'https://www.youtube.com/feeds/videos.xml?channel_id={}'
VIDEOS = 'https://www.youtube.com/channel/{}/videos'
WATCH = 'https://www.youtube.com/watch?v={}'
EMBED = 'https://www.youtube-nocookie.com/embed/{}'
THUMB = 'https://i.ytimg.com/vi/{}/hqdefault.jpg'
WATCH_BUDGET = 4          # 订阅挂掉时，每个频道每轮最多打开几个视频页补发布时间
RETRY_PAUSE = 20          # 订阅失败后隔几秒重试一次
_VID = re.compile(r'^[\w-]{11}$')
_CID = re.compile(r'^UC[\w-]{22}$')


def valid_channel_id(value):
    return bool(_CID.match(str(value or '')))


# ---------- 订阅源 ----------

def parse_feed(body):
    """频道订阅 → [{video_id, title, published, description, thumb, views}]；不是 YouTube 订阅抛 FeedError。"""
    try:
        root = ET.fromstring(body)
    except ET.ParseError:
        raise FeedError('not_xml') from None
    if root.tag != ATOM + 'feed':
        raise FeedError('not_feed')
    out = []
    for e in root.findall(ATOM + 'entry'):
        vid = (e.findtext(YT + 'videoId') or '').strip()
        if not _VID.match(vid):
            continue
        group = e.find(MEDIA + 'group')
        desc = (group.findtext(MEDIA + 'description') if group is not None else '') or ''
        thumb = group.find(MEDIA + 'thumbnail') if group is not None else None
        stats = group.find(f'{MEDIA}community/{MEDIA}statistics') if group is not None else None
        views = stats.get('views') if stats is not None else None
        out.append({
            'video_id': vid,
            'title': (e.findtext(ATOM + 'title') or '').strip(),
            'published': (e.findtext(ATOM + 'published') or '').strip(),
            'description': desc,
            'thumb': thumb.get('url') if thumb is not None and (thumb.get('url') or '').startswith('https://') else '',
            'views': int(views) if views and views.isdigit() else None,
        })
    return out


# ---------- 公开页面兜底 ----------

def _initial_data(html, var):
    m = re.search(r'(?:var |window\[")' + re.escape(var) + r'(?:"\])?\s*=\s*(\{.*?\});\s*(?:var |</script>)', html, re.S)
    if not m:
        return None
    try:
        return json.loads(m.group(1))
    except ValueError:
        return None


def _walk(node, key):
    stack = [node]
    while stack:
        cur = stack.pop()
        if isinstance(cur, dict):
            if key in cur:
                yield cur[key]
            stack.extend(reversed(list(cur.values())))
        elif isinstance(cur, list):
            stack.extend(reversed(cur))


def parse_channel_page(html):
    """频道「视频」页 → [{video_id, title, thumb, duration_ms?}]（新到旧）。结构不认识返回 []。"""
    data = _initial_data(html, 'ytInitialData')
    if not data:
        return []
    out, seen = [], set()
    for lv in _walk(data, 'lockupViewModel'):
        if not isinstance(lv, dict) or lv.get('contentType') != 'LOCKUP_CONTENT_TYPE_VIDEO':
            continue
        vid = lv.get('contentId') or ''
        if not _VID.match(vid) or vid in seen:
            continue
        seen.add(vid)
        meta = ((lv.get('metadata') or {}).get('lockupMetadataViewModel') or {})
        title = ((meta.get('title') or {}).get('content') or '').strip()
        row = {'video_id': vid, 'title': title, 'thumb': ''}
        img = ((lv.get('contentImage') or {}).get('thumbnailViewModel') or {})
        sources = ((img.get('image') or {}).get('sources') or [])
        if sources and str(sources[-1].get('url', '')).startswith('https://'):
            row['thumb'] = sources[-1]['url']
        for badge in _walk(img, 'thumbnailBadgeViewModel'):
            ms = duration_ms((badge or {}).get('text'))
            if ms:
                row['duration_ms'] = ms
                break
        out.append(row)
    return out


def duration_ms(text):
    """'15:14' / '1:02:03' → 毫秒；认不出返回 None。"""
    m = re.fullmatch(r'\s*(?:(\d+):)?(\d{1,2}):(\d{2})\s*', str(text or ''))
    if not m:
        return None
    h, mi, s = int(m.group(1) or 0), int(m.group(2)), int(m.group(3))
    return ((h * 60 + mi) * 60 + s) * 1000


def parse_watch_page(html):
    """视频页 → {published, description, duration_ms?}；没有发布时间返回 None。"""
    m = re.search(r'"publishDate":"([^"]+)"', html) or re.search(r'itemprop="datePublished" content="([^"]+)"', html)
    if m:
        published = m.group(1)
    else:
        # 机房 IP 常被要求「登录确认不是机器人」，页面没有 microformat，只剩 dateText（如 "Nov 14, 2026"，YouTube 按太平洋时间给日期）。
        # 只有日期没有时刻：取当天太平洋时间中午，卡片上的时刻因此是近似值（日期是真的）。
        d = re.search(r'"dateText":\{"simpleText":"(?:[^"]*?\s)?([A-Z][a-z]{2} \d{1,2}, \d{4})"', html)
        if not d:
            return None
        try:
            day = datetime.strptime(d.group(1), '%b %d, %Y')
        except ValueError:
            return None
        published = day.strftime('%Y-%m-%dT12:00:00-08:00')
    out = {'published': published, 'description': ''}
    d = re.search(r'"shortDescription":"((?:[^"\\]|\\.)*)"', html)
    if d:
        try:
            out['description'] = json.loads('"' + d.group(1) + '"')
        except ValueError:
            pass
    n = re.search(r'"lengthSeconds":"(\d+)"', html)
    if n:
        out['duration_ms'] = int(n.group(1)) * 1000
    return out


# ---------- 条目 ----------

def _item(platform, account, row, fetched_at):
    moment = parse_time(row.get('published'))
    if moment is None:
        return None, None
    vid = row['video_id']
    sid = source_id(platform['id'], account['handle'])
    desc = normalize_text(row.get('description') or '')
    thumb = THUMB.format(vid)
    media = {'type': 'youtube', 'url': EMBED.format(vid), 'preview_url': thumb}
    if row.get('duration_ms'):
        media['duration_ms'] = row['duration_ms']
    item = {
        'id': f'{sid}:{vid}',
        'kind': 'post',
        'channel': None,
        'source_id': sid,
        'source_name': account['name'],
        'title': row.get('title') or '',
        'summary': summary_of(desc),
        'body': clip(desc, BODY_CHARS),
        'url': WATCH.format(vid),
        'image': {'url': thumb, 'width': 480, 'height': 360},
        'published_at': iso(moment),
        'fetched_at': fetched_at,
        'lang': detect_lang(row.get('title') or '', desc[:800]),
        'blogger': {
            'platform': platform['id'],
            'handle': account['handle'],
            'display_name': account['name'],
            'media': [media],
            'quote': None,
        },
    }
    if isinstance(row.get('views'), int):
        item['blogger']['metrics'] = {'view': row['views']}
    return moment, item


def channel_posts(http, platform, account, fetched_at, limit=10, cache=None, sleep=None):
    """返回 (条目列表, 用到的路子 'rss'|'page')；两条路都失败抛 FeedError。cache: {video_id: watch 页解析结果}。"""
    cid = account['handle']
    cache = cache if cache is not None else {}
    rows, via, last = None, None, FeedError('network')
    for attempt in range(2):
        if attempt and sleep:
            sleep(RETRY_PAUSE)
        try:
            rows = parse_feed(http(FEED.format(cid)))
            via = 'rss'
            break
        except FeedError as exc:
            last = exc
    if rows is None:
        try:
            listed = parse_channel_page(http(VIDEOS.format(cid)).decode('utf-8', 'replace'))
        except FeedError as exc:
            raise FeedError(f'rss_{last.code}+page_{exc.code}') from None
        if not listed:
            raise FeedError(f'rss_{last.code}+page_unparsed')
        rows, budget = [], WATCH_BUDGET
        for row in listed[:limit]:
            got = cache.get(row['video_id'])
            if got is None and budget > 0:
                budget -= 1
                try:
                    got = parse_watch_page(http(WATCH.format(row['video_id'])).decode('utf-8', 'replace'))
                except FeedError:
                    got = None
                if got:
                    cache[row['video_id']] = got
            if got:
                rows.append(dict(row, published=got['published'], description=got.get('description', ''),
                                 **({'duration_ms': got['duration_ms']} if got.get('duration_ms') and not row.get('duration_ms') else {})))
        via = 'page'
    out = []
    for row in rows:
        moment, item = _item(platform, account, row, fetched_at)
        if item:
            out.append((moment, item))
    out.sort(key=lambda pair: pair[0], reverse=True)
    return [item for _, item in out[:limit]], via


def load_cache(path):
    try:
        data = json.loads(Path(path).read_text(encoding='utf-8'))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def save_cache(path, cache, keep=600):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    items = list(cache.items())[-keep:]
    tmp = path.with_name(path.name + '.tmp')
    tmp.write_text(json.dumps(dict(items), ensure_ascii=False), encoding='utf-8')
    tmp.replace(path)
