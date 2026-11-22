# 拾光资讯仓库改名实施方案

> 后续执行者：仅在阿欢批准对应阶段后，按 `executing-plans` 逐项执行。仓库执行者规则见 [`AGENTS.md`](../../../AGENTS.md)；本次代办不改常规规则。

**目标：** 把拾光资讯仓库身份由 `shiguang-hot` 改为 `shiguang-news`，同步本地路径和有效引用，与拾光日记迁移分开。

**方法：** 先在本地分支记录方案；后续把本地路径/引用与 GitHub 改名分成可独立回退的阶段。公网 `news.kwinweng.com`、DNS、nginx、采集数据、`main`、`gh-pages`、Pages 设置及例程在本次不做主动变更；如果无法证实改名不会中断同步或触发部署，停在 GitHub 改名之前。

**工具：** Git worktree、GitHub CLI、T3 项目设置、HTTPS/DNS 只读检查。

---

## 需求和验收边界

- 本轮只创建本地方案分支 `docs/shiguang-news-rename-plan`，不推送、不启工作流、不改 GitHub、不部署、不删除文件；记录进展到 `HANDOFF.md`。仓内没有独立的 `需求`、`开发规则` 或 `进度.md`；本页记录迁移需求和运行约束，`AGENTS.md` 是规则入口。最终实施结束后按要求在 `进度.md` 记录结果。
- 后续改动只做仓库身份、目录、remote、T3 引用和仓内有效链接更新。不改产品名称、站点域名、日记仓库、独立 iOS 仓库、模块名、生产固定路径或历史取证原文；不能因字符串相同就替换。
- 代码和发布脚本的引用改动只在独立分支，不合并 `main`。更改仓内 `deploy/news-sync.sh` 不会更改服务器上已安装的脚本，不能以此当作生产连续性证据。

## 基线与影响

| 位置 | 当前状态 / 后续范围 |
|---|---|
| 内置盘 Git 主仓 | `~/projects/shiguang-hot`，盘点时为干净 detached HEAD `69ed741`；改名保留完整 `.git` 和分支/提交。 |
| SSD 关联工作树 | `/Volumes/kwin_SSD/Development/shiguang-hot`，盘点时 `mini/dev-20261122` 在 `b4c0d24` 且干净；当前方案分支从该提交建立。 |
| Git remote | 共用 `origin`（SSH）、`mini-handoff`（HTTPS）；都指向旧名。分别保留现有 fetch refspec、upstream、传输方式；先确认有无独立 push URL 或 worktree 级覆盖。 |
| T3 | 现有「拾光资讯」项目绑定 SSD 旧路径和旧远端身份，未发现项目定时任务。更新原项目，不新建或删除项目；当前线程可能仍持有旧 cwd。 |
| Air / 恢复目录 | Air 未链接，实际目录、remote、T3、自动化未核实。Mini 的 T3 scratch 内 `recovery-checkout` 指向旧名，有 3 份未提交文档；`trial.eHE8SG` 无 remote。先判定用途，不改或清理恢复材料。 |
| GitHub | `kwinweng/shiguang-hot` 为公开仓库，`main` 为默认分支，盘点时新名未查到。Pages 为 `gh-pages:/`、无 CNAME、旧 Pages 项目地址 HTTP 200；`hourly` 是手动只读测试，另有 Pages 自动构建。 |
| 自定义域名 | 北京时间 2026-11-22 23:42 左右，nginx 上首页、CSS、JS、`data/meta.json` 均 `200`，`/rebang/` `301` 回根；JSON `data_at=2026-11-22T23:09:09+08:00`、`fixture=false`。这是改名前只读基线，不是改名后结果。 |
| 生产同步 | 接收服务器同步脚本默认直连 `https://codeload.github.com/kwinweng/shiguang-hot/tar.gz/refs/heads/gh-pages`；盘点时返回 200。仓库文档记录每 20 分钟（另有最多 90 秒抖动），安装位置 `/usr/local/libexec/news-sync.sh`；尚未在主机核对现装版本和日志。还需核对盒子 `/workspace/shiguang-prod`、例程以及 Mini `/opt/shiguang-news/checkout` 固定发布克隆的实际引用（若在用）。 |

## 执行清单（本轮不执行切换）

### 1. 冻结证据，不触发发布

