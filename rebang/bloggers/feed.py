"""RSS 2.0 / Atom 订阅源 → 博主帖子条目。博客、Wechat2RSS（夕小瑶）、自建 RSSHub（即刻）共用。"""
import xml.etree.ElementTree as ET

from .common import (BODY_CHARS, clip, detect_lang, html_images, html_to_text, iso, native_id,
                     parse_time, source_id, summary_of)

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
        body_text = html_to_text(html)
        summary_text = html_to_text(entry['summary_html']) if entry['summary_html'] else body_text
        images = html_images(html, url or account.get('home', ''))
        if entry['enclosure'] and entry['enclosure'] not in [m['url'] for m in images]:
            images.insert(0, {'url': entry['enclosure']})
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
                'media': [{'type': 'image', 'url': m['url']} for m in images],
                'quote': None,
            },
        }
        out.append((moment, item))
    out.sort(key=lambda pair: pair[0], reverse=True)
    return [item for _, item in out[:limit]]
