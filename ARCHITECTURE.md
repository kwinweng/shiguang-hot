# 拾光热榜 · 架构

一条线：**来源 → 条目 → 页面**。每个渠道先变成同一种条目（`Item`），再按时间（今日、热点）或按渠道、标签（栏目）去取；没有为某个来源单独写的页面。接新渠道只动第一层：在 `sources.json` 加一项，按 `INGEST.md` 投递。

## 代码分层

| 位置 | 做什么 |
| --- | --- |
| `pipeline.py` | 入口：抓 TG 和 RSS/YouTube → 清洗、分话题 → 热点 → 建站。`main(now=None)` |
| `shiguang/config.py` | 读取并校验 `sources.json`，补默认值；兼容旧字段名 |
| `shiguang/ingest/telegram.py` | 抓 t.me/s 公开页写入 `tg.db`，图片缓存在 `media/`（按消息时间保留 14 天） |
| `shiguang/ingest/web.py` | RSS 2.0 / Atom（含 YouTube 频道）抓取解析，存进 `tg.db` 的 `entry` 表，首图缓存 14 天 |
| `shiguang/ingest/feeds.py` | 找到各 inbox 来源的每一期、校验、压缩图片 |
| `shiguang/ingest/adapters.py` | mail / world / x 三种旧格式转成统一格式（这些 bot 改写统一格式后删除） |
| `shiguang/model.py` | `Item`，以及把 TG 消息和期刊条目变成 `Item` 的函数 |
| `shiguang/enrich/` | `clean.py` 标题与正文清洗；`topics.py` 标签；`hot.py` 热点（热度与按时间排序）；`rank.py` 当天排序 |
| `shiguang/site/pages.py` | 每个页面一个函数：决定哪页放哪些条目 |
| `shiguang/site/render.py` | 纯 HTML 组件，不读写文件；`icons.py` 图标；`light.py` 环境光 |
| `shiguang/site/build.py` | 在临时目录建整站 → 公开版隐私检查 → 原子替换 `site/`；CSS/JS 用内容哈希命名 |
| `web/` | `style.css`、`app.js`、`assets/`（图标、manifest） |
| `tools/` | `validate_feed.py` 投递校验、`screenshot.py` 截图、`build_icons.py` 生成图标 |
| `tests/` | `python3 -m unittest discover tests` |

内网版的登录（登录页 + 180 天 Cookie，代替 Basic Auth）由 `tools/login_gate.py` 提供，接入 nginx/Caddy 的方法见 `PRIVATE_LOGIN.md`。

根目录另有几个兼容入口，给本机脚本用：`run.sh`、`mailbuild.py`（本机定时任务调用）、`validate_feed.py`（投递 bot 调用）、`feeds.py`（`publish_public.py` 可能 `import feeds`，其 `config()` 仍返回旧字段）。本机脚本收进仓库后删除后两个。

## 页面

底栏 4 格：今日 / 热点 / 栏目 / 收藏，公开版和内网版相同。

| 页面 | 内容 |
| --- | --- |
| `index.html` 今日 | 只放今天：顶部时光机（最近 7 天的日期条 + 日历面板）；今日重点（摘要和前 3 条）；此刻要闻；当天信息流，话题胶囊和来源选择两种筛选，「展开这一天全部」；最后各栏目当天的摘要和前 3 条。早上 6 点前另附昨天的前 10 条。 |
| `archive/<date>.html` | 时光机里的某一天，和今日同一个模板，首条是当天热度最高的 |
| `hot.html` 热点 | 最近 3 天热度过线的消息，按时间倒序，按小时分段；顶部 0–24 点时间轴，每小时一根热度柱，左右拖动跳到对应时段，拖过 0 点到前一天；列表滚动时时间轴跟着走 |
| `columns.html` 栏目 | 「按渠道 / 按标签」切换（记在本机）。按渠道：每日简报、X、YouTube、RSS、电邮订阅、GitHub、Telegram、邮件，按 `platform` 分组。按标签：每个标签最近 3 天的条数 |
| `tag/<slug>.html` | 一个标签最近 3 天，按天分组，可按来源筛选 |
| `<id>/index.html` | TG 频道或 RSS/YouTube 来源：最近 3 天（至少 30 条），按天分组；期刊来源：最新一期 |
| `<id>/<date>.html` | 期刊来源的一期 |
| `favorites.html` 收藏 | 本机收藏，由 app.js 从 localStorage 呈现 |

