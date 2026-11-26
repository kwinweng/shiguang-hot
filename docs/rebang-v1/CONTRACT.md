# 拾光资讯 v1 数据契约

要改字段、频道或目录，先改本契约和 `tests/test_rebang_contract.py`，再改生产者和前端。（11/15 开发期按功能分支划分，现已全部合入 main。）依据：`/workspace/deliverables/daily-site/docs/architecture-plan-v1-20261115.md`（2026-11-15）。

## 1. 唯一真相

| 文件 | 内容 |
|---|---|
| `rebang/contract/channels.json` | 6 个频道（current 时事 / world 环球 / finance 财经 / tech-ai 科技与 AI / digital 数码 / tools 工具与项目）与来源映射；18 个 TG（不含 reorx_share）；今日重点由建站时的独立来源互证判定 |
| `rebang/contract/hotsearch.json` | 热搜提供方 baidu、zhihu、bilibili（11/15 20:41 阿欢确认；不要微博），可替换；每家最多 51 条（百度 = 置顶 1 + 普通 50）；展示在底栏「热搜」页（`view:hot`），按北京日期归档（`archive.dir/keep`） |
| `rebang/contract/bloggers.json` | 博主平台与名单：X 16、博客 7、即刻 9、微博 6、公众号 6、YouTube 13（知乎空占位 2026-11-25 撤掉） |
| `rebang/contract/schema.py` | 纯标准库校验：`validate_item` / `validate_items_envelope` / `validate_hotsearch` |

旧 `sources.json` 和 `shiguang/` 继续驱动 TG 采集（写 `tg.db`）和旧站（现状见 `docs/legacy/README.md`），新版**复用**而不改它们的行为。

## 2. 统一条目（`rebang.items/1`）

生产者输出信封：`{"schema":"rebang.items/1","producer":"<分支名>","generated_at":"<带时区 ISO>","items":[...]}`；可选 `sources[]`（ingest）/`platforms[]`（bloggers），每项是带 `id`、`status`（ok/empty/error/cached/…）的对象，前端据此显示「暂时取不到」；可选 `translation{engine,translated,pending,untranslated}` 统计。

