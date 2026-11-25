# Mac mini 快进发布

本手册不是上线授权。当前只交付功能分支和本地验证；不要合并 `main`、操作 DO 或启动生产任务。首次生产推送和启用定时分别按阿欢批准的提交号、设备和影响范围办理。

## 入口与防护

- `tools/mac_publish.sh --code-sha FULL_SHA` 只用于专用 clone。由同一个标准账号从手动和系统 `launchd` 运行。`PATH` 和 `BOX_PYTHON` 使用绝对路径；需要 Python 3.11+、`beautifulsoup4`、`pillow`、`lxml`、`flock`、`realpath` 和支持原子推送的 Git。`PATH` 将该 Python 环境的 `bin` 放在系统目录之前，以便接收脚本调用同一环境的 `python3`。
- 代码在 detached HEAD 上运行，`--code-sha` 是批准的起点：HEAD 必须是它本身或它的后代（只能是下文「自动跟进」切过去的）。每轮只 `fetch` 两个数据来源 ref，不 reset/clean。首轮以远端 `main:tg.db` 为起点，最多只替换仍与固定提交一致的 `tg.db`；后续保留本地采集数据和运行缓存。专用工作区不要运行任何其他会写 DB、采集缓存或发布的入口。首期不读取来源 Cookie、会话文件或翻译密钥。
- 持锁依次跑旧流水线、`rebang_refresh.sh --no-publish`、`write_build_info.py`。有 SQLite journal/WAL/SHM 就拒绝。在临时 Git index 上从 `main` 父提交构造纯 `tg.db` 数据提交；若库没变则不写 `main`。`build-info.json` 的 `source_commit` 是固定运行代码，不是数据提交；`database_sha256` 对比实际入库的 blob。
- `publish_pages.sh --dry-run --already-built` 只打包。新入口以观察到的 `gh-pages` 为唯一父提交，保持打包 tree 不变。把父包和待推包分别 `git archive` 到干净树，给原版 `deploy/news-sync.sh --dry-run` 检查。公网 `data/meta.json` 须与父包 `rebang/data/meta.json` 字节一致，才把父包作为本地基线。它只是公开版本标记，不证明 DO 已安装的每个文件都相同；`file://` 演练不访问公网。
- 校验后再核对远端两个 ref，只调用一次普通 `git push --atomic`，不强推、不降级、不重试。两个 ref 都需更新时要么一起更新，要么都不更新。普通快进不是独占写入权，切换前必须排除其他写入口。
- `.git/mac-publish/HALT` 在发起推送前创建，成功记录两条远端 ref 后才清除。推送被拒、结果不明、或发现未经预期的 ref 变化，都停止后续手动和定时轮次。保留 `tg.db`、`refs.json`、`HALT` 和日志，核对两个真实远端 SHA、候选 SHA、数据库和公网，再另行批准恢复。不要自动删标记、覆盖库、重置分支或强推旧包。接收校验失败未推送，保留本地库；常规下一轮可在同一远端基线上重试。

## 自动跟进 main：先试跑，下一轮再切

`main` 正常往前合并（含只改文档）不再写 HALT。状态都在 `.git/mac-publish/`：

| 文件 | 含义 |
| --- | --- |
| `refs.json` | 上轮成功推送后的两条远端 ref（原有） |
| `trial.json` | 最近一次试跑：`sha`、`ok`、第几次 `attempts`、失败原因 `reason`、时间 |
| `trial.log` | 最近一次试跑的完整输出 |
| `candidate.json` | 试跑通过、等下一轮切换的提交 |
| `switch.json`、`tg.db.switching` | 只在切换那几秒存在；中途被杀时由下次启动收尾 |

每轮顺序：

