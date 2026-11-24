# Mac mini 快进发布

本手册不是上线授权。切换目录、停启调度、首次生产写入均由获批操作者按批准的提交号和设备执行。不要并行运行第二个发布入口，不操作 DO 或旧盒子。

## 入口与防护

- `tools/mac_publish_launcher.py` 是固定入口的**源文件**。人工把获批版本安装到发布根目录的 `bin/mac_publish_launcher.py`。部署模板用同一个 Python 3.11+ 环境、绝对路径和固定的 `checkout/` 工作目录；自动 checkout **不会更新** `bin/`。升级固定入口也须在旧轮次退出后手动替换。`tools/mac_publish.sh --code-sha FULL_SHA` 仍兼容旧 plist（SHA 参数不再用于固定版本）；它不会自动切到会替换这条旧入口链的候选。旧版线上固定 SHA 的程序不会自更新，须一次性迁移。
- 固定入口独占 `checkout/.git/mac-publish/lock`。每轮只抓取 `main`、`gh-pages`；首次没有 `refs.json` 时也必须证明远端 `main` 是人工确认的 detached HEAD 或其后代。有检查点后还要证明它是已接受 `main` 的快进，且 `gh-pages` 与上次检查点一致。缺 ref、历史倒退或远端库分叉时写 `HALT`。远端库变化且与本地库字节不同时，保留本地 `tg.db`，另存 `remote-tg-<候选 SHA>.db`，记录三个 blob 和候选提交。
- 从候选提交提取 shell 和 Python，做 `sh -n`、`py_compile`、隔离导入，合计默认最多 30 秒。启动到确认另有一个总时限，默认 30 秒，包含 checkout 和两次远端核对。`mac_publish.sh --worker-v1 LOCK_FD SOCKET_FD MAIN PAGES` 中，worker 发 `1+` 表示就绪并支持回执。固定入口切换 checkout、核对远端后发 `G`，收到 `A` 才更新 `refs.json` 和 `boot.json.good`，写完发 `C` 允许采集。候选进程组在启动期由固定入口的子进程监护，超时或固定入口意外退出都会结束未放行的进程组。预检或启动失败记录候选为 `bad`、保留检查点，沿用数据库保护逻辑回退到 `good`。下一轮仍 fetch，同一坏 SHA 跳过，等 `main` 到新 SHA 再试。启动确认后的普通采集或校验失败可在下一轮重试。安装时固定入口和 worker 要用同一获批版本，两端都必须支持本回执约定。
- checkout 只允许未暂存的 `tg.db` 与 HEAD 不同。首次仅在本地库仍等于启动 HEAD 的库时，用不同的远端种子替换；有检查点后保留本地库和忽略的缓存，不覆盖与新跟踪路径冲突的缓存。拒绝 SQLite journal/WAL/SHM。中断后若 HEAD、index 和跟踪文件一致，且无 `index.lock`，可自动取回 `checkout-tg.db`；否则保留现场，见下节。采集不继承来源 Cookie、会话或翻译密钥。
- 持锁依次跑旧流水线、`rebang_refresh.sh --no-publish` 和 `write_build_info.py`。临时 Git index 从本轮抓到的 `main` 构造数据提交，只允许 `tg.db` 改变。**库没变也生成一条同 tree 提交** `Refresh public collection data (no db change)`，否则 Git 会把相同 SHA 的 ref 排除在服务端事务之外。`build-info.json` 的 `source_commit` 是本轮启动和建站所用提交，`database_sha256` 与实际入库 blob 对比。
- `publish_pages.sh --dry-run --already-built` 只打包。新 Pages 提交以观察到的 `gh-pages` 为唯一父提交，保持打包 tree 不变。把父包和待推包分别 `git archive` 到干净树，交原版 `deploy/news-sync.sh --dry-run` 验证。公网 `data/meta.json` 与父包 `rebang/data/meta.json` 必须字节一致；该标记不证明 DO 已安装的每个文件都相同。`file://` 演练不访问公网。
- 校验后再次核对远端两个 ref，只调用一次 `git push --atomic`。两条 ref 都更新，都用精确旧 SHA 的 `--force-with-lease`，无 `+`，新提交各以观察到的提交为父。若远端在通告后改变其中一条，服务端原子事务拒绝两条更新，库没有变化时也一样。切换前仍必须排除其他写入口；Git 不能检测观察间隔内移走又回到原 SHA 的写入。
- 在 push 前写 `HALT`。普通快进使本轮基线过期时，如果能证明 `main` 是本轮观察值的后代、其 `tg.db` 与检查点一致，且 `gh-pages` 未变，本轮记录 `publish deferred` 并正常结束，下一轮用最新代码重建；最终核对和明确的原子 lease 拒绝都走这条规则。历史改写、远端库变化、`gh-pages` 异动或无法确认推送结果会保留 `HALT`。推送成功后仍须用 `git ls-remote` 核对两个目标 SHA，才更新检查点并清除标记。普通采集、建站或接收校验失败且远端稳定时，保留本地库和已接受的检查点，旧站继续服务。

