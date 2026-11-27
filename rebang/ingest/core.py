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
from urllib.parse import urljoin, urlsplit
from zoneinfo import ZoneInfo

from rebang.cache import save_cache
from rebang.chinese_news import chinese_text, is_web_news, native_preview, needs_translation
from rebang.contract import ITEMS_SCHEMA, load_channels
from rebang.contract.schema import is_aware_iso
from rebang.health_time import observation_time

ROOT = Path(__file__).resolve().parents[2]
BEIJING = ZoneInfo('Asia/Shanghai')
DEFAULT_CACHE = ROOT / 'var' / 'rebang' / 'cache' / 'ingest'
MEDIA_DAYS = 14          # 与 shiguang/ingest/telegram.py MEDIA_DAYS 一致：图片按条目时间保留 14 天
SUMMARY_CHARS = 300
PRODUCER = 'ingest'
FEED_LANG = 'en'         # 官方订阅都是英文
MT = '机器翻译'


# ---------- 小工具 ----------

def _aware(moment):
    return moment if moment.tzinfo else moment.replace(tzinfo=BEIJING)


def _iso(moment):
    return _aware(moment).astimezone(BEIJING).isoformat(timespec='seconds')


def _parse_when(value):
    try:
        return _aware(datetime.fromisoformat(str(value or '').strip().replace('Z', '+00:00'))).astimezone(BEIJING)
    except (ValueError, OverflowError):
        return None


def _plain(text, cap=None):
    text = re.sub(r'\s+', ' ', str(text or '')).strip()
    return text[:cap].rstrip() + '…' if cap and len(text) > cap else text


def _sha(value):
    return hashlib.sha1(value.encode('utf-8')).hexdigest()[:16]


def _http_url(url):
    return url if re.match(r'https?://[^\s/]+', str(url or '')) else ''


def _valid_http(url, schemes=('http', 'https')):
    """与契约 schema._is_url 同一口径（scheme + 主机名），另外挡住 urlsplit 自己会抛错的地址（如坏 IPv6）。"""
    if not isinstance(url, str) or not url.strip():
        return False
    try:
        parts = urlsplit(url.strip())
        return parts.scheme in schemes and bool(parts.netloc) and bool(parts.hostname)
    except ValueError:
        return False


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


_BARE_URL = re.compile(r'https?://[^\s《》「」“”‘’，。、；：！？（）【】<>]+')
_QUOTED = re.compile(r'《[^》]*》|「[^」]*」|“[^”]*”')


def mostly_chinese(title):
    """英文订阅按条判断，只看标题：先去掉《》「」“”里的内容（引用的中文作品名/原话），
    再去掉裸链接（遇中文标点或括号停止），剩下的只要有汉字就是 zh，否则 en。摘要不参与。"""
    rest = _BARE_URL.sub('', _QUOTED.sub('', str(title or '')))
    return bool(_CJK.search(rest))


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
                media = (tg or {}).get('media', [])
                has_video = (tg or {}).get('video_unavailable') or any(m['type'] == 'video' for m in media)
                if has_video and title in ('', '[图片]'):
                    title, body = '[视频]', ''
                if not title:
                    continue
                image_local = None
                for rel in (json.loads(row[3]) if has_images and row[3] else []):
                    image_local = _local_image(media_root / rel, published, now, media_root)
                    if image_local:
                        break
                poster = next((m.get('preview_url') or m['url'] for m in media
                               if m.get('preview_url') or m['type'] == 'image'), None)
                item = _news(cfg, channel, str(msg_id), title, _plain(rest, SUMMARY_CHARS),
                             f'https://t.me/{handle}/{msg_id}', published, now, body=body,
                             image={'url': poster} if poster and not image_local else None, image_local=image_local)
                if quote:
                    item['quote'] = quote
                if tg:
                    item['tg'] = tg
                items.append(item)
                count += 1
            ok, err, at = last_status.get(handle, (None, None, None))
            status = 'ok' if count else 'empty'
            status_row = _status(cfg, channel, status, count,
                                 error=(f'上次采集：{err}' if ok == 0 and err else None), fetched_at=at)
            if ok in (0, 1):
                status_row['collection_ok'] = bool(ok)
            statuses.append(status_row)
    finally:
        con.close()
    return items, statuses


