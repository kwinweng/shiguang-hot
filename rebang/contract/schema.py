"""统一条目 / 热搜 / 博主卡片的校验。只用标准库，返回错误列表，不抛异常（除 ContractError 便捷包装）。"""
import json
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlsplit

HERE = Path(__file__).resolve().parent
ITEMS_SCHEMA = 'rebang.items/1'
HOTSEARCH_SCHEMA = 'rebang.hotsearch/1'
KINDS = ('news', 'post')
PROVIDER_STATUS = ('ok', 'empty', 'error')
MEDIA_TYPES = ('image', 'video', 'gif', 'youtube')   # youtube：url 是 youtube-nocookie 嵌入地址，preview_url 是封面
METRIC_KEYS = ('reply', 'repost', 'like', 'quote', 'bookmark', 'view')
MT_LABEL = '机器翻译'


class ContractError(ValueError):
    pass


@lru_cache(maxsize=None)
def _load(name):
    return json.loads((HERE / f'{name}.json').read_text(encoding='utf-8'))


def load_channels():
    return _load('channels')


def load_hotsearch():
    return _load('hotsearch')


def load_bloggers():
    return _load('bloggers')


def channel_slugs():
    return [c['slug'] for c in sorted(load_channels()['channels'], key=lambda c: c['order'])]


def source_channel(source_id):
    """来源 id → 频道 slug；不在表里返回 None。"""
    for channel in load_channels()['channels']:
        for source in channel['sources']:
            if source['id'] == source_id:
                return channel['slug']
    return None


def _is_url(value, allow_empty=True):
    if value == '' and allow_empty:
        return True
    return isinstance(value, str) and urlsplit(value).scheme in ('http', 'https') and bool(urlsplit(value).netloc)


def _is_aware_iso(value):
    if not isinstance(value, str):
        return False
    try:
        moment = datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError:
        return False
    return moment.tzinfo is not None


def _str(item, key, errors, where, required=True):
    if key not in item:
        if required:
            errors.append(f'{where}: 缺 {key}')
        return
    if not isinstance(item[key], str):
        errors.append(f'{where}: {key} 必须是字符串')


def _image(value, errors, where):
    if value is None:
        return
    if not isinstance(value, dict) or not _is_url(value.get('url'), allow_empty=False):
        errors.append(f'{where}: image 必须是 {{url, width?, height?}} 且 url 为 http(s)')
        return
    for dim in ('width', 'height'):
        if dim in value and not (isinstance(value[dim], int) and value[dim] > 0):
            errors.append(f'{where}: image.{dim} 必须是正整数')


def _blogger(value, errors, where):
    if not isinstance(value, dict):
        errors.append(f'{where}: post 必须带 blogger 对象')
        return
    platforms = {p['id'] for p in load_bloggers()['platforms']}
    if value.get('platform') not in platforms:
        errors.append(f'{where}: blogger.platform 不在 bloggers.json')
    for key in ('handle', 'display_name'):
        _str(value, key, errors, f'{where}.blogger')
    if 'avatar' in value and value['avatar'] is not None and not _is_url(value['avatar'], allow_empty=False):
        errors.append(f'{where}: blogger.avatar 必须是 http(s) 或 null')
    if 'verified' in value and not isinstance(value['verified'], bool):
        errors.append(f'{where}: blogger.verified 必须是布尔')
    for key, number in (value.get('metrics') or {}).items():
        if key not in METRIC_KEYS or not (isinstance(number, int) and number >= 0):
            errors.append(f'{where}: blogger.metrics.{key} 非法（只认 {METRIC_KEYS}，非负整数；没有就不写）')
    for index, media in enumerate(value.get('media') or []):
        if not isinstance(media, dict) or media.get('type') not in MEDIA_TYPES or not _is_url(media.get('url'), allow_empty=False):
            errors.append(f'{where}: blogger.media[{index}] 需 type∈{MEDIA_TYPES} 与 http(s) url')
    quote = value.get('quote')
    if quote is not None and not (isinstance(quote, dict) and quote.get('text') and quote.get('handle')):
        errors.append(f'{where}: blogger.quote 只有拿到完整引用（handle+text）才写，否则为 null')
    # quote 允许附带 display_name/avatar/published_at/url/media 等字段，不校验多出来的键
    comments = value.get('comments')
    if comments is not None:
        if not isinstance(comments, list):
            errors.append(f'{where}: blogger.comments 必须是数组')
        else:
            for index, comment in enumerate(comments):
                if not (isinstance(comment, dict) and isinstance(comment.get('text'), str) and comment.get('handle')):
                    errors.append(f'{where}: blogger.comments[{index}] 需 handle + text')


