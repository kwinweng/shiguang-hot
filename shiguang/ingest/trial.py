"""Isolated trial collection. Never writes publication tables or downloads images."""
import json
import re
import sqlite3
import time
import xml.etree.ElementTree as ET
from collections import Counter
from datetime import datetime, timezone
from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup
from shiguang.config import ROOT
from shiguang.ingest import http, scheduler, telegram, web


def prepare(data):
    categories = {}
    for category in data['categories']:
        key = category['id']
        if (not re.fullmatch(r'[a-z0-9-]+', key) or key in categories
                or category['section'] not in ('好玩', '好买') or not category['name']):
            raise ValueError('试跑分类非法或重复')
        categories[key] = category
    if len(categories) > 16 or any(n > 8 for n in Counter(c['section'] for c in categories.values()).values()):
        raise ValueError('试跑分类超过上限')
    ids = set()
    for source in data['sources']:
        key = source['id']
        if not re.fullmatch(r'[A-Za-z0-9_-]+', key) or key in ids:
            raise ValueError('试跑来源 id 非法或重复')
        ids.add(key)
        category = categories.get(source['category'])
        if not category or category['section'] != source['section'] or not source['name']:
            raise ValueError('试跑来源分类不存在或栏目不符')
        scheduler.endpoint(source['url'])
        if source['fetch'] not in ('rss', 'page', 'telegram'):
            raise ValueError('试跑抓取方式非法')
        if source['fetch'] == 'page' and source.get('parser') not in ('ucca', 'douban_events'):
            raise ValueError('试跑网页解析器非法')
        if source['fetch'] == 'telegram':
            channel = source.get('channel', '')
            if not re.fullmatch(r'[A-Za-z0-9_]+', channel) or source['url'] != f'https://t.me/s/{channel}':
                raise ValueError('试跑 Telegram 入口与 channel 不符')
    return data


def load(path=None):
    return prepare(json.loads((path or ROOT / 'trial-sources.json').read_text()))


def ensure_table(db):
    db.execute('''create table if not exists trial_item(
        source_id text not null, section text not null, category text not null,
        url text primary key, title text not null, summary text not null,
        image_url text, published_at text, fetched_at text not null)''')


def parse_page(body, source):
    soup = BeautifulSoup(body, 'html.parser')
    pattern = r'^/exhibition/[^/]+/?$' if source['parser'] == 'ucca' else r'^/event/\d+/?$'
    items = {}
    for link in soup.select('a[href]'):
        url = urljoin(source['url'], link['href'])
        parts = urlsplit(url)
        if source['parser'] == 'douban_events':
            host = parts.hostname or ''
            valid_host = host == 'douban.com' or host.endswith('.douban.com')
        else:
            valid_host = parts.hostname == urlsplit(source['url']).hostname
        if not valid_host or not re.fullmatch(pattern, parts.path):
            continue
        image = link.find('img')
        title = link.get_text(' ', strip=True) or link.get('title') or (image.get('alt') if image else '')
        if source['parser'] == 'douban_events':
            title = (title or '').strip()
        if not title:
            continue
        canonical = parts._replace(query='', fragment='').geturl()
        if source['parser'] == 'douban_events':
            canonical = 'https://www.douban.com' + parts.path.rstrip('/') + '/'
        previous = items.get(canonical, {})
        images = ([urljoin(url, image['src'])] if source['parser'] == 'ucca' and image and image.get('src')
                  else previous.get('images', []))
        container = link.find_parent(['li', 'article'])
        details = container.get_text(' ', strip=True) if container else ''
        items[canonical] = dict(url=canonical, title=title, body=details[:500], ts=None, images=images)
    if not items:
        raise http.FetchFailure('invalid_content')
    return list(items.values())


def parse_telegram(body, source):
    soup = BeautifulSoup(body, 'html.parser')
    items = []
    for message in soup.select('div.tgme_widget_message[data-post]'):
        post = message['data-post']
        if not re.fullmatch(re.escape(source['channel']) + r'/\d+', post):
            continue
        node = message.select_one('.tgme_widget_message_text')
        text = telegram.extract(node) if node else ''
        if source['id'] == 'Apps_Share' and node:
            # Download labels and slugs can contain the name missing from the tag-only heading.
            for anchor in node.select('a[href]'):
                if (urlsplit(anchor['href']).hostname or '').lower() == 'apps.apple.com':
                    text += '\n' + anchor['href']
        images = telegram.image_urls(message)
        moment = message.select_one('time[datetime]')
        if not text and not images:
            continue
        items.append(dict(url='https://t.me/' + post, title=text.split('\n')[0][:200] or '[图片]',
                          body=text, images=images, ts=web._when(moment['datetime']) if moment else None))
    if not items:
        raise http.FetchFailure('invalid_content')
    return items


def fetch(db, source, batch):
    kind = 'trial-' + source['fetch']
    try:
        response = batch.get(kind, source['url'])
        if source['fetch'] == 'rss':
            items = web.parse(response.body)
        elif source['fetch'] == 'telegram':
            items = parse_telegram(response.body, source)
        else:
            items = parse_page(response.body, source)
        for item in items:
            url = item['url']
            if not url or urlsplit(url).scheme not in ('https', 'http'):
                continue
            published = scheduler.stamp(item['ts']) if item['ts'] else None
            images = item['images']
            image = urljoin(url, images[0]) if images else None
            if image and urlsplit(image).scheme not in ('https', 'http'):
                image = None
            cursor = db.execute('insert or ignore into trial_item values(?,?,?,?,?,?,?,?,?)',
                                (source['id'], source['section'], source['category'], url, item['title'],
                                 item['body'][:500], image, published, scheduler.stamp(batch.now)))
            batch.new += cursor.rowcount
            if not cursor.rowcount:
                db.execute('update trial_item set title=?,summary=?,image_url=?,published_at=? where url=?',
                           (item['title'], item['body'][:500], image, published, url))
        db.commit()
        batch.progress += 1
    except (ET.ParseError, http.FetchFailure, ValueError) as error:
        batch.resource_error(kind, source['url'], error)


def run(db, sources, *, clock=None):
    """Caller holds the shared collection lock; trials get separate quota identities."""
    scheduler.ensure_schema(db)
    ensure_table(db)
    db.commit()
    clock = clock or (lambda: datetime.now(timezone.utc))
    for source in sources:
        batch, reason = scheduler.claim(db, 'trial:' + source['id'], clock())
        if reason:
            state = db.execute('select status,next_eligible_at,last_attempt_at,last_success_at '
                               'from source_fetch_state where source_id=?', ('trial:' + source['id'],)).fetchone()
            scheduler.emit(source, result='skip', skip_reason=reason, source_status=state[0],
                           next_eligible_at=state[1], last_checked=state[2], last_success=state[3],
                           requests=0, cache_hits=0, new=0)
            continue
        time.sleep(1)  # Also separates the first trial request from the regular collector.
        batch.clock = clock
        try:
            fetch(db, source, batch)
        except sqlite3.Error:
            raise
        except OSError as error:
            batch.note(error)
        scheduler.emit(source, **batch.finish(clock()))