# ---------- 官方订阅 + GitHub Trending（联网可选，结果缓存） ----------

def default_http_get(url, now):
    from shiguang.ingest import http
    response = http.request(url)
    http.check(response, now)
    return response.body


_XML_BASE = '{http://www.w3.org/XML/1998/namespace}base'
_ATOM = '{http://www.w3.org/2005/Atom}'


def _join(base, ref):
    try:
        return urljoin(base, ref) if base else ref
    except ValueError:
        return ref


def _atom_link_bases(xml, feed_url):
    """Atom 条目的链接基准地址（xml:base 逐层叠加：feed 地址 → <feed> → <entry> → <link>），
    按文档顺序返回 {(id 或 链接原文, 链接原文): 基准地址}。不是 Atom 或解析不了就返回空。"""
    try:
        root = ET.fromstring(xml)
    except (ET.ParseError, ValueError):
        return {}
    if root.tag != _ATOM + 'feed':
        return {}
    feed_base = _join(feed_url, root.get(_XML_BASE)) if root.get(_XML_BASE) else feed_url
    out = {}
    for entry in root.findall(_ATOM + 'entry'):
        entry_base = _join(feed_base, entry.get(_XML_BASE)) if entry.get(_XML_BASE) else feed_base
        link = next((l for l in entry.findall(_ATOM + 'link') if l.get('rel', 'alternate') == 'alternate'), None)
        if link is None:
            continue
        href = link.get('href') or ''
        base = _join(entry_base, link.get(_XML_BASE)) if link.get(_XML_BASE) else entry_base
        out.setdefault((entry.findtext(_ATOM + 'id') or href, href), base)
    return out


def _resolve_link(url, base):
    """条目链接：绝对 http(s) 原样用；不带协议的相对地址用基准地址补全；带协议却不合格（https:///x、
    javascript: 等）、补全后仍不合格或没有基准就置空。链接坏了只让这条没有原文链接，条目本身保留。"""
    url = str(url or '').strip()
    if not url or _valid_http(url):
        return url
    try:
        relative = not urlsplit(url).scheme
    except ValueError:
        relative = False
    joined = _join(base, url) if base and relative else ''
    return joined if _valid_http(joined) else ''


def parse_feed(xml, feed_url=None):
    from shiguang.ingest import web
    bases = _atom_link_bases(xml, feed_url)
    out = []
    for e in web.parse(xml, with_publication=True):
        raw = e['url'] or ''
        base = bases.get((e['id'] or raw, raw), feed_url)
        out.append({'id': e['id'] or _sha(raw or e['title']), 'ts': _iso(e['ts']), 'title': e['title'] or '',
                    'summary': e['body'] or '', 'url': _resolve_link(raw, base),
                    'image': next((u for u in e.get('images') or [] if _valid_http(u, ('https',))), None),
                    'published_at_verified': e.get('published_at_verified', False),
                    'feed_attribution': e.get('feed_attribution', True)})
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


def _preserve_tg_success(rows, cache, now):
    # The legacy DB keeps a single attempt per channel. Keep the last observed success with the ingest cache.
    key = 'telegram-health'
    saved = _read_cache(cache, key)
    saved = saved if isinstance(saved, dict) else {}
    updated = {}
    for row in rows:
        source_id = row['id']
        previous = observation_time(_parse_when(saved.get(source_id)), now)
        reported = observation_time(_parse_when(row.get('fetched_at')), now) if row.get('collection_ok') else None
        last_ok = max(filter(None, (previous, reported)), default=None)
        row['last_ok_at'] = _iso(last_ok) if last_ok else None
        if last_ok:
            updated[source_id] = row['last_ok_at']
    if updated != saved:
        save_cache(_write_json, _cache_path(cache, key), updated)


