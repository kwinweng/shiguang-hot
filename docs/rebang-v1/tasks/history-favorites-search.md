# 任务卡：feat/rebang-v1-history-favorites-search（历史 / 收藏 / 搜索）

- **可观察验收结果（从用户入口验证，先写这条再动手）**：手机尺寸打开新站：在详情页点收藏后到底栏「收藏」能看到、刷新页面仍在；底栏「历史」能按北京日期翻到前一天的真实条目，空日期有说明；顶部搜索一个已上站标题的关键词能搜到该条。
- worktree：`/workspace/rebang-v1-wt/history-favorites-search`。
- 做什么：
  - 归档：`rebang/archive/`：`build(items, out_dir)` 把条目按北京日期合并进 `var/rebang/archive/YYYY-MM-DD.json`（按 id 去重，保留首次与最新版本），并输出 `site-v11/data/history/index.json`（有内容的日期与条数）+ `history/<date>.json`；空日期说清「这天没有内容」。
  - 搜索索引：`site-v11/data/search-index.json`，只含已上站的标题、摘要、来源名、推文译文和原文；不写 AI 摘要。
  - 前端功能：`web-v11/features/history.js`（按日期翻）、`favorites.js`（localStorage，只在详情页有收藏按钮，键为条目 id，注明换设备会消失）、`search.js`（顶部搜索，纯前端匹配）。挂到 frontend 预留的 `#view-history`、`#view-favorites`、`#search-panel`；通过 `window.Rebang.register(name, mount)` 约定接入（frontend 提供 register，未合入前用测试桩）。
- 改哪些目录：`rebang/archive/`、`web-v11/features/`、`tests/test_rebang_archive*.py`、`tests/rebang_features*.test.js`。
- 验收：单测覆盖跨日（北京时间 00:00 边界）、重复 id、空日期、索引不含未上站条目；node 测试覆盖收藏增删持久化、搜索中英文与译文命中；与 frontend 合并后 Playwright 走一遍历史/收藏/搜索。
- 不许碰：契约、frontend 其它文件、旧站、线上。
