"""博主条目的公共工具：纯文本化、语言判断、时间、条目组装。只用标准库 + bs4。"""
import hashlib
import re
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import urljoin, urlsplit
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup

BJT = ZoneInfo('Asia/Shanghai')
SUMMARY_CHARS = 200
BODY_CHARS = 20000
_CJK = re.compile(r'[\u3400-\u9fff\uf900-\ufaff]')
_LATIN = re.compile(r'[A-Za-z]')


def now_bjt():
    return datetime.now(BJT).replace(microsecond=0)


def iso(moment):
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(BJT).replace(microsecond=0).isoformat()


def parse_time(value):
    """ISO 8601 / RFC 822 → 带时区 datetime；解析不了返回 None（不编时间）。"""
    if not value or not isinstance(value, str):
        return None
    value = value.strip()
    try:
        moment = datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError:
        try:
            moment = parsedate_to_datetime(value)
        except (TypeError, ValueError, IndexError):
            return None
    if moment is None:
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment


def html_to_text(html):
    if not html:
        return ''
    soup = BeautifulSoup(html, 'html.parser')
    for tag in soup(['script', 'style', 'noscript', 'iframe', 'svg', 'form']):
        tag.decompose()
    for br in soup.find_all('br'):
        br.replace_with('\n')
    text = soup.get_text('\n')
    return normalize_text(text)


def normalize_text(text):
    text = (text or '').replace('\r', '').replace('\xa0', ' ')
    lines = [re.sub(r'[ \t]+', ' ', line).strip() for line in text.split('\n')]
    out, blank = [], False
    for line in lines:
        if not line:
            blank = bool(out)
            continue
        if blank:
            out.append('')
        out.append(line)
        blank = False
    return '\n'.join(out).strip()


def clip(text, limit):
    text = text or ''
    if len(text) <= limit:
        return text
    cut = text[:limit].rstrip()
    return cut + '…'


def summary_of(text):
    """卡片 3 行摘要：正文前几行压成一段，截到 SUMMARY_CHARS。没有正文就空串，不编。"""
    flat = re.sub(r'\s+', ' ', text or '').strip()
    return clip(flat, SUMMARY_CHARS)


def detect_lang(*texts):
    """粗判语言：去掉链接后，汉字数 ×4 ≥ 拉丁字母数 视为中文。"""
    sample = re.sub(r'https?://\S+', ' ', ' '.join(t for t in texts if t))[:4000]
    cjk = len(_CJK.findall(sample))
    latin = len(_LATIN.findall(sample))
    if cjk == 0 and latin == 0:
        return 'zh'
    return 'zh' if cjk * 4 >= latin else 'en'


def html_images(html, base_url='', limit=4):
    """正文里真实出现的图片（http(s)），跳过 1px 追踪图和 data: 图。"""
    if not html:
        return []
    soup = BeautifulSoup(html, 'html.parser')
    out = []
    for img in soup.find_all('img'):
        src = img.get('src') or img.get('data-src') or ''
        src = urljoin(base_url, src.strip()) if src else ''
        if urlsplit(src).scheme not in ('http', 'https'):
            continue
        dims = {}
        for key in ('width', 'height'):
            raw = str(img.get(key) or '').strip()
            if raw.isdigit() and int(raw) > 0:
                dims[key] = int(raw)
        if dims.get('width', 99) <= 2 or dims.get('height', 99) <= 2:
            continue
        if src not in [m['url'] for m in out]:
            out.append({'url': src, **dims})
        if len(out) >= limit:
            break
    return out


def native_id(guid, url):
    guid = (guid or '').strip()
    if guid:
        return guid
    return hashlib.sha1((url or '').encode('utf-8')).hexdigest()[:16]


def source_id(platform, handle):
    return f'{platform}-{handle}'


def apply_translation(item, translator, fields=('title', 'summary', 'body')):
    """非中文条目入库时翻译；失败 → translated=false，不编译文。"""
    item['translated'] = False
    if item['lang'].startswith('zh') or translator is None:
        return item
    keys = [k for k in fields if item.get(k)]
    if not keys:
        return item
    result = translator.translate_detailed([item[k] for k in keys], item['lang'])
    if result is None:
        return item
    texts, engine = result
    translation = {'title': '', 'summary': ''}
    translation.update(dict(zip(keys, texts)))
    translation['engine'] = engine
    translation['label'] = '机器翻译'
    item['translated'] = True
    item['translation'] = translation
    return item
