"""Telegram 公开网页上的「附加信息」：本频道自己的话、引用（回复）/转发的原帖、表情回应、浏览数、公开评论。

只读 t.me 公开页面（https://t.me/s/<频道> 与讨论组挂件 https://t.me/<频道>/<id>?embed=1&discussion=1），
不登录、不用任何密钥。页面上没有的不写（不编数字、不编评论）。

为什么单独做：旧 shiguang 采集（tg.db）只存了消息里第一个 .tgme_widget_message_text，
遇到「回复/引用」消息时存下的是被引用的原文，频道自己写的话反而丢了；表情回应、浏览数、评论也没存。
这里另存一份 var/rebang/cache/tgmeta.json，ingest 按 <频道>/<消息号> 合进条目，旧站与 tg.db 不动。
"""
import json
import re
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_STORE = ROOT / 'var' / 'rebang' / 'cache' / 'tgmeta.json'
BEIJING = timezone(timedelta(hours=8))
SCHEMA = 'rebang.tgmeta/1'
KEEP_DAYS = 16              # 条目只收 14 天，多留两天
REFRESH_HOURS = 48          # 48 小时内的消息每次都重抓表情/浏览数（数字还在涨）
MAX_PAGES = 45              # 每个频道每次最多翻多少页（每页约 20 条）
COMMENT_HOURS = 48          # 只给 48 小时内的消息抓评论
COMMENT_PER_CHANNEL = 10    # 每个频道每次最多抓几条消息的评论
COMMENT_REFRESH_HOURS = 6
COMMENT_PREVIEW = 30        # 评论楼：每条最多存几条评论（挂件加 comments_limit 参数后一次能给这么多，最新的在后）
REPLY_SNIPPET = 120         # 楼中楼「回复 某人：…」引用的原话最多几个字
PROBE_HOURS = 24            # 多久重新确认一次频道有没有开公开评论


def _text(node):
    """与 shiguang/ingest/telegram.extract 同规则：<br> 变换行，内联元素无缝拼接。"""
    if node is None:
        return ''
    node = BeautifulSoup(str(node), 'html.parser')
    for br in node.find_all('br'):
        br.replace_with('\n')
    t = node.get_text('').replace('\xa0', ' ')
    t = re.sub(r'[ \t]+\n', '\n', t)
    t = re.sub(r'\n{3,}', '\n\n', t)
    return t.strip()


def parse_count(label):
    """'340' → 340，'20.2K' → 20200，'1.3M' → 1300000；认不出返回 None。显示仍用原文 label，不假装精确。"""
    m = re.fullmatch(r'\s*([\d.]+)\s*([KkMm]?)\s*', str(label or ''))
    if not m:
        return None
    try:
        n = float(m.group(1))
    except ValueError:
        return None
    return int(round(n * {'': 1, 'k': 1000, 'm': 1000000}[m.group(2).lower()]))


def _own_text_node(msg):
    for node in msg.select('.tgme_widget_message_text'):
        if 'js-message_reply_text' in (node.get('class') or []) or node.find_parent(class_='tgme_widget_message_reply'):
            continue
        return node
    return None


def _reactions(msg):
    out = []
    for r in msg.select('.tgme_widget_message_reactions .tgme_reaction'):
        label = r.get_text('', strip=True)
        emoji_node = r.select_one('b')
        if emoji_node is not None:
            emoji = emoji_node.get_text('', strip=True)
            label = label[len(emoji):].strip() if label.startswith(emoji) else label
        elif 'tgme_reaction_paid' in (r.get('class') or []):
            emoji = '⭐'
        else:
            continue     # 自定义表情没有可显示的字符，跳过，不编
        count = parse_count(label)
        if emoji and count is not None:
            out.append({'emoji': emoji, 'count': count, 'label': label})
    return out


