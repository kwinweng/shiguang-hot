# 拾光资讯 v11 模块说明

各模块的入口、输入输出、约束和已知缺口。字段定义以 [`CONTRACT.md`](CONTRACT.md) 为准，发布与服务器见 [`OPERATIONS.md`](OPERATIONS.md)。
一键全流程是 `sh tools/rebang_refresh.sh`，下面的命令都是它会调用的单步。所有 `var/rebang/`、`site-v11/` 产物都不进 git。

（本文件合并了 11/15 各功能分支的任务卡与执行记录；原任务卡已删除，见 Git 历史。）

## 数据流

```
tg.db（旧站采集写入）──┐
t.me 公开页 → tgmeta ──┼→ ingest → var/rebang/in/ingest.json ─┐
官方订阅 / Trending ───┤                                        │
今日重点原稿（仅打标）──┘                                       ├→ rebang.site → site-v11/ → publish_pages.sh（gh-pages 的 rebang/）
百度 / 知乎 / B 站 → hotsearch → var/rebang/in/hotsearch.json ──┤
博客 / Wechat2RSS / X dump → bloggers → var/rebang/in/bloggers.json ┘
                     翻译缓存 var/rebang/translate/cache.json（ingest、bloggers 入库时自动套用）
```

## tgmeta：TG 附加信息
- `python3 -m rebang.tgmeta [--store var/rebang/cache/tgmeta.json] [--channels a,b] [--fixtures DIR]`。
- 读 t.me/s 公开页，补频道自己的话、引用/转发原帖、表情、浏览数、公开评论及公开的图、视频地址；按 `<频道>/<消息号>` 由 ingest 合进条目，`tg.db` 不动。沿用原页面请求和刷新范围，不额外下载视频。Telegram 网页仅给封面（如文件太大）时，正文给原帖入口。CDN 播放失败同样可回原帖。旧缓存条目要等对应页被重新读取才会有媒体字段。
- 评论楼（2026-11-16）：开了公开讨论区的频道（现为 zaihuapd、xhqcankao、FinanceNewsDaily、CE_Observe、myBigCharacterPoster）每条最多存 30 条评论；详情页「评论楼」按时间从早到晚，先放最近 10 条，「展开更早的 N 条」看其余，楼中楼显示被回复的人和原话，每条有「原楼」链接回 t.me。
- 坑：`?before=` 翻页时转发头的名字有时为空。空名会退回作者名，新值缺失或变空时保留旧值（PR #41）。

## ingest：资讯来源 → `rebang.items/1`
- `python3 -m rebang.ingest --db tg.db --media-root . --out var/rebang/in/ingest.json [--no-fetch | --live] [--days 14]`。
- 来源（`rebang/contract/channels.json`，整源进一个频道）：18 个 TG（只读 `tg.db`，`mode=ro`）、6 个官方订阅（BBC、卫报、Google、OpenAI、GitHub Blog、Apple Newsroom，复用 `shiguang/ingest/web.py`）、GitHub Trending 公开页。
- 只收最近 14 天；TG 图片用 `tg.db` 旁的 `media/` 缓存，输出 `image_local`，建站时复制到 `site-v11/media/`。
- `--no-fetch` 读 `var/rebang/cache/ingest/` 缓存，没缓存标 `not_fetched`，不编。
- 今日重点（hot-daily）：链接命中已收条目只打 `highlight`，不另出条目。
- TG 无标题：`【…】` 取括号内，否则取首行（过长截到首句，最多 60 字），其余是摘要。

## hotsearch：热搜
- `python3 -m rebang.hotsearch --out var/rebang/in/hotsearch.json --live [--archive var/rebang/hotsearch-archive]`；离线 `--fixtures DIR`。
- 三家独立适配器 `rebang/hotsearch/providers/`：百度 `top.baidu.com/api/board?tab=realtime`、知乎 `api.zhihu.com/topstory/hot-lists/total`、B 站 `api.bilibili.com/x/web-interface/wbi/search/square`。
- 一家失败只空这一家（超时、非 200、code≠0、结构变）；每家每轮 1 次请求、超时 ≤10 秒；B 站若开始强制签名就空着，不破解。不要微博、第三方榜、公共 RSSHub。
- 归档：每个北京日期留最后一次成功抓取，保留 60 天（`rebang/hotsearch/archive.py`）。换一家 = 改 `hotsearch.json` + 增删一个 provider 文件。

