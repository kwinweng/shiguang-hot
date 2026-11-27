"""frontend-v11 测试用的合成条目（契约格式，全部是假内容，只用于单测/浏览器测）。"""
from datetime import datetime, timedelta

from rebang.contract import load_bloggers, load_channels
from rebang.site.builder import BEIJING

NOW = datetime(2026, 11, 15, 20, 0, tzinfo=BEIJING)
TG = {'current': 'tnews365', 'world': 'freechinese', 'finance': 'FinanceNewsDaily', 'tech-ai': 'zaihuapd',
      'digital': 'CE_Observe', 'tools': 'yxzbp'}


def news(source, channel, n, *, minutes=0, image=None, summary='合成摘要，测试用。', **extra):
    item = {'id': f'{source}:{n}', 'kind': 'news', 'channel': channel, 'source_id': source, 'source_name': source,
            'title': f'{channel} 合成标题 {n}', 'summary': summary, 'body': f'{channel} 合成正文 {n}',
            'url': f'https://example.com/{source}/{n}', 'image': image,
            'published_at': (NOW - timedelta(minutes=minutes)).isoformat(), 'lang': 'zh', 'translated': False}
    item.update(extra)
    return item


def img(n, w=1200, h=675):
    return {'url': f'https://img.test/{n}.png', 'width': w, 'height': h}


def envelope(items, producer='test'):
    return {'schema': 'rebang.items/1', 'producer': producer, 'generated_at': NOW.isoformat(), 'items': items}


def site_items():
    """时事 70 条（7 张合格大图 → banner 5）、环球 1 条英文译文、财经 0 条图、其余各 3 条，外加 2 条博主帖。"""
    items = []
    for n in range(70):
        image = img(n) if n < 7 else (img(n, 200, 100) if n == 8 else None)
        item = news('tnews365', 'current', n, minutes=n * 5, image=image, summary='' if n == 9 else '合成摘要，测试用。')
        if n == 8:
            item.update(url='https://t.me/tnews365/8', tg={'media': [
                {'type': 'video', 'url': 'https://vid.test/v1.webm', 'preview_url': 'https://img.test/v1.png'},
                {'type': 'image', 'url': 'https://img.test/p0.png'},
            ], 'video_unavailable': True})
        items.append(item)
    items.append(news('bbc-world', 'world', 1, title='Synthetic headline', lang='en', translated=True,
                      translation={'title': '合成译文标题', 'summary': '合成译文摘要。', 'summary_source': '合成摘要，测试用。',
                                   'engine': 'test', 'label': '机器翻译'}))
    for slug in ('finance', 'tech-ai', 'digital', 'tools'):
        for n in range(3):
            items.append(news(TG[slug], slug, n, minutes=n))
    for n, handle in enumerate(('dotey', 'simonw')):
        items.append({'id': f'x-{handle}:{n}', 'kind': 'post', 'channel': None, 'source_id': f'x-{handle}', 'source_name': 'X',
                      'title': '', 'summary': f'合成推文 {n}', 'body': f'合成推文 {n}', 'url': f'https://x.com/{handle}/status/{n}',
                      'published_at': (NOW - timedelta(hours=n)).isoformat(), 'lang': 'zh', 'translated': False,
                      'blogger': {'platform': 'x', 'handle': handle, 'display_name': handle, 'avatar': None, 'verified': True,
                                  'metrics': {'reply': 1, 'repost': 2, 'like': 3}, 'media': MEDIA.get(handle, []), 'quote': None}})
    return items


# dotey 这条带图片 + 视频 + GIF（站内播放器测试用）；simonw 这条视频地址是坏的（兜底测试用）
MEDIA = {
    'dotey': [{'type': 'image', 'url': 'https://img.test/p0.png'},
              {'type': 'video', 'url': 'https://vid.test/v1.webm', 'preview_url': 'https://img.test/v1.png', 'duration_ms': 3000},
              {'type': 'gif', 'url': 'https://vid.test/g2.webm', 'preview_url': 'https://img.test/g2.png'}],
    'simonw': [{'type': 'video', 'url': 'https://vid.test/missing.webm', 'preview_url': 'https://img.test/v9.png'}],
}


def hotsearch():
    return {'schema': 'rebang.hotsearch/1', 'generated_at': NOW.isoformat(), 'providers': [
        {'id': 'baidu', 'name': '百度热搜', 'status': 'ok', 'fetched_at': NOW.isoformat(),
         'items': [{'rank': 1, 'title': '合成置顶', 'url': 'https://www.baidu.com/s?wd=a', 'pinned': True}] +
                  [{'rank': i, 'title': f'合成热搜 {i}', 'url': f'https://www.baidu.com/s?wd={i}', 'pinned': False, 'hot_score': 4900000 - i}
                   for i in range(2, 13)]},
        {'id': 'zhihu', 'name': '知乎热榜', 'status': 'error', 'fetched_at': NOW.isoformat(), 'error': 'http_403', 'items': []},
        {'id': 'bilibili', 'name': 'B 站热搜', 'status': 'empty', 'fetched_at': None, 'items': []}]}


def health_inputs():
    """Synthetic adapter results for the mobile health page and screenshot."""
    recent = (NOW - timedelta(hours=1)).isoformat()
    earlier = (NOW - timedelta(hours=53)).isoformat()
    news = [{'id': s['id'], 'status': 'ok', 'count': 14, 'fetched_at': recent}
            for c in load_channels()['channels'] for s in c['sources']]
    for row in news:
        if row['id'] == 'tnews365':
            row.update(collection_ok=False, last_ok_at=(NOW - timedelta(hours=29)).isoformat())
        if row['id'] == 'guardian-world':
            row['fetched_at'] = earlier
        if row['id'] == 'selfhst':  # 新加的源还没抓过一轮
            row.update(status='not_fetched', count=0, fetched_at=None)
    platforms = []
    for platform in load_bloggers()['platforms']:
        platform_id = platform['id']
        accounts = [{'handle': a['handle'], 'status': 'ok', 'count': 4, 'last_ok_at': recent}
                    for a in platform['accounts']]
        if platform_id == 'weibo':
            for account in accounts:
                account.update(status='login_expired', error='weibo_cookie_expired', last_ok_at=earlier)
        if platform_id == 'x':
            dump_at = (NOW - timedelta(hours=56)).isoformat()
            for account in accounts:
                account.update(status='error', error='x_dump_stale', dump_at=dump_at, last_ok_at=earlier)
        platforms.append({'id': platform_id, 'accounts': accounts})
    return news, platforms
