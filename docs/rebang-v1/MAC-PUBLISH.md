# Mac mini 快进发布

本手册不是上线授权。当前只交付功能分支和本地验证；不要合并 `main`、操作 DO 或启动生产任务。首次生产推送和启用定时分别按阿欢批准的提交号、设备和影响范围办理。

## 入口与防护

- `tools/mac_publish.sh --code-sha FULL_SHA` 只用于专用 clone。由同一个标准账号从手动和系统 `launchd` 运行。`PATH` 和 `BOX_PYTHON` 使用绝对路径；需要 Python 3.11+、`beautifulsoup4`、`pillow`、`lxml`、`flock`、`realpath` 和支持原子推送的 Git。`PATH` 将该 Python 环境的 `bin` 放在系统目录之前，以便接收脚本调用同一环境的 `python3`。
- 代码固定在 detached HEAD（必须等于 `--code-sha`），不自动拉入生产代码，换代码只能手动（见下文）；每轮只 `fetch` 两个数据来源 ref，不 reset/clean。首轮以远端 `main:tg.db` 为起点，最多只替换仍与固定提交一致的 `tg.db`；后续保留本地采集数据和运行缓存。专用工作区不要运行任何其他会写 DB、采集缓存或发布的入口。首期不读取来源 Cookie、会话文件或翻译密钥。
- 持锁依次跑旧流水线、`rebang_refresh.sh --no-publish`、`write_build_info.py`。有 SQLite journal/WAL/SHM 就拒绝。在临时 Git index 上从 `main` 父提交构造纯 `tg.db` 数据提交；若库没变则不写 `main`。`build-info.json` 的 `source_commit` 是固定运行代码，不是数据提交；`database_sha256` 对比实际入库的 blob。
- `publish_pages.sh --dry-run --already-built` 只打包。新入口以观察到的 `gh-pages` 为唯一父提交，保持打包 tree 不变。把父包和待推包分别 `git archive` 到干净树，给原版 `deploy/news-sync.sh --dry-run` 检查。公网 `data/meta.json` 须与父包 `rebang/data/meta.json` 字节一致，才把父包作为本地基线。它只是公开版本标记，不证明 DO 已安装的每个文件都相同；`file://` 演练不访问公网。
- 校验后再 `ls-remote` 核对远端两个 ref，然后只调用一次 `git push --atomic --porcelain`：`main` 和 `gh-pages` **都写进推送**（库没变时 `main` 是原值不动），每个都带 `--force-with-lease=<ref>:<建包时的 SHA>`，候选都是父提交的直接子提交（推送前再核对是快进）。这样 `ls-remote` 之后任何一边被人改动（包括 `gh-pages` 被回退到祖先），整次推送都被拒，不会被当成正常推送清掉 HALT。不降级、不重试。普通快进不是独占写入权，切换前必须排除其他写入口；`main` 不变时它在 Git 推送自身读取远端与 `gh-pages` 落地之间仍有毫秒级窗口，那时有人合并 `main` 只会让下一轮看到一次正常合并。
- `.git/mac-publish/HALT` 在发起推送前创建，成功记录两条远端 ref 后才清除。推送被拒、结果不明、或发现未经预期的 ref 变化，都停止后续手动和定时轮次。保留 `tg.db`、`refs.json`、`HALT` 和日志，核对两个真实远端 SHA、候选 SHA、数据库和公网，再另行批准恢复。不要自动删标记、覆盖库、重置分支或强推旧包。接收校验失败未推送，保留本地库；常规下一轮可在同一远端基线上重试。
- `refs.json` 用同目录临时文件 + `fsync` + rename 原子替换。它读不出、不是两条 ref 的完整 SHA 记录时，写 HALT 停发，原文件、库都不动，等人工核对。

## main 正常合并后继续发布（11/25 起）

每轮开始 `fetch` 远端两条 ref，和 `refs.json`（上次成功推送后的两条 ref）比：

- **一样**：照常。
- **只有 `main` 往前走了，且是正常合并**——新 `main` 是记录里 `main` 的后代、`gh-pages` 与记录完全一致、`tg.db` 在 Git 树里的模式/类型/blob 与记录里的 `main` 一致——日志打印 `main advanced normally <旧>..<新>; publishing on it with pinned code <SHA>`，**不写 HALT**。仍用固定的老代码采集建站，数据提交接在新 `main` 上，推送成功后 `refs.json` 更新为新值。`build-info.json` 的 `source_commit` 仍是固定代码。只改文档、改代码的合并都一样，新代码要等手动换版本才生效。
- **其他情况都 HALT（与原来一样）**：历史改写/非后代、别人改了 `tg.db`（含只改文件模式、删掉它）、`gh-pages` 有任何变化（含回退到祖先）。
- **首次启动/升级**：远端 `main` 必须包含当前 `--code-sha`，否则报 `remote main must contain --code-sha`，不写 `refs.json`、不动库、不写 HALT。

