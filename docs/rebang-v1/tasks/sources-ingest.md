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