| 字段 | 必填 | 说明 |
|---|---|---|
| `id` | 是 | `"<source_id>:<native_id>"`；TG 用消息号，feed 用 guid，无 guid 用 `sha1(url)[:16]`。全站唯一、稳定（收藏/历史靠它） |
| `kind` | 是 | `news`（6 频道资讯）或 `post`（博主帖子） |
| `channel` | news 必填 | 必须等于 `channels.json` 中该来源所在频道；`post` 为 null |
| `source_id` / `source_name` | 是 | 来源 id 与显示名 |
| `title` | 是 | news 不能为空；post 可为空串 |
| `summary` | 是 | 卡片 3 行摘要用的纯文本；没有正文写空串，由前端显示「无正文」，**不编摘要**。摘要开头的裸链接由 ingest 去掉 |
| `body` | 否 | 正文纯文本（详情页整页正文） |
| `url` | 是 | 原文 http(s)，没有写空串 |
| `image` | 否 | `{url, width?, height?}` 或 null；banner 只取有合适大图的条目，不编图 |
| `image_local` | 否 | ingest 存到本地的图：`{path, rel, width, height}`；`rel` 必须是相对路径且不含 `..`，宽高为正整数，否则整条不合格。站点构建把它复制到 `<site>/media/<rel>`，前端用相对地址 `media/<rel>` |
| `published_at` | 是 | 带时区 ISO 8601（历史按北京时间日期分组） |
| `fetched_at` | 否 | 带时区 |
| `lang` | 是 | `zh` / `en` / … ；判断不了写 `und`（不翻译）。ingest 规则：TG 含汉字为 zh，否则 en；官方订阅按条判断、只看标题（摘要不参与）：先去掉裸链接，再去掉书名号《》、「」、“” 里的内容，剩下的只要有汉字就标 zh、不进翻译队列，否则 en（如 `Review of 《黑神话：悟空》` 是 en，`MacBook Pro M4 Max 评测` 是 zh）；GitHub Trending 含汉字为 zh。订阅条目入库时校验链接和图片，在本契约 http(s) 口径上额外检查主机名并拦截解析异常：不带协议的相对链接先用 xml:base / 订阅自身地址补全，补不出合格地址（或旧缓存没有基准地址）就把链接置空、条目保留，绝不因链接丢条；图片坏了只丢图、条目保留 |
| `translated` + `translation` | 否 | 非中文才翻；`translation={title, summary, body?, blocks?, body_pending?, engine, label:"机器翻译"}`。标题和摘要一旦有译文就写入，不必等正文或 blocks；正文稍后补上时详情页再换全文。正文还在排队时 `body_pending:true`，详情用已有的中文摘要并标明全文还在翻译，不把英文长文铺上去。入库时就译好，打开页面不现翻。流程：缓存 `var/rebang/translate/cache.json` 命中直接用 → 没命中进 `pending.json` → 由 Grok 翻好后 `python3 -m rebang.translate fill FILE --engine grok-bot` 回填，下次构建生效；只翻新增条目（增量）。公开新闻页会先抽全文（`rebang.extract`，按 URL 缓存，单轮有上限），抽失败则沿用原摘要 |
| `highlight` / `highlight_date` | 否 | 频道新闻展示标记。站点构建按滚动 24 小时内的独立来源互证重新计算，标记日期为构建时的北京时间日期。旧输入标记仍可读取。 |
| `blogger` | post 必填 | `{platform, handle, display_name, avatar?, verified?, metrics{reply,repost,like,quote,bookmark,view}?, media[{type:image|video|gif|youtube,url,preview_url?,duration_ms?}]（`youtube` 的 url 是 `https://www.youtube-nocookie.com/embed/<视频号>`，preview_url 是封面，站内查看器用嵌入播放器）, quote{handle,text,display_name?,published_at?,url?,...}|null, comments[{handle,text,display_name?,avatar?,published_at?,url?,like?,text_zh?}]?}`；评论最多 10 条，按点赞排序。`like` 是非负整数，拿不到不写。英文回复译文在 `text_zh`，原文留在 `text`。拿不到的字段不写，不编数字。Grok bot 的 4 类整理内容是 `platform:"grok"`、`handle` = 来源 id（hot-daily/x/world/github）、`channel:null` |
| `quote` | 否（news） | v13：TG 引用/转发的原帖。`{kind: forward|reply, source_name, url, text}`。`forward` = 频道转发别人的帖子，频道自己没写话时 `summary/body` 为空串，前端标「转发」；`reply` = 频道引用了某条帖子，`title/summary/body` 是频道自己的话，`quote.text` 是被引用的原文（≤1500 字）。来自 t.me 公开页面，拿不到不写 |
| `tg` | 否（news） | Telegram 公开页面上的附加信息。`{views?, views_label?, reactions[{emoji,count,label}]?, comments_total?, comments[{display_name,text,id?,published_at?,reply_to?,reply_to_id?,reply_text?}]?, media[{type:image\|video,url,preview_url?}]?, video_unavailable?, fetched_at?}`。媒体地址仅来自公开页面；只有封面时不假造视频源。付费星星记为 ⭐，自定义表情（没有字符）跳过；评论只在频道开了公开讨论区、挂件里能看到时才写，否则不写，**不编** |
| `blocks` | 否 | 公众号/博客文章，以及从公开新闻页抽出的正文，按原文顺序：`p{text}`、`h{text,level}`、`quote{text}`、`ul/ol{items}`、`pre{text}`、`hr`、`img{src,width?,height?,alt?,local?,missing?}`。`blocks` 存在时 `body` = 块里的文字。公众号图片在 bloggers 运行时不带 Referer 下载到 `var/rebang/media/wechat/`（`local{path,rel,width,height}`），站点构建复制到 `media/wechat/…` 并去掉 `local`；没下下来的公众号图标 `missing:true`，前端如实写「这张图没存下来」，不外链（外站引用公众号图床会变成「未经允许不可引用」占位图）。Wechat2RSS 加的开头「原创/作者/日期/属地」行、封面图、结尾「跳转微信打开」都去掉 |

### 2.1 TG 公开页面附加信息（`rebang.tgmeta/1`，v13）