来源页和标签页标亮「栏目」，日期页和今日重点的期刊页标亮「今日」。

合并掉的旧地址保留为跳转页：`all.html`、`archive/index.html`、`hot-daily/index.html` → 今日。

今日筛选：`?source=` 预选来源，`?topic=` 预选话题。信息流每个来源有上限（见下），当天其余条目标 `data-more` 并隐藏，选了筛选、搜索或点「展开这一天全部」时才显示。

## 规则

- **标签**：所有来源共用 `sources.json` 的 `topics`：全球、财经、AI、科技、数码、汽车、开发者、社会、娱乐，其余为「其他」。条目自带 `topic` 就用它；否则先看标题、再看全文，按顺序取第一个匹配的正则；都不匹配用来源的 `topic`（如 GitHub 热门为「开发者」）；再不行是「其他」。「其他」不显示在卡片上。
- **当天排序**：分数 = `home.weight` / (1 + 消息年龄小时数 / 24)。每个来源按分数取 `home.cap` 条（TG 默认 4，期刊默认 8），按轮次混排，每轮每来源最多一条。首条：今天是最新的一条热点，往日是当天热度最高的一条；没有热点时用排序第一条。
- **热点**：同一件事（12 小时内文字相近）只算一次，记在第一次报道上。热度 = 报道的频道数 × 4 + `hot.keywords` 命中数 + 篇幅加分（最多 2）；热度 ≥ 6 入选，两个以上频道报道的一定入选。卡片标「N 个频道」。
- **顺序**：来源的 `order` 决定栏目页、菜单和来源选择里的顺序（今日重点 0、邮件精华 10、环球要闻 20、推特爆款 30、GitHub 热门 40、TG 频道 50 起）。

## sources.json

```json
{
  "topics": [{"name": "AI", "slug": "ai", "pattern": "正则"}],
  "hot": {"source": "hot-daily", "keywords": ["美联储"]},
  "sources": [{"id": "x", "type": "inbox", "name": "推特爆款", "visibility": "public", "platform": "x", "order": 30}]
}
```

`topics` 的顺序就是筛选胶囊和匹配的顺序；`slug` 是标签页地址。`hot.source` 指定放在今日顶部的期刊（今日重点）。

| 字段 | 说明 |
| --- | --- |
| `id` `name` `type` `visibility` | 必填。`type`：`telegram`（TG 频道）、`feed`（RSS/YouTube）、`inbox`（期刊投递）；`visibility`：`public` 或 `private` |
| `platform` | 栏目「按渠道」的分组：brief / x / youtube / rss / newsletter / github / telegram / mail。默认 TG 为 telegram、feed 为 rss、期刊为 brief |
| `url` | feed 来源的地址；YouTube 用 `https://www.youtube.com/feeds/videos.xml?channel_id=<频道 ID>` |
| `icon` | 状态图标：home / hot / all / archive / mail / world / x / code，默认 all |
| `order` | 顺序，默认 TG 和 feed 50、期刊 45 |
| `home` | `{"weight": 1, "cap": 4或8}`，当天信息流的权重和条数，`cap: 0` 表示不进信息流 |
| `lead` `note` | 期刊来源页打头的一句话（`{count}` 换成条目数）和小字说明 |
| `topic` | 匹配不到标签时用的默认标签 |
| `reading` | `true` 时正文用纸面和阅读字号切换（邮件精华） |
| `channel` | TG 频道名 |
| `adapter` `directory` `filename` `env` | 期刊来源的投递位置和格式，见 `INGEST.md` |

旧写法 `topics: {名称: 正则}`、`categories`、`daily_order`、`nav.order`、`home_weight`、`home_cap` 仍能读取；`color`、`nav.enabled`、`nav.tabs`、`nav.favorites` 已不再使用。

## 两种模式与数据流

公开版（GitHub Actions 每 30 分钟，`.github/workflows/hourly.yml`；定时任务常晚几分钟）：

1. 抓取配置中 public 的 TG 频道和 RSS/YouTube 来源，写入 `tg.db`，配图进 `media/`（Actions cache 保存）。
2. 期刊只从仓库的 `public-feeds/<id>/<date>/feed.json` 读取。
3. 建站后检查：不得出现 private 来源的目录、名称或正文，以及「邮件」字样；通过后部署 Pages。

