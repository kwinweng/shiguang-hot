# X 转储私有收件箱

盒子上的 Grok 定时把 X 原始响应导出成「清单 + 包」，推到一个独立的私有 GitHub 仓库。Mac mini 发布器（`tools/mac_publish.py`）每轮采集前只读拉取一次，校验通过的新批次原子放进发布 checkout 的 `var/rebang/x-dump/<dump_id>/`，之后由现有 X 适配器照常读取（适配器不改）。Mini 仍是唯一发布端。

本文不是上线授权。启用要改 Mini 的 plist、配私库只读凭证，属于红灯，须阿欢批准（见文末）。收件代码在 `tools/x_inbox.py`，测试在 `tests/test_x_inbox.py` 和 `tests/test_mac_publish.py`（只用本地合成仓库）。取代草稿 PR #91 的持久 Git 缓存做法。

## 发件格式（盒子 → 私库）

私库只用 `main` 分支。仓库里只允许这些文件，多一个、少一个都整轮跳过（`x_inbox_layout`）：

- `dumps/<dump_id>.json`：这一批的清单；
- `dumps/<dump_id>.tar.gz`：这一批的包，和清单**在同一个提交里**一起出现；
- 可选根目录 `README.md`。

全部是普通文件（Git 模式 `100644`）：不能是软链接、子模块或可执行文件，不能有子目录、其他文件名。树里最多 64 个文件。**私库只留最近 6 批**（老的由盒子在同一个提交里删掉），因为 Mini 每轮会浅克隆整棵最新树，单个文件的下载上限是 48 MiB。

清单格式和单包规则沿用 11/26 用真实包离线验过的格式（6 个 JSON、75 条主帖），只是清单不再放根目录 `manifest.json`，而是每批一份，跟包同名：

```json
{
  "dump_id": "20261127T0106",
  "generated_at": "2026-11-27T01:08:22+08:00",
  "files": ["posts.json", "quotes.json", "_dump.json"],
  "post_count": 66,
  "sha256": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
}
```

- `dump_id` 是导出开始时的北京时间 `YYYYMMDDTHHMM`，必须等于文件名，不能晚于 `generated_at`、也不能早于它 36 小时以上。不同导出不要复用同一个 `dump_id`。
- `generated_at` 带时区的 ISO 8601；收件时只认过去 36 小时到未来 5 分钟内的批次。包里 `_dump.json` 的 `generated_at` 必须是同一时刻。
- 包是 gzip 压缩的 **USTAR**，JSON 文件直接放在包顶层（不包目录、不带 `./`）。成员名以 ASCII 字母、数字或 `_` 开头，其余只用字母、数字、`_`、`-`、`.`，以 `.json` 结尾，最长 100 字符，大小写折叠后不重名；只收普通文件，不收链接、目录、设备或 PAX/GNU 扩展头。
- `files` 是包里完整的文件列表（含 `_dump.json`），一个不多一个不少；`post_count` 是现有 `read_export` 读出的不重复主帖数，必须大于 0；`sha256` 是**整个 `.tar.gz`** 的小写十六进制 SHA-256。
- 上限：清单 64 KiB，**包 5 MiB**，解压后的 tar 32 MiB，单成员 8 MiB，最多 128 个成员。仓库里不要放其他文件或任何凭据。

## Mini 收件（每轮发布前）

只有发布器进程环境里有非空的 `REBANG_X_INBOX_REPO` 时才执行；没设置或为空，本轮和以前完全一样：不导入收件代码、不建目录、不打印任何 `x_inbox` 日志。

设置后，在 `pipeline.py` 之前：

1. 删掉 `var/rebang/` 下所有 `.x-inbox-work-*` 目录（包括上一轮被硬杀留下的），再新建本轮的 work 目录。
2. 检查 `var/rebang` 所在磁盘可用空间，不足 1 GiB 就跳过拉取（仍做第 6 步清理）。
3. 在 work 目录里浅克隆私库：`git clone --bare --depth=1 --single-branch --branch=main --no-tags`，不签出任何文件。每个 Git 进程有 48 MiB 的单文件硬上限（`RLIMIT_FSIZE`）、独立进程组，整个收件步骤共 120 秒，超时整组 `SIGKILL`。Git 的 stderr 一律丢弃，日志里不会出现仓库地址或凭证提示。只允许 `https`、`ssh`、`file` 协议；不对私库做任何写操作。
4. 只看树的元数据核对上面的目录规则，再挑比 `x-dump` 里现有最新批次**更新**的批次，最多取最新的 2 个，按从旧到新处理。已存在的同名目录不覆盖；比现有最新批次旧的（重放、已被清理的）直接忽略。
5. 每批先查大小，再读清单和包，在 work 目录里解包并完成全部校验（哈希、结构、成员白名单、时效、主帖数）。全部通过才写入 `.x-inbox-owned` 标记并**一次改名**进 `x-dump/<dump_id>`（同一文件系统，原子）。改名就是这一批成功的分界：读取端只会看到完整批次。某一批不过只跳过这一批，另一批照常。
6. 清理：`x-dump` 里只保留最近 24 个**收件器自己装的**批次（名字合规、真实目录、标记内容等于目录名）。更老的先改名移进 work 目录（读取端立刻看不到），手动放的、名字不合规的、软链接一律不动。
7. 打印一行结果，然后在 `finally` 里删掉所有 work 目录（第 6 步移出的旧批次随之删除）。删除失败**另起一行**记录，不改结果行；残留目录下一轮第 1 步再删。

