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
    # 摘要只是正文截短时只译正文，再从译文截出摘要，避免同一段话译两遍
    derive_summary = 'body' in keys and 'summary' in keys and item['summary'] == summary_of(item['body'])
    if derive_summary:
        keys.remove('summary')
    if not keys:
        return item
    result = translator.translate_detailed([item[k] for k in keys], item['lang'])
    if result is None:
        return item
    texts, engine = result
    translation = {'title': '', 'summary': ''}
    translation.update(dict(zip(keys, texts)))
    if derive_summary:
        translation['summary'] = summary_of(translation['body'])
    translation['engine'] = engine
    translation['label'] = '机器翻译'
    item['translated'] = True
    item['translation'] = translation
    return item


# ---------- 按原文顺序的正文块（公众号 / 博客文章页忠实还原：段落、标题、图片、引用、列表） ----------

_SKIP_TAGS = {'script', 'style', 'noscript', 'iframe', 'svg', 'form', 'button', 'input', 'mp-common-profile',
              'mpprofile', 'mp-common-videosnap', 'video', 'audio'}
_INLINE_TAGS = {'span', 'strong', 'b', 'em', 'i', 'a', 'code', 'sup', 'sub', 'u', 's', 'font', 'mark', 'small',
                'big', 'abbr', 'cite', 'q', 'del', 'ins', 'label', 'time', 'mp-style-type', 'tt', 'var'}
_HEADING = {'h1', 'h2', 'h3', 'h4', 'h5', 'h6'}
MAX_BLOCKS = 600


def unwrap_image_url(src):
    """Wechat2RSS 的 img-proxy/?u=<原图> 拆回公众号原图地址（img-proxy 在 Cloudflare 后面，手机上常打不开）。"""
    from urllib.parse import parse_qs
    parts = urlsplit(src)
    if parts.path.rstrip('/').endswith('img-proxy'):
        inner = (parse_qs(parts.query).get('u') or [''])[0]
        if urlsplit(inner).scheme in ('http', 'https'):
            return inner
    return src


def _img_block(img, base_url):
    src = (img.get('data-src') or img.get('src') or '').strip()
    src = urljoin(base_url, src) if src else ''
    if urlsplit(src).scheme not in ('http', 'https'):
        return None
    dims = {}
    for key in ('width', 'height'):
        raw = str(img.get(key) or '').strip()
        if raw.isdigit() and int(raw) > 0:
            dims[key] = int(raw)
    if dims.get('width', 99) <= 2 or dims.get('height', 99) <= 2:
        return None      # 1px 追踪图
    block = {'type': 'img', 'src': unwrap_image_url(src)}
    ratio = img.get('data-ratio')
    w = img.get('data-w')
    if w and str(w).isdigit():
        block['width'] = int(w)
        try:
            block['height'] = max(1, round(int(w) * float(ratio)))
        except (TypeError, ValueError):
            pass
    if img.get('alt') and img.get('alt').strip():
        block['alt'] = img['alt'].strip()
    return block


WECHAT_TAIL = ('跳转微信打开', '阅读原文')


def html_blocks(html, base_url='', wechat=False):
    """HTML → [{type:p|h|quote|ul|ol|img|pre|hr, ...}]，严格按文档顺序；一张图只在它原来的位置出现一次。
    wechat=True：去掉 Wechat2RSS 在开头加的「原创 / 作者 / 日期 / 属地」行和它额外插的封面图（原文正文里没有）。"""
    if not html:
        return []
    soup = BeautifulSoup(html, 'html.parser')
    blocks, buf = [], []

    def flush():
        text = normalize_text(''.join(buf))
        buf.clear()
        if text:
            blocks.append({'type': 'p', 'text': text})

    def inline_text(node):
        node = BeautifulSoup(str(node), 'html.parser')
        for br in node.find_all('br'):
            br.replace_with('\n')
        for tag in node(list(_SKIP_TAGS)):
            tag.decompose()
        return normalize_text(node.get_text(''))

    def walk(node):
        for child in node.children:
            name = getattr(child, 'name', None)
            if name is None:
                if type(child).__name__ in ('Comment', 'Doctype', 'Declaration', 'ProcessingInstruction'):
                    continue
                buf.append(str(child))
                continue
            if name in _SKIP_TAGS:
                continue
            if name == 'br':
                buf.append('\n')
            elif name == 'img':
                flush()
                block = _img_block(child, base_url)
                if block:
                    blocks.append(block)
            elif name in _HEADING:
                flush()
                text = inline_text(child)
                if text:
                    blocks.append({'type': 'h', 'level': int(name[1]), 'text': text})
                for img in child.find_all('img'):
                    block = _img_block(img, base_url)
                    if block:
                        blocks.append(block)
            elif name == 'blockquote':
                flush()
                parts = []
                for p in child.find_all(['p', 'section'], recursive=True) or [child]:
                    if p.find(['p', 'section']):
                        continue
                    t = inline_text(p)
                    if t:
                        parts.append(t)
                text = '\n'.join(parts) if parts else inline_text(child)
                if text:
                    blocks.append({'type': 'quote', 'text': text})
                for img in child.find_all('img'):
                    block = _img_block(img, base_url)
                    if block:
                        blocks.append(block)
            elif name in ('ul', 'ol'):
                flush()
                items = [inline_text(li) for li in child.find_all('li', recursive=False)]
                items = [t for t in items if t]
                if items:
                    blocks.append({'type': name, 'items': items})
                for img in child.find_all('img'):
                    block = _img_block(img, base_url)
                    if block:
                        blocks.append(block)
            elif name == 'pre':
                flush()
                text = child.get_text('').strip('\n')
                if text.strip():
                    blocks.append({'type': 'pre', 'text': text})
            elif name == 'hr':
                flush()
                blocks.append({'type': 'hr'})
            elif name in _INLINE_TAGS:
                walk(child)
            else:            # p / section / div / figure / table …：块级，前后断段
                flush()
                walk(child)
                flush()
    walk(soup)
    flush()
    if wechat:
        # 开头：Wechat2RSS 插入的「原创 作者 日期 属地」行
        while blocks and blocks[0]['type'] == 'p' and len(blocks[0]['text']) <= 60 and (
                blocks[0]['text'].startswith('原创') or re.search(r'\d{4}-\d{2}-\d{2}', blocks[0]['text'])):
            blocks.pop(0)
        # 紧接着的一张图若不是正文图（公众号正文图都带 data-w/rich_pages），是 Wechat2RSS 加的封面
        first_imgs = soup.find_all('img', limit=1)
        if blocks and blocks[0]['type'] == 'img' and first_imgs and not first_imgs[0].get('data-w') \
                and 'rich_pages' not in (first_imgs[0].get('class') or []):
            blocks.pop(0)
        # 结尾：Wechat2RSS 追加的「跳转微信打开」链接（原文正文里没有）
        while blocks and blocks[-1]['type'] == 'p' and blocks[-1]['text'].strip() in WECHAT_TAIL:
            blocks.pop()
    return blocks[:MAX_BLOCKS]


def blocks_text(blocks):
    """正文块 → 纯文本（搜索、翻译、摘要用），图片不进文本。"""
    out = []
    for b in blocks or []:
        if b['type'] in ('p', 'h', 'quote', 'pre'):
            out.append(b['text'])
        elif b['type'] in ('ul', 'ol'):
            out.extend(('• ' if b['type'] == 'ul' else f'{i}. ') + t for i, t in enumerate(b['items'], 1))
    return '\n\n'.join(out)
