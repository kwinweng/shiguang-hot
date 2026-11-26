# Mac mini 快进发布

本手册不是上线授权。当前只交付功能分支和本地验证；不要合并 `main`、操作 DO 或启动生产任务。首次生产推送和启用定时分别按阿欢批准的提交号、设备和影响范围办理。

## 入口与防护

- `tools/mac_publish.sh --code-sha FULL_SHA` 只用于专用 clone。由同一个标准账号从手动和系统 `launchd` 运行。`PATH` 和 `BOX_PYTHON` 使用绝对路径；需要 Python 3.11+、`beautifulsoup4`、`pillow`、`lxml`、`flock`、`realpath` 和支持原子推送的 Git。`PATH` 将该 Python 环境的 `bin` 放在系统目录之前，以便接收脚本调用同一环境的 `python3`。
- 代码固定在 detached HEAD（必须等于 `--code-sha`），不自动拉入生产代码，换代码只能手动（见下文）；每轮只 `fetch` 两个数据来源 ref，不 reset/clean。首轮以远端 `main:tg.db` 为起点，最多只替换仍与固定提交一致的 `tg.db`；后续保留本地采集数据和运行缓存。专用工作区不要运行任何其他会写 DB、采集缓存或发布的入口。不读取翻译密钥。来源登录只认固定位置 `<账号家目录>/.config/rebang/weibo-cookie.txt`、`weread-session.json`，家目录取系统账号库（`pwd`），不看继承的 `HOME`。规则在 `rebang/private_file.py`：从 `/` 起逐级不跟软链接地打开；每级上级目录须是 root 或本账号所有、组和其他人不可写、没有允许类 ACL（macOS 家目录自带的 `everyone deny delete` 可以）；`rebang` 目录须本账号所有、0700、无 ACL；文件须是本账号的普通文件、0600 以内且本人可读、只有一个硬链接、无 ACL。合格才把**路径**交给采集脚本（发布器只打开检查、不读内容）；否则把对应环境变量置空（明确禁用，不依赖备用路径），该平台显示「未配置」。这只是预检：采集器读取时在同一个文件描述符上按同样规则再查，检查后被换掉只会读失败、降级为未配置。不继承 `REBANG_WEIBO_COOKIE`/`REBANG_WEREAD_SESSION` 环境变量。真正进入采集前打印 `source_credentials=weibo,weread`（或 `none`），只表示本地预检通过，不代表登录有效，也不含内容；`HALT` 等提前停下的轮次不打印。落盘用 `python -m rebang.bloggers.weibo save-cookie` 和 `weread login --session …`，见 `COLLECTION-RECOVERY.md`。
- 持锁依次跑旧流水线、`rebang_refresh.sh --no-publish`、`write_build_info.py`。有 SQLite journal/WAL/SHM 就拒绝。在临时 Git index 上从 `main` 父提交构造纯 `tg.db` 数据提交，提交信息固定为 `Refresh public collection data`；**库没变也照样建一个空的数据提交**（树与父提交相同），所以每轮 `main` 都会前进一个提交。下一轮靠 `refs.json` 记录的 SHA 认出这是自己推的，空提交同样适用。`build-info.json` 的 `source_commit` 是固定运行代码，不是数据提交；`database_sha256` 对比实际入库的 blob。
- `publish_pages.sh --dry-run --already-built` 只打包。新入口以观察到的 `gh-pages` 为唯一父提交，保持打包 tree 不变。把父包和待推包分别 `git archive` 到干净树，给原版 `deploy/news-sync.sh --dry-run` 检查。公网 `data/meta.json` 须与父包 `rebang/data/meta.json` 字节一致，才把父包作为本地基线。它只是公开版本标记，不证明 DO 已安装的每个文件都相同；`file://` 演练不访问公网。
- 校验后再 `ls-remote` 核对远端两个 ref，然后只调用一次 `LC_ALL=C git push --atomic --porcelain`：`main` 和 `gh-pages` 都是**真正的更新**（各自是父提交的新子提交，推送前核对是快进且不等于原值），都进同一个原子事务，每个都带 `--force-with-lease=<ref>:<建包时的 SHA>`。客户端发现任何一边已变就整次拒绝；服务端在同一个事务里核对两边的旧值，推送途中有人改动任何一边（包括 `gh-pages` 回退到祖先、别人改了 `main` 的 `tg.db`），也整次拒绝，不会发布旧库页面、不会清 HALT。不降级、不重试。普通快进不是独占写入权，切换前必须排除其他写入口。
- `.git/mac-publish/HALT` 在发起推送前创建，成功记录两条远端 ref 后才清除。推送被拒、结果不明、或发现未经预期的 ref 变化，都停止后续手动和定时轮次。保留 `tg.db`、`refs.json`、`HALT` 和日志，核对两个真实远端 SHA、候选 SHA、数据库和公网，再另行批准恢复。不要自动删标记、覆盖库、重置分支或强推旧包。接收校验失败未推送，保留本地库；常规下一轮可在同一远端基线上重试。
- `refs.json` 用同目录临时文件 + `fsync` + rename 原子替换。它读不出、不是两条 ref 的完整 SHA 记录、或记录的 SHA 在本地不是可用的 commit（对象不存在、是 tree/blob）时，写 HALT 停发，原文件、库都不动，等人工核对。
- 一开始 `fetch` 失败时从严判断，拿不准就写 HALT（`refs.json` 在 `fetch` 之前就先校验）：
  - `fetch` 的 stderr（`LC_ALL=C`）里有 `couldn't find remote ref` → 立刻写 HALT，不再看后续复查（复查时分支恢复了也一样，远端断开了也一样）。
  - 否则跑 `ls-remote --refs`。它**成功**时一律写 HALT：缺 `main` 或 `gh-pages`、`gh-pages` 不等于 `refs.json` 里的值、输出有看不懂的行，各有对应原因；都没有也写 HALT（`fetch` 失败而远端能连上，原因不明）。
  - 只有 `ls-remote` 本身也失败（断网、认证）、且前面没看到任何明确异常 → 报 `remote unreachable` 退出 1，不写 HALT，下一轮自然重试。
