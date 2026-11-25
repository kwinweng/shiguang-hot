# 拾光资讯采集断更恢复方案

2026-11-21。本文只记录排障和待批方案，不是生产执行授权。时间均为北京时间。

## 断点

| 环节 | 已核实 / 待确认 |
| --- | --- |
| 旧采集 → `tg.db` 和旧站 `site/data/live.json` | `tools/box_scrape.sh` 是生产旧采集入口；`pipeline.py` 实际采集并生成 `live.json`，`tools/persist_action_data.sh` 只提交 `tg.db`，最后写 `site/build-info.json`。远端最后一次数据提交是 11/20 01:13:06 的 `6313e1e3`。据转报，负责这条链路的「热榜抓取发布」例程 01:16 起暂停；暂停原因和最后一次执行结果待盒子证实。 |
| v11 刷新 → 组合发布 | `tools/rebang_refresh.sh` 读取 `tg.db`，也独立抓取部分 v11 来源，只重建 `site-v11/`。它调用 `tools/publish_pages.sh --already-built`，不会重建旧站。当前 `gh-pages` 仍是 `b0ed26e1`（11/20 01:20:26）；该包旧站 `live.updated` 为 01:11:36，`build-info.source_commit` 为 `6313e1e3`，v11 `meta.built_at` 为 01:20:22。转报的后续 v11 建站成功但发布被拒，与此调用关系一致。 |
| `gh-pages` → `news-sync` → nginx 根路径 | 服务器每 20 分钟拉包；根路径展示包内的 `rebang/`，但接收仍验证旧站根目录、归档和 `data/live.json`。#77 在源端拒绝过期旧站，即使 v11 刚生成；接收端对旧候选的同类拒绝也是预期，均不是故障起点。服务器本轮日志与静态根未由本机独立读取。 |

`live.updated` 是旧站本轮构建输入时间，不是最后一条报道的发布时间。不能只改时间戳或离线重建旧库来假装采集恢复；自然小时配额也意味着一轮可能没有新增。恢复须同时确认实际采集状态、最近内容日期和 v11 的数据，而非只看构建时间。接收端还拒绝空/样例实时流及不够新的归档；先单测打包，再做接收验证。

## 候选修复

`tools/box_scrape.sh --no-publish` 仍从干净的 `main` 完成正常采集、旧站构建、数据持久化和构建元信息写入，**仍可提交并推送真实的 `tg.db` 到 `main`**，只省略旧 runner 自己的 Pages 发布。锁忙或任一步失败返回非零。默认模式不变。然后由 `tools/rebang_refresh.sh` 建 v11 并使用现有发布器一次性打包旧站和 v11。它不拉 Git 或重置旧树，发布时仍取 `.box-scrape.lock`。旧阶段失败时跳过本轮 v11 发布，避免发送本轮未持久化或未写完元数据的包。#77 的源端和接收端保护原样保留。

### 阿欢可先查的只读证据

- **盒子**：核对「热榜抓取发布」暂停时间/原因、最后一次运行的命令/退出状态和 `/workspace/shiguang-logs` 中对应日志；核对 `/workspace/ops/rebang-refresh-loop.sh` 和 X/翻译例程的实际工作目录、执行频率、拉取方式，以及哪些环节会写 `tg.db` 或推 `gh-pages`。只给脚本的流程摘要和脱敏日志，不要抄环境文件或凭据。
- **盒子**：在实际生产 checkout 核对分支、有没有未提交的数据、HEAD、旧站 `site/data/live.json` 的 `updated`、v11 `site-v11/data/meta.json` 的 `built_at` 与最近一次发布报错；不要为通过干净检查而清理工作区。
- **服务器**：核对 `news-sync.timer` 最近触发、`news-sync.service` 拒收/最后 `published=true` 的时间和候选 SHA；读实际 nginx 静态根的 `build-info.json`、`rebang/data/meta.json`。不启动、不修改 unit，不手改线上文件。

## 生产恢复：审批与验收

建议先在已有输入和 Linux 构建能力的盒子恢复；本轮不迁机器。每一项都要阿欢单独明确批准，合并与部署批准绑定 PR 及提交号；没有批准就不执行。下方命令仅供获批后使用。

