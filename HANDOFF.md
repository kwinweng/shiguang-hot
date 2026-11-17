# HANDOFF
（拾光热榜 v11。更早的交接记录在 `docs/HANDOFF-history.md`；v11 各模块开发记录已并入 `docs/rebang-v1/MODULES.md`。）

## 目标
6 频道新版热榜按 `docs/rebang-v1/CONTRACT.md` 上线并稳定刷新。

## 最新交接（2026-11-17，北京时间）

以下为当前状态；下面 11/16 的运行节奏、视觉和待办只作历史参考。

- **PR #73**（`290f744d`，11/16 23:48）：频道、博主各为连续长流；段间「下一个：X」，最后「内容已结束」；去掉全部「查看更多」。收藏、热搜只在各自页面无限下拉。
- **PR #74**（`f312142d`，11/17 01:28）：v16 视觉参考少数派，红色强调、白底、细分隔线、毛玻璃底栏，缩略图在右，X 头像无红边；热搜只叫百度/知乎/B站，日期用「今天」，顶栏无 logo，暗色跟随系统。旧 v10/v13 金色方向已被取代；实际令牌见 `web-v11/app.css`。
- **PR #75**（`f060942a`，11/17 10:01）：FREE 中文、双语新闻从环球移到时事。时事为竹新社、我的一张大字报、FREE 中文、双语新闻；环球为 BBC World、卫报 World。来源只归属一个频道，以 `rebang/contract/channels.json` 为准。
- **已定交互**：收藏、分享均长按卡片；横滑只切频道；图片可全屏、多图横滑；详情保留互动数、热门回复、TG 评论楼、X 引用卡片。
- **接管顺序与授权**：阿欢要求当前会话在 Mac 接管；先手动刷新并发布，线上核实成功后回报，再由阿欢通知旧机器停刷新循环和例程；旧任务停止确认前不启用新定时任务。目标为普通刷新、X+翻译各每 30 分钟。**08:30 私聊已由阿欢在 11/17 后续交接中取消，本机不创建；旧例程由阿欢在切换时暂停。** 站内今日重点整理来源保留。不要把这项授权扩大成任意代码合并或其他部署。

### 本机准备与阻塞