本轮进行中有人合并 `main`：

- `ls-remote` 时发现 `main` 已被正常合并（`gh-pages` 未动）→ 不推送，退出码 75，stderr `Mac publish skipped: main advanced normally during this round…`，不写 HALT、不写 `refs.json`。本地新采的库保留，下一轮在新 `main` 上一起提交。
- `ls-remote` 之后、推送时被合并 → 推送被 lease 拒绝。只有 `--porcelain` 回执能逐个确认两条 ref 都是 `!` 且为 `[rejected] (stale info)` / `[rejected] (atomic push failed)`（至少一个 stale info）、以 `Done` 结尾，并且重新 `fetch` 后确认只是 `main` 正常合并，才删掉本轮刚建的 HALT、按上面的「跳过」处理。
- 断线、超时（15 分钟）、回执缺行或不明、远端钩子拒绝、复查失败或复查发现别的变化 → 退出码 1，HALT 保留；已有的 HALT 从不自动清。

## 手动换代码版本

换版本时 plist 的 `--code-sha` 必须同步改成新 SHA（入口要求 HEAD 等于它），新 SHA 必须已在远端 `main` 里。整个检出期间持有发布锁，`:05` 那一轮撞上锁只会报 `already running` 退出、不写任何东西。以专用账号在发布 clone 里：

```sh
cd /opt/shiguang-news/checkout            # 按实际路径
NEW_SHA=<要换到的完整 SHA>                  # 必须是远端 main 上的提交
flock -n .git/mac-publish/lock sh -euc '
  test ! -e .git/mac-publish/HALT || { echo "先处理 HALT"; exit 1; }
  backup="$HOME/mac-publish-backup-$(date +%Y%m%d%H%M%S)"; mkdir "$backup"
  cp -p tg.db "$backup/"; cp -Rp .git/mac-publish "$backup/"
  git fetch --no-tags origin main
  git merge-base --is-ancestor "$0" FETCH_HEAD
  mv tg.db "$backup/tg.db.live"            # 本地库不能被提交里的副本替换
  git checkout --quiet --detach "$0"
  mv "$backup/tg.db.live" tg.db
  test "$(git rev-parse HEAD)" = "$0"
  git status --short                        # 只应有 " M tg.db"
' "$NEW_SHA"
```

`flock -n` 拿不到锁说明正在发布，等它结束再来（别在 `:05` 前后操作）。检出后改 plist：由获批操作者把 `/Library/LaunchDaemons/local.shiguang.news-publish.plist` 里的 `--code-sha` 改成 `$NEW_SHA`，`plutil -lint`，`launchctl bootout system/local.shiguang.news-publish` 后再 `launchctl bootstrap system /Library/LaunchDaemons/local.shiguang.news-publish.plist`，`launchctl print system/local.shiguang.news-publish` 核对参数。改 plist 前若撞上一轮，HEAD 与旧 `--code-sha` 不符，入口直接拒绝、不写东西。`refs.json` 保留不动。等下一个 `:05` 自然运行，看到 `published main=…`，`gh-pages` 上 `build-info.json` 的 `source_commit` 等于新 SHA 才算换好。

**上线本改动（第一次换到含本逻辑的版本）**：11/25 Mini 实际 plist 的 `--code-sha` 是 `e0070253c5d8da63e8497945d763d7dc50601ac6`。旧代码在本 PR 合并后的下一个 `:05` 会因为 `main` 被别人推动而写 HALT（内容以 `remote refs changed since the last local checkpoint` 开头，这种 HALT 表示没有发起推送）。最好在合并后、下一个 `:05` 前按上面步骤换到合并后的 `main` SHA；来不及时：核对 HALT 正是这句开头、远端 `gh-pages` 等于 `refs.json` 里的值、`main` 是记录值的后代且 `tg.db` 没被改，再把 HALT 移进备份目录，然后换版本，新代码下一轮会自己再按上面的规则复查。HALT 若是 `Push started…` 开头，说明推送结果不明，先人工核对两个远端 ref 和候选 SHA，不能直接清。

## 回退

- 回到旧版本（例如 `e0070253…`）用同一段持锁步骤检出旧 SHA，plist 的 `--code-sha` 同步改回。旧入口同样要求 HEAD 精确等于 `--code-sha`。
- 旧入口要求远端两条 ref 与 `refs.json` **完全一致**：新代码跟进过别人的合并后，`refs.json` 记录的是最新值，只要回退后再有人推 `main`，旧代码就会在下一轮写 HALT（这就是原来的行为）。回退前核对 `refs.json` 与 `git ls-remote origin refs/heads/main refs/heads/gh-pages` 一致；不一致就先不回退。
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
