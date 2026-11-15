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
