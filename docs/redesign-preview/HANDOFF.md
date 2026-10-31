# 交接记录

## 本轮 B5 修改（2026-10-25）

### 分类与群组

- 分类按钮去掉 `--sub` 实心底块、10px 圆角与边框，改为透明背景文字 chip；未选中文字用 `--t2`、图标用 `--t3`，选中为 `--accent` 文字/图标 + 16×2 短下划线。探索 `.explore-chips` 复用同一规则，不再有实心块。
- 删除 `.channel-row` / `.channel-chip` 及其窄屏样式。`.filters` 改为 flex 行：`.category-rail` 占满剩余宽度并横向滚动，右侧 `.filter-actions` 固定放频道标签与 `.group-btn`。
- `.group-btn`（`users-three` + 「群组」，`aria-label="选择群组"`）仅在分类不是「全部」时渲染；分类未读总数 > 0 时显示 `.group-dot` 数字。点击通过 hash 路由 `#group` 打开 `.group-sheet`，标题为 `<分类> · 群组`，列出 `.group-option[data-ch]` 与 `.unread-badge`。
- 选择频道：写入 `state.channel`、`lastSeen[ch] = 最新 ts` 并持久化、关闭 sheet，列表按 `sourceId` 收窄；`.channel-tag` 与 `.channel-tag-clear` 出现在群组按钮旁。清除标签取消筛选；切换分类沿用 `selectCategory` 清空频道。
- 新增点击动作 `group` / `pick-channel` / `clear-channel`；`readRoute` 与 `renderModal` 支持 group sheet。横滑、下拉刷新、按日快照、探索横滑均未改动。

### 验收

- `shot.py` 移除 channel-row 断言与截图，新增：明暗下分类/探索 chip 为透明背景、无边框、无圆角且两者一致；`.group-btn` 在「全部」缺席、分类下存在；`.group-dot` 数字等于分类未读总数；sheet 中至少一个 `.unread-badge` 可见；选择频道后实时/热点/回顾只剩该 ch、`.channel-tag` 出现、`lastSeen` 写入最新 `ts`、该频道徽标清零、`.group-dot` 递减；清除标签恢复分类全量；切换分类清空频道。
- 截图改为 24 张：新增 `group-category-{light,dark}.png`（实时 + 新闻选中）、`group-sheet-{light,dark}.png`、`group-filtered-{light,dark}.png`；删除 `channel-row-light.png` 的生成逻辑。旧的 `shots/channel-row-light.png` 若仍存在，重跑后可手动删除。
- 本轮未运行 `python3 shot.py`（当前会话不能执行命令），需在允许执行的环境复核 24 张截图与全部检查。

## 本轮 B4 修改（2026-10-24 晚间）

### 交互

- **频道行**：`data.js` 新增由 `REAL_ITEMS` 派生的 `CHANNELS`（id／名称／主分类）。资讯选中除「全部」外的分类时，分类栏下渲染 `.channel-row` + `.channel-chip[data-ch]`；点选频道把实时/热点/回顾收窄到该频道，再点取消，切换分类会清空频道筛选。「全部」不渲染频道行。
- **未读徽标**：频道 chip 内的 `.unread-badge` 显示该频道 `ts` 晚于 `lastSeen[ch]` 的条数。`lastSeen` 保存在 `localStorage['rebang.lastSeen']`（JSON `{ch: iso}`）。选中频道即写入该频道最新 `ts` 并持久化，徽标立即消失。首次运行且键不存在时写入预览种子：`xhqcankao/freechinese/HuaErJie1/pelosi3/CE_Observe/zaihuapd/NewlearnerChannel` 取最新一条前 2–6 小时，其余频道等于最新一条，因此四个分类都至少有一个可复现的未读数。
- **探索横滑**：复用资讯的横滑判定（`|dx|>50`、`|dx|>1.5*|dy|`），左右滑动切换好玩/好看/好买，两端停住，切换后标签回到「全部」；纵向下拉仍走原有刷新。
- **按日快照**：回顾标题栏新增 `.calendar-btn`（`aria-label="选择日期"`、Phosphor `calendar-blank`）。打开 `.date-picker` 日期表，按最新快照月份展示近 90 天窗口，只有 `HOT_SNAPSHOTS` 中存在的 10 月 20–24 日可选，其余 disabled。选中后标题为「10月22日 热点」，按快照名次展示当天全部条目；`.day-toggle` 切到当天回顾时间线，「回到今天」恢复普通回顾。切换顶部视图会退出按日模式。