## bloggers：博主
- `python3 -m rebang.bloggers --out var/rebang/in/bloggers.json --platform blog,wechat[,x] [--x-dump DIR] --translate-engine cache`。
- 输出带 `platforms[{id,status,last_ok_at,reason?,accounts[...]}]`，前端据此显示空状态和上次成功日期。
- **博客 7 个**：官方订阅源，直接抓。
- **公众号**：夕小瑶科技说走 Wechat2RSS 公开源；图片不带 Referer 下载到 `var/rebang/media/wechat/`，下载失败标 `missing`，不外链。其余 5 个（MacTalk、独立开发变现周刊、乱翻书、caoz的梦呓、王建硕）走微信读书：`rebang/bloggers/weread.py`。没扫码时是 `not_configured`（“已准备好，等扫码”）。`book_id` 已写在 `bloggers.json`（公开 __biz 解码，用 cover 接口返回的名字核对过）；网页搜索搜不到公众号本身。优先取 `/web/mp/articles` 列表；2026-11-16 实测新鲜会话上该接口仍回 `-2041`（不是登录失效），于是改走 `/api/mp/cover`（最新一篇）+ `/web/mp/content` 补发布时间和原文链接，账号行 `via` 记 `articles` 或 `cover`。cover 每次只有最新一篇，上次的帖子会保留。`-2010`/`-2012` 才标 `login_expired` 并保留旧条目。
  - 扫码：`python3 -m rebang.bloggers.weread login --session <会话路径> --qr-png "$(mktemp -d)/weread-login-qr.png" --wait 600`（不写 `--qr-png` 时默认放进新建的私有临时目录）（生成二维码要 segno，盒子上用 `/workspace/rebang-v1-briefs/tools/.venv-qr/bin/python`）。命令打印 `confirm_url` 和二维码图；在微信里扫码（或在微信里打开 confirm_url），手机上点确认。`getLoginInfo` 是长轮询，约 56 秒回一次 `{logicCode: LOGIN_TIMEOUT, canRetry: true}`，这只表示这一轮等完了，同一个二维码仍有效，命令用同一个 uid 接着等到 `--wait` 用完（11/16 前两次扫码失败就是把它当过期退出了）；只有没有 `canRetry` 时才换新码（覆盖同一个 PNG、打印 `"step": "refreshed"`）。输出每行即时 flush。要验证码时命令会打印带 `--uid … --otp <码>` 的重跑命令。
  - 会话只存 vid/skey，写在仓库外 `~/.config/rebang/weread-session.json`（0600，可用 `REBANG_WEREAD_SESSION` 改路径），通过 curl 标准输入传 Cookie，不进命令行、不打印。读写都走 `rebang/private_file.py`（不跟软链接、只本人可用、无 ACL、单一硬链接；写入用同目录随机名 0600 临时文件再原子改名）；内容不是含非空 vid/skey 字符串的 JSON 对象就当未配置，并保留上次公众号内容。curl 不跟任何跳转（3xx 一律当这次失败，跳登录页记 login_expired），配置里的 URL 只允许 `https://weread.qq.com/` 下由代码拼出的安全地址并开 `globoff`；任何非 2xx（401/403 记 login_expired）或非 0 errCode 都当失败：站上保留旧文，但账号状态不是 ok、`last_ok_at` 不前进。`python3 -m rebang.bloggers.weread status` 只有用户接口明确回了本人 userVid 才报 valid。
  - 列表回包和 cover/正文页都用真数据核过（2026-11-16）；列表通的时候用列表，不通时 cover 兜底。测试覆盖两种路径，以及 `-2041` 不把登录判死。
