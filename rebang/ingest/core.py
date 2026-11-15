"""collect(now, fetch=…) → rebang.items/1 信封。各来源互不影响：一家失败只把自己标 error。"""
import contextlib
import hashlib
import json
import os
import re
import sqlite3
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from rebang.contract import ITEMS_SCHEMA, load_channels

ROOT = Path(__file__).resolve().parents[2]
BEIJING = ZoneInfo('Asia/Shanghai')
DEFAULT_CACHE = ROOT / 'var' / 'rebang' / 'cache' / 'ingest'
MEDIA_DAYS = 14          # 与 shiguang/ingest/telegram.py MEDIA_DAYS 一致：图片按条目时间保留 14 天
SUMMARY_CHARS = 300
PRODUCER = 'ingest'
FEED_LANG = 'en'         # 6 个官方订阅都是英文
MT = '机器翻译'


# ---------- 小工具 ----------

def _aware(moment):
    return moment if moment.tzinfo else moment.replace(tzinfo=BEIJING)


def _iso(moment):
    return _aware(moment).astimezone(BEIJING).isoformat(timespec='seconds')


def _parse_when(value, fallback_day=None):
    """'2026-11-14T08:13:18+08:00' / '2026-11-14 10:20' / '2026-11-14' → 北京时间 aware；都不行用 fallback_day 当天 00:00。"""
    for raw in (str(value or '').strip().replace('Z', '+00:00'), str(fallback_day or '').strip()):
        if not raw:
            continue
        try:
            return _aware(datetime.fromisoformat(raw)).astimezone(BEIJING)
        except ValueError:
            continue
    return None


def _plain(text, cap=None):
    text = re.sub(r'\s+', ' ', str(text or '')).strip()
    return text[:cap].rstrip() + '…' if cap and len(text) > cap else text


def _sha(value):
    return hashlib.sha1(value.encode('utf-8')).hexdigest()[:16]


def _norm_url(url):
    url = str(url or '').strip()
    url = re.sub(r'^http://', 'https://', url)
    url = re.sub(r'^https://t\.me/s/', 'https://t.me/', url)
    return url.split('#')[0].rstrip('/')


def _http_url(url):
    return url if re.match(r'https?://[^\s/]+', str(url or '')) else ''


def _image_size(path):
    try:
        from PIL import Image
        with Image.open(path) as im:
            return im.size
    except Exception:
        return None


def _local_image(path, published, now, root=None):
    """仓库/盒子本地图片（TG media 缓存、成品期刊目录图）。契约 image 只收 http(s)，本地图放 image_local。"""
    if published < now - timedelta(days=MEDIA_DAYS) or not path or not os.path.isfile(path):
        return None
    size = _image_size(path)
    if not size:
        return None
    out = {'path': str(path), 'width': size[0], 'height': size[1]}
    if root:
        out['rel'] = os.path.relpath(path, root)
    return out


def source_table():
    """来源 id → (频道 slug, 来源配置)，顺序同 channels.json。"""
    table = {}
    for channel in sorted(load_channels()['channels'], key=lambda c: c['order']):
        for source in channel['sources']:
            table[source['id']] = (channel['slug'], source)
    return table


def _news(source, channel, native_id, title, summary, url, published, now, lang='zh', body=None, image=None,
          image_local=None):
    item = {'id': f"{source['id']}:{native_id}", 'kind': 'news', 'channel': channel, 'source_id': source['id'],
            'source_name': source['name'], 'title': title, 'summary': summary, 'url': _http_url(url),
            'image': image, 'published_at': _iso(published), 'fetched_at': _iso(now), 'lang': lang,
            'translated': False}
    if body:
        item['body'] = body
    if image_local:
        item['image_local'] = image_local
    return item


def _status(source, channel, status, count=0, error=None, fetched_at=None):
    out = {'id': source['id'], 'name': source['name'], 'type': source['type'], 'channel': channel,
           'status': status, 'count': count}
    if error:
        out['error'] = error
    if fetched_at:
        out['fetched_at'] = fetched_at
    return out


