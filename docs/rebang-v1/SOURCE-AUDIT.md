# 来源盘点与归档清单（串行计划第 3 步，2026-11-25）

分支 `chore/source-audit-archive`，基于 `main` `78b8d10c`。本文只是清单：**没有删除、归档或停用任何文件、来源或例程**，下面的「归档 / 删除」都是候选，等阿欢过目后另开分支逐项执行（删文件、停采集属红灯）。

本分支实际做了三件事（阿欢 11/25 已在聊天里确认）：

1. 加 8 个免登录官方订阅（见 §1）。
2. 撤掉博主页里没有名单的「知乎」占位（`rebang/contract/bloggers.json`、`rebang/bloggers/run.py` 的 `ALL_PLATFORMS`）。热搜里的知乎热榜不受影响。
3. 写这份清单。

## 1. 本次新加的 8 个订阅

一个来源只进一个频道。都写在 `rebang/contract/channels.json`（`type: feed`），不进 `sources.json`（那份只驱动旧站和 TG 采集，BBC、卫报等现有订阅也不在里面）。2026-11-25 每个地址用 curl 只读拉过一次，都返回 200 和有效 RSS，前 2 条存成离线样本 `tests/fixtures/rebang/ingest/sources-20261125/`，用例在 `tests/test_rebang_sources_20261125.py`。

| id | 名称 | 频道 | 订阅地址 | 地址依据 |
|---|---|---|---|---|
| `cna-world` | CNA International | 环球 | `https://www.channelnewsasia.com/api/v1/rss-outbound-feed?_format=xml&category=6311` | CNA 官方 RSS 目录页 `channelnewsasia.com/rss` 列的 World（6311）；样本 20 条中 16 条是 `/world/` |
| `france24-en` | France 24 English | 环球 | `https://www.france24.com/en/rss` | 订阅自带 `atom:link rel=self` 即此地址；官方英文总订阅（含少量体育、节目） |
| `dw-world` | DW World | 环球 | `https://rss.dw.com/xml/rss-en-world` | 订阅自带 `rel=self`，频道标题 `World \| Deutsche Welle` |
| `npr-world` | NPR World | 环球 | `https://feeds.npr.org/1004/rss.xml` | `npr.org/sections/world/` 页面的 `<link rel=alternate>` |
| `android-authority` | Android Authority | 数码 | `https://www.androidauthority.com/feed/` | 订阅自带 `rel=self` |
| `macrumors` | MacRumors | 数码 | `https://feeds.macrumors.com/MacRumors-All` | `macrumors.com` 首页的 `<link rel=alternate>` |
| `selfhst` | selfh.st | 工具与项目 | `https://selfh.st/rss/` | `selfh.st` 首页的 `<link rel=alternate>`；每周一期 Self-Host Weekly，条数少 |
| `itsfoss` | It's FOSS | 工具与项目 | `https://itsfoss.com/rss/` | `itsfoss.com` 首页的 `<link rel=alternate>`；会跳转到 `feed.itsfoss.com`（FeedPress） |

上线后要留意的事：

- 环球从 2 个源变成 6 个，线上 11/25 17:39 那版环球只有 35 条，工具与项目 57 条、数码 148 条；这三个频道都会明显变厚。
- 新源全是英文，会进翻译队列（`var/rebang/translate/pending.json`），DeepSeek Flash 的用量会上升；全文抽取每轮仍最多 40 篇（`rebang/extract` 的 `MAX_FETCH_PER_RUN`），不会因为加源变成无上限。
- It's FOSS 的条目链接是 FeedPress 跳转地址（`feed.itsfoss.com/link/...`），点开会跳到原文，但跨来源按链接去重时认不出是同一篇。第 5 步做去重时再考虑要不要解跳转。
- France 24 的总订阅偶尔有空摘要的直播条，属于原文如此，前端显示「无正文」。
- 健康看板会多出 8 行；首轮抓取前它们显示「未配置 / 尚无采集记录」，抓过一轮就正常。