`python3 -m rebang.tgmeta` 读 `channels.json` 里的 TG 频道，低频翻 `https://t.me/s/<频道>`（只读、匿名、不登录），存到 `var/rebang/cache/tgmeta.json`（不进仓库）：每条消息的频道自己的话、转发来源、引用原文、表情回应、浏览数；每个频道每 24 小时用最新一条探测一次是否开了公开讨论区（`?embed=1&discussion=1`），开了才抓最近 48 小时内每频道最多 10 条消息的公开评论（6 小时内不重抓）。挂件加 `comments_limit=30`，每条最多存最近 30 条评论（评论楼），带楼号 `id`、被回复的楼号 `reply_to_id` 和原话 `reply_text`（≤120 字）；只有图片/贴纸的评论没有文字，跳过。保留 16 天。`python3 -m rebang.ingest` 默认读这个文件（`--no-tgmeta` 关掉，文件不存在就跳过）。旧 `tg.db` 对引用消息存的是被引用的原文，有 tgmeta 时以 t.me 页面上频道自己的话为准。

## 3. 热搜（`rebang.hotsearch/1`）

`{"schema","generated_at","providers":[{"id","name","status":"ok|empty|error","fetched_at|null","error?","items":[{"rank","title","url","pinned","hot_score?","hot_label?","summary?","image?"}]}]}`

- 每家一个适配器 `rebang/hotsearch/providers/<id>.py`，暴露 `fetch(http, now) -> list[dict]`；异常/非 200/结构变化 → 该家 `status=error, items=[]`，其它家不受影响。
- `status!=ok` 时 items 必须为空：不编排名、不拿旧榜冒充今天。前端显示「暂时取不到」。
- 换提供方：改 `hotsearch.json` + 增删适配器文件，前端不动。
- 归档：每次抓取后 `rebang/hotsearch/archive.py` 把至少一家 ok 的快照存成 `var/rebang/hotsearch-archive/<北京日期>.json`，同一天只留最后一次可用的，保留 60 天；全部失败的那次不覆盖当天已有的。

## 4. 模块目录

| 模块 | 代码与测试 |
|---|---|
| 契约 | `rebang/contract/`、`tests/test_rebang_contract.py` |
| 资讯来源 ingest | `rebang/ingest/`、`tests/test_rebang_ingest*.py`、`tests/fixtures/rebang/ingest/` |
| TG 附加信息 tgmeta | `rebang/tgmeta/`、`tests/test_rebang_tgmeta*.py` |
| 热搜 hotsearch | `rebang/hotsearch/`、`tests/test_rebang_hotsearch*.py`、`tests/fixtures/rebang/hotsearch/` |
| 博主与翻译 | `rebang/bloggers/`、`rebang/translate/`、`tests/test_rebang_bloggers*.py`、`tests/fixtures/rebang/bloggers/` |
| 建站与前端 | `rebang/site/`、`web-v11/`、`tests/test_rebang_site*.py`、`tests/test_rebang_dedup.py`（频道内合并）、`tests/rebang_site*.test.js` |
| 归档、收藏、搜索 | `rebang/archive/`、`web-v11/features/`、`tests/test_rebang_archive*.py`、`tests/rebang_features*.test.js` |
| 8:30 私聊稿 | `rebang/push/`、`tests/test_rebang_push*.py` |

各模块入口命令见 [`MODULES.md`](MODULES.md)。

运行产物（已 gitignore）：

