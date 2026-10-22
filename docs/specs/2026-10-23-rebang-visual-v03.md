# [Spec] 热榜视觉系统 v0.3 全量对齐

- 日期：2026-10-23 · 作者：工头 · 状态：Draft，待阿欢过目
- 批准：阿欢 10/23 01:32（🔥热榜开发小组）通过视觉系统 v0.3，附一条修正：底栏不能挡住正文
- 仓库：kwinweng/shiguang-hot · 基线分支 `feat/rebang-trial-sources`（PR #24 的试跑源工作保留）
- 真相来源（冲突时按此顺序）：① 本 Spec 的「已定决策」② `playground/DESIGN.md` v0.3 + `tokens.json` ③ 预览 https://rebang-design-preview.vercel.app/#screens ④ 差异包 `design/pr24-diff/diff.md`

## 0. 已定决策
1. 底栏第 2 项叫「资讯」。
2. 原「好看」页改名「每日简报」，放进「栏目」，不在底栏。
3. 全部屏一轮做完，不拆。
4. 无图文字卡（色板 7 组、4:3、圆角 12）已对齐，**不改**。
5. PR #24 不按原样合并；本轮在其分支之上继续。
6. 技术栈不变：Python 构建 + 原生 JS，无框架，不新增依赖；图标 Phosphor 2.1.1 内联 SVG（阿欢例外，替代 Lucide 默认），未选 regular、选中 fill。
7. 手机按 iPhone 17 Pro 402×874（顶部安全区 59，底部 34）；桌面 1440。主色热榜红 `--c-brand` #D7282F / 暗 #F05A5F；暗色必须有，跟随 `prefers-color-scheme`。

## 1. Token 落地
- 把 `tokens.json` v0.3 生成的 `tokens.css` 原样引入 `web/`，作为唯一样式变量来源；删除旧变量（`--space-*`、`--tab-clearance`、收藏页 `.g-light` 渐变、米色 #EEE8DF 等）。
- 不允许在组件里写死颜色/字号；只用 `--c-* --t-* --sp-* --r-* --sh-* --s-* --m-*`。
- 关键值（完整表见 DESIGN.md §2）：
  - 颜色：bg #FFFFFF/#111214；text #1A1C20/#ECEDEF；text-2 #5A5E68/#B4B8C0；text-3 #8A8F99；text-4 #A3A8B2/#6B7080；line #EDEEF0/#26282D；glass rgba(255,255,255,.72)/rgba(30,32,36,.72)；sheet #FFFFFF/#1C1D21；up/down #D7282F,#1E8E4E / #F05A5F,#3DBB72；lightbox #000。
  - 字：page-title 28/36/600；section 20/28/600；mag-title 20/28/600；list-title 17/24/600；card-title 15/22/600；excerpt 15/24；ui 15/22；caption 13/20；meta 12/16；tab-label 11/14。
  - 间距：页边距 20（锁定）；分区标题上 28 下 4。圆角 xs4/sm8/md12/lg16/bar35/sheet20。
  - 尺寸：thumb 120×90；control 40；bar-h 70；icon 24/16；filter-dot 7；masonry-gap 12（桌面 24）；content-col 720；drawer 320；cal-cell 44；ptr 56；rail 340；app-icon 64。
  - 动效：fast 120ms，base 200ms，ease cubic-bezier(.2,0,0,1)，玻璃 blur(20px) saturate(170%)。

## 2. 全局骨架（所有屏）
### 2.1 页头
去掉老 52px sticky 顶栏和 `.g-lead`。每页 `.ph` 高 56：左大标题（page-title），右 40×40 图标按钮（圆角 12，无底，24px，悬停 bg-hover）。今日标题「拾光热榜」，下方日期行「10月22日 周四 · 17:10 更新」13px text-3，margin-top −6px。≡ 按钮打开抽屉。
### 2.2 悬浮底栏（含阿欢修正）
- 位置左右 16、距底 16 + `env(safe-area-inset-bottom)`，高 70，圆角 35，内边距 6；玻璃 `--c-glass` + `--m-blur` + 0.5px `--c-glass-edge` 内描边 + `--sh-glass`。
- 5 项：今日 house / 资讯 book-open-text / 好玩 compass / 好买 shopping-bag / 收藏 bookmark-simple。单项 71×58，图标 24 + 标签 11/14/400。选中：底 `--c-bg-press`，图标 fill + `--c-brand`，文字保持 `--c-text`。
- **不挡正文（硬性）**：
  1. 每个滚动容器 `padding-bottom: calc(var(--s-bar-h) + 16px + env(safe-area-inset-bottom) + 16px)`（底栏高 + 底栏距底 + 安全区 + 16）。不得被后续规则覆盖（PR #24 的 `--tab-clearance` 被 `padding-bottom: var(--space-8)` 覆盖的 bug 要删掉）。
  2. 设计 10/23 补充：从底栏顶边到屏幕底铺一层实底（`--c-bg`），其上一段短渐隐（透明→`--c-bg`），亮暗都有。具体渐隐高度和颜色以 DESIGN.md 更新后的数值为准；DESIGN.md 未更新前实现不得开工这一项（见 §9 Q1）。
  3. 验收：滚到底时最后一条（含标题、来源行、书签）完全在底栏上沿之上 ≥16px；暗色下底栏后面看不到卡片文字。
