"""微博：只做 weibo-crawler（dataabc/weibo-crawler）的调用框架与输出映射。

- Cookie 默认路径：``~/.config/rebang/weibo-cookie.txt``（可用 ``REBANG_WEIBO_COOKIE`` / ``--weibo-cookie-file`` 改）。
  仓库外、建议 0600。这里只检查“文件是否存在”，不打开、不读取、不打印内容。没有文件 → not_configured，不抓。
- 文件格式：一行浏览器 Cookie 头（weibo-crawler 的 cookie 文件），例如 ``SUB=...; SUBP=...; SSOLoginState=...; ALF=...``，
  不要写成 JSON，不要加 ``Cookie:`` 前缀。从已登录微博的小号浏览器里复制即可。
- 输出默认 ``var/rebang/weibo-crawler/``（``REBANG_WEIBO_OUTPUT`` / ``--weibo-output``）。刷新脚本在 Cookie 文件出现且本机装了 weibo-crawler 时才去跑它；没装则保持 weibo_crawler_output_missing。
- 映射按 weibo-crawler 输出的 {"user": {...}, "weibo": [...]} 结构，字段名接入真实输出时需再复核。
"""
import json
import os
from datetime import datetime
from pathlib import Path

from .common import BJT, BODY_CHARS, clip, iso, normalize_text, source_id, summary_of, html_to_text

DEFAULT_COOKIE = Path(os.environ.get("REBANG_WEIBO_COOKIE") or Path.home() / ".config" / "rebang" / "weibo-cookie.txt")
DEFAULT_OUTPUT = Path(__file__).resolve().parents[2] / "var" / "rebang" / "weibo-crawler"


def cookie_configured(cookie_file):
    """只看路径是否指向一个存在的普通文件；不读内容。"""
    return bool(cookie_file) and os.path.isfile(cookie_file)


def _time(value):
    if not value:
        return None
    for fmt in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%dT%H:%M:%S', '%Y-%m-%d %H:%M', '%Y-%m-%d'):
        try:
            return datetime.strptime(str(value).strip(), fmt).replace(tzinfo=BJT)
        except ValueError:
            continue
    return None


def _int(value):
    if isinstance(value, int) and value >= 0:
        return value
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    return None


def map_crawler_json(data, platform, account, fetched_at, limit=10):
    user = data.get('user') or {}
    sid = source_id(platform['id'], account['handle'])
    items = []
    for w in data.get('weibo') or []:
        moment = _time(w.get('full_created_at') or w.get('created_at'))
        text = normalize_text(html_to_text(w.get('text') or '')) if '<' in (w.get('text') or '') else normalize_text(w.get('text') or '')
        if not moment or not (text or w.get('pics')):
            continue
        pics = w.get('pics') or []
        if isinstance(pics, str):
            pics = [p for p in pics.split(',') if p.strip()]
        media = [{'type': 'image', 'url': p.strip()} for p in pics if p.strip().startswith('http')]
        if isinstance(w.get('video_url'), str) and w['video_url'].startswith('http'):
            media.append({'type': 'video', 'url': w['video_url'].split(';')[0]})
        metrics = {k: v for k, v in (('like', _int(w.get('attitudes_count'))), ('reply', _int(w.get('comments_count'))),
                                     ('repost', _int(w.get('reposts_count')))) if v is not None}
        bid = w.get('bid') or w.get('id')
        uid = str(w.get('user_id') or user.get('id') or account['handle'])
        blogger = {'platform': platform['id'], 'handle': account['handle'],
                   'display_name': w.get('screen_name') or user.get('screen_name') or account['name'],
                   'media': media, 'quote': None}
        avatar = user.get('avatar_hd') or user.get('profile_image_url')
        if isinstance(avatar, str) and avatar.startswith('http'):
            blogger['avatar'] = avatar
        if metrics:
            blogger['metrics'] = metrics
        first = next((m for m in media if m['type'] == 'image'), None)
        items.append((moment, {
            'id': f'{sid}:{w.get("id") or bid}', 'kind': 'post', 'channel': None,
            'source_id': sid, 'source_name': account['name'], 'title': '',
            'summary': summary_of(text), 'body': clip(text, BODY_CHARS),
            'url': f'https://weibo.com/{uid}/{bid}' if bid else '',
            'image': {'url': first['url']} if first else None,
            'published_at': iso(moment), 'fetched_at': fetched_at, 'lang': 'zh', 'blogger': blogger,
        }))
    items.sort(key=lambda pair: pair[0], reverse=True)
    return [it for _, it in items[:limit]]


def find_output(output_dir, account):
    """weibo-crawler 默认把结果写到 weibo/<昵称或UID>/<UID>.json；按 UID/handle 查找。"""
    if not output_dir:
        return None
    root = Path(output_dir)
    for pattern in (f'**/{account["handle"]}.json', f'**/*{account["handle"]}*.json'):
        hits = sorted(root.glob(pattern))
        if hits:
            return hits[-1]
    return None


def load_output(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))