- `var/rebang/in/<producer>.json`：各生产者最新一次输出（items 信封或热搜）。producer ∈ `ingest` / `hotsearch` / `bloggers`。
- `var/rebang/archive/YYYY-MM-DD.json`：按北京日期累积的条目，供搜索索引和 8:30 稿补漏（生产放在 `/workspace/shiguang-prod/var/rebang/`）。按日期翻旧资讯的「历史」页 11/15 21:26 已去掉。
- `var/rebang/hotsearch-archive/YYYY-MM-DD.json`：热搜每日最后一份。
- `var/rebang/translate/{cache,pending}.json`：译文缓存与待翻队列。
- `var/rebang/cache/`（tgmeta、ingest 订阅缓存）、`var/rebang/x-dump/`（X 原始响应）、`var/rebang/media/`（公众号图片）、`var/rebang/logs/`（`tools/rebang_refresh.sh` 日志）。
- `site-v11/`：新版静态站构建输出（`python3 -m rebang.site --out <dir> [--hot-archive DIR]`）。`<site>/data/` 下：
  - `meta.json`（`rebang.site-meta/1`）：`built_at`、`data_at`、`today`、`page_size`、`note`、`public_base`（8:30 私聊稿链接 = `public_base#/item/<id>`）、`counts`、`channels[{slug,name,order,desc,sources,unavailable,total,feed_total,merged_total,pages,banner[≤5]}]`。
  - `channel/<slug>/page-<n>.json`（`rebang.page/1`）：每页 30 条，`has_more` 到最后一页为 false；「查看更多」整页按页往下加载到「没有更多了」。
  - 频道内跨来源合并（第 5 步，`rebang/site/dedup.py`）：**只在同一频道内合并，不跨频道**（一个来源只进一个频道，频道归属不变）。建站预处理只按 id 去重（同 id 取较新），原始链接完全相同的不同 id 都保留，交给合并步骤折叠；旧 `hot-daily` 新闻仍按同频道同链接去重，剩余旧条目保留原深链。旧整理稿不参与取证，原有旧标仍用于选择主条。只认一种「同一条」（2026-11-25 第 3 轮复核到上限后收紧，宁可几乎不合也不误合）：**规范化后的链接相同且原标题相同**，并且是不同来源、组里最早最晚相差 ≤24 小时，缺一不合。链接规范化：http→https、去 `www.`（`m.` 等子域保留）、去尾 `/`、路径大小写不动；只去明确的追踪参数：`utm_*`、`fbclid`/`gclid` 等点击追踪参数全局去，BBC 的 `at_*` 只在 bbc.com / bbc.co.uk 及其子域去，`ref_src`/`si`/`spm_id_from` 等只在 X、YouTube、B 站等对应网站去，`ref`/`from`/`at_format` 等在其它网站保留；其余参数按名字排序、同名参数保持原相对顺序；`#` 片段去掉，以 `/` 或 `!` 开头的路由片段保留；没有链接或不是 http(s) 的不合。原标题只去首尾空白、合并连续空白，**不改大小写、不改全半角、不去标点**（`100 mW`/`100 MW`、`？`/`。` 都算不同），不用机器翻译标题比较。因此：滚动新闻共用一个链接但标题不同（如「上调」/「下调」）不合；**仅标题相同、链接不同的不合**（如同名「实时汇总」）；**同来源同链接同标题也不合**（每组每个来源最多一条）。分组按（规范化链接, 原标题）分桶，桶内按（发布时间, id）从早到晚逐条放进第一个没有同来源、放进去后整组跨度仍 ≤24 小时的组，放不进就自成一组；结果与输入顺序无关。折叠仍按旧重点标和时间选择主条。选完清掉公开条目的旧重点标，再按 id 写入新标记（见 [今日重点规则](HIGHLIGHTS-SCORING.md)）。主条在分页和 `banner` 里多一个可选字段 `merged[{id, source_id, source_name, title, title_zh?, url, published_at}]`（按时间正序），前端在列表行和顶部大图卡都显示「另有 N 个来源」（按 `source_id` 计数）折叠列表；被折叠的完整条目写进 `channel/<slug>/merged.json`（`rebang.merged/1`：`{schema, channel, items}`），**`id-index.json` 里被折叠条目的 id 也指向这个 `merged.json`**；详情页先按 id 经 `id-index` 读本次发布的完整条目，读不到才用收藏/搜索快照兜底，所以联网时收藏/深链/搜索打开的都是带正文和今日重点标的完整条目。读 `id-index.json` 和正文所在文件（分页或 `merged.json`）**各限时 5 秒**，串行最长约 10 秒；超时或离线时，有快照的照样打开快照，但可能缺正文和今日重点标，没快照的提示「这条已经不在最近一次发布的数据里了」。打开还在加载时，关闭详情、点返回、浏览器前进后退、切到别的页，或又打开了别的条目，这次加载作废：晚到的结果不打开详情、不改地址栏、不覆盖已显示的快照。频道的 `total`/`feed_total` 只数主条，另加 `merged_total`；`counts.news` 仍是全部条数，搜索索引收到每个 id。旧前端忽略 `merged` 字段，只是频道里不再出现被折叠的条目。
  - `hotsearch.json`（当前）、`hotsearch/index.json`（`rebang.hotsearch-index/1`：`today`、`current_at`、`dates[{date,generated_at}]`）+ `hotsearch/<date>.json`（往日最后一份）。
  - `bloggers.json`（`rebang.site-bloggers/1`）：`platforms[{id,name,login,curated,icon,connected,count,status,reason,last_ok_at,accounts[{handle,name,key,total}]}]` + `items`（每平台、每人各取最新 10 条做预览）；`blogger/<platform>/<all|key>/page-<n>.json` 是每平台、每人的全部帖子分页（`key = "h-" + sha1(handle)[:10]`），索引和每个分页都带与 `meta.json` 相同的 `built_at` 和 `blogger_revision`（博主名单、索引、分页规则和全部有序帖子内容的指纹，同一秒内重建也能区分）。版本不明或不匹配不显示为空、不拼页；页脚可刷新后重新读索引。输出帖子带 `feed_order`，是本次建站按发布时间（保留微秒）倒序、同刻按 ID 升序的位置，平台流/个人流沿用；不回写采集或归档。
  - `meta.json` 的 `health_summary` 含 `total`（来源数）和 `issues`（健康以外的来源数），均按 `health.json` 的顶层来源计数。入口按 `built_at`、看板按自己的 `generated_at` 与当前时间比较，超过 3 小时提示快照已过期。
  - `health.json`（`rebang.source-health/1`）记录 `generated_at` 和 `sources[]`。来源包括六个频道的每个新闻源（含 TG）和博主名单中的各平台，平台附 `accounts[]`。各行包括 `id`、`name`、`group`、`status`、`last_ok_at`、`count`、`run_count`、`reason` 和 `issue_since`。`count` 为最近可用条数（新闻是采集窗口内条数），`run_count` 为本轮从来源得到的条数，未知时为 `null`。`issue_since` 是异常时用于显示间隔的时间锚点，通常是上次成功时间，X 断更时用导出时间，部分账号异常时用受影响账号中最早的锚点。
    - `ok` 正常。采集顺利但没有条目也属正常。`stale` 断更。复用 X 36 小时的导出过期规则，其余成功结果超过 48 小时判为断更。`login_expired` 沿用采集器显式判定。`failed` 为最近一轮采集失败或采集时间无效。`not_configured` 无名单、缺少配置或尚无采集记录。`unknown` 为无法识别的状态。博主平台按账号中最严重的状态展示，依次为登录失效、失败、断更、未配置、状态未知、正常。
    - 时间带时区，未知用 `null`，超出当前时间 5 分钟的采集时间不计作成功。`reason` 只从固定文案生成；采集成功但缓存写入失败时只给出提示，不丢弃已采集的条目。原始错误、配置路径、接口地址、响应内容和凭证不进入该产物。
  - `id-index.json`：`id → 所在分页文件`，深链 `#/item/<id>` 冷启动用。
  - `search-index.json`：搜索用。
  - `<site>/media/`：本地图；`<site>/icons/`：平台官方图标（来源与许可见 `web-v11/icons/README.md`）。