### 2.3 通用组件
按 DESIGN.md §4：按钮 40/12/15px；分类文字 Tab（15px，选中 text + 2px brand 下划线，底线 1px line，高 40，间距 20）；图标筛选 44×44 圆角 12，图标 22，选中 fill + brand + 7px 点；搜索框高 44 bg-subtle；收藏按钮 32×32 bookmark-simple（未收藏 regular text-3，已收藏 fill brand）；Toast 底部居中 2.5s 不叠加；状态行（danger/warning + 原因 + 文字操作）。禁用：胶囊按钮、渐变卡、图上压字遮罩、左彩条、emoji。
### 2.4 列表与卡片
- 资讯行：上下 16，图文距 14，底线 1px line；左图 120×90 r8，占位 bg-subtle，1px `--c-img-edge`；标题 list-title ≤3 行；meta「来源 · 分类 · 时间」12px text-3；右下书签。无图行纯文字 + 右下书签。去掉 `brightness(.82)` 压暗滤镜（见 Q3）。
- 大图卡（好玩/好买）：两列，列宽 174，列距 12，行距 20；图片保持原比例（GitHub 2:1），r12，占位 bg-subtle；标题 card-title 2 行；摘要 13/20 text-2 2 行；来源行 12/16 text-3 在摘要**下面**，右侧书签。
- 无图文字卡：不改。

## 3. 每屏规格与验收（手机 402，除注明外亮暗都要）
| # | 屏 id | 规格要点 | 验收 |
|---|---|---|---|
| 1 | today | 页头「拾光热榜」+ 日期行 + 日历/搜索；顺序：资讯（5 行左图）→ 好玩 ×4 → 好买 ×4；分区标题 20/600 + 数量 20/400 text-4（左距 8）+「更多 ›」15px brand + 16px caret | 顺序正确；三个分区标题值与表一致；点「更多」进对应页 |
| 2 | news（资讯·速览，含 news-quick） | 底栏第 2 项；顶部「速览 / 热点」二段文字 Tab + 下划线；来源图标筛选行 + 分类文字 Tab；日期分隔；原帖时间倒序；加载更多到底 | 无胶囊；切来源/分类结果正确；到底提示出现 |
| 3 | hot | 热点：排名数字 + 标题 + 热度 + 迷你折线，涨 `--c-up` 跌 `--c-down` | 数字、颜色亮暗都对 |
| 4 | play | 好玩：分组文字 Tab（替换圆形图标按钮）+ 两列瀑布流 | 选中下划线红、暗色用 #F05A5F |
| 5 | buy | 好买：同 play，可选文字标签和官方价 | 同上 |
| 6 | fav | 收藏：三类混排；纯 `--c-bg`，去掉米色和渐变 | 亮 #FFFFFF / 暗 #111214；取消收藏实时消失 |
| 7 | mag（每日简报） | 栏目内；16:10 头图 r16，标题 20/28，摘要 15/24 三行 | 从栏目进入；底栏无此项 |
| 8 | detail ×5 | 有图/无图、已/未收藏、好玩/资讯/好买 | 返回回到来处 |
| 9 | search | 初始/有结果/无结果；只搜已加载日期 | 三态都出 |
| 10 | 状态 | 各页 加载（骨架）/ 空 / 出错 | 每页三态 |
| 11 | cal / cal-empty | 底部 sheet（sheet 色、r20、sh-sheet、遮罩 scrim-sheet）；7 列 44 格；有存档正常、无存档灰；选中红底白字；点无存档 toast「这一天没有存档」 | 选日加载该天；空日 toast |
| 12 | columns / columns-tag | ≡ 进入；按来源 / 按标签；行 = 图标 + 名 + 今日条数 + 最新一条；含「每日简报」入口 | 两种排序可切 |
| 13 | src-github / src-x / src-world / src-channel | 统一头（图标、名、简介、更新时间）；GitHub 星数+语言；X 推文行；环球要闻 3×3 行情格（红涨绿跌）；频道列表 | 4 种来源页都出 |
| 14 | drawer | 右侧滑出 320；栏目、最近看过、收藏、设置；选中 fill + 红字；遮罩点关；Esc 关；焦点圈住 | 键盘可操作 |
| 15 | capsule / history | 看往日时顶部胶囊「10月22日 · 回到今天」；最近看过按天分组，行尾「看于 hh:mm」 | 点胶囊回今天 |
| 16 | lightbox | 纯黑底；顶关闭 + 张数；底来源 + 保存 | 亮暗都纯黑 |
| 17 | ptr-pull / ptr-loading | 下拉区 56 | 下拉触发刷新 |
| 18 | toast-action / toast-error | 带一个文字动作（撤销/重试） | 动作可点；不叠加 |
| 19 | offline / offline-none | 离线条显示缓存时间；无缓存空态 + 重试 | 断网模拟两态 |
| 20 | first / pwa | 首启一屏说明 + 开始；PWA 安装 sheet，图标 64 | 只首启出现一次 |
| 21 | d-today / d-news / d-hot / d-play / d-buy / d-fav / d-pwa（1440） | 左侧栏 220 + 主列（资讯/热点 720）+ 右栏 340 热点榜；瀑布流 4 列间距 24；底栏换左侧栏 | 7 屏都出 |