### 真实实现数据规格

#### 频道 → 分类

| id | name | category |
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

真实实现应把频道表落到数据库（`channel(id, name, category)`）或配置表；原型从本地快照派生，频道条目目前各自只属于一个主分类。

注：已停更的频道不纳入该映射（`liangjiahepost` 已于 10 月 22 日停更并移除）。

#### 未读（客户端）

- 存储：`localStorage['rebang.lastSeen']`，JSON 对象 `{ "<channel_id>": "<ISO 时间>" }`。
- 计数：`unread(ch) = count(items where item.ch == ch and item.ts > lastSeen[ch])`。
- 查看：选中频道（或进入该频道的频道页）时写入 `lastSeen[ch] = max(item.ts for ch)` 并立即持久化，徽标按新值重算。
- 原型仅在键不存在时写入种子；真实实现可从服务端同步已读时间，但本地缓存仍沿用同一键和结构。

#### 每日热点快照

- 每日抓取完成后生成一次当日快照，排序规则与「热点」完全一致：`heat` 降序，同热度按 `ts` 降序；排名从 1 开始，保存当天全部条目。
- 表结构：

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

- 读取：过去日期只读快照；当天可先实时计算，快照生成后改读快照。原型用 `HOT_SNAPSHOTS {'YYYY-MM-DD': [itemId...]}` 由 `REAL_ITEMS` 现算，不写死排名。
- 保留：只保留最近 90 天。每日清理任务（建议在快照生成后执行）：

```sql
DELETE FROM hot_snapshot WHERE day < CURRENT_DATE - INTERVAL '90 days';
```

- 日期表同样按 90 天窗口生成，无快照的日期不可选；原型以最新快照月份为准。

### 验收

- `shot.py` 新增：频道行在「全部」缺席、分类下出现且与频道表一致；频道筛选收窄与取消、切换分类清空；未读徽标与种子计数一致、样式为 400 字重和强调色、查看后消失且 `lastSeen` 持久化；探索横滑三段与两端停止；日历按钮仅在回顾出现、日期表启用 20–24 日且其余 disabled、选择过去日后按 `HOT_SNAPSHOTS` 展示全部条目、切换当天回顾、回到今天。
- 新增截图：`channel-row-light.png`、`explore-swipe-light.png`、`calendar-open-light.png`、`day-hot-light.png`、`day-review-light.png`；总计 19 张。
- 本轮未运行 `python3 shot.py`（当前会话命令执行受限），需在允许执行的环境复核 19 张截图与新增检查。

## B3 修改（2026-10-24 晚间）

- 探索分类 chips（全部／北京周末／温泉／新店／美食等）改为复用资讯分类栏的 `.category-rail > button` 规则：同一个 `--sub` 实心底块、10px 圆角、`0 11px` 内边距，选中态为强调色文字 + 短下划线；去掉描边和条数徽标，字重保持 400。
- `shot.py` 新增首屏配图检查：打开资讯／实时／全部时，至少 2 张 `.feed-img` 已完成加载（`complete && naturalWidth > 0`），且完整落在 `.feed-scroll` 初始首屏可视区内；检查过程不得滚动列表。
- `shot.py` 新增 chips 样式一致性检查：探索 chips 与资讯分类 chips 的 `background-color`、`border-radius`（以及无边框）在浅色与深色下都必须一致。
- `explore-src/` 目录已删除，探索配图全部位于 `img/explore/`；`shot.py` 的 `assert_no_explore_src` 保留，继续做静态文件与运行时资源路径两重检查。
- 数据快照为 2026-10-24 18:00 JST（17:00 +08）之前的帖子，与 `real-data.js` 顶部注释一致。
- 本轮仍未运行 `python3 shot.py`（解释器命令被权限层拦截），需在允许执行的环境复核 14 张截图与新增检查。

## 范围与运行

- 当前目录为独立静态原型，无构建步骤；直接打开 `index.html`。
- 只在当前目录写文件。未读取密钥文件，未使用 Git，未联网、合并或部署。
- 视觉参考是灵记 v0.2；分类唯一依据是上一级 `categories.md`。
- `python3 shot.py` 执行离线交互检查和 24 张 DPR 3 截图。不要为了截图安装或更新依赖，当前环境已有 Playwright 和指定 Chromium。