旧 `site/`、`web/`、`pipeline.py` 行为不改。`tools/publish_pages.sh` 把 `site-v11/` 放进 gh-pages 的 `rebang/`，服务器挂到根路径（见 `OPERATIONS.md`）。

## 5. 测试命令约定

```bash
python3 -m pytest -q -p no:cacheprovider tests/test_rebang_contract.py        # 契约
python3 -m pytest -q -p no:cacheprovider tests/test_rebang_<area>*.py         # 单个模块
python3 -m pytest -q -p no:cacheprovider                                       # 全量（基线见 HANDOFF）
node --test tests/*.test.js                                                    # 前端单测
NO_FETCH=1 python3 pipeline.py                                                 # 旧站构建不能被打破
```

- 改动先写「可观察验收结果」，最终从用户实际入口（手机尺寸打开站点 / dry-run 终端输出）验证；单测只是辅助。线上回归：`python3 docs/rebang-v1/evidence/integration-v13/capture.py <站点地址> <截图前缀>`（390x844 真触摸，76 项）。
- 单测一律用 `tests/fixtures/rebang/<area>/` 下的合成或已脱敏的真实样本，**不联网**；真实抓取只在显式 `--live` 冒烟里跑，且只读、低频。
- 依赖只用标准库 + 已有的 beautifulsoup4、Pillow；要加依赖先在 `HANDOFF.md` 写明并经确认。
- 所有时间展示与日期分组用北京时间（Asia/Shanghai）。
