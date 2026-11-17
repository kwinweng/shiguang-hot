# 拾光热榜 v11 上线与运维

2026-11-15 上线到 `/rebang/`；2026-11-16 00:08 阿欢决定根路径 `https://news.kwinweng.com/` 改为 v11，旧的登录阅读器（shiguang-reader）和 `/mail/`、`/archive/` 下线，保留 noindex。

## 发布链路
- 代码：`main`（box 上生产克隆 `/workspace/shiguang-prod`，旧站抓取 `tools/box_scrape.sh` 每次运行前会 ff 到 origin/main，并继续写 tg.db）。
- 刷新：`sh tools/rebang_refresh.sh`（不需要 token）：t.me 附加信息 → 热搜+归档 → 博主（博客、公众号；X 读 `var/rebang/x-dump/` 最新转储）→ TG/RSS/官方源入库（自动用翻译缓存）→ 建 `site-v11/`（原子替换，保留 `site-v11.prev/`）→ `tools/publish_pages.sh --already-built`。
  加锁（`var/rebang/.refresh.lock`；发布时再拿 `.box-scrape.lock`，与旧站抓取互斥）；一步失败保留上次数据继续；建站失败不替换、不发布。日志 `var/rebang/logs/`，最近一次结果 `var/rebang/logs/last-refresh.json`。
- `tools/publish_pages.sh` 把旧公开站 `site/` 与 `site-v11/`（放进 `rebang/` 子目录）一起强推 gh-pages。旧站树仍然要发：服务器 `news-sync` 的校验按旧站格式检查。**不要用 `REBANG_PUBLISH=0`**——根路径只读 `rebang/`，不带它整站会 404。
- 服务器：`news-sync.timer` 每 20 分钟拉 gh-pages → `/var/www/news.kwinweng.com`。nginx 用 `try_files /rebang$uri /rebang$uri/index.html =404` 把 `rebang/` 挂到根路径；旧站文件不再对外提供。`/rebang/...` 301 到 `/...`（浏览器保留 `#/item/<id>`）。`/mail/`、`/archive/`、`/__login/`、`/api/` 返回 404；`robots.txt` 全站 Disallow，响应头带 `X-Robots-Tag: noindex, nofollow`，页面本身也有 noindex。
- 深链：`https://news.kwinweng.com/#/item/<id>`（`REBANG_PUBLIC_BASE` 默认 `https://news.kwinweng.com/`，经 `--public-base` 写进 `data/meta.json`；8:30 私聊稿 `python3 -m rebang.push` 读它）。
- 旧阅读器：`shiguang-reader.service` 与 `shiguang-reader-update.timer` 均已 `disable --now`（更新定时器于 11/16 00:32 停用）。更新定时器实际原是每 5 分钟跑，不是每天一次。灵记 `lingji-news-source` 仍只读线上 `/var/lib/shiguang-reader/topics.sqlite3`，此库和 `/etc/systemd/system/` 里的 unit 文件都保留；库从此不再更新。`shiguang-reader-ai.timer` 原本就是 disabled。只恢复更新：`systemctl enable --now shiguang-reader-update.timer`。2026-11-16 01:17 起，旧阅读器/旧站回滚备份已按阿欢确认删除，见下面「回退」。
- 图标：favicon、apple-touch、PWA、启动图和 og:image 用袋鼠原图（`web-v11/brand/`，`python3 tools/build_rebang_icons.py`）；顶栏不放 logo，日期居左（PR #47）。
- GitHub Pages 上的公开旧站尚未关掉，见 `HANDOFF.md`「下一步」。

## 定时与切换（2026-11-17）

阿欢要求迁往 Mac 后：普通刷新每 30 分钟；X 博主抓取、回复和翻译每 30 分钟；今日重点每天北京时间 08:30 私聊阿欢、最多 5 条。**这些是接管后的目标；本机尚未启用。** 旧包 `routine-x-translate.md` 标题的「每 2 小时」和 `routine-0830.md` 的「尚未建例程」是历史文字，不代表当前指示。

1. 先在新机器手动刷新、发布，打开线上核对本次版本及 noindex。
2. 回报「新机器已发布成功」，由阿欢通知旧机器的管家停掉旧循环和例程。
3. 收到旧任务已停的确认后，再启用新定时任务；切换前不启动第二个 `tg.db` 数据提交者，也不改旧机器任务。

常规入口仍是仓库根目录 `sh tools/rebang_refresh.sh`。它仅读 `tg.db`，不会替代 `box_scrape.sh` 的真正 TG 采集；不能只迁刷新而漏掉数据库更新。`box_scrape.sh` 正常模式要求干净的 `main`，不要为了运行它删除开发目录里的用户文件。

X 抓取保持 API v2 原始 JSON、16 位博主、最近 24 小时、排除转推/回复，引用和热门回复分开保存。dump 在 `var/rebang/x-dump/<时间>/`，回复缓存为 `var/rebang/x-replies/store.json`；接口错误不得写成成功空响应。沿用每分钟最多 30 次、每天最多 1000 次、搜索间隔至少 2.2 秒和每页最多 25 条的限额；30 分钟频率下还须按当天剩余额度限制每轮调用，不能把每轮 200 次上限当成全天预算。新机器的 API 读取方式尚未接通。