def _image_local(value, errors, where):
    """ingest 的本地图：{path, rel?, width?, height?, alt?}。站点构建时复制进 site/media/，改写成相对地址 image.url。"""
    if value is None:
        return
    if not isinstance(value, dict) or not isinstance(value.get('path'), str) or not value['path']:
        errors.append(f'{where}: image_local 必须是 {{path, rel?, width?, height?, alt?}}')
        return
    rel = value.get('rel')
    if rel is not None and (not isinstance(rel, str) or rel.startswith('/') or '..' in rel.split('/')):
        errors.append(f'{where}: image_local.rel 必须是不含 .. 的相对路径')
    for dim in ('width', 'height'):
        if dim in value and not (isinstance(value[dim], int) and value[dim] > 0):
            errors.append(f'{where}: image_local.{dim} 必须是正整数')


QUOTE_KINDS = ('reply', 'forward')
BLOCK_TYPES = ('p', 'h', 'quote', 'ul', 'ol', 'img', 'pre', 'hr')


def _nonneg_int(v):
    return isinstance(v, int) and not isinstance(v, bool) and v >= 0


def _news_quote(value, errors, where):
    """TG 引用（回复）/转发：{kind, source_name, url, text}。只写页面上真有的原帖。"""
    if value is None:
        return
    if not isinstance(value, dict) or value.get('kind') not in QUOTE_KINDS or not isinstance(value.get('text'), str) \
            or not isinstance(value.get('source_name'), str) or not _is_url(value.get('url', '')):
        errors.append(f'{where}: quote 必须是 {{kind∈{QUOTE_KINDS}, source_name, url(http(s)/空), text}}')


def _tg(value, errors, where):
    """TG 公开页面上的互动：views(+views_label)、reactions[{emoji,count,label}]、comments_total、comments[{display_name,text}]。"""
    if value is None:
        return
    if not isinstance(value, dict):
        errors.append(f'{where}: tg 必须是对象')
        return
    if 'media' in value:
        media = value['media']
        if not isinstance(media, list):
            errors.append(f'{where}: tg.media 必须是数组')
        else:
            for i, m in enumerate(media):
                if not (isinstance(m, dict) and m.get('type') in ('image', 'video')
                        and _is_url(m.get('url'), allow_empty=False)
                        and _is_url(m.get('preview_url', ''))):
                    errors.append(f'{where}: tg.media[{i}] 必须是带 http(s) 地址的图片或视频')
    if 'video_unavailable' in value and not isinstance(value['video_unavailable'], bool):
        errors.append(f'{where}: tg.video_unavailable 必须是布尔')
    if 'views' in value and not _nonneg_int(value['views']):
        errors.append(f'{where}: tg.views 必须是非负整数')
    for i, r in enumerate(value.get('reactions') or []):
        if not (isinstance(r, dict) and isinstance(r.get('emoji'), str) and r['emoji'] and _nonneg_int(r.get('count'))):
            errors.append(f'{where}: tg.reactions[{i}] 需 emoji + 非负整数 count')
    if 'comments_total' in value and not _nonneg_int(value['comments_total']):
        errors.append(f'{where}: tg.comments_total 必须是非负整数')
    for i, c in enumerate(value.get('comments') or []):
        if not (isinstance(c, dict) and isinstance(c.get('display_name'), str) and isinstance(c.get('text'), str) and c['text']):
            errors.append(f'{where}: tg.comments[{i}] 需 display_name + text')


