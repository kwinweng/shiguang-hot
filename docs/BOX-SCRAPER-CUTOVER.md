# Box 采集切换（PR A / step 0）

公开仓库的 Actions 分钟免费。本次迁移把采集、构建与发布交给自有 Linux 主机；Pages 改从 gh-pages 根目录部署。
本文件取代 SCHEDULE-OPERATIONS.md 中旧的 schedule、dispatch 采集说明；内网同步保持原流程。

## 新数据流与边界

Box 每小时 :07/:37 运行 pipeline（Telegram、RSS/YouTube 及既有 trial 采集），公开模式构建通过后，仅提交 tg.db 并普通推送 main。
复用 tools/persist_action_data.sh：无变化不提交；提交失败或推送被拒绝即失败，不强推、不自动 rebase。
主机 push hook 要求 ALLOW_MAIN_PUSH=publish；仅 tools/persist_action_data.sh 为该次 main 推送设置此变量，不 export，也不在 bot routine 中设置。
数据持久化成功后，runner 在同一锁和日志中更新 build-info.json，调用 tools/publish_pages.sh --already-built。
发布失败会明确记录 Pages publish failed，但不改变采集/持久化成功的退出状态，也不撤销数据提交。
Actions 仅保留 workflow_dispatch 手动测试，contents: read；无构建、部署或 Pages 写权限。
公开 feed 推送由下一轮 bot routine 发布。取消既有 :11 外部 dispatch 的部署调用；保留内网 sync.sh。

使用专用公开 checkout 和专用用户，禁止复用含私有数据的内网 tg.db。正常模式要求 main 分支、受跟踪文件干净。
每轮先 fetch origin main，再 merge --ff-only；存在分叉即停止，运维先保留本地数据库和提交再处理。
flock 覆盖同步、采集、提交和推送；同 checkout 的第二轮直接跳过。不同 checkout 不共享锁，必须只启用一个生产 bot routine。
既有数据库自然小时配额与失败退避保持不变，:37 可能记录 hour_used；两次调度不保证两次实际抓取。

## 安装与切换清单

1. 记录切换前 main 提交和最近一次 Pages 成功运行，备份旧 hourly.yml、既有 bot routine 配置、公开 tg.db。
   运行中的数据库用 SQLite backup 备份，不直接复制正在写入的库。备份放仓库外。
2. 在 Linux 安装 git、curl、Python 3.12、venv；使用支持 flock 的本地文件系统。此 Box 没有 cron，使用定时 bot routine。
   预置专用 checkout `/opt/shiguang`，确认 tg.db 为已知有效公开库。创建 venv：

   ```sh
   python3 -m venv /opt/shiguang/.venv
   /opt/shiguang/.venv/bin/python -m pip install beautifulsoup4 pillow
   mkdir -p /var/log/shiguang
   ```

   checkout 和日志目录须归 bot routine 运行用户所有。BOX_PYTHON 指定绝对解释器；脚本不加载 .env。
   运维通过既有安全方式配置 SSH deploy key（可写）或具有 Contents 写权限的 PAT，不把凭证放命令或日志。
   Box 使用独立凭证推送 main 和 gh-pages；脚本不读取或打印凭证。
3. 先检查参数（无采集、无 Git 操作）：

   ```sh
   BOX_PYTHON=/opt/shiguang/.venv/bin/python /opt/shiguang/tools/box_scrape.sh --checkout /opt/shiguang --dry-run
   ```

4. 由运维执行一次隔离真实小检查；开发验收不执行真实抓取：

   ```sh
   BOX_PYTHON=/opt/shiguang/.venv/bin/python /opt/shiguang/tools/box_scrape.sh --checkout /opt/shiguang --test-dir /tmp/shiguang-check-001 --limit 2 --log-dir /var/log/shiguang
   ```

   test-dir 必须不存在且位于 checkout 外。它复制允许的公开代码、配置、public-feeds 和数据库快照；tg.db、media、site 全在该目录。
   不复制 .env、Git 元数据或私有 inbox，不执行任何 Git 命令。已有小时配额也会复制，可能零请求；不要清除生产配额。
   limit 按 source id 排序、按采集端点去重后选择前 N 个公开 Telegram/feed 源；每源只读首页，禁用 trial。
   不翻页、不补 gap、不下载图片（含历史图片重试）；首页消息/条目照常写入隔离 tg.db。
   因此总计最多 N 次逻辑 HTTP 尝试，每个 fetch_status.requests 计该源实际调用 http.request 的次数，失败尝试也计数。
   配额/退避跳过和批内缓存命中不计 requests；底层 curl 最多跟随 5 次重定向，重定向跳数不单独计数。
   limit 不再通过抛出 request_limit 截断采集；未带 limit 的隔离运行仍执行完整采集。
   检查日志中首源 requests=1、new>0，并在 test-dir/tg.db 的 msg（Telegram）或 entry（feed）核对新记录。
   首页全为已有或超过保留窗口的消息时 new=0 是正常结果，不能据此认定写入失败。
   --limit 必须搭配 --test-dir，避免把部分采集发布到生产。--dry-run 可搭配其他选项，但只打印计划。
