# 拾光热榜 · 离线原型（B5）

直接打开 `index.html`，无需服务、构建或网络。底部「资讯 / 探索 / 我的」切换整个应用；`?t=light|dark` 只用于指定打开时的明暗外观，之后暗色切换不再改写地址。顶部信息按钮打开设计说明。

## 全局结构

- **底部导航**：资讯、探索、我的三个入口，图标取 Phosphor `house_line` / `compass_line` / `user-circle_line`，选中态只用 `--accent`。导航底部留出 24px 以上内边距，文字标签始终位于 home indicator 上方；切换页面分别记住各页滚动位置。
- **顶栏**：Logo 使用定稿 D（`logo/d-tab.svg`），标题随页面为「拾光热榜 / 探索 / 我的」；右侧为仅图标的明暗切换按钮，与「我的」里的深色开关共用同一份主题状态。
- **下拉刷新**：资讯、探索、我的三个页面的滚动区都支持。仅当滚动位置为 0、向下拖动至少 50px 且以纵向为主（`dy >= 50` 且 `|dy|>1.5*|dx|`）时触发，显示 `.ptr-indicator`，约 800ms 后用当前筛选重绘；不足 50px 或横滑都不会刷新。
- **我的**：主题开关、「设计说明」入口、三条统计（内容总数、回顾天数、来源频道数）、数据来源与日期范围。统计值全部由真实数据现算，不写死。
- **弹层路由**：事件、频道原文、探索详情、设计说明都通过地址 hash 打开；关闭时清空 hash。背景加 `inert`，键盘焦点被约束在弹层内，关闭后回到触发按钮。`file://` 下不调用 History API。

## 资讯

- **视图标签**：实时、热点、回顾在同一页内切换，保留当前分类；切换视图会退出「某日快照」并回到今天。
- **分类栏**：一级分类「全部、新闻、财经、消费、科技」，每项带 Phosphor 图标（`squares-four_line` / `newspaper_line` / `chart-line-up_line` / `shopping-bag_line` / `cpu_line`）。按钮不再使用实心底块：背景透明、无边框、无圆角块；未选中为次要灰文字（`--t2`）与更弱的图标（`--t3`），选中为强调色文字、图标与短下划线。
- **群组按钮**：分类栏右端固定 `.group-btn`（`users-three` 图标 + 「群组」，`aria-label="选择群组"`），仅在分类不是「全部」时出现。该分类未读总数大于 0 时，按钮右上角显示 `.group-dot` 数字角标。
- **群组面板**：点 `.group-btn` 打开底部 `.group-sheet`（复用日期表的底部 sheet 样式），标题为「<分类> · 群组」，逐行列出该分类频道 `.group-option[data-ch]`，右侧显示 `.unread-badge` 未读数。选择一个频道后：列表收窄到该频道、面板关闭、该频道写入已读、群组按钮旁出现可移除的 `.channel-tag`（频道名 + `.channel-tag-clear` 关闭按钮）。清除标签恢复该分类全量列表；切换分类会自动清空频道筛选。实时、热点、回顾三个视图共用。
- **未读徽标**：`.group-dot` 显示当前分类各频道未读之和；`.group-option` 内的 `.unread-badge` 显示单频道 `ts` 晚于 `lastSeen[ch]` 的条数；`lastSeen` 存在 `localStorage['rebang.lastSeen']`（JSON，值为 ISO 时间）。选择频道即视为查看，写入该频道最新一条的 `ts`、持久化并让该频道徽标立即清零。原型首次运行且没有该键时写入示例 `lastSeen`：部分频道取最新一条，部分频道取最新一条前若干小时，因此首屏能看到少量未读数。
- **横滑切换分类**：在资讯区左右滑动，按「全部→新闻→财经→消费→科技」顺序切换；位移超过 50px 且明显偏横向（`|dx|>1.5*|dy|`）才生效，两端停住不循环。纵向滚动不触发；横滑不会触发刷新，下拉也不会切换分类。
- **实时**：`REAL_ITEMS` 按 `ts` 从新到旧排列。有图的条目显示 `img.feed-img`（本地 `img/feed/` 路径、`object-fit: cover`、`loading="lazy"`）；无图条目沿用纯文字布局。详情展示真实标题、摘要、频道与时间。
- **热点**：由同一批真实条目现算，按 `heat` 降序。热度为固定公式：标题长度 × 2 + 摘要长度 + 剩余新鲜度，同一数据每次得到相同结果。热度条宽度取 `heat / maxHeat * 100%`，与排序同源，第一名满格。前三名为 `.hot-top` 大卡片，第 4 名起为 `.hot-row` 紧凑行。
- **回顾**：按 `ts` 的日期分组，最新一天在最前；每天先按 `heat` 降序（同热度按时间倒序）取前 5 条，再按时间倒序展示。当前数据覆盖 10 月 20 日至 10 月 24 日，共 5 天。
- **按日快照**：回顾标题右侧的 `.calendar-btn`（`aria-label="选择日期"`，Phosphor `calendar-blank`）打开 `.date-picker` 日期表。只启用最近 90 天内、确有快照的日期（当前为 10 月 20–24 日），其余日期 disabled。选中某日后，顶部标题变为「10月22日 热点」，按 `HOT_SNAPSHOTS[day]` 列出当天全部条目的热度排名；`.day-toggle` 可切到当天的回顾时间线，「回到今天」返回普通回顾列表。`HOT_SNAPSHOTS` 在原型中由 `REAL_ITEMS` 现算，排序规则与热点一致。
- **原文来源**：每条真实条目只有一个 TG 频道，`count` 恒为 1，因此不显示「N 个频道在说」胶囊。详情中的「查看原文」打开本地示例页，可返回事件；关闭后恢复列表位置。

