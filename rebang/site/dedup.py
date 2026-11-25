"""频道内跨来源去重与同类事件合并（第 5 步）。只用标准库。

规则（保守，宁可漏合也不误合）：
- 只在同一频道内合并；不跨频道（契约「一个来源只进一个频道」，频道归属不变）。
- 同链接：规范化后相同直接归为一组（同来源也合，见下）。规范化只做明确不改变指向的事：
  http→https、去 www.（`m.` 等其它子域保留）、去尾 /、t.me/s/ 预览路径；去掉白名单里的追踪参数
  （utm_*、BBC 的 at_*、fbclid、gclid 等全局；ref_src、si、spm_id_from 等只在对应网站去）；
  剩下的参数按名字排序，同名参数保持原来的相对顺序；`#` 片段去掉，但以 `/` 或 `!` 开头的（前端路由）保留。
  路径大小写不动。`ref`、`from` 这类通用参数不去（?ref=101 与 ?ref=202 不是同一地址）。
- 近似标题：不同来源、发布时间相差 ≤ 24 小时，标题词重合度（Jaccard）达到门槛，且没有冲突：
  - 含中文的标题：中文按相邻两字切词，英文/数字按词；门槛 0.5。
  - 纯英文标题：去掉常见虚词后按词；门槛 0.6。
  - 冲突（任一条成立就判为不同事件）：
    - 撞词：两边各自有对方没有的关键词。关键词 = 数字（营收 2073.4 亿 vs 资本支出 814.3 亿）、
      中文标题里的英文词、英文标题里的专名（非句首的大写词、带数字的型号、内部有大写的词如 OpenAI）。
    - 否定不一致：一边有否定词（not/no/never/denies…，不/未/没有/无法/否认/拒绝…）而另一边没有。
  - 有机器翻译标题的英文条目，同时用原标题和译文标题比，取较高的一个；但任何一对标题有冲突就整体不合，
    译文相似不能盖过原文里已经识别出的冲突。
  - 主语不同：两边开头的词都不在对方标题里（「腾讯第三季度营收…」vs「拼多多第三季度营收…」），这一对不算。
  - 每边至少 6 个词，太短的标题（如「ETF 数据汇总」）不按标题合并。
  - 按标题入组时要和组里**每一条**都没有冲突（不只是主条），防止「只写 Gemini」的首条把 Hydrogen、Neon 串进一组。
- 同一组里每个来源只留一条；同来源的其它近似条目各自成条（同链接的除外：同来源同链接也折叠）。
- 主条：组里有「今日重点」标的优先，否则最早发的那条；其余折叠进主条的 merged[]。
"""
import re
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

WINDOW = timedelta(hours=24)
CJK_THRESHOLD = 0.5
LATIN_THRESHOLD = 0.6
MIN_TOKENS = 6

# 全局追踪参数（白名单，只收明确只用于统计来源的）
_TRACKING = re.compile(
    r'^(utm_[a-z0-9_]*|at_(medium|campaign|link_id|link_origin|link_type|ptr_name|bbc_team|format)|'
    r'fbclid|gclid|dclid|gbraid|wbraid|msclkid|yclid|twclid|igshid|mc_cid|mc_eid|_hsenc|_hsmi|mkt_tok|cmpid|ocid)$',
    re.I)
# 只在特定网站去掉的参数：别的网站上同名参数可能有实际含义
_SITE_TRACKING = {
    'twitter.com': {'ref_src', 'ref_url', 's', 't'},
    'x.com': {'ref_src', 'ref_url', 's', 't'},
    'youtube.com': {'si', 'feature'},
    'youtu.be': {'si', 'feature'},
    'bilibili.com': {'spm_id_from', 'vd_source', 'share_source', 'share_medium', 'share_from', 'share_plat',
                     'share_session_id', 'share_tag', 'timestamp', 'unique_k', 'from_spmid'},
    'b23.tv': {'share_source', 'share_medium', 'share_from'},
    'taobao.com': {'spm'},
    'tmall.com': {'spm'},
}
_CJK = re.compile(r'[㐀-鿿豈-﫿]')
_STOP = frozenset('''a an the of in on at to for from by with and or as is are was were be been after before over
into than that this these those its it his her their our new says say said amid about up out off how why what who
will has have had vs via'''.split())
# 否定词：英文按词，中文按字串（先去掉含这些字但不表否定的常用词）
_NEG_EN = re.compile(r"\b(not|no|never|none|nobody|nothing|neither|nor|without|cannot|can't|won't|"
                     r"[a-z]+n't|den(?:y|ies|ied|ying)|refus(?:e|es|ed|ing)|reject(?:s|ed|ing)?|fail(?:s|ed)? to)\b")
_NEG_ZH_SAFE = re.compile(r'未来|不过|不断|不少|不仅|不同|不久|不到|无人机|非洲|非常|是非')
_NEG_ZH = re.compile(r'否认|拒绝|没有|并非|无法|无意|无望|不|未|没|非')


