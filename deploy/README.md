# 公开快讯站点同步

唯一生产输入为公开 `gh-pages`：

```text
https://codeload.github.com/kwinweng/shiguang-hot/tar.gz/refs/heads/gh-pages
```

`news-sync.sh` 默认无凭据下载此压缩包，每 20 分钟校验后替换静态根。无需 Git、GitHub token、SSH 构建主机或私有 feeds。负责人已批准用 public 替换现有 private 静态站，删除 mail 与 private-only 历史；旧版“必须保留全部 private 历史”的方案不再适用。本目录不修改 reader 数据库、nginx 或认证配置。

## 接收、校验与发布

- 压缩包下载和解包各用一个新建空目录；不从旧站填充候选。拒绝路径穿越、符号/硬链接、特殊文件及凭据/数据库文件名。只读取静态数据，不运行下载树中的脚本、不导入其 Python 模块、不执行构建。数据处理使用 `python3 -I`。
- 首页必须带 `data-bookmark-scope="public"`；归档 manifest 与每天 JSON 必须为 schema 3 / public，日期一致。manifest 中每个 SHA-256 必须匹配对应 `archive/data/YYYY-MM-DD.json`，文件集合必须与 manifest 一致；每天的 public HTML fallback 必须逐项匹配 JSON 的 HTML（解析时统一相对 URL），不只检查 HTML 文件存在。
- 整树禁止 `mail` 路径（含空目录）、JSON 中 mail 来源标记、private scope/visibility，以及 HTML 中 mail 来源标记和本地 mail 链接。嵌入 JSON 的记录 HTML 和 HTML 中的 JSON script 同样检查。不根据正文是否出现“邮件”一词判断泄露。
- `data/live.json` 必须非 sample 且 `messages` 非空。`updated` 必须有时区，过去不超过 2 小时、未来不超过 10 分钟。最新**非空归档内容日**不得早于当前静态站（兼容 private 当前站），不得晚于北京时间今天，且至少为北京时间当前时刻减 2 小时所在日；仅刷新构建时间不能通过。
- 防止明显截断：以当前文件数扣除 mail 路径为基数，候选文件数须至少为 `max(100, ceil(基数 × 50%))`；private→public 与日常更新使用同一门槛。**不要求旧日期、UID、private-only 页面或哈希资源逐个保留。** 校验日志给出实际数量及最低数量。小型合成测试用无敏感内容的填充资源满足 100 文件门槛，不增加生产绕过开关。
- 所有校验通过后，将目录设为 0755、文件设为 0644，并统一为现静态根的 uid/gid，供 nginx 读取。Linux `renameat2(RENAME_EXCHANGE)` 原子交换同文件系统上的两棵目录；不支持该调用时拒绝发布。保留一版同级 `<target>.news-sync-previous`，下一次成功发布会替换它。首次上一版可能包含私有内容，必须留在 Web root 之外，不能给它配置公开路由。
- `flock` 防止发布重叠；timer 每 20 分钟加最多 90 秒抖动。每轮下载完整压缩包、计算当前/候选文件哈希及解析 HTML/JSON，会产生相应网络与磁盘 I/O。需预留压缩包、候选、上一版和独立迁移备份的空间；不新增采集或模型调用。

## 首次迁移先决条件

生产操作由协调者执行，本地测试不能替代以下检查：

1. 确认负责人已批准本次目标和影响范围，完成 Linux 隔离测试及真实候选 dry-run。盘点旧静态根、reader 导入状态和回退步骤；不要读取或打印凭据或私人正文。
2. **先做独立备份**：静态树备份至 `/var/backups/news-kwinweng-pre-public-20261107.tar.gz`；使用 SQLite `.backup` 将 `/var/lib/shiguang-reader/topics.sqlite3` 一致性备份到同目录，限制访问并运行 `PRAGMA quick_check`。不要直接复制正在写入的数据库。脚本仅保留一版 previous，不能替代永久迁移备份。
3. **先用临时 reader 数据库导入 public 候选**：从生产库用 SQLite `.backup` 创建临时副本，以 `shiguang-reader` 用户执行下列现有命令。确认无错误、`new_versions > 0`、11 月 4 日至当日均有导入，且 `source_versions` 最新日为当日。若 reader 拒绝 public 格式，停止安装并报告。该步骤不改生产 reader 库。

   ```bash
   runuser -u shiguang-reader -- /opt/shiguang-reader/venv/bin/python \
     /opt/shiguang-reader/current/tools/topic_news.py import-published \
     --database /tmp/reader-check/topics.sqlite3 --published-root /tmp/staged-public-site
   ```