## 探索

- **分类**：好玩、好看、好买三段切换；下方标签 chips 复用资讯分类栏的无底色文字 chip 样式（透明背景、无边框、无圆角块，选中态强调色文字 + 短下划线），可在当前段内继续收窄；不再显示条数徽标。
- **横滑切换**：探索列表复用资讯分类的横滑判定（`|dx|>50` 且 `|dx|>1.5*|dy|`），左滑依次进入好玩→好看→好买，右滑反向；两端停住不循环，切换后标签回到「全部」。横滑不会触发下拉刷新。
- **内容**：改编自已批准的 探索 模块样刊 #2，数据在 `explore-data.js`（`window.PLAY` / `window.BUY`），按标签把剧、电影、小说、展览归入「好看」，其余归「好玩」。
- **卡片与详情**：卡片含分类、标题、推荐理由、时间地点（好买另显示价格与上市／订阅信息），有图的条目显示本地配图。详情完整展示分条信息、未核实项与来源名称／域名（纯文本，不可点击跳转），不伪造事实。
- 配图引用本目录 `img/explore/`；页面不加载任何外网资源，来源域名只作为纯文本标注。

## 内容规则

- `real-data.js` 的 `REAL_ITEMS` 是唯一的资讯数据源：120 条、10 个来源频道，分类只有新闻、财经、消费、科技；快照仅含 2026-10-24 18:00 JST（17:00 +08）之前的帖子，日期范围 10 月 20–24 日。旧的虚构事件夹具已不再渲染；`data.js` 保留 `CATEGORIES`、`CHANNEL_NAMES`，并由真实条目派生 `CHANNELS` 频道→分类表。
- 频道→分类映射（频道条目目前各自只属于一个主分类）：

| 频道 ID | 名称 | 分类 |
| --- | --- | --- |
| `xhqcankao` | 风向旗参考快讯 | 新闻 |
| `tnews365` | 竹新社 | 新闻 |
| `freechinese` | FREE 中文 | 新闻 |
| `FinanceNewsDaily` | 华尔街见闻·财经时讯 | 财经 |
| `HuaErJie1` | 华尔街日报 | 财经 |
| `TimeHorizonX` | Time经济观察 | 财经 |
| `pelosi3` | 敏感经济信息分享 | 财经 |
| `CE_Observe` | 每日消费电子观察 | 消费 |
| `zaihuapd` | 在花科技圈 | 科技 |
| `NewlearnerChannel` | Newlearnerの自留地 | 科技 |

已停更的频道不纳入该映射（`liangjiahepost` 已于 10 月 22 日停更并移除）。

- 分类只在「实时 / 热点 / 回顾」内部筛选；热点与回顾共用同一条分类栏；频道筛选只在已选分类内生效。
- 按日快照 `HOT_SNAPSHOTS` 由当日真实条目按热点公式排序得到，键为 `YYYY-MM-DD`，值为按名次排列的条目 ID；原型只保留有数据的 10 月 20–24 日。真实实现的存储与 90 天清理见 `HANDOFF.md`。
- 当前是展示层原型，不实现真实抓取、规范化链接或自动聚类；本地备数据不等于线上实时内容。

## 真实实现数据规格（B5）

