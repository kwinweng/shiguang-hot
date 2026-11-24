# Mac mini 快进发布

本手册不是上线授权。当前只交付功能分支和本地验证；不要合并 `main`、操作 DO 或启动生产任务。首次生产推送和启用定时分别按阿欢批准的提交号、设备和影响范围办理。

## 入口与防护

- `tools/mac_publish.sh` 只用于专用 clone。由同一个标准账号从手动和系统 `launchd` 运行。现有 plist 可保留 `--code-sha FULL_SHA`，新版本接受该参数以兼容现有调度，启动后以远端检查点决定运行版本。`PATH` 和 `BOX_PYTHON` 使用绝对路径；需要 Python 3.11+、`beautifulsoup4`、`pillow`、`lxml`、`flock`、`realpath` 和支持原子推送的 Git。`PATH` 将该 Python 环境的 `bin` 放在系统目录之前，以便接收脚本调用同一环境的 `python3`。
- 每轮只抓取远端 `main` 和 `gh-pages`。`gh-pages` 需与上次 `.git/mac-publish/refs.json` 一致，`main` 可相同或正常快进。核对后记录这一对 ref。若 detached HEAD 需要前进，先切到本轮取到的 `main`，再带着同一把锁重启发布入口。新版本确认远端两条 ref 仍一致才采集，发布器本身的更新也在本轮生效。
- 专用工作区只有未暂存的 `tg.db` 可与 HEAD 不同。初次运行若无检查点，以远端 `main:tg.db` 起步，只允许替换仍与启动时 HEAD 相同的库。后续切换保留本地数据库和忽略的缓存文件，遇到缓存与新跟踪文件冲突就退出。若切换中断后留下 `.git/mac-publish/checkout-tg.db`，下一轮取回原始库。有 SQLite journal/WAL/SHM 就拒绝操作。专用工作区只运行本入口，采集不读取来源 Cookie、会话文件或翻译密钥。
- 持锁依次跑旧流水线、`rebang_refresh.sh --no-publish`、`write_build_info.py`。在临时 Git index 上从本轮抓取的 `main` 构造只更新 `tg.db` 的数据提交；库没变时无需写 `main`。`build-info.json` 的 `source_commit` 记录本轮启动和建站所用的提交，`database_sha256` 对比实际入库的 blob。
- `publish_pages.sh --dry-run --already-built` 只打包。新入口以观察到的 `gh-pages` 为唯一父提交，保持打包 tree 不变。把父包和待推包分别 `git archive` 到干净树，给原版 `deploy/news-sync.sh --dry-run` 检查。公网 `data/meta.json` 须与父包 `rebang/data/meta.json` 字节一致，才把父包作为本地基线。它只是公开版本标记，不证明 DO 已安装的每个文件都相同；`file://` 演练不访问公网。
- 校验后再核对远端两个 ref，只调用一次普通 `git push --atomic`，不强推、不降级、不重试。两个 ref 都需更新时要么一起更新，要么都不更新。普通快进不是独占写入权，切换前必须排除其他写入口。
- `main` 非快进、`gh-pages` 与检查点不一致、必要的远端 ref 消失，或切换和采集建站期间发现远端 ref 又移动，都会写 `.git/mac-publish/HALT`。发起推送前也会创建 HALT，成功记录两条远端 ref 后才清除。推送被拒、结果不明或推送中断时，保留标记，后续手动和定时轮次都停止。人工恢复前保留 `tg.db`、`refs.json`、`HALT` 和日志，核对两个真实远端 SHA、候选 SHA、数据库和公网。
- 采集、建站或接收校验失败时，日志记录用到的 `source_commit`，不推送，旧站继续服务。本地数据库和已接受的检查点保留。远端 ref 未发生异常时，下一轮可以用同一版本或更新的正常快进版本重试。

## 从固定 SHA 切换到自动跟进（合并后在 Mini 手动做一次）

1. 等最近一次 `:05` 任务退出，在下一次触发前完成准备。以专用账号进入现有部署 clone，确认没有在途采集或发布，也没有其他写入口。先独立备份 `tg.db`、`.git/mac-publish/refs.json`、现有 `HALT` 和日志。确认没有 SQLite journal/WAL/SHM，工作区只有未暂存的 `tg.db` 可能有改动。
2. 获取真实远端 `main`、`gh-pages` 的 SHA（`git ls-remote --refs origin refs/heads/main refs/heads/gh-pages`），并 `git fetch --no-tags origin main gh-pages`。确认 `main` 包含获批的这次改动，是此前 `main` 检查点的快进。核对 `gh-pages` 的检查点、已有推送回执和公网 meta；如果 HALT 提到推送结果不明，先核清两个 ref 和数据库再继续。把核对过的 `main` 和 `gh-pages` 完整 SHA 分别记为 `MAIN_SHA`、`PAGES_SHA`。
3. 用 `git checkout --detach --no-overwrite-ignore "$MAIN_SHA"` 切换。若唯一阻碍是 `tg.db` 与新提交冲突，先在停止写入的前提下确认备份可读，再暂时用 `git show HEAD:tg.db` 恢复工作区的跟踪版本，重新 checkout。切换无论成功或失败都立即原样放回备份的 `tg.db`。核对 `HEAD`、暂存区和本地库哈希后再继续。缓存与新跟踪文件冲突时停下来查明。
4. 再核对远端两个 SHA 没变。原子更新 `.git/mac-publish/refs.json`，键沿用 `refs/heads/main`、`refs/heads/gh-pages`。在确认备份、代码、库和两个 ref 都对得上后，把现有 `HALT` 移到备份目录。既有 plist 仍可用，无需重装或改 SHA。

   ```sh
   printf '{"refs/heads/main":"%s","refs/heads/gh-pages":"%s"}\n' \
     "$MAIN_SHA" "$PAGES_SHA" > .git/mac-publish/refs.next &&
     mv .git/mac-publish/refs.next .git/mac-publish/refs.json
   ```

5. 在现有 plist 的账号和最小环境下手动跑一轮 `tools/mac_publish.sh`。核对日志里的 `source_commit`、`validation=passed`、推送回执和两个远端 SHA，等现有线上接收流程完成，再核对公网 `data/meta.json` 与本轮 Pages 包字节一致、线上 `build-info.json` 的 `source_commit` 包含本次改动、新条目可以打开。下一次 `:05` 自然触发后核对定时日志和公网版本。

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
