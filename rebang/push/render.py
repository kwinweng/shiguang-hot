"""把挑出的条目渲染成可直接发私聊的纯文本稿。不编摘要、不编链接。"""
from urllib.parse import quote

from rebang.contract import load_bloggers, load_channels

from .timeutil import BEIJING

EMPTY_MESSAGE = '过去 24 小时没有新的重点'
LOGIN_EXPIRED = 'login_expired'
# 与方案里的提醒措辞对齐：微信读书是公众号的登录方式。
REMINDER_NAMES = {'weibo': '微博', 'wechat': '微信读书'}


def channel_names():
    return {channel['slug']: channel['name'] for channel in load_channels()['channels']}


def display_text(item):
    """非中文且已译：用译文标题和摘要；没有摘要就不编。"""
    translation = item.get('translation') if item.get('translated') else None
    if isinstance(translation, dict):
        title = (translation.get('title') or item.get('title') or '').strip()
        summary = (translation.get('summary') or '').strip()
    else:
        title = (item.get('title') or '').strip()
        summary = (item.get('summary') or '').strip()
    return title, summary


def item_url(item, base_url=''):
    item_id = quote(item.get('id') or '', safe='')
    base = (base_url or '').rstrip('/')
    fragment = f'#/item/{item_id}'
    return f'{base}{fragment}' if base else fragment


def login_reminders(platforms):
    """同一平台只提醒一次；只针对 login_expired，不管 not_configured / error。"""
    catalog = {row['id']: row.get('name') or row['id'] for row in load_bloggers()['platforms']}
    seen = set()
    lines = []
    for row in platforms or []:
        if not isinstance(row, dict) or row.get('status') != LOGIN_EXPIRED:
            continue
        platform_id = row.get('id')
        if not platform_id or platform_id in seen:
            continue
        seen.add(platform_id)
        name = REMINDER_NAMES.get(platform_id) or row.get('name') or catalog.get(platform_id) or platform_id
        lines.append(f'{name}登录已失效，待重新登录。')
    return lines


def render_brief(items, now, base_url='', platforms=None):
    local = now.astimezone(BEIJING)
    header = f'今日重点 · {local.month}月{local.day}日'
    names = channel_names()
    blocks = [header, '']
    if not items:
        blocks.append(EMPTY_MESSAGE)
    else:
        for index, item in enumerate(items, 1):
            title, summary = display_text(item)
            channel = names.get(item.get('channel'), '')
            heading = f'【{channel}】{title}' if channel and title else (title or '无标题')
            blocks.append(f'{index}. {heading}')
            if summary:
                blocks.append(summary)
            blocks.append(item_url(item, base_url))
            if index < len(items):
                blocks.append('')
    reminders = login_reminders(platforms)
    if reminders:
        blocks.append('')
        blocks.extend(reminders)
    return '\n'.join(blocks) + '\n'
