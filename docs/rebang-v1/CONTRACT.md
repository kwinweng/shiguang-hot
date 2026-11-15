# 拾光热榜 v1 数据契约

集成分支 `feat/rebang-v1` 所有。各功能分支**只读**本契约；要改字段、频道或目录，先回集成分支改契约和 `tests/test_rebang_contract.py`，再让各分支 rebase。依据：`/workspace/deliverables/daily-site/docs/architecture-plan-v1-20261115.md`（2026-11-15）。

## 1. 唯一真相

| 文件 | 内容 |
|---|---|
| `rebang/contract/channels.json` | 6 个频道（current 时事 / world 环球 / finance 财经 / tech-ai 科技与 AI / digital 数码 / tools 工具与项目）与来源映射；18 个 TG（不含 reorx_share）；今日重点只给频道里同链接条目打标（2026-11-15 21:26 起不再进频道） |
| `rebang/contract/hotsearch.json` | 热搜提供方 baidu、zhihu、bilibili（11/15 20:41 阿欢确认；不要微博），可替换；每家最多 51 条（百度 = 置顶 1 + 普通 50）；展示在底栏「热搜」页（`view:hot`），按北京日期归档（`archive.dir/keep`） |
| `rebang/contract/bloggers.json` | 博主平台与名单：X 16、Grok bot 4（今日重点/推特爆款/环球要闻/GitHub 热门，`curated-inbox`，11/15 21:26 从主题频道移来）、博客 7、即刻 9、微博 6、公众号 6、知乎 0 |
| `rebang/contract/schema.py` | 纯标准库校验：`validate_item` / `validate_items_envelope` / `validate_hotsearch` |

旧 `sources.json` 和 `shiguang/` 继续驱动现有线上站与 TG 采集（写 `tg.db`），新版**复用**而不改它们的行为。

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
| `lang` | 是 | `zh` / `en` / … ；判断不了写 `und`（不翻译）。ingest 规则：含中日韩字符为 zh，否则 en |
| `translated` + `translation` | 否 | 非中文才翻；`translation={title, summary, body?, engine, label:"机器翻译"}`。入库时就译好，打开页面不现翻。流程：缓存 `var/rebang/translate/cache.json` 命中直接用 → 没命中进 `pending.json` → 由 Grok 翻好后 `python3 -m rebang.translate fill FILE --engine grok-bot` 回填，下次构建生效；只翻新增条目（增量） |
| `highlight` / `highlight_date` | 否 | 今日重点标记（站上不单开栏） |
| `blogger` | post 必填 | `{platform, handle, display_name, avatar?, verified?, metrics{reply,repost,like,quote,bookmark,view}?, media[{type:image|video|gif,url,preview_url?,duration_ms?}], quote{handle,text,display_name?,published_at?,url?,...}|null, comments[{handle,text,display_name?,avatar?,published_at?}]?}`；拿不到的字段不写，不编数字。Grok bot 的 4 类整理内容是 `platform:"grok"`、`handle` = 来源 id（hot-daily/x/world/github）、`channel:null` |

## 3. 热搜（`rebang.hotsearch/1`）

`{"schema","generated_at","providers":[{"id","name","status":"ok|empty|error","fetched_at|null","error?","items":[{"rank","title","url","pinned","hot_score?","hot_label?","summary?","image?"}]}]}`

- 每家一个适配器 `rebang/hotsearch/providers/<id>.py`，暴露 `fetch(http, now) -> list[dict]`；异常/非 200/结构变化 → 该家 `status=error, items=[]`，其它家不受影响。
- `status!=ok` 时 items 必须为空：不编排名、不拿旧榜冒充今天。前端显示「暂时取不到」。
- 换提供方：改 `hotsearch.json` + 增删适配器文件，前端不动。
- 归档：每次抓取后 `rebang/hotsearch/archive.py` 把至少一家 ok 的快照存成 `var/rebang/hotsearch-archive/<北京日期>.json`，同一天只留最后一次可用的，保留 60 天；全部失败的那次不覆盖当天已有的。

## 4. 目录约定（按分支划地盘，减少冲突）

