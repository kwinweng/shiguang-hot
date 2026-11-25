"""频道内跨来源去重（第 5 步）。只用标准库。

规则（最保守，宁可几乎不合也不误合；2026-11-25 第 3 轮复核到上限后收紧成唯一一条）：
- 只在同一频道内合并；不跨频道（契约「一个来源只进一个频道」，频道归属不变）。
- 只认一种「同一条」：规范化后的链接相同 **且** 原标题相同。两条都要满足，缺一不合：
  · 链接规范化只做明确不改变指向的事：http→https、去 www.（`m.` 等其它子域保留）、去尾 /、t.me/s/ 预览路径；
    去掉明确的追踪参数（全局只去 utm_*、fbclid、gclid 等点击/邮件追踪参数；BBC 的 at_* 只在 bbc.com / bbc.co.uk
    及其子域去；ref_src、si、spm_id_from 等只在 X、YouTube、B 站等对应网站去）；剩下的参数按名字排序，
    同名参数保持原相对顺序；`#` 片段去掉，但以 `/` 或 `!` 开头的（前端路由）保留。路径大小写不动。没有链接或不是 http(s) 的不合。
  · 原标题只去首尾空白、把连续空白合成一个空格；**不改大小写、不改全半角、不去标点**（`100 mW`/`100 MW`、`？`/`。` 都算不同）。
    不用机器翻译标题比较。
  · 只合不同来源：同一来源同链接同标题的两条也不合（每组每个来源最多一条）。
  · 组里任意两条发布时间相差 ≤ 24 小时（即整组最早到最晚 ≤ 24 小时）。
- 分组：按 (规范化链接, 原标题) 分桶；桶内按 (发布时间, id) 从早到晚逐条放进第一个「没有同来源、且放进去后整组跨度
  仍 ≤ 24 小时」的组，放不进就自成一组。顺序固定，结果与输入顺序无关。
- 主条：组里有「今日重点」标的优先，否则最早发的那条；其余折叠进主条的 merged[]。
"""
import re
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

WINDOW = timedelta(hours=24)

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
    """原标题比较用：只去首尾空白、合并连续空白；不改大小写、全半角和标点。"""
    return re.sub(r'\s+', ' ', str(text or '')).strip()


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
    groups = []                    # 每组：成员列表（按时间正序）
    open_by_key = {}               # (规范化链接, 原标题) → 这个键下已有的组（下标）
    for it in order:
        url, title = norm_url(it.get('url')), norm_title(it.get('title'))
        if not url or not title:
            groups.append([it])
            continue
        for g in open_by_key.setdefault((url, title), []):
            members = groups[g]
            # 成员按时间正序加入，members[0] 是组里最早的：放进来后整组跨度 = 这条时间 − 最早那条
            if all(m.get('source_id') != it.get('source_id') for m in members) and _when(it) - _when(members[0]) <= WINDOW:
                members.append(it)
                break
        else:
            open_by_key[(url, title)].append(len(groups))
            groups.append([it])
    out = []
    for members in groups:
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