内网版（`SITE_MODE=private`，兼容 `MAIL_DIGEST=1`），在本机 `/workspace/tg-local` 的脚本里运行：

1. `sync.sh` 取共用锁；工作区干净时 `pull --rebase --autostash`。
2. `publish_public.py` 只处理 public 期刊：转换、压图、原子写 JSON，保留 14 天，有变化才提交推送 `public-feeds/`。
3. 内网构建包含 public 与 private，本机原始目录优先，其次 `/workspace/feeds-inbox`，最后 `public-feeds`。
4. `mailbuild.py` 或 `python3 -m shiguang.site.build`（`inbox_sync.sh` / `mail_sync.sh`）只重建期刊来源页，今日等页面保持上次完整构建的快照。
5. 本机 `tg.db` 不提交。

## 添加来源

- **TG 频道**：加一项 `type: "telegram"`，填 `id`、`channel`、`name`、`visibility`。
- **RSS / YouTube**：加一项 `type: "feed"`，填 `id`、`name`、`url`、`visibility`，YouTube 加 `"platform": "youtube"`。下一次构建开始抓取。
- **电邮订阅（Newsletter）**：走期刊投递，`platform: "newsletter"`；本机把邮件整理成 feed.json 后投递。
- **期刊**：加一项 `type: "inbox"`、`adapter: "native"`，按 `INGEST.md` 原子写入 feed.json 和图片。本机先跑 `python3 validate_feed.py <id>`，public 内容经 `publish_public.py` 进入仓库后，Actions 才能读到。

不需要改代码：有数据就自动进入今日、标签、栏目和菜单；没有数据不生成入口。

## 本地运行

### 试跑来源 v1

`trial-sources.json` 独立于页面来源配置，登记 13 个试跑源及数据驱动分类。
完整采集在同一数据库锁内调用 `shiguang.ingest.trial`，复用小时配额、HTTP 校验和失败退避。
试跑身份为 `trial:<id>`，仅写 `trial_item` 及采集状态表；URL 全表唯一，摘要最多 500 字，
图片只记远端地址。Telegram 复用现有公开页正文与图片地址提取，不写 msg/entry，不下载图片。
所有试跑结果均不传给页面或公开期刊发布器。`NO_FETCH=1` 同样跳过试跑且不迁移数据库。

已停用的三个频道只从数据库读出旧消息，经独立归档路径生成旧日期 HTML 与 sidecar；
元数据保存在 `history.RETIRED`，不加入现行来源、热点、标签或按渠道入口。

`python tools/trial_report.py --days 7` 只读数据库，按首次抓取的北京时间日期统计新增，
终端与 `reports/trial/YYYY-MM-DD.md` 输出一致。可用 `--db /tmp/copy.db --output /tmp/trial-reports`
检查临时库。报告包含按源、栏目、分类的小计和每源最近完整成功时间（包括零新增成功）。
`reports/` 已忽略，不提交、不发布。

离线样例放在 `tests/fixtures/trial-*`，为人工构造的代表性 HTML/XML，不代表真实站点快照。
本轮不真实抓取。页面改版适配需另以合法公开样本核对。

- `NO_FETCH=1 python3 pipeline.py`：用现有 `tg.db` 构建公开版到 `site/`，不抓取。
- `SITE_MODE=private NO_FETCH=1 python3 pipeline.py`：内网版。
- `python3 tools/screenshot.py index.html`：手机整页截图到 `shots/`；`--desktop`、`--dark`、`--build` 见 `--help`。
- `python3 -m unittest discover tests`：测试。

## 视觉规范

本站遵循「光」视觉规范：https://claude.ai/artifact/R2fskGqeaA8ozH9e7BHfNE 。颜色、字号、间距、圆角、阴影、时长都取自规范的 tokens（`web/style.css` 第 1 节），组件沿用规范的类名（`g-light`、`g-lead`、`g-card`、`g-sheet`、`g-wash`、`g-pill`、`g-btn`、`g-round`、`g-topbar`、`g-tabbar`、`g-seg`、`g-panel`）。和规范的对应：