收件不写 `HALT`、不改退出码、不影响发布器的干净检查（`var/rebang/` 已被 `.gitignore` 忽略），本轮其他来源照常建站发布。X 拿不到新批次时，适配器按原规则读已有批次，超过 36 小时就显示过期。

### 日志

- `x_inbox=ok installed=20261127T0106,20261127T0306`：装了这些批次；`installed=none` 表示私库里没有更新的批次。
- `x_inbox=error code=<错误码> installed=…`：本轮有问题，`installed` 仍如实列出已经装好的批次。
- 可能附带 ` pruned=<数量>`（清理了几个旧批次）、` prune_error=<异常类型>`（清理改名失败，下一轮重试）。
- `x_inbox_cleanup=failed error=<异常类型> count=<个数>`：work 目录没删干净，下一轮会再删；结果行不受影响。

### 错误码

- `x_inbox_disk_low`：可用空间不足 1 GiB，本轮没拉取。
- `x_inbox_fetch_failed`：克隆或读取失败。包括网络、认证、仓库或 `main` 不存在，以及下载的单个文件超过 48 MiB 被系统截断。
- `x_inbox_timeout`：整个收件步骤超过 120 秒，Git 进程组已被杀掉。改名是原子的，超时前已装好的批次是完整的。
- `x_inbox_layout`：私库里有多余文件、子目录、软链接或可执行文件，名字不合规，清单和包没有成对出现，或文件超过 64 个。整轮不装任何批次。
- `x_inbox_too_large`：清单超过 64 KiB、包超过 5 MiB、解压后超过 32 MiB、单成员超过 8 MiB 或成员超过 128 个。只跳过这一批。
- `x_inbox_sha256_mismatch`：包的哈希和清单不符（常见于半写、截断）。只跳过这一批。
- `x_inbox_stale`：`generated_at` 超过 36 小时或在未来 5 分钟以后。只跳过这一批。
- `x_inbox_invalid_batch`：清单或包内容不合规：JSON 坏了、`dump_id` 和文件名不符、不是 gzip/USTAR、成员路径穿越、带目录、链接、非 JSON、文件列表或主帖数不符、没有主帖。只跳过这一批。
- `x_inbox_target_invalid`：`var/rebang/x-dump` 是软链接或不是目录。不拉取、不清理，需人工查看。
- `x_inbox_internal`：收件代码本身出了意外（含导入失败）。已装好的批次仍列在 `installed` 里。

多个批次都出错时只记第一个错误码。

### 硬中断以后

没有长期 Git 缓存：每轮都是新的临时浅克隆，用完就删。发布器被 `SIGKILL` 或超时后，残留的只是 `var/rebang/.x-inbox-work-*`，下一轮开头整个删除重来，不需要修复任何锁或缓存。改名前被杀，批次不可见；改名后被杀，批次完整可见。如果整个发布器进程被杀而 Git 子进程还在跑，它只能往残留的 work 目录写（受 48 MiB 单文件上限约束），HTTPS 低速 30 秒、SSH 保活约 30 秒后会自己断开。

## 启用（红灯，须阿欢批准）

前提：Mini 已换到包含本功能的代码版本（按 `MAC-PUBLISH.md`「手动换代码版本」），盒子已能按上面的格式推送并核对过回执。

1. 私库给 Mini 一个**只读**身份：建议只读 deploy key，配成 Mini 发布账号 `~/.ssh/config` 里的专用主机别名（例如 `Host github-x-inbox`，指定该 key、`IdentitiesOnly yes`）。不要把令牌写进地址、仓库或日志；AI 不读、不保存这把 key。
2. 在发布账号下先手动试一次只读克隆（不写任何东西）：`git clone --bare --depth=1 --branch=main git@github-x-inbox:<owner>/<repo>.git /tmp/x-inbox-check && rm -rf /tmp/x-inbox-check`。
3. 按 `MAC-PUBLISH.md` 的持锁步骤（第 0–3 步拿锁、记原状、停任务、备份）进去，在 plist 的 `EnvironmentVariables` 里加 `REBANG_X_INBOX_REPO`，值是不含凭证的地址（例如 `git@github-x-inbox:<owner>/<repo>.git`），`plutil -lint`，装回、核对后再退出持锁 shell。
4. 验收：等下一个 `:05`，日志出现 `x_inbox=ok installed=…`；公网博主页 X 筛选出现 36 小时内的帖子；连续两轮发布都不超时、不停发。只看到 `x_inbox=ok installed=none` 不算恢复。

回退：在同样的持锁步骤里从 plist 删掉 `REBANG_X_INBOX_REPO`。之后不再拉取；`x-dump` 里已有的批次留着，过 36 小时后 X 显示过期，不影响其他来源。
