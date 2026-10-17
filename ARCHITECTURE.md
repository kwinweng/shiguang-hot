# 拾光聚合平台

## 模块与配置

`pipeline.py` 保留 Telegram t.me/s 抓取、SQLite 增量去重、14 天图片缓存和热点评分。
`textclean.py` 把消息正文清洗为标题与正文：优先【标题】、其次开头粗体、再次首句；网址和「====」分隔线不进入标题，正文去掉裸网址，只剩标题时正文留空。
`feeds.py` 管理 JSON 配置、四种适配器、验证和图片压缩。
`items.py` 把 TG 消息与 inbox 条目统一为 `Item`（来源、子来源、分类、时间、图片、链接）；`render.py` 只含 HTML 模板，按页面上下文生成相对链接，不读写文件；`sitebuild.py` 只负责取数、排序、组页、隐私自检和原子发布。新增来源或调整版式通常只需改其中一层。
`icons.py` 定义图标与 sprite；`style.css`、`app.js` 以内容哈希命名（如 `style.<hash>.css`）独立发布，浏览器可长期缓存，无需手动改版本号；仅更新栏目时保留旧哈希文件，避免上次完整构建的页面失去样式。`build_icons.py` 生成蓝色图标、manifest 并检验边缘。
`validate_feed.py` 为独立投递校验入口；规范见 INGEST.md。`mailbuild.py` 兼容旧入口，仅重建内网 inbox。

`sources.json` 声明 id、type、name、icon、color、visibility、nav（enabled/order）。
Telegram 使用 channel；inbox 使用 directory、filename、adapter（native/mail/world/x）和可选 env。
`x` 使用平铺 `/workspace/x-digest/YYYY-MM-DD.json`，filename 为 `{date}.json`；`latest.json` 仅补缺失日期，忽略 Markdown。`X_FEED_DIR` 可覆盖目录，公开输出仍为原生 feed.json，保留最近 14 天。
分类正则位于 categories。导航按顺序自动生成；inbox 有合法数据才显示。
手机底栏与桌面导航使用顶层 `nav.tabs` 的五个固定槽位：private 为邮件、日报、首页、资讯、推特爆款；public 为收藏、日报、首页、资讯、推特爆款。首页必须居中，以透明玻璃描边的 inline SVG 房屋显示，不显示文字，aria-label 为首页；缺数据的栏目保留禁用槽位，不生成空页。资讯继续使用 hot.html。底栏只有当前项使用 sun 填充。
`nav.favorites` 配置 enabled、label、path、column，控制收藏页、菜单入口与栏目入口。两种模式菜单均保留 all.html。收藏页只生成空容器，由客户端读取 localStorage 后呈现，可逐条移除，空列表显示温和提示。
每张信息卡提供书签按钮，aria-pressed 表示状态，aria-label 使用收藏或取消收藏。仅存储 id、title、url、source、time、snippet；id 由来源、原始 id 或链接或标题及时间的 SHA-256 生成。收藏不会上传；public/private 使用独立存储键，即使同源也不混用。内网邮件收藏仅留在设备浏览器，favorites.html 不嵌入任何服务端邮件卡片或正文。不同页面和标签页同步收藏状态；存储不可用时显示提示。
来源的 `nav.enabled` 和 `nav.order` 只控制「栏目」行及菜单，不再争夺第五个槽位。所有有数据且启用导航的 inbox 均出现在栏目行和菜单，包括 world、github、hot-daily；菜单另含核心页面及有数据的 TG 频道页。链接使用相对路径，支持 Pages `/tg-digest/`。

## 视觉规范

「光」：sun #e3a01e 是唯一强调色，只作填充（底栏当前项、徽标太阳圆点、前三名排名、收藏后的书签），不用于文字、描边或轮廓；`test_render.py` 会检查 style.css 是否违反。界面外壳采用液态玻璃：`.glass` 为较实的「常规玻璃」（模糊 + 饱和、顶部高光、细边与固定斜向高光），用于顶栏、底栏、吸顶分类等盖在正文上的地方，保证文字可读。