## 启动或 checkout 中断后的人工恢复

1. 等在途轮次退出，获批操作者在专用 clone 里拿**同一把锁**，拿不到就不要操作。没有在途任务也不能假定 `index.lock` 是废的；确认没有 Git/checkout/数据库写入进程，尤其是旧轮次留下的子进程。以下检查、保全和修复全在持锁 shell 内做。

   ```sh
   umask 077
   mkdir -p .git/mac-publish && flock -n .git/mac-publish/lock /bin/sh
   ```

2. 在改任何文件之前，备份工作区 `tg.db`、`.git/index`、`.git/HEAD`、`.git/mac-publish/`（含 `checkout-tg.db`、`refs.json`、`boot.json`、`HALT`、临时文件和远端库副本）、日志和有差异的文件。用 `git status --porcelain`、`git diff --cached`、`git diff HEAD`、`git ls-files -u` 核对 HEAD、index 与工作区是否处于不同提交；分别核对 SQLite sidecar、库完整性和两个真实远端 SHA、候选提交及公网 meta。
3. 确定只是废弃的 `.git/index.lock` 后，将它移入现场备份，**不要**直接删仍可能被 Git 使用的锁。确认 HEAD 仍 detached、对应的是已批准的基线；若 index/跟踪文件部分写入了另一提交，从已批准提交明确恢复那些路径（例如用 `git restore --source=HEAD --staged --worktree -- <确认要恢复的路径>`），保留尚未弄清来源的改动、未跟踪文件和忽略的缓存。不要盲跑 `git reset --hard` 或 `git clean`。若无法区分或 index 损坏，保全整个 clone 后准备另一个干净 checkout，比在脏工作区强切安全。
4. `checkout-tg.db` 是被换出前的原始库；先核对并保留工作区那份，再在无 SQLite sidecar 时恢复原始库。确认只余未暂存的 `tg.db` 差异、暂存区干净，再用 `git checkout --detach --no-overwrite-ignore <核准 SHA>` 切换（若目标跟踪的库不同，先将本地库单独备份并保留，再用旧 HEAD 的跟踪版本过 checkout，完成后恢复本地库）。检查新 HEAD/index 和库。若有 `HALT`，在推送状态、库和公网对账完成且获批后，将标记移进现场备份；不要为清标记擅自重写检查点。

程序不会自动移走 `.git/index.lock` 或覆盖半写好的非数据库文件：发布锁不能证明独立 Git 进程已退出，文件差异也不能证明是 checkout 中断还是人工改动。干净的前/后状态可自动恢复数据库；两种 `SIGKILL` 窗口及保留半更新现场已用 `file://` 演练，未在 Mini 实测断电。

## 迁移到新目录 + 浅克隆（获批后一次性做）