# ---------- Telegram（只读 tg.db） ----------

_SENTENCE = re.compile(r'[。！？!?]')


def split_tg_text(text):
    """TG 消息没有标题：【…】开头取括号内；否则取首行（过长截到首句或 60 字）。摘要是剩余原文，不编。"""
    text = str(text or '').strip()
    m = re.match(r'^[【\[]([^】\]\n]{2,80})[】\]]\s*(.*)$', text, re.S)
    if m:
        return m.group(1).strip(), m.group(2).strip()
    first, _, rest = text.partition('\n')
    first = first.strip()
    if len(first) <= 60:
        return first, rest.strip()
    gap = re.search(r'\s{2,}', first[8:61])   # 频道常把「标题  正文」用两个空格连在一行
    if gap:
        cut = 8 + gap.start()
        return first[:cut].strip(), (first[cut:] + '\n' + rest).strip()
    stop = _SENTENCE.search(first, 8, 61)
    if stop:
        return first[:stop.end()], (first[stop.end():] + '\n' + rest).strip()
    return first[:60] + '…', text


def telegram_items(db_path, media_root, sources, now, floor):
    """sources: [(channel, cfg)]。只读打开，不迁移、不写。"""
    items, statuses = [], []
    db_path = Path(db_path)
    media_root = Path(media_root) if media_root else db_path.resolve().parent
    if not db_path.is_file():
        return [], [_status(cfg, ch, 'error', error='tg.db 不存在') for ch, cfg in sources]
    con = sqlite3.connect(f'file:{db_path.resolve()}?mode=ro', uri=True)
    try:
        con.execute('pragma query_only=on')
        has_images = 'images' in [r[1] for r in con.execute('pragma table_info(msg)')]
        last_status = {}
        if con.execute("select 1 from sqlite_master where type='table' and name='status'").fetchone():
            last_status = {r[0]: (r[1], r[2], r[3]) for r in con.execute('select ch,ok,err,at from status')}
        for channel, cfg in sources:
            handle = cfg.get('handle') or cfg['id']
            cols = 'id,ts,text' + (',images' if has_images else '')
            count = 0
            for row in con.execute(f'select {cols} from msg where ch=? order by id desc', (handle,)):
                msg_id, ts, text = row[0], row[1], row[2]
                published = _parse_when(ts)
                if published is None or published < floor:
                    continue
                title, rest = split_tg_text(text)
                if not title:
                    continue
                image_local = None
                for rel in (json.loads(row[3]) if has_images and row[3] else []):
                    image_local = _local_image(media_root / rel, published, now, media_root)
                    if image_local:
                        break
                items.append(_news(cfg, channel, str(msg_id), title, _plain(rest, SUMMARY_CHARS),
                                   f'https://t.me/{handle}/{msg_id}', published, now, body=str(text).strip(),
                                   image_local=image_local))
                count += 1
            ok, err, at = last_status.get(handle, (None, None, None))
            status = 'ok' if count else 'empty'
            statuses.append(_status(cfg, channel, status, count,
                                    error=(f'上次采集：{err}' if ok == 0 and err else None), fetched_at=at))
    finally:
        con.close()
    return items, statuses


# ---------- 官方订阅 + GitHub Trending（联网可选，结果缓存） ----------

def default_http_get(url, now):
    from shiguang.ingest import http
    response = http.request(url)
    http.check(response, now)
    return response.body


def parse_feed(xml):
    from shiguang.ingest import web
    out = []
    for e in web.parse(xml):
        out.append({'id': e['id'] or _sha(e['url'] or e['title']), 'ts': _iso(e['ts']), 'title': e['title'] or '',
                    'summary': e['body'] or '', 'url': e['url'] or '',
                    'image': next((u for u in e.get('images') or [] if str(u).startswith('https://')), None)})
    return out


