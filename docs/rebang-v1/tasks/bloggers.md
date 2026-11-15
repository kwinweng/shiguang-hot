# 任务卡：feat/rebang-v1-bloggers（博主抓取与翻译）

- **可观察验收结果（从用户入口验证，先写这条再动手）**：打开新站底栏「博主」，能看到 7 个博客与 X 博主的真实帖子卡片（头像/名字/时间/正文，英文有译文）；即刻、微博、公众号（除夕小瑶）显示真实空状态和原因，没有假帖子。
- worktree：`/workspace/rebang-v1-wt/bloggers`。
- 做什么：按 `bloggers.json` 产出 `kind=post` 条目写 `var/rebang/in/bloggers.json`，外加 `rebang/translate/` 翻译接口（资讯英文也用）。
  - 博客 7 个：官方订阅源，直接做完。
  - X 16 人：走盒子上现有公开读取能力 / 现有成品，补头像、媒体、互动数（字段见 SPEC `bloggers-card-fields.md`）；不新做未登录硬爬。
  - 即刻 9 人：适配器读「自建 RSSHub 即刻用户路由」的地址（配置项，默认未配置 → 平台 `status=not_configured`、空）。部署 RSSHub 要另批，本分支不部署。
  - 微博 6 人：只做 weibo-crawler 调用框架与输出映射；Cookie 只接受仓库外密钥文件**路径**参数，代码不读取内容做别的事、不打印；没有文件 → `not_configured`。**需要登录/扫码时停下报告。**
  - 公众号：夕小瑶走 Wechat2RSS 公开订阅直接做；其余 5 个微信读书只做框架，需扫码时停。
  - 翻译：`translate(texts, src_lang='en') -> list[str] | None`，复用盒子上已有翻译能力（先查清是哪个、额度口径，不另买）；失败返回 None → 条目 `translated=false`，不编译文。
  - 平台状态写进输出：`platforms[{id, status: ok|empty|error|not_configured|login_expired, last_ok_at}]`，失效时站上保留上次成功内容并标日期。
- 改哪些目录：`rebang/bloggers/`、`rebang/translate/`、`tests/test_rebang_bloggers*.py`、`tests/fixtures/rebang/bloggers/`。
- 接口：`python3 -m rebang.bloggers --out var/rebang/in/bloggers.json [--platform blog,x] [--weibo-cookie-file PATH]`。
- 验收：单测全绿；博客 7 个 `--live` 冒烟有真实条目且通过 `validate_items_envelope`；X 至少用现有成品产出合法卡片；登录类平台在无配置时输出 `not_configured` 而非报错或假数据。
- 不许碰：契约、密钥/Cookie 内容、`.env`、密码；不发测试微博；遇登录页/验证码/风控立即停，当天不重试。不部署 RSSHub。

## 执行记录（2026-11-15 北京时间，Grok 本分支）

- **产出**：`python3 -m rebang.bloggers --out var/rebang/in/bloggers.json`。信封在契约字段外多带 `platforms[{id,name,status,last_ok_at,reason?,accounts[{handle,name,status,count,error?,last_ok_at,stale?}]}]`。
- **博客 7 个**：官方订阅源全部实测 200 可解析（阮一峰 atom 3 条、Reorx/图拉鼎/Simon/Karpathy/Mollick/Lilian Weng 各取最新 10 条）。图拉鼎博客最新一篇是 2025-07-23，照实显示。
- **公众号·夕小瑶科技说**：Wechat2RSS 公开源实测 200，最新 10 条；开头「原创/作者/日期/属地」短行不进摘要。其余 5 个公众号 `not_configured(wechat_weread_qr)`。
- **X 16 人**：盒子上能用、不用阿欢登录的只有 Grok Bot 自带的公开 X 读取工具（agent 工具，Python 里调不到）。所以适配器只读它写的原始响应目录 `var/rebang/x-dump/<YYYYMMDDTHHMM>/`（X API v2 结构，`quotes*/replies*/refs*` 开头的文件只作引用和评论参考，可放 `_dump.json` 写 generated_at）。超过 36 小时 → `error(x_dump_stale)` 并保留上次内容；没有 dump → `not_configured`。本次 dump 由本分支用该工具实取（search_posts_all 3 页 + get_posts_by_ids 补全文、媒体和引用 + 一次评论搜索），13/16 人有帖；karpathy、sama、AndrewYNg 自 11-08 起无原创帖，状态为 `empty`，不编数据。**生产里谁定时写 dump 还没定**，需要另建一个 Grok 例程（要阿欢批）。
- **即刻**：配置 `--jike-rsshub`（或 `REBANG_JIKE_RSSHUB`）后读 `<根>/jike/user/<UUID>`；默认没配，状态 `not_configured`。RSSHub 不部署。
- **微博**：`--weibo-cookie-file` 只检查文件是否存在，不读取（单测用权限 000 的文件证明）。没有文件 → `not_configured(weibo_cookie_unset)`；有文件但没有 `--weibo-output` 的 crawler 输出 → `not_configured(weibo_crawler_output_missing)`。weibo-crawler 没装、没跑；映射用合成样本测过，接真实输出时要再复核字段。
- **翻译** `rebang/translate`：`translate(texts, src_lang)` 返回 `list[str] | None`。默认引擎 `cache` 只查本地译文缓存，缺的原文写进 `pending.json`。由 Grok 例程（盒子上中文圈早报、资讯中译用的就是它，只用 Grok 额度）翻好后，运行 `python3 -m rebang.translate fill FILE --engine grok-bot` 合并。可选引擎 `openai-compatible` 需要 `REBANG_TRANSLATE_URL`、`REBANG_TRANSLATE_MODEL`，以及存密钥的环境变量名 `REBANG_TRANSLATE_KEY_ENV`；密钥不落盘、不打印。本次 68/68 条英文由 Grok 译好入缓存（engine=grok-bot，label=机器翻译）。博客只译标题和摘要；X 译全文，摘要从译文里截。
- **验收证据** `docs/rebang-v1/evidence/bloggers/`：`live-run-summary.json`，以及 390×844 手机尺寸截图 `mobile-{x,blog,jike,weibo,wechat,zhihu}.png`、`mobile-x-original-expanded.png`。截图来自 `python3 -m rebang.bloggers.preview` 生成的**验收预览页，不是 v11 正式前端**；正式「博主」页由 frontend-v11 分支实现。
- HANDOFF.md 里没有按分支分行的表，本分支不改 HANDOFF，以本记录为准。