## 2. 配置文件盘点

### 2.1 `rebang/contract/*.json`：全部在用

| 文件 | 结论 | 说明 |
|---|---|---|
| `channels.json` | 在用 | 6 频道与来源（本次后：18 个 TG、14 个订阅、1 个 GitHub Trending 页）；`highlights` 规则在用；`excluded_sources` 是旧 id 黑名单，保留 |
| `bloggers.json` | 在用 | 本次撤掉知乎后剩 6 个平台：X 16、博客 7、即刻 9、微博 6、公众号 6、YouTube 13 |
| `hotsearch.json` | 在用 | 百度、知乎、B 站热搜 |

### 2.2 `sources.json`（23 项）：一半在用，一半只剩旧站在用

| 内容 | 结论 | 说明 |
|---|---|---|
| 18 个 TG 频道 | 在用 | `pipeline.py` 每小时抓到 `tg.db`，新站 `rebang.ingest` 从 `tg.db` 读；`tests/test_rebang_contract.py` 要求新站的 TG 必须先在这里登记 |
| `reorx_share` | 停采候选 | 新站 11/15 起排除，但 `pipeline.py` 仍每小时抓它，只给已不对外的旧站用。要停须改采集名单（红灯，等批准） |
| inbox `hot-daily`（今日重点） | 在用，但现在实际不生效 | 见 §4 |
| inbox `world`（环球要闻）、`x`（推特爆款）、`github`（GitHub 热门） | 归档候选 | 11/22 起新站不再读这三份整理稿，只有旧站构建还在读；Mac mini 上也没有它们的投递目录。随旧站一起归档 |
| `topics`、`hot` 两段 | 归档候选 | 只给旧站的分类和热点用，新站不读 |

### 2.3 `trial-sources.json`（旧站「探索」13 个源）：在抓，但没人看

`pipeline.py` 每小时调 `shiguang/ingest/trial.py` 把这 13 个源抓进 `tg.db` 的 `trial_item` 表，只给旧站「探索」页用；旧站 11/16 起已不对外提供，所以这些抓取现在只是在占请求和库空间。阿欢希望尽量保留活跃源，下面是**频道归属方案，本分支不实施**：

| 源 | 现在怎么抓 | 建议 | 理由 |
|---|---|---|---|
| 少数派（Matrix，经 RSSHub 镜像） | `rsshub.ktachibana.party/sspai/matrix` | 迁到「工具与项目」，改用官方 `https://sspai.com/feed` | 官方订阅 11/25 实测 200、10 条，不依赖公共 RSSHub |
| TG 少数派 `sspai` | t.me 公开页 | 不迁（与上面重复） | 同一家只留一个，官方 RSS 更稳 |
| 小众软件 | `https://www.appinn.com/feed/` | 迁到「工具与项目」 | 11/25 实测 200、10 条 |
| TG `Apps_Share`（iOS 限免） | t.me 公开页 | 可选：迁到「工具与项目」 | 会让 TG 从 18 个变 19 个，要改「18 个 TG」的约定（DECISIONS 11/15），须阿欢点头 |
| 9to5Mac | `https://9to5mac.com/feed/` | 可选：迁到「数码」 | 11/25 实测 200、100 条；和本次加的 MacRumors 题材重叠很大，建议先看 MacRumors 一周再定 |
| Apple Newsroom | 同新站 | 不迁（新站「数码」已有） | 探索这份是重复的 |
| 拓竹博客 | `https://blog.bambulab.com/rss/` | 可选：迁到「数码」 | 3D 打印硬件，量很小（4 条） |
| 机核 | `https://www.gcores.com/rss` | 暂不迁，归档 | 游戏文化，6 个频道都不贴；要保留就得新开频道（改产品方向，须批准） |
| Steam | `store.steampowered.com/feeds/news.xml` | 暂不迁，归档 | 同上，没有游戏频道 |
| What's on Netflix | RSS | 暂不迁，归档 | 影视，没有对应频道 |
| EarthSky | RSS | 暂不迁，归档 | 天文科普；博主页已有 Dr. Becky、AstroBackyard |
| UCCA 北京 | 网页解析 | 暂不迁，归档 | 北京展览，不是资讯；网页解析易坏 |
| 豆瓣同城·北京本周 | 网页解析 | 暂不迁，归档 | 同上 |

