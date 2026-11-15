# 任务卡：feat/rebang-v1-sources-ingest（来源接入与分类）

- **可观察验收结果（从用户入口验证，先写这条再动手）**：在新站（`python3 -m rebang.site` 构建后本地打开 site-v11/index.html，手机尺寸 393×852）6 个频道每个都能看到来自其配置来源的真实条目，竹新社只出现在时事、Apple Newsroom 只出现在数码；英文条目显示中文译文并标「机器翻译」。
- worktree：`/workspace/rebang-v1-wt/sources-ingest`，从 `feat/rebang-v1` 建。
- 做什么：把 `channels.json` 里全部资讯来源变成 `rebang.items/1` 条目，按「整源一频道」归类，写 `var/rebang/in/ingest.json`。
  - TG 18 个：只读 `tg.db`（现有 `shiguang/ingest/telegram.py` 采集，能力同 f2e9c04 交接所述），不改采集器；图片沿用 `media/` 14 天缓存。
  - 官方订阅 6 个（BBC/卫报/Google/OpenAI/GitHub Blog/Apple Newsroom）：复用 `shiguang/ingest/web.py` 解析；GitHub Trending 解析公开页。
  - 现有成品 4 个（推特爆款 x、环球要闻 world、GitHub 热门 github、今日重点 hot-daily）：复用 `shiguang/ingest/feeds.py`。注意：仓库里 `public-feeds/*` 最新只到 2026-10-23，先只读查清当前成品实际落在哪里，查不到就如实报缺口，不编。
  - 今日重点：按 `channels.json.highlights.rule` 打 `highlight` 或归频道。
  - 英文条目（BBC/卫报/Google/OpenAI/GitHub/Apple）调用 `rebang/translate/`（bloggers 分支提供接口 `translate(texts, src_lang) -> list[str]|None`）；接口未合入前留 `translated=false`，不阻塞。
- 改哪些目录：`rebang/ingest/`、`tests/test_rebang_ingest*.py`、`tests/fixtures/rebang/ingest/`。
- 接口：CLI `python3 -m rebang.ingest --db tg.db --out var/rebang/in/ingest.json [--no-fetch]`；函数 `collect(now, *, fetch=False) -> envelope`。
- 验收：`python3 -m pytest -q tests/test_rebang_contract.py tests/test_rebang_ingest*.py` 全绿；`python3 -m rebang.ingest --no-fetch` 对真实 `tg.db` 输出通过 `validate_items_envelope`，18 个 TG 来源都有归属、无 reorx_share、每条 channel 与配置一致；一次 `--live` 只读冒烟记录 7 个订阅/页面的真实条数。
- 不许碰：`sources.json`、`shiguang/`、`pipeline.py`、`tools/`、`tg.db` 写入、`rebang/contract/`、其它分支目录。不改线上采集与例程。

## 结果（2026-11-15 20:50 北京时间，sources-ingest 分支）

- 实现：`rebang/ingest/`（`core.py` + CLI `__main__.py`）。`python3 -m rebang.ingest --db <tg.db> [--media-root DIR] --out var/rebang/in/ingest.json [--no-fetch | --live] [--days 14]`；默认联网抓 7 个订阅/页面，`--no-fetch` 读 `var/rebang/cache/ingest/` 缓存（没缓存标 `not_fetched`，不编）。`collect(now, *, fetch=False, …)` 可注入 `http_get` / `inbox_loader` / `translator` 供测试。
- tg.db 只读（`mode=ro` + `query_only`），不迁移不写；只收最近 14 天（`--days`）；只取 channels.json 的 18 个 TG，`reorx_share` 等排除源不出现。TG 无标题：`【…】`取括号内，否则首行（过长截到首句/双空格/60 字），摘要为剩余原文。
- 图片 14 天：TG 用 tg.db 旁 `media/` 缓存（`--media-root`，生产 tg.db 在 `/workspace/shiguang-prod`，媒体也在那）；订阅源用 RSS 里的 https 图；超过 14 天的条目不带图。
- 每日成品实际位置（只读查清，均为盒子上原始投递目录，`shiguang.ingest.feeds.load_issues(local=True)` 已能读）：
  - 推特爆款 `x`：`/workspace/x-digest/YYYY-MM-DD.json`，最新 2026-11-14（文件 11-14 08:15 写入；查时 11-15 当天文件还没有）。
  - 环球要闻 `world`：`/workspace/world-brief/YYYY-MM-DD/brief.json`，最新 11-14（11-14 21:13 写入，`/workspace/global-brief/` 生成）。
  - GitHub 热门 `github`：`/workspace/feeds-inbox/github/YYYY-MM-DD/feed.json`，最新 11-15（09:39 写入）。
  - 今日重点 `hot-daily`：`/workspace/feeds-inbox/hot-daily/YYYY-MM-DD/feed.json`，最新 11-14（22:13 写入，`/workspace/hot-daily/` 生成）。
  - 仓库与 `/workspace/shiguang-prod` 的 `public-feeds/` 都只到 10-23：公开归一化发布停在那天，原因未查（不在本分支范围），不影响新版读取原始目录。
- 今日重点：link 命中已收条目只打 `highlight/highlight_date`；否则按 `sources` 第一个能匹配 id/name 的来源归频道，都不行归 current（source_id 仍为 hot-daily）。实测 11-01～11-14 的 98 条全部命中已收 TG 条目，没有额外条目。
- 翻译：`rebang.translate.translate(texts, 'en')` 存在就调（结果缓存在 `var/rebang/cache/ingest/translations.json`，不重复翻）；本分支尚无该模块 → 全部 `translated=false`。GitHub Trending 仓库名不翻，只翻简介。
- 证据：`docs/rebang-v1/evidence/sources-ingest/live-smoke.txt`、`no-fetch-repo-tgdb.txt`。
- 用户入口验收（新站 6 频道看到条目）需 frontend-v11 构建器合入后在集成分支做；本分支只验到 `var/rebang/in/ingest.json` 层。

### 契约变更请求（未改契约）
1. 本地图片：契约 `image.url` 只收 http(s)，但 TG 图（media/ 缓存）和成品期刊图都是本地文件。现在输出 `image: null` + 额外字段 `image_local {path, rel?, width, height, alt?}`；请集成分支定：正式加 `image_local`（由 site 构建复制进 `site-v11/media/`），或允许 `image.url` 为站内相对路径。
2. 信封额外字段 `sources[]`（每源 id/name/type/channel/status/count/error?/fetched_at?/latest_issue?/marked?）和 `translation{available, translated}`：校验器已容忍，建议写进 CONTRACT 供前端显示「暂时取不到」。
