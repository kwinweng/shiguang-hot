"""Extract exact event identities from explicit, affirmative original headlines.

Each pattern must account for the whole title. Unrecognized qualifiers are a
reason to abstain, since they may change the identity of the event.
"""
import re
from decimal import Decimal

# Require bounded names, without punctuation that introduces another clause.
_NAME = r"[^\W\d_][\w’'&-]*(?: [\w’'&-]+){0,9}?"
_ZH_NAME = r'[\w·-]+?(?: [\w·-]+?){0,5}?'
_BANK = rf'(?P<actor>{_NAME} (?:Central|Reserve) Bank|Bank of {_NAME})'
_RATE = r'(?P<object>benchmark(?: interest)? rate|policy(?: interest)? rate|key interest rate)'
_CHANGE = r'(?P<action>cuts|lowers|reduces|raises|lifts|increases)'
_ZH_BANK = rf'(?P<actor>{_ZH_NAME}(?:央行|中央银行|储备银行))'
_ZH_RATE = r'(?P<object>基准利率|政策利率|关键利率)'
_ZH_CHANGE = r'(?P<action>下调|调降|降低|上调|调升|提高)'
_VALUE = r'(?P<value>[0-9]+(?:\.[0-9]+)?)'
_ASSET = rf'(?P<object>{_NAME} (?:Bridge|Line|Tunnel))'
_PLACE = rf'(?P<place>{_NAME})'
_ZH_ASSET = rf'(?P<object>{_ZH_NAME}(?:大桥|桥|线|隧道))'
_ZH_PLACE = r'(?P<place>[㐀-鿿]+?[市县区省镇州])'
_COURT = rf'(?P<actor>{_NAME} (?:Court|Tribunal))'
_ZH_COURT = rf'(?P<actor>{_ZH_NAME}(?:法院|法庭))'
_DOCKET = r'[0-9]{2,4}[-:](?:[A-Za-z0-9]+-){0,3}[A-Za-z]*[0-9][A-Za-z0-9]*'
_CASE = rf'(?P<object>{_DOCKET})'
_ZH_CASE = rf'(?P<object>{_DOCKET}|[（(][0-9]{{4}}[）)][㐀-鿿][0-9]{{0,6}}[㐀-鿿]{{1,6}}[0-9]+)'
_CASE_PARENS = str.maketrans('（）', '()')
_VERSION = r'v?(?P<value>[0-9]+(?:\.[0-9]+){1,3})'
_PRODUCT = rf'(?P<object>{_NAME}) (?:version )?{_VERSION}'
_ZH_PRODUCT = rf'(?P<object>{_ZH_NAME}) ?{_VERSION}(?: ?(?:正式)?版(?:本)?)?'

_PATTERNS = [(kind, re.compile(pattern, re.I)) for kind, pattern in (
    ('rate', rf'{_BANK} {_CHANGE} (?:its |the )?{_RATE} to {_VALUE} ?%'),
    ('rate', rf'{_ZH_BANK}将{_ZH_RATE}{_ZH_CHANGE}(?:至|到) ?{_VALUE} ?[%％]'),
    ('rate', rf'{_ZH_BANK}{_ZH_CHANGE}{_ZH_RATE}(?:至|到) ?{_VALUE} ?[%％]'),
    ('opening', rf'{_PLACE} (?:officially )?(?:opens|inaugurates|puts into service) (?:the )?{_ASSET}'),
    ('opening', rf'{_ASSET} (?:officially )?(?:opens(?: to traffic)?|enters service) in {_PLACE}'),
    ('opening', rf'{_ZH_PLACE}(?:正式)?(?:启用|开通){_ZH_ASSET}'),
    ('opening', rf'{_ZH_PLACE}{_ZH_ASSET}(?:正式)?(?:通车|启用|开通)'),
    ('ruling', rf'{_COURT} (?:rules|issues (?:a|its) ruling|hands down (?:a|its) ruling) (?:in|on) case (?:No\. )?{_CASE}'),
    ('ruling', rf'{_ZH_COURT}对{_ZH_CASE}号案件(?:作出|发布)(?:裁决|判决)'),
    ('ruling', rf'{_ZH_COURT}(?:裁决|判决){_ZH_CASE}号案件'),
    ('release', rf'(?P<actor>{_NAME}) (?:releases|rolls out|ships) {_PRODUCT}'),
    ('release', rf'{_PRODUCT} (?:is )?released'),
    ('release', rf'(?P<actor>{_ZH_NAME})(?:正式)?(?:发布|推出){_ZH_PRODUCT}'),
)]
_DOWN = {'cuts', 'lowers', 'reduces', '下调', '调降', '降低'}
_PLACEHOLDER = re.compile(
    r'^(?:某|当地|本地|该|有关|一[个家座条款所间]|不明|未具名|地区性|某种)|'
    r'\b(?:some|unnamed|unidentified|unspecified|unknown|undisclosed|placeholder)\b|'
    r'^(?:an?|the) (?:local|regional|national|foreign)\b', re.I,
)
# A rate clause can state direction without a final level (e.g. a change in basis points).
_RATE_ACTION = re.compile(
    r'(?P<down>\b(?:cut|lower|reduc|decreas)\w*\b|\b(?:fell|fallen|dropped)\b|下调|调降|降低|降息)|'
    r'\b(?:rais|lift|increas|hik)\w*\b|\b(?:rose|risen|climbed)\b|上调|调升|提高|加息', re.I,
)
_RATE_TARGET = re.compile(rf'.{{0,80}}?(?:\bto\b|至|到)\s*{_VALUE}\s*[%％]', re.I)
_RATE_OBJECT = re.compile(r'\b(?:deposit|lending|mortgage|repo|refinancing|overnight) (?:interest )?rates?\b|'
                          r'(?:存款|贷款|房贷|回购|再融资|隔夜)利率', re.I)
