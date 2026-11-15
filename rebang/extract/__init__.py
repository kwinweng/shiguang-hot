"""公开网页正文抽取（readability 风格）。只抓公开页，不登录、不读 cookie。

成功则把 body / blocks 写回条目（图片按原文顺序留在 blocks 里）；失败或正文没有明显长于现有摘要，
就保持原来的摘要，不编内容。结果按 URL 缓存，刷新时只抓尚未缓存的新条目，并限制单轮抓取次数。
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup, Comment, NavigableString

from rebang.bloggers.common import blocks_text, html_blocks

# 需要登录或明显不是公开文章页的站点：不抓，沿用已有摘要。
SKIP_HOSTS = frozenset({
    't.me', 'www.t.me', 'telegram.me', 'www.telegram.me', 'telegram.org', 'www.telegram.org',
    'x.com', 'www.x.com', 'twitter.com', 'www.twitter.com', 'mobile.twitter.com',
    'weibo.com', 'www.weibo.com', 'm.weibo.cn',
    'mp.weixin.qq.com',
    'accounts.google.com', 'login.microsoftonline.com',
    'github.com', 'www.github.com',  # Trending 链到仓库页，不是文章
    'instagram.com', 'www.instagram.com',
    'facebook.com', 'www.facebook.com', 'm.facebook.com',
})
SKIP_PATH_RE = re.compile(r'(^|/)(login|signin|sign-in|signup|account|auth)(/|$)', re.I)
NAVY = re.compile(r'\b(nav|menu|footer|header|sidebar|comment|share|promo|advert|cookie|subscribe|breadcrumb|related|recommend|popup|modal|social)\b', re.I)
CANDIDATE_SEL = (
    'article', '[role="main"]', 'main', '.post-content', '.article-body', '.article-content',
    '.entry-content', '.story-body', '.StoryBodyCompanionColumn', '#content', '.content__article-body',
    '.l-container', '[itemprop="articleBody"]', '.post__content', '.c-entry-content',
)
UNLINK = re.compile(r'https?://\S+')
WS = re.compile(r'\s+')

# 现有正文已经够长就不再联网；抽出的文字至少要比摘要多这么多才替换。
HAVE_BODY_CHARS = 800
MIN_BODY_CHARS = 400
MIN_GAIN_CHARS = 200
MAX_FETCH_PER_RUN = 40
FAIL_TTL_HOURS = 24


def url_key(url):
    return hashlib.sha256(url.encode('utf-8')).hexdigest()[:32]


def is_public_article_url(url):
    parts = urlsplit(url or '')
    if parts.scheme not in ('http', 'https') or not parts.netloc:
        return False
    host = parts.netloc.lower().split(':')[0]
    if host in SKIP_HOSTS or host.endswith('.onion'):
        return False
    if SKIP_PATH_RE.search(parts.path or ''):
        return False
    return True


def should_extract(item):
    """只处理公开文章页。已有长正文或公众号/博客 blocks 的不再抓。"""
    if not is_public_article_url(item.get('url')):
        return False
    if item.get('kind') == 'post' and item.get('blocks'):
        return False
    if item.get('source_id') == 'github-trending':
        return False
    body = (item.get('body') or '').strip()
    if len(body) >= HAVE_BODY_CHARS:
        return False
    return True


def _drop_noise(soup):
    for tag in soup.find_all(['script', 'style', 'noscript', 'iframe', 'svg', 'form', 'button',
                              'input', 'textarea', 'select', 'nav', 'footer', 'aside', 'header']):
        tag.decompose()
    for c in soup.find_all(string=lambda n: isinstance(n, Comment)):
        c.extract()
    for tag in list(soup.find_all(True)):
        if getattr(tag, 'decomposed', False) or tag.attrs is None:
            continue
        classes = ' '.join(tag.get('class') or [])
        tid = tag.get('id') or ''
        role = tag.get('role') or ''
        if NAVY.search(f'{classes} {tid} {role}') and tag.name not in ('html', 'body'):
            tag.decompose()


def _text_len(node):
    return len(WS.sub(' ', node.get_text(' ', strip=True))) if node else 0


def _link_density(node):
    text = _text_len(node)
    if not text:
        return 1.0
    return sum(_text_len(a) for a in node.find_all('a')) / text


def _score(node):
    text = node.get_text(' ', strip=True)
    if len(text) < 80:
        return 0
    score = len(text) + text.count(',') * 10 + text.count('，') * 10 + len(node.find_all('p')) * 30
    score -= _link_density(node) * 400
    name = ' '.join((node.get('class') or []) + [node.get('id') or '', node.name or ''])
    if re.search(r'article|entry|post|story|content|body', name, re.I):
        score += 80
    if NAVY.search(name):
        score -= 200
    return score


def _best_root(soup):
    for sel in CANDIDATE_SEL:
        for node in soup.select(sel):
            if _text_len(node) >= 200 and _link_density(node) < 0.5:
                return node
    body = soup.body or soup
    best, best_score = None, 0
    for node in body.find_all(['div', 'section', 'article']):
        s = _score(node)
        if s > best_score:
            best, best_score = node, s
    return best or body


def _looks_like_gate(soup, text):
    title = (soup.title.get_text(' ', strip=True) if soup.title else '')[:200]
    head = f'{title}\n{text[:400]}'
    return bool(re.search(
        r'(sign[\s-]?in|log[\s-]?in|subscribe to (continue|read)|create an account|'
        r'paywall|登录|注册后|订阅后阅读|开通会员)',
        head, re.I))


def extract_html(html, url=''):
    """HTML → {body, blocks} 或 None。"""
    if not html or not str(html).strip():
        return None
    soup = BeautifulSoup(html, 'lxml')
    for tag in soup.find_all(['script', 'style', 'noscript']):
        tag.decompose()
    root = _best_root(soup)
    if root is None:
        return None
    work = BeautifulSoup(str(root), 'lxml')
    _drop_noise(work)
    target = work.body or work
    blocks = html_blocks(str(target), base_url=url)
    # 去掉极小的追踪图后若几乎没字，失败
    body = blocks_text(blocks).strip()
    if len(body) < MIN_BODY_CHARS:
        return None
    if _looks_like_gate(soup, body):
        return None
    # 封面图：正文里第一张图
    return {'body': body, 'blocks': blocks}


class ExtractCache:
    def __init__(self, path):
        self.path = Path(path)
        self.entries = {}
        if self.path.exists():
            try:
                self.entries = json.loads(self.path.read_text(encoding='utf-8')).get('entries', {})
            except (ValueError, OSError):
                self.entries = {}

    def get(self, url):
        return self.entries.get(url_key(url))

    def put(self, url, payload):
        self.entries[url_key(url)] = payload

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_name(self.path.name + '.tmp')
        tmp.write_text(json.dumps({'schema': 'rebang.extract-cache/1', 'entries': self.entries},
                                  ensure_ascii=False), encoding='utf-8')
        os.replace(tmp, self.path)


def _fresh_fail(entry, now):
    if not entry or entry.get('ok'):
        return False
    raw = entry.get('fetched_at')
    if not raw:
        return True
    try:
        when = datetime.fromisoformat(raw)
    except ValueError:
        return True
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    return (now - when).total_seconds() < FAIL_TTL_HOURS * 3600


def _apply_hit(item, hit):
    if not hit or not hit.get('ok'):
        return False
    body = (hit.get('body') or '').strip()
    summary = (item.get('summary') or '').strip()
    if len(body) < MIN_BODY_CHARS or len(body) < len(summary) + MIN_GAIN_CHARS:
        return False
    item['body'] = body
    if hit.get('blocks'):
        item['blocks'] = hit['blocks']
        if not item.get('image'):
            img = next((b for b in hit['blocks'] if b.get('type') == 'img' and b.get('src')), None)
            if img:
                image = {'url': img['src']}
                for dim in ('width', 'height'):
                    if isinstance(img.get(dim), int) and img[dim] > 0:
                        image[dim] = img[dim]
                item['image'] = image
    return True


def apply_extraction(items, cache_dir, *, fetch=False, http_get=None, now=None, limit=MAX_FETCH_PER_RUN):
    """给需要全文的条目补 body/blocks。返回统计。"""
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    cache = ExtractCache(Path(cache_dir) / 'pages.json')
    report = {'considered': 0, 'from_cache': 0, 'fetched': 0, 'applied': 0, 'failed': 0, 'skipped': 0}
    iso = now.isoformat()
    for item in items:
        if not should_extract(item):
            continue
        report['considered'] += 1
        url = item['url']
        hit = cache.get(url)
        if hit and (hit.get('ok') or _fresh_fail(hit, now)):
            if _apply_hit(item, hit):
                report['from_cache'] += 1
                report['applied'] += 1
            elif not hit.get('ok'):
                report['failed'] += 1
            continue
        if not fetch or http_get is None or report['fetched'] >= limit:
            report['skipped'] += 1
            continue
        try:
            raw = http_get(url, now)
            html = raw.decode('utf-8', 'replace') if isinstance(raw, (bytes, bytearray)) else str(raw or '')
            got = extract_html(html, url)
        except Exception as ex:
            got, err = None, type(ex).__name__ + (f': {ex}' if str(ex) else '')
            if len(err) > 200:
                err = err[:200]
        else:
            err = 'too_short' if not got else None
        report['fetched'] += 1
        if got:
            cache.put(url, {'url': url, 'ok': True, 'body': got['body'], 'blocks': got['blocks'], 'fetched_at': iso})
            if _apply_hit(item, cache.get(url)):
                report['applied'] += 1
            else:
                report['failed'] += 1
        else:
            cache.put(url, {'url': url, 'ok': False, 'error': err or 'extract_failed', 'fetched_at': iso})
            report['failed'] += 1
    cache.save()
    return report
