"""RSS 2.0 / Atom 订阅源 → 博主帖子条目。博客、Wechat2RSS（夕小瑶）、自建 RSSHub（即刻）共用。"""
import re
import xml.etree.ElementTree as ET

from .common import (BODY_CHARS, blocks_text, clip, detect_lang, html_blocks, html_images, html_to_text, iso,
                     native_id, parse_time, source_id, summary_of, unwrap_image_url)

ATOM = '{http://www.w3.org/2005/Atom}'
CONTENT = '{http://purl.org/rss/1.0/modules/content/}encoded'
MEDIA = '{http://search.yahoo.com/mrss/}'


class FeedError(Exception):
    def __init__(self, code):
        super().__init__(code)
        self.code = code


def _text(el):
    return (el.text or '').strip() if el is not None else ''


def parse_feed(body):
    """返回 [{guid, title, url, published, html, summary_html, enclosure}]；不是订阅源抛 FeedError。"""
    try:
        root = ET.fromstring(body)
    except ET.ParseError:
        raise FeedError('not_xml') from None
    entries = []
    if root.tag == ATOM + 'feed':
        for e in root.findall(ATOM + 'entry'):
            link = ''
            for l in e.findall(ATOM + 'link'):
                if l.get('rel', 'alternate') == 'alternate' and l.get('href'):
                    link = l.get('href')
                    break
            entries.append({
                'guid': _text(e.find(ATOM + 'id')),
                'title': html_to_text(_text(e.find(ATOM + 'title'))),
                'url': link,
                'published': _text(e.find(ATOM + 'published')) or _text(e.find(ATOM + 'updated')),
                'html': _text(e.find(ATOM + 'content')),
                'summary_html': _text(e.find(ATOM + 'summary')),
                'enclosure': None,
            })
        return entries
    channel = root.find('channel')
    if root.tag != 'rss' or channel is None:
        raise FeedError('not_feed')
    for it in channel.findall('item'):
        enclosure = None
        enc = it.find('enclosure')
        if enc is not None and (enc.get('type') or '').startswith('image/') and enc.get('url'):
            enclosure = enc.get('url')
        thumb = it.find(MEDIA + 'thumbnail')
        if thumb is None:
            thumb = it.find(MEDIA + 'content')
        if enclosure is None and thumb is not None and thumb.get('url') and (thumb.get('medium', 'image') == 'image'):
            enclosure = thumb.get('url')
        entries.append({
            'guid': _text(it.find('guid')),
            'title': html_to_text(_text(it.find('title'))),
            'url': _text(it.find('link')),
            'published': _text(it.find('pubDate')) or _text(it.find('{http://purl.org/dc/elements/1.1/}date')),
            'html': _text(it.find(CONTENT)),
            'summary_html': _text(it.find('description')),
            'enclosure': enclosure,
        })
    return entries


_WX_HEAD = re.compile(r'^(?:原创|\d{4}-\d{2}-\d{2}(?: \d{2}:\d{2})?|.{1,12})$')


def _strip_wechat_header(text):
    """公众号正文开头的「原创 / 作者 / 日期 / 属地」短行不进摘要。只删开头连续的短行，正文不动。"""
    lines = text.split('\n')
    index = 0
    while index < len(lines) and index < 8 and (not lines[index].strip() or _WX_HEAD.match(lines[index].strip())):
        index += 1
    rest = '\n'.join(lines[index:]).strip()
    return rest or text


def feed_posts(body, platform, account, fetched_at, limit=10):
    """订阅源正文 → 条目列表（新到旧，最多 limit 条）。没有可解析时间的条目丢弃，不编时间。"""
    handle = account['handle']
    sid = source_id(platform['id'], handle)
    out = []
    for entry in parse_feed(body):
        moment = parse_time(entry['published'])
        url = entry['url'] if entry['url'].startswith(('http://', 'https://')) else ''
        if moment is None or not (entry['title'] or entry['html'] or entry['summary_html']):
            continue
        html = entry['html'] or entry['summary_html']
        wechat = platform['id'] == 'wechat'
        # 文章页按原文顺序渲染（段落/标题/图片/引用/列表），不再「整段纯文本 + 前 4 张图拼九宫格」
        blocks = html_blocks(html, url or account.get('home', ''), wechat=wechat)
        body_text = blocks_text(blocks) if blocks else html_to_text(html)
        if wechat and not blocks:
            body_text = _strip_wechat_header(body_text)
        summary_text = html_to_text(entry['summary_html']) if entry['summary_html'] and platform['id'] != 'wechat' else body_text
        images = html_images(html, url or account.get('home', ''))
        if entry['enclosure'] and entry['enclosure'] not in [m['url'] for m in images]:
            images.insert(0, {'url': entry['enclosure']})
        if wechat:
            images = [dict(m, url=unwrap_image_url(m['url'])) for m in images]
        item = {
            'id': f'{sid}:{native_id(entry["guid"], url)}',
            'kind': 'post',
            'channel': None,
            'source_id': sid,
            'source_name': account['name'],
            'title': entry['title'],
            'summary': summary_of(summary_text),
            'body': clip(body_text, BODY_CHARS),
            'url': url,
            'image': dict(images[0]) if images else None,
            'published_at': iso(moment),
            'fetched_at': fetched_at,
            'lang': detect_lang(entry['title'], summary_text[:1500]),
            'blogger': {
                'platform': platform['id'],
                'handle': handle,
                'display_name': account['name'],
                # 公众号图只走本地副本（blocks / image_local），不放外链九宫格
                'media': [] if wechat and blocks else [{'type': 'image', 'url': m['url']} for m in images],
                'quote': None,
            },
        }
        if blocks and (len(blocks) > 1 or blocks[0]['type'] != 'p'):
            item['blocks'] = blocks
        out.append((moment, item))
    out.sort(key=lambda pair: pair[0], reverse=True)
    return [item for _, item in out[:limit]]
