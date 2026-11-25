"""频道内跨来源去重与同类事件合并（第 5 步）。只用标准库。

规则（保守，宁可漏合也不误合）：
- 只在同一频道内合并；不跨频道（契约「一个来源只进一个频道」，频道归属不变）。
- 同链接：规范化后相同（http→https、去 www.、去 #片段、去 utm_* 等追踪参数、参数排序、去尾 /）直接归为一组。
  有实际含义的参数（如 ?id=1 与 ?id=2）不同就不算同链接。
- 近似标题：不同来源、发布时间相差 ≤ 24 小时，标题词重合度（Jaccard）达到门槛，且没有「撞词」冲突：
  - 含中文的标题：中文按相邻两字切词，英文/数字按词；门槛 0.5。
  - 纯英文标题：去掉常见虚词后按词；门槛 0.6。
  - 冲突：两边各自有对方没有的数字（营收 2073.4 亿 vs 资本支出 814.3 亿），或中文标题里各自有对方没有的英文名
    （Gemini 4 Hydrogen vs Gemini 4 Neon），判为不同事件。
  - 有机器翻译标题的英文条目，同时用原标题和译文标题比，取较高的一个。
  - 主语不同：两边开头的词都不在对方标题里（「腾讯第三季度营收…」vs「拼多多第三季度营收…」），判为不同事件。
  - 每边至少 6 个词，太短的标题（如「ETF 数据汇总」）不按标题合并。
- 同一组里每个来源只留一条；同来源的其它近似条目各自成条（同链接的除外）。
- 主条：组里有「今日重点」标的优先，否则最早发的那条；其余折叠进主条的 merged[]。
"""
import re
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

WINDOW = timedelta(hours=24)
CJK_THRESHOLD = 0.5
LATIN_THRESHOLD = 0.6
MIN_TOKENS = 6

_TRACKING = re.compile(
    r'^(utm_[a-z0-9_]*|at_(medium|campaign|link_id|link_origin|link_type|ptr_name|bbc_team|format)|spm|fbclid|gclid|'
    r'igshid|mc_cid|mc_eid|ref|ref_src|ref_url|cmpid|ocid|si|from|share_source|share_medium|share_from|share_token)$',
    re.I)
_CJK = re.compile(r'[㐀-鿿豈-﫿]')
_STOP = frozenset('''a an the of in on at to for from by with and or as is are was were be been after before over
into than that this these those its it his her their our new says say said amid about up out off how why what who
will has have had not no vs via'''.split())


def norm_url(url):
    """同链接判定用的规范化地址；不是 http(s) 返回空串。"""
    raw = str(url or '').strip()
    if not re.match(r'^https?://', raw, re.I):
        return ''
    parts = urlsplit(raw)
    host = parts.netloc.lower()
    if host.startswith('www.'):
        host = host[4:]
    path = parts.path or '/'
    if host == 't.me' and path.startswith('/s/'):
        path = path[2:]
    path = path.rstrip('/') or '/'
    query = sorted((k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True) if not _TRACKING.match(k))
    return urlunsplit(('https', host, path, urlencode(query), ''))


def _clean(text):
    text = str(text or '').lower().replace('#', ' ')
    text = re.sub(r'https?://\S+', ' ', text)
    return re.sub(r'(?<=\d),(?=\d{3})', '', text)   # 2,073.4 → 2073.4


def title_tokens(text):
    """(词集合, 关键词集合, 是否含中文, 开头的词)。关键词 = 数字；含中文的标题再加上其中的英文词。"""
    text = _clean(text)
    has_cjk = bool(_CJK.search(text))
    tokens, keys, lead = set(), set(), None
    for match in re.finditer(r'[\u3400-\u9fff\uf900-\ufaff]+|[a-z0-9]+(?:\.[0-9]+)?', text):
        run = match.group()
        if _CJK.match(run):
            got = [run[i:i + 2] for i in range(len(run) - 1)] if len(run) > 1 else [run]
        elif run.isdigit() or re.fullmatch(r'[0-9]+\.[0-9]+', run):
            got = [run]
            keys.add(run)
        elif has_cjk:
            got = [run]
            keys.add(run)
        elif run not in _STOP and len(run) > 1:
            got = [run]
        else:
            got = []
        if got and lead is None:
            lead = got[0]
        tokens.update(got)
    return tokens, keys, has_cjk, lead


