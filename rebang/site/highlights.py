"""Match only events and newsroom identities we can substantiate from the news contract."""
import re
from collections import defaultdict
from datetime import timedelta, timezone
from itertools import combinations
from urllib.parse import urlsplit

from rebang.site.dedup import norm_title, norm_url
from rebang.site.events import conflicts_with_report, event_key

# Keys identify configured editorial feeds. Each value lists the publisher's own article hosts.
# A repost account or a link on a shared platform cannot establish editorial provenance.
_NEWSROOMS = {
    'bbc-world': {'bbc.com', 'bbc.co.uk'},
    'guardian-world': {'theguardian.com'},
    'cna-world': {'channelnewsasia.com'},
    'france24-en': {'france24.com'},
    'dw-world': {'dw.com'},
    'npr-world': {'npr.org'},
    'android-authority': {'androidauthority.com'},
    'macrumors': {'macrumors.com'},
    'selfhst': {'selfh.st'},
    'itsfoss': {'itsfoss.com'},
}

_REPUBLICATION = re.compile(
    r'\b(?:Reuters|Associated Press|AFP|AP News|dpa|Agence France[- ]Presse|'
    r'originally (?:published|appeared)|republish(?:ed|ing)|syndicat(?:ed|ion)|'
    r'(?:reporting|reported|written|provided|published|translated) by|(?:according|credit) to)\b|\(AP\)|'
    r'\b(?:source|via|byline|credit|author|reprinted from|adapted from)\s*[:：]|'
    r'\b(?-i:[A-Z][\w’\'-]*(?: [A-Z][\w’\'-]*)*) (?:reports?|reported|reported that)\b|'
    r'(?:^|[.。\n]\s*)By\s+(?:the\s+)?(?-i:[A-Z])|'
    r'路透社|美联社|法新社|德新社|转载|转引|编译自|引自|转述自|'
    r'(?:来源|出处|作者|署名|稿源|供稿|采编|编译|撰文|记者)\s*[:：]|'
    r'据[^，。！？；\n]{1,36}?(?:报道|消息|披露|刊载)', re.I)
_UNCERTAINTY = re.compile(
    r'\b(?:beta|release candidate|rumou?rs?|unconfirmed|reportedly|den(?:y|ies|ied)|'
    r'correction|not|never|may|might|expected|allegedly)\b|n[’\']t\b|\byet\s+to\b|[?？]|'
    r'传闻|据传|据称|未经证实|尚未|仍未|并未|未能|否认|预计|测试版|候选版', re.I)
# Han text is usually unspaced. Use character windows for it and word windows elsewhere.
_HAN = r'\u3400-\u9fff'
_WORD = re.compile(rf'[^\W{_HAN}]+')
_HAN_WORDS = re.compile(rf'[{_HAN}]+')
_COPY_WORDS = 8


def _report_text(item):
    parts = [item['summary'], item.get('body') or '']
    for block in item.get('blocks') or []:
        if block['type'] in ('p', 'h', 'quote', 'pre'):
            parts.append(block['text'])
        elif block['type'] in ('ul', 'ol'):
            parts.extend(block['items'])
    return '\n'.join(part for part in parts if isinstance(part, str))


def _passages(text):
    """A shared verbatim passage makes independent authorship too uncertain to count the pair."""
    words = _WORD.findall(text.casefold())
    passages = {tuple(words[i:i + _COPY_WORDS]) for i in range(len(words) - _COPY_WORDS + 1)}
    han = ''.join(_HAN_WORDS.findall(text))
    width = 16
    passages.update(han[i:i + width] for i in range(len(han) - width + 1))
    return passages


def corroborated_ids(news, now, parse_time):
    """Return eligible report IDs plus direct copies of those exact reports."""
    now = now.astimezone(timezone.utc)
    floor = now - timedelta(hours=24)
    candidates = defaultdict(list)
    copies = defaultdict(set)
    for item in news:
        if item.get('published_at_verified') is False:
            continue
        when = parse_time(item['published_at'])
        if when is None or not floor <= when <= now:
            continue
        title = norm_title(item['title'])
        if _UNCERTAINTY.search(title):
            continue
        event = event_key(title)
        if event is None:
            continue
        url = norm_url(item['url'])
        if not url:
            continue
        text = _report_text(item)
        if _UNCERTAINTY.search(text) or conflicts_with_report(event, text):
            continue
        copies[url, title].add(item['id'])
        publisher = item['source_id']
        if (urlsplit(url).netloc not in _NEWSROOMS.get(publisher, ())
                or item.get('quote') or item.get('feed_attribution') or _REPUBLICATION.search(title + '\n' + text)):
            continue
        passages = _passages(text)
        if passages:
            candidates[event].append((publisher, url, title, passages))

    result = set()
    for reports in candidates.values():
        if len({report[0] for report in reports}) < 2:
            continue
        for (publisher, url, title, text), (other, other_url, other_title, other_text) in combinations(reports, 2):
            if (publisher != other and url != other_url and title.casefold() != other_title.casefold()
                    and text.isdisjoint(other_text)):
                result.update(copies[url, title], copies[other_url, other_title])
    return result