- [ ] 从当前工作树运行 `git status --short --branch`、`git worktree list --porcelain`、`git rev-parse --path-format=absolute --git-common-dir`。确认主仓、工作树、待改分支、两个目标路径均符合基线；遇到新工作树、未提交改动或正在运行的线程/任务，先停。不 stash、强制移动或覆盖文件。
- [ ] 记录两个 remote 的 URL、独立 push URL（如有）、fetch refspec 和 upstream；日志脱敏，不读密钥、Cookie、`.env`。用 `gh repo view kwinweng/shiguang-hot --json id,nameWithOwner,defaultBranchRef,viewerPermission` 记录 GitHub 仓库 ID，`gh api repos/kwinweng/shiguang-hot/pages` 核对 CNAME、发布源、状态；记录 `main` 和 `gh-pages` 的 SHA、Actions/Pages 构建的状态与时间。正常生产可能继续更新，不将自然推进误判成此次分支推送。
- [ ] 从可访问的盒子、接收主机及固定发布机，只读核对实际拉取 URL、发布 remote、运行身份和在途调度；记清是否存在仓库名守卫。T3 Air 未链接则由阿欢开通或在 Air 本机核对，不把 Mini 的恢复副本当作 Air 现状。
- [ ] 以 GET 方式检查 `https://news.kwinweng.com/`、`app.css`、`app.js`、`data/meta.json`、`rebang/`，记录 HTTPS、200/301、`public_base`、`data_at`、`built_at` 和 `fixture`。另外记录旧 Pages 地址和直连压缩包状态，作为两个独立检查项。

### 2. 只在分支准备引用

- [ ] 从最新核准基线另开实施分支 `chore/shiguang-news-repo-identity`。列出引用：`git grep -n -I -E 'shiguang[-_]hot|shiguang-prod' -- README.md AGENTS.md HANDOFF.md deploy docs .github tools tests`；逐项分类，不做全局替换。
- [ ] 把 `deploy/news-sync.sh` 的归档默认地址、`deploy/README.md` 和 `tests/test_news_server_sync.py` 的对应断言一同更新为新仓库路径。`tools/dispatch_hourly.py` 更新 `REPO`，`tests/test_schedule_tools.py` 更新对应地址夹具；不能实际 dispatch。核对 `.github/workflows/hourly.yml` 没有需要变更的仓库名，不改触发条件；`tools/publish_pages.sh` 仍使用 `origin`，不改发布行为。
- [ ] `README.md` 更新现行仓库/Pages 链接，保留当前 Pages 是否启用的事实；`HANDOFF.md`、`docs/HANDOFF-history.md`、`docs/legacy/` 和取证记录中的历史旧名按原文保留，必要时加迁移说明。保留 `news.kwinweng.com` 和生产路径，除非另有批准。
- [ ] 跑 `bash -n deploy/news-sync.sh`、`python3 -I tests/test_news_server_sync.py`、`python3 -I tests/test_schedule_tools.py`、`git diff --check`。预期本地测试通过；Linux 原子发布的用例允许在 macOS 按预期跳过。仅使用现有测试夹具，不访问真实数据，不手动推 `main` / `gh-pages`，不合并 `main`。

### 3. GitHub 改名前停点（需要阿欢确认）

