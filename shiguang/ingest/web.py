"""Feed sources (type "feed"): RSS 2.0 and Atom, which covers blogs, news sites and YouTube channels
(https://www.youtube.com/feeds/videos.xml?channel_id=…).

Entries are kept in tg.db (table `entry`) beside the Telegram messages, so they survive between
hourly runs; each entry's first image is cached under media/<source>/ like Telegram photos.
"""
import hashlib, json, os, re, subprocess, sys
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from email.utils import parsedate_to_datetime
from bs4 import BeautifulSoup
from shiguang.model import BEIJING
from shiguang.ingest import telegram

NS = {'atom': 'http://www.w3.org/2005/Atom', 'media': 'http://search.yahoo.com/mrss/'}
KEEP = 50   # newest entries taken from one fetch


def _text(markup):
    """Plain text of an HTML fragment, whitespace collapsed, capped."""
    text = BeautifulSoup(markup or '', 'html.parser').get_text(' ')
    return re.sub(r'\s+', ' ', text).strip()[:2000]


def _when(value):
    value = (value or '').strip()
    if not value:
        return None
    try:
        moment = datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError:
        try:
            moment = parsedate_to_datetime(value)
        except (TypeError, ValueError):
            return None
    return (moment if moment.tzinfo else moment.replace(tzinfo=BEIJING)).astimezone(BEIJING)


def _first_img(markup):
    tag = BeautifulSoup(markup or '', 'html.parser').find('img', src=True)
    return tag['src'] if tag else None


def parse(xml):
    """Entries of an RSS or Atom document: dict(id, ts, title, body, url, images), newest first."""
    root = ET.fromstring(xml)
    entries = []
    if root.tag == '{%s}feed' % NS['atom']:
        for e in root.findall('atom:entry', NS):
            link = next((l.get('href') for l in e.findall('atom:link', NS) if l.get('rel', 'alternate') == 'alternate'), '')
            group = e.find('media:group', NS)
            summary = e.findtext('atom:summary', '', NS) or e.findtext('atom:content', '', NS)
            if group is not None and not summary:
                summary = group.findtext('media:description', '', NS)
            thumb = (group.find('media:thumbnail', NS) if group is not None else None)
            image = thumb.get('url') if thumb is not None else _first_img(summary)
            entries.append(dict(id=e.findtext('atom:id', '', NS) or link, url=link,
                                ts=_when(e.findtext('atom:published', '', NS) or e.findtext('atom:updated', '', NS)),
                                title=_text(e.findtext('atom:title', '', NS)), body=_text(summary),
                                images=[image] if image else []))
    else:
        for e in root.iter('item'):
            description = e.findtext('description', '')
            enclosure = next((x.get('url') for x in e.findall('enclosure') if (x.get('type') or '').startswith('image/')), None)
            media = e.find('media:content', NS) if e.find('media:content', NS) is not None else e.find('media:thumbnail', NS)
            image = enclosure or (media.get('url') if media is not None else None) or _first_img(description)
            link = e.findtext('link', '').strip()
            entries.append(dict(id=e.findtext('guid', '').strip() or link, url=link, ts=_when(e.findtext('pubDate', '')),
                                title=_text(e.findtext('title', '')), body=_text(description),
                                images=[image] if image else []))
    entries = [e for e in entries if e['ts'] and (e['title'] or e['body'])]
    return sorted(entries, key=lambda e: e['ts'], reverse=True)[:KEEP]


def ensure_table(db):
    db.execute("create table if not exists entry(source text, id text, ts text, title text, body text, url text,"
               " images text not null default '[]', primary key(source, id))")


def fetch(db, sources, now):
    """Fetch every feed source and store new entries; one broken feed never stops the rest."""
    ensure_table(db)
    floor = now - timedelta(days=telegram.MEDIA_DAYS)
    for s in sources:
        try:
            xml = subprocess.run(['curl', '--fail', '-sL', '-m', '25', '-A', 'Mozilla/5.0', s['url']],
                                 capture_output=True, check=True).stdout
            new = 0
            for e in parse(xml):
                key = hashlib.sha1(e['id'].encode()).hexdigest()[:12]
                if db.execute('select 1 from entry where source=? and id=?', (s['id'], e['id'])).fetchone():
                    continue
                images = telegram.download_images(s['id'], key, [u for u in e['images'] if u.startswith('https://')]) if e['ts'] >= floor else []
                db.execute('insert into entry values(?,?,?,?,?,?,?)',
                           (s['id'], e['id'], e['ts'].isoformat(), e['title'], e['body'], e['url'], json.dumps(images)))
                new += 1
            print(s['id'], 'new', new, file=sys.stderr)
        except (subprocess.CalledProcessError, ET.ParseError) as ex:
            print(s['id'], 'feed error', str(ex)[:200], file=sys.stderr)


def entries(db):
    """Every stored entry, newest first, with image paths that exist."""
    if not db.execute("select 1 from sqlite_master where type='table' and name='entry'").fetchone():
        return []
    return [dict(source=source, id=i, ts=ts, title=title, body=body, url=url,
                 images=[p for p in json.loads(images) if os.path.isfile(os.path.join(telegram.D, p))])
            for source, i, ts, title, body, url, images in db.execute('select * from entry order by ts desc')]
