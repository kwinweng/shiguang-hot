# HANDOFF
（拾光热榜 v11。更早的交接记录在 `docs/HANDOFF-history.md`；v11 各模块开发记录已并入 `docs/rebang-v1/MODULES.md`。）

## 目标
6 频道新版热榜按 `docs/rebang-v1/CONTRACT.md` 上线并稳定刷新。

## 现在做到哪（2026-11-16）
- **已上线**：https://news.kwinweng.com/ 根路径就是 v11（11/16 00:08 阿欢决定）；`/rebang/` 301 到根；全站 noindex（页面 meta、`X-Robots-Tag`、`robots.txt`）。旧的登录阅读器、`/mail/`、`/archive/` 已下线。`shiguang-reader-update.timer` 已于 00:32 `disable --now`（实际原是每 5 分钟跑，不是每天一次）；灵记 `lingji-news-source` 只读的 `topics.sqlite3` 从此不再更新。发布链路、服务器配置、回退见 `docs/rebang-v1/OPERATIONS.md`。
- 合并记录：PR #40（v13 合入 main）、#41（TG 转发来源名）、#42（搜索索引加载竞态）、#44（public_base 改为根地址）、#45（文档审计）、#46（袋鼠图标）、#47（去掉顶栏袋鼠，日期回到最左边）。标签页、加到主屏、启动图和分享图仍是袋鼠；顶栏只有日期，没有 logo。
- 线上验收（11/16 00:20 左右）：Playwright 390x844 真触摸 76/76（`docs/rebang-v1/evidence/integration-v13/capture.py`）；数据、媒体、脚本 200；深链 `https://news.kwinweng.com/#/item/<id>` 冷启动直达详情，旧 `/rebang/#/item/<id>` 跳转后同样可用。图标改动后复查 75/76，剩下的失败是部分英文新闻尚未翻译，与图标无关。
- 刷新：`tools/rebang_refresh.sh` 已在 main，**还没有定时运行**（盒子没有 cron，定时都靠 bot 例程）。旧站采集 `tools/box_scrape.sh` 仍由工头「热榜抓取发布」例程按 :07/:37 跑，继续写 `tg.db`、发布 gh-pages；它发布时会顺带把当时的 `site-v11/` 一起发出去，但不会重建 v11。
- 例程草稿（未创建，在盒子 `/workspace/rebang-v1-briefs/`）：`routine-x-translate.md`（每 2 小时 X 博主 + 翻译）、`routine-0830.md`（8:30 私聊 3–5 条）。

## 下一步
1. 阿欢批准后：在工头「热榜抓取发布」例程里 `box_scrape.sh` 之后加 `sh tools/rebang_refresh.sh`；由工头建 X+翻译例程和 8:30 例程。X dump 超过 36 小时博主栏会标「未更新」。
2. 旧推送停哪些由阿欢定（清单在 11/15 的上线报告里）。
3. 第二期：即刻（自建 RSSHub，另批）、微博（weibo-crawler，Cookie 文件另批）、其余 5 个公众号（微信读书扫码）。
4. GitHub Pages（https://kwinweng.github.io/shiguang-hot/ ）阿欢已批准关闭，但接口返回 422（`Deactivating GitHub pages for this repository is not allowed.`），站点仍是 200。需要阿欢在仓库 Settings → Pages 把发布源改为 None（只点 Unpublish 不够，下次 `publish_pages.sh` 推 gh-pages 会重新上线）。不要改或删 `gh-pages` 分支，news.kwinweng.com 靠它同步。

## 已定的决定
- 规划、评审、编码、测试全程只用 Grok（阿欢 11/15）；见 `AGENTS.md`。
- 一个来源只进一个频道，不按条拆；18 个 TG（去掉 reorx_share）；不做自动热点榜；YouTube、TG 评论楼/视频、灵记快讯页不在第一期。
- 今日重点不进频道：放博主页 Grok bot，频道里同链接的条目只打「今日重点」标（11/15 21:26）。
- 热搜：百度 + 知乎 + B 站，不要微博；每家独立、失败就空；放底栏「热搜」页，按北京日期归档 60 天（11/15 20:41 / 21:26）。
- 界面按 v10/v13 设计稿（深色杂志风、金色 #d6b36a、banner ≤5、底栏 频道/博主/热搜/收藏）；左右模式下横滑只换频道，收藏/分享靠长按（11/15 23:05）；收藏只存本机浏览器；英文先显示译文、标「机器翻译」。
- 8:30 私聊：3–5 条已上站内容，发阿欢和工头，没有新内容如实说。
- 新代码在 `rebang/`、`web-v11/`；旧 `shiguang/`、`web/`、`pipeline.py` 继续负责 TG 采集和旧站，行为不改。
- 新站归档（条目、热搜、翻译缓存、X dump、媒体）放在生产克隆的 `var/rebang/`，不进 git。

## 以后再说
- `public-feeds/` 最后一次数据提交是 `62a26398d`（2026-10-23 21:20 北京时间）。当天 `/workspace/tg-local/sync.sh` 改为调用 `publish_public.py --no-push`（改前备份 `sync.sh.bak-20261023-pause-push`），之后日志为 `public feeds prepared; no git mutation`。v11 直接读盒子上的原始成品目录，不受影响。
- 旧站回顾：盒子上未见调用 `tools/daily_summary.py` 的例程、cron 或近期日志。`site/history/` 由每次 `pipeline.py` 建站时的 `shiguang/site/news.py` 写入（摘要仍是 MOCK）；生产克隆没有仓库根目录的 `history/` 缓存。脚本还在，设计为 00:30 重跑前一天。
