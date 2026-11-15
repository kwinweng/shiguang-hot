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

from rebang.contract import ITEMS_SCHEMA, load_bloggers, load_channels

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


_LEADING_URLS = re.compile(r'^(?:\s*https?://\S+)+\s*')
_CJK = re.compile(r'[\u3400-\u9fff]')


def strip_leading_urls(text):
    """卡片摘要开头常是裸链接（TG 把原文链接放第一行）：入库时去掉，正文 body 保留原样。"""
    return _LEADING_URLS.sub('', str(text or ''))


def guess_lang(*texts):
    return 'zh' if _CJK.search(' '.join(t or '' for t in texts)) else 'en'


def grok_sources():
    """博主页 Grok bot 渠道的 4 份每日成品（bloggers.json platforms[id=grok].accounts）。"""
    for platform in load_bloggers()['platforms']:
        if platform['id'] == 'grok':
            return [{'id': a['handle'], 'name': a['name'], 'type': 'inbox'} for a in platform['accounts']]
    return []


def _news(source, channel, native_id, title, summary, url, published, now, lang='zh', body=None, image=None,
          image_local=None):
    summary = strip_leading_urls(summary)
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


QUOTE_CHARS = 1500


def _tg_clean(handle, text):
    """与旧采集同一套频道文案清理（freechinese 去引流尾巴/广告）；旧模块不在时原样返回。"""
    try:
        from shiguang.ingest.telegram import channel_text
    except Exception:  # pragma: no cover - 旧模块缺依赖时
        return text
    out = channel_text(handle, text)
    return text if out is None else out


def _tg_parts(handle, text, meta):
    """tg.db 原文 + tgmeta → (标题, 摘要原文, 正文, quote, tg)。
    tg.db 遇到回复/引用消息存的是被引用的原文，这里改用公开页面上频道自己写的话；
    转发消息频道自己没写话：正文留空，原帖放进 quote（kind=forward），标题取自原帖，前端标「转发」。"""
    from rebang.tgmeta import merge_meta
    extra = merge_meta(meta)
    quote = extra.get('quote')
    if quote:
        quote = dict(quote, text=_plain(quote['text'], QUOTE_CHARS) if len(quote['text']) > QUOTE_CHARS else quote['text'])
    own = _tg_clean(handle, extra.get('own_text') or '').strip() if extra else ''
    if quote and quote['kind'] == 'forward':
        title, _ = split_tg_text(quote['text'] or text)
        return title, '', '', quote, extra.get('tg')
    if own:
        title, rest = split_tg_text(own)
        return title, rest, own, quote, extra.get('tg')
    if quote:   # 回复但自己只发了图：标题取被引用原文，正文空
        title, _ = split_tg_text(quote['text'])
        return title, '', '', quote, extra.get('tg')
    title, rest = split_tg_text(text)
    return title, rest, str(text).strip(), None, extra.get('tg')


def telegram_items(db_path, media_root, sources, now, floor, tgmeta=None):
    """sources: [(channel, cfg)]。只读打开，不迁移、不写。tgmeta：rebang.tgmeta 缓存里的 messages（<频道>/<消息号> → meta）。"""
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
                title, rest, body, quote, tg = _tg_parts(handle, text, (tgmeta or {}).get(f'{handle}/{msg_id}'))
                if not title:
                    continue
                image_local = None
                for rel in (json.loads(row[3]) if has_images and row[3] else []):
                    image_local = _local_image(media_root / rel, published, now, media_root)
                    if image_local:
                        break
                item = _news(cfg, channel, str(msg_id), title, _plain(rest, SUMMARY_CHARS),
                             f'https://t.me/{handle}/{msg_id}', published, now, body=body,
                             image_local=image_local)
                if quote:
                    item['quote'] = quote
                if tg:
                    item['tg'] = tg
                items.append(item)
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
    """Grok bot 每日成品 → kind=post（blogger.platform=grok，handle=成品 id），不进 6 个频道。"""
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
            item = _news(cfg, None, native, title, _plain(body, SUMMARY_CHARS), url, published, now,
                         lang=guess_lang(title, body), body=body or None, image_local=image_local)
            item['kind'] = 'post'
            item['blogger'] = {'platform': 'grok', 'handle': cfg['id'], 'display_name': cfg['name'], 'media': []}
            items.append(item)
            count += 1
        latest = issues[0][0].get('date') if issues else None
        statuses.append(dict(_status(cfg, channel, 'ok' if count else 'empty', count), latest_issue=latest))
    return items, statuses


