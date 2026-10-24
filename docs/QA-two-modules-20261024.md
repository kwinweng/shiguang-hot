# 热榜两模块本地验收

实现依据：`docs/spec/SPEC-two-modules-20261024.md` 和 two-modules 定稿原型；`docs/PLAN.md` 保持工头版本。

## 改动

- 默认资讯·实时；资讯增加热点、回顾，探索分好玩、好看、好买，我的收纳收藏、设置、关于。
- 热点读取现有日报全部条目，以北京时间 22:00 切换日期；原地展开摘要与来源，不使用回顾样例事件替代日报。
- 回顾使用前后日期、昨天、今天、横滑日期条；今天未生成显示「00:30 后生成」。
- 六标签下拉刷新均使用 `fetch` 的 `cache: 'no-store'`，按新增稳定 ID 去重计数。仅重读已发布文档。
- C 行布局、无图详情、图片失败移除图位、骨架、空态、重试、离线缓存提示、404 返回资讯。
- 保留公开/私有收藏存储隔离，旧收藏仍能从我的打开；主题设置持久化。
- Logo D 替换 favicon、Apple Touch、应用图标和 manifest；`python3 tools/build_icons.py` 可重生成位图。
- 并入 `origin/feat/floating-bar` 的悬浮栏、安全区、当前页点击判断，按新 Spec 改成三格。Supersedes #29；未操作 PR #29。

## 检查

- `python3 -m pytest -q`：192 passed，58 subtests passed。
- `node tests/test_news_query.cjs`：4 passed，覆盖默认标签、22:00 前后及跨年、刷新新增计数、404 文案。
- `node --test tests/news_modules.test.js`：3 passed，保留分类与转义合同。
- `NO_FETCH=1 python3 pipeline.py`：成功，使用本地数据生成 2346 TG、0 feed、4 inbox sources。
- `git diff --check`：通过。
- 构建后检查全站 HTML 可见文本：无「今日实时」「今日重点」「往日回顾」。旧来源名称仅在展示层映射，不改输入配置和采集数据。
- 全量检查期间，既有定时工具测试曾出现一次 Git 索引字节快照差异；未改相关代码，单项重跑 1 passed / 8 subtests passed，随后全量 192 passed / 58 subtests passed。
- 现有 Playwright 浏览器测试覆盖六标签实际刷新请求、收藏兼容、热点全部条目与展开、日期条、无图详情、错误重试、离线缓存、404、主题持久化。

## 手机截图

运行 `python3 tools/check_two_modules.py` 生成 [24 张亮暗截图及布局记录](qa/two-modules-20261024/checks.json)，视口 393×852。资讯三个标签、探索三个标签、我的、收藏、设置、无图详情、关于、404 均无横向溢出，底栏高70px，浏览器无页面异常。

与原型 shots 对照：采用三格玻璃悬浮栏、64px 分类列、76×76 缩略图和两行文字层级；按 Spec，页面标题与导航使用400，只有详情24px标题使用600。截图不模拟原型的系统状态栏与 Home Indicator。当前公开数据没有匹配探索分类的条目，探索展示空态；分类、图片及无图详情由离线浏览器输入验证，没有引入原型虚构内容。

未改抓取、数据管线、定时任务或部署配置；未添加依赖，未 push、未开 PR。