_RATE_TERM = re.compile(r'\b(?:interest |benchmark |policy |key )?rates?\b|利率|降息|加息', re.I)
# Match what was held steady, not a nearby conference, fee or exchange rate.
_MONETARY_RATE = r'(?:(?:benchmark|policy|key)(?: interest)?|interest) rates?'
_STEADY = r'(?:unchanged|steady|flat|on hold)\b'
_HELD_LEVEL = rf'(?:{_STEADY}|at [0-9])'
_RATE_HOLD = re.compile(
    rf'\b(?:held|holds?|kept|keeps?|left|leaves?|maintained|maintains?) (?:the |its )?(?:{_MONETARY_RATE}|rates?)\b|'
    rf'\b(?:{_MONETARY_RATE}|(?:the |its |^)rates?) (?:'
    rf'(?:remains?|remained|stays?|stayed) {_HELD_LEVEL}|'
    rf'(?:was|were|is|are) (?:{_STEADY}|(?:held|kept|left|maintained) {_HELD_LEVEL}))|'
    r'(?:维持|保持)(?:现行|当前)?(?:基准|政策|关键)?利率|利率(?:仍然?|继续)?(?:维持|保持)(?:不变|稳定|在)|利率(?:仍然?|继续)?不变', re.I,
)
_RATE_SCOPE = re.compile(
    r'\b(?:appl(?:ies|ied|y) only to|only applies to|limited to|restricted to|exclusively for)\b|'
    r'仅(?:限于|适用于)|只(?:限于|适用于)', re.I,
)
_CLAUSES = re.compile(r'[。！？!?；;\n]|\.(?![0-9])')
# Match a future predicate of this event class, not just a time word in an article.
# In particular, 将 followed by the object (将基准利率下调至…) is not a future marker.
_PLAN_EN = r'\b(?:will|would|(?:plans?|intends?|scheduled|due|set) to)\s+(?:(?:be|formally|officially|soon)\s+){0,3}'
_PLAN_ZH = (r'(?:计划|即将|将要|将|拟|定于)(?:于|在)?'
            r'(?:(?:本|下)(?:个)?(?:周|星期|月|季度)[一二三四五六日天]?|明[天日年月]|次[日月]|'
            r'[0-9]{1,2}月(?:[0-9]{1,2}日)?)?(?:正式)?')
_NAME_WORD = r"[\w’'-]+(?:\.[0-9]+)*"  # keep version dots, not sentence boundaries
_PLAN_SUBJECT = rf'(?: (?:of|in case) {_NAME_WORD}(?: {_NAME_WORD}){{0,5}})?'
_PLANNED = {kind: re.compile(rf'{_PLAN_EN}(?:{en})\b|\b(?:{noun}){_PLAN_SUBJECT} (?:is |was |has been )?'
                             rf'(?:scheduled|planned|set) for\b|{_PLAN_ZH}(?:{zh})', re.I)
            for kind, en, noun, zh in (
                ('rate', r'cut|lower(?:ed)?|reduced?|raised?|increased?|hiked?',
                 r'rate (?:cut|increase|hike)', r'下调|调降|降低|降息|上调|调升|提高|加息'),
                ('opening', r'open(?:ed)?|inaugurated?|enter service', r'opening|inauguration',
                 r'通车|开通|启用'),
                ('ruling', r'rule|(?:issue|deliver|hand down) (?:a |the |its )?(?:ruling|judgment|decision)',
                 r'ruling|judgment', r'(?:对[该本]案)?(?:作出|发布)?(?:裁决|判决)'),
                ('release', r'released?|ship(?:ped)?|roll(?:ed)? out|launch(?:ed)?', r'release|rollout',
                 r'发布|推出|发行'),
            )}
