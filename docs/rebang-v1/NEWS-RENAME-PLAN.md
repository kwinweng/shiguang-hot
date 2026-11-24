# 名字统一成 News：实施方案（2026-11-25 草案）

在 11/22 旧方案（本地分支 `docs/shiguang-news-rename-plan` `939aee7`，`docs/superpowers/plans/2026-11-22-shiguang-news-rename.md`）基础上扩大范围。旧方案的冻结证据、演练、逐段回退做法照用；本页只写变化和新增项。**本页只是方案，不授权执行。** 每一段红灯操作执行前绑定提交号请阿欢批准。

## 已定（阿欢 11/25）

- 原话：「好的，那也设计这样一个方案吧，然后你把它排在我目录之后单独做……我希望到时产品、仓库、本地等都是要统一的，然后都用 News 就可以了。」
- 时机：仍放在串行计划第 5 步之后（第 6 步），排在 0.5 步「挪发布目录 + 浅克隆」之后。
- 发布目录最终名：`~/projects/shiguang-news-publish`（0.5 步直接挪到这里，改名时不再动它的路径）。开发仓库改名后叫 `~/projects/shiguang-news`。
- `rebang/` 代码目录、站点路径 `/rebang/`、`gh-pages` 里的 `rebang/data` 这次不改，记为以后可选的一步。

## 命名约定

- 中文产品名保留「拾光资讯」（「资讯」即 News）。
- 英文标识统一：仓库、目录、包名、日志标签用 `shiguang-news`；需要展示的英文名用 `Shiguang News`。
- 域名 `news.kwinweng.com` 不变。

## 统一范围（当前 → 新名 · 谁改 · 回退）

1. **GitHub 仓库** `kwinweng/shiguang-hot` → `kwinweng/shiguang-news`。阿欢批准后由 T3 用 `gh repo rename` 执行，执行前后核对仓库 ID 不变。回退：`gh repo rename shiguang-hot`（旧名未被占用时）。GitHub Pages 已于 11/25 停用，旧方案里「改名可能触发 Pages 构建」的顾虑已不存在；但 `gh-pages` 分支仍是线上同步源，必须保留。
2. **服务器同步脚本** `/usr/local/libexec/news-sync.sh` 里写死的 `codeload.github.com/kwinweng/shiguang-hot/...` → `shiguang-news`。基于服务器现装版本做一行最小改动（现装版本与仓内不同，不能直接覆盖），改前备份为 `news-sync.sh.bak-<日期>`。**顺序：GitHub 改名后、旧地址失效前尽快改**；若改名后旧 codeload 地址仍跳转可用，可先观察一轮自然同步再改。回退：恢复备份。须阿欢批准并提供服务器入口。
3. **内置盘主仓** `~/projects/shiguang-hot` → `~/projects/shiguang-news`，用旧方案第 4 段的 `git worktree move` + `mv -n` + `git worktree repair` 命令。回退：逆序执行。
4. **SSD 工作树** `/Volumes/kwin_SSD/Development/shiguang-hot` → `/Volumes/kwin_SSD/Development/shiguang-news`，同上一并移动。
5. **T3 工作区** `~/.t3/worktrees/shiguang-hot/*`（目前 11 个，`git worktree list` 13 条）。先清理已合并、已结束线程的工作区（清理前列清单请阿欢确认，未提交改动不删）；剩下的全部 `git worktree repair` 指向新主仓。目录前缀 `shiguang-hot` 是否改名取决于 T3 是否支持，不支持就保留旧前缀并记为已知遗留。回退：repair 回旧主仓。
6. **T3 项目** `workspaceRoot` 改为新 SSD 路径，项目标题改为「拾光资讯 / Shiguang News」。不新建、不删除项目。回退：改回原路径。
7. **remotes**：`origin` → `git@github.com:kwinweng/shiguang-news.git`，`mini-handoff` → `https://github.com/kwinweng/shiguang-news.git`，保留原 fetch refspec、`[blob:none]` 过滤和 upstream。只用 `git ls-remote` 验证。回退：`set-url` 回旧名。
8. **发布 checkout 的 remote**（`~/projects/shiguang-news-publish/checkout`）：在两次 `:05` 之间、持发布锁时改 `origin` URL，确认无 HALT 后下一轮自然运行验证。plist 路径因 0.5 步已是最终名，**不需要再改 LaunchDaemon**；只有 plist 里若写了仓库名（如日志标签）才改。回退：改回 URL。
9. **Air 本机**：Air 已在 T3 链接但本机引用未核实。改名前只读盘点 Air 上的克隆、remote、自动化；改名后按同样方式更新 remote/目录。核实不了就记为未完成，不声称全量完成。
10. **仓内引用**：代码里的仓库名已由 PR #82 换成 `shiguang-news`（`deploy/news-sync.sh`、`tools/dispatch_hourly.py`、测试夹具、README）。剩下 `AGENTS.md`（开发目录路径）、`docs/SOURCE-FETCH-OPERATIONS.md` 两处有效引用，改名当天一起更新。`HANDOFF-history.md`、`docs/legacy/`、取证记录里的旧名保留原文。
11. **产品英文名**：页面里如有英文标识（manifest `name`/`short_name`、`<title>` 英文部分、分享图文案）统一为 `Shiguang News`；中文显示不变。改动会进站点，按普通功能合并走测试 + 线上核实。
12. **不在本次范围**：`shiguang-hot-ios` 仓库（独立 App 仓库，另议）、拾光日记、`rebang` 目录与站点路径、域名、DNS、nginx。

## 执行段落与停点（每段单独批准）

- **段 A（绿灯）**：只读冻结证据——两条 remote、所有工作树状态、仓库 ID、`main`/`gh-pages` SHA、线上 `meta.json` 指纹、服务器现装 `news-sync.sh` 的 SHA-256、Air 盘点。合进仓内英文名统一（第 11 项）。
- **段 B（红灯）**：GitHub 改名（第 1 项）→ 立刻核对新旧 codeload 地址 → 改服务器同步脚本（第 2 项）→ 观察一轮自然同步成功、公网指纹随新发布推进。异常立即停，按回退处理。
- **段 C（红灯，涉及工作区路径）**：暂停所有挂在旧路径上的 T3 线程 → 移动主仓和 SSD 工作树（第 3–5 项）→ 更新 T3 项目（第 6 项）→ 改 remotes（第 7–8 项）→ Air（第 9 项）→ 更新仓内剩余引用（第 10 项）。
- **验收**：GitHub 新名可读、仓库 ID 一致；服务器一轮自然同步 `published=true`；mini 一轮自然 `:05` 发布成功、`build-info.json` 的 `source_commit` 正确；各工作树 `HEAD` 与迁移前一致；结果写进 `进度.md`。

## 复核

段 B、段 C 涉及权限、发布链路和服务器，按 `AGENTS.md` 在执行前交另一家模型（指定具体模型，如 GPT-6.2-Sol）只读复核最终命令清单和回退步骤，复核前后做工作区指纹比对。