5. 合并本 PR 的工作流变更，使旧 Actions schedule 停止；等待原采集运行结束，避免两个写库方重叠。
   记录这一短暂采集空窗，随后运行 Box 正常模式一次（不带 test-dir、limit、dry-run）。
6. 检查退出码和时间戳日志：应有 start、fetch_status、built site 和 success。
   核验 main 新提交只包含 tg.db。数据库无变化时不产生数据提交，但仍发布站点。
7. **Pages source switch**：首次 gh-pages 发布成功后，在 Settings → Pages → Build and deployment 选择 Deploy from a branch，分支 gh-pages，目录 / (root)。
   当前配置为 build_type=workflow、cname=null；本 PR 不自动修改远端设置。站点地址保持 https://kwinweng.github.io/shiguang-hot/。
   在 Pages 核验分支部署成功；不要在 gh-pages 首次发布前切换来源。
   核对线上 build-info.json 的数据库 SHA-256、public_feeds_tree 和 source_commit 与构建输入一致。
   浏览今日、热点、栏目；确认更新时间与公开内容。工作流绿色不替代页面验收。
8. 创建唯一的定时 bot routine，调度时区设为 Asia/Shanghai，每小时 :07 和 :37 各运行一次 tools/box_scrape.sh：

   ```sh
   BOX_PYTHON=/opt/shiguang/.venv/bin/python /opt/shiguang/tools/box_scrape.sh --checkout /opt/shiguang --log-dir /var/log/shiguang
   ```

   确认 routine 已启用，运行用户和 PATH 能找到 git、curl；runner 同样设置 Asia/Shanghai。
   tools/box_cron.example 保留，仅供有 cron 的主机参考；此 Box 不使用该文件。
9. 连续观察 24 小时：bot routine 执行记录、逐轮日志、最后成功时间、请求状态、数据库提交、Pages 最新部署。
   busy 表示上一轮仍运行；长期 busy、blocked、持续错误或 Pages 落后须调查。日志使用日期加 PID；配置 logrotate/保留期并监控磁盘。
   Box media 不随 tg.db 提交；站点内引用的公开配图随 site/ 发布，不依赖 Actions cache。

## 发布脚本

`BOX_PYTHON` 与 box_scrape.sh 一致，默认 python3。独立执行 `sh tools/publish_pages.sh` 会运行
`SITE_MODE=public MAIL_DIGEST=0 TZ=Asia/Shanghai python pipeline.py`，成功后运行 `python tools/write_build_info.py`。
`--already-built` 跳过两步构建，要求现有 site/index.html 和 site/build-info.json；runner 在数据持久化后刷新元数据再使用该选项。
`--dry-run` 仍构建并在临时 worktree 准备单个无父提交，打印文件数和 SHA，但不推送；可与 --already-built 组合。
脚本拒绝缺失入口、元数据或包含任意 .env* 的 site/；添加 .nojekyll，默认移除 CNAME，仅 PAGES_CNAME 非空时生成。
当前无自定义域名，不设置 PAGES_CNAME。发布用 `git push --force origin <commit>:refs/heads/gh-pages`，不设置 ALLOW_MAIN_PUSH。
临时 worktree 通过 trap 清理；主 checkout 的 index、main 均不改变。gh-pages 每轮仅保留一个提交。
发布失败可在排查后用 --already-built 重试；持久化失败则不会尝试发布。

## 故障与回滚

- **Pages 来源回滚**：暂停 bot routine，等待当前运行结束；Settings → Pages 将来源切回 GitHub Actions，再普通 revert 本次 PR，恢复先前 Actions 部署工作流。保留数据库和日志，不强推 main。

- **配置回滚**：先暂停/删除 bot routine，等待当前 Box 运行结束，再恢复旧 hourly.yml（schedule :07/:37、dispatch 采集和数据库持久化）。
  用普通提交发布恢复，不强推。旧工作流的 tg.db push 不触发采集，可恢复历史文件整体内容。
  如先前移除了外部 :11 dispatch，可按原需要恢复；内网同步始终保留。
- **代码回滚**：暂停/删除 bot routine 后，使用普通 revert 提交撤销 PR A 的代码，或将 Box 专用 checkout 切回记录的已知版本。
  保留日志、数据库备份和未推送提交。先恢复工作流再移除 runner；不要让 bot routine 指向不存在的脚本。
- **数据回滚**：暂停/删除 bot routine，停止所有采集写入者，备份当前 tg.db，确定最后一个有效数据库版本。
  将该版本 tg.db 恢复为新的工作区内容，仅提交 tg.db 并普通推送；也可对仅修改 tg.db 的坏提交执行 git revert。
  不重置远端历史，不回退 public-feeds。恢复 PR A 工作流时，该新数据提交会触发 Pages；旧工作流则手动 dispatch 重建。
  数据恢复也恢复配额/退避状态；核验库完整性和公开内容，再恢复唯一采集调度。
- **推送拒绝或中断**：保留当前 tg.db 和本地 data 提交，查看 main 分叉原因。不要自动丢弃、强推或 rebase 数据。
  未提交数据会使下一轮因工作区不干净而停止，必须由运维备份后解决；重新运行成功才恢复唯一 bot routine。

本 PR 只准备代码、示例和本地测试；不创建 bot routine、不读取密钥、不真实采集、不向远端推送。