# 正文只作否决，不用它猜主体或补事件。宁可丢掉同时谈到关闭/撤回/延期的复杂报道。
_DELAYED = r'\b(?:postponed|deferred|pending|delayed|cancelled|canceled|withdrawn)\b|推迟|延后|延期|取消|撤回|暂缓'
_CONTRARY = {
    'opening': re.compile(_DELAYED + r'|\b(?:remains?|stays?|is|still) (?:temporarily |fully |partially )?(?:closed|shut|inaccessible)\b|'
                          r'\b(?:closed to traffic|road closure|permanent closure)\b|封闭|封路|关闭|未通车', re.I),
    'ruling': re.compile(_DELAYED + r'|\b(?:vacated|overturned|reversed)\b|撤销|尚待裁决|改判', re.I),
    'release': re.compile(_DELAYED + r'|\b(?:unreleased|recalled|retracted|unavailable)\b|召回|下架|尚未发布', re.I),
}


def conflicts_with_report(event, text):
    """A contrary action in the report vetoes a title match, never supplies a vote."""
    if event[0] != 'rate':
        return bool(_CONTRARY[event[0]].search(text) or _PLANNED[event[0]].search(text))
    _, _, direction, _, value, _ = event
    for clause in _CLAUSES.split(text):
        if not _RATE_TERM.search(clause):
            continue
        if _RATE_SCOPE.search(clause) or _RATE_HOLD.search(clause) or _PLANNED['rate'].search(clause):
            return True
        for action in _RATE_ACTION.finditer(clause):
            if ('down' if action['down'] else 'up') != direction:
                return True
            target = _RATE_TARGET.match(clause, action.end())
            if target and (Decimal(target['value']) != value or _RATE_OBJECT.search(clause)):
                return True
    return False

# Words that may otherwise be swallowed by a name slot (for example, "Foo delays
# Bar" as the supposed publisher of a release). Keep the original name itself exact.
_NON_NAME = re.compile(
    r'\b(?:after|before|during|until|while|when|reports?|says?|claims?|announces?|confirms?|'
    r'delays?|cancels?|withdraws?|releases?|ships?|opens?|closes?|rules?|vacates?|cuts?|raises?|'
    r'rolls out|tests?|preview|alpha|rc|plans?|will|could|set to|poised to|'
    r'purportedly|supposedly|prepares? to|proposes? to)\b|'
    r'计划|传闻|据称|据报|否认|并未|尚未|拟|将要|预计|推迟|取消|撤回|撤销|暂停|重新|再度|发布|推出|裁决|通车|开通|启用|测试版|'
    r'[将未欲要]$',
    re.I,
)
# Bare institution types and generic references carry no named identity.
_GENERIC_NAME = re.compile(
    r'(?:(?:the|a|an|local|regional|national|federal|state|high|top|supreme|new|major|central|reserve) )*'
    r'(?:bank|court|tribunal|city|town|county|government|ministry|authorities|bridge|line|tunnel|'
    r'company|developer|product|software|platform|system|project|app)|'
    r'(?:该|本|新|一座|当地|某|全国|最高)*(?:央行|中央银行|储备银行|法院|法庭|市|县|区|省|镇|州|大桥|桥|线|隧道|平台|公司|项目)',
    re.I,
)


def event_key(title):
    """Return a hashable identity or None when the original title leaves it uncertain."""
    if len(title) > 240:
        return None
    headline = title.removesuffix('.').removesuffix('。')
    for kind, pattern in _PATTERNS:
        match = pattern.fullmatch(headline)
        if match is None:
            continue
        fields = match.groupdict()
        names = (fields[key] for key in ('actor', 'place', 'object') if key in fields)
        if any(_NON_NAME.search(name) or _GENERIC_NAME.fullmatch(name) or _PLACEHOLDER.search(name)
               for name in names):
            continue
        if kind == 'rate':
            action = 'down' if fields['action'].lower() in _DOWN else 'up'
            rate = fields['object'].lower().replace(' interest rate', ' rate')
            return kind, fields['actor'], action, rate, Decimal(fields['value']), '%'
        if kind == 'opening':
            return kind, fields['place'], fields['object']
        if kind == 'ruling':
            return kind, fields['actor'], fields['object'].translate(_CASE_PARENS)
        return kind, fields.get('actor'), fields['object'], fields['value']
    return None