- 推送回执逐行核对：只认 Git 的 `To …` 抬头、恰好两条状态行、`Done`，多出任何行（含残缺状态行、空行）都按回执不明处理，HALT 保留。

## main 正常合并后继续发布（11/25 起）

每轮开始 `fetch` 远端两条 ref，和 `refs.json`（上次成功推送后的两条 ref）比：

- **一样**：照常。
- **只有 `main` 往前走了，且是正常合并**——新 `main` 是记录里 `main` 的后代、`gh-pages` 与记录完全一致、`tg.db` 在 Git 树里的模式/类型/blob 与记录里的 `main` 一致——日志打印 `main advanced normally <旧>..<新>; publishing on it with pinned code <SHA>`，**不写 HALT**。仍用固定的老代码采集建站，数据提交接在新 `main` 上，推送成功后 `refs.json` 更新为新值。`build-info.json` 的 `source_commit` 仍是固定代码。只改文档、改代码的合并都一样，新代码要等手动换版本才生效。
- **其他情况都 HALT（与原来一样）**：历史改写/非后代、别人改了 `tg.db`（含只改文件模式、删掉它）、`gh-pages` 有任何变化（含回退到祖先）。
- **首次启动/升级**：远端 `main` 必须包含当前 `--code-sha`，否则报 `remote main must contain --code-sha`，不写 `refs.json`、不动库、不写 HALT。

本轮进行中有人合并 `main`：

「跳过」的条件很窄：`gh-pages` 在**每一次**观测里（`ls-remote`、推送回执、重新 `fetch`）都等于建包时的值，而且 `main` 的变化能核实为正常合并。复查只能确认、不能洗掉前面已经看到的异常。

