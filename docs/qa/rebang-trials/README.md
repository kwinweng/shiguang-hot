# 热榜试跑源实现与验收

依据：`docs/specs/2026-10-22-rebang-trial-sources.md`。第 11 节全部采用建议答案。
文字卡使用 `/workspace/shiguang-rebang/design/textcard-tokens.md` 的正式变量与 regular Phosphor 图标；观星为 `moon-stars`。

## 修改文件

- `shiguang/ingest/trial.py`：保留活动详情和 App Store 链接；重抓刷新字段，保留首次抓取时间及新增计数。
- `shiguang/site/trials.py`：只读试跑表、13 源白名单、来源筛选、标题清洗、日期解析、过期过滤、去重、排序和栏目卡片。
- `shiguang/site/pages.py`：好玩、好买列表与今日首页最近 7 天各 5 条。
- `shiguang/site/render.py`：导航入口、页面主题和栏目导航选中状态。
- `shiguang/site/icons.py`：内联 Phosphor core 2.1.1 图标，分类使用 regular；沿用现有 MIT 许可文件。
- `shiguang/site/history.py`：统一 Phosphor 图标入口，并将图标实现计入归档兼容性摘要。
- `web/app.js`：分类筛选、ARIA 状态、图片错误降级和按高度排列的双列瀑布流。
- `web/style.css`：正式亮暗色板、4:3 文字卡、红色主色和响应式样式。
- `tests/test_trial_publication.py`：清洗、去重、日期、来源准入、无图、未知分类、首页、只读和首次抓取时间测试。
- `tests/test_trial_browser.py`：402×874 亮暗主题、筛选、图片 404、ARIA、无溢出及无脚本错误测试。
- `tests/trial_cards.test.js`：直接执行页面筛选和图片错误处理代码。
- `tests/test_trial.py`、`tests/test_feeds.py`：将旧版“不公开试跑源”和旧导航断言更新为新产品行为。
- `tools/verify_trial_publication.py`：离线真实产物截图与桌面宽度检查。
- 本目录 `README.md` 与六张 PNG：验收记录和截图。

## 验证结果

- `GIT_CONFIG_GLOBAL=/dev/null python3 -m unittest discover tests`：155 项通过，包括公开隐私检查和实际 Chromium 测试，无跳过。
- `node tests/*.test.js`：通过。该写法由 Node 只执行展开后的第一个脚本，因此另跑 `node --test tests/*.test.js`：全部 7 项通过。
- `tools/validate_feed.py`：24 份已有公开 feed 全部通过。
- `tools/trial_report.py --output /tmp/rebang-trial-report`：通过，原始数据仍为 13 源共 298 条。
- `NO_FETCH=1 SITE_MODE=public MAIL_DIGEST=0 SITE_OUT=/tmp/rebang-site python3 pipeline.py`：完整离线公开构建通过。
- 截图工具检查：好玩 166 条、好买 89 条、首页各 5 条；亮暗模式均无水平溢出及脚本错误，1440×900 桌面检查通过。
- 实库抽查：公开 255 条，无规范化 URL 重复，无“标签：”标题；UCCA 展期显示 `展期 7/14–1/31`。
- 13 个源均已启用。当前 Apps_Share 的 21 条标签摘要无法恢复 App 名，另 1 条为互推；均被过滤。Steam 保留 1 条新品，过滤 19 条无图更新；小众软件过滤 2 条促销。

## 截图

| 页面 | 亮色 | 暗色 |
| --- | --- | --- |
| 好玩 | [play-light.png](play-light.png) | [play-dark.png](play-dark.png) |
| 好买 | [buy-light.png](buy-light.png) | [buy-dark.png](buy-dark.png) |
| 今日 | [index-light.png](index-light.png) | [index-dark.png](index-dark.png) |

## 与 Spec 的差异和验证限制

- 按本次明确要求，以正式设计变量替代第 13 节占位色；文字卡采用设计稿 4:3 比例、标题和 meta 位于卡片下方。
- 额外过滤 Apps_Share 的互推广告，避免把频道推广作为软件条目展示。
- 截图在断网路由中完成，远程封面统一返回 404，验证降级路径；没有验证真实源站图片的在线可达性。
- Browser 插件不可用，使用仓库已有 Playwright 和 Chromium；未安装依赖。
- 截图保存在工作区；依照本次约束，不创建远程 PR、不 push、不部署。

## 提交限制

已尝试 `git add` 并准备使用中文提交信息 `feat: 上线好玩好买试跑源及分类文字卡`。
工作区对应的 Git 元数据在只读路径 `/workspace/pi-work/shiguang-spec-1/.git/worktrees/shiguang-impl-1`。
Git 无法创建 `index.lock`，返回 `Read-only file system`；因此暂存与提交均未完成，修改全部保留在工作区。

未改数据库 schema、npm 依赖、GitHub Actions 或部署配置；未读取 `.env` 或 secrets。