**图标**：`icons.py` 定义唯一一套 24×24、1.75 描边的线性图标，每页在 body 顶部输出一次 SVG sprite，其余位置用 `<use href="#i-名称">` 引用。每个图标有「主体」路径，用 `--i-fill` 着色：默认透明为线框，当前项、已收藏等状态设置填充色，同一个图标即可表现两种状态。sources.json 的 icon 键（home/hot/all/archive/mail/world/x/code）映射到图标名，未知键回退为 list。栏目和页面标题使用 `badge`：柔和底块 + 线性图标 + 右上角太阳圆点（「拾光」的光）。

**组件**：`render.py` 里每种组件一个函数，类名与 style.css 分节一致：卡片 `card`（元信息行、标题、正文、配图、操作行）、栏目块 `tile`、筛选 `chip`、输入 `field`、面板 `panel`、分组标题 `group`、空状态 `empty`、导航面板 `sheet`、提示 `toast`。app.js 只依赖 id 与 data-* 属性，不依赖样式类名。卡片只有一行元信息：来源色点（取 sources.json 的 color）· 子来源 · 分类（与来源同名或「综合」时省略）· 时间；收藏书签在操作行右侧。单张实拍图在标题右侧，截图类以通栏横幅显示，多图最多三张一行。

**动效**：时长分四档（按压 120ms、状态 220ms、移动 420ms、翻页 320ms），弹簧曲线由弹簧方程生成（`linear()`，旧浏览器回退到 cubic-bezier）。
- 翻页：跨页面 View Transitions，顶栏和底栏不动，内容轻微上移淡入；底栏当前项的太阳色块是独立元素，位于各标签之下，在两页之间滑动。
- 按压：所有可点控件按下时轻微缩小。卡片随滚动进入视口时轻微上浮（scroll-driven，静止状态始终完整可见）。
- 收藏：书签弹跳并填充，底部提示「已收藏 · 查看」；取消时提示「已取消收藏 · 撤销」，收藏页中卡片先淡出再收起。
- 展开全文：正文高度平滑展开、收起，箭头旋转；正文未被截断时不显示按钮。
- 图片：从缩略图放大到全屏（View Transitions），按 Esc、点外部或向下拖动关闭。
- 导航面板：手机上从底部弹起，可向下拖动关闭；桌面端从菜单按钮下方出现。
- 滚动：顶栏在内容滑入其下时出现阴影；向下阅读时底栏让开，向上滚动即回来；点当前标签回到顶部；下拉刷新时太阳图标随拉动旋转。
- 系统开启「减少动态效果」时，以上动画与翻页过渡全部关闭。

## 首页与跨来源日报

渲染层将 TG 消息和 inbox sections 归一化为带 source_id、日期、正文、图片的卡片；每张卡片标明注册来源。仅有 blocks 的期刊也生成首页候选。首页候选取每个 inbox 最新一期以及 TG 消息，与 nav.enabled 无关；visibility 在加载前过滤，邮件只进入内网构建。
`home_weight` 默认 1，排名为 weight / (1 + 消息年龄小时数 / 24)，未来时间按年龄 0 处理。每个来源按排名取 `home_cap` 条（TG 默认 4，inbox 默认 8）；按轮次混排，每轮每来源最多一条。此刻要闻为首条，剩余为首页信息流，头条也计入限额。五个 TG 频道合计默认最多 20 条，避免单一频道占满首页。
日报入口 archive/index.html 展示最新有数据日期的跨来源摘要，并链接各日 archive/<date>.html。日期取 TG 和所有可见 inbox 的并集，不受首页限额影响。inbox 按 `daily_order` 升序（默认 45），再按 nav.order、id 排序；当前配置为今日重点 0、邮件精华 10、环球要闻 20、推特爆款 30、GitHub 热门 40。每个来源保留 blocks 和全部条目，最后 TG 资讯按话题分组，频道按 daily_order（默认 50）排序。无数据的来源不显示。

## 两种模式与数据流

默认公开模式：