def parse_page(html):
    """t.me/s/<频道> 一页 → {消息号: meta}。meta 见模块说明，拿不到的键不写。"""
    soup = BeautifulSoup(html, 'html.parser')
    out = {}
    for msg in soup.select('div.tgme_widget_message[data-post]'):
        try:
            mid = int(msg['data-post'].split('/')[1])
        except (IndexError, ValueError):
            continue
        meta = {'text': _text(_own_text_node(msg))}
        tm = msg.select_one('.tgme_widget_message_date time[datetime]') or msg.select_one('time[datetime]')
        if tm:
            meta['published_at'] = tm['datetime']
        fwd = msg.select_one('.tgme_widget_message_forwarded_from')
        if fwd:
            link = fwd.select_one('a.tgme_widget_message_forwarded_from_name, a[href]')
            name_node = fwd.select_one('.tgme_widget_message_forwarded_from_name') or fwd
            name = name_node.get_text(' ', strip=True).replace('Forwarded from', '').strip()
            if not name:   # 名字为空时用页面上的作者名（如「Linghao Zhang」），仍是 t.me 页面原文
                author = fwd.select_one('.tgme_widget_message_forwarded_from_author')
                name = author.get_text(' ', strip=True) if author else ''
            meta['forward'] = {'name': name, 'url': link['href'] if link and link.get('href', '').startswith('https://') else ''}
        reply = msg.select_one('.tgme_widget_message_reply')
        if reply:
            author = reply.select_one('.tgme_widget_message_author_name')
            meta['reply'] = {
                'name': author.get_text(' ', strip=True) if author else '',
                'text': _text(reply.select_one('.js-message_reply_text, .tgme_widget_message_text')),
                'url': reply.get('href', '') if reply.get('href', '').startswith('https://') else '',
            }
        reactions = _reactions(msg)
        if reactions:
            meta['reactions'] = reactions
        views = msg.select_one('.tgme_widget_message_views')
        if views and parse_count(views.get_text(strip=True)) is not None:
            meta['views_label'] = views.get_text(strip=True)
            meta['views'] = parse_count(meta['views_label'])
        out[mid] = meta
    return out


def parse_discussion(html):
    """讨论组挂件 → {'enabled': bool, 'total': int|None, 'comments': [...]}。
    页面没有讨论区（频道没开评论）→ enabled False，comments 为空。"""
    soup = BeautifulSoup(html, 'html.parser')
    off = {'enabled': False, 'total': None, 'comments': []}
    if not soup.select_one('.tgme_post_discussion, .body_widget_discussion'):
        return off
    if re.search(r'Discussion is not available|Comments are (?:disabled|closed)', soup.get_text(' ', strip=True), re.I):
        return off      # 频道没开公开评论：挂件只给一句「不可用」
    total = None
    head = soup.select_one('.tgme_post_discussion_header')
    if head:
        m = re.search(r'([\d.,]+[KkMm]?)\s+comments?', head.get_text(' ', strip=True))
        if m:
            total = parse_count(m.group(1).replace(',', ''))
        elif re.search(r'\bno comments\b', head.get_text(' ', strip=True), re.I):
            total = 0
    comments = []
    for msg in soup.select('.tgme_post_discussion .tgme_widget_message, .tgme_widget_message[data-post-id]'):
        text = _text(_own_text_node(msg))
        author = msg.select_one('.tgme_widget_message_bubble > .tgme_widget_message_author .tgme_widget_message_author_name, '
                                '.tgme_widget_message_author_name, .tgme_widget_message_owner_name')
        if not text or not author:
            continue          # 只有图片/贴纸的评论没有可显示的文字，跳过，不编
        c = {'display_name': author.get_text(' ', strip=True), 'text': text}
        if str(msg.get('data-post-id') or '').isdigit():
            c['id'] = int(msg['data-post-id'])
        tm = msg.select_one('.tgme_widget_message_footer time[datetime], .tgme_widget_message_date time[datetime]') or msg.select_one('time[datetime]')
        if tm:
            c['published_at'] = tm['datetime']
        reply = msg.select_one('.tgme_widget_message_reply')
        if reply is not None:
            who = reply.select_one('.tgme_widget_message_author_name')
            if who and who.get_text(' ', strip=True):
                c['reply_to'] = who.get_text(' ', strip=True)
            said = _text(reply.select_one('.js-message_reply_text, .tgme_widget_message_text'))
            if said:
                c['reply_text'] = said if len(said) <= REPLY_SNIPPET else said[:REPLY_SNIPPET].rstrip() + '…'
            if str(reply.get('data-reply-to') or '').isdigit():
                c['reply_to_id'] = int(reply['data-reply-to'])
        if c not in comments:
            comments.append(c)
    if total is None and not comments:
        return off
    return {'enabled': True, 'total': total, 'comments': comments[-COMMENT_PREVIEW:]}