- **X 16 人**：Python 里调不到 Grok Bot 的公开 X 读取工具，所以适配器只读工具写好的原始响应 `var/rebang/x-dump/<YYYYMMDDTHHMM>/`（X API v2 结构；`quotes*`、`replies*`、`refs*` 开头的文件只作引用/评论参考；可选 `_dump.json` 写 `generated_at`）。取最新子目录；限 36 小时。可用 `REBANG_X_DUMP` 指向现有原稿目录或文件；缺失和过期均报告原因并保留上次成功内容。历史上原稿由盒子「X 博主 + 翻译」例程写入；Mac 刷新是读者，不会替它产生新原稿。11/25 排查：Mini 生产克隆里没有 `var/rebang/x-dump/`，盒子到 Mini 没有传送通道，见 `COLLECTION-RECOVERY.md`「博主采集断更」。
- **即刻 9 人**（2026-11-16 接通）：公共 RSSHub 实例的 `/jike/user/<UUID>`，不登录、不带 Cookie。实例清单在 `bloggers.json` 的 `rsshub_mirrors`，每个账号错开起点轮换，失败（超时、5xx、回错误页）换下一个，全挂才标 `jike_mirrors_down` 并保留上次内容；账号行写 `via` 记下这次用的实例。`--jike-rsshub`（或 `REBANG_JIKE_RSSHUB`，逗号分隔）可覆盖清单。`rebang/bloggers/jike.py` 去掉「发布了/转发了」前缀（即刻帖子没有标题），转发的原帖进 `blogger.quote`，频道头像来自订阅源的 `<image>`。公共实例是第三方服务，随时可能限流或下线。
- **微博**：2026-11-16 试过公开方式都不通：公共 RSSHub 的微博路由全部 503，`m.weibo.cn` 免登录接口返回 `ok:-100` 跳登录，`weibo.com/ajax` 403，无头浏览器停在游客验证页。阿欢 2026-11-16 15:49：「微博用小号 Cookie，我回头给你」；18:03 起用副号在盒子浏览器登录 weibo.com 后存了 Cookie。
  - **Cookie**：仓库外 `~/.config/rebang/weibo-cookie.txt`（`REBANG_WEIBO_COOKIE` 可改），0600，一行 weibo.com 请求头里的 Cookie 值（不带 `Cookie:` 前缀）。只在发请求时读进内存；不打印、不写日志、不进仓库/输出文件，测试里断言过。读取同样走 `rebang/private_file.py` 的安全打开，不合格当未配置；写入用 `python3 -m rebang.bloggers.weibo save-cookie`（标准输入，最多 64 KiB，超了不动旧文件；`save-cookie`/`check` 只用账号家目录（`pwd`）下的固定路径，不理会 `REBANG_WEIBO_COOKIE`）。urllib 只在同一个 HTTPS 源里带 Cookie 跟跳转，跨域或降级为 http 不跟（跳去 passport 登录页记 login_expired）。这份 Cookie 是桌面 weibo.com 的，`m.weibo.cn/api/config` 不认登录，所以**不用 weibo-crawler**（它走 m.weibo.cn）。
  - **接口**（`rebang/bloggers/weibo.py`）：`weibo.com/ajax/statuses/mymblog?uid=<uid>&page=1` 取主页第一页（约 20 条，按时间取最新 10 条）；`isLongText` 的帖再调 `/ajax/statuses/longtext?id=<mblogid>` 补全文，按 mblogid 缓存在 `var/rebang/weibo-crawler/longtext-cache.json`（同一条只问一次）。请求之间至少隔 3 秒，只抓 `bloggers.json` 里的 6 个号。`linfcstmr` 是个性域名，配置里写了 uid `2169039837`。
  - **映射**：正文 `text_raw`/长文；图取 `pic_infos[*].largest`（原图）；视频取 `page_info.media_info` 的 720p mp4 + 封面 + 时长；转发写成 `quote`（原帖作者昵称、正文、链接），纯转发图片帖把原帖图挂出来；链接 `https://weibo.com/<uid>/<mblogid>`；点赞/评论/转发数。前端不显示纯数字 uid 的「@」。
  - **图片**：sinaimg / weibocdn 对浏览器只认 `Referer: https://weibo.com/`（不带或带本站都 403，CORB/ORB 拦掉），所以抓取时带这个 Referer（不带 Cookie）把图、视频封面、博主头像下载成 webp（长边 1280，GIF 保留）到 `var/rebang/media/weibo/`，建站复制进 `site/media/weibo/`，原图地址留在 `orig_url`。首轮约 240 张 / 38MB、约 6 分钟，之后只下新图；不再引用的自动删。视频本体不存：站内播放会被微博拒，查看器显示「视频暂时播不了 · 打开原帖」。
  - **Cookie 失效**：接口 `ok` 不是 1、跳到 passport/登录页、回的不是 JSON 或 401/403 → 整个微博平台标 `login_expired`（`weibo_cookie_expired`），后面的号不再请求，站上沿用上次成功的内容（`stale` + `last_ok_at`），stderr 打一行 `weibo cookie expired`，8:30 私聊按已有逻辑提醒「微博」登录失效。单个号网络错误只记 `weibo_fetch_failed`，保留该号上次内容。重新登录副号、替换 Cookie 文件即可恢复。
- **YouTube**（2026-11-16 管道就绪，名单为空）：`rebang/bloggers/youtube.py`。官方频道订阅 `https://www.youtube.com/feeds/videos.xml?channel_id=UC…`，不用 API 密钥。这个接口 2026 年经常整段时间对存在的频道回 404/500，所以订阅失败隔 20 秒重试一次，仍失败退到公开频道「视频」页（`ytInitialData` 的 `lockupViewModel`），发布时间和简介从视频页 microformat 取、按视频号缓存在 `var/rebang/cache/youtube-watch.json`，每频道每轮最多补 4 个视频页；拿不到发布时间的这轮不出。账号行 `via` 记 `rss` 或 `page`。媒体 `type:"youtube"`，查看器用 youtube-nocookie 嵌入播放器（iframe 单独带 `referrerpolicy=strict-origin-when-cross-origin`，否则全站 same-origin 会让播放器报配置错误），不自动播放，下方有「在 YouTube 打开」。只译标题和摘要。名单在 `bloggers.json` 的 `youtube.accounts`，阿欢确认前为空，站上显示「频道名单待确认」；候选见 [`youtube-candidates.md`](youtube-candidates.md)。
- 预览页 `python3 -m rebang.bloggers.preview IN.json OUT.html` 只是验收截图用，不是正式前端。