def _blocks(value, errors, where):
    """按原文顺序的正文块（公众号/博客）：p/h/quote/pre 带 text；ul/ol 带 items；img 带 http(s) src；hr 无内容。"""
    if value is None:
        return
    if not isinstance(value, list):
        errors.append(f'{where}: blocks 必须是数组')
        return
    for i, b in enumerate(value):
        t = b.get('type') if isinstance(b, dict) else None
        ok = t in BLOCK_TYPES
        if ok and t in ('p', 'h', 'quote', 'pre'):
            ok = isinstance(b.get('text'), str) and bool(b['text'].strip())
        elif ok and t in ('ul', 'ol'):
            ok = isinstance(b.get('items'), list) and all(isinstance(x, str) for x in b['items']) and bool(b['items'])
        elif ok and t == 'img':
            ok = _is_url(b.get('src', ''), allow_empty=False)
        if not ok:
            errors.append(f'{where}: blocks[{i}] 不合格（type∈{BLOCK_TYPES}）')


def validate_item(item, where='item'):
    errors = []
    if not isinstance(item, dict):
        return [f'{where}: 必须是对象']
    for key in ('id', 'kind', 'source_id', 'source_name', 'title', 'summary', 'url', 'published_at', 'lang'):
        _str(item, key, errors, where)
    if errors:
        return errors
    kind = item['kind']
    if kind not in KINDS:
        errors.append(f'{where}: kind 必须是 {KINDS}')
    if not item['id'].startswith(item['source_id'] + ':'):
        errors.append(f'{where}: id 必须是 "<source_id>:<native_id>"')
    if not _is_url(item['url']):
        errors.append(f'{where}: url 只允许 http(s) 或空串')
    if not _is_aware_iso(item['published_at']):
        errors.append(f'{where}: published_at 必须是带时区的 ISO 8601')
    if 'fetched_at' in item and not _is_aware_iso(item['fetched_at']):
        errors.append(f'{where}: fetched_at 必须是带时区的 ISO 8601')
    if kind == 'news':
        if item.get('channel') not in channel_slugs():
            errors.append(f'{where}: news 的 channel 必须是 {channel_slugs()}')
        else:
            expected = source_channel(item['source_id'])
            highlight_src = load_channels()['highlights']['source_id']
            if expected is None and item['source_id'] != highlight_src:
                errors.append(f'{where}: source_id {item["source_id"]} 不在 channels.json')
            elif expected is not None and expected != item['channel']:
                errors.append(f'{where}: {item["source_id"]} 只能进 {expected}，不能进 {item["channel"]}')
        if not item['title'].strip():
            errors.append(f'{where}: news 必须有标题')
        if 'blogger' in item:
            errors.append(f'{where}: news 不能带 blogger')
        _news_quote(item.get('quote'), errors, where)
        _tg(item.get('tg'), errors, where)
    if kind == 'post':
        if item.get('channel') is not None:
            errors.append(f'{where}: 博主帖子不进资讯频道，channel 必须为 null 或不写')
        _blogger(item.get('blogger'), errors, where)
    _blocks(item.get('blocks'), errors, where)
    _image(item.get('image'), errors, where)
    _image_local(item.get('image_local'), errors, where)
    translated = item.get('translated', False)
    if not isinstance(translated, bool):
        errors.append(f'{where}: translated 必须是布尔')
    translation = item.get('translation')
    if translated:
        if item['lang'].startswith('zh'):
            errors.append(f'{where}: 中文原文不翻译、不打机器翻译标')
        if not isinstance(translation, dict) or not isinstance(translation.get('title'), str) \
                or not isinstance(translation.get('summary'), str):
            errors.append(f'{where}: translated=true 必须带 translation{{title, summary, body?, engine, label}}')
        elif translation.get('label') != MT_LABEL or not translation.get('engine'):
            errors.append(f'{where}: translation.label 必须是「{MT_LABEL}」且写明 engine')
    elif translation is not None:
        errors.append(f'{where}: 未翻译时 translation 必须为 null 或不写')
    if 'highlight' in item and not isinstance(item['highlight'], bool):
        errors.append(f'{where}: highlight 必须是布尔')
    return errors


