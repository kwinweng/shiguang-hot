# 任务卡：feat/rebang-v1-frontend-v11（新版前端与构建）

- **可观察验收结果（从用户入口验证，先写这条再动手）**：手机尺寸打开新站首页：顶部日期/滑法/搜索，6 个频道可左右滑切换，每频道 banner ≤5 张，信息流卡片符合 v10；点开一条进整页正文，按返回回到原频道原滚动位置；滚到底出现「没有更多了」。截图与 v10 设计稿并排对照。
- worktree：`/workspace/rebang-v1-wt/frontend-v11`。
- 做什么：按 v10 设计（`/workspace/deliverables/daily-site/mocks/rebang-v10.html`，线上 daily-site-mocks.vercel.app/rebang-v10.html）做 6 频道静态站，读 `var/rebang/in/*.json`（无数据时读 `tests/fixtures/rebang/contract/`），构建到 `site-v11/`。
  - 深色杂志风、金色 `#d6b36a`；每频道顶部 ≤5 张大图 banner（只用有合适图的条目，不够就少）；信息流卡片：有图左小图 + 标题 + 3 行摘要 + 来源时间，无图标题 + 3 行摘要；无正文如实写。
  - 时事 banner 下放热搜模块（榜单样式，分家 tab，失败家显示「暂时取不到」）。
  - 左右换频道（默认）/ 上下看频道两种，顶栏图标切换；底栏：频道 / 博主 / 历史 / 收藏；顶部日期、滑法切换、搜索入口。
  - 点开整页正文（非弹窗），返回回到原栏/频道/滚动位置；无限加载到「没有更多了」；刷新按钮 + 下拉刷新（提示是最近一次发布的数据）；全局显示最近刷新时间（到分钟，北京时间）。
  - 译文优先、标「机器翻译」、可展开原文；博主栏真实推文卡片，未接通平台显示真实空状态。
  - 构建器 `python3 -m rebang.site --out site-v11`：合并去重、按频道分页（每页 30）、写 `data/meta.json`；调用 `rebang.archive.build(items, out_dir)`（history 分支提供；未合入时跳过）。
- 改哪些目录：`rebang/site/`、`web-v11/`（`web-v11/features/` 除外，那是 history 分支的）、`tests/test_rebang_site*.py`、`tests/rebang_site*.test.js`。
- 接口：在页面上预留挂载点 `#view-history`、`#view-favorites`、`#search-panel`，由 `web-v11/features/*.js` 挂载（约定见 history 任务卡）。
- 验收：`python3 -m rebang.site --out /tmp/site-v11` 用 fixture 与真实 `var/rebang/in` 都能构建；Playwright 在 393×852 与 1280 宽截图对照 v10；单测覆盖分页、banner 选图、无图卡片、热搜失败态、返回位置。
- 不许碰：旧 `web/`、`site/`、`shiguang/site/`、`pipeline.py`、发布脚本、gh-pages、域名。

## 执行结果（2026-11-15，Grok）

- 技术选择：纯静态、零依赖（无框架、无 npm 包），构建器只用 Python 标准库。理由：现有 `web/` 就是「一个脚本、无依赖」，v10 设计稿也是手写 CSS/JS；手势、banner、无限加载都从 v10 原样移植，不引第二套设计语言。
- 产物：`rebang/site/`（builder.py、`python3 -m rebang.site`）、`web-v11/`（index.html、app.css、lib.js、app.js）、测试 `tests/test_rebang_site.py`、`tests/test_rebang_site_browser.py`、`tests/rebang_site.test.js`、`tests/rebang_site_testdata.py`；证据 `docs/rebang-v1/evidence/frontend-v11/`（capture.py 可重跑）。
- 对接：深链 `#/item/<urlencoded id>`（冷启动和已打开页面都能直接开，经 `data/id-index.json` 找到后面页的条目）；`window.Rebang.register` + `_queue` 冲队列，挂载点 `#view-history`/`#view-favorites`/`#search-panel`，详情页收藏槽调 `attachButton`；构建调用 `rebang.archive.build`（未安装时记 skipped）；TG `image_local` 复制到 `media/`；`sources[]`/`platforms[]` 驱动「暂时取不到」与博主空状态、上次成功抓取日期。
- 与 v10 的偏差（待阿欢设计检查点确认）：上下模式每个频道先放 6 条，用「继续看「X」（还有 N 条）」按钮加载，不像 v10 那样自动无限加载——真实数据一个频道上千条，自动加载会把人困在第一个频道里。
- 设计检查点预览：`/workspace/rebang-v1-preview/make.sh` 用三个分支的真实输出 + history 的 features 拼成 `/workspace/rebang-v1-preview/site`（约 71M，其中 media 56M）。未部署；放到 daily-site-mocks 子路径需先批。
- 契约变更请求：见 `docs/rebang-v1/evidence/frontend-v11/README.md`。