def _titles(item):
    out = [item.get('title') or '']
    tr = item.get('translation') or {}
    if item.get('translated') and tr.get('title'):
        out.append(tr['title'])
    return [t for t in out if t.strip()]


def _pair_score(a, b):
    ta, ka, ca, la = a
    tb, kb, cb, lb = b
    if ca != cb or len(ta) < MIN_TOKENS or len(tb) < MIN_TOKENS:
        return 0.0
    if (ka - tb) and (kb - ta):
        return 0.0                       # 撞词冲突：两边各有对方没有的数字/英文名
    if la not in tb and lb not in ta:
        return 0.0                       # 主语不同：两边开头的词都不在对方标题里（腾讯… vs 拼多多…）
    score = len(ta & tb) / len(ta | tb)
    return score if score >= (CJK_THRESHOLD if ca else LATIN_THRESHOLD) else 0.0


def title_similarity(a, b):
    """两条的标题相似分；0 表示不算同一事件。"""
    best = 0.0
    for x in a['_tok']:
        for y in b['_tok']:
            best = max(best, _pair_score(x, y))
    return best


def _when(item):
    try:
        moment = datetime.fromisoformat(str(item.get('published_at')).replace('Z', '+00:00'))
    except ValueError:
        return datetime.min.replace(tzinfo=timezone.utc)
    return moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)


def _ref(item):
    ref = {k: item.get(k) for k in ('id', 'source_id', 'source_name', 'title', 'url', 'published_at')}
    tr = item.get('translation') or {}
    if item.get('translated') and tr.get('title'):
        ref['title_zh'] = tr['title']
    return ref


def cluster(items):
    """items：同一频道的条目。返回 [[主条, 折叠条…], …]，组按主条发布时间倒序，组内折叠条按时间正序。不改入参。"""
    entries = []
    for item in sorted(items, key=lambda i: (_when(i), i['id'])):
        entries.append({'item': item, 'url': norm_url(item.get('url')), 'when': _when(item),
                        '_tok': [title_tokens(t) for t in _titles(item)]})
    groups, by_url = [], {}
    for entry in entries:
        group = by_url.get(entry['url']) if entry['url'] else None
        if group is None:
            best, best_score = None, 0.0
            sid = entry['item']['source_id']
            for cand in groups:
                seed = cand['members'][0]
                if entry['when'] - seed['when'] > WINDOW or sid in cand['sources']:
                    continue
                score = title_similarity(entry, seed)
                if score > best_score:
                    best, best_score = cand, score
            group = best
        if group is None:
            group = {'members': [], 'sources': set()}
            groups.append(group)
        group['members'].append(entry)
        group['sources'].add(entry['item']['source_id'])
        if entry['url']:
            by_url.setdefault(entry['url'], group)
    out = []
    for group in groups:
        members = [e['item'] for e in group['members']]
        primary = next((m for m in members if m.get('highlight')), members[0])
        out.append([primary] + [m for m in members if m is not primary])
    out.sort(key=lambda g: (_when(g[0]), g[0]['id']), reverse=True)
    return out


def fold(items):
    """返回 (频道里显示的主条列表（带 merged[] 的浅拷贝）, 被折叠的完整条目列表)。没有重复时原样返回。"""
    shown, folded = [], []
    for group in cluster(items):
        primary, rest = group[0], group[1:]
        if rest:
            primary = dict(primary, merged=[_ref(m) for m in rest])
            folded.extend(rest)
        shown.append(primary)
    return shown, folded
