# 拾光热榜视觉系统

状态：2026-10-20 Playground 首轮实现，**待阿欢视觉评审**。已确认的产品 Spec 不等于视觉效果已验收。本轮不整合正式业务页面。

## 入口与交付

```sh
python3 tools/design_preview.py --host 0.0.0.0 --port 8766
```

开发路由 `/design/`，默认进入 Screens，支持 `#screens/today`、`#screens/look`、`#screens/play`、`#screens/buy`、`#screens/saved`，以及 `#foundations`、`#components`、`#patterns`。Screens 的“全屏体验五页”使用 `?focus=1#screens/...`，隐藏评审外壳；手机浏览器可直接以393×852体验五页，浏览器返回即回到视觉系统。

独立生成（由 bot 取产物，不由 Codex 部署）：

```sh
python3 tools/design_preview.py --build-only --standalone --output /tmp/shiguang-design-review
```

输出 `/tmp/shiguang-design-review/design/` 供 bot 按既有流程放入 owner-only tailnet 预览站的 `/design/`。附带 `design/standalone.html` 可下载后离线打开，全部样例和资源内嵌，无需启动服务。部署配置、生产构建和正式导航均不改。此工具不负责认证或部署，开发端口只用于受控环境。

源码、生产站输出和数据库不由预览服务提供；不在该脚本中调用生产 pipeline，不生成公开站页面。自动刷新未做：修改 Python/样例后重新执行生成命令，修改 CSS/JS 后重新生成并刷新。服务的 Cache-Control 为 no-store。

## 文件与共享边界

- `web/ui/tokens.css`：唯一设计 token 源，基础 → 语义 → 组件；亮暗映射，独立密度。
- `web/ui/components.css`：共享组件、布局和预览外壳；颜色读取语义 token。
- `web/ui/interactions.js`：瀑布流测量、键盘 Tab、弹层、Toast、图片失败与动效等纯 UI 行为。
- `shiguang/site/ui.py`：无业务取数的展示函数，文本转义及 URL 限制；未导入正式建站入口。
- `design/render.py`：组件状态展台、布局模式、五页样例，全部使用上述组件。
- `design/playground.js`：示例收藏、过滤、视图和 token 编辑；仅设计预览存储键。
- `design/samples.json` 与 `design/assets/`：明确标示的虚构排版数据、有出处的图片、无品牌示意形态。没有生产或个人数据。
- `tools/design_preview.py`：独立生成/开发服务，目录 `.design-preview/` 被 git 忽略。图片与字体不依赖外部网络。

评审后才接入正式页面。未来同名共享组件直接复用，不再复制一套视觉源码；生产收藏迁移、来源采集、排序/热点评分在功能 PR 中实现。

## Foundations

品牌沿用蓝白表盘与暖光点图标。品牌蓝 `#82C4FF → #438FE8`；交互蓝亮色 `#1E5FA8`、暗色 `#91C5FF`；暖光 `#FFDFA0` 只做提示，不作浅底小字。正文和卡片采用实底，没有大面积光效或玻璃透字。

| 语义 | 亮 | 暗 |
| --- | --- | --- |
| `--page` | #F4F8FD | #0D1725 |
| `--surface` | #FFFFFF | #162335 |
| `--text` | #18283B | #EEF4FF |
| `--muted` | #526477 | #AFBED1 |
| `--border` | #D9E4F0 | #33455D |
| `--action` | #1E5FA8 | #91C5FF |

状态成对定义底色/文字色，并写明已核实、未核实、传闻、带狗或众筹有风险。正常正文对比度目标≥4.5:1；关键大字/图形≥3:1。token 编辑器允许探索，修改值不保证对比度合格，导出不代表批准。

字体统一系统无衬线（Apple / PingFang SC / Noto Sans CJK SC / system fallback），无在线字体请求。字号12/13/14/16/18/22/28/34；正文400、标题600，资讯正文行高1.8，发现理由13/1.6。12用于元信息。

间距4/8/12/16/24/32/48。控件圆角10、卡片16、弹层24、胶囊999。触控区至少44，紧凑只减少空白。资讯阅读区最大760、页面最大1200。手机边距16、列间12。

手机瀑布流2列；预览容器可用宽度达到720/1100后为3/4列（对应平板/桌面内容区域）。选择 iPhone 时画布固定393×852；窄窗口适配为可用宽度。CSS Grid细行跨度测量保留 DOM 顺序，不用 dense、多栏或重排数据；无 JS 是普通双列网格。

