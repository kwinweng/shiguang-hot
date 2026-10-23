# Box 采集切换（PR A / step 0）

公开仓库的 Actions 分钟免费。本次迁移是为把采集调度交给自有 Linux 主机；Pages 仍由 Actions 构建部署。
本文件取代 SCHEDULE-OPERATIONS.md 中旧的 schedule、dispatch 采集说明；内网同步保持原流程。

## 新数据流与边界

Box 每小时 :07/:37 运行 pipeline（Telegram、RSS/YouTube 及既有 trial 采集），公开模式构建通过后，仅提交 tg.db 并普通推送 main。
复用 tools/persist_action_data.sh：无变化不提交；提交失败或推送被拒绝即失败，不强推、不自动 rebase。
Actions 仅在 main 的 tg.db、public-feeds/** 推送或 workflow_dispatch 时运行，NO_FETCH=1 始终生效。
Actions 不提交数据库，contents 权限降为 read，因此没有推送循环。dispatch_id 继续兼容旧调用方，但手动触发只部署。
公开 feed 推送仍可独立触发部署。既有 :11 外部 dispatch 可取消其中重复部署调用；保留内网 sync.sh。

使用专用公开 checkout 和专用用户，禁止复用含私有数据的内网 tg.db。正常模式要求 main 分支、受跟踪文件干净。
每轮先 fetch origin main，再 merge --ff-only；存在分叉即停止，运维先保留本地数据库和提交再处理。
flock 覆盖同步、采集、提交和推送；同 checkout 的第二轮直接跳过。不同 checkout 不共享锁，必须只安装一条生产 cron。
既有数据库自然小时配额与失败退避保持不变，:37 可能记录 hour_used；两次调度不保证两次实际抓取。

## 安装与切换清单

1. 记录切换前 main 提交和最近一次 Pages 成功运行，备份旧 hourly.yml、crontab、公开 tg.db。
   运行中的数据库用 SQLite backup 备份，不直接复制正在写入的库。备份放仓库外。
2. 在 Linux 安装 git、curl、Python 3.12、venv、cron；使用支持 flock 的本地文件系统。
   预置专用 checkout `/opt/shiguang`，确认 tg.db 为已知有效公开库。创建 venv：

   ```sh
   python3 -m venv /opt/shiguang/.venv
   /opt/shiguang/.venv/bin/python -m pip install beautifulsoup4 pillow
   mkdir -p /var/log/shiguang
   ```

   checkout 和日志目录须归 cron 用户所有。BOX_PYTHON 指定绝对解释器；脚本不加载 .env。
   运维通过既有安全方式配置 SSH deploy key（可写）或具有 Contents 写权限的 PAT，不把凭证放命令或日志。
   不能使用 GITHUB_TOKEN 作为 Box 推送凭证：其推送通常不会触发后续 Actions。
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
   limit 同时限制前 N 个公开采集源和总 N 次 http.request 调用（包含分页、图片），禁用 trial。
   每次调用底层 curl 仍可跟随最多 5 次重定向；此上限计逻辑请求，不计 HTTP 重定向跳数。
   --limit 必须搭配 --test-dir，避免把部分采集发布到生产。--dry-run 可搭配其他选项，但只打印计划。
5. 合并本 PR 的工作流变更，使旧 Actions schedule 停止；等待原采集运行结束，避免两个写库方重叠。
   记录这一短暂采集空窗，随后运行 Box 正常模式一次（不带 test-dir、limit、dry-run）。
6. 检查退出码和时间戳日志：应有 start、fetch_status、built site 和 success。
   核验新提交只包含 tg.db。无变化时不产生提交；可用 workflow_dispatch 单独验证部署。
7. 在 GitHub Actions 核验本次 tg.db push 触发 hourly，Build 步骤 NO_FETCH=1，Pages 部署成功。
   核对线上 build-info.json 的数据库 SHA-256、public_feeds_tree 和 source_commit 与构建输入一致。
   浏览今日、热点、栏目；确认更新时间与公开内容。工作流绿色不替代页面验收。
8. 使用 `crontab -e` 安装 tools/box_cron.example 中一条任务，替换路径；不要覆盖其他 cron。
   :07/:37 在任意主机时区都相同；runner 设置 Asia/Shanghai。确认 cron 服务启用且 PATH 能找到 git、curl。
9. 连续观察 24 小时：cron.log、逐轮日志、最后成功时间、请求状态、数据库提交、Pages 最新部署。
   busy 表示上一轮仍运行；长期 busy、blocked、持续错误或 Pages 落后须调查。日志使用日期加 PID；配置 logrotate/保留期并监控磁盘。
   Box media 不会随 tg.db 提交，Actions 只能使用现有 cache；缓存缺图时页面会缺少本地配图，图片同步不在 step 0 范围。

## 故障与回滚

- **配置回滚**：先移除本次 cron 行，等待当前 Box 运行结束，再恢复旧 hourly.yml（schedule :07/:37、dispatch 采集和数据库持久化）。
  用普通提交发布恢复，不强推。旧工作流的 tg.db push 不触发采集，可恢复历史文件整体内容。
  如先前移除了外部 :11 dispatch，可按原需要恢复；内网同步始终保留。
- **代码回滚**：停止 cron 后，使用普通 revert 提交撤销 PR A 的代码，或将 Box 专用 checkout 切回记录的已知版本。
  保留日志、数据库备份和未推送提交。先恢复工作流再移除 runner；不要让 cron 指向不存在的脚本。
- **数据回滚**：停止所有采集写入者，备份当前 tg.db，确定最后一个有效数据库版本。
  将该版本 tg.db 恢复为新的工作区内容，仅提交 tg.db 并普通推送；也可对仅修改 tg.db 的坏提交执行 git revert。
  不重置远端历史，不回退 public-feeds。恢复 PR A 工作流时，该新数据提交会触发 Pages；旧工作流则手动 dispatch 重建。
  数据恢复也恢复配额/退避状态；核验库完整性和公开内容，再恢复唯一采集调度。
- **推送拒绝或中断**：保留当前 tg.db 和本地 data 提交，查看 main 分叉原因。不要自动丢弃、强推或 rebase 数据。
  未提交数据会使下一轮因工作区不干净而停止，必须由运维备份后解决；重新运行成功才恢复 cron。

本 PR 只准备代码、示例和本地测试；不安装 cron、不读取密钥、不真实采集、不向远端推送。
