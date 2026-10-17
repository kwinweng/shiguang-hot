# 拾光聚合平台

## 模块与配置

`pipeline.py` 保留 Telegram t.me/s 抓取、断行清洗、SQLite 增量去重、14 天图片缓存和热点评分。
`feeds.py` 管理 JSON 配置、三种适配器、验证和图片压缩；`sitebuild.py` 统一渲染卡片、导航、栏目和归档。
`style.css`、`app.js` 提供共享视觉与交互。`build_icons.py` 生成蓝色图标、manifest 并检验边缘。
`validate_feed.py` 为独立投递校验入口；规范见 INGEST.md。`mailbuild.py` 兼容旧入口，仅重建内网 inbox。

`sources.json` 声明 id、type、name、icon、color、visibility、nav（enabled/order）。
Telegram 使用 channel；inbox 使用 directory、filename、adapter（native/mail/world）和可选 env。
分类正则位于 categories。导航按顺序自动生成；inbox 有合法数据才显示。
手机最多五项，多余栏目放入“更多”；链接使用相对路径，支持 Pages `/tg-digest/`。

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
无需修改渲染代码。图标 key 支持 home/hot/all/archive/mail/world，未知 key 回退 all。
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