| 目录 | 归属分支 |
|---|---|
| `rebang/contract/`、`docs/rebang-v1/CONTRACT.md`、`tests/test_rebang_contract.py`、`HANDOFF.md` | 集成 `feat/rebang-v1` |
| `rebang/ingest/`、`tests/test_rebang_ingest*.py`、`tests/fixtures/rebang/ingest/` | `feat/rebang-v1-sources-ingest` |
| `rebang/hotsearch/`、`tests/test_rebang_hotsearch*.py`、`tests/fixtures/rebang/hotsearch/` | `feat/rebang-v1-hotsearch` |
| `rebang/bloggers/`、`rebang/translate/`、`tests/test_rebang_bloggers*.py`、`tests/fixtures/rebang/bloggers/` | `feat/rebang-v1-bloggers` |
| `rebang/site/`、`web-v11/`（除 `web-v11/features/`）、`tests/test_rebang_site*.py`、`tests/rebang_site*.test.js` | `feat/rebang-v1-frontend-v11` |
| `rebang/archive/`、`web-v11/features/`、`tests/test_rebang_archive*.py`、`tests/rebang_features*.test.js` | `feat/rebang-v1-history-favorites-search` |
| `rebang/push/`、`tests/test_rebang_push*.py` | `feat/rebang-v1-push-0830` |

运行产物（已 gitignore）：

- `var/rebang/in/<producer>.json`：各生产者最新一次输出（items 信封或热搜）。producer ∈ `ingest` / `hotsearch` / `bloggers`。
- `var/rebang/archive/YYYY-MM-DD.json`：按北京日期累积的条目，供搜索索引（生产里放哪儿上线时再定）。按日期翻旧资讯的「历史」页 11/15 21:26 已去掉。
- `var/rebang/hotsearch-archive/YYYY-MM-DD.json`：热搜每日最后一份。
- `var/rebang/translate/{cache,pending}.json`：译文缓存与待翻队列。
- `site-v11/`：新版静态站构建输出（`python3 -m rebang.site --out <dir> [--hot-archive DIR]`）。`<site>/data/` 下：
  - `meta.json`（`rebang.site-meta/1`）：`built_at`、`data_at`、`today`、`page_size`、`note`、`public_base`（8:30 私聊稿链接 = `public_base#/item/<id>`）、`counts`、`channels[{slug,name,order,desc,sources,unavailable,total,feed_total,pages,banner[≤5]}]`。
  - `channel/<slug>/page-<n>.json`（`rebang.page/1`）：每页 30 条，`has_more` 到最后一页为 false；「查看更多」整页按页往下加载到「没有更多了」。
  - `hotsearch.json`（当前）、`hotsearch/index.json`（`rebang.hotsearch-index/1`：`today`、`current_at`、`dates[{date,generated_at}]`）+ `hotsearch/<date>.json`（往日最后一份）。
  - `bloggers.json`（`rebang.site-bloggers/1`）：`platforms[{id,name,login,curated,icon,connected,count,status,reason,last_ok_at,accounts[{handle,name,key,total}]}]` + `items`（每平台、每人各取最新 10 条做预览）；`blogger/<platform>/<all|key>/page-<n>.json` 是每平台、每人的全部帖子分页（`key = "h-" + sha1(handle)[:10]`）。
  - `id-index.json`：`id → 所在分页文件`，深链 `#/item/<id>` 冷启动用。
  - `search-index.json`：搜索用。
  - `<site>/media/`：本地图；`<site>/icons/`：平台官方图标（来源与许可见 `web-v11/icons/README.md`）。

旧 `site/`、`web/`、`pipeline.py`、`gh-pages` 发布脚本不动；新版切换上线在集成阶段另批。

## 5. 测试命令约定

```bash
python3 -m pytest -q -p no:cacheprovider tests/test_rebang_contract.py        # 契约
python3 -m pytest -q -p no:cacheprovider tests/test_rebang_<area>*.py         # 本分支
python3 -m pytest -q -p no:cacheprovider                                       # 全量（基线见 HANDOFF）
node --test tests/*.test.js                                                    # 前端单测
NO_FETCH=1 python3 pipeline.py                                                 # 旧站构建不能被打破
```

- 每个分支先写「可观察验收结果」（任务卡第一条），最终从用户实际入口（手机尺寸打开新站 / dry-run 终端输出）验证；单测只是辅助。
- 单测一律用 `tests/fixtures/rebang/<area>/` 下的合成或已脱敏的真实样本，**不联网**；真实抓取只在显式 `--live` 冒烟里跑，且只读、低频。
- 依赖只用标准库 + 已有的 beautifulsoup4、Pillow；要加依赖写进任务卡并在集成时确认。
- 所有时间展示与日期分组用北京时间（Asia/Shanghai）。
