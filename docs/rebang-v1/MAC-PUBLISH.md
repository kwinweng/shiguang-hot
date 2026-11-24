# Mac mini 快进发布

本手册不是上线授权。当前只交付功能分支和本地验证；不要合并 `main`、操作 DO 或启动生产任务。首次生产推送和启用定时分别按阿欢批准的提交号、设备和影响范围办理。

## 入口与防护

- `tools/mac_publish.sh` 只用于专用 clone。由同一个标准账号从手动和系统 `launchd` 运行。现有 plist 可保留 `--code-sha FULL_SHA`，新版本接受该参数以兼容现有调度，启动后以远端检查点决定运行版本。`PATH` 和 `BOX_PYTHON` 使用绝对路径；需要 Python 3.11+、`beautifulsoup4`、`pillow`、`lxml`、`flock`、`realpath` 和支持原子推送的 Git。`PATH` 将该 Python 环境的 `bin` 放在系统目录之前，以便接收脚本调用同一环境的 `python3`。
- 每轮只抓取远端 `main` 和 `gh-pages`。`gh-pages` 需与上次 `.git/mac-publish/refs.json` 一致，`main` 可相同或正常快进。推进检查点前比较旧 `main` 和候选 `main` 的 `tg.db` blob。远端库变化且与本地库字节不同时，保留本地 `tg.db`，另存 `.git/mac-publish/remote-tg-<候选 SHA>.db`，记录两个远端 blob、本地 blob 和候选提交，写 HALT 停发。
- detached HEAD 需要前进时，从候选提交提取两个发布脚本到状态目录下的临时目录，运行 `sh -n`、`python -I -m py_compile` 和隔离导入检查。旧发布进程持锁等待，候选 shell 继承同一个锁文件描述符并 `exec` 候选 Python。候选 Python 确认锁并写下启动标记，核对本地 HEAD 和远端两条 ref 后才会推进检查点、切换 checkout。预检或启动失败的日志包含候选 SHA，保留旧入口，下一轮可再拉取后续修复。新版本在 checkout 后再次核对远端才采集。
- 专用工作区只有未暂存的 `tg.db` 可与 HEAD 不同。初次运行若无检查点，以远端 `main:tg.db` 起步，只允许替换仍与启动时 HEAD 相同的库。后续切换保留本地数据库和忽略的缓存文件，遇到缓存与新跟踪文件冲突就退出。若切换中断后留下 `.git/mac-publish/checkout-tg.db`，下一轮取回原始库。有 SQLite journal/WAL/SHM 就拒绝操作。专用工作区只运行本入口，采集不读取来源 Cookie、会话文件或翻译密钥。
- 持锁依次跑旧流水线、`rebang_refresh.sh --no-publish`、`write_build_info.py`。在临时 Git index 上从本轮抓取的 `main` 构造只更新 `tg.db` 的数据提交；库没变时无需写 `main`。`build-info.json` 的 `source_commit` 记录本轮启动和建站所用的提交，`database_sha256` 对比实际入库的 blob。
- `publish_pages.sh --dry-run --already-built` 只打包。新入口以观察到的 `gh-pages` 为唯一父提交，保持打包 tree 不变。把父包和待推包分别 `git archive` 到干净树，给原版 `deploy/news-sync.sh --dry-run` 检查。公网 `data/meta.json` 须与父包 `rebang/data/meta.json` 字节一致，才把父包作为本地基线。它只是公开版本标记，不证明 DO 已安装的每个文件都相同；`file://` 演练不访问公网。
- 校验后再核对远端两个 ref，只调用一次 `git push --atomic`。两条 ref 都带精确旧 SHA 的 `--force-with-lease`，refspec 无 `+`，候选提交只允许快进。两个 ref 都有更新时，远端在同一事务校验旧 SHA，任一失配会拒绝整批。库未变时也发送 `main` 的 refspec 和 lease，Git 可在通告时发现旧 SHA 失配，但通告为已是目标 SHA 时会把 `main` 省出事务。
- 每次推送后都用 `git ls-remote` 核对两条真实 ref。库未变时，若 `main` 在 Git 通告后移动，Pages 可能已写入，此时只能发现失配、保留旧检查点和 HALT，人工核对远端及公网。推后检测覆盖核对时仍可见的差异。两次检查间移动又回到原 SHA 或核对后发生的写入无法由本轮推后检查发现。切换前必须排除其他写入口。
- `main` 非快进、`gh-pages` 与检查点不一致、必要的远端 ref 消失、远端库分叉，或切换和采集建站期间发现远端 ref 又移动，都会写 `.git/mac-publish/HALT`。发起推送前也会创建 HALT。推送成功且两条真实 ref 与候选完全一致后才更新检查点并清除 HALT。推送被拒、失配、结果不明或推送中断时，保留标记，后续手动和定时轮次都停止。人工恢复前保留数据库、`refs.json`、`HALT` 和日志，核对两个真实远端 SHA、候选 SHA、数据库和公网。
- 采集、建站或接收校验失败时，日志记录用到的 `source_commit`，不推送，旧站继续服务。本地数据库和已接受的检查点保留。远端 ref 未发生异常时，下一轮可以用同一版本或更新的正常快进版本重试。

## 从固定 SHA 切换到自动跟进（合并后在 Mini 手动做一次）

1. 等最近一次 `:05` 任务退出。以专用账号进入现有部署 clone，确认没有其他写入口。用与发布器相同的锁文件打开维护 shell。锁拿不到就退出，等在途发布结束。以下核对、备份、checkout、恢复库、更新检查点全在这个 shell 内完成。

   ```sh
   umask 077
   mkdir -p .git/mac-publish && flock -n .git/mac-publish/lock /bin/sh
   ```

