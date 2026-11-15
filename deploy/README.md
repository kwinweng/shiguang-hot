# 公开快讯站点同步

唯一生产输入为公开 `gh-pages`：

```text
https://codeload.github.com/kwinweng/shiguang-hot/tar.gz/refs/heads/gh-pages
```

`news-sync.sh` 默认无凭据下载此压缩包，每 20 分钟校验后替换静态根。无需 Git、GitHub token、SSH 构建主机或私有 feeds。本目录不修改 nginx 配置。

## 现状（2026-11-16）

- 服务器上安装的 `/usr/local/libexec/news-sync.sh` 与本目录 `news-sync.sh` 一致（11/15 核对 md5）。
- 静态根里同时有旧站树（gh-pages 根目录）和 v11（`rebang/`）。nginx 用 `try_files /rebang$uri …` 只对外提供 v11，挂在 https://news.kwinweng.com/ 根路径；旧站文件不再对外，但**校验仍按旧站格式**，所以旧站树必须继续发布。nginx 配置与回退见 [`docs/rebang-v1/OPERATIONS.md`](../docs/rebang-v1/OPERATIONS.md)。
- 登录阅读器 `shiguang-reader.service` 已停用（`disable --now`），`/mail/`、`/archive/`、`/__login/`、`/api/` 返回 404。`shiguang-reader-update.timer` 已于 11/16 00:32 `disable --now`；灵记只读的阅读器库从此不再更新。回退命令见 [`docs/rebang-v1/OPERATIONS.md`](../docs/rebang-v1/OPERATIONS.md)。
- 2026-11-07 首次从私有站迁到公开 gh-pages 的过程与验收记录在 [`docs/HANDOFF-history.md`](../docs/HANDOFF-history.md)。

## 接收、校验与发布

- 压缩包下载和解包各用一个新建空目录；不从旧站填充候选。拒绝路径穿越、符号/硬链接、特殊文件及凭据/数据库文件名。只读取静态数据，不运行下载树中的脚本、不导入其 Python 模块、不执行构建。数据处理使用 `python3 -I`。
- 首页必须带 `data-bookmark-scope="public"`；归档 manifest 与每天 JSON 必须为 schema 3 / public，日期一致。manifest 中每个 SHA-256 必须匹配对应 `archive/data/YYYY-MM-DD.json`，文件集合必须与 manifest 一致；每天的 public HTML fallback 必须逐项匹配 JSON 的 HTML（解析时统一相对 URL），不只检查 HTML 文件存在。
- 整树禁止 `mail` 路径（含空目录）、JSON 中 mail 来源标记、private scope/visibility，以及 HTML 中 mail 来源标记和本地 mail 链接。嵌入 JSON 的记录 HTML 和 HTML 中的 JSON script 同样检查。不根据正文是否出现“邮件”一词判断泄露。
- `data/live.json` 必须非 sample 且 `messages` 非空。`updated` 必须有时区，过去不超过 2 小时、未来不超过 10 分钟。最新**非空归档内容日**不得早于当前静态站（兼容 private 当前站），不得晚于北京时间今天，且至少为北京时间当前时刻减 2 小时所在日；仅刷新构建时间不能通过。
- 防止明显截断：以当前文件数扣除 mail 路径为基数，候选文件数须至少为 `max(100, ceil(基数 × 50%))`；private→public 与日常更新使用同一门槛。**不要求旧日期、UID、private-only 页面或哈希资源逐个保留。** 校验日志给出实际数量及最低数量。小型合成测试用无敏感内容的填充资源满足 100 文件门槛，不增加生产绕过开关。
- 所有校验通过后，将目录设为 0755、文件设为 0644，并统一为现静态根的 uid/gid，供 nginx 读取。Linux `renameat2(RENAME_EXCHANGE)` 原子交换同文件系统上的两棵目录；不支持该调用时拒绝发布。保留一版同级 `<target>.news-sync-previous`，下一次成功发布会替换它。首次上一版可能包含私有内容，必须留在 Web root 之外，不能给它配置公开路由。
- `flock` 防止发布重叠；timer 每 20 分钟加最多 90 秒抖动。每轮下载完整压缩包、计算当前/候选文件哈希及解析 HTML/JSON，会产生相应网络与磁盘 I/O。需预留压缩包、候选、上一版和独立迁移备份的空间；不新增采集或模型调用。

## 再次迁移或重装前

生产操作由协调者执行，本地测试不能替代：先确认阿欢批准目标和影响范围；先做独立备份（静态树 tar、阅读器库用 SQLite `.backup` 并 `PRAGMA quick_check`，不要直接复制正在写的库）；再用 `--dry-run` 审阅删除清单和最新内容日。脚本只保留一版 previous，不能代替永久备份。

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

依赖 Bash、Python 3.8+、curl、flock、realpath 和支持 `renameat2` 的 Linux 文件系统；无需 rsync、OpenSSH 或 GitHub 凭据。确认静态根父目录可由 service 写入，nginx 能穿过其父目录读取新树。从获批版本复制本目录三个文件到临时传输目录后，执行以下步骤；必须使用 `set -e`，预检失败即停止。（11/07 已安装，重装时才需要。）

```bash
set -euo pipefail
# 默认从公开 gh-pages 下载；只写临时目录，审阅删除清单和最新内容日。
install -d -m 0700 /tmp/news-sync-check
bash /tmp/news-sync-install/news-sync.sh \
  --target /var/www/news.kwinweng.com --dry-run --work-dir /tmp/news-sync-check
rmdir /tmp/news-sync-check

# 仅在独立备份通过后安装及启动。
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

验收应同时核对静态 public scope、非空 live、最新内容日、mail 路径不可访问，以及线上 v11 的 `data/meta.json` 时间。nginx 用 `try_files` 改写路径，不能把根路径的响应当成静态根 `index.html` 的内容。

停止后续同步：`systemctl disable --now news-sync.timer`，再停止/等待正在运行的 service。协调者回退时须暂停 reader 导入，并在 Linux 上用 `renameat2(RENAME_EXCHANGE)` 原子交换静态根与同级 previous，不能用两次 `mv` 制造静态根缺失窗口；恢复 private 备份前须重新确认其暴露范围。reader 已导入的数据不会随静态树回退，须按已验证的 reader 恢复流程单独处理。