1. **启动收尾**：有 `switch.json` 就先把 `tg.db.switching` 放回 `tg.db`。原位置若有文件，只有它等于切换两端提交里的 `tg.db` 才覆盖；否则两份都留着、本轮报错，等人工核对。
2. **看远端**：和 `refs.json` 一样 → 照常。不一样时，只有「`gh-pages` 没动、新 `main` 是旧 `main` 和当前代码的后代、`tg.db` 没被别人改」才算正常合并，继续；历史改写、非后代、别人改了 `tg.db` 或 `gh-pages` 都 HALT（与原来一样）。首次启动（没有 `refs.json`）要求远端 `main` 已包含当前代码，否则拒绝、什么都不写。
3. **切换**：有 `candidate.json`，且它仍在「当前代码 → 远端 `main`」这条线上，就把 `tg.db` 挪到一边、`git checkout` 候选、再放回 `tg.db`（本地库始终不被提交里的副本替换），然后用新代码的入口重新跑本轮。切换失败：放回 `tg.db`、丢掉候选、把这版代码记为不再试跑，本轮报错，下一轮照旧用老版本发布。重跑的那次不会再切第二次。
4. **正式发布**：用当前版本，流程和校验与原来一样。数据提交接在观察到的 `main` 上。推送前或推送时 `main` 被别人正常合并：本轮不发布、**不写 HALT**，库保留，下一轮在新 `main` 上重建；其他变化或推送结果不明照旧 HALT。
5. **试跑**（只在推送成功后、且 `main` 的代码和当前代码不同才做）：在 `.git/mac-publish/trial/` 用 `git clone --shared` 检出新 `main`，复制本轮的 `tg.db`、`media/`、`var/rebang/`（APFS 上是写时复制），跑同一套 `pipeline.py` → `rebang_refresh.sh --no-publish` → `write_build_info.py` → `publish_pages.sh --dry-run`，再用当前的接收脚本以刚发布的包为基线做 dry-run。全程不推送、不碰正式目录和远端；跑完删掉试跑目录。
   - 成功 → 写 `candidate.json`，日志 `follow: trial passed`，下一轮切换。
   - 失败或超时（默认 20 分钟，`--trial-timeout` 可改）→ 杀掉整个试跑进程组，写 `trial.json` 原因，日志 `follow: trial FAILED …`，**照常用老版本发布，不停发**。同一份代码最多试 3 次，之后日志 `failed 3 times` 并等新代码；要强制重试就删 `trial.json`。
   - 发布器在试跑中被停（launchd 发 SIGTERM）→ 杀掉试跑进程组，这次计入次数。试跑进程不持有发布锁。

日志里搜 `follow:` 就能看到每次跟进、试跑结果和切换；健康看板暂未接入这些状态。

### 上线这次改动（主线程在 Mini 手动做一次）

1. 停发间隙内（不在 :05 运行中），确认没有 `HALT`、发布锁空闲，备份 `tg.db` 和 `.git/mac-publish/`。
2. 在发布 clone 里 `git fetch origin main`，确认合并后的 `main` 包含本改动；把 `tg.db` 挪到一边，`git checkout --detach <合并后的 main SHA>`，再把 `tg.db` 放回，`git status` 只应显示 `tg.db` 改动。
3. plist 里的 `--code-sha` 可以不改（旧值 `06d08d7c…` 是新 `main` 的祖先即可；也可以改成新 SHA）。`refs.json` 保留。
4. 等下一次 :05 自然运行，日志里应有 `published main=…`，`build-info.json` 的 `source_commit` 是新 SHA。之后合一次只改文档的 PR，确认下一轮有 `follow: trial passed`、再下一轮有 `follow: switched code`，且没有 `HALT`。

### 回退

- **不想自动切了**：删 `candidate.json`；在 `trial.json` 里写 `{"sha": "<新 main SHA>", "ok": false, "attempts": 3}` 可让这版代码不再试跑。
- **切过去的新版本有问题**：等当前一轮结束，按上面第 2 步的同样做法（`tg.db` 先挪开再放回）检出上一个好的 SHA，删 `candidate.json` 和 `trial.json`。注意：只要 `main` 上的代码和运行版本不同，下一轮还会试跑并切回去，所以真正的回退是在 `main` 上合一个 revert PR；临时止血可以同时写上面的 `trial.json` 锁住那版代码。
- **完全退回旧行为**：检出本改动之前的提交（同样保护 `tg.db`），删 `candidate.json`、`trial.json`；旧代码会在 `main` 下次被别人推动时写 HALT。

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
