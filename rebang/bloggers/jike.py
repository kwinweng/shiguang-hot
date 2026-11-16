"""即刻：公共 RSSHub 实例的 /jike/user/<UUID> 路由（不登录、不带任何 Cookie）→ 博主帖子条目。

RSSHub 的即刻路由把「发布了: / 转发了: 」和截断的正文拼成标题，正文在 description 里；
转发的原帖放在 <div class="rsshub-quote">转发 <a>@名字</a>: 原文</div>。
这里把标题去掉（即刻帖子没有标题），频道自己的话进正文，被转发的原帖进 blogger.quote。
多个公共实例按顺序轮换、失败换下一个（实例是第三方的，可能限流或下线），全部失败才算这个账号失败。
"""
import re

from bs4 import BeautifulSoup

from .common import (BODY_CHARS, clip, detect_lang, html_images, html_to_text, iso, native_id, parse_time,
                     source_id, summary_of)
from .feed import FeedError, parse_feed

_TITLE_PREFIX = re.compile(r'^(?:发布了|转发了)\s*[:：]\s*')
_PLACEHOLDER = '一条动态'


def _split_quote(html):
    """description → (自己的话 html, 转发原帖 {handle, display_name, text, url?} 或 None, 原帖里的图)"""
    soup = BeautifulSoup(html or '', 'html.parser')
    box = soup.select_one('div.rsshub-quote')
    if box is None:
        return str(soup), None, []
    images = html_images(str(box), 'https://m.okjike.com/')
    link = box.find('a')
    name, url = '', ''
    if link is not None:
        name = link.get_text('', strip=True).lstrip('@')
        href = link.get('href') or ''
        url = href if href.startswith('https://') else ''
        link.decompose()
    text = html_to_text(str(box))
    text = re.sub(r'^转发\s*[:：]?\s*', '', text).lstrip(':： ').strip()
    box.decompose()
    quote = None
    if name and text:
        handle = url.rstrip('/').rsplit('/', 1)[-1] if url else name
        quote = {'handle': handle, 'display_name': name, 'text': clip(text, 1500)}
        if url:
            quote['url'] = url
    return str(soup), quote, images


def _avatar(body):
    """RSSHub 把即刻用户头像放在 <channel><image><url>；只收 https。"""
    import xml.etree.ElementTree as ET
    try:
        url = (ET.fromstring(body).findtext('channel/image/url') or '').strip()
    except ET.ParseError:
        return None
    return url if url.startswith('https://') else None


def jike_posts(body, platform, account, fetched_at, limit=10):
    handle = account['handle']
    sid = source_id(platform['id'], handle)
    out = []
    avatar = _avatar(body)
    for entry in parse_feed(body):
        moment = parse_time(entry['published'])
        url = entry['url'] if entry['url'].startswith(('http://', 'https://')) else ''
        if moment is None:
            continue
        own_html, quote, quote_images = _split_quote(entry['html'] or entry['summary_html'])
        text = html_to_text(own_html)
        images = html_images(own_html, url or 'https://m.okjike.com/') or quote_images
        if not text and quote is None:
            text = _TITLE_PREFIX.sub('', entry['title'] or '').strip()
            if text == _PLACEHOLDER and images:   # 只有图：RSSHub 补的占位标题不当正文
                text = ''
        if not text and quote is None and not images:
            continue
        item = {
            'id': f'{sid}:{native_id(entry["guid"], url)}',
            'kind': 'post',
            'channel': None,
            'source_id': sid,
            'source_name': account['name'],
            'title': '',
            'summary': summary_of(text or (quote or {}).get('text', '')),
            'body': clip(text, BODY_CHARS),
            'url': url,
            'image': dict(images[0]) if images else None,
            'published_at': iso(moment),
            'fetched_at': fetched_at,
            'lang': detect_lang(text, (quote or {}).get('text', '')[:500]),
            'blogger': {
                'platform': platform['id'],
                'handle': handle,
                'display_name': account['name'],
                'media': [{'type': 'image', 'url': m['url']} for m in images],
                'quote': quote,
            },
        }
        if avatar:
            item['blogger']['avatar'] = avatar
        out.append((moment, item))
    out.sort(key=lambda pair: pair[0], reverse=True)
    return [item for _, item in out[:limit]]


def roots_of(value, platform):
    """--jike-rsshub / REBANG_JIKE_RSSHUB 可写逗号分隔的多个根地址；没写就用 bloggers.json 里的公共实例清单。"""
    if value:
        roots = [r.strip().rstrip('/') for r in str(value).split(',') if r.strip()]
    else:
        roots = [r.rstrip('/') for r in platform.get('rsshub_mirrors') or []]
    return [r for r in roots if r.startswith(('http://', 'https://'))]


def fetch_account(http, roots, account, start=0):
    """从第 start 个实例开始轮流试，返回 (feed 字节, 用到的根地址)；全部失败抛最后一个 FeedError。"""
    last = FeedError('no_mirror')
    order = roots[start % len(roots):] + roots[:start % len(roots)] if roots else []
    for root in order:
        try:
            body = http(f'{root}/jike/user/{account["handle"]}')
            parse_feed(body)          # 实例返回了错误页（200 + HTML）就换下一个
            return body, root
        except FeedError as exc:
            last = exc
    raise last