- **未读**：客户端保存 `localStorage['rebang.lastSeen'] = { "<ch>": "<iso>" }`；`unread(ch)` 为 `ts > lastSeen[ch]` 的条目数。查看频道时写入该频道最新 `ts` 并持久化，徽标随即清零。原型首次运行按频道种子写入示例值。
- **每日热点快照**：每天落库一次当天全部条目的排名，排序与热点一致（`heat` 降序，同热度按 `ts` 降序）。表：

```sql
hot_snapshot(
  day        date        not null,
  rank       smallint    not null,
  ch         text        not null,
  msg_id     bigint      not null,
  heat       real        not null,
  created_at timestamptz not null default now(),
  primary key (day, rank)
);
```

- **保留与清理**：只保留 90 天；每日任务执行 `DELETE FROM hot_snapshot WHERE day < CURRENT_DATE - INTERVAL '90 days';`。日期表按同一 90 天窗口生成，只有存在快照的日期可选。

## 视觉与实现

沿用灵记 v0.2 的中性灰、文字层级、细分隔线与留白，不设左侧分类栏。分类与探索标签使用透明背景文字 chip，不再使用实心底块、边框或圆角块。所有颜色只来自现有 CSS 变量（`--bg`、`--sub`、`--press`、`--line`、`--line2`、`--t1`、`--t2`、`--t3`、`--red`、`--accent`、`--tint`），没有新增十六进制色值。正文与控件统一 400 字重，只有品牌标题（页面大标题）加粗；选中态只用强调色区分。浅色模式红字对比度不低于 4.5:1。

全部图标使用 `icons.js` 的 Phosphor 集合（MIT，保留原版权说明），统一 `viewBox="0 0 256 256"`、`fill="currentColor"`，不含 Lucide 图标或描边式 24×24 图形。没有外网字体、图片、CDN、fetch 或运行时依赖。桌面显示居中的 402×874 CSS px 手机框，宽度不超过 600px 时全屏适配。

## 截图与验收

运行 `python3 shot.py`。脚本使用预装 Playwright 和指定 Chromium，viewport 402×874、DPR 3，离线模式下生成 24 张 1206×2622 截图：

- `shots/realtime-{light,dark}.png`
- `shots/hot-{light,dark}.png`
- `shots/review-{light,dark}.png`
- `shots/group-category-{light,dark}.png`（实时 + 新闻选中）
- `shots/group-sheet-{light,dark}.png`（群组面板打开）
- `shots/group-filtered-{light,dark}.png`（按频道筛选并显示标签）
- `shots/explore-play-{light,dark}.png`
- `shots/explore-kan-{light,dark}.png`
- `shots/explore-buy-{light,dark}.png`
- `shots/mine-{light,dark}.png`
- `shots/explore-swipe-light.png`
- `shots/calendar-open-light.png`
- `shots/day-hot-light.png`
- `shots/day-review-light.png`

验收以 `REAL_ITEMS` 现算的期望值为准，覆盖：页面与全部 JS 无 Lucide 标记、所有 SVG 为 256 视图框、五个分类与三个底部入口各含图标；分类行与探索 chips 在明暗两种主题下均为透明背景、无边框、无圆角块且两者样式一致；群组按钮在「全部」隐藏、在选定分类下出现，`.group-dot` 数字等于该分类未读总数；群组面板列出该分类频道与未读徽标，选择频道后实时/热点/回顾都只剩该频道条目、`.channel-tag` 出现、`lastSeen` 等于该频道最新 `ts` 且该频道徽标清零，清除标签恢复分类全量，切换分类会清空频道；`localStorage['rebang.lastSeen']` 首次加载写入示例值，未读数与 `ts` 晚于 `lastSeen` 的条数一致；探索横滑切换三段并两端停住；日历按钮仅在回顾出现，日期表启用有快照的 10 月 20–24 日、其余 disabled，选中过去某日后按 `HOT_SNAPSHOTS` 顺序展示当天全部条目、可切到当天回顾时间线、可回到今天；资讯列表至少 5 张本地图片（`naturalWidth > 0`），且首次加载的资讯／实时／全部首屏内至少有 2 张已加载图片完整可见；三个底部入口可切换；探索三段与标签筛选；我的主题开关与顶栏联动；实时排序、热点热度排序与热度条比例、前三名大卡片与紧凑行、回顾按天分组且每日按热度取前 5 条再按时间展示；底部导航文字标签与 home indicator 不相交；横滑切换与两端停止、下拉刷新（含 10px 下拉不触发）、原文往返、空态与错误重试、字重、对比度、44px 触控、焦点约束、窄屏无溢出、桌面居中、浏览器错误 0、外网请求 0。运行过程仅在本目录创建并清理浏览器临时目录。