def remote_items(sources, now, floor, *, fetch, cache, http_get):
    items, statuses = [], []
    for channel, cfg in sources:
        sid, entries, state, error, fetched_at = cfg['id'], None, None, None, None
        cache_warning = None
        if fetch:
            try:
                raw = http_get(cfg['url'], now)
                parsed = parse_trending(raw.decode('utf-8', 'replace'), now) if cfg['type'] == 'page' else parse_feed(raw, cfg['url'])
            except Exception as ex:  # 一家失败不影响其它家；错误只记代码，不带响应体
                code = getattr(ex, 'code', None) or ('invalid_content' if isinstance(ex, (ET.ParseError, ValueError)) else type(ex).__name__)
                state, error = 'error', str(code)
            else:
                entries, fetched_at = parsed, _iso(now)
                state = 'ok' if entries else 'empty'
                if not save_cache(_write_json, _cache_path(cache, sid),
                                  {'fetched_at': fetched_at, 'url': cfg['url'], 'entries': entries}):
                    cache_warning = 'write_failed'
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
            timestamp = e.get('ts')
            published = _parse_when(timestamp)
            verified = (cfg['type'] == 'feed' and e.get('published_at_verified') is True
                        and is_aware_iso(timestamp) and published is not None)
            published = published or now
            if cfg['type'] != 'page' and published < floor:
                continue
            title = _plain(e.get('title'))
            if not title:
                continue
            # 缓存里的链接不再补全（旧缓存没存基准地址）：不合格就置空，条目保留
            link = _resolve_link(e.get('url'), None)
            full = _plain(e.get('summary'))
            body = full + ('\n' + e['meta'] if e.get('meta') else '') if (full or e.get('meta')) else None
            if cfg['type'] == 'page':
                lang = 'zh' if re.search(r'[\u4e00-\u9fff]', title + full) else FEED_LANG
            else:   # 英文订阅里偶尔混进中文条目：只看标题，标题有汉字（引号/书名号里的不算）标 zh，不送翻译
                lang = 'zh' if mostly_chinese(title) else FEED_LANG
            # 图片地址坏了（缺主机名等）只丢图、条目保留；旧缓存里的坏图同样在这里挡掉
            fresh = published >= now - timedelta(days=MEDIA_DAYS)
            image = {'url': e['image']} if fresh and _valid_http(e.get('image')) else None
            native = e['id'] if cfg['type'] == 'page' else str(e.get('id') or _sha(e.get('url') or title))
            item = _news(cfg, channel, native, title, _plain(full, SUMMARY_CHARS), link, published, now,
                         lang=lang, body=body, image=image)
            item['published_at_verified'] = verified
            if cfg['type'] == 'feed':
                item['feed_attribution'] = e.get('feed_attribution') is not False  # 旧缓存未保留署名信息，不投票
            if fetched_at:
                item['fetched_at'] = fetched_at
            items.append(item)
            count += 1
        run_count = (0 if state == 'error' else count) if fetch else None
        if state in ('ok', 'cached') and not count:
            state = 'empty'
        row = dict(_status(cfg, channel, state, count, error=error, fetched_at=fetched_at), run_count=run_count)
        if cache_warning:
            row['cache_warning'] = cache_warning
        statuses.append(row)
    return items, statuses


# ---------- 旧 #88 主条优先级（本地整理稿只参与折叠） ----------

def default_inbox_loader(source_id):
    from shiguang.ingest.feeds import load_issues

    sources = json.loads((ROOT / 'sources.json').read_text(encoding='utf-8'))['sources']
    source = next(s for s in sources if s['id'] == source_id)
    with contextlib.redirect_stdout(sys.stderr):
        return load_issues(source, local=True)


