"""频道内跨来源去重（第 5 步）。只用标准库。

规则（最保守，宁可漏合也不误合；2026-11-25 第 3 轮起不再做「标题相近」打分合并）：
- 只在同一频道内合并；不跨频道（契约「一个来源只进一个频道」，频道归属不变）。
- 只认两种「同一条」：
  a. 同链接：规范化后的链接相同（同来源也合，显示「另有 N 条相同链接」）。规范化只做明确不改变指向的事：
     http→https、去 www.（`m.` 等其它子域保留）、去尾 /、t.me/s/ 预览路径；去掉明确的追踪参数
     （全局只去 utm_*、fbclid、gclid 等点击/邮件追踪参数；BBC 的 at_* 只在 bbc.com / bbc.co.uk 及其子域去；
     ref_src、si、spm_id_from 等只在 X、YouTube、B 站等对应网站去）；剩下的参数按名字排序，同名参数保持原相对顺序；
     `#` 片段去掉，但以 `/` 或 `!` 开头的（前端路由）保留。路径大小写不动。
  b. 原标题完全相同：规范化（去首尾空白、合并空白、统一全半角和大小写、去掉末尾标点）后一字不差；
     不同来源；发布时间相差 ≤ 24 小时；标题够长（含中文的至少 8 个字，纯外文至少 4 个词），太短的不合。
     不用机器翻译标题比较。
- 分组：先按同链接收齐，再按完全相同的标题把组并起来。按标题并组时：两组不能有相同来源
  （每组每个来源最多一条；同链接优先——同链接带进来的同来源条目照样留在组里，只是这样的组不再按标题并入有同来源的组），
  并且并完后按标题连起来的整组时间跨度 ≤ 24 小时。处理顺序按 (发布时间, id) 固定，结果与输入顺序无关。
- 主条：组里有「今日重点」标的优先，否则最早发的那条；其余折叠进主条的 merged[]。
"""
import re
import unicodedata
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

WINDOW = timedelta(hours=24)
MIN_CJK_CHARS = 8
MIN_WORDS = 4

# 全局追踪参数（白名单，只收明确只用于统计点击来源的）
_TRACKING = re.compile(
    r'^(utm_[a-z0-9_]*|fbclid|gclid|dclid|gbraid|wbraid|msclkid|yclid|twclid|igshid|mc_cid|mc_eid|_hsenc|_hsmi|mkt_tok)$',
    re.I)
_BBC_AT = re.compile(r'^at_[a-z0-9_]*$', re.I)
# 只在特定网站（含子域）去掉的参数：别的网站上同名参数可能有实际含义（如 ?at_format=one/two）
_SITE_TRACKING = {
    'bbc.com': _BBC_AT,
    'bbc.co.uk': _BBC_AT,
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
# 汉字（CJK 统一表意文字及扩展 A、兼容表意文字）；不含韩文、日文假名
_CJK = re.compile(r'[㐀-䶿一-鿿豈-﫿]')


def _site_rule(host):
    for site, rule in _SITE_TRACKING.items():
        if host == site or host.endswith('.' + site):
            return rule
    return None


def _site_drops(rule, key):
    if rule is None:
        return False
    if isinstance(rule, re.Pattern):
        return bool(rule.match(key))
    return key.lower() in rule


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
    rule = _site_rule(host)
    kept = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True)
            if not _TRACKING.match(k) and not _site_drops(rule, k)]
    query = sorted(kept, key=lambda kv: kv[0])      # 稳定排序：同名参数保持原相对顺序
    fragment = parts.fragment if parts.fragment[:1] in ('/', '!') else ''
    return urlunsplit(('https', host, path, urlencode(query), fragment))


def norm_title(text):
    """完全相同标题判定用的规范化原标题：统一全半角（NFKC）和大小写、合并空白、去首尾空白和末尾标点。"""
    text = unicodedata.normalize('NFKC', str(text or '')).casefold()
    text = re.sub(r'\s+', ' ', text).strip()
    end = len(text)
    while end and (unicodedata.category(text[end - 1]).startswith('P') or text[end - 1].isspace()):
        end -= 1
    return text[:end]


def title_key(item):
    """可按标题合并的键；标题太短（含中文的不到 8 个字、纯外文不到 4 个词）返回空串，不按标题合并。"""
    text = norm_title(item.get('title'))
    if not text:
        return ''
    if _CJK.search(text):
        chars = [c for c in text if c.isalnum()]      # 汉字、字母、数字都算字；标点、空格、表情不算
        return text if len(chars) >= MIN_CJK_CHARS else ''
    words = re.findall(r'\w+', text)
    return text if len(words) >= MIN_WORDS else ''


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
    """items：同一频道的条目。返回 [[主条, 折叠条…], …]，组按主条发布时间倒序，组内折叠条按时间正序。不改入参。
    结果只取决于条目本身，与输入顺序无关。"""
    order = sorted(items, key=lambda i: (_when(i), str(i.get('id')), str(i.get('source_id')), str(i.get('url'))))
    n = len(order)
    parent = list(range(n))
    when = [_when(i) for i in order]

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    # 第一遍：同链接。根取较小下标，保证组内信息挂在最早那条上
    first_by_url = {}
    for i, it in enumerate(order):
        url = norm_url(it.get('url'))
        if not url:
            continue
        if url in first_by_url:
            a, b = find(first_by_url[url]), find(i)
            if a != b:
                parent[max(a, b)] = min(a, b)
        else:
            first_by_url[url] = i
    # 每组：来源集合、按标题连起来的成员时间范围（同链接成员的时间不限）
    sources, span = {}, {}
    for i, it in enumerate(order):
        r = find(i)
        sources.setdefault(r, set()).add(it.get('source_id'))
    # 第二遍：完全相同的原标题。按 (时间, id) 顺序逐对尝试，结果确定
    seen_title = {}
    for j, it in enumerate(order):
        key = title_key(it)
        if not key:
            continue
        for i in seen_title.get(key, []):
            if order[i].get('source_id') == it.get('source_id') or when[j] - when[i] > WINDOW:
                continue
            a, b = find(i), find(j)
            if a == b or sources[a] & sources[b]:
                continue                       # 已同组，或两组有同一来源：不并
            lo_a, hi_a = span.get(a, (when[i], when[i]))
            lo_b, hi_b = span.get(b, (when[j], when[j]))
            lo, hi = min(lo_a, lo_b, when[i], when[j]), max(hi_a, hi_b, when[i], when[j])
            if hi - lo > WINDOW:
                continue                       # 按标题连起来的整组跨度超过 24 小时：不并
            root, other = min(a, b), max(a, b)
            parent[other] = root
            sources[root] = sources[a] | sources[b]
            span[root] = (lo, hi)
        seen_title.setdefault(key, []).append(j)
    groups = {}
    for i, it in enumerate(order):
        groups.setdefault(find(i), []).append(it)
    out = []
    for members in groups.values():
        primary = next((m for m in members if m.get('highlight')), members[0])
        out.append([primary] + [m for m in members if m is not primary])
    out.sort(key=lambda g: (_when(g[0]), str(g[0].get('id'))), reverse=True)
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