## 已确认的坑

1. 指定 `news-icons.js` 的 moon_line / sun_line 在主 ICONS 对象之后单独追加。只解析对象会误判图标缺失。`theme-icons.js` 保留这些确切 SVG。
2. DPS Build 不能按频道整批归类。频道可出现在消费与开发工具筛选中，但条目仍只有一个主类。
3. 合并数量只统计规范化后的不同 TG 频道。`world`、`github` 及频道别名不额外计数；频道筛选不得把完整事件的 N 缩成 1。
4. 原文是本地示例链接，不能改成线上地址后仍声称完全离线。原型不实现真实抓取或自动事件聚类。
5. 抽屉重绘需要保留抽屉滚动位置和焦点；关闭详情需要恢复资讯列表位置。弹层打开时背景使用 inert，并约束键盘焦点。
6. Chromium 的 Unix socket 路径上限为 108 字节。本目录路径较长，浏览器临时目录使用短前缀 `.p-`；长前缀会导致 `Socket path too long` 启动失败。启动 Playwright 前设置 TMPDIR，确保浏览器运行文件也留在当前目录。

当前 B5 的行为与验收入口以本页顶部记录为准；`DESIGN.md` 已同步为 B5 说明。B4 及更早记录保留在下方，仅作历史参考。

## 资源与数据更新（2026-10-24）

- 探索配图已复制到 `img/explore/`，`app.js` 的卡片与详情都改用该目录；`explore-src/` 目录已删除，应用文件（`*.js`、`*.css`、`index.html`）不再引用它。
- `shot.py` 新增 `assert_no_explore_src`：静态检查应用文件，并检查运行时已加载资源路径均不含 `explore-src`；该检查保留。
- `real-data.js` 重新生成（schema 不变）：当前 129 条、50 条带本地图、11 个频道、10-21 至 10-24；数据快照仅含 2026-10-24 18:00 JST（17:00 +08）之前的帖子。`shot.py` 的图片数量、分类条数、日期与频道全部从 `REAL_ITEMS` 现算，滚动加载也按实际列表高度遍历，不再依赖固定滚动位置。
- 新增实时分类配图检查：新闻／财经／消费／科技各自选中时至少有一张 `img/feed/` 图片真实加载；同时校验 `.feed-img` 数量等于该分类数据中的配图数。
- 新增 Logo 检查：顶栏与「我的」页 `<img>` 的 `src` 均为 `logo/d-tab.svg`，且实际解码成功。
- 本轮未运行 `python3 shot.py`（解释器命令仍被权限层拦截），需在允许执行的环境复核。

## 验收结果

- `shot.py` 的 B2 检查与截图命名已更新，shot.py run and passed。
- 脚本预期输出 `shots/realtime-{light,dark}.png`、`shots/hot-{light,dark}.png`、`shots/review-{light,dark}.png`，每张 1206×2622（402×874 CSS px，DPR 3）。
- 脚本仍校验浏览器错误 0、外网请求 0、320px 窄屏无横向页面溢出与桌面手机框居中。
- `shots/` 中旧的 A/B/C 截图已不再由脚本生成，确认新截图后可删除。

## 上一版修改（A/B/C，2026-10-24）

- 字重统一为 400，仅 `.brand h1` 与方案说明页大标题保留加粗；所有选中态只用品牌红，不再靠字重。
- 浅色 `--tint` 改为 `rgba(215,40,47,.05)`，红字对比度提升到 4.5:1 以上；暗色不变。
- A：频道标签圆角 22→9；子类分段视觉高 36px，按钮触控区仍为 44px。
- B：去掉满底正红块，选中分类改为红字 + 下划线；子类换到下一行，五个分类始终可达，「消费」保留左侧留白。
- C：分类行去外框和分隔线，频道标签去边框；筛选按钮移到分类行，不再截断频道行，「看新闻学英语」首屏完整可见；删除重复的「分类 / 子类」摘要行；查看一个分类最多两次点击。
- `python3 shot.py` 已更新并通过：新增字重、浅色对比度、A 子类触控、B 分类可达、C 边框/按钮/频道完整显示等检查。

## B2 修改（2026-10-24）

