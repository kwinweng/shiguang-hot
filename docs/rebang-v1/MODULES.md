# 拾光热榜 v11 模块说明

各模块的入口、输入输出、约束和已知缺口。字段定义以 [`CONTRACT.md`](CONTRACT.md) 为准，发布与服务器见 [`OPERATIONS.md`](OPERATIONS.md)。
一键全流程是 `sh tools/rebang_refresh.sh`，下面的命令都是它会调用的单步。所有 `var/rebang/`、`site-v11/` 产物都不进 git。

（本文件合并了 11/15 各功能分支的任务卡与执行记录；原任务卡已删除，见 Git 历史。）

## 数据流

```
tg.db（旧站采集写入）──┐
t.me 公开页 → tgmeta ──┼→ ingest → var/rebang/in/ingest.json ─┐
官方订阅 / Trending ───┤                                        │
盒子上的 4 个每日成品 ─┘                                        ├→ rebang.site → site-v11/ → publish_pages.sh（gh-pages 的 rebang/）
百度 / 知乎 / B 站 → hotsearch → var/rebang/in/hotsearch.json ──┤
博客 / Wechat2RSS / X dump → bloggers → var/rebang/in/bloggers.json ┘
                     翻译缓存 var/rebang/translate/cache.json（ingest、bloggers 入库时自动套用）
```

## tgmeta：TG 附加信息
- `python3 -m rebang.tgmeta [--store var/rebang/cache/tgmeta.json] [--channels a,b] [--fixtures DIR]`。
- 读 t.me/s 公开页，补频道自己的话、引用/转发原帖、表情、浏览数、公开评论；按 `<频道>/<消息号>` 由 ingest 合进条目，`tg.db` 不动。
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
- **公众号**：夕小瑶科技说走 Wechat2RSS 公开源；图片不带 Referer 下载到 `var/rebang/media/wechat/`，下载失败标 `missing`，不外链。其余 5 个（MacTalk、独立开发变现周刊、乱翻书、caoz的梦呓、王建硕）走微信读书：`rebang/bloggers/weread.py`。没扫码时是 `not_configured`（“已准备好，等扫码”）；扫码后按公众号名在微信读书里搜 `MP_WXS_` bookId（缓存 `var/rebang/cache/weread-books.json`），再取 `/web/mp/articles` 文章列表；登录失效标 `login_expired`、保留旧条目。
  - 扫码：`python3 -m rebang.bloggers.weread login --qr-png /tmp/weread-login-qr.png --wait 600`（生成二维码要 segno，盒子上用 `/workspace/rebang-v1-briefs/tools/.venv-qr/bin/python`）。命令打印 `confirm_url` 和二维码图；在微信里扫码（或在微信里打开 confirm_url），手机上点确认。要验证码时命令会打印带 `--uid … --otp <码>` 的重跑命令。
  - 会话只存 vid/skey，写在仓库外 `~/.config/rebang/weread-session.json`（0600，可用 `REBANG_WEREAD_SESSION` 改路径），通过 curl 标准输入传 Cookie，不进命令行、不打印。`python3 -m rebang.bloggers.weread status` 只回报 ok / login_expired。
  - 文章回包结构按公开逆向资料写的，测试用合成样例；扫码后第一次刷新要用真数据核对。
- **X 16 人**：Python 里调不到 Grok Bot 的公开 X 读取工具，所以适配器只读工具写好的原始响应 `var/rebang/x-dump/<YYYYMMDDTHHMM>/`（X API v2 结构；`quotes*`、`replies*`、`refs*` 开头的文件只作引用/评论参考；可选 `_dump.json` 写 `generated_at`）。取最新子目录；超过 36 小时标 `x_dump_stale` 并保留上次内容；没有 dump 是 `not_configured`。谁定时写 dump：例程草稿已备，**未创建**。
- **即刻 9 人**（2026-11-16 接通）：公共 RSSHub 实例的 `/jike/user/<UUID>`，不登录、不带 Cookie。实例清单在 `bloggers.json` 的 `rsshub_mirrors`，每个账号错开起点轮换，失败（超时、5xx、回错误页）换下一个，全挂才标 `jike_mirrors_down` 并保留上次内容；账号行写 `via` 记下这次用的实例。`--jike-rsshub`（或 `REBANG_JIKE_RSSHUB`，逗号分隔）可覆盖清单。`rebang/bloggers/jike.py` 去掉「发布了/转发了」前缀（即刻帖子没有标题），转发的原帖进 `blogger.quote`，频道头像来自订阅源的 `<image>`。公共实例是第三方服务，随时可能限流或下线。
- **微博**：2026-11-16 试过公开方式都不通：公共 RSSHub 的微博路由全部 503（「Cooling down before new visitor Cookies」或实例的无头浏览器挂了），`m.weibo.cn` 免登录接口返回 `ok:-100` 跳登录，`weibo.com/ajax` 403，无头浏览器打开主页停在游客验证页。要接只能用副号 Cookie（待阿欢定）。`--weibo-cookie-file` 只检查文件存在，不读内容、不打印；还需 `--weibo-output`（weibo-crawler 的输出）。crawler 未安装；字段映射只用合成样本测过，接真实输出要复核。
- **YouTube**（2026-11-16 管道就绪，名单为空）：`rebang/bloggers/youtube.py`。官方频道订阅 `https://www.youtube.com/feeds/videos.xml?channel_id=UC…`，不用 API 密钥。这个接口 2026 年经常整段时间对存在的频道回 404/500，所以订阅失败隔 20 秒重试一次，仍失败退到公开频道「视频」页（`ytInitialData` 的 `lockupViewModel`），发布时间和简介从视频页 microformat 取、按视频号缓存在 `var/rebang/cache/youtube-watch.json`，每频道每轮最多补 4 个视频页；拿不到发布时间的这轮不出。账号行 `via` 记 `rss` 或 `page`。媒体 `type:"youtube"`，查看器用 youtube-nocookie 嵌入播放器（iframe 单独带 `referrerpolicy=strict-origin-when-cross-origin`，否则全站 same-origin 会让播放器报配置错误），不自动播放，下方有「在 YouTube 打开」。只译标题和摘要。名单在 `bloggers.json` 的 `youtube.accounts`，阿欢确认前为空，站上显示「频道名单待确认」；候选见 [`youtube-candidates.md`](youtube-candidates.md)。
- 预览页 `python3 -m rebang.bloggers.preview IN.json OUT.html` 只是验收截图用，不是正式前端。