def parse_trending(html, now):
    """github.com/trending 公开页：仓库名、简介、语言、今日星数。页面无时间，用抓取时间。"""
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, 'html.parser')
    out = []
    for art in soup.select('article.Box-row'):
        link = art.select_one('h2 a[href]')
        if not link:
            continue
        repo = re.sub(r'\s+', '', link['href']).strip('/')
        if repo.count('/') != 1:
            continue
        desc = art.select_one('p')
        lang = art.select_one('[itemprop=programmingLanguage]')
        today = art.select_one('span.d-inline-block.float-sm-right')
        meta = ' · '.join(x for x in (lang.get_text(strip=True) if lang else '',
                                       today.get_text(' ', strip=True) if today else '') if x)
        summary = desc.get_text(' ', strip=True) if desc else ''
        out.append({'id': repo, 'ts': _iso(now), 'title': repo, 'summary': summary, 'meta': meta,
                    'url': f'https://github.com/{repo}', 'image': None})
    if not out:
        raise ValueError('trending 页面结构变化：没有找到 article.Box-row')
    return out


def _cache_path(cache, sid):
    return Path(cache) / f'{sid}.json'


def _read_cache(cache, sid):
    try:
        return json.loads(_cache_path(cache, sid).read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return None


def _write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + '.tmp')
    tmp.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
    os.replace(tmp, path)


def remote_items(sources, now, floor, *, fetch, cache, http_get):
    items, statuses = [], []
    for channel, cfg in sources:
        sid, entries, state, error, fetched_at = cfg['id'], None, None, None, None
        if fetch:
            try:
                raw = http_get(cfg['url'], now)
                entries = parse_trending(raw.decode('utf-8', 'replace'), now) if cfg['type'] == 'page' else parse_feed(raw)
                fetched_at = _iso(now)
                _write_json(_cache_path(cache, sid), {'fetched_at': fetched_at, 'url': cfg['url'], 'entries': entries})
                state = 'ok' if entries else 'empty'
            except Exception as ex:  # 一家失败不影响其它家；错误只记代码，不带响应体
                code = getattr(ex, 'code', None) or ('invalid_content' if isinstance(ex, (ET.ParseError, ValueError)) else type(ex).__name__)
                state, error = 'error', str(code)
        if entries is None:
            cached = _read_cache(cache, sid)
            if cached:
                entries, fetched_at = cached.get('entries') or [], cached.get('fetched_at')
                state = state or 'cached'
            else:
                entries = []
                state = state or 'not_fetched'
        count = 0
        for e in entries:
            published = _parse_when(e.get('ts')) or now
            if cfg['type'] != 'page' and published < floor:
                continue
            title = _plain(e.get('title'))
            if not title:
                continue
            full = _plain(e.get('summary'))
            body = full + ('\n' + e['meta'] if e.get('meta') else '') if (full or e.get('meta')) else None
            lang = 'zh' if re.search(r'[\u4e00-\u9fff]', title + full) and cfg['type'] == 'page' else FEED_LANG
            image = {'url': e['image']} if e.get('image') and published >= now - timedelta(days=MEDIA_DAYS) else None
            native = e['id'] if cfg['type'] == 'page' else str(e.get('id') or _sha(e.get('url') or title))
            item = _news(cfg, channel, native, title, _plain(full, SUMMARY_CHARS), e.get('url'), published, now,
                         lang=lang, body=body, image=image)
            if fetched_at:
                item['fetched_at'] = fetched_at
            items.append(item)
            count += 1
        if state in ('ok', 'cached') and not count:
            state = 'empty'
        statuses.append(_status(cfg, channel, state, count, error=error, fetched_at=fetched_at))
    return items, statuses


# ---------- 现有每日成品（x / world / github / hot-daily） ----------

def _legacy_sources():
    return {s['id']: s for s in json.loads((ROOT / 'sources.json').read_text(encoding='utf-8'))['sources']}