def discussion_url(channel, mid):
    """讨论组挂件地址：加 comments_limit 一次拿评论楼，而不是默认的最近 5 条。"""
    return f'https://t.me/{channel}/{mid}?embed=1&discussion=1&comments_limit={COMMENT_PREVIEW}'


def _get(url):
    import subprocess
    r = subprocess.run(['curl', '-sL', '--fail', '-m', '25', '-A', 'Mozilla/5.0', url], capture_output=True, text=True)
    if r.returncode or not r.stdout.strip():
        raise RuntimeError(f'curl {r.returncode}')
    return r.stdout


def _when(value):
    try:
        moment = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    except ValueError:
        return None
    return moment if moment.tzinfo else moment.replace(tzinfo=BEIJING)


def load_store(path=DEFAULT_STORE):
    try:
        data = json.loads(Path(path).read_text(encoding='utf-8'))
        if data.get('schema') == SCHEMA:
            return data
    except (OSError, ValueError):
        pass
    return {'schema': SCHEMA, 'channels': {}, 'messages': {}}


def save_store(store, path=DEFAULT_STORE):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + '.tmp')
    tmp.write_text(json.dumps(store, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
    tmp.replace(path)


def refresh(channels, now=None, store=None, get=_get, days=14, sleep=0.25, log=None):
    """抓 channels（频道 handle 列表）的公开页面，更新 store 并返回统计。单个频道失败不影响其它频道。"""
    now = now or datetime.now(BEIJING)
    store = store or load_store()
    msgs, chans = store.setdefault('messages', {}), store.setdefault('channels', {})
    floor = now - timedelta(days=days)
    recent = now - timedelta(hours=REFRESH_HOURS)
    stats = {'pages': 0, 'messages': 0, 'comments_fetched': 0, 'errors': {}}
    stamp = now.isoformat(timespec='seconds')
    for ch in channels:
        before, pages = None, 0
        try:
            while pages < MAX_PAGES:
                html = get(f'https://t.me/s/{ch}' + (f'?before={before}' if before else ''))
                page = parse_page(html)
                pages += 1
                stats['pages'] += 1
                if not page:
                    break
                known_old = True
                for mid, meta in page.items():
                    key = f'{ch}/{mid}'
                    old = msgs.get(key)
                    if old and 'comments' in old:
                        meta['comments'] = old['comments']
                    # t.me 有时给出名字为空的转发/引用头（同一条在别的页里有名字）：不拿空的覆盖已知的
                    for part in ('forward', 'reply'):
                        new, prev = meta.get(part), (old or {}).get(part)
                        if prev and (not new or (not new.get('name') and prev.get('name')) or (not new.get('url') and prev.get('url'))):
                            meta[part] = prev
                    meta['fetched_at'] = stamp
                    msgs[key] = meta
                    stats['messages'] += 1
                    moment = _when(meta.get('published_at'))
                    if old is None or (moment and moment >= recent):
                        known_old = False
                oldest = min((_when(m.get('published_at')) for m in page.values() if m.get('published_at')), default=None)
                low = min(page)
                if oldest is None or oldest < floor or (known_old and oldest < recent) or (before is not None and low >= before):
                    break
                before = low
                time.sleep(sleep)
            chans.setdefault(ch, {})['pages_at'] = stamp
        except Exception as ex:   # 网络/结构问题：记下，留着旧数据
            stats['errors'][ch] = type(ex).__name__ + (f': {ex}' if str(ex) else '')
            chans.setdefault(ch, {})['error'] = stats['errors'][ch]
            continue
        chans[ch].pop('error', None)
        # ---- 公开评论（讨论组挂件）----
        info = chans[ch]
        mine = sorted(((int(k.split('/')[1]), v) for k, v in msgs.items() if k.split('/')[0] == ch), reverse=True)
        probe_at = _when(info.get('discussion_probed_at'))
        if mine and (probe_at is None or now - probe_at > timedelta(hours=PROBE_HOURS)):
            try:
                result = parse_discussion(get(discussion_url(ch, mine[0][0])))
                info['discussion'] = result['enabled']
                info['discussion_probed_at'] = stamp
                if result['enabled']:
                    mine[0][1]['comments'] = dict(result, fetched_at=stamp)
                    stats['comments_fetched'] += 1
            except Exception as ex:
                stats['errors'][ch + ':discussion'] = type(ex).__name__
        if not info.get('discussion'):
            continue
        budget = COMMENT_PER_CHANNEL
        for mid, meta in mine:
            if budget <= 0:
                break
            moment = _when(meta.get('published_at'))
            if not moment or moment < now - timedelta(hours=COMMENT_HOURS):
                continue
            got = (meta.get('comments') or {}).get('fetched_at')
            if got and now - _when(got) < timedelta(hours=COMMENT_REFRESH_HOURS):
                continue
            try:
                meta['comments'] = dict(parse_discussion(get(discussion_url(ch, mid))), fetched_at=stamp)
                stats['comments_fetched'] += 1
            except Exception as ex:
                stats['errors'][f'{ch}/{mid}:discussion'] = type(ex).__name__
            budget -= 1
            time.sleep(sleep)
        if log:
            log(f'{ch}\tpages={pages}\tdiscussion={info.get("discussion")}')
    cut = now - timedelta(days=KEEP_DAYS)
    for key in [k for k, v in msgs.items() if (_when(v.get('published_at')) or now) < cut]:
        del msgs[key]
    store['generated_at'] = stamp
    return store, stats


def merge_meta(meta):
    """tgmeta 一条 → 条目上要加/改的字段：own_text（频道自己的话）、quote、tg。拿不到的不写。"""
    if not meta:
        return {}
    out = {'own_text': meta.get('text', '')}
    if meta.get('forward'):
        f = meta['forward']
        # 转发：消息正文就是原帖原文，频道自己没写话
        out['quote'] = {'kind': 'forward', 'source_name': f.get('name') or '', 'url': f.get('url') or '', 'text': meta.get('text', '')}
        out['own_text'] = ''
    elif meta.get('reply'):
        r = meta['reply']
        out['quote'] = {'kind': 'reply', 'source_name': r.get('name') or '', 'url': r.get('url') or '', 'text': r.get('text') or ''}
    tg = {}
    if meta.get('views') is not None:
        tg['views'] = meta['views']
        tg['views_label'] = meta.get('views_label') or str(meta['views'])
    if meta.get('reactions'):
        tg['reactions'] = meta['reactions']
    c = meta.get('comments') or {}
    if c.get('enabled') and (c.get('comments') or c.get('total')):
        if c.get('total') is not None:
            tg['comments_total'] = c['total']
        tg['comments'] = c.get('comments') or []
    if tg:
        tg['fetched_at'] = meta.get('fetched_at')
        out['tg'] = tg
    return out