迁移前要先做的一件技术改动：新站 `rebang/ingest/core.py` 把所有订阅一律标成英文（`FEED_LANG = 'en'`），少数派、小众软件是中文，直接加进去会被当成英文送去翻译。迁中文订阅前要先让订阅也按内容判语言（现在只有网页类来源这样判）。

探索整体建议：先按上表迁 2 个（少数派官方 RSS、小众软件），可选的 3 个等阿欢定；迁完后再停 `trial.run`、归档 `trial-sources.json` 和 `shiguang/ingest/trial.py`。`tg.db` 里的 `trial_item` 表不删。

## 3. 旧站代码盘点

旧站 = `pipeline.py` + `shiguang/` + `web/`，产物是 `site/`。新站现在还离不开它，有两条硬依赖：

1. **TG 采集**：Mac mini 每小时 `tools/mac_publish.py` 先跑 `pipeline.py`（抓 TG、抓探索、建旧站），再跑 `tools/rebang_refresh.sh`（新站）。新站的 TG 条目全部来自 `pipeline.py` 写的 `tg.db`。
2. **服务器校验**：服务器 `news-sync` 按旧站格式检查 gh-pages（`index.html` public 标记、`data/live.json` 两小时内新鲜度、文件数下限等，见 `deploy/README.md`），旧站树缺了整次不同步。改这项要动服务器（红灯）。

另外新站代码直接 import 了旧代码（迁移前不能动这些模块）：

| 新站位置 | 用到的旧代码 | 作用 |
|---|---|---|
| `rebang/ingest/core.py` `default_http_get` | `shiguang.ingest.http` | 所有订阅和网页的 HTTP 请求 |
| `rebang/ingest/core.py` `parse_feed` | `shiguang.ingest.web` →（间接）`shiguang.ingest.telegram`、Pillow | RSS/Atom 解析 |
| `rebang/ingest/core.py` `_tg_clean` | `shiguang.ingest.telegram.channel_text` | TG 文本清洗 |
| `rebang/ingest/core.py` `default_inbox_loader` | `shiguang.ingest.feeds.load_issues` → `shiguang.ingest.adapters`、`shiguang.config` + `sources.json` | 今日重点读整理稿 |
| `rebang/bloggers/run.py` | `shiguang.ingest.http` | 博主抓取的 HTTP 请求 |

### 3.1 清单