- `ls-remote` 时发现 `main` 已被正常合并、`gh-pages` 等于基线 → 再 `fetch` 一次，`gh-pages` 仍是基线、`main` 从建包值经 `ls-remote` 看到的值到现在都是正常合并 → 不推送，退出码 75，stderr `Mac publish skipped: main advanced normally during this round; nothing published, no HALT, checkpoint unchanged…`。不写 HALT，**不推进 `refs.json`**（首轮跳过时 `refs.json` 停在初始化写入的建包基线）。本地新采的库保留，下一轮在新 `main` 上一起提交。`ls-remote` 看到 `gh-pages` 有任何不同或缺失 → HALT，哪怕复查时已恢复。
- `ls-remote` 之后、推送前被合并 → 客户端 lease 拒绝。只有 `--porcelain` 回执逐行恰好是：`main` 为 `!` + `[rejected] (stale info)`、`gh-pages` 为 `!` + `[rejected] (atomic push failed)`（只是被原子推送连带）、两行的源 SHA 都等于本轮候选、以 `Done` 结尾，并且重新 `fetch` 后 `gh-pages` 仍是基线、`main` 是正常合并，才删掉本轮刚建的 HALT、按上面的「跳过」处理。回执里 `gh-pages` 是 `stale info` 一律 HALT。
- 推送途中（服务端已读出 ref 之后）被人改动 → 服务端回 `[remote rejected] (atomic transaction failed)`，两边都不动。这种情况分不清是正常合并还是别的写入，**一律保守停发（HALT）**，本地库有变化时也一样，人工核对后再恢复。
- 断线、超时（15 分钟）、回执缺行/截断/只有一条 ref、远端钩子拒绝、复查失败或复查发现别的变化 → 退出码 1，HALT 保留；已有的 HALT 从不自动清。

## 手动换代码版本

换版本要同时换「检出的代码」和 plist 的 `--code-sha`（入口要求 HEAD 等于它），新 SHA 必须已在远端 `main` 里。由获批操作者在**一个**终端里完成全部步骤。

**为什么必须全程在同一个持锁子 shell 里做**：发布器每轮开头对 `.git/mac-publish/lock` 拿独占锁，拿不到就报 `already running` 退出 1、什么都不写。第 0 步用 `flock` 拿住这把锁再开一个子 shell，锁一直归这个 shell，直到最后 `exit` 才释放。所以：拿到锁本身就证明没有在途发布；停任务、备份、处理 HALT、换检出、改 plist、装回的整个过程中，`:05` 定时轮次、手动运行都进不来，看不到「新代码 + 旧 plist」之类的半成品。**锁外不做任何一步**（包括 `bootout`、备份、清 HALT、检出、改 plist、`bootstrap`）：一旦先 `exit` 再补做，中间任何时刻都可能有一轮插进来，写 HALT 或用半换好的状态发布。装回后、`exit` 前如果正好到 `:05`，那一轮会撞锁退出 1，不写任何东西，下一小时再正常跑。

规矩：逐条手动执行、每条看结果，不用 `sh -e` 一口气跑（中途失败时恢复步骤会被跳过）。每步写了失败后做什么；失败了任务保持停用，按「失败恢复」处理，不要临时发挥。终端意外断开会释放锁：任务此时应是停用的，重新做第 0 步拿锁，`launchctl print "$LABEL"` 确认仍停用（还在就先 `launchctl bootout "$LABEL"`），按 `$backup/start.txt` 重设变量，再按「失败恢复」处理，不要从中间继续往前走。

