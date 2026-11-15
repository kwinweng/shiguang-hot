# 拾光热榜 v1 数据契约

集成分支 `feat/rebang-v1` 所有。各功能分支**只读**本契约；要改字段、频道或目录，先回集成分支改契约和 `tests/test_rebang_contract.py`，再让各分支 rebase。依据：`/workspace/deliverables/daily-site/docs/architecture-plan-v1-20261115.md`（2026-11-15）。

## 1. 唯一真相

| 文件 | 内容 |
|---|---|
| `rebang/contract/channels.json` | 6 个频道（current 时事 / world 环球 / finance 财经 / tech-ai 科技与 AI / digital 数码 / tools 工具与项目）与来源映射；18 个 TG（不含 reorx_share）；今日重点拆分规则 |
| `rebang/contract/hotsearch.json` | 热搜提供方（第一期建议：baidu、zhihu、bilibili；不要微博）；可替换 |
| `rebang/contract/bloggers.json` | 博主名单：X 16、博客 7、即刻 9、微博 6、公众号 6、知乎 0 |
| `rebang/contract/schema.py` | 纯标准库校验：`validate_item` / `validate_items_envelope` / `validate_hotsearch` |

旧 `sources.json` 和 `shiguang/` 继续驱动现有线上站与 TG 采集（写 `tg.db`），新版**复用**而不改它们的行为。

## 2. 统一条目（`rebang.items/1`）

生产者输出信封：`{"schema":"rebang.items/1","producer":"<分支名>","generated_at":"<带时区 ISO>","items":[...]}`。

| 字段 | 必填 | 说明 |
|---|---|---|
| `id` | 是 | `"<source_id>:<native_id>"`；TG 用消息号，feed 用 guid，无 guid 用 `sha1(url)[:16]`。全站唯一、稳定（收藏/历史靠它） |
| `kind` | 是 | `news`（6 频道资讯）或 `post`（博主帖子） |
| `channel` | news 必填 | 必须等于 `channels.json` 中该来源所在频道；`post` 为 null |
| `source_id` / `source_name` | 是 | 来源 id 与显示名 |
| `title` | 是 | news 不能为空；post 可为空串 |
| `summary` | 是 | 卡片 3 行摘要用的纯文本；没有正文写空串，由前端显示「无正文」，**不编摘要** |
| `body` | 否 | 正文纯文本（详情页整页正文） |
| `url` | 是 | 原文 http(s)，没有写空串 |
| `image` | 否 | `{url, width?, height?}` 或 null；banner 只取有合适大图的条目，不编图 |
| `published_at` | 是 | 带时区 ISO 8601（历史按北京时间日期分组） |
| `fetched_at` | 否 | 带时区 |
| `lang` | 是 | `zh` / `en` / … |
| `translated` + `translation` | 否 | 非中文才翻；`translation={title, summary, body?, engine, label:"机器翻译"}`。入库时就译好，打开页面不现翻 |
| `highlight` / `highlight_date` | 否 | 今日重点标记（站上不单开栏） |
| `blogger` | post 必填 | `{platform, handle, display_name, avatar?, verified?, metrics{reply,repost,like,quote,bookmark,view}?, media[{type:image|video|gif,url,preview_url?,duration_ms?}], quote{handle,text,...}|null}`；拿不到的字段不写，不编数字 |

## 3. 热搜（`rebang.hotsearch/1`）

`{"schema","generated_at","providers":[{"id","name","status":"ok|empty|error","fetched_at|null","error?","items":[{"rank","title","url","pinned","hot_score?","hot_label?","summary?","image?"}]}]}`

- 每家一个适配器 `rebang/hotsearch/providers/<id>.py`，暴露 `fetch(http, now) -> list[dict]`；异常/非 200/结构变化 → 该家 `status=error, items=[]`，其它家不受影响。
- `status!=ok` 时 items 必须为空：不编排名、不拿旧榜冒充今天。前端显示「暂时取不到」。
- 换提供方：改 `hotsearch.json` + 增删适配器文件，前端不动。

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
- `var/rebang/archive/YYYY-MM-DD.json`：按北京日期累积的条目（history 分支维护，生产里放哪儿上线时再定）。
- `site-v11/`：新版静态站构建输出。`site-v11/data/` 下：`meta.json`、`channel/<slug>/page-<n>.json`（每页 30 条，最后一页 `has_more:false`）、`hotsearch.json`、`bloggers.json`、`history/index.json` + `history/<date>.json`、`search-index.json`。

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