- 仅保留 B：移除 A/C、顶部 A/B/C 切换器和筛选抽屉；点击分类按钮直接切换，不再先弹筛选层。筛选草稿与确认/重置代码一并删除。
- 资讯区横滑切换分类（全部→新闻→财经→消费→科技）：`|dx|>50` 且 `|dx|>1.5*|dy|` 才判定为横滑；两端停住不循环；选中分类调用 `scrollIntoView({inline:'center'})`。监听器为 passive，资讯区使用 `touch-action: pan-y`，不拦截纵向滚动。
- 热点改为榜单：大号排名、按 heat 决定宽度的 `.hot-bar`、频道数胶囊 `.hot-channels`，前三名为更大的 `.hot-top` 卡片，与实时列表明显区分。
- 回顾改为按天时间线：每天一张 `.review-day` 卡片，最多列出 5 条 `.review-item`，向下滚动查看更早日期；新增 10 月 22、21 日样例。
- 热点与回顾共用实时页的分类栏，并遵守分类、子类与频道筛选。
- `data.js` 为热点新增 heat 指标，为回顾新增 day/weekday 与两天样例；原有条目未删改。
- 截图改为 `realtime/hot/review × light/dark` 六张；`shot.py` 移除 A/C 检查，新增分类直达无弹层、合成横滑（阈值与两端停止）、热点结构与回顾每日上限检查。
- 当前原型原本没有下拉刷新实现，本次未新增；现有滚动与重绘行为保持不变。

## 下拉刷新与一致性修正（2026-10-24）

- 新增下拉刷新：触摸开始时记录 `.feed-scroll` 的 `scrollTop`，仅在起点为 0、`dy>0` 且 `|dy|>1.5*|dx|` 时触发；先判定横滑（`|dx|>50` 且 `|dx|>1.5*|dy|`）并直接返回，因此横滑不会刷新，下拉也不会切换分类。触发后插入 `.ptr-indicator.ptr-refreshing`，约 800ms 后调用 `render()` 模拟刷新并移除指示器。三个视图共用这一交互。
- 顶部标签选中下划线从 `--red` 改为 `--accent`，与选中文字一致；深色主题下同步使用 `#F05A5F`。
- 热点频道数胶囊仅在 `count > 1` 时渲染，与实时列表一致；全部热点中可见胶囊由 7 个变为 6 个（`hot-6` 仅一个 TG 频道）。
- `DESIGN.md` 重写为仅描述 B2 当前行为。
- `shot.py` 新增下拉刷新（顶部出现/消失、下滑不触发、横滑不触发、不切换分类）、明暗下划线颜色等于选中文字、热点无「1 个频道在说」等检查；热点胶囊数量改为按 `count > 1` 动态计算，原有检查未删除或放宽。

## 热点榜单修正（2026-10-24）

- 热点渲染前按 `heat` 降序排序，排序与热度条使用同一数值；热度条宽度改为 `heat / maxHeat * 100%`，当前筛选下的第一名恒为满格，其余按比例缩短。
- `data.js` 的 `HOT_HEAT` 调整为 `[96, 82, 69, 57, 46, 35, 24]`，拉开差距，避免全部接近满格。
- 前三名继续使用 `.hot-top` 大卡片；第 4 名起改为 `.hot-row` 紧凑行：小号名次、标题、单行省略来源（`.hot-source`），背景透明且无卡片边框，颜色与字重沿用现有 CSS 变量和 400。
- `shot.py` 新增 `assert_hot_ranking`：校验热度降序、首名热度条约等于轨道宽度、后续条宽度递减且与热度比例误差不超过 2%，以及第 4 名起的 `.hot-row` 透明背景、无边框、单行省略来源；全部分类与各一级分类下都会执行。
- 本次改动后需重新运行 `python3 shot.py` 生成六张截图并复核新增检查（当前会话未执行该脚本）。

## B3 修改（2026-10-24）

### 数据与结构

- `index.html` 依次加载 `icons.js`、`theme-icons.js`、`real-data.js`、`data.js`、`explore-data.js`、`app.js`（均 `defer`）。资讯唯一数据源改为 `REAL_ITEMS`（129 条、11 个来源频道，分类仅新闻／财经／消费／科技，日期 10-20 至 10-24，其中 45 条带本地图）。`data.js` 只保留 `CATEGORIES` 与 `CHANNEL_NAMES`，旧的虚构事件夹具不再渲染。
- 事件 ID 为 `real-<id>`，由 `ts` 直接生成日期、星期、时间与 `dateKey`；`count` 固定为 1，因此详情不显示「N 个频道在说」。热点热度由标题长度 × 2 + 摘要长度 + 剩余新鲜度现算，排序与 `.hot-bar` 宽度共用该值；前三名 `.hot-top`，第 4 名起 `.hot-row`。回顾按 `dateKey` 分组、每日上限 5 条、最新一天在前。
- 彻底移除子类与频道筛选：没有 `SUBCATEGORIES`、子类分段、频道标签行或筛选抽屉；分类栏只有五个一级分类。