翻译脚本从环境变量读 `REBANG_TRANSLATE_API_KEY`，只准 `deepseek-flash`，关闭思考，绝不用 Pro。移用旧脚本时需设置 `REBANG_REPO` 为新仓库根目录，并把 `--usage-log` 指向本机可写的日志目录；旧默认 `/workspace/...` 不适用于 Mac。翻译完成后 `sh tools/rebang_refresh.sh --no-fetch` 重建发布。脚本尚未取得本机密钥，不应把已有中文缓存视为翻译 API 已通过实测。

`python3 -m rebang.push --site site-v11 --dry-run` 只出稿，不会发送。今日重点须使用脚本给出的根地址 `https://news.kwinweng.com/#/item/...`，不沿用旧例程里的 `/rebang/` 链接。私聊投递渠道仍待配置。

## Mac 迁移检查

- 本次缓存包为 `rebang-state-20261117.tar.gz`，运行说明包为 `rebang-ops-briefs-20261117.tar.gz`；解包前核对随包 SHA256，在各自新的空目录中检查，不执行包内 Linux 虚拟环境和软链接。缓存恢复到 `var/rebang/`，凭据不在包内。
- 本机 Python：`var/rebang/venv/bin/python`。运行 shell 入口时设置 `BOX_PYTHON="$PWD/var/rebang/venv/bin/python"`，PATH 含 Homebrew 的 `/opt/homebrew/bin`（提供 `flock`）。
- `site/` 和 `site/build-info.json` 也必须存在，服务器校验依赖它们。可先 `NO_FETCH=1 SITE_MODE=public MAIL_DIGEST=0 TZ=Asia/Shanghai "$BOX_PYTHON" pipeline.py`，再 `"$BOX_PYTHON" tools/write_build_info.py`；这只构建，不会更新 TG 数据库。
- 缓存里旧的 `/workspace/shiguang-prod/var/rebang/media/...` 绝对路径在 Mac 上不存在，须对应到已恢复的本地文件。TG 根目录 `media/` 不在 state 包中，可从现有 gh-pages 的 `rebang/media/` 恢复公开图片；核对最终产物，不向服务器登录或改变路径权限。
- **四个每日整理输入不在 state 包中**：推特爆款 `/workspace/x-digest/YYYY-MM-DD.json`（可用 `X_FEED_DIR` 指定新目录）；环球要闻 `/workspace/world-brief/YYYY-MM-DD/brief.json`（`WORLD_FEED_DIR`）；GitHub 热门 `/workspace/feeds-inbox/github/YYYY-MM-DD/feed.json`；今日重点 `/workspace/feeds-inbox/hot-daily/YYYY-MM-DD/feed.json`。后二者在当前 `sources.json` 没有独立目录环境变量。重新 ingest 前必须安排这些输入的迁移或明确后续生产方式，不能静默丢弃原来已上站的整理内容。缓存 `in/ingest.json` 可用于核对，不能代替持续供稿。
- 微博 Cookie 和微信读书会话仅放仓库外 `~/.config/rebang/`，权限 0600，不查看或打印内容。微博当前实现调用 `weibo.com` 桌面 ajax；交接中提到的 `m.weibo.cn` Cookie 能否用于此实现，需要收到阿欢配置后实测，不能先认定成功。
- 接管成功必须同时具备：真实刷新结果、发布 SHA、本次线上 `built_at`/版本对应、关键内容与图片核对、页面 meta + `X-Robots-Tag` + robots.txt 的 noindex 核对。仅本地构建、dry-run 或 gh-pages 推送成功都不算切换完成。

## 回退
1. 站点内容出问题：服务器上一版在 `/var/www/news.kwinweng.com.news-sync-previous`（news-sync 每次成功发布都会替换它）；或在 box 上把 `site-v11.prev` 换回 `site-v11` 后跑 `sh tools/publish_pages.sh --already-built`。
2. nginx 配置：当前 v11 根路径配置的备份是 `/etc/nginx/sites-available/news.kwinweng.com.conf.bak-20261115-171713-v11-root`（文件名是服务器 UTC 时间 2026-11-15 17:17:13，北京时间 2026-11-16 01:17:13）。恢复后执行 `nginx -t && systemctl reload nginx`。
3. 代码：在 GitHub revert 合并 PR。
4. 2026-11-16 按阿欢确认，已删除旧阅读器/旧站回滚备份：`gh-pages-pre-rebang-20261115`，nginx 的 `pre-root`、`pre-rebang` 和 `bak-20261017-183807`，`/root/backup-shiguang-reader-20261115-160953/`，`/root/backup-shiguang-reader-update-20261115-163256/`，`/var/backups/shiguang-reader/`，以及 `/var/backups/news-kwinweng-pre-public-20261107*`。确认依据：news-sync 只拉当前 `gh-pages`，并用同级 `news-sync-previous` 做上一版；灵记 `lingji-news-source` 只读线上 `/var/lib/shiguang-reader/topics.sqlite3`（此库保留）；没有脚本或例程引用那些备份。当前 gh-pages 和服务器静态根里的旧站树仍须保留，因为 news-sync 校验还按旧站格式检查，不要删。远程分支现在只留 `main` 和 `gh-pages`。