def _legacy_link(url):
    url = re.sub(r'^http://', 'https://', url.strip())
    url = re.sub(r'^https://t\.me/s/', 'https://t.me/', url)
    return url.split('#', 1)[0].rstrip('/')


def _remember_fold_preference(items, floor, loader):
    if not items:
        return
    try:
        issues = loader(load_channels()['highlights']['source_id'])
    except Exception:  # 与旧入口一样，整理稿不可用时仍能采集新闻
        return
    by_url = {}
    for item in items:
        if item['kind'] == 'news' and item['url']:
            by_url.setdefault(_legacy_link(item['url']), item)
    cut = floor.replace(hour=0, minute=0, second=0, microsecond=0)
    for feed, _ in issues:
        day = _parse_when(feed.get('date'))
        if day is None or day < cut:
            continue
        for section in feed.get('sections') or []:
            for entry in section.get('items') or []:
                url = _http_url(entry.get('link')) if isinstance(entry, dict) else ''
                target = by_url.get(_legacy_link(url)) if url else None
                if target is not None:
                    target['fold_preferred'] = True


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
    return translator.translate_detailed, translator.engine, translator.save


def _call_translator(fn, texts, kinds=None):
    """兼容测试里只收 (texts, src) 的假翻译器。"""
    if not texts:
        return None
    try:
        got = fn(texts, 'en', kinds) if kinds is not None else fn(texts, 'en')
    except TypeError:
        got = fn(texts, 'en')
    if isinstance(got, tuple):
        out, engine = got
    elif got is None:
        return None
    else:
        out, engine = got, None
    if not (isinstance(out, list) and len(out) == len(texts)):
        return None
    return out, engine


def _translate_one(fn, texts, kinds=None):
    """一批一起翻；缺一段则逐段再试，这样标题/摘要不必等正文。返回 (译文或 None 的列表, engine) 或 None。"""
    if not texts:
        return None
    got = _call_translator(fn, texts, kinds)
    if got:
        return got
    out, engine, any_hit = [], None, False
    for i, text in enumerate(texts):
        if not (text or '').strip():
            out.append('')
            continue
        kind = [kinds[i]] if kinds and i < len(kinds) else None
        one = _call_translator(fn, [text], kind)
        if one:
            out.append(one[0][0])
            engine = one[1]
            any_hit = True
        else:
            out.append(None)
    return (out, engine) if any_hit else None


def _blocks_texts(blocks):
    """抽出 blocks 里待译文本，返回 (定位键, 文本列表)。定位键是 (下标, 'text' 或条目下标)。"""
    keys, texts = [], []
    for i, block in enumerate(blocks or []):
        if block.get('type') in ('p', 'h', 'quote', 'pre') and block.get('text'):
            keys.append((i, 'text'))
            texts.append(block['text'])
        elif block.get('type') in ('ul', 'ol'):
            for j, line in enumerate(block.get('items') or []):
                if line:
                    keys.append((i, j))
                    texts.append(line)
    return keys, texts


def _apply_block_texts(blocks, keys, texts):
    import copy
    out = copy.deepcopy(blocks)
    for (i, field), zh in zip(keys, texts):
        if field == 'text':
            out[i]['text'] = zh
        else:
            out[i]['items'][field] = zh
    return out


def _summary_from_body(body, limit=300):
    body = (body or '').strip()
    if len(body) <= limit:
        return body
    return body[:limit].rstrip()


