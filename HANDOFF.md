# HANDOFF
（拾光热榜 v11。更早的交接记录在 `docs/HANDOFF-history.md`；v11 各模块开发记录已并入 `docs/rebang-v1/MODULES.md`。）

## 目标
6 频道新版热榜按 `docs/rebang-v1/CONTRACT.md` 上线并稳定刷新。

## 现在做到哪（2026-11-16）
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
- 规划、评审、编码、测试全程只用 Grok（阿欢 11/15）；见 `AGENTS.md`。
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