| 路径 | 结论 | 说明 |
|---|---|---|
| `pipeline.py` | 在用 | TG 采集 + 旧站构建，Mac mini 每小时跑 |
| `shiguang/ingest/telegram.py`、`scheduler.py`、`http.py`、`web.py` | 在用 | TG 采集与调度；`http`/`web`/`telegram` 还被新站直接 import |
| `shiguang/ingest/feeds.py`、`adapters.py`、`shiguang/config.py` | 在用 | 今日重点读整理稿靠它们；旧站也用 |
| `shiguang/ingest/trial.py` + `trial-sources.json` | 归档候选 | 探索迁完后停（§2.3） |
| `shiguang/enrich/`（clean、topics、hot、rank） | 在用（仅旧站构建） | 新站不用；旧站停建后归档 |
| `shiguang/site/`、`web/` | 在用（仅为通过服务器校验） | 旧站页面已不对外；服务器校验改掉之前不能停建 |
| `shiguang/site/history.py` 的 `RETIRED` | 在用 | `pipeline.py` 用它保留已退役频道的历史消息 |
| `public-feeds/` | 归档候选 | 最后一次数据 10/23；目前只是旧站和今日重点的兜底目录（兜到的是过期数据，见 §4） |
| `tools/mac_publish.py`、`mac_publish.sh`、`rebang_refresh.sh`、`publish_pages.sh`、`write_build_info.py`、`persist_action_data.sh` | 在用 | 生产发布链路 |
| `tools/rebang_mac_refresh.sh` | 在用（手动入口） | 设置四路整理目录后调 `rebang_refresh.sh`；定时发布没走它（§4） |
| `tools/translate_deepseek.py` | 在用 | 清翻译队列 |
| `tools/box_scrape.py`、`box_scrape.sh`、`box_cron.example` | 待确认 | 旧机器「热榜抓取发布」例程的入口；发布已迁到 Mac mini，旧例程是否已停须阿欢确认，停之前不动 |
| `validate_feed.py`（根目录）、`tools/validate_feed.py` | 待确认 | 注释写「投递 bot 仍按旧路径调用」，可能是今日重点生产方在用；确认前保留 |
| `feeds.py`（根目录） | 归档候选 | 给盒子上 `publish_public.py` 的兼容入口；`public-feeds` 10/23 起已不再推送 |
| `mailbuild.py` | 删除候选 | 内网版 inbox 重建入口，内网版已停用 |
| `tools/login_gate.py` | 删除候选 | 内网登录，已停用（`docs/legacy/PRIVATE_LOGIN.md`） |
| `tools/dispatch_hourly.py` | 删除候选 | GitHub Actions 外部触发，已被本机采集取代、未接任何例程；注意改名分支动过它，删前先对齐第 6 步 |
| `tools/daily_summary.py` | 删除候选 | 旧站回顾的 MOCK 摘要，没有例程调用 |
| `tools/benchmark_news_history.py`、`check_two_modules.py`、`screenshot.py`、`build_icons.py`、`trial_report.py` | 归档候选 | 旧站开发、验收工具，随旧站一起归档 |
| `tools/build_rebang_icons.py` | 在用 | 新站图标 |
| `rebang/push/`（8:30 私聊稿） | 归档候选 | 08:30 私聊 11/17 定不做（NOT-DOING），刷新脚本也不调它 |
| 仓库根目录 `screenshot.png` | 删除候选 | 旧站时期的截图，只在改名方案里被提到 |
| `deploy/`（news-sync） | 在用（参考） | 服务器上装的是单独一份，改名时以服务器现装版本为准 |
| `docs/legacy/` | 保留 | 历史记录 |
| 旧站测试：`tests/test_feeds.py`、`test_render.py`、`test_sitebuild.py`、`test_news_*`、`test_trial.py`、`test_box_scrape.py`、`test_login_gate.py` 等 | 随对应代码处理 | 代码归档或删除时一起动，不单独删 |

### 3.2 建议的执行顺序（每步一个分支，都等批准）

1. 先修今日重点的输入（§4），这是线上现在真实缺的功能。
2. 探索按 §2.3 迁 2～5 个源（先做订阅按内容判语言），迁完停 `trial.run`。
3. 删 4 个删除候选（`mailbuild.py`、`tools/login_gate.py`、`tools/dispatch_hourly.py`、`tools/daily_summary.py`）和根目录 `screenshot.png`，连同各自测试。
4. 把新站直接 import 的 `shiguang.ingest.http/web/telegram/feeds` 搬进 `rebang/`，新站不再 import `shiguang`。
5. TG 采集从 `pipeline.py` 搬到新站，服务器 `news-sync` 校验改成检查新站产物（服务器改动，红灯）。做完这步旧站才能真正停建、整体归档（`pipeline.py`、`shiguang/`、`web/`、`public-feeds/`、`sources.json` 中旧站专用的部分）。