0. **拿锁进子 shell**（避开 `:00–:10`）：
   ```sh
   cd /opt/shiguang-news/checkout                       # 按实际路径
   sudo flock -n -E 75 .git/mac-publish/lock zsh -f; echo "locked-shell-exit=$?"
   ```
   立刻打印 `locked-shell-exit=75` = 没拿到锁（正在发布或别人在操作）：停止，过后再来，什么都没动。拿到锁会进入 root 的子 shell，下面所有命令都在这个 shell 里输：
   ```sh
   ACCOUNT=shiguang-news                                # plist 的 UserName
   a() { sudo -u "$ACCOUNT" -H "$@"; }                 # Git 命令一律用专用账号跑，免得留下 root 的文件
   cd /opt/shiguang-news/checkout
   LABEL=system/local.shiguang.news-publish
   PLIST=/Library/LaunchDaemons/local.shiguang.news-publish.plist
   OLD_SHA=$(a git rev-parse HEAD)
   NEW_SHA=<要换到的完整 SHA>                           # 必须是远端 main 上的提交
   ```
1. **记下原状**（还没改任何东西）：
   ```sh
   plutil -p "$PLIST" | grep -A4 ProgramArguments       # 第 3 项（--code-sha）应等于 $OLD_SHA
   backup="/Users/$ACCOUNT/mac-publish-backup-$(date +%Y%m%d%H%M%S)"; mkdir -m 700 "$backup"
   PLIST_SHA0=$(shasum -a 256 < "$PLIST"); DB_SHA0=$(shasum -a 256 < tg.db)
   printf 'backup=%s\nOLD_SHA=%s\nNEW_SHA=%s\nPLIST_SHA0=%s\nDB_SHA0=%s\n' \
     "$backup" "$OLD_SHA" "$NEW_SHA" "$PLIST_SHA0" "$DB_SHA0" > "$backup/start.txt"
   ls -l .git/mac-publish/ >> "$backup/start.txt"; cat "$backup/start.txt"
   ```
   `--code-sha` 不等于 `$OLD_SHA`，或任一条失败：任务没停、什么都没改，直接 `exit` 释放锁，先查清楚。
2. **停任务并确认已停**：`launchctl bootout "$LABEL"`，然后 `launchctl print "$LABEL"; echo "print=$?"` 应报找不到服务、`print=` 非 0。仍能看到服务：再 `bootout` 一次；还在就 `exit`（plist、库、检出都没动，任务原样装着），报告。
3. **备份**：
   ```sh
   cp -p tg.db "$backup/tg.db"
   shasum -a 256 tg.db > "$backup/tg.db.sha256"         # 记的是相对名 tg.db：在哪个目录 -c 就核对哪份
   cp -Rp .git/mac-publish "$backup/mac-publish"        # refs.json、HALT（若有）
   if [ -e .git/mac-publish/HALT ]; then cp -p .git/mac-publish/HALT "$backup/HALT.orig"; fi
   cp -p "$PLIST" "$backup/news-publish.plist"
   (cd "$backup" && shasum -a 256 -c tg.db.sha256)       # 必须 OK
   [ "$(shasum -a 256 < "$backup/news-publish.plist")" = "$PLIST_SHA0" ] && echo plist-backup-ok
   [ ! -e .git/mac-publish/HALT ] || cmp .git/mac-publish/HALT "$backup/HALT.orig" && echo halt-backup-ok
   touch "$backup/COMPLETE"                             # 只有上面全部通过才执行这一条
   ```
   任一条失败：不要 `touch COMPLETE`，按「失败恢复」**情况 A**（备份不全、plist 没改）。