def default_inbox_loader(source_id):
    """盒子上原始投递目录优先，其次仓库 public-feeds。返回 [(feed, base_dir)]，新→旧。"""
    from shiguang.ingest.feeds import load_issues
    with contextlib.redirect_stdout(sys.stderr):
        return load_issues(_legacy_sources()[source_id], local=True)


def _issue_entries(issues, floor):
    for feed, base in issues:
        day = feed.get('date')
        start = _parse_when(day)
        if start is None or start < floor.replace(hour=0, minute=0, second=0, microsecond=0):
            continue
        for section in feed.get('sections') or []:
            for entry in section.get('items') or []:
                if isinstance(entry, dict):
                    yield day, Path(base), entry


def inbox_items(sources, now, floor, loader):
    items, statuses = [], []
    for channel, cfg in sources:
        try:
            issues = loader(cfg['id'])
        except Exception as ex:
            statuses.append(_status(cfg, channel, 'error', error=type(ex).__name__))
            continue
        seen, count = set(), 0
        for day, base, entry in _issue_entries(issues, floor):
            title, body, url = _plain(entry.get('title')), str(entry.get('body') or '').strip(), _http_url(entry.get('link'))
            if not title:
                continue
            native = _sha(_norm_url(url)) if url else _sha(f'{day}|{title}')
            if native in seen:   # 新→旧遍历，同一链接只留最新一期
                continue
            seen.add(native)
            published = _parse_when(entry.get('date'), day) or _parse_when(day)
            image_local = None
            for im in entry.get('images') or []:
                if isinstance(im, dict) and isinstance(im.get('file'), str) and '/' not in im['file'] and not im['file'].startswith('.'):
                    image_local = _local_image(base / im['file'], published, now)
                    if image_local:
                        image_local['alt'] = str(im.get('alt') or '')
                        break
            items.append(_news(cfg, channel, native, title, _plain(body, SUMMARY_CHARS), url, published, now,
                               body=body or None, image_local=image_local))
            count += 1
        latest = issues[0][0].get('date') if issues else None
        statuses.append(dict(_status(cfg, channel, 'ok' if count else 'empty', count), latest_issue=latest))
    return items, statuses


def apply_highlights(items, now, floor, loader, table):
    """channels.json.highlights.rule：link 命中已上站条目只打标；否则按 sources 第一个能匹配的来源归频道；都不行归 current。"""
    rule = load_channels()['highlights']
    hid = rule['source_id']
    cfg = {'id': hid, 'name': rule['name'], 'type': 'inbox'}
    try:
        issues = loader(hid)
    except Exception as ex:
        return [], _status(cfg, None, 'error', error=type(ex).__name__)
    by_url = {}
    for item in items:
        if item['url']:
            by_url.setdefault(_norm_url(item['url']), item)
    by_key = {}
    for sid, (slug, source) in table.items():
        by_key.setdefault(sid, slug)
        by_key.setdefault(source['name'], slug)
    extra, marked, seen = [], 0, set()
    for day, _base, entry in _issue_entries(issues, floor):
        url = _http_url(entry.get('link'))
        target = by_url.get(_norm_url(url)) if url else None
        if target is not None:
            if not target.get('highlight'):
                marked += 1
            target['highlight'] = True
            target['highlight_date'] = max(day, target.get('highlight_date') or day)
            continue
        title = _plain(entry.get('title'))
        if not title:
            continue
        native = _sha(_norm_url(url)) if url else _sha(f'{day}|{title}')
        if native in seen:
            continue
        seen.add(native)
        names = [s for s in (entry.get('sources') or []) if isinstance(s, str)] or ([entry['source']] if isinstance(entry.get('source'), str) else [])
        channel = next((by_key[n] for n in names if n in by_key), 'current')
        body = str(entry.get('body') or '').strip()
        published = _parse_when(entry.get('date'), day) or _parse_when(day)
        item = _news(cfg, channel, native, title, _plain(body, SUMMARY_CHARS), url, published, now, body=body or None)
        item.update(highlight=True, highlight_date=day)
        extra.append(item)
    latest = issues[0][0].get('date') if issues else None
    status = dict(_status(cfg, None, 'ok' if (marked or extra) else 'empty', len(extra)),
                  marked=marked, latest_issue=latest)
    return extra, status