和第 6 步改名的关系：上面 3～5 会大量删改 `rebang/`、`tools/` 里的文件，建议排在第 6 步改名之前做完，省得改名时连带改要删掉的东西。

## 4. 「今日重点」在新版里的依赖链

结论：**仍然依赖旧站代码，而且线上现在实际没有今日重点标记。**

依赖链：

1. 生产方：「资讯」bot 在阿欢电脑上每天生成 `hot-daily` 整理稿（`<日期>/feed.json`），不在本仓库（DECISIONS 11/17）。
2. 投递目录：`sources.json` 里 `hot-daily` 的 `directory` 是盒子路径 `/workspace/feeds-inbox/hot-daily`，可用环境变量 `HOT-DAILY_FEED_DIR` 覆盖。
3. 读取：`rebang/ingest/core.py` `apply_highlights` → `default_inbox_loader` → 旧代码 `shiguang.ingest.feeds.load_issues(sources.json 的 hot-daily 项, local=True)`，按顺序找 ① `HOT-DAILY_FEED_DIR` 或 `/workspace/feeds-inbox/hot-daily` ② `/workspace/feeds-inbox/hot-daily` ③ 仓库 `public-feeds/hot-daily/`。读到的稿经 `shiguang.ingest.adapters` 规整、`shiguang.ingest.feeds.validate` 校验。
4. 打标：只看最近 14 天的稿，把稿里链接和频道条目按规整后的链接比对，同链接的打 `highlight`；对不上的只计数，不单独成条。
5. 展示：`rebang/site` 原样带出，前端卡片显示「今日重点」角标。

线上现状（推断 + 线上核对）：

- Mac mini 定时发布走 `tools/mac_publish.py`，它只把 `PATH`、`HOME`、`TMPDIR`、`SSH_AUTH_SOCK` 传给子进程，直接调 `tools/rebang_refresh.sh`，**没有经过**会设置 `HOT-DAILY_FEED_DIR` 的 `tools/rebang_mac_refresh.sh`。
- Mac 上没有 `/workspace/...`，于是落到 `public-feeds/hot-daily/`，最后一期是 2026-10-22，早于 14 天窗口，打标数为 0。
- 就算走 `rebang_mac_refresh.sh`，默认目录也是 11/17 23:24 的交接快照，不会有新稿，快照里的稿会陆续滑出 14 天窗口。
- 11/25 只读拉了线上 `news.kwinweng.com`（`built_at` 2026-11-25T17:39+08:00）6 个频道的第一页，共 180 条，`highlight` 全是 0，和上面推断一致。（生产机上的 ingest 状态没去看，本任务不碰 Mac mini。）

要让今日重点恢复，需要阿欢定一件事：今日重点的整理稿以后从哪来（让「资讯」bot 持续同步到 Mac mini 的某个目录，或者等第 5 步改成站内自动打分、不再要整理稿）。前一种还要把那个目录传进定时发布（改 `mac_publish.py` 或启动配置），属于生产发布链路改动。第 5 步做完自动打分后，`hot-daily`、`load_issues` 这条旧依赖就可以整条拿掉。

## 5. 要阿欢过目的事

1. §1 的 8 个源和频道归属（已实现，等合并）。
2. §2.3 探索归属方案：建议先迁少数派（官方 RSS）、小众软件到「工具与项目」；Apps_Share（会变成 19 个 TG）、9to5Mac、拓竹博客要不要迁；机核、Steam、Netflix、EarthSky、UCCA、豆瓣同城是否同意归档。
3. §3.1 的删除候选 4 个文件 + 根目录截图；「待确认」两项（旧机器 `box_scrape` 例程是否已停、投递 bot 是否还调 `validate_feed.py`）。
4. §4 今日重点：整理稿以后从哪来，还是等第 5 步自动打分。
5. `reorx_share` 是否停采。