4. **核对 HALT**：`ls -l .git/mac-publish/HALT`。不存在就继续。存在时读内容，只有「上线本改动」里那一种可以在这里清（`mv .git/mac-publish/HALT "$backup/HALT.cleared"`，原件已在 `HALT.orig`）；其他 HALT 一律不清，按「失败恢复」**情况 B**（会原样放回）中止。
5. **换检出**：
   ```sh
   a git fetch --no-tags origin main
   a git merge-base --is-ancestor "$NEW_SHA" FETCH_HEAD && echo on-main   # 必须打印 on-main
   a git status --short --untracked-files=no                             # 只应是 " M tg.db" 或为空
   a git checkout --quiet --force --detach "$NEW_SHA"                    # --force 只会覆盖 tg.db（已备份）
   cp -p "$backup/tg.db" tg.db                                           # 放回本地库
   shasum -a 256 -c "$backup/tg.db.sha256"                                # 必须 OK
   ```
   - `fetch`/`merge-base` 失败或没打印 `on-main`、`status` 里有 tg.db 以外的行：还没动检出，按「失败恢复」情况 B 中止（不要带着别的改动用 `--force`）。
   - `checkout` 失败，或放回库后核对不 OK：按「失败恢复」情况 B。
6. **核对**：`a git rev-parse HEAD` 等于 `$NEW_SHA`；`shasum -a 256 -c "$backup/tg.db.sha256"` OK；`a git status --short` 只有 ` M tg.db`（或为空）；`ls tg.db-journal tg.db-wal tg.db-shm` 全都不存在；`cmp "$backup/mac-publish/refs.json" .git/mac-publish/refs.json` 无输出。任何一项不符 → 情况 B。
7. **改 plist、装回、核对，然后才释放锁**：
   ```sh
   /usr/libexec/PlistBuddy -c "Set :ProgramArguments:3 $NEW_SHA" "$PLIST"
   plutil -lint "$PLIST"
   plutil -p "$PLIST" | grep -A4 ProgramArguments      # 第 3 项应是 $NEW_SHA
   launchctl bootstrap system "$PLIST"
   launchctl print "$LABEL" | grep -A6 arguments       # 核对 --code-sha 是 $NEW_SHA
   exit                                                # 到这里才释放锁
   ```
   `PlistBuddy`/`plutil -lint` 失败或参数不对：不 `bootstrap`，按情况 B（会从备份放回 plist）。`bootstrap` 失败，或 `print` 里参数不对：先 `launchctl bootout "$LABEL"` 并确认已停，再按情况 B。

`refs.json` 全程不动。等下一个 `:05` 自然运行，看到 `published main=…`，`gh-pages` 上 `build-info.json` 的 `source_commit` 等于新 SHA 才算换好。

**失败恢复**（仍在同一个持锁 shell 里；任务保持停用；逐条执行、逐条看结果）：

先看 `ls "$backup/COMPLETE"` 选情况。

**情况 A：备份没完成（没有 `COMPLETE`），plist 还没改。** 不用任何依赖备份的步骤，只核对原样，原样装回：
```sh
[ "$(shasum -a 256 < "$PLIST")" = "$PLIST_SHA0" ] && echo plist-untouched
[ "$(shasum -a 256 < tg.db)" = "$DB_SHA0" ] && echo db-untouched
[ "$(a git rev-parse HEAD)" = "$OLD_SHA" ] && echo head-untouched
ls -l .git/mac-publish/                                 # 与 start.txt 里的清单比：HALT 有无一致
```
四项都对：`launchctl bootstrap system "$PLIST"`，`launchctl print "$LABEL" | grep -A6 arguments` 核对是 `$OLD_SHA`，`exit`。任一项不对：不装回，`exit`，报告哪项不对（这时不要拿不完整的备份去覆盖）。

**情况 B：备份已完成（有 `COMPLETE`）。** 按顺序做，前一条失败也继续做后面能做的「放回」，但最后不装回：