### 全应用

- 底部导航「资讯 / 探索 / 我的」，图标为 Phosphor `house_line` / `compass_line` / `user-circle_line`；顶栏 Logo 换成 `logo/d-tab.svg`，标题随页面变化。每个页面独立记忆滚动位置。
- 探索沿用已批准的 探索 模块：`explore-data.js` 提供 `PLAY` / `BUY`，`KAN_TAGS = ['剧','电影','小说','展览']` 决定「好看」归属；好玩／好看／好买三段与标签 chips 均按本地数据现算条数。
- 我的页面含深色模式开关（与顶栏按钮共用 `state.theme`，整行 56px 都是开关）、设计说明入口，以及由 `REAL_ITEMS` 现算的条数／天数／频道数统计。统计当前为 129 / 5 / 11，但代码不写死。
- 主题仍可用 `?t=light|dark` 指定打开时的外观；切换主题只更新页面，不改写地址。弹层改为纯 hash 路由：打开设置 `location.hash`，关闭清空 hash，由 `hashchange` 重绘。已删除 `updateURL`、`history.replaceState` 与 `popstate` 监听，避免 `file://` 下 History API 抛 SecurityError；关闭后用 `pendingFocus` 在异步重绘后把焦点还给触发按钮。

### 图标

- 全站只用 `icons.js` 的 Phosphor 图标（含 `theme-icons.js` 的月亮／太阳），统一 `viewBox="0 0 256 256"`、`fill="currentColor"`，没有 Lucide 标记或描边式 24×24 SVG。`icon()` 会自动补 `_line` 后缀，分类与底部导航的键名集中在 `CATEGORY_ICONS` / `SECTIONS`。

### 资源限制

- 本会话沙箱最初只放行只读命令，`mkdir` / `cp` / `python3` 等写操作或解释器命令会被权限层拦截（提示 `Error: Allow Bash to run: ...`）。该限制后续已解除：探索配图已复制到 `img/explore/`（`v_p9.webp`、`v_b8.webp`、`v_b6.webp`、`v_b7.webp`），`app.js` 的 `renderExploreItem` 与 `renderExploreDetail` 均改用该目录，仍完全在本目录内且不发外网请求。`explore-src/` 随后已删除，不再作为配图来源。

### 验收状态

- `shot.py` 已改为 B3：移除子类／频道筛选相关检查；期望值改为从 `REAL_ITEMS` / `PLAY` / `BUY` 现算；新增无 Lucide、SVG 256 视图框、图标不含 stroke、每项分类与底部入口含图标、无子类行、至少 5 张 `img/feed/` 图片实际解码、三个底部入口切换、探索三段与标签、我的统计与主题联动、本地配图等检查；原有横滑、下拉刷新、热点排名与胶囊、回顾上限、原文往返、空态／错误、字重、对比度、触控、焦点、窄屏与零外网检查未删除或放宽。
- 两处旧断言按 B3 行为修正：实时与回顾的首条本来就都是最新条目，改为分别校验「实时首条 = 最新」与「回顾首条 = 最新」，「热点首条 = heat 最高」；频道原文页有两个同名「返回事件」链接，改为明确点击 `.sheet-header` 内的返回链接，避免 Playwright strict mode 报错。
- 截图改为 14 张：`realtime-{light,dark}`、`hot-{light,dark}`、`review-{light,dark}`、`explore-play-{light,dark}`、`explore-kan-{light,dark}`、`explore-buy-{light,dark}`、`mine-{light,dark}`，每张 1206×2622。
- 本轮未能实际运行 `python3 shot.py`（该命令被沙箱权限层拦截），`shots/` 仍只有 B2 的六张图；需在允许执行的环境重跑并复核 14 张输出。运行前保留脚本内短前缀 TMPDIR（`.p-`）的处理，避免 socket 路径超长。