## translate：英文翻译
- 入库时就译好，打开页面不现翻。默认引擎 `cache` 只查 `var/rebang/translate/cache.json`，缺的原文进 `pending.json`。
- 流程：`python3 -m rebang.translate pending` → 由 Grok 逐条译好写成 `{"<key>": "<译文>"}` → `python3 -m rebang.translate fill FILE --engine grok-bot` → 下次建站生效。只翻新增条目。
- 可选引擎 `openai-compatible`（`REBANG_TRANSLATE_URL`、`REBANG_TRANSLATE_MODEL`、存密钥的环境变量名 `REBANG_TRANSLATE_KEY_ENV`），目前不用；密钥不落盘、不打印。
- 博客只译标题和摘要，X 译全文。

## site：静态站构建
- `python3 -m rebang.site --in var/rebang/in --out site-v11 --hot-archive var/rebang/hotsearch-archive --public-base https://news.kwinweng.com/`；`var/rebang/in` 没有可用文件时读 `tests/fixtures/rebang/contract/`（`--fixture` 强制）。
- 纯 Python 标准库，前端零依赖（`web-v11/`，手势、banner 从 v10 设计稿移植）。按频道分页（每页 30），写 `data/meta.json`（含 `public_base`）、`data/id-index.json`（深链找条目）、`data/search-index.json`。
- 调 `rebang.archive.build`：条目按北京日期并入 `var/rebang/archive/YYYY-MM-DD.json`（按 id 去重），供搜索和 8:30 稿补漏。
- 深链 `#/item/<urlencoded id>`：冷启动和已打开页面都能直接开。
- 与 v10 的已确认偏差：上下模式每个频道先放 6 条，用「继续看」按钮加载，不自动无限加载。
- 前端功能模块 `web-v11/features/favorites.js`（localStorage，只在详情页收藏，换设备会消失）、`search.js`（纯前端匹配标题、摘要、来源、译文和原文；索引没加载完时先提示，加载完自动重搜）。

## push：8:30 今日重点私聊稿
- `python3 -m rebang.push --site site-v11 --dry-run [--output FILE] [--now ISO]`：只生成，不发送。
- 只挑过去 24 小时已上站的条目，最多 5 条（`rebang/push/select.py` 的 `MAX_ITEMS`），优先 `highlight`，再按频道轮转补足；排除邮件和未上站内容；没有新内容如实写。链接用 `data/meta.json` 的 `public_base`。
- 博主平台登录失效时，同一条稿子里提醒一次。创意雷达不在这里生成。

## 已知缺口
- `public-feeds/` 只到 2026-10-23（`/workspace/tg-local/sync.sh` 改为 `publish_public.py --no-push`）；4 个每日成品直接读盒子上的原始目录：推特爆款 `/workspace/x-digest/YYYY-MM-DD.json`、环球要闻 `/workspace/world-brief/YYYY-MM-DD/brief.json`、GitHub 热门 `/workspace/feeds-inbox/github/YYYY-MM-DD/feed.json`、今日重点 `/workspace/feeds-inbox/hot-daily/YYYY-MM-DD/feed.json`（11/15 核对时的位置）。
- 微博未接通（公开方式都要登录/游客验证）；5 个公众号的微信读书管道已备好、等扫码；YouTube 管道已备好、频道名单待确认。站上显示真实空状态。