4. 静态树原子发布后，等待现有 `shiguang-reader-update.timer` 导入，检查 `new_versions` 日志与生产库 `source_versions` 的最新日期。保持 reader、登录和 nginx 配置不变；已有 reader 历史不在本次删除范围内，停止从 private 产物新增数据即可。完成后清理临时目录。

## 本地隔离验证

仅使用临时合成数据，无网络、无 SSH、无真实数据库或凭据：

```bash
bash -n deploy/news-sync.sh
python3 -I tests/test_news_server_sync.py
```

macOS 可运行全部校验/dry-run 测试；Linux `flock`/`renameat2` 原子发布用例在 macOS skip。测试的默认下载入口使用本地假 curl 和合成压缩包；这不是 GitHub 连通性验收。Linux 完整测试应覆盖 private→public 删除 mail/private-only 页面、保留一版 previous、权限和 inode 原子交换。

本地已有合成静态目录时也可直接检查；`--source` 只接受本地目录，不接受 SSH 地址：

```bash
bash deploy/news-sync.sh --source /tmp/synthetic-public-site \
  --target /tmp/synthetic-current-site --dry-run --work-dir /tmp
```

目标须为已存在的绝对目录。`--work-dir` 仅用于 dry-run，必须位于目标外；dry-run 不写目标，也不创建 previous。

## 接收服务器安装与验收

依赖 Bash、Python 3.8+、curl、flock、realpath 和支持 `renameat2` 的 Linux 文件系统；无需 rsync、OpenSSH 或 GitHub 凭据。确认静态根父目录可由 service 写入，nginx 能穿过其父目录读取新树。从获批版本复制本目录三个文件到临时传输目录后，执行以下步骤；必须使用 `set -e`，预检失败即停止。

```bash
set -euo pipefail
# 默认从公开 gh-pages 下载；只写临时目录，审阅删除清单和最新内容日。
install -d -m 0700 /tmp/news-sync-check
bash /tmp/news-sync-install/news-sync.sh \
  --target /var/www/news.kwinweng.com --dry-run --work-dir /tmp/news-sync-check
rmdir /tmp/news-sync-check

# 仅在独立备份和临时 reader 导入验收通过后安装及启动。
install -D -m 0755 /tmp/news-sync-install/news-sync.sh /usr/local/libexec/news-sync.sh
install -m 0644 /tmp/news-sync-install/news-sync.service /etc/systemd/system/news-sync.service
install -m 0644 /tmp/news-sync-install/news-sync.timer /etc/systemd/system/news-sync.timer
systemd-analyze verify /etc/systemd/system/news-sync.service /etc/systemd/system/news-sync.timer
systemctl daemon-reload
systemctl start news-sync.service
systemctl enable --now news-sync.timer
systemctl list-timers news-sync.timer
journalctl -u news-sync.service -n 30 --no-pager
```

验收应同时核对静态 public scope、非空 live、最新内容日、历史页、mail 路径不可访问，以及 reader 的实际导入结果。先确认 nginx 是否代理/缓存相关路径，不能把代理首页的响应当成静态根内容验证。

停止后续同步：`systemctl disable --now news-sync.timer`，再停止/等待正在运行的 service。协调者回退时须暂停 reader 导入，并在 Linux 上用 `renameat2(RENAME_EXCHANGE)` 原子交换静态根与同级 previous，不能用两次 `mv` 制造静态根缺失窗口；恢复 private 备份前须重新确认其暴露范围。reader 已导入的数据不会随静态树回退，须按已验证的 reader 恢复流程单独处理。