def apply_highlights(items, now, floor, loader, table=None):
    """channels.json.highlights.rule：今日重点不进频道（整份是 Grok bot 渠道的帖子）；频道里同链接的条目只打 highlight 标。"""
    rule = load_channels()['highlights']
    hid = rule['source_id']
    cfg = {'id': hid, 'name': rule['name'], 'type': 'inbox'}
    try:
        issues = loader(hid)
    except Exception as ex:
        return [], _status(cfg, None, 'error', error=type(ex).__name__)
    by_url = {}
    for item in items:
        if item['kind'] == 'news' and item['url']:
            by_url.setdefault(_norm_url(item['url']), item)
    marked = unmatched = 0
    for day, _base, entry in _issue_entries(issues, floor):
        url = _http_url(entry.get('link'))
        target = by_url.get(_norm_url(url)) if url else None
        if target is None:
            unmatched += 1
            continue
        if not target.get('highlight'):
            marked += 1
        target['highlight'] = True
        target['highlight_date'] = max(day, target.get('highlight_date') or day)
    latest = issues[0][0].get('date') if issues else None
    status = dict(_status(cfg, None, 'ok' if marked else 'empty', 0), marked=marked, unmatched=unmatched,
                  latest_issue=latest, role='highlight-marks')
    return [], status


# ---------- 翻译（rebang/translate 由 bloggers 分支提供；没有就留 translated=false） ----------

def default_translator():
    """共享 rebang.translate 的缓存（var/rebang/translate/cache.json + pending.json）。返回 (fn, engine, saver) 或 None。"""
    try:
        from rebang.translate import Translator
    except ImportError:
        return None
    translator = Translator()
    if translator.engine == 'none':
        return None
    return (lambda texts, src: translator.translate_detailed(texts, src)), translator.engine, translator.save


def _translate_one(fn, texts):
    """逐条翻；缺一段就整条不标 translated（下次缓存补齐后再上）。返回 (译文列表, engine) 或 None。"""
    want = [t for t in texts if t.strip()]
    if not want:
        return None
    got = fn(want, 'en')
    if isinstance(got, tuple):
        out, engine = got
    elif got is None:
        return None
    else:
        out, engine = got, None
    if not (isinstance(out, list) and len(out) == len(want)):
        return None
    it = iter(out)
    return [next(it) if t.strip() else '' for t in texts], engine


def apply_translation(items, translator, cache=None):
    """只翻非中文条目的标题 + 卡片摘要（GitHub Trending 仓库名不翻）。按条增量：
    已译过的条目（cache/translations.json，按 id+标题+摘要）直接复用，不再调翻译；新条目才调。
    默认翻译器只查 rebang.translate 缓存，缺的原文进 pending.json，等 Grok 补译后
    （python3 -m rebang.translate fill）下次生成即带上。"""
    if not translator:
        return 0
    fn, default_engine = translator[0], translator[1]
    store_path = Path(cache) / 'translations.json' if cache else None
    try:
        store = json.loads(store_path.read_text(encoding='utf-8')) if store_path else {}
    except (OSError, ValueError):
        store = {}
    key = lambda i: _sha(i['id'] + '\n' + i['title'] + '\n' + i['summary'])  # noqa: E731
    done, changed = 0, False
    for item in items:
        if item['lang'].startswith('zh') or item['lang'] == 'und':
            continue
        hit = store.get(key(item))
        if not hit:
            keep_title = item['source_id'] == 'github-trending'
            texts = ([] if keep_title else [item['title']]) + [item['summary']]
            result = _translate_one(fn, texts)
            if not result:
                continue
            out, engine = result
            title = item['title'] if keep_title else out[0]
            if not (title or '').strip():
                continue
            hit = store[key(item)] = {'title': title, 'summary': out[-1], 'engine': engine or default_engine}
            changed = True
        item['translated'] = True
        item['translation'] = {'title': hit['title'], 'summary': hit['summary'], 'engine': hit['engine'], 'label': MT}
        done += 1
    if changed and store_path:
        _write_json(store_path, store)
    if len(translator) > 2 and callable(translator[2]):
        translator[2]()
    return done


# ---------- 入口 ----------

def collect(now, *, fetch=False, db=None, media_root=None, cache=DEFAULT_CACHE, days=14, http_get=None,
            inbox_loader=None, translator='default', tgmeta=None):
    now = _aware(now).astimezone(BEIJING)
    floor = now - timedelta(days=days)
    table = source_table()
    by_type = {}
    for sid, (slug, cfg) in table.items():
        by_type.setdefault(cfg['type'], []).append((slug, cfg))
    loader = inbox_loader or default_inbox_loader
    items, statuses = [], []
    if isinstance(tgmeta, (str, Path)):
        from rebang.tgmeta import load_store
        tgmeta = load_store(tgmeta).get('messages', {})
    got, st = telegram_items(db or ROOT / 'tg.db', media_root, by_type.get('telegram', []), now, floor, tgmeta)
    items += got; statuses += st
    got, st = remote_items(by_type.get('feed', []) + by_type.get('page', []), now, floor, fetch=fetch, cache=cache,
                           http_get=http_get or default_http_get)
    items += got; statuses += st
    got, st = inbox_items([(None, cfg) for cfg in grok_sources()], now, floor, loader)
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
            'sources': statuses, 'translation': {'available': bool(translator), 'translated': translated,
                                              'untranslated': sum(1 for i in ordered if not i['lang'].startswith('zh') and i['lang'] != 'und' and not i.get('translated'))}}


def write_envelope(envelope, out):
    _write_json(Path(out), envelope)