- 已同步 `origin/main`（准备开始时 `296c8a14`），GitHub CLI 已登录；尚未实测 gh-pages 推送。两个交接包均通过 `SHA256SUMS` 校验，运行缓存恢复到 `var/rebang/`，运行说明包仅隔离提取两份例程、翻译脚本和旧刷新循环；不复用 Linux 包里的虚拟环境或软链接。
- Mac 使用 `var/rebang/venv/bin/python`（Python 3.13），已安装现有运行依赖 beautifulsoup4、Pillow，以及验证/扫码所需 pytest、segno；安装 Homebrew `flock`。脚本运行需 `BOX_PYTHON="$PWD/var/rebang/venv/bin/python"`，PATH 需含 `/opt/homebrew/bin`。旧站已以 `NO_FETCH=1 SITE_MODE=public MAIL_DIGEST=0` 构建，并写出 `site/build-info.json`；没有运行会更新 `tg.db`、提交和发布的 `box_scrape.sh`。
- 现有契约、站点、博主、今日重点测试 **105 passed**。首次真实刷新仅跑 `--no-publish`；第一次因 T3 重启在 tgmeta 阶段终止，核实无残留进程后重跑。重跑于 **11/17 23:08:16–23:13:36** 完成，tgmeta、三家热搜、bloggers、ingest、build 均返回成功，`var/rebang/logs/last-refresh.json` 的 `failed` 为空，但语义检查发现四份整理输入全部为空，见下条。新站为真实数据（`fixture:false`），2573 条新闻、460 条博主帖子，不能以此覆盖线上完整内容。
- **本地发布打包通过，未推送**：`publish_pages.sh --already-built --dry-run` 打包 1700 个文件，包含 `rebang/`。媒体重定位后 23:14:53 重建，1095 个站内媒体 URL 全部有对应文件，无缺失；`rebang.push --dry-run` 出 5 条根地址深链，仅出稿、未发送（其中新英文条目仍待翻译）。准备阶段浏览器读到的线上 `built_at` 为 11/17 22:49:19，2577 条新闻、1027 条帖子，meta + X-Robots-Tag + robots.txt 均保留 noindex。这是旧机器版本，**不是本机发布验收；未发布、未创建新定时任务，不应通知旧机器停止**。
- **四份整理输入已补交并恢复**：最初缓存包仅有合并后的数据，首次 ingest 会丢掉 562 条整理帖子。阿欢随后交付 `rebang-digests-20261117.tar.gz`（23:24 快照），已校验 SHA256 并恢复到 `var/rebang/digests/20261117T2324/`。通过现有四个目录环境变量真实 ingest，world 173、x 138、hot-daily 118、github 133，共 **562 条全部恢复**。`HOT-DAILY_FEED_DIR` 名称含连字符，用 `env` 或 subprocess env 字典传入；不需要改适配器或 `sources.json`。原始资料仍由原「资讯」bot 每日生产，持续只读接收方式尚未落地，不能把今晚快照当成同步完成，见 `OPERATIONS.md`。
- **媒体迁移已验证**：包内 522 处本地媒体引用使用 `/workspace/shiguang-prod/...` 绝对路径；另有 699 处 TG 图片引用指向根目录 `media/`，这个目录不在 state 包内。已从现有 `origin/gh-pages` 的 `rebang/media/` 恢复缺少的公开图片（不改远端发布物）。原缓存 1221 处引用均能找到对应文件；刷新后的 bloggers 输入中仍有 517 处旧绝对路径，已仅对这些路径重定位到本机，修改前备份位于 `var/rebang/local-ops/before-media-relocation-20261117T231453/`。最终建站核对 1095 个站内媒体 URL，无缺失。后续再次恢复原包时仍需重定位，不能只看构建退出码。
- **登录与权限**：微信读书已由阿欢扫码登录，`weread status` 实测 `session:true, valid:true`，会话权限 `0600`。列表接口回 `-2041`，沿用现有 cover + 正文回退；首轮正文读取不稳定，复核时乱翻书、caoz 各抓到 1 条，夕小瑶公共源抓到 10 条；MacTalk、独立开发变现周刊、王建硕保留原快照各 1 条，未把缓存说成新抓取。恢复缓存时保留原 id 和时间，并修复 3 处旧媒体路径、补回 3 张原包图片。DeepSeek 密钥已由阿欢通过安全输入提供，仅传给翻译运行进程；23:38 实测 `deepseek-flash`（关闭思考）39/39 段成功、失败 0、pending 0，5 次请求、4182/2879 prompt/completion tokens。后续定时安全注入尚未配置。微博副号 Cookie 文件仍未到位，阿欢可直接拷到本机 `~/.config/rebang/weibo-cookie.txt`（0600），不经聊天；X API v2 新读取仍缺权限，不能转用旧 bot 的专有工具或擅自办理付费套餐。目前 X 仅读取已迁移的 dump。08:30 私聊已取消，无需投递渠道。凭据不查看、不打印、不提交。
- **Mac 连续建站兼容修复（待合并）**：旧站首次构建正常，目标 `site/` 已存在时 Linux 专用 `renameat2` 在 macOS 报 `symbol not found`。`shiguang/site/build.py` 已对 Darwin 使用系统 `renamex_np(RENAME_SWAP)`，Linux 保持 `renameat2(RENAME_EXCHANGE)`，两者均保留整树原子交换与失败不替换的契约。Mac 上 4 项既有原子构建回归通过；真实旧站连续重建两次成功，相关测试合计 **109 passed**。没有改成先删旧目录，也没有改变服务器发布方式。
- **TG 采集不能遗漏**：`rebang_refresh.sh` 的 ingest 只读 `tg.db`，tgmeta 只补公开元数据。新定时运行还需保留真正更新 `tg.db` 的既有采集步骤。`box_scrape.sh` 要求 `main` 且工作区干净，不能在有用户未跟踪文件的开发目录里强行运行或清理；旧机器仍写库时也不要启动第二个数据提交者。

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