## translate：英文翻译
- 入库时就译好，打开页面不现翻。默认引擎 `cache` 只查 `var/rebang/translate/cache.json`，缺的原文进 `pending.json`。
- 现行流程（2026-11-16 13:15 起，阿欢批准）：例程跑盒子上的 `/workspace/rebang-v1-briefs/tools/translate_deepseek.py`，用 DeepSeek Flash（`REBANG_TRANSLATE_MODEL=deepseek-flash`，脚本拒绝任何带 pro 的模型名；关掉深度思考）清空 `pending.json` 并写回缓存，下次建站生效。密钥只从环境变量 `REBANG_TRANSLATE_API_KEY` 读，不落盘、不打印。
- 兜底：DeepSeek 连续两次失败时，`python3 -m rebang.translate pending --limit 150` → 由 Grok 逐条译好写成 `{"<key>": "<译文>"}` → `python3 -m rebang.translate fill FILE --engine grok-bot`。
- 仓库内也有 `openai-compatible` 引擎（`REBANG_TRANSLATE_URL`、`REBANG_TRANSLATE_MODEL`、存密钥的环境变量名 `REBANG_TRANSLATE_KEY_ENV`），现行例程不走它。
- 博客只译标题和摘要，X 译全文。

## site：静态站构建
- `python3 -m rebang.site --in var/rebang/in --out site-v11 --hot-archive var/rebang/hotsearch-archive --public-base https://news.kwinweng.com/`；`var/rebang/in` 没有可用文件时读 `tests/fixtures/rebang/contract/`（`--fixture` 强制）。
- 纯 Python 标准库，前端零依赖（`web-v11/`，手势、banner 从 v10 设计稿移植）。按频道分页（每页 30），写 `data/meta.json`（含 `public_base`）、`data/id-index.json`（深链找条目）、`data/search-index.json`。
- 调 `rebang.archive.build`：条目按北京日期并入 `var/rebang/archive/YYYY-MM-DD.json`（按 id 去重），供搜索和 8:30 稿补漏。
- 深链 `#/item/<urlencoded id>`：冷启动和已打开页面都能直接开。
- 来源健康：频道顶栏的「来源状态」随 `meta.json` 显示待处理数量，点开 `#/health` 才加载 `data/health.json`。看板按状态计数、筛选和折叠，平台按一个来源计数，账号明细可展开。也可长按左上角频道标题，从诊断面板进入。TG 在 ingest 缓存里保留最后观察到的成功时间，不改数据库；X 复用导出时间和已有 36 小时规则。只展示，不发送提醒。
- 与 v10 的已确认偏差：上下模式每个频道先放 6 条，用「继续看」按钮加载，不自动无限加载。
- 前端功能模块 `web-v11/features/favorites.js`（localStorage，只在详情页收藏，换设备会消失）、`search.js`（纯前端匹配标题、摘要、来源、译文和原文；索引没加载完时先提示，加载完自动重搜）。

## push：8:30 今日重点私聊稿
- `python3 -m rebang.push --site site-v11 --dry-run [--output FILE] [--now ISO]`：只生成，不发送。
- 只挑过去 24 小时已上站的条目，最多 5 条（`rebang/push/select.py` 的 `MAX_ITEMS`），优先 `highlight`，再按频道轮转补足；排除邮件和未上站内容；没有新内容如实写。链接用 `data/meta.json` 的 `public_base`。
- 博主平台登录失效时，同一条稿子里提醒一次。创意雷达不在这里生成。

## 历史供稿记录

2026-11-22 修复分支移除博主页 Grok bot 分组及其供稿入口；旧站来源、8:30 稿和「今日重点」只给同链接打标的规则不变。下列为旧记录，不是现行配置。
- `public-feeds/` 只到 2026-10-23（`/workspace/tg-local/sync.sh` 改为 `publish_public.py --no-push`）；4 个每日成品直接读盒子上的原始目录：推特爆款 `/workspace/x-digest/YYYY-MM-DD.json`、环球要闻 `/workspace/world-brief/YYYY-MM-DD/brief.json`、GitHub 热门 `/workspace/feeds-inbox/github/YYYY-MM-DD/feed.json`、今日重点 `/workspace/feeds-inbox/hot-daily/YYYY-MM-DD/feed.json`（11/15 核对时的位置）。
- 微博未接通（公开方式都要登录/游客验证）；5 个公众号的微信读书管道已备好、等扫码；YouTube 管道已备好、频道名单待确认。站上显示真实空状态。
