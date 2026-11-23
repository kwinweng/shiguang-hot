# HANDOFF
（拾光资讯 v11。更早的交接记录在 `docs/HANDOFF-history.md`；v11 各模块开发记录已并入 `docs/rebang-v1/MODULES.md`。）

## 目标
6 频道资讯站按 `docs/rebang-v1/CONTRACT.md` 稳定刷新；按 11/23 定的串行计划逐步改进。

## 现在做到哪（2026-11-24）
- **线上**：https://news.kwinweng.com/ ，每小时 :10 左右由「Shiguang publisher」用 `origin/main` 最新代码建站发布（gh-pages `build-info.json` 的 `source_commit` 即线上代码版本）。11/23 23:10 一版：新闻 2471 条、博主内容 293 条。
- **采集缺口（11/23 23:10）**：X 16 个博主 0 条（没收到原始转储）；微博 6 个 0 条（疑似 Cookie 失效）；公众号 6 个只有「夕小瑶科技说」有内容（其余 5 个等微信读书扫码）。即刻、YouTube、博客、6 个新闻频道正常。
- **第 0 步**（`chore/t3-handover-rules`）：规则改为 T3 Code 接手、测试通过直接合并上线（见 `AGENTS.md`、`DECISIONS.md` 11/23）；合并积压的 #76（Mac 接管运行、Mac 原子建站、公众号正文失败不再误报成功、仓库内翻译脚本）和 #78（对外名统一为「拾光资讯」）。旧交接内容移到 `docs/HANDOFF-history.md`。
- **测试环境**：全量测试需 Python 3.11+，装 pytest、beautifulsoup4、lxml、Pillow、segno、playwright（含 chromium）。缺 lxml 时 `test_rebang_extract` 会失败，缺浏览器时 `test_rebang_site_browser` 全部报错，都不是代码问题。全量浏览器测试会改写 `docs/rebang-v1/evidence/history-favorites-search/` 三张截图，验完还原，不要提交。`test_news_browser` 的胶囊时钟用例偶发失败，重跑即过。

## 串行计划（阿欢 11/23 确认；一步一分支，合并并核验线上后再开下一步）
0. `chore/t3-handover-rules`：规则、两个积压 PR。
1. `feat/source-health-monitor`：统一来源健康表（各新闻频道、博主平台的最后成功时间、条数、状态、失败原因）；早上提醒里带出断更/异常来源。
2. `fix/blogger-collection-recovery`：查清并恢复 X 原有转储供稿；微博新 Cookie、微信读书扫码时停下来请阿欢操作，验证真回包后合并。
3. `chore/source-audit-archive`：盘点 `sources.json`、`trial-sources.json`、`rebang/contract/*.json` 与旧站代码（TG 采集仍靠 `pipeline.py`/`shiguang/`，先迁移再归档），出「在用 / 归档 / 删除」清单和「环球」等薄弱频道的免登录来源建议。**清单先给阿欢过目再执行。**
4. `feat/blogger-twitter-feed`：博主页改成推特/微博手机版式信息流 + 个人用户流。**先做样页给阿欢确认。**
5. `feat/dedup-and-auto-highlights`：跨来源去重、同类事件合并（主条 + 折叠同源）；「今日重点」自动打分（多源交叉、来源权重、时效），只做筛选不做热点排行。**先确认打分偏好。**

## 其他待办
1. GitHub Pages（https://kwinweng.github.io/shiguang-hot/ ）阿欢已批准关闭，但接口返回 422，需要阿欢在仓库 Settings → Pages 把发布源改为 None。不要改或删 `gh-pages` 分支，news.kwinweng.com 靠它同步。
2. 采集断更恢复方案见 `docs/rebang-v1/COLLECTION-RECOVERY.md`（11/21）；11/22 晚起每小时数据提交与发布已恢复，执行主机待第 2 步一并查清。

## 已定的决定
- 开发、合并、上线由 T3 Code 接手，非高风险改动测试通过即合并上线再汇报（阿欢 11/23 破例，取代 11/15 仅 Grok、11/17 逐次批准）；见 `AGENTS.md`、`DECISIONS.md`。
- 一个来源只进一个频道，不按条拆；18 个 TG（去掉 reorx_share）；不做自动热点榜；YouTube、TG 评论楼/视频不在第一期（第二期已做评论楼和 YouTube 管道）；灵记快讯页 2026-11-16 砍掉（见 NOT-DOING）。
- 11/15 21:26 决定今日重点不进频道：当时放博主页 Grok bot。11/22 取消该平台分组，保留频道里同链接的条目只打「今日重点」标。
- 热搜：百度 + 知乎 + B 站，不要微博；每家独立、失败就空；放底栏「热搜」页，按北京日期归档 60 天（11/15 20:41 / 21:26）。
- 界面现为 v16 视觉（PR #74，白底红色强调，令牌见 `web-v11/app.css`；底栏 频道/博主/热搜/收藏）；左右模式下横滑只换频道，收藏/分享靠长按（11/15 23:05）；收藏只存本机浏览器；英文先显示译文、标「机器翻译」。
- 8:30 私聊：11/17 阿欢说「不做了」（见 NOT-DOING）；11/23 确认的计划里要「谁断更早上直接提醒你」，第 1 步开工时先确认提醒走哪个渠道。
- 新代码在 `rebang/`、`web-v11/`；旧 `shiguang/`、`web/`、`pipeline.py` 继续负责 TG 采集和旧站，行为不改。
- 新站归档（条目、热搜、翻译缓存、X dump、媒体）放在生产克隆的 `var/rebang/`，不进 git。

## 以后再说
- `public-feeds/` 最后一次数据提交是 `62a26398d`（2026-10-23 21:20 北京时间）。当天 `/workspace/tg-local/sync.sh` 改为调用 `publish_public.py --no-push`（改前备份 `sync.sh.bak-20261023-pause-push`），之后日志为 `public feeds prepared; no git mutation`。v11 直接读盒子上的原始成品目录，不受影响。
- 旧站回顾：盒子上未见调用 `tools/daily_summary.py` 的例程、cron 或近期日志。`site/history/` 由每次 `pipeline.py` 建站时的 `shiguang/site/news.py` 写入（摘要仍是 MOCK）；生产克隆没有仓库根目录的 `history/` 缓存。脚本还在，设计为 00:30 重跑前一天。