def _site_of(host):
    for site in _SITE_TRACKING:
        if host == site or host.endswith('.' + site):
            return site
    return None


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
    site_params = _SITE_TRACKING.get(_site_of(host), set())
    kept = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True)
            if not _TRACKING.match(k) and k.lower() not in site_params]
    query = sorted(kept, key=lambda kv: kv[0])      # 稳定排序：同名参数保持原相对顺序
    fragment = parts.fragment if parts.fragment[:1] in ('/', '!') else ''
    return urlunsplit(('https', host, path, urlencode(query), fragment))


def _clean(text):
    text = str(text or '').replace('#', ' ')
    text = re.sub(r'https?://\S+', ' ', text)
    return re.sub(r'(?<=\d),(?=\d{3})', '', text)   # 2,073.4 → 2073.4


def _negated(text):
    """标题里有没有否定。只看有没有，不看是哪个词：「达不成」和「无法达成」算一样。"""
    low = text.lower().replace('\u2019', "'")
    return bool(_NEG_EN.search(low) or _NEG_ZH.search(_NEG_ZH_SAFE.sub(' ', text)))


def title_tokens(text):
    """(词集合, 关键词集合, 是否含中文, 开头的词, 有无否定)。
    关键词 = 数字；含中文的标题再加上其中的英文词；纯英文标题加上专名（非句首大写词、型号、内部大写词）。"""
    raw = _clean(text)
    text = raw.lower()
    has_cjk = bool(_CJK.search(text))
    tokens, keys, lead = set(), set(), None
    first_latin = True
    for match in re.finditer(r'[㐀-鿿豈-﫿]+|[A-Za-z0-9]+(?:[.\-][A-Za-z0-9]+)*', raw):
        orig = match.group()
        run = orig.lower()
        if _CJK.match(run):
            got = [run[i:i + 2] for i in range(len(run) - 1)] if len(run) > 1 else [run]
        elif re.fullmatch(r'[0-9]+(?:\.[0-9]+)?', run):
            got = [run]
            keys.add(run)
        elif has_cjk:
            got = [run]
            keys.add(run)
        elif run not in _STOP and len(run) > 1:
            got = [run]
            proper = (any(c.isdigit() for c in orig) or any(c.isupper() for c in orig[1:])
                      or (orig[0].isupper() and not first_latin))
            if proper:
                keys.add(run)
        else:
            got = []
        if not _CJK.match(run):
            first_latin = False
        if got and lead is None:
            lead = got[0]
        tokens.update(got)
    return tokens, keys, has_cjk, lead, _negated(raw)


def _titles(item):
    out = [item.get('title') or '']
    tr = item.get('translation') or {}
    if item.get('translated') and tr.get('title'):
        out.append(tr['title'])
    return [t for t in out if t.strip()]


def _comparable(a, b):
    return a[2] == b[2] and len(a[0]) >= MIN_TOKENS and len(b[0]) >= MIN_TOKENS


def _pair_conflict(a, b):
    """两个同语种标题之间有没有「肯定不是同一件事」的证据。"""
    ta, ka, _, _, na = a
    tb, kb, _, _, nb = b
    if (ka - tb) and (kb - ta):
        return True                      # 撞词：两边各有对方没有的数字/英文名/专名
    return na != nb                      # 否定不一致：is liable vs is not liable


def _pair_score(a, b):
    ta, _, ca, la, _ = a
    tb, _, _, lb, _ = b
    if not _comparable(a, b) or _pair_conflict(a, b):
        return 0.0
    if la not in tb and lb not in ta:
        return 0.0                       # 主语不同：两边开头的词都不在对方标题里（腾讯… vs 拼多多…）
    score = len(ta & tb) / len(ta | tb)
    return score if score >= (CJK_THRESHOLD if ca else LATIN_THRESHOLD) else 0.0


def conflicts(a, b):
    """两条（cluster 的 entry）之间是否有任何一对可比标题存在冲突。"""
    return any(_comparable(x, y) and _pair_conflict(x, y) for x in a['_tok'] for y in b['_tok'])


def title_similarity(a, b):
    """两条的标题相似分；0 表示不算同一事件。任何一对标题有冲突，译文再像也是 0。"""
    if conflicts(a, b):
        return 0.0
    best = 0.0
    for x in a['_tok']:
        for y in b['_tok']:
            best = max(best, _pair_score(x, y))
    return best


def entry_of(item):
    """cluster 内部用的比对记录；测试也用它逐对断言。"""
    return {'item': item, 'url': norm_url(item.get('url')), 'when': _when(item),
            '_tok': [title_tokens(t) for t in _titles(item)]}


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
    entries = [entry_of(item) for item in sorted(items, key=lambda i: (_when(i), i['id']))]
    groups, by_url, lo = [], {}, 0
    for entry in entries:
        group = by_url.get(entry['url']) if entry['url'] else None
        if group is None:
            # groups 按首条时间正序追加：首条已超出 24 小时窗口的组以后也不会再命中，跳过
            while lo < len(groups) and entry['when'] - groups[lo]['members'][0]['when'] > WINDOW:
                lo += 1
            best, best_score = None, 0.0
            sid = entry['item']['source_id']
            for cand in groups[lo:]:
                if sid in cand['sources']:
                    continue
                score = title_similarity(entry, cand['members'][0])
                if score > best_score and not any(conflicts(entry, m) for m in cand['members'][1:]):
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
