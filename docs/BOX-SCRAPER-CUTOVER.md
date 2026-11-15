# Box 采集与发布（`tools/box_scrape.sh`）

2026-10 从 GitHub Actions 迁到盒子（PR A / step 0）。现在 TG 采集、`tg.db` 提交和 gh-pages 发布都由这里完成；GitHub Actions（`.github/workflows/hourly.yml`）只剩手动跑测试，没有构建、部署或 Pages 写权限。

## 现状

- 生产克隆：`/workspace/shiguang-prod`（迁移时文档写的 `/opt/shiguang` 在盒子上不存在）。
- 调度：盒子没有 cron，由工头「热榜抓取发布」例程每小时 :07/:37（Asia/Shanghai）运行。必须只启用一个生产例程。2026-11 核过的命令是 `sh tools/box_scrape.sh --checkout /workspace/shiguang-prod --log-dir /workspace/shiguang-logs`（工头例程 `automation-1792760094684`，`CRON_TZ=Asia/Shanghai`，`7,37 * * * *`）；11/16 00:37 一轮日志仍写入该目录。不传 `--log-dir` 时日志写 `<checkout>/logs/box-scrape/`。
- v11 刷新是另一个脚本 `tools/rebang_refresh.sh`（见 `docs/rebang-v1/OPERATIONS.md`），发布时会等 `.box-scrape.lock`，两者互斥。

## 每轮做什么

1. 取 `<checkout>/.box-scrape.lock`（flock）；同一 checkout 的第二轮直接跳过（busy）。
2. 要求在 `main` 且受跟踪文件干净；`fetch origin main` 后 `merge --ff-only`。若有未推送的提交且只改了 `tg.db`，先建 `backup/<完整 SHA>` 分支再 `reset --hard origin/main`；涉及其他文件或含合并提交就报错停止，不丢提交。**所以合并到 main 的代码会在下一轮生效。**
3. 跑 `pipeline.py`（公开模式；Telegram、RSS/YouTube 和 trial 试跑采集），写 `tg.db`、`media/`，建旧站 `site/`。
4. `tools/persist_action_data.sh`：无变化不提交；有变化先备份库，只提交 `tg.db`（提交信息 `data YYYY-MM-DDTHH`）并普通推送 main。推送被拒时在最新 `origin/main` 上重建一次再试，仍失败就非零退出；不强推、不 merge/rebase 数据库。远端自基线后改过 `tg.db` 时停止覆盖，日志给出 `.git/persist-db.*/tg.db` 备份路径。
5. 持久化成功后更新 `site/build-info.json`，调 `tools/publish_pages.sh --already-built`。发布失败记 `Pages publish failed`，不改变采集退出状态、不撤销数据提交。

盒子全局 pre-push 钩子挡住对 `main` 的推送，只有 `persist_action_data.sh` 在这一次推送里设置 `ALLOW_MAIN_PUSH=publish`（不 export，例程里也不设）。

数据库自然小时配额与失败退避不变（见 `docs/SOURCE-FETCH-OPERATIONS.md`），:37 可能记 `hour_used`，两次调度不保证两次实际抓取。

## 发布脚本 `tools/publish_pages.sh`

- 独立执行会先跑 `SITE_MODE=public MAIL_DIGEST=0 TZ=Asia/Shanghai python pipeline.py` 和 `tools/write_build_info.py`；`--already-built` 跳过构建，要求现有 `site/index.html` 和 `site/build-info.json`。
- 在临时 worktree 里把 `site/` 放根目录、`site-v11/` 放 `rebang/`（`REBANG_PUBLISH=0` 不带，但线上根路径会因此 404），加 `.nojekyll`，默认不写 CNAME（`PAGES_CNAME` 非空才写）。拒绝缺入口、缺元数据或含 `.env*` 的树。
- `git push --force origin <commit>:refs/heads/gh-pages`：gh-pages 每次只有一个无父提交，没有历史；需要回退时另建备份分支（例如 `gh-pages-pre-rebang-20261115`）。
- `--dry-run` 只准备提交并打印文件数和 SHA，不推送。

## 检查与隔离运行

```sh
sh tools/box_scrape.sh --checkout /workspace/shiguang-prod --dry-run          # 只打印计划
sh tools/box_scrape.sh --checkout /workspace/shiguang-prod --test-dir /tmp/shiguang-check-001 --limit 2
```

`--test-dir` 必须不存在且在 checkout 外：复制公开代码、配置、`public-feeds` 和数据库快照，不复制 `.env`、Git 元数据或私有 inbox，不执行 Git。`--limit N` 只能配 `--test-dir`：按 source id 取前 N 个公开 Telegram/feed 源，每源只读首页，不翻页、不补 gap、不下载图片、禁用 trial。首页全是已有消息时 `new=0` 是正常的。

## 故障与回滚

- **busy 长期不退 / blocked / 持续错误 / Pages 落后**：看日志里的 `fetch_status` 行，blocked 处理见 `docs/SOURCE-FETCH-OPERATIONS.md`。
- **推送被拒或中断**：查日志里的数据库备份路径和 `backup/<SHA>` 分支，确认是否有第二个写库方；不要强推或 rebase 数据。未提交数据会让下一轮因工作区不干净而停止，须先备份再处理。
- **代码回滚**：暂停例程、等当前一轮结束，用普通 revert 撤销问题合并；不要让例程指向不存在的脚本。
- **数据回滚**：暂停例程，备份当前 `tg.db`，把最后一个有效版本恢复成新的工作区内容，只提交 `tg.db` 普通推送（或 revert 只改 `tg.db` 的坏提交）。不重写远端历史，不回退 `public-feeds`。
- `tools/box_cron.example` 只供有 cron 的主机参考，这个盒子不用。
