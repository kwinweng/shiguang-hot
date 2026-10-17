"""Inbox feeds: find each source's issues on disk, adapt, validate and compress their images.

Delivery format: INGEST.md. Public builds read only public-feeds/; private builds prefer the
original directories on this machine.
"""
import copy, hashlib, json, re
from pathlib import Path
from datetime import date
from urllib.parse import urlsplit
from PIL import Image, ImageOps
from shiguang.config import ROOT, directory
from shiguang.ingest.adapters import adapt


def normalize(data, source):
    """A delivered file in the shared shape; native feeds pass through unchanged."""
    return adapt(data, source) if source.get('adapter', 'native') != 'native' else copy.deepcopy(data)

def image_refs(feed):
    for section in feed.get('sections', []) or []:
        if isinstance(section, dict):
            for item in section.get('items', []) or []:
                if isinstance(item, dict):
                    for im in item.get('images', []) or []:
                        if isinstance(im, dict): yield im, 'file'
    for block in feed.get('blocks', []) or []:
        if isinstance(block, dict) and block.get('type') == 'chart' and block.get('image'):
            if isinstance(block['image'], dict): yield block['image'], 'file'
            else: yield block, 'image'

def safe_image(base, file):
    if not isinstance(file, str) or not file or Path(file).is_absolute(): return None
    p = (base / file).resolve()
    return p if p.is_relative_to(base.resolve()) and p.is_file() and p.suffix.lower() in ('.jpg', '.jpeg', '.png', '.webp') and p.stat().st_size <= 10 * 1024 * 1024 else None

def validate(feed, base, expected=None):
    errors, warnings = [], []
    if not isinstance(feed, dict): return ['根节点必须为对象'], []
    if feed.get('schema') != 'shiguang.feed/1': errors.append('schema 必须为 shiguang.feed/1')
    if not isinstance(feed.get('source'), str) or not re.fullmatch(r'[a-zA-Z0-9_-]+',feed.get('source','')) or (expected and feed.get('source') != expected): errors.append('source 不匹配')
    try:
        day = date.fromisoformat(feed.get('date', ''))
        if day.isoformat() != feed['date']: raise ValueError()
    except (ValueError, TypeError): errors.append('date 必须为 YYYY-MM-DD')
    for field in ('sections', 'blocks'):
        if field in feed and not isinstance(feed[field], list): errors.append(field + ' 必须为数组')
    if errors: return errors, warnings
    if not feed.get('sections') and not feed.get('blocks'): warnings.append('没有内容')
    for section in feed.get('sections', []):
        if not isinstance(section, dict) or not isinstance(section.get('items'), list):
            errors.append('section.items 必须为数组'); continue
        if not isinstance(section.get('title', ''), str): errors.append('section.title 必须为字符串')
        for item in section['items']:
            if not isinstance(item, dict): errors.append('item 必须为对象'); continue
            for field in ('title', 'body', 'link', 'source', 'date', 'topic'):
                if field in item and item[field] is not None and not isinstance(item[field], str): errors.append('item.' + field + ' 必须为字符串')
            if not item.get('title'): warnings.append('条目缺 title，将回退')
            if not item.get('body'): warnings.append('条目缺 body')
            if item.get('link') and urlsplit(str(item['link'])).scheme not in ('http', 'https'): warnings.append('忽略非 HTTP 链接')
            if item.get('images') is not None and not isinstance(item['images'], list): errors.append('images 必须为数组')
            if item.get('sources') is not None and (not isinstance(item['sources'], list) or any(not isinstance(x,str) for x in item['sources'])): errors.append('sources 必须为字符串数组')
    for b in feed.get('blocks', []):
        if not isinstance(b, dict): errors.append('block 必须为对象'); continue
        kind = b.get('type')
        if kind not in ('oneliner', 'markets', 'chart', 'tomorrow'): warnings.append('忽略未知 block: ' + str(kind))
        elif kind != 'chart' and not isinstance(b.get('items'), list): errors.append(kind + '.items 必须为数组')
        elif kind == 'markets' and any(not isinstance(x, dict) for x in b['items']): errors.append('markets.items 元素必须为对象')
        elif kind in ('oneliner','tomorrow') and any(not isinstance(x,(str,dict)) for x in b['items']): errors.append(kind+'.items 元素必须为字符串或对象')
    if errors: return errors, warnings
    for im, key in image_refs(feed):
        p = safe_image(base, im.get(key))
        if p is None: warnings.append('图片缺失、超限或路径非法: ' + str(im.get(key)))
        else:
            try:
                with Image.open(p) as picture: picture.verify()
            except (OSError, ValueError, Image.DecompressionBombError): warnings.append('图片无法解码: ' + str(im.get(key)))
    return errors, warnings

def load_issues(source, local=False):
    roots = [(ROOT / 'public-feeds' / source['id'], 'feed.json', True)]
    if local:
        roots = [(directory(source), source.get('filename', 'feed.json'), False), (Path('/workspace/feeds-inbox') / source['id'], 'feed.json', True)] + roots
    result = {}
    for root, filename, native in roots:
        flat = not native and filename == '{date}.json'
        files = sorted(root.glob('????-??-??.json' if flat else '????-??-??/' + filename), reverse=True)
        if flat and (root / 'latest.json').is_file(): files.append(root / 'latest.json')
        for file in files:
            try:
                d = json.loads(file.read_text())
                day = d.get('date') if flat and file.name == 'latest.json' else file.stem if flat else file.parent.name
                if day in result or (flat and file.name == 'latest.json' and (root / (str(day) + '.json')).exists()): continue
                d = normalize(d, dict(source, adapter='native') if native else source)
                errors, warnings = validate(d, file.parent, source['id'])
                if d.get('date') != day: errors.append('路径日期与 date 不符')
                if errors: print(f'{file}: ' + '; '.join(errors)); continue
                if not any(section.get('items') for section in d.get('sections', [])) and not any(b.get('type') in ('oneliner','markets','tomorrow') and b.get('items') or b.get('type')=='chart' and b.get('image') for b in d.get('blocks', [])): continue
                result[d['date']] = (d, file.parent)
            except (OSError, ValueError, TypeError) as ex: print(f'{file}: {ex}')
    return [result[k] for k in sorted(result, reverse=True)]

def compress_images(feed, base, target, prefix=''):
    d = copy.deepcopy(feed)
    for im, key in image_refs(d):
        p = safe_image(base, im.get(key))
        im[key] = ''
        if p:
            try:
                name = hashlib.sha256(p.read_bytes()).hexdigest()[:24] + '.webp'
                target.mkdir(parents=True, exist_ok=True)
                with Image.open(p) as original:
                    pic = ImageOps.exif_transpose(original).convert('RGB'); pic.thumbnail((1200, 1200))
                    tmp = target / (name + '.tmp'); pic.save(tmp, 'WEBP', quality=80); tmp.replace(target / name)
                im[key] = prefix + name
            except (OSError, ValueError, Image.DecompressionBombError): pass
    return d