- **光**：`shiguang/site/light.py` 是规范 `Guang` 取色的 Python 移植（主图缩到 16×24，取横 4 纵 6 余弦分量，在 OKLab 里按浅/深两套参数调色，还原成 30×40 的小图），逐格结果与规范的 bundle.js 完全一致。每页在构建时算好浅色、深色两张，铺满并四周放大 14%，上面盖薄纱和右上角暖光；没有图或读不了图时是清晨的天色。有照片的分组另带一组光（`data-light`），列表滚进哪一组，光就换成那一组的颜色，回到顶部换回本页的光。换页和换组时光都用 900 毫秒叠化。
- **表面**：信息卡是玻璃卡（不做背景模糊）；玻璃面不画边框，边缘用一组阴影画出来（`--shadow-glass`：顶部亮边、内细线、外发丝线、贴地阴影、柔和投影，借鉴 [Solid Glass](https://github.com/deeplethe/solid-glass)，MIT），卡片、圆按钮、底栏、切换器、提示条、下拉刷新共用，深浅色各有一套 `--glass-rim/inner/edge/contact/shade`；邮件正文进纸（`g-sheet`，`reading` 字号）；邮件页顶部有阅读字号切换（16.5/31、18/33、19.5/36，记在本机）；卡里再分层用冲淡块；多图是照片条（高 232，宽按比例夹在 0.56–1.78、最多 59vw，下面圆点跟随滑动）；一句话速览、市场看板等编辑/AI 的内容加金色一抹（`g-card--sun`）。毛玻璃只给浮动控件：顶栏圆按钮、底栏、提示条、下拉刷新。会盖住整页的导航面板用不透明的 `page`。
- **打头块**：每页开头是 58 的立体状态图标 + 一句 `lead`（28/32·700）+ 一行 `note`，直接放在光上。
- **图标**：`shiguang/site/icons.py` 两套，每页输出一次 sprite。功能图标是 Tabler Icons 3.48.0 线性图标（线宽 1.75，路径原样取自官方包，许可证见 `LICENSES/tabler-icons.txt`）；状态图标是本站原有的立体插画（打头 58、栏目卡 22），渐变只定义一次。
- **顶栏**：本身没有底色；滚过 30 后顶边（`edge`）淡入、中间出现当前页名。话题胶囊吸顶时接上同样的顶边。
- **底栏**：居中的胶囊，只有字，不放图标，每格 72×46、字 15/20，当前项亮玻璃；换页时亮玻璃用不回弹的弹簧滑到新位置，文字始终在它上面。电脑上改为顶栏里的玻璃切换（`g-seg`）。
- **金色**只表示「新」「今天」「进行中」：一小时内的条目带「新」，时光机里的今天带金色圆点，下拉刷新时的转圈是金色。不当字色、不做装饰。
- **品牌**：顶栏只放产品名文字，不放 logo；来源不再各配一种颜色。
- **字**：只用系统字体；字重只用 400/500/600/700；只有卡片小标题（`section`）和顶栏产品名（`brand`）有字距。`ink-3` 只给序号、箭头、占位。
- **动效**：叠化和滑动按规范时长（光 900、顶边 250、照片 240），切换类用不回弹的弹簧；系统开启「减弱动态效果」时全部直接到位，「减弱透明度」时毛玻璃换成不透明的 `page`。网页不做振动；底栏不随滚动隐藏。

`tests/test_render.py` 会检查：金色只作填充、字重与字距范围、玻璃卡不做背景模糊、光的明度范围与清晨天色、每个引用的图标都在 sprite 里。

## 安全边界

private 原始输入和产物永不入 git。site/、proposal/、mail-digest/、feeds-inbox/、private-feeds/ 均忽略。
完整构建先清空 site，防止从内网切换公开时残留私有页面和图片。
公开内容加载器仅枚举 public 来源，不从本机 inbox 载入公开内容；自检可只读 private 原文，比对长标题与正文以发现误混内容。发布器只枚举 public 来源并拒绝未知来源目录。
输入 HTML 全部转义；链接只接受 HTTP/HTTPS；图片路径必须在当期目录内，限制格式和 10 MiB，转换后长边最多 1200px。
不使用投递内容声明 visibility，也不将 private 数据复制到 public-feeds。
不要将示例、私人附件或 proposal 放入 public-feeds；本机同步锁可防止同步脚本相互覆盖。

公开 TG 新闻中的普通“邮件”用词显示为同义词“电邮”，使公开产物不含私有栏目的字面标记；原始数据库不改写。