## 下一步
1. 阿欢批准后：在工头「热榜抓取发布」例程里 `box_scrape.sh` 之后加 `sh tools/rebang_refresh.sh`（让 TG/热搜 30 分钟更新一次；现在 v11 只随 2 小时一次的 X+翻译例程发布）。X dump 超过 36 小时博主栏会标「未更新」。
2. 旧推送停哪些由阿欢定（清单在 11/15 的上线报告里）。
3. 第二期剩下：① 阿欢扫码微信读书：`cd /workspace/shiguang-prod && /workspace/rebang-v1-briefs/tools/.venv-qr/bin/python -m rebang.bloggers.weread login --qr-png /tmp/weread-login-qr.png --wait 600`，把打印的 confirm_url / 二维码发给他，微信里确认；成功后下一轮刷新核对 5 个号的真回包。② YouTube 名单等阿欢确认后写进 `bloggers.json` 的 `youtube.accounts`（handle 用 UC 频道号）。③ 微博：已用副号 Cookie 接通（PR #69）。
4. GitHub Pages（https://kwinweng.github.io/shiguang-hot/ ）阿欢已批准关闭，但接口返回 422（`Deactivating GitHub pages for this repository is not allowed.`），站点仍是 200。需要阿欢在仓库 Settings → Pages 把发布源改为 None（只点 Unpublish 不够，下次 `publish_pages.sh` 推 gh-pages 会重新上线）。不要改或删 `gh-pages` 分支，news.kwinweng.com 靠它同步。

## 已定的决定
- 规划、评审、编码、测试全程只用 Grok（阿欢 11/15）；见 `AGENTS.md`。
- 一个来源只进一个频道，不按条拆；18 个 TG（去掉 reorx_share）；不做自动热点榜；YouTube、TG 评论楼/视频不在第一期（第二期已做评论楼和 YouTube 管道）；灵记快讯页 2026-11-16 砍掉（见 NOT-DOING）。
- 今日重点不进频道：放博主页 Grok bot，频道里同链接的条目只打「今日重点」标（11/15 21:26）。
- 热搜：百度 + 知乎 + B 站，不要微博；每家独立、失败就空；放底栏「热搜」页，按北京日期归档 60 天（11/15 20:41 / 21:26）。
- 界面按 v10/v13 设计稿（深色杂志风、金色 #d6b36a、banner ≤5、底栏 频道/博主/热搜/收藏）；左右模式下横滑只换频道，收藏/分享靠长按（11/15 23:05）；收藏只存本机浏览器；英文先显示译文、标「机器翻译」。
- 8:30 私聊：3–5 条已上站内容，发阿欢和工头，没有新内容如实说。
- 新代码在 `rebang/`、`web-v11/`；旧 `shiguang/`、`web/`、`pipeline.py` 继续负责 TG 采集和旧站，行为不改。
- 新站归档（条目、热搜、翻译缓存、X dump、媒体）放在生产克隆的 `var/rebang/`，不进 git。

## 以后再说
- `public-feeds/` 最后一次数据提交是 `62a26398d`（2026-10-23 21:20 北京时间）。当天 `/workspace/tg-local/sync.sh` 改为调用 `publish_public.py --no-push`（改前备份 `sync.sh.bak-20261023-pause-push`），之后日志为 `public feeds prepared; no git mutation`。v11 直接读盒子上的原始成品目录，不受影响。
- 旧站回顾：盒子上未见调用 `tools/daily_summary.py` 的例程、cron 或近期日志。`site/history/` 由每次 `pipeline.py` 建站时的 `shiguang/site/news.py` 写入（摘要仍是 MOCK）；生产克隆没有仓库根目录的 `history/` 缓存。脚本还在，设计为 00:30 重跑前一天。
