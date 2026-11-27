# 公众号与 Telegram 阅读页调研

核验日期：2026-11-27（北京时间）。仅看公开网页，不用真实登录态，不新增来源或例程。

## 公众号候选

- **极客公园（互联网产品、商业与科技）**：[官方公众号入口](https://about.geekpark.net/)；[官网 RSS](https://www.geekpark.net/rss) 返回近期条目和较长的正文片段，[11 月 26 日官网文章](https://www.geekpark.net/news/374536) 可不登录读到结尾。第三方目录可见近期公众号标题与简介；历史列表提示登录，未证实能直接采公众号原文。首选官网 RSS 发现、按需读取官网，不把它当作公众号全量同步。
- **量子位（AI 与科技）**：[官方公众号 QbitAI](https://www.qbitai.com/微信公众号)；[官网 RSS](https://www.qbitai.com/feed) 返回标题、时间、链接和摘要，[11 月 26 日官网样本](https://www.qbitai.com/2026/11/513021.html) 可不登录读到结尾。公众号原文自动化和全量同步未核实。
- **少数派（软件、数码与工作流）**：[官方订阅指南](https://sspai.com/post/24194) 列公众号 `sspaime` 与 [公开 RSS](https://sspai.com/feed)，样本仅有摘要；[11 月 26 日官网文章](https://sspai.com/post/116773) 可不登录读完。[会员 RSS 指南](https://sspai.com/prime/story/member-rss-feed) 明示是会员文章摘要，不能当全文来源，不接登录或付费内容。

建议从极客公园的官网 RSS 开始，量子位、少数派分别补 AI 与软件实用内容。试采先核对标题、作者、发布时间、稳定链接、摘要和去重，不把官网更新称作公众号同步。公开能读不等于有权转载；默认展示出处、链接和允许使用的摘要，全文和配图只在权利明确时入站。遇到登录、付费或不可读，保留链接与已有合法摘要，不尝试绕过。

## Telegram 即时预览

频道是 [@shuangyunews_rss](https://t.me/shuangyunews_rss)，已在现有频道配置。公开[样例 #14596](https://t.me/s/shuangyunews_rss/14596) 有消息链接/编号、公开时间、预览标题/片段、Telegraph 目标及原刊链接。帖子预览本身没有双语全文；公开 Telegraph 目标另有英中段落与原刊链接。不要把 Telegraph 当作已获授权的原刊镜像。

- **抓公开网页**：采消息字段，以及公开、允许采集的目标页正文块（段落、标题、列表、引用和可用图片元数据）；先用原刊公开且可授权内容。仅有预览、目标打不开或权限不明时，保留摘要及「打开原文 / 在 Telegram 查看」，不把摘要标成全文，也不把原文切成伪译稿。
- **读 Telegram 的缓存页面**：[官方 `messages.getWebPage`](https://core.telegram.org/method/messages.getWebPage) 只对用户会话开放，不是 Bot API；[响应 `webPage.cached_page`](https://core.telegram.org/constructor/webPage) 可包含 Instant View。是否存在取决于链接和模板。公开网页/嵌入不是该接口，本轮没登录，也没验证样例是否真的返回 `cached_page`。
- **站内做类似阅读页（推荐）**：复用现有结构化正文和详情页，合法可用的稿件显示中文优先；需要对照时再提供原文。无需导入 Telegram 会话、不复刻 Telegram 界面。将来若想让我们自己的站点链接在 Telegram 内出现即时预览，那是另一条线：为自有站提交[模板](https://instantview.telegram.org/)，由 Telegram 审核。两者都不授予第三方全文转载权。