示例根目录 `/Users/kwin/projects/shiguang-news-publish`，其下 `checkout/`、`venv/`、`log/`、`bin/` 都可配置。`/Users/kwin/projects/shiguang-news` 留给开发仓库，不放发布任务。模板还要按实核对账号、`HOME`、`PATH`、`BOX_PYTHON` 和所有绝对路径。用既有专用身份和非交互认证；不改凭据或分支保护，不读取密钥文件。

1. 安排在两次 `:05` 之间，先等旧轮次自然退出，再由操作者执行 `sudo launchctl bootout system /Library/LaunchDaemons/local.shiguang.news-publish.plist`（sudo 由操作者输入）。确认旧任务已卸载、没有在跑的发布或其他写入口；拿旧 clone 的发布锁，核对无 `HALT`、无 `checkout-tg.db`、无 SQLite sidecar，记录旧 HEAD、`refs.json`、两个实际远端 SHA、成功回执和公网 meta 指纹。对不上就停，不靠迁移绕过旧状态。若迁移窗口不够，保持停发，不抢在 `:05` 前半配半启。
2. 备份旧 plist、日志和整个旧发布目录，不删。用已核准的同一个仓库 URL（不要在命令里写凭据）创建新的专用发布 clone：

   ```sh
   ROOT=/Users/kwin/projects/shiguang-news-publish
   mkdir -p "$ROOT/bin" "$ROOT/log"
   git clone --depth=50 --single-branch --branch main --no-tags "$ORIGIN_URL" "$ROOT/checkout"
   git -C "$ROOT/checkout" fetch --depth=50 --no-tags --refmap= origin \
     refs/heads/gh-pages:refs/mac-publish/gh-pages
   git -C "$ROOT/checkout" checkout --detach "$APPROVED_MAIN_SHA"
   ```

   在挪旧目录之前，用 Mini 已配置的发布 Git 身份设置新 clone 的本地提交信息，并确认命令输出取到正确身份：

   ```sh
   git -C "$ROOT/checkout" config --local user.name "$PUBLISH_GIT_NAME"
   git -C "$ROOT/checkout" config --local user.email "$PUBLISH_GIT_EMAIL"
   git -C "$ROOT/checkout" var GIT_AUTHOR_IDENT
   git -C "$ROOT/checkout" var GIT_COMMITTER_IDENT
   ```

   还要用 plist 里实际的运行账号、`HOME`、`PATH` 和该认证方式需要的环境（如 `SSH_AUTH_SOCK`）在新 clone 验证。启动器和 worker 都保留 Git 已配置的 `core.sshCommand`；只有未配置时才用 `ssh -o BatchMode=yes`。如果 Mini 用了旧 clone 的局部设置，按既有配置为新 clone 设置，并确认 SSH 使用非交互模式。下面在该最小环境中运行，使用与启动器相同的认证设置：

   ```sh
   cd "$ROOT/checkout"
   export GIT_TERMINAL_PROMPT=0
   if ! git config --get core.sshCommand >/dev/null; then
     export GIT_SSH_COMMAND='ssh -o BatchMode=yes'
   fi
   git ls-remote --exit-code --refs origin refs/heads/main refs/heads/gh-pages
   git push --dry-run --atomic --no-follow-tags origin \
     refs/remotes/origin/main:refs/heads/main refs/mac-publish/gh-pages:refs/heads/gh-pages
   ```

   确认两条 ref 都返回，dry-run 能非交互连接接收端，且没有真实更新。如果 clone 期间远端已前进，先刷新这两条本地 ref 再检查。dry-run 不验证所有实际写入规则。Mini 现装认证方式和权限待获批迁移时实测。

   `APPROVED_MAIN_SHA` 是已验证包含获批修复的 `main` 提交，必须接在旧检查点和旧 HEAD 后。若本地浅克隆没有所需提交，先手动 deepen 并验证；不要只比较 SHA 字符串、跳过检查点或假定历史相关。用同一 Python 3.11 在新根目录重建 `venv/`，安装 `beautifulsoup4`、`pillow`、`lxml` 等既有发布依赖，验证 `python3`、`realpath`、`git`（须支持原子推送）和用于维护的 `flock`。从获批的工作区安装固定入口：

   ```sh
   install -m 0644 "$ROOT/checkout/tools/mac_publish_launcher.py" "$ROOT/bin/mac_publish_launcher.py"
   ```

