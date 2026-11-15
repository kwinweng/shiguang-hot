# HANDOFF
（拾光热榜 v1 新版。旧交接记录已移到 `docs/HANDOFF-history.md`。）

## 目标
6 频道新版热榜（时事/环球/财经/科技与 AI/数码/工具与项目）按 `docs/rebang-v1/CONTRACT.md` 做完并新上线发布。验收 = 新版上线。

## 现在做到哪
- 2026-11-15 阶段 0：集成分支 `feat/rebang-v1`（基于 origin/main 8b5c6735e）写了数据契约 `rebang/contract/`。
- 6 个功能分支已于 11/15 晚合入 `feat/rebang-v1`（依次合并，实际是顺序做的，不是并行）：
  - sources-ingest（4d7969412）：18 TG + 6 官方订阅 + GitHub Trending + 4 个每日成品 → `rebang.items/1`；21:35 live 实抓 2584 条资讯；图片存本地 14 天。
  - hotsearch（4716f832b）：百度/知乎/B 站三家独立适配器；21:35 实抓 百度 51 / 知乎 30 / B 站 50，均 ok。
  - bloggers（730dd665f）：博客/Wechat2RSS/X（读 Grok 写的 X dump）适配器 + 可插拔翻译；实抓 151 条，英文 68/68 已译；即刻/微博/其余公众号未配置。
  - frontend-v11（25ab6022e）：`python3 -m rebang.site` 静态构建 + `web-v11/` 前端（两种滑法、banner、博主、整页正文、深链）。
  - history-favorites-search（04b3652f3）：归档增量、搜索索引、收藏/搜索模块（历史模块已按 21:26 改版删除）。
  - push-0830（cd1110730）：`python3 -m rebang.push --dry-run` 生成 8:30 今日重点私聊稿（只输出，不发送、不建定时）。
- 11/15 21:26 阿欢批的 5 处改版已做：底栏「历史」→「热搜」（当前三家 + 按北京日期的往日切换，`var/rebang/hotsearch-archive/` 每天留最后一份，保留 60 天；时事里不再放热搜；旧的按日期资讯历史页删除）；博主页新平台「Grok bot」（今日重点/推特爆款/环球要闻/GitHub 热门，离开主题频道）；每个频道和博主有「查看更多」整页（一直加载到「没有更多了」，返回回原位）；X/即刻/微博/知乎/公众号/Grok 官方图标本地化（`web-v11/icons/README.md` 记来源与许可）；英文标题和摘要全部机器翻译（缓存 → pending → `rebang.translate fill`，由 Grok 翻，只翻新增条目）。
- 集成测试（11/15 21:5x）：全量 pytest 354 过 / 1 失败（基线已知 `test_news_modules_browser` dark 子用例）；node 28/28；手机 390x844 从真实入口实测 30/30（`docs/rebang-v1/evidence/integration/capture.py`，截图同目录）。
- 设计检查点预览第 2 版：daily-site-mocks `/rebang-v12/`（构建脚本 `/workspace/rebang-v1-preview/make-v12.sh`；一次性快照，不自动更新）。
- 基线（未改动的 origin/main）：pytest 228 过 / 1 失败（同上 dark 子用例）；node 13/13。

## 下一步
1. 阿欢在手机上看 `/rebang-v12/`，确认 5 处改版；回答待定项（8:30 私聊条数 3–5 还是约 10 条）。
2. 定上线切换方案（新站产物放哪、gh-pages/news.kwinweng.com 怎么切、回退）+ 刷新例程（脚本每 30 分钟；X 抓取与翻译每 2 小时）→ 阿欢一次性单独批，批之前不建例程。
3. 上线后线上核实；再由阿欢定停旧推送、建 8:30 定时任务。
4. 第二期：即刻/微博/其余公众号接入（微博 Cookie 只放本机仅自己可读的文件，不进仓库）。

## 已定的决定
- 规划、评审、编码、测试全程只用 Grok（阿欢 11/15 指示与正式版 app-flow；覆盖 AGENTS.md 里「只有 Codex 写代码」），不启动 Magpie、Codex 或其他外部模型。
- HANDOFF.md 只在决定、可验证结果、阻塞或下一步变化时更新。
- 一个来源只进一个频道，不按条拆；18 个 TG（去掉 reorx_share）；不做自动热点榜；YouTube、TG 评论/视频、灵记快讯页不在第一期。
- 今日重点不进频道：放博主页 Grok bot，频道里同链接的条目只打「今日重点」标（11/15 21:26）。
- 热搜第一期：百度官方 JSON + 知乎 + B 站，不要微博；每家独立、失败就空；可替换；放底栏「热搜」页，按北京日期归档（11/15 20:41 / 21:26 确认）。
- 界面按 v10（深色杂志风、金色 #d6b36a、banner ≤5、底栏 频道/博主/热搜/收藏（11/15 21:26 历史→热搜））；收藏只存本机浏览器；英文先译文、标机器翻译。
- 新代码在 `rebang/`、`web-v11/`，产物 `var/rebang/`、`site-v11/`；旧 `shiguang/`、`web/`、`site/`、`pipeline.py` 与线上发布不动。
- 红灯须阿欢本人批：合并 main、部署/上线、改域名与 news 密码、停旧推送、花钱、部署 RSSHub、写微博密钥文件。

## 以后再说
- 仓库 `public-feeds/` 里推特爆款/环球要闻/GitHub 热门/今日重点最新只到 10-23，需查当前成品实际位置。
- `f2e9c04` 不在 GitHub 远端（只在交接方本地），以 main 上现有 `shiguang/ingest/telegram.py` 为复用基线。
- 新站归档（条目归档、热搜归档、翻译缓存）在生产中放哪（提交仓库 / gh-pages / 盒子本地）上线前定。