1. Actions 每小时运行 pipeline.py，从配置中的 public Telegram 频道抓取。
2. 消息按 `(channel,id)` 写入 tg.db，配图进入 media/，Actions cache 保存图片。
3. public inbox 仅从仓库 public-feeds/<id>/<date>/feed.json 读取。
4. 生成 site/ 后进行 private 目录、栏目名与路由检查，再由现有 Actions 部署 Pages。
5. all.html、hot.html、archive/index.html 和每日 archive/<date>.html 保留。

内网模式由 `SITE_MODE=private` 开启，兼容 `MAIL_DIGEST=1`：

1. /workspace/tg-local/sync.sh 获取共用 flock。
2. 工作区有 tg.db、public-feeds/ 以外的改动则记录并跳过 pull，仍可继续本地构建。
3. 否则还原 tg.db、移除 journal，执行 pull --rebase --autostash。
4. publish_public.py 仅处理配置中 public inbox，适配、压图、原子写 JSON，保留最近 14 天。
5. public-feeds 有变化才暂存、提交和推送；暂存前后检查路径仅在 public-feeds/ 下，并再次检查 visibility。
6. pipeline.py 内网构建包含 public 与 private，原始目录优先；本机原始数据缺失才回退原生投递与 public-feeds。
7. 每期输出 <id>/<date>.html，最新输出 <id>/index.html，页面内含往期列表；图片位于 <id>/img/。
8. 还原本机 tg.db，不提交本机数据库；确认只绑定 127.0.0.1:8766 的 serve.sh 在服务。

`inbox_sync.sh` 与 sync.sh 共用锁，仅更新 inbox 栏目页；`mail_sync.sh` 是其别名。
只更新栏目时首页和 TG 页面保持上次完整构建的快照；新来源进入全站导航、首页混流需完整 sync。
本机脚本在 /workspace/tg-local，不在本仓库内。

## 添加来源

新增 Telegram：只增加一个 type=telegram 配置，填写 channel、唯一 id、名称、配色及可见范围。
新增原生栏目：只增加 type=inbox、adapter=native 配置；将合法 feed.json 和图片原子写入约定目录。
原生 public 栏目包括 `github`（GitHub 热门）和 `hot-daily`（今日重点，导航 order 26）。`hot-daily` 仅取自 5 个公开 TG 频道，由「热点日报」bot 每晚北京时间 22:00 生成，写入 `/workspace/feeds-inbox/hot-daily/YYYY-MM-DD/feed.json`，沿用通用 public inbox 发布流程。
无需修改渲染代码。有数据即自动加入首页和对应日期日报；用 home_weight、home_cap 控制首页，用 daily_order 控制日报顺序。来源 nav.enabled/order 控制栏目与菜单；底栏需显式修改顶层 nav.tabs，新增来源不会挤走固定槽位。图标 key 支持 home/hot/all/archive/mail/world/x/code，未知 key 回退 all。
需要导航的 inbox 设置 nav.enabled=true 和 order。无有效数据时隐藏入口，不生成空栏目。
本机执行 validate_feed.py <id>，再运行 sync.sh。public 内容经 publish_public.py 进入仓库后，Actions 才能获得。
可用 publish_public.py --no-push 仅准备文件，不执行 git 操作。

## 安全边界

private 原始输入和产物永不入 git。site/、proposal/、mail-digest/、feeds-inbox/、private-feeds/ 均忽略。
完整构建先清空 site，防止从内网切换公开时残留私有页面和图片。
公开内容加载器仅枚举 public 来源，不从本机 inbox 载入公开内容；自检可只读 private 原文，比对长标题与正文以发现误混内容。发布器只枚举 public 来源并拒绝未知来源目录。
输入 HTML 全部转义；链接只接受 HTTP/HTTPS；图片路径必须在当期目录内，限制格式和 10 MiB，转换后长边最多 1200px。
不使用投递内容声明 visibility，也不将 private 数据复制到 public-feeds。
不要将示例、私人附件或 proposal 放入 public-feeds；本机同步锁可防止同步脚本相互覆盖。

公开 TG 新闻中的普通“邮件”用词显示为同义词“电邮”，使公开产物不含私有栏目的字面标记；原始数据库不改写。
