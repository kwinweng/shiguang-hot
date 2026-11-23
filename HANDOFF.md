# HANDOFF
（拾光资讯 v11。更早的交接记录在 `docs/HANDOFF-history.md`；v11 各模块开发记录已并入 `docs/rebang-v1/MODULES.md`。）

## 目标
6 频道资讯站按 `docs/rebang-v1/CONTRACT.md` 上线并稳定刷新。

## 2026-11-21 对外更名一期（待审批）
- [PR #78](https://github.com/kwinweng/shiguang-hot/pull/78) → `main`。新旧网页、PWA、分享、文档和测试统一为「拾光资讯」；`AGENTS.md` 按 14:47 确认改由 T3 agent 开发，审批红绿灯不变。
- 更名相关 pytest 60 通过、1 跳过（无真实 `var/rebang/in`）；前端 43 通过。macOS 全量 pytest 427 通过、7 失败、2 跳过；7 项均在干净的 `6313e1e3` 复现，dark 子用例在两边均通过。全量离线测试会改写 `docs/rebang-v1/evidence/history-favorites-search/` 下三张跟踪截图，本次已恢复，未提交截图。
- iOS 只在本地改显示名和提示并重新生成工程；主 Bundle ID 仍为 `com.kwinweng.shiguang-hot`，签名团队、描述文件、SKU 不变。仓库名、域名、`rebang` 路径和发布布局不变；未合并、部署、传 TestFlight 或操作采集例程。
- 下一步：等阿欢分别批准是否首次入库 `ios/` 和是否合并/发布 #78。采集恢复是另一任务。

## 最新交接（2026-11-18，北京时间）

以下为当前状态；下面 11/16 的运行节奏、视觉和待办只作历史参考。

- **PR #73**（`290f744d`，11/16 23:48）：频道、博主各为连续长流；段间「下一个：X」，最后「内容已结束」；去掉全部「查看更多」。收藏、热搜只在各自页面无限下拉。
- **PR #74**（`f312142d`，11/17 01:28）：v16 视觉参考少数派，红色强调、白底、细分隔线、毛玻璃底栏，缩略图在右，X 头像无红边；热搜只叫百度/知乎/B站，日期用「今天」，顶栏无 logo，暗色跟随系统。旧 v10/v13 金色方向已被取代；实际令牌见 `web-v11/app.css`。
- **PR #75**（`f060942a`，11/17 10:01）：FREE 中文、双语新闻从环球移到时事。时事为竹新社、我的一张大字报、FREE 中文、双语新闻；环球为 BBC World、卫报 World。来源只归属一个频道，以 `rebang/contract/channels.json` 为准。
- **已定交互**：收藏、分享均长按卡片；横滑只切频道；图片可全屏、多图横滑；详情保留互动数、热门回复、TG 评论楼、X 引用卡片。
- **接管顺序与授权**：阿欢要求当前会话在 Mac 接管；先手动刷新并发布，线上核实成功后回报，再由阿欢通知旧机器停刷新循环和例程；旧任务停止确认前不启用新定时任务。目标为普通刷新、X+翻译各每 30 分钟。**08:30 私聊已由阿欢在 11/17 后续交接中取消，本机不创建；旧例程由阿欢在切换时暂停。** 站内今日重点整理来源保留。不要把这项授权扩大成任意代码合并或其他部署。

### 本机准备与阻塞

- **首次本机推送成功，但线上接管未通过：版本在观测前被覆盖**。11/17 23:53:52–23:54:14，`rebang_refresh.sh --no-fetch` 的 ingest/build/publish 全部成功，`failed` 为空。gh-pages SHA `454494cd5fabcd6386e2288aa1c77ed69a5faee8`，源码提交 `a951c7fc`，新站 `built_at=2026-11-17T23:53:53+08:00`，2579 条新闻、1027 条博主内容、pending 0；三家热搜在 23:53:30 均抓取成功。一次性核验两次仍见线上 23:39:37 版，随后发现 gh-pages 已被 `423e10bf`（23:55:54）替换，结果为 `publication_replaced_before_observed`，见 `var/rebang/logs/cutover-verification.json`。该覆盖版本的新站时间 23:55:50，旧站 build-info 指向原发布链路源码 `7177e323`；又一轮 `5d9da84c`（11/18 00:01:28）继续发布同一源码，浏览器实测线上已为 **11/18 00:01:25**（2578 条新闻、984 条博主内容，`fixture:false`），页面 meta、响应头及 robots.txt 的 noindex 均保留。提交的通用发布者名称不能单独证明具体执行主机；可以确定存在本次 Mac 发布之外的持续发布。本次没有盲目再次强推、没有改旧任务、没有创建新定时任务，也未报告接管成功。下一次发布须能覆盖服务器同步核验窗口；仍按阿欢既定顺序切换，不擅自先停旧任务。X 新读取、四份整理的持续接收、微博 Cookie、定时翻译的安全注入仍需落实。
- 已同步 `origin/main`（准备开始时 `296c8a14`，后续纳入 `59ba584` 自动数据），GitHub CLI 的功能分支与 gh-pages 写入均已实测。两个交接包均通过 `SHA256SUMS` 校验，运行缓存恢复到 `var/rebang/`，运行说明包仅隔离提取两份例程、翻译脚本和旧刷新循环；不复用 Linux 包里的虚拟环境或软链接。
- Mac 使用 `var/rebang/venv/bin/python`（Python 3.13），已安装现有运行依赖 beautifulsoup4、Pillow，以及验证/扫码所需 pytest、segno；安装 Homebrew `flock`。脚本运行需 `BOX_PYTHON="$PWD/var/rebang/venv/bin/python"`，PATH 需含 `/opt/homebrew/bin`。旧站已以 `NO_FETCH=1 SITE_MODE=public MAIL_DIGEST=0` 构建，并写出 `site/build-info.json`；没有运行会更新 `tg.db`、提交和发布的 `box_scrape.sh`。
- 接管最初的契约、站点、博主、今日重点测试 **105 passed**（Mac 修复后的 109 项结果见下文）。首次真实刷新仅跑 `--no-publish`；第一次因 T3 重启在 tgmeta 阶段终止，核实无残留进程后重跑。重跑于 **11/17 23:08:16–23:13:36** 完成，tgmeta、三家热搜、bloggers、ingest、build 均返回成功，`var/rebang/logs/last-refresh.json` 的 `failed` 为空，但语义检查发现四份整理输入全部为空，见下条。新站为真实数据（`fixture:false`），2573 条新闻、460 条博主帖子，不能以此覆盖线上完整内容。
- **23:14 早期预检（当时未推送；后续首次发布见上条）**：`publish_pages.sh --already-built --dry-run` 打包 1700 个文件，包含 `rebang/`。媒体重定位后 23:14:53 重建，1095 个站内媒体 URL 全部有对应文件，无缺失；`rebang.push --dry-run` 出 5 条根地址深链，仅出稿、未发送（其中新英文条目仍待翻译）。准备阶段浏览器读到的线上 `built_at` 为 11/17 22:49:19，2577 条新闻、1027 条帖子，meta + X-Robots-Tag + robots.txt 均保留 noindex。这是旧机器版本，**不是本机发布验收；当时未发布、未创建新定时任务**。当前切换状态以本节首条为准。
- **四份整理输入已补交并恢复**：最初缓存包仅有合并后的数据，首次 ingest 会丢掉 562 条整理帖子。阿欢随后交付 `rebang-digests-20261117.tar.gz`（23:24 快照），已校验 SHA256 并恢复到 `var/rebang/digests/20261117T2324/`。通过现有四个目录环境变量真实 ingest，world 173、x 138、hot-daily 118、github 133，共 **562 条全部恢复**。`HOT-DAILY_FEED_DIR` 名称含连字符，用 `env` 或 subprocess env 字典传入；不需要改适配器或 `sources.json`。原始资料仍由原「资讯」bot 每日生产，持续只读接收方式尚未落地，不能把今晚快照当成同步完成，见 `OPERATIONS.md`。
- **媒体迁移已验证**：包内 522 处本地媒体引用使用 `/workspace/shiguang-prod/...` 绝对路径；另有 699 处 TG 图片引用指向根目录 `media/`，这个目录不在 state 包内。已从现有 `origin/gh-pages` 的 `rebang/media/` 恢复缺少的公开图片（不改远端发布物）。原缓存 1221 处引用均能找到对应文件；刷新后的 bloggers 输入中仍有 517 处旧绝对路径，已仅对这些路径重定位到本机，修改前备份位于 `var/rebang/local-ops/before-media-relocation-20261117T231453/`。最终建站核对 1095 个站内媒体 URL，无缺失。后续再次恢复原包时仍需重定位，不能只看构建退出码。
- **登录与权限**：微信读书已由阿欢扫码登录，`weread status` 实测 `session:true, valid:true`，会话权限 `0600`。列表接口回 `-2041`，沿用现有 cover + 正文回退；首轮正文读取不稳定，复核时乱翻书、caoz 各抓到 1 条，夕小瑶公共源抓到 10 条；MacTalk、独立开发变现周刊、王建硕保留原快照各 1 条，未把缓存说成新抓取。恢复缓存时保留原 id 和时间，并修复 3 处旧媒体路径、补回 3 张原包图片。DeepSeek 密钥已由阿欢通过安全输入提供，仅传给翻译运行进程；23:38 实测 `deepseek-flash`（关闭思考）39/39 段成功、失败 0、pending 0，5 次请求、4182/2879 prompt/completion tokens。后续定时安全注入尚未配置。微博副号 Cookie 文件仍未到位，阿欢可直接拷到本机 `~/.config/rebang/weibo-cookie.txt`（0600），不经聊天；X API v2 新读取仍缺权限，不能转用旧 bot 的专有工具或擅自办理付费套餐。目前 X 仅读取已迁移的 dump。08:30 私聊已取消，无需投递渠道。凭据不查看、不打印、不提交。
- **Mac 连续建站兼容修复（待合并）**：旧站首次构建正常，目标 `site/` 已存在时 Linux 专用 `renameat2` 在 macOS 报 `symbol not found`。`shiguang/site/build.py` 已对 Darwin 使用系统 `renamex_np(RENAME_SWAP)`，Linux 保持 `renameat2(RENAME_EXCHANGE)`，两者均保留整树原子交换与失败不替换的契约。Mac 上 4 项既有原子构建回归通过；真实旧站连续重建两次成功，相关测试合计 **109 passed**。没有改成先删旧目录，也没有改变服务器发布方式。
- **TG 采集不能遗漏**：`rebang_refresh.sh` 的 ingest 只读 `tg.db`，tgmeta 只补公开元数据。新定时运行还需保留真正更新 `tg.db` 的既有采集步骤。`box_scrape.sh` 要求 `main` 且工作区干净，不能在有用户未跟踪文件的开发目录里强行运行或清理；旧机器仍写库时也不要启动第二个数据提交者。
- **持续供稿方案已验源，连接未落地**：独立技术方案来自 T3 子任务「四份每日整理持续供稿方案」，请求 `group/design-claude`，实测 `claude-opus-5-5`；`verify_t3_claude.py --task plan` 返回 `verified:true`，decision `57b8d9c3-adb7-49c7-a0ad-d7e5cb42de2f`。采用的准备方向是保留原资讯 bot 生产，新机器只读接收原始 JSON 与媒体，再用现有四个目录环境变量读取；不为源连接缺失另建生成器。尚缺四路实际源目录、可用且获授权的传输通道、产出时间/写入方式及媒体布局。本机手动入口已保留在 `var/rebang/local-ops/mac-refresh.sh`，固定当前 23:24 快照并传入 Python、PATH、时区和四路目录；仅做 shell 语法与目录检查，未再次运行发布，未创建调度。快照可验证发布链路，不能证明后续供稿或 X 实时读取就绪。方案较早的密钥/登录未就绪描述已由后续实测更新，当前状态以上方记录为准。

### 11/18 无需本人配合的准备与验证

- **本轮范围**：阿欢要求先完成不需要本人配合的部分。继续本地实现、真实只读采集及隔离验证；不据此合并 main、部署、切换旧任务或安装定时任务。
- **TG 真实采集已隔离验证**：使用既有 `box_scrape.py --test-dir <仓库外新目录> --limit 3`。三个来源各 1 次请求，全部 `ok`，FinanceNewsDaily 新增 6 条；隔离副本真实建站成功，原 `tg.db` 的 SHA256 前后相同，没有 Git 数据提交或发布。临时副本已清理，日志和摘要留在 `var/rebang/local-ops/validation-20261118/tg-logs/` 与 `tg-isolation.json`。正式 TG 数据写入仍须等旧写入者停止，并使用满足既有要求的干净 main。
- **公众号六个号本轮均实际抓取成功（00:23）**：先复现 MacTalk 正文读取 `network`，独立开发变现周刊正文约 3.6 MB；原代码吞掉正文错误，随后合并旧缓存并把本轮标 `ok`，会误更新 `last_ok_at`。现在正文请求启用 curl 压缩，正文错误或缺可验证发布时间交回原有失败保留逻辑：保留内容和上次成功时间，标本轮 error/stale。复测五个微信读书来源各取到 1 条、公共来源取到 10 条，缓存合并后共 16 条（MacTalk 2 条，其余保留原条数）。这证明本轮抓取成功，不代表每轮都有新发布文章。证据：`wechat-compressed-summary.json`。故障回归覆盖网络失败及正文无时间两条路径。
- **运行入口已纳入仓库**：`tools/rebang_mac_refresh.sh` 固定传入 Python、PATH、时区和整理根目录，支持未来以 `REBANG_DIGEST_ROOT` 指向同步目录；缺任一输入目录提前退出，实测未启动刷新。旧本机入口转发到仓库脚本。`tools/translate_deepseek.py` 复用已实测批量实现，去掉旧机器专属默认路径、把 usage log 放本机日志目录，仅放行精确模型名 `deepseek-flash`。密钥仍从环境变量读取，未变更存储或创建长期注入；离线验证覆盖真实 pending→HTTP 边界→缓存/usage log、错误保留及密钥不输出。
- **本地完整重建通过（00:25:10）**：使用 Mac 入口 `--no-fetch --no-publish`，ingest/build 全部成功，`fixture:false`，2575 条新闻、984 条博主内容，pending 0；扫描生成 JSON 中 3342 处媒体引用，无缺失。本轮跨日后按既有整理保留窗口收录 518 条，历史 562 条为 11/17 恢复时的数量，不要求跨日保持不变。没有再次发布。
- **回归与 Mac 避坑**：相关既有测试加新增回归合计 **131 passed，8 subtests passed**。首次运行 box_scrape 测试有 1 项因 macOS `/var`→`/private/var` 的路径别名比较失败；测试临时根目录统一 `resolve()` 后通过，未改生产采集逻辑。
- **YouTube 状态更正**：`DECISIONS.md` 11/16 15:49 已记本人确认 13 个频道全部启用，当前配置确有 13 个，缓存共 130 条。下方“名单为空/待确认”为更早历史，不是当前阻塞，无需再次找本人确认。

## 11/16 历史状态
- **已上线**：https://news.kwinweng.com/ 根路径就是 v11（11/16 00:08 阿欢决定）；`/rebang/` 301 到根；全站 noindex（页面 meta、`X-Robots-Tag`、`robots.txt`）。旧的登录阅读器、`/mail/`、`/archive/` 已下线。`shiguang-reader-update.timer` 已于 00:32 `disable --now`（实际原是每 5 分钟跑，不是每天一次）；灵记 `lingji-news-source` 只读的 `topics.sqlite3` 从此不再更新。发布链路、服务器配置、回退见 `docs/rebang-v1/OPERATIONS.md`。2026-11-16 已按确认删除旧阅读器/旧站回滚备份；线上阅读器库和 unit 文件仍保留，因为灵记还在读这份库。
- 合并记录：PR #40（v13 合入 main）、#41（TG 转发来源名）、#42（搜索索引加载竞态）、#44（public_base 改为根地址）、#45（文档审计）、#46（袋鼠图标）、#47（去掉顶栏袋鼠，日期回到最左边）。标签页、加到主屏、启动图和分享图仍是袋鼠；顶栏只有日期，没有 logo。
- 线上验收（11/16 00:20 左右）：Playwright 390x844 真触摸 76/76（`docs/rebang-v1/evidence/integration-v13/capture.py`）；数据、媒体、脚本 200；深链 `https://news.kwinweng.com/#/item/<id>` 冷启动直达详情，旧 `/rebang/#/item/<id>` 跳转后同样可用。图标改动后复查 75/76，剩下的失败是部分英文新闻尚未翻译，与图标无关。
- 刷新：v11 现在由「X 博主 + 翻译」例程每 2 小时刷新并发布一次（提示词 `/workspace/rebang-v1-briefs/routine-x-translate.md`：写 X dump → `rebang_refresh.sh --no-publish` → DeepSeek Flash 翻译 → `rebang_refresh.sh --no-fetch` 发布；每轮简报在 `/workspace/rebang-v1-briefs/runs/x-translate-*.md`，11/16 01:52 起）。8:30 私聊例程也在跑（`routine-0830.md`，11/16 稿 `runs/push-2026-11-16.sent.txt`）。30 分钟一次的刷新还没加（盒子没有 cron，定时都靠 bot 例程）。旧站采集 `tools/box_scrape.sh` 仍由工头「热榜抓取发布」例程按 :07/:37 跑，继续写 `tg.db`、发布 gh-pages；它发布时会顺带把当时的 `site-v11/` 一起发出去，但不会重建 v11。
- **第一期收尾已上线（PR #53，squash `dd7824944`；11/16 13:50 建站发布，14:03 线上 built_at 13:50:40）**：博主页 X 视频/GIF 站内播放（查看器图视频混排、离开即暂停、播放失败给原帖链接；页面 referrer 改 same-origin，否则 video.twimg.com 回 403）；底栏切换卡顿修掉（4 倍降速长任务 335ms→61ms，`docs/rebang-v1/evidence/perf-0116/`）；设计令牌 + 全站 Lucide 图标 + 动效令牌与「减少动态效果」（`docs/rebang-v1/DESIGN-SYSTEM.md`）；修了刷新按钮倒转、查看器底栏按钮触摸误关、滚动时误弹长按菜单、正文译文没好时看不到原文、搜索索引里已清掉的本地图 404。线上核实（14:07）：`capture.py` 84/84、真数据视频检查 21/21、noindex（meta + X-Robots-Tag + robots.txt）仍在。没测：真 iPhone Safari、画中画/横屏。
- **第二期已上线（PR #55–#59，11/16 15:21 建站发布，15:41 线上 built_at 15:21:42）**：即刻 9/9 走公共 RSSHub（免登录，4 实例轮换，90 条）；TG 评论楼（每条最多 30 条公开评论、楼中楼、10 条以上折叠；线上 133 条带评论、623 条评论、70 条楼中楼，旧缓存按 6 小时窗口陆续补成新格式）；YouTube 管道与播放器已上（名单空，显示「频道名单待确认」，候选 `docs/rebang-v1/youtube-candidates.md`）；5 个公众号微信读书管道已备好，站上写「等扫码」；微博免登录方式全不通。线上 e2e `capture.py --phase2` 92/94，两条失败是新英文条目等翻译例程（`p2live-result.json`）。
- **第三期整理（11/16 16:00 前后）**：远程只留 `main`、`gh-pages`（以及进行中的 `grok/p3-*` 功能分支）；删了已合并的 `feat/rebang-ui-fulltext`、`feat/rebang-partial-translate`。盒子删了没合并的旧分支 `agent/hot-daily-publish`（11/07 旧站日报发布链，已被 main 取代）和 5 个 `backup/*` 旧 `tg.db` 快照提交，删前打包到 `/workspace/_archive/rebang-20261116/git/unmerged-local-branches.bundle`；盒子旧文件归档清单见 `/workspace/_archive/rebang-20261116/README.md`。旧站文档 `ARCHITECTURE.md`、`DESIGN.md`、`INGEST.md`、`PRIVATE_LOGIN.md` 和 `docs/LEGACY-SITE.md` 移到 `docs/legacy/`。
- **微博 6 个博主已上线（PR #69，squash `e942ae97d`；11/16 19:26 建站发布，19:42 线上 built_at 19:26:16）**：用 weibo.com 桌面版 ajax + 副号 Cookie（`~/.config/rebang/weibo-cookie.txt`，0600，不进仓库/日志），不用 weibo-crawler（m.weibo.cn 不认这份 Cookie）。线上每人 10 条。sinaimg 对浏览器只认 weibo.com Referer，所以图、封面、头像在抓取时存成本地副本 `var/rebang/media/weibo/`（约 240 张 / 38MB）；视频站内播不了，查看器给「打开原帖」。Cookie 失效（ok≠1/跳登录）→ 微博标 login_expired、保留上次内容、日志打 `weibo cookie expired`；换 Cookie 文件即可恢复。线上 `docs/rebang-v1/evidence/weibo/capture.py` 10/10。细节见 `docs/rebang-v1/MODULES.md` 微博条。
- **注意**：11/16 19:00 前后的建站数据里，公众号 6 个号有 5 个是 `login_expired`（微信读书会话失效），要阿欢重新扫码。

## 2026-11-21 采集断更
- 末次数据提交 `6313e1e3`，末次发布 `b0ed26e1`（11/20 01:20 北京时间）。旧采集例程暂停后，v11 刷新只重建新版产物，#77 按预期拒绝旧站 `live.json` 过期的组合包。盒子和服务器日志仍待核对；生产未恢复。
- 恢复候选在[采集断更恢复方案](docs/rebang-v1/COLLECTION-RECOVERY.md)。用 `box_scrape.sh --no-publish` 先完成真实采集与持久化，再由 v11 一次发布；单一例程须用外层锁。候选经独立技术评审（已验源 Opus 5.5）有条件通过，条件为单写入/单发布、外层互斥和盒子生产验收，见方案。合并、部署、例程和任何服务器变更另批。
- 本机用隔离 Git 和假 HTTP 验证真实旧流水线：新数据写入 `live.json`，#77 发布器 dry-run 通过，旧包仍拒绝。macOS 不能验证现有旧站的连续原子替换（main 用 Linux `renameat2`）；Mac 接管另做。采集测试夹具路径用 `resolve()`，避免 macOS `/var` 和 `/private/var` 指向同一临时目录却比较失败。

## 2026-11-22 Telegram 媒体与博主页修复候选
- Telegram 旧流程只缓存图片和视频封面，未把视频地址交给页面。候选从同一轮 `tgmeta` 公开页提取图及视频，复用网页查看器；不增加服务器端抓取请求，不改 `tg.db`。公开样本 `freechinese/113503` 的 MP4 已在手机尺寸 Chromium 实际播放；`tnews365/35797` 两张图能在查看器打开。`freechinese/113505` 的频道页和单帖挂件都只给封面（`Media is too big`），页面明确引导去 Telegram，不能承诺站内播放这类视频。
- X 目前没有新原稿：正在使用的 Mac 发布克隆没有默认 `var/rebang/x-dump`，目前能找到的本机开发转储是 11 月 18 日，超过 36 小时。旧刷新脚本还会在默认目录为空时直接跳过 X（包括已指定 `REBANG_X_DUMP` 的情形）。候选始终调用既有适配器、区分缺失/过期并保留上次成功帖子；按生成时点隔离回放旧转储，网页能显示 13 位博主的 80 条历史帖子，不算恢复持续采集。下一步是让已有供稿方送来一份新鲜转储做只读验收；若要新账号、接口、付费服务或调整任务，先报再做。
- 博主页 Grok bot 的配置、入口、图标、成品转帖路径已移除；不动旧站专用来源、8:30 稿或「今日重点」同链接打标。博主页改版另开分支。
- `shiguang-hot-ios` 的 `HotWebSession` 加载同一个线上网页，已允许内联媒体。共享改动影响 App，但不需改原生代码；未做 iOS 真机验收。未合并、部署或操作 LaunchAgent。未来获批合并前先安排在同一发布锁下核对 `main`、`gh-pages`、数据库和 `HALT`，另行校准检查点并确认固定运行代码如何切换；不要手删保护标记。
- 验证：Python 3.11 全量 445 通过、2 跳过，另有 87 个子测试通过；前端 39 通过。macOS 的默认 Python 3.9 不满足发布器的 Python 3.11+ 要求（缺 `hashlib.file_digest`），首次全跑还有 Steam RDF 失败；切到隔离的 3.11 环境后均通过。全量浏览器测试会重写 `docs/rebang-v1/evidence/history-favorites-search/` 三张历史截图，验完不要把这些产物混入 PR。

## 下一步
1. 阿欢按采集恢复方案核对盒子/服务器证据，再逐项批准恢复。不另启第二个数据写入或发布任务。X dump 超过 36 小时博主栏会标「未更新」。
2. 旧推送停哪些由阿欢定（清单在 11/15 的上线报告里）。
3. 第二期剩下：① 阿欢扫码微信读书：`cd /workspace/shiguang-prod && /workspace/rebang-v1-briefs/tools/.venv-qr/bin/python -m rebang.bloggers.weread login --qr-png /tmp/weread-login-qr.png --wait 600`，把打印的 confirm_url / 二维码发给他，微信里确认；成功后下一轮刷新核对 5 个号的真回包。② YouTube 名单等阿欢确认后写进 `bloggers.json` 的 `youtube.accounts`（handle 用 UC 频道号）。③ 微博：已用副号 Cookie 接通（PR #69）。
4. GitHub Pages（https://kwinweng.github.io/shiguang-hot/ ）阿欢已批准关闭，但接口返回 422（`Deactivating GitHub pages for this repository is not allowed.`），站点仍是 200。需要阿欢在仓库 Settings → Pages 把发布源改为 None（只点 Unpublish 不够，下次 `publish_pages.sh` 推 gh-pages 会重新上线）。不要改或删 `gh-pages` 分支，news.kwinweng.com 靠它同步。

## 已定的决定
- 规划、编码、测试改由阿欢在 T3 Code 里派的 agent 执行（阿欢 11/21 14:47，取代 11/15 的仅 Grok 规则）；审批红绿灯不变，见 `AGENTS.md`。
- 一个来源只进一个频道，不按条拆；18 个 TG（去掉 reorx_share）；不做自动热点榜；YouTube、TG 评论楼/视频不在第一期（第二期已做评论楼和 YouTube 管道）；灵记快讯页 2026-11-16 砍掉（见 NOT-DOING）。
- 11/15 21:26 决定今日重点不进频道：当时放博主页 Grok bot。11/22 取消该平台分组，保留频道里同链接的条目只打「今日重点」标。
- 热搜：百度 + 知乎 + B 站，不要微博；每家独立、失败就空；放底栏「热搜」页，按北京日期归档 60 天（11/15 20:41 / 21:26）。
- 界面按 v10/v13 设计稿（深色杂志风、金色 #d6b36a、banner ≤5、底栏 频道/博主/热搜/收藏）；左右模式下横滑只换频道，收藏/分享靠长按（11/15 23:05）；收藏只存本机浏览器；英文先显示译文、标「机器翻译」。
- 8:30 私聊：3–5 条已上站内容，发阿欢和工头，没有新内容如实说。
- 新代码在 `rebang/`、`web-v11/`；旧 `shiguang/`、`web/`、`pipeline.py` 继续负责 TG 采集和旧站，行为不改。
- 新站归档（条目、热搜、翻译缓存、X dump、媒体）放在生产克隆的 `var/rebang/`，不进 git。

## 以后再说
- `public-feeds/` 最后一次数据提交是 `62a26398d`（2026-10-23 21:20 北京时间）。当天 `/workspace/tg-local/sync.sh` 改为调用 `publish_public.py --no-push`（改前备份 `sync.sh.bak-20261023-pause-push`），之后日志为 `public feeds prepared; no git mutation`。v11 直接读盒子上的原始成品目录，不受影响。
- 旧站回顾：盒子上未见调用 `tools/daily_summary.py` 的例程、cron 或近期日志。`site/history/` 由每次 `pipeline.py` 建站时的 `shiguang/site/news.py` 写入（摘要仍是 MOCK）；生产克隆没有仓库根目录的 `history/` 缓存。脚本还在，设计为 00:30 重跑前一天。