3. 在旧入口停止、锁仍持有时，完整保留旧 `tg.db`、`.git/mac-publish/` 状态（尤其 `refs.json`、已有的 `boot.json` 和远端库副本）、`var/`、`media/`、`site/`、`site-v11/`、`site-v11.prev/` 和实际使用的运行缓存。逐项确认路径并以保留权限的方式复制到新 clone 对应位置，校验数据库字节指纹、检查点和运行文件；不要覆盖新 Git 的 HEAD、index、refs 或浅克隆元数据。日志可留存旧目录或按既有保留规则另存。不复制来源凭据，不用测试库或试跑包替代生产资料。完成后释放旧锁、把旧目录改名为有日期的备份（不删除），并将旧 plist 和原路径记录ไว้以备回退。
4. 以 `tools/mac_publish.launchd.plist.example` 为模板修改 plist，确认 `UserName`、`WorkingDirectory`、`ProgramArguments`、`HOME`、`BOX_PYTHON`、`PATH` 和日志目录都指向新位置。`plutil -lint`；检查 `Minute=5`，没有 `RunAtLoad`/`KeepAlive`。在本机同样最小环境下先用 `file://` 裸库演练，**不要**对生产远端手动代跑。获批操作者安装 plist（root:wheel、0644，日志目录可由专用账号写），`sudo launchctl bootstrap system /Library/LaunchDaemons/local.shiguang.news-publish.plist`，用 `launchctl print system/local.shiguang.news-publish` 核对等待状态，不 `kickstart`。
5. 等本机时间自然 `:05`。查新日志里的 `source_commit`、`validation=passed`、两条推送回执和结束状态；取回执 `gh-pages` 的 `build-info.json`，确认 `source_commit` 包含获批提交。等既有接收流程，比较该包 `rebang/data/meta.json` 和公网 `https://news.kwinweng.com/data/meta.json` 的原始字节 SHA-256，并确认新条目打开、仍为 noindex。日志、版本、指纹不符则报待验；不启动旧任务、不强推或重复发布。回切前也须单独确认并先对账两条远端 ref、库和公网，不能直接启用停发前的旧状态。

浅克隆验证覆盖从 `file://` 用 `--depth=50` 克隆、浅的 `gh-pages` 父包、正常快进、两个提交父子关系和原子推送。`merge-base --is-ancestor` 可能因缺历史误判，固定入口会请求 `main` 依次 `--deepen=50`、`150`、`300` 再证明，仍无法证明则留 `HALT`。Git 也可能顺带补齐其他已知浅边界。迁移前若已知检查点很旧，建议手动深化 `main`，确认 `git merge-base --is-ancestor` 返回 0 再启用；必要时让 `main` 取得完整历史。不要周期性重新浅截工作 clone。深度 50 是初始深度，不是永久磁盘上限，历史仍会增长。生产 transport 是否支持及实际占盘在 Mini 迁移时验收，不从本地演练推断。

## 没有旧任务的新机器

首次部署仍按独立的首发批准、调度批准两步做。用上节的专用 clone、固定入口和 plist 环境，保留最后可信的数据库和公开归档/媒体。按同一套接收检查验收，不降低 `max(100, ceil(公开基线文件数 × 0.5))` 的门槛，不用试跑包或人为改发布时间冒充最新内容。获批首发后才手动执行 plist 的同一条命令一次，记录采集/建站耗时、占盘峰值、收包延迟和公网 SHA-256；公网验收通过且另获调度批准，才按上节安装并等自然 `:05`，不代跑。