1. **批准合并 PR 到 `main`。** 先确认本轮检查结果和生产 clone 的自动拉取影响。现有回路可能在下一轮拉到新版；不能把合并当作无上线影响。
2. **批准调整现有例程。** 核实后暂停或切换会独立推同一个 `gh-pages` 的循环/例程，等正在跑的轮次结束；确认没有第二个 `tg.db` 写入者。仍给站点产 X/翻译缓存或每日原稿的生产者应保留，若同一例程兼有发布，另批切掉发布段。不要删除例程。
3. **批准单轮生产部署（含正常数据持久化和一次 Pages 发布）。** 在确认 checkout 干净、仅有这一条写入/发布路径后，用同一把**外层锁**串联旧采集和 v11 刷新；不能用内部两把锁代替跨两阶段的互斥。确认 `BOX_PYTHON`、日志目录和发布配置沿用盒子的有效环境，不设 `REBANG_PUBLISH=0`。例如：

   ```sh
   flock -n -E 75 /workspace/shiguang-prod/.git/zixun-cycle.lock sh -c '
     cd /workspace/shiguang-prod &&
     sh tools/box_scrape.sh --no-publish --log-dir /workspace/shiguang-logs &&
     sh tools/rebang_refresh.sh
   '
   ```

   `75` 表示外层锁冲突，本轮未运行；需核对实际部署为普通克隆，或由管理员指明等效的绝对锁路径。记录整轮耗时、采集日志和 `last-refresh.json`，验证唯一一次发布、两个产物都新、数据库哈希与提交吻合。随后等现有 timer 拉取，核对 `published=true`、真实静态根的版本、线上首页/noindex 与至少一个新条目。要求单轮明显短于 30 分钟；整轮中没有第二轮进入。不把成功生成包算作已上线。
4. **批准恢复/更新定时例程。** 单轮及线上验收通过后，复用盒子原 :07/:37（Asia/Shanghai）的例程执行同一条带外层锁的序列；不启第二套生产调度。区分锁冲突、旧采集/持久化失败、v11 刷新失败、发布失败和接收拒收。v11 的个别来源失败时脚本可能已发布降级包并返回非零，须查分步日志与包版本，不能只凭退出码重跑。连续两个定时周期核对产物、耗时、无重叠与线上同步，不因 `hour_used` 就重试。单次调用的请求与配额不变；先对比现有 v11 循环频率，确认合并调度后每天的请求量，试运行时记录实际耗时和请求量。
5. **服务器变更另批，仅在接收侧确有独立故障时。** 正常路径不改 timer、服务、nginx、静态根或阈值。新包仍拒收时先看日志并用符合接收环境的 `deploy/news-sync.sh --source <隔离候选> --target <隔离目标> --dry-run` 核对；若需要手动触发接收、改配置或回退静态站，另列目标、影响和回退，等批准。

若发现组合任务不稳定，先按批准边界暂停组合任务（不删除），保留采集和接收日志与最近一次正常版本。默认旧 runner 未改变；是否临时恢复旧例程、回退代码或回滚线上站点分别批准。不要推旧包或伪造新时间通过 #77。

## 长期定时

接管目标仍是 Mac 每 30 分钟自动运行。建议由常在线 Mac 上的 `launchd` 定时调用**单一、非交互、串联并互斥**的生产入口，保留 Linux 盒子作为已验证的恢复路径，服务器只接收，不成为第二采集者。Air 尚无此调度；旧站 `staged_output` 更新已有目录用 Linux 的 `renameat2`，main 在 macOS 不能直接连续构建，未合并的 Mac 交接分支不能当成现有生产能力。迁移前另行验证连续原子建站、真实 TG、X 与翻译限额、四路持续原稿（不是一次性快照）、登录/休眠后的调度行为、凭据安全注入、整轮性能与单次发布回执；届时单独审批新例程、旧例程停用与切换。若 Mac 达不到持续在线要求，继续由盒子单一例程运行，不双写。

## 博主采集断更（2026-11-25 排查）

只读核对 Mac mini 生产发布目录 `~/projects/shiguang-news-publish/checkout`（代码 `e0070253`）17:39 那轮的 `var/rebang/in/bloggers.json`，以及仓库交接记录。盒子（`/workspace`）本机连不到，盒子侧状态未独立核实。