1. **库先放回（与 Git 无关，第一步就做）**：`cp -p "$backup/tg.db" tg.db`，`shasum -a 256 -c "$backup/tg.db.sha256"` 必须 OK。不 OK：再做一次；还不 OK 就记下，继续 2–4，最后不装回。
2. **代码回旧版**：`a git rev-parse HEAD` 已等于 `$OLD_SHA` 就跳过。否则 `a git status --short --untracked-files=no` 只能有 tg.db 一行，再 `a git checkout --quiet --force --detach "$OLD_SHA"`，然后**再放一次库**：`cp -p "$backup/tg.db" tg.db`，`shasum -a 256 -c "$backup/tg.db.sha256"`（检出会用提交里的副本覆盖它）。
   - `status` 有 tg.db 以外的行，或 `checkout` 失败：不要再试别的 Git 命令。单独执行 `cp -p "$backup/tg.db" tg.db` 和 `shasum -a 256 -c "$backup/tg.db.sha256"`，确保库已在原位；`a git status --short > "$backup/git-status.failed"`、`a git rev-parse HEAD >> "$backup/git-status.failed"` 留现场；继续 3–4，最后不装回。
3. **HALT 放回原样**：有 `$backup/HALT.orig` 就 `cp -p "$backup/HALT.orig" .git/mac-publish/HALT` 并 `cmp` 无输出；没有 `HALT.orig` 而现在有 HALT（不该出现）就别动它，记下。再 `cmp "$backup/mac-publish/refs.json" .git/mac-publish/refs.json`：不同就别覆盖，保留两份，最后不装回。
4. **plist 放回**：`cp -p "$backup/news-publish.plist" "$PLIST"`，`[ "$(shasum -a 256 < "$PLIST")" = "$PLIST_SHA0" ] && echo plist-restored`，`plutil -lint "$PLIST"`。
5. **装回**：只有 1–4 全部通过、`a git rev-parse HEAD` 等于 `$OLD_SHA` 时，才 `launchctl bootstrap system "$PLIST"`，`launchctl print "$LABEL" | grep -A6 arguments` 核对是 `$OLD_SHA`，然后 `exit`。否则不装回，直接 `exit`，报告卡在哪一步；任务保持停用（有 HALT 时装回也只会每轮报 `HALT exists`，这是原状）。

**上线本改动（第一次换到含本逻辑的版本）**：11/25 Mini 实际 plist 的 `--code-sha` 是 `e0070253c5d8da63e8497945d763d7dc50601ac6`。旧代码在本 PR 合并后的下一个 `:05` 会因为 `main` 被别人推动而写 HALT（内容以 `remote refs changed since the last local checkpoint` 开头，这种 HALT 表示没有发起推送）。最好在合并前就做第 0–3 步（拿锁、记原状、停任务、备份），**保持这个持锁 shell 不退出**，合并后在同一个 shell 里设好 `NEW_SHA` 为合并后的 `main` SHA（`printf 'NEW_SHA=%s\n' "$NEW_SHA" >> "$backup/start.txt"`）继续第 4 步。没来得及、已经有 HALT 时：第 4 步核对 HALT 正是这句开头、远端 `gh-pages` 等于 `refs.json` 里的值、`main` 是记录值的后代且 `tg.db` 没被改，再 `mv .git/mac-publish/HALT "$backup/HALT.cleared"` 继续；中止时情况 B 第 3 步会从 `HALT.orig` 放回。新代码下一轮会自己再按上面的规则复查。HALT 若是 `Push started…` 开头，说明推送结果不明，先人工核对两个远端 ref 和候选 SHA，不能清。

## 回退

- 回到旧版本（例如 `e0070253…`）走上面同一套步骤，`NEW_SHA` 设成旧 SHA：同样从第 0 步拿锁开始，全程在持锁 shell 里停任务、备份、核对 HALT、换检出、改 plist、装回，最后才 `exit`；失败同样按「失败恢复」。旧入口同样要求 HEAD 精确等于 `--code-sha`。
- 旧入口要求远端两条 ref 与 `refs.json` **完全一致**：新代码跟进过别人的合并后，`refs.json` 记录的是最新值，只要回退后再有人推 `main`，旧代码就会在下一轮写 HALT（这就是原来的行为）。回退前（在持锁 shell 里、第 5 步之前）核对 `refs.json` 与 `a git ls-remote origin refs/heads/main refs/heads/gh-pages` 一致；不一致就按情况 B 中止，先不回退。
- 回退不改 `refs.json`、不动 `tg.db`、不强推任何 ref。