# ---------- 翻译（rebang/translate 由 bloggers 分支提供；没有就留 translated=false） ----------

def default_translator():
    try:
        from rebang import translate as module
    except ImportError:
        return None
    fn = getattr(module, 'translate', None)
    if not callable(fn):
        return None
    engine = getattr(module, 'ENGINE', None) or 'rebang.translate'
    return lambda texts, src: fn(texts, src), engine


def apply_translation(items, translator, cache):
    if not translator:
        return 0
    fn, engine = translator
    store_path = Path(cache) / 'translations.json'
    try:
        store = json.loads(store_path.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        store = {}
    todo = [i for i in items if not i['lang'].startswith('zh')]
    key = lambda i: _sha(i['id'] + '\n' + i['title'] + '\n' + i['summary'])  # noqa: E731
    missing = [i for i in todo if key(i) not in store]
    if missing:
        titles = [i['title'] for i in missing if i['source_id'] != 'github-trending']
        summaries = [i['summary'] for i in missing]
        t_out = fn(titles, 'en') if titles else []
        s_out = fn(summaries, 'en')
        if isinstance(t_out, list) and isinstance(s_out, list) and len(t_out) == len(titles) and len(s_out) == len(summaries):
            t_iter = iter(t_out)
            for item, summary in zip(missing, s_out):
                title = item['title'] if item['source_id'] == 'github-trending' else next(t_iter)
                if isinstance(title, str) and isinstance(summary, str) and title.strip():
                    store[key(item)] = {'title': title, 'summary': summary, 'engine': engine}
            _write_json(store_path, store)
    done = 0
    for item in todo:
        hit = store.get(key(item))
        if hit:
            item['translated'] = True
            item['translation'] = {'title': hit['title'], 'summary': hit['summary'], 'engine': hit['engine'], 'label': MT}
            done += 1
    return done


# ---------- 入口 ----------

def collect(now, *, fetch=False, db=None, media_root=None, cache=DEFAULT_CACHE, days=14, http_get=None,
            inbox_loader=None, translator='default'):
    now = _aware(now).astimezone(BEIJING)
    floor = now - timedelta(days=days)
    table = source_table()
    by_type = {}
    for sid, (slug, cfg) in table.items():
        by_type.setdefault(cfg['type'], []).append((slug, cfg))
    loader = inbox_loader or default_inbox_loader
    items, statuses = [], []
    got, st = telegram_items(db or ROOT / 'tg.db', media_root, by_type.get('telegram', []), now, floor)
    items += got; statuses += st
    got, st = remote_items(by_type.get('feed', []) + by_type.get('page', []), now, floor, fetch=fetch, cache=cache,
                           http_get=http_get or default_http_get)
    items += got; statuses += st
    got, st = inbox_items(by_type.get('inbox', []), now, floor, loader)
    items += got; statuses += st
    extra, hstatus = apply_highlights(items, now, floor, loader, table)
    items += extra; statuses.append(hstatus)
    if translator == 'default':
        translator = default_translator()
    translated = apply_translation(items, translator, cache)
    unique = {}
    for item in items:
        unique.setdefault(item['id'], item)
    ordered = sorted(unique.values(), key=lambda i: i['published_at'], reverse=True)
    return {'schema': ITEMS_SCHEMA, 'producer': PRODUCER, 'generated_at': _iso(now), 'items': ordered,
            'sources': statuses, 'translation': {'available': bool(translator), 'translated': translated}}


def write_envelope(envelope, out):
    _write_json(Path(out), envelope)