- **X 16 个 0 条（`x_dump_missing`）**：适配器只读 `var/rebang/x-dump/<时间>/` 里现成的原始响应，自己不联网。原稿一直由工头盒子上 Grok Bot 的「X 博主 + 翻译」例程用它自带的公开 X 读取工具写进盒子生产克隆 `/workspace/shiguang-prod/var/rebang/x-dump/`（提示词 `/workspace/rebang-v1-briefs/routine-x-translate.md`，11/16 01:52 起每 2 小时）。11/17 起发布迁到 Mac（先 Air、11/24 起 Mini），但从没接过「盒子 → Mac」的转储传送；Mac 上能找到的最后一份转储是 11/18（Air 开发目录，早已超过 36 小时）。Mini 生产克隆里根本没有 `var/rebang/x-dump/`，`last_ok_at` 也是空（新克隆没带上旧帖）。所以断因不是代码 bug，而是生产机器换了、供稿方还在旧机器上（或已随 Grok Bot 停用而停了），中间没有通道。代码侧读取、过期判断和「缺失/过期」提示都正常；只要有新转储放进 Mini 的 `checkout/var/rebang/x-dump/<YYYYMMDDTHHMM>/`（被 `.gitignore` 忽略，不影响发布器的干净检查），下一轮就会读到。
- **微博 6 个 0 条（`weibo_cookie_unset`，不是 `login_expired`）**：Mini 上没有 `~/.config/rebang/` 目录，Cookie 文件从没放到这台机器；而且 Mini 发布器原来故意把 Cookie 路径指向不存在的保留路径，放了也不会读。已改为只认固定位置、权限 0600 的文件（见 `MAC-PUBLISH.md`）。
- **公众号 5 个（`wechat_weread_qr`）**：同上，Mini 上没有微信读书会话文件，发布器也原样屏蔽；已一并放开到同一固定位置。夕小瑶走公开源，正常。

### 请阿欢在 Mac mini 上操作（AI 不碰 Cookie、不扫码）

1. **微博 Cookie**：在电脑浏览器登录微博副号，打开 weibo.com 任意页 → 开发者工具 → 网络 → 选一个 `weibo.com/ajax/...` 请求 → 请求头里 `Cookie` 的值，只复制值。然后在 Mini 终端：

   ```sh
   mkdir -p ~/.config/rebang && chmod 700 ~/.config/rebang
   (umask 077; pbpaste > ~/.config/rebang/weibo-cookie.txt)
   chmod 600 ~/.config/rebang/weibo-cookie.txt
   ```

   文件里只有一行 Cookie 值（带不带 `Cookie:` 前缀都行）。不要发到聊天里。
2. **微信读书扫码**（约 10 分钟内完成）：

   ```sh
   cd ~/projects/shiguang-news-publish/checkout
   ../venv/bin/python -m rebang.bloggers.weread login --qr-png /tmp/weread-login-qr.png --wait 600
   ```

   另开一个终端 `open /tmp/weread-login-qr.png`，用微信扫码并在手机上点确认。中途约每 56 秒出现一次 `LOGIN_TIMEOUT` 是正常的，码仍有效，继续等；如果打印要验证码，按它给的带 `--otp` 的命令重跑。成功后会话自动存到 `~/.config/rebang/weread-session.json`（0600）。可用 `../venv/bin/python -m rebang.bloggers.weread status` 确认是 ok。
3. 两项都只在含本次修复的代码换上 Mini 之后才会生效。生效后下一轮 :05 的 `log/publish.log` 会出现 `source_credentials=weibo,weread`，博主页微博、公众号有新内容才算恢复。
4. **X 需要阿欢定**：原供稿方是盒子上的 Grok Bot 例程。要恢复「原来的转储供稿」，先要确认这个例程现在还在不在跑、最后一次写转储是什么时候；再决定由谁、用什么方式把转储送到 Mini 的 `checkout/var/rebang/x-dump/`（比如盒子定时用只读同步推过来，或 Mini 定时从盒子拉）。这涉及例程和机器之间的访问权限，按红灯等阿欢批准，不用付费 X API、不新开账号。