## 贴给 Mini 本机 T3 的切换指令（获批后才执行）

1. 在 Mini 本机使用专用标准账号，核对阿欢批准的提交 SHA。新建专用 clone（不使用 Air 工作树、试跑目录或已有开发目录），从 `origin/fix/zixun-collection-recovery` 取该提交，`git checkout --detach "$APPROVED_SHA"` 后确认 `git rev-parse HEAD` 完全一致。准备稳定的日志目录和 Python 环境；用最小权限、可吊销的仓库专用身份及非交互认证，不读凭据文件、不改分支保护。确认盒子与其他采集发布入口无在途写入、不会自动重启。先保留最后可信数据库及所需公开归档/媒体的独立备份；只用可核实的公开缓存，不用 177 文件试跑包替代生产数据。父包检查仍要求 `max(100, ceil(公开基线文件数 × 0.5))`，如果规模或内容不合格就停，不降低门槛或伪造新鲜度。
2. 复制 `tools/mac_publish.launchd.plist.example` 到未安装的本地文件，将账号、路径、HOME 和完整 SHA 改为实际绝对值，`plutil -lint`，确认没有 `RunAtLoad` 或 `KeepAlive`。在相同账号和最小环境中用 `file://` 裸仓库跑 `tests/test_mac_publish.py`；核对 Python/`flock`/`realpath` 路径、GitHub 和公开来源网络。记录现网公网 meta 指纹。没有单轮生产写入批准，不运行指向真实 `origin` 的入口。
3. 批准首发后，在同一账号和 plist 环境**手动运行一次**，不要先装任务。示例路径与模板对应（按实填值，不传密钥）：

   ```sh
   env -i HOME=/Users/shiguang-news \
     PATH=/opt/shiguang-news/venv/bin:/opt/homebrew/bin:/usr/bin:/bin \
     BOX_PYTHON=/opt/shiguang-news/venv/bin/python3 \
     /bin/sh /opt/shiguang-news/checkout/tools/mac_publish.sh --code-sha "$APPROVED_SHA"
   ```

   核对 `validation=passed`、推送回执、两条远端 ref、代码 SHA、数据库哈希与用时。等待现有接收流程自然触发；以回执中的 `gh-pages` SHA 比对 `git show "$PAGES_SHA:rebang/data/meta.json"` 与公网 HTTPS `https://news.kwinweng.com/data/meta.json`（重新请求、比较原始字节 SHA-256，不只看 HTTP 200）。确认新条目能打开、仍 noindex，记录推包到公网更新时间；如果可获得现有接收回执，核对其 `published=true` 和对应包，不自行登录或操作 DO。公网不匹配、无新内容或指标明显异常就停，不重发或装任务。首次真实包要记录采集/建站总耗时、磁盘峰值和上传/收包延迟，确认小时调度有余量。
4. 首发公网验收通过并另获调度批准后，才由获批操作者将已检查的 plist 安装到 `/Library/LaunchDaemons/local.shiguang.news-publish.plist`（root:wheel、0644，日志目录允许专用账号写），执行 `launchctl bootstrap system /Library/LaunchDaemons/local.shiguang.news-publish.plist`。用 `launchctl print system/local.shiguang.news-publish` 核对身份和等待状态。保留 `StartCalendarInterval` 的 `Minute=5`；不 `kickstart`，不手动代跑。等系统本地时间下一个 `:05` 的自然触发，记录启动、结束和日志，再用同一套公网指纹核对该轮是新包。不能看到日志或公网新版本就报待验，不宣称迁移完成。FileVault、来电开机、桌面登录、DO、旧盒子均不在这段指令的变更范围内。