def validate_items_envelope(envelope):
    if not isinstance(envelope, dict) or envelope.get('schema') != ITEMS_SCHEMA:
        return [f'envelope: schema 必须是 {ITEMS_SCHEMA}']
    errors = []
    _str(envelope, 'producer', errors, 'envelope')
    if not _is_aware_iso(envelope.get('generated_at')):
        errors.append('envelope: generated_at 必须带时区')
    for key in ('sources', 'platforms'):
        rows = envelope.get(key)
        if rows is None:
            continue
        if not isinstance(rows, list) or not all(isinstance(r, dict) and r.get('id') and r.get('status') for r in rows):
            errors.append(f'envelope: {key} 必须是 [{{id, status, ...}}]')
    items = envelope.get('items')
    if not isinstance(items, list):
        return errors + ['envelope: items 必须是数组']
    seen = set()
    for index, item in enumerate(items):
        errors += validate_item(item, f'items[{index}]')
        if isinstance(item, dict):
            if item.get('id') in seen:
                errors.append(f'items[{index}]: id 重复 {item.get("id")}')
            seen.add(item.get('id'))
    return errors


def validate_hotsearch(payload):
    if not isinstance(payload, dict) or payload.get('schema') != HOTSEARCH_SCHEMA:
        return [f'hotsearch: schema 必须是 {HOTSEARCH_SCHEMA}']
    errors = []
    if not _is_aware_iso(payload.get('generated_at')):
        errors.append('hotsearch: generated_at 必须带时区')
    known = {p['id'] for p in load_hotsearch()['providers']}
    cap = load_hotsearch()['max_items_per_provider']
    for pi, provider in enumerate(payload.get('providers') or []):
        where = f'providers[{pi}]'
        if provider.get('id') not in known:
            errors.append(f'{where}: id 不在 hotsearch.json')
        if provider.get('status') not in PROVIDER_STATUS:
            errors.append(f'{where}: status 必须是 {PROVIDER_STATUS}')
        items = provider.get('items')
        if not isinstance(items, list):
            errors.append(f'{where}: items 必须是数组')
            continue
        if provider.get('status') == 'ok' and not items:
            errors.append(f'{where}: status=ok 时 items 不能为空')
        if provider.get('status') != 'ok' and items:
            errors.append(f'{where}: 失败/空时 items 必须为空（不编排名，不留旧榜冒充今天）')
        if len(items) > cap:
            errors.append(f'{where}: 超过 {cap} 条')
        if provider.get('fetched_at') is not None and not _is_aware_iso(provider['fetched_at']):
            errors.append(f'{where}: fetched_at 必须带时区')
        for ii, entry in enumerate(items):
            w = f'{where}.items[{ii}]'
            if not (isinstance(entry.get('rank'), int) and entry['rank'] >= 1):
                errors.append(f'{w}: rank 必须 >= 1')
            if not isinstance(entry.get('title'), str) or not entry['title'].strip():
                errors.append(f'{w}: 必须有 title')
            if not _is_url(entry.get('url', ''), allow_empty=False):
                errors.append(f'{w}: url 必须是 http(s)')
            if not isinstance(entry.get('pinned', False), bool):
                errors.append(f'{w}: pinned 必须是布尔')
            if 'image' in entry and entry['image'] is not None and not _is_url(entry['image'], allow_empty=False):
                errors.append(f'{w}: image 必须是 http(s) 或 null')
    return errors
