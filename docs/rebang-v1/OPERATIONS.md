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

## 定时
- 盒子没有 cron，定时都靠 bot 例程。现在 v11 由「X 博主 + 翻译」例程每 2 小时刷新并发布一次（提示词 `/workspace/rebang-v1-briefs/routine-x-translate.md`，翻译脚本 `/workspace/rebang-v1-briefs/tools/translate_deepseek.py`，每轮简报 `/workspace/rebang-v1-briefs/runs/`）；8:30 私聊例程的提示词是同目录的 `routine-0830.md`。
- 2026-11-21：旧采集例程暂停后，v11 单独刷新不能生成发布包所需的旧站数据。见[采集断更恢复方案](COLLECTION-RECOVERY.md)；恢复例程和部署须阿欢批准。
- 手动刷新：在 `/workspace/shiguang-prod` 跑 `sh tools/rebang_refresh.sh`（约 1–2 分钟）；有新英文条目时先 `python3 -m rebang.translate pending`，译好后 `fill`，再 `sh tools/rebang_refresh.sh --no-fetch`。

## 回退
1. 站点内容出问题：服务器上一版在 `/var/www/news.kwinweng.com.news-sync-previous`（news-sync 每次成功发布都会替换它）；或在 box 上把 `site-v11.prev` 换回 `site-v11` 后跑 `sh tools/publish_pages.sh --already-built`。
2. nginx 配置：当前 v11 根路径配置的备份是 `/etc/nginx/sites-available/news.kwinweng.com.conf.bak-20261115-171713-v11-root`（文件名是服务器 UTC 时间 2026-11-15 17:17:13，北京时间 2026-11-16 01:17:13）。恢复后执行 `nginx -t && systemctl reload nginx`。
3. 代码：在 GitHub revert 合并 PR。
4. 2026-11-16 按阿欢确认，已删除旧阅读器/旧站回滚备份：`gh-pages-pre-rebang-20261115`，nginx 的 `pre-root`、`pre-rebang` 和 `bak-20261017-183807`，`/root/backup-shiguang-reader-20261115-160953/`，`/root/backup-shiguang-reader-update-20261115-163256/`，`/var/backups/shiguang-reader/`，以及 `/var/backups/news-kwinweng-pre-public-20261107*`。确认依据：news-sync 只拉当前 `gh-pages`，并用同级 `news-sync-previous` 做上一版；灵记 `lingji-news-source` 只读线上 `/var/lib/shiguang-reader/topics.sqlite3`（此库保留）；没有脚本或例程引用那些备份。当前 gh-pages 和服务器静态根里的旧站树仍须保留，因为 news-sync 校验还按旧站格式检查，不要删。远程分支现在只留 `main` 和 `gh-pages`。