图标采用现有 Tabler 3.48.0 线性体系（MIT，沿用 `icons.py` 许可），补充同风格线性形状。状态不靠 emoji。底栏五等分图标+文字，选中淡蓝底、交互蓝、加粗；所有页面同一底栏。

按下100ms、状态160ms、面板220ms，`cubic-bezier(.2,0,0,1)`；减少动态时取消非必要位移。没有自动播放。

## Components、Patterns 与 Screens

- Foundations：双主题色板、语义状态、字体阶梯、间距、圆角、阴影、栅格与图标、点击动效演示。
- Components：按钮默认/按下/聚焦/禁用/加载/错误，搜索输入/清空/失败，筛选/Tab，资讯卡/置顶要闻、同源折叠、图片卡/价格、收藏、弹层、Toast、空态、骨架与图片失败/重试。模拟焦点明确标“示例”，另支持真实 Tab 和鼠标操作。静态组件不制造不适用的状态。
- Patterns：统一顶部与底栏、实底吸顶筛选、分组标题、瀑布流和今日混合摘要。
- Screens：今日、好看、好玩、好买、收藏；好看支持速览/热点/栏目。搜索、来源、分类、带狗为交集；空结果可重置。资讯搜索命中折叠成员会原位展开；来源单选不折叠。
- 今日固定头条1+3、好玩4、好买4，不补齐。样例界面不实现生产采集与算法，热点数据只是演示小时内排序。
- 收藏按收藏时间混排，胶囊只列有内容的类型+全部，支持取消/撤销和刷新保留，键前缀 `shiguang-design-v05:`，不读取正式收藏。空态有操作入口。
- 弹层支持 Esc、焦点恢复、原文出处；可点击放大示例图片。所有样例有统一提示，形态示意和虚构价格再次逐卡标记；没有真实报价或个人本地活动。
- 每块列 token 名及 Do/Don’t；token 编辑器可改语义颜色、圆角、正文字号、卡片内边距，按亮暗分别保存在本机，支持重置和导出 CSS。

## 样例图源

- 蓝白图标：仓库原有 `web/assets/icon-512.png`。
- `jungle-coast.jpg`、`tree-bird.jpg`、`view-from-the-sky.jpg`、`watery-view.jpg`：MDN `dom-examples/view-transitions/spa/images/` 原图，CC0 仓库许可随附 `design/assets/MDN-LICENSE.txt`。确切 URL 和 git 版本见该目录 README。只是排版图，不冒充北京、目的地、展览或作品实拍。
- Solid Glass / SolidCraft：先前已取得的官方 README 截图/演示截帧，保留原图和出处，标历史样例。并未将项目自动接入好玩生产内容。
- `objects.svg`：手写无品牌形态示意，仅作布局与价格格式样例。不是实际产品照片；含价格的卡片均明确写虚构格式示例，不指向真实官方报价。

## 评审与验收记录

阿欢用 Annotate 标注后，逐条修改共享 token/组件并在这里记录；通过之前不套用正式页面。

本轮验证（Playwright + 现有 Chromium）：

- 1440×1000、393×852 × 亮/暗 × 舒适/紧凑 × 五页，共40种组合，未发现横向溢出；手机瀑布流保持2列。
- 全屏手机路由画布正好393×852，统一底栏位于视窗底部。
- 预览条数、折叠/搜索/来源、热点与栏目键盘切换、分组/带狗交集、空结果重置、收藏混排/筛选/刷新/取消撤销通过。
- 弹层/Esc/焦点恢复/看图，token同步/分主题修改/重置/CSS导出、四层切换、动效与减少动态通过。
- 滚动后全部本地样例图片可载入；单文件版仅允许载入HTML主文档、其余网络请求全部阻断时仍可导航、收藏并展示图片。当前受管 Chromium 禁止直接 file 导航，因此该项以 HTTP 提供单文件进行验证；未宣称实测本机 file 打开。
- 新增5项边界测试；包括公开资产入口不输出 design/ui/样例，且正式 CSS/JS 字节未改变。连同现有83项共88项通过。
- 默认亮暗正文/状态色组合13组对比度实算均≥4.5:1；自定义 token 仍需复核。

真实 iOS Safari 不在当前 Chromium 验证范围内。无生产发布、部署或合并。