- [ ] 在获准的非生产仓库（不用真实内容、不开 Pages 或发布工作流）演练同类改名：确认改名后旧的直连 `codeload` URL 能否跟随重定向、是否保持 `https` 以及最终是否指向正确仓库/分支。用同步脚本同样的 curl 选项验证 GET，不用 GitHub 网页或 `git fetch` 成功代替。演练结果只是证据，不能当成生产持久保证。
- [ ] [GitHub 改名文档](https://docs.github.com/en/repositories/creating-and-managing-repositories/renaming-a-repository)不保证 Pages 项目 URL 重定向，也未对直连 codeload 或不触发 Pages 构建给出保证。若不能确认已装生产同步在整个窗口可用、没有在途写入，或不能排除改名触发 Pages 自动部署，**不运行改名命令**。若要先调整生产入口或 Pages 设置，单独提出方案，绑定提交号请阿欢批准；不临时改 DNS、停例程或关闭 Pages 绕过限制。
- [ ] 只有通过停点并收到明确批准，才运行 `gh repo rename shiguang-news -R kwinweng/shiguang-hot`（不在本轮运行）。立即查询新名元数据，仓库 ID 必须与原值一致；核对分支、Pages 设置、构建记录、旧/新归档 URL 以及生产首页和数据，再继续本地切换。若出现意外构建或同步异常，立即停止后续步骤并报告。

### 4. 本地目录、remote、T3 和 Air

- [ ] 先让依赖旧路径的 T3 线程、编辑器、任务停止访问工作树；从不在这两个目录内的稳定执行位置迁移。先在临时合成 Git 仓库演练同一 Git 版本的移动/修复。仅在两个目标路径不存在、旧路径确认为原仓且没有未提交文件风险时执行：

```sh
old_main="$HOME/projects/shiguang-hot"
new_main="$HOME/projects/shiguang-news"
old_ssd=/Volumes/kwin_SSD/Development/shiguang-hot
new_ssd=/Volumes/kwin_SSD/Development/shiguang-news
# 下列命令属于获批切换阶段，不用于本轮写方案。
( set -eu
  test -d "$old_main/.git" && test -f "$old_ssd/.git" || exit 1
  for dest in "$new_main" "$new_ssd"; do
    test ! -e "$dest" && test ! -L "$dest" || exit 1
  done
  git -C "$old_main" worktree move "$old_ssd" "$new_ssd"
  mv -n "$old_main" "$new_main"
  test -d "$new_main/.git" && test ! -e "$old_main" || exit 1
  git -C "$new_main" worktree repair "$new_ssd"
  git -C "$new_main" worktree list --porcelain
  git -C "$new_ssd" rev-parse --path-format=absolute --git-common-dir
)
```

- [ ] 预期登记两条新路径，SSD 的 common dir 指向内置盘新 `.git`；两处各自 `git status --short --branch`、`git rev-parse HEAD` 与迁移前一致。命令报错立即停止，先看路径和登记，不重复整段、不 prune。
- [ ] 只在 GitHub 新身份可读、旧/新仓库 ID 核对完成后，从新 SSD 工作树运行 `git remote set-url origin git@github.com:kwinweng/shiguang-news.git` 和 `git remote set-url mini-handoff https://github.com/kwinweng/shiguang-news.git`。如有独立 push URL，按原协议单独更新。仅用 `git ls-remote` 验证访问，不 push；比较 fetch refspec 和 upstream 不变。
- [ ] T3 对原「拾光资讯」项目仅更新 `workspaceRoot` 为新 SSD 路径，重新读取项目核对仓库身份、标题、线程及项目设置；打开新的 checkout 后再继续。Air 本机按同样原则核对后单独安排，不迁移拾光日记、不改 Mini 的恢复取证副本。任何无法更新的生产侧引用列为未完，不对外声称全量完成。

### 5. 验收与回退

- [ ] 切换后立即复查第 1 项的公网基线和 GitHub 元数据；在不主动触发同步的前提下，至少观察一个完整的预期接收周期，核对服务器日志成功，以及 `data_at` / `built_at` 能随新发布自然推进。如果接收上游在窗口内没有新版本，只能报告「站点可访问，持续更新待验收」。在 `进度.md` 记录分支、前后路径、远端、线上核验（含时间）、未验项和阿欢待办。
- [ ] **仅分支方案或代码未切换：** 保留分支和文件，不执行 GitHub/生产回退。切回原分支前先保存现有修改；不 `reset --hard`，不删除文件或分支。
- [ ] **本地目录/remote/T3 回退：** 按实际完成步骤逆序。先停止访问新路径；若两个目录均已迁移且旧路径未占用，从新内置盘主仓用 `git worktree move` 把 SSD 工作树移回旧名，再将内置盘移回旧名，从旧主仓 `git worktree repair` 指明旧 SSD 路径。若只完成一步，先检查登记再只撤销那一步。根据是否回退 GitHub 身份恢复 remote，并核对原有 fetch refspec/独立 push URL；T3 原项目恢复原路径后复查两处 HEAD 和状态。
- [ ] **远端或生产异常：** 停止本地切换，不重跑发布，也不回滚数据。保留当前静态树、`gh-pages`、日志和同步状态。记录故障后由阿欢批准是否执行 `gh repo rename shiguang-hot -R kwinweng/shiguang-news`；执行前核对仓库 ID 和旧名未被占用。恢复后重查归档、Pages 页面和实际同步；按需另行批准服务器处置。不得 force-push 旧包、删除备份、改 DNS 或将改回名字视为自动恢复的证明。