2. 在持锁 shell 内执行 `git ls-remote --refs origin refs/heads/main refs/heads/gh-pages` 和 `git fetch --no-tags origin main gh-pages`。确认 `main` 包含获批改动，是此前 `main` 检查点的快进。核对 `gh-pages` 检查点、已有推送回执和公网 meta。若远端库自检查点变化，先核对并保留两份库，确认应恢复的本地库。若有 HALT，先按其中原因对账，核对两个 ref 和数据库。将确认过的完整 SHA 赋给 `MAIN_SHA`、`PAGES_SHA`，将实际 Python 绝对路径赋给 `BOX_PYTHON`。
3. 在持锁 shell 内运行以下命令。报错时保留备份、日志和现有 HALT，查明原因后再继续。

   ```sh
   (
     set -eu
     umask 077
     state=.git/mac-publish
     [ -f tg.db ] && [ ! -L tg.db ]
     for path in tg.db-journal tg.db-wal tg.db-shm "$state/checkout-tg.db"; do
       [ ! -e "$path" ] && [ ! -L "$path" ] || exit 1
     done
     [ -z "$(git branch --show-current)" ]
     git diff --quiet HEAD -- . ':(exclude)tg.db'
     git diff --cached --quiet
     [ -z "$(git ls-files --others --exclude-standard)" ]
     backup=$(mktemp -d "$state/manual-XXXXXX")
     echo "Backup: $backup"
     cp -p tg.db "$backup/tg.db"
     cmp tg.db "$backup/tg.db"
     for path in refs.json HALT; do
       if [ -e "$state/$path" ]; then cp -p "$state/$path" "$backup/$path"; fi
     done
     # Retain the corresponding launchd logs separately.
     git show "$MAIN_SHA:tools/mac_publish.sh" > "$backup/mac_publish.sh"
     git show "$MAIN_SHA:tools/mac_publish.py" > "$backup/mac_publish.py"
     /bin/sh -n "$backup/mac_publish.sh"
     "$BOX_PYTHON" -I -m py_compile "$backup/mac_publish.py"
     "$BOX_PYTHON" -I -c 'import runpy, sys; runpy.run_path(sys.argv[1])' "$backup/mac_publish.py"
     git show HEAD:tg.db > "$backup/tracked-tg.db"
     restore_db() {
       if [ -f "$state/checkout-tg.db" ]; then mv "$state/checkout-tg.db" tg.db; fi
     }
     trap restore_db EXIT
     trap 'exit 1' HUP INT TERM
     mv tg.db "$state/checkout-tg.db"
     cp "$backup/tracked-tg.db" tg.db
     git checkout --detach --no-overwrite-ignore "$MAIN_SHA"
     restore_db
     cmp tg.db "$backup/tg.db"
     [ "$(git rev-parse HEAD)" = "$MAIN_SHA" ]
     git diff --cached --quiet
     actual=$(git ls-remote --refs origin refs/heads/main refs/heads/gh-pages)
     actual=$(printf '%s\n' "$actual" | LC_ALL=C sort -k2)
     expected=$(printf '%s\trefs/heads/gh-pages\n%s\trefs/heads/main\n' "$PAGES_SHA" "$MAIN_SHA")
     [ "$actual" = "$expected" ]
     printf '{"refs/heads/main":"%s","refs/heads/gh-pages":"%s"}\n' \
       "$MAIN_SHA" "$PAGES_SHA" > "$state/refs.next"
     mv "$state/refs.next" "$state/refs.json"
     if [ -e "$state/HALT" ]; then mv "$state/HALT" "$backup/HALT.reconciled"; fi
   )
   ```

4. `exit` 退出维护 shell，释放锁。既有 plist 可继续用。在获批的账号和 plist 环境下手动跑一轮 `tools/mac_publish.sh`，核对日志里的 `source_commit`、`validation=passed`、推送回执和两个远端 SHA。等现有线上接收流程完成，再核对公网 `data/meta.json` 与本轮 Pages 包字节一致、线上 `build-info.json` 的 `source_commit` 包含本次改动、新条目可以打开。下一次 `:05` 自然触发后核对定时日志和公网版本。

## 启动故障或断电后的人工恢复

- 若预检或交接失败，日志会带候选 SHA，旧入口仍可在下轮尝试后续提交。若已安装的入口仍无法启动，用上节的 `flock` 命令直接进入同锁维护 shell，无需调用发布 Python。保留现有库、远端库副本、检查点、HALT 和日志，确认 `tg.db` 无 SQLite sidecar。按上节核对远端，选择包含修复且获批的 `main`，用同一组命令切换到该提交并放回原始库。远端 SHA 或库仍有分歧时，保留 HALT 并先完成对账。
- 断电后先拿同一把锁。备份 `tg.db`、可能存在的 `checkout-tg.db`、`refs.json`、`refs.next`、HALT 和日志，再核对 HEAD、暂存区、SQLite sidecar、库的完整性、两条真实远端 ref 和公网版本。`checkout-tg.db` 留存时，将它视作切换前的库，核对并保留工作区那份后再恢复。遇到 checkout 残留或推送结果不明，先核清再恢复或清理标记。进程 `SIGKILL` 恢复已在 `file://` 演练中测试，实际断电恢复未经实测。

## 首次部署到新 Mini 的切换指令（获批后才执行）

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