预览 #screens 共 29 张新/改屏（22 手机 + 7 桌面），加上原有主页面、详情、搜索与状态，本轮覆盖视觉系统全部屏。

## 4. QA 截图清单（每张亮 + 暗）
Playwright Chromium，手机 402×874 DPR 3，桌面 1440×900。文件名 `qa/v03/<id>-<light|dark>.png`，与 `design/pr24-diff/new-screens/` 和预览逐张并排对比。
- 手机：today、today-bottom（滚到底，验底栏）、news、news-quick、news-bottom、hot、play、play-bottom、buy、buy-bottom、fav、fav-bottom、mag、detail-img、detail-text、search-init、search-result、search-empty、loading、empty、error、cal、cal-empty、columns、columns-tag、src-github、src-x、src-world、src-channel、drawer、capsule、history、lightbox、ptr-pull、ptr-loading、toast-action、toast-error、offline、offline-none、first、pwa
- 桌面：d-today、d-news、d-hot、d-play、d-buy、d-fav、d-pwa
- 共 48 屏 × 2 = 96 张。设计 bot 对照签字后才算过。

## 5. 测试计划（全部本地跑，GitHub Actions 额度已用完）
1. `python -m pytest tests/`：现有测试全过（含 test_public_privacy、test_news_browser）。
2. `node --test tests/*.test.js`：现有 JS 测试全过。
3. 新增 `tests/test_visual_tokens.py`：构建产物 CSS 只用 tokens 变量；无旧变量、无 #EEE8DF、无渐变背景；底栏 padding 规则存在且未被覆盖。
4. 新增 Playwright 脚本 `tools/qa_v03.py`（用已有 Playwright，不加依赖）：生成 §4 截图；对每个滚动页滚到底，断言最后一项 bottom ≤ 底栏 top − 16；对 §2 关键值用 `getComputedStyle` 比对 tokens（复用 `design/pr24-diff/capture.py` 的方法）。
5. 暗色：同脚本 `colorScheme: 'dark'` 再跑一遍。
6. 可访问性：图标按钮都有 aria-label；文字对比 ≥ 4.5:1（text-3 只用于 meta）；抽屉/sheet 焦点管理。
7. PR 描述附本地运行输出和截图包路径。

## 6. 分支计划
- `spec/rebang-visual-v03`（本 Spec，基于 `feat/rebang-trial-sources`）→ Draft PR 进 main，只放文档，不合并。
- Spec 获批后：实现分支 `feat/rebang-visual-v03` 从 `spec/rebang-visual-v03` 切出（含 #24 的源工作），另开 PR 进 main；#24 关闭并在描述里指向新 PR。
- 不强推；合并和部署都要阿欢本人批准。

## 7. 不做
- 无图文字卡改动；新增数据源或改抓取逻辑；后端/feeds 管线；
- 资讯详情正文（线上无正文）；设置/订阅邮件；好买官方价数据接入（有数据才显示，无数据不显示）；
- 新依赖、框架、换图标库；部署（另走运维流程）；「北京」分组是否在公开版隐藏的产品决定。

## 8. 风险
- 骨架重写面大，按页提交，每页带截图。
- #24 的 CSS 覆盖链复杂，先删旧样式再加新样式，避免叠加。

## 9. 开放问题（附建议）
- Q1 底栏下方实底 + 渐隐的具体值：等设计更新 DESIGN.md。建议渐隐 24px、`--c-bg` 透明→实色，作为默认。
- Q2 分类文字选中字重 400 还是 600（DESIGN.md 标待定）。建议 400 + 红下划线，按视觉系统。
- Q3 资讯列表图暗色压暗滤镜是否保留。建议去掉，按视觉系统原图。
- Q4 好玩/好买分组名和「北京」组是否公开显示。建议本轮按设计示例分组做，「北京」先保留，产品后续再定。