def apply_translation(items, translator, cache=None):
    """只翻非中文条目的标题、摘要和正文（GitHub Trending 仓库名不翻）。按条增量：
    已译过的条目（cache/translations.json，按 id+标题+摘要+正文）直接复用；新条目或新抽出的
    正文才调。默认翻译器只查 rebang.translate 缓存，缺的原文进 pending.json，等 Grok 补译后
    （python3 -m rebang.translate fill）下次生成即带上。

    标题和摘要一旦有译文就写入，不等待正文。正文稍后补上；在此之前详情页用中文摘要，并标明全文还在翻译。
    """
    if not translator:
        return 0
    fn, default_engine = translator[0], translator[1]
    store_path = Path(cache) / 'translations.json' if cache else None
    try:
        store = json.loads(store_path.read_text(encoding='utf-8')) if store_path else {}
    except (OSError, ValueError):
        store = {}
    key = lambda i: _sha(i['id'] + '\n' + i['title'] + '\n' + i['summary'] + '\n' + (i.get('body') or ''))  # noqa: E731
    done, changed = 0, False
    for item in items:
        web = is_web_news(item)
        if web:
            if not needs_translation(item):
                continue
        elif item['lang'].startswith('zh') or item['lang'] == 'und':
            continue
        hit = store.get(key(item))
        body = (item.get('body') or '').strip()
        src_sum = item.get('summary') or ''
        keep_preview = web and native_preview(item)
        keep_title = item['source_id'] == 'github-trending' or keep_preview
        if keep_preview:
            hit = {**(hit or {}), 'title': item['title'], 'summary': src_sum, 'engine': (hit or {}).get('engine') or default_engine}
        if web and isinstance(hit, dict):
            # 旧版可能把空摘要/英文回显写成命中。重新查字段缓存，不能永久跳过。
            hit = dict(hit)
            for field in ('title', 'summary', 'body'):
                if (field == 'title' and not keep_title or field == 'summary' and src_sum.strip() and not keep_preview
                        or field == 'body' and body) and not chinese_text(hit.get(field)):
                    hit.pop(field, None)
            if src_sum.strip() and not keep_preview and hit.get('summary_source') != src_sum:
                hit.pop('summary', None)
            if hit.get('blocks') and not all(chinese_text(t) for t in _blocks_texts(hit['blocks'])[1]):
                hit.pop('blocks', None)
        derive_summary = bool(body and src_sum and (src_sum == body or body.startswith(src_sum)))
        missing_body = bool(body) and not (hit and hit.get('body'))
        missing_blocks = bool(item.get('blocks')) and not (hit and hit.get('blocks'))
        # 1) 标题和摘要单独翻，不被长正文拖住
        if not hit or not hit.get('title') or hit.get('summary') is None:
            texts, slots, kinds = [], [], []
            if not keep_title and not (hit and hit.get('title')):
                texts.append(item['title']); slots.append('title'); kinds.append('title')
            need_summary = not (hit and hit.get('summary') is not None)
            if need_summary and src_sum.strip() and (web or not derive_summary or not (hit and hit.get('body'))):
                texts.append(src_sum); slots.append('summary'); kinds.append('summary')
            result = _translate_one(fn, texts, [f'web:{kind}' for kind in kinds] if web else kinds) if texts else None
            if result or (keep_title and not src_sum.strip()):
                out, engine = (result or ([], None))
                mapped = {slot: zh for slot, zh in zip(slots, out)
                          if isinstance(zh, str) and zh.strip() and (not web or chinese_text(zh))}
                title = item['title'] if keep_title else mapped.get('title') or (hit or {}).get('title')
                summary = mapped.get('summary')
                if summary is None:
                    summary = (hit or {}).get('summary')
                if summary is None and not src_sum.strip():
                    summary = ''
                # 标题已译、摘要还在排队时先上标题，预览暂空，避免英文摘要出现在列表；下次仍会重试摘要
                summary_pending = False
                if summary is None and (title or '').strip():
                    summary, summary_pending = '', True
                if (title or '').strip() and summary is not None:
                    prev = dict(hit or {})
                    prev.update({
                        'title': title, 'summary': summary,
                        'engine': engine or prev.get('engine') or default_engine,
                    })
                    if web and 'summary' in mapped:
                        prev['summary_source'] = src_sum
                    if summary_pending:
                        prev['summary_pending'] = True
                    else:
                        prev.pop('summary_pending', None)
                    hit = store[key(item)] = prev
                    changed = True
        # 2) 正文和 blocks 另一次，缺了也不撤掉已有的标题/摘要
        if hit and (missing_body or missing_blocks):
            texts, slots, kinds = [], [], []
            bkeys, btexts = ([], [])
            if missing_body:
                texts.append(body); slots.append('body'); kinds.append('body')
            if missing_blocks:
                bkeys, btexts = _blocks_texts(item.get('blocks'))
                texts.extend(btexts)
                kinds.extend(['block'] * len(btexts))
            result = _translate_one(fn, texts, [f'web:{kind}' for kind in kinds] if web else kinds) if texts else None
            if result:
                out, engine = result
                mapped = {slot: zh for slot, zh in zip(slots, out[:len(slots)])
                          if isinstance(zh, str) and zh.strip() and (not web or chinese_text(zh))}
                trans_body = mapped.get('body') or hit.get('body')
                if trans_body:
                    hit['body'] = trans_body
                    if derive_summary and not web:
                        hit['summary'] = _summary_from_body(trans_body)
                        hit.pop('summary_pending', None)
                if bkeys and all(isinstance(x, str) and x.strip() for x in out[len(slots):]):
                    hit['blocks'] = _apply_block_texts(item['blocks'], bkeys, out[len(slots):])
                hit['engine'] = engine or hit.get('engine') or default_engine
                store[key(item)] = hit
                changed = True
        if not hit or not hit.get('title') or hit.get('summary') is None:
            continue
        item['translated'] = True
        trans = {'title': hit['title'], 'summary': hit['summary'], 'engine': hit['engine'], 'label': MT}
        if web and 'summary_source' in hit and hit.get('summary'):
            trans['summary_source'] = hit['summary_source']
        if hit.get('body'):
            trans['body'] = hit['body']
        if hit.get('blocks'):
            trans['blocks'] = hit['blocks']
        if (body or item.get('blocks')) and not hit.get('body') and not hit.get('blocks'):
            trans['body_pending'] = True
        item['translation'] = trans
        done += 1
    if changed and store_path:
        save_cache(_write_json, store_path, store)
    if len(translator) > 2 and callable(translator[2]):
        save_cache(translator[2])
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
    items, statuses = [], []
    if isinstance(tgmeta, (str, Path)):
        from rebang.tgmeta import load_store
        tgmeta = load_store(tgmeta).get('messages', {})
    got, st = telegram_items(db or ROOT / 'tg.db', media_root, by_type.get('telegram', []), now, floor, tgmeta)
    _preserve_tg_success(st, cache, now)
    items += got; statuses += st
    got, st = remote_items(by_type.get('feed', []) + by_type.get('page', []), now, floor, fetch=fetch, cache=cache,
                           http_get=http_get or default_http_get)
    items += got; statuses += st
    _remember_fold_preference(items, floor, inbox_loader or default_inbox_loader)
    if translator == 'default':
        translator = default_translator()
    from rebang.extract import apply_extraction
    extract_cache = Path(cache) / 'extract' if cache else Path(DEFAULT_CACHE) / 'extract'
    extracted = apply_extraction(items, extract_cache, fetch=fetch, http_get=http_get or default_http_get, now=now)
    translated = apply_translation(items, translator, cache)
    unique = {}
    for item in items:
        unique.setdefault(item['id'], item)
    ordered = sorted(unique.values(), key=lambda i: i['published_at'], reverse=True)
    return {'schema': ITEMS_SCHEMA, 'producer': PRODUCER, 'generated_at': _iso(now), 'items': ordered,
            'sources': statuses, 'translation': {'available': bool(translator), 'translated': translated,
                                              'untranslated': sum(1 for i in ordered if not i['lang'].startswith('zh') and i['lang'] != 'und' and not i.get('translated'))},
            'extraction': extracted}


def write_envelope(envelope, out):
    _write_json(Path(out), envelope)
