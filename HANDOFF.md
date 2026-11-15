# HANDOFF
（拾光热榜 v1 新版。旧交接记录已移到 `docs/HANDOFF-history.md`。）

## 目标
6 频道新版热榜（时事/环球/财经/科技与 AI/数码/工具与项目）按 `docs/rebang-v1/CONTRACT.md` 做完并新上线发布。验收 = 新版上线。

## 现在做到哪
- 2026-11-15 阶段 0：集成分支 `feat/rebang-v1`（基于 origin/main 8b5c6735e）已写数据契约 `rebang/contract/` + 契约测试 20 项全绿。
- 6 个功能分支与 worktree 已建（`/workspace/rebang-v1-wt/<name>`），任务卡在 `docs/rebang-v1/tasks/`。
- history-favorites-search（`feat/rebang-v1-history-favorites-search`）：归档增量、搜索索引、历史/收藏/搜索模块已完成；手机尺寸实测通过，证据 `docs/rebang-v1/evidence/history-favorites-search/`。
- 基线（未改动的 origin/main）：pytest 228 过 / 1 失败（`test_news_modules_browser` 主题切换 dark 子用例，原样复现，非本次引入）；node 13/13；`NO_FETCH=1 python3 pipeline.py` 成功（6527 TG，0 feed，4 inbox）。

## 下一步
1. 做 6 个分支（目录互不重叠，可并行；实际是否并行以执行记录为准）：sources-ingest、hotsearch、bloggers、frontend-v11、history-favorites-search、push-0830（任务卡里有验收命令）。
2. 各分支验收后合回 `feat/rebang-v1`，跑全量测试 + 新站构建 + 手机截图。
3. 定上线切换方案（新站产物放哪、gh-pages/news.kwinweng.com 怎么切、回退）→ 阿欢单独批。
4. 上线后线上核实；再由阿欢定停旧推送、建 8:30 定时任务。

## 已定的决定
- 规划、评审、编码、测试全程只用 Grok（阿欢 11/15 指示与正式版 app-flow；覆盖 AGENTS.md 里「只有 Codex 写代码」），不启动 Magpie、Codex 或其他外部模型。
- HANDOFF.md 只在决定、可验证结果、阻塞或下一步变化时更新。
- 一个来源只进一个频道，不按条拆；18 个 TG（去掉 reorx_share）；不做自动热点榜；YouTube、TG 评论/视频、灵记快讯页不在第一期。
- 今日重点不单开栏：打 highlight 标或按其来源归频道（规则在 channels.json）。
- 热搜第一期：百度官方 JSON + 知乎 + B 站，不要微博；每家独立、失败就空；做成可替换（阿欢说要改，待他说怎么改）。
- 界面按 v10（深色杂志风、金色 #d6b36a、banner ≤5、底栏 频道/博主/历史/收藏）；收藏只存本机浏览器；英文先译文、标机器翻译。
- 新代码在 `rebang/`、`web-v11/`，产物 `var/rebang/`、`site-v11/`；旧 `shiguang/`、`web/`、`site/`、`pipeline.py` 与线上发布不动。
- 红灯须阿欢本人批：合并 main、部署/上线、改域名与 news 密码、停旧推送、花钱、部署 RSSHub、写微博密钥文件。

## 以后再说
- 热搜具体怎么改（等阿欢）。
- 仓库 `public-feeds/` 里推特爆款/环球要闻/GitHub 热门/今日重点最新只到 10-23，需查当前成品实际位置。
- `f2e9c04` 不在 GitHub 远端（只在交接方本地），以 main 上现有 `shiguang/ingest/telegram.py` 为复用基线。
- 新站历史归档在生产中放哪（提交仓库 / gh-pages / 盒子本地）上线前定。
