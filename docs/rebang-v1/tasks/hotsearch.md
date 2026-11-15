# 任务卡：feat/rebang-v1-hotsearch（时事热搜模块）

- **可观察验收结果（从用户入口验证，先写这条再动手）**：打开新站「时事」频道，banner 下能看到百度 / 知乎 / B 站三块真实热搜榜（带抓取时间）；把某一家接口改成不可达后重建，页面上该家显示「暂时取不到」，另外两家照常显示。
- worktree：`/workspace/rebang-v1-wt/hotsearch`。
- 做什么：按 `hotsearch.json` 做百度 / 知乎 / B 站三个独立适配器，汇总成 `rebang.hotsearch/1` 写 `var/rebang/in/hotsearch.json`。不要微博，不接第三方榜和公共 RSSHub。阿欢说过要改热搜但没说怎么改：保持「改配置 + 增删一个适配器文件」即可换家。
  - 百度 `top.baidu.com/api/board?tab=realtime`：标题、热度、链接、摘要、图、置顶。
  - 知乎 `api.zhihu.com/topstory/hot-lists/total?limit=50`：标题、热度文案、摘要、缩略图；链接转成 `https://www.zhihu.com/question/<id>`。
  - B 站 `api.bilibili.com/x/web-interface/wbi/search/square?limit=50`：热搜词，链接为站内搜索页；开始强制签名就失败空着，不做 wbi 破解。
  - 失败（超时/非 200/code≠0/结构变）→ 该家 `status=error`、items 空，记短错误码。请求带明确 UA、超时 ≤10s、每家每轮 1 次。
- 改哪些目录：`rebang/hotsearch/`（`providers/<id>.py` 一家一个）、`tests/test_rebang_hotsearch*.py`、`tests/fixtures/rebang/hotsearch/`（可从 `/workspace/deliverables/daily-site/research/hotsearch-probe-20261115/` 复制真实样本做 fixture）。
- 接口：`python3 -m rebang.hotsearch --out var/rebang/in/hotsearch.json [--fixtures DIR]`；`collect(now, http=None) -> dict`。
- 验收：单测覆盖三家正常样本、每家各自失败不影响别家、全失败输出合法空榜；`validate_hotsearch` 无错误；一次 `--live` 冒烟记录三家真实条数与状态。
- 不许碰：契约、其它分支目录、旧站、线上。
