"""Chinese-first public projection for official web news; never mutate source snapshots."""
import re
from functools import lru_cache

from rebang.contract import load_channels

_URL = re.compile(r'https?://[^\s《》「」“”‘’，。、；：！？（）【】<>]+')
_HAN = re.compile(r'[㐀-鿿]')
_LATIN_WORD = re.compile(r'[A-Za-zÀ-ÖØ-öø-ÿ]+')
_LATIN_PROSE = re.compile(r'\b[a-z]{2,}(?:[ \t]+[a-z]{2,}){2,}\b', re.I)
_REPO = re.compile(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+\Z')


@lru_cache(maxsize=1)
def web_sources():
    return frozenset(source['id'] for channel in load_channels()['channels'] for source in channel['sources']
                     if source['type'] in ('feed', 'page'))


def is_web_news(item):
    return item.get('kind') == 'news' and item.get('source_id') in web_sources()


def chinese_text(text):
    """Conservative check, not language detection: reject English prose and untranslated lines.

    Allow terms like BBC and AI in Chinese text, as well as separate URLs and numeric lines.
    """
    if not isinstance(text, str) or not _HAN.search(_URL.sub('', text)):
        return False
    return all(not _LATIN_PROSE.search(line) and len(_LATIN_WORD.findall(line)) <= max(3, len(_HAN.findall(line)))
               and (not _LATIN_WORD.search(line) or _HAN.search(line)) for line in _URL.sub('', text).split('\n'))


def _block_texts(blocks, *, captions=False):
    for block in blocks or ():
        if not isinstance(block, dict):
            continue
        kind = block.get('type')
        if kind in ('p', 'h', 'quote', 'pre'):
            yield block.get('text')
        elif kind in ('ul', 'ol'):
            yield from block.get('items') or ()
        elif captions and kind == 'img':
            yield block.get('alt')


def has_text(text):
    return isinstance(text, str) and bool(_URL.sub('', text).strip())


def _all_chinese(texts):
    return all(not has_text(text) or chinese_text(text) for text in texts)


def _repo_title(item):
    return item.get('source_id') == 'github-trending' and bool(_REPO.fullmatch(item.get('title') or ''))


def native_preview(item):
    native_title = (item.get('lang') or '').startswith('zh') and chinese_text(item.get('title'))
    return (native_title or _repo_title(item)) and _all_chinese([item.get('summary')])


def native_body(item):
    blocks = item.get('blocks')
    return _all_chinese(_block_texts(blocks, captions=True) if blocks else [item.get('body')])


def needs_translation(item):
    if not is_web_news(item):
        return False
    return not native_preview(item) or not native_body(item)


def _safe_blocks(blocks):
    return (isinstance(blocks, list) and bool(blocks)
            and all(isinstance(b, dict) and b.get('type') in ('p', 'h', 'quote', 'ul', 'ol', 'hr', 'img')
                    for b in blocks)
            and any(chinese_text(t) for t in _block_texts(blocks))
            and _all_chinese(_block_texts(blocks, captions=True)))


def public_item(item):
    """Return a safe public rendition or None. Raw originals remain for explicit expansion only."""
    if not is_web_news(item):
        return item
    if not needs_translation(item):
        # An old translation must not override valid original Chinese.
        return {**item, 'translated': False, 'translation': None} if item.get('translated') else item
    raw = item.get('translation')
    tr = dict(raw) if item.get('translated') is True and isinstance(raw, dict) else {}
    native = native_preview(item)
    if native:
        if not tr or not (chinese_text(tr.get('body')) or _safe_blocks(tr.get('blocks'))):
            return {**item, 'translated': False, 'translation': None}
        tr.update(title=item['title'], summary=item.get('summary') or '')
    elif _repo_title(item):
        tr['title'] = item['title']
    elif not chinese_text(tr.get('title')):
        return None
    if not native and has_text(item.get('summary')) and (
            not chinese_text(tr.get('summary')) or tr.get('summary_source') != item.get('summary')):
        return None
    if not chinese_text(tr.get('summary')):
        tr['summary'] = ''
    if not chinese_text(tr.get('body')):
        tr.pop('body', None)
    if not _safe_blocks(tr.get('blocks')):
        tr.pop('blocks', None)
    if (item.get('body') or item.get('blocks')) and not (tr.get('body') or tr.get('blocks')):
        tr['body_pending'] = True
    else:
        tr.pop('body_pending', None)
    # A bare GitHub identifier is not itself translated.
    if not raw and not tr['summary']:
        tr.update(engine='source', label='机器翻译')
    return {**item, 'translated': True, 'translation': tr}
