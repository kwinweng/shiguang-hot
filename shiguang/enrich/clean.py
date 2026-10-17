"""Turn raw Telegram message text into a clean headline and body for the cards."""
import re
from bs4 import BeautifulSoup

AD = re.compile(r'-{3,}\s*本条新闻由.*', re.S)
URL = re.compile(r'[‎‏]?https?://\S+')
DIVIDER = re.compile(r'^[=＝\-—_~·*]{4,}$', re.M)  # "========" lines some channels use between title and body
INLINE_DIVIDER = re.compile(r'\s*[=＝]{4,}\s*')
SENTENCE_END = re.compile(r'[。！？\n]')
TITLE_LIMIT = 86


def clean(text):
    text = AD.sub('', text)
    # 华尔街见闻把话题写成 " #美国 "，去掉 # 和它两侧人为插入的空格，让中文连续成句
    text = re.sub(r'[ \t]*#(?:\s*#)*\s*([\w一-鿿]+)[ \t]*', r'\1', text)
    text = DIVIDER.sub('', text)
    text = INLINE_DIVIDER.sub('\n', text)
    text = re.sub(r'[ \t]{2,}', ' ', text)
    lines = '\n'.join(line.strip() for line in text.split('\n'))
    return re.sub(r'\n{3,}', '\n\n', lines).strip()


def readable(text):
    """Text without bare URLs: they are unreadable in a card and the original post keeps the links."""
    text = URL.sub('', text)
    text = re.sub(r'[ \t]{2,}', ' ', text)
    text = '\n'.join(line.strip() for line in text.split('\n'))
    return re.sub(r'\n{3,}', '\n\n', text).strip()


def first_sentence(text):
    """Up to the first sentence end. A URL also ends it ("标题 https://… 正文"), and an early
    ！/？ does not, so "这次能飞了！特斯拉第二代跑车亮相" stays whole."""
    head = URL.split(text)[0]
    for end in SENTENCE_END.finditer(head):
        if end.group() in '！？' and len(head[:end.start()].strip()) < 10:
            continue
        return head[:end.start()].strip()
    return head.strip()


def headline(text, raw_html=''):
    """(title, body) for a cleaned message. Prefers 【标题】, then a leading bold run, then the first sentence."""
    bracket = re.match(r'【([^】]+)】', text)
    bold = BeautifulSoup(raw_html or '', 'html.parser').select_one('b, strong')
    bold_title = clean(bold.get_text('')) if bold else ''
    if bracket:
        title = bracket.group(1)
    elif len(bold_title) >= 12 and text.startswith(bold_title):
        title = bold_title
    else:
        title = first_sentence(text)
    title = title.strip('【】 ')
    if len(title) < 6:
        title = first_sentence(text)
    # A bold run can span lines; its first line is the headline when it says enough on its own.
    first_line = title.split('\n')[0].strip()
    if len(first_line) >= 6:
        title = first_line

    body = text
    if text.startswith('【' + title + '】'):
        body = text[len(title) + 2:].strip()
    elif text.startswith(title):
        body = text[len(title):].lstrip('。！？\n ')

    title = readable(title).replace('\n', ' ') or readable(text)[:TITLE_LIMIT]
    if len(title) > TITLE_LIMIT:
        title, body = title[:TITLE_LIMIT] + '…', text
    body = readable(body)
    if body.startswith(title):
        body = body[len(title):].lstrip('。！？\n ')
    # An empty body is better than repeating the title.
    return title, body
