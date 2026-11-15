# 拾光热榜 v11 上线与运维

2026-11-15 上线到 `/rebang/`；2026-11-16 00:08 阿欢决定根路径 `https://news.kwinweng.com/` 改为 v11，旧的登录阅读器（shiguang-reader）和 `/mail/`、`/archive/` 下线，保留 noindex。

## 发布链路
- 代码：`main`（box 上生产克隆 `/workspace/shiguang-prod`，旧站抓取 `tools/box_scrape.sh` 每次运行前会 ff 到 origin/main，并继续写 tg.db）。
- 刷新：`sh tools/rebang_refresh.sh`（不需要 token）：t.me 附加信息 → 热搜+归档 → 博主（博客、公众号；X 读 `var/rebang/x-dump/` 最新转储）→ TG/RSS/官方源入库（自动用翻译缓存）→ 建 `site-v11/`（原子替换，保留 `site-v11.prev/`）→ `tools/publish_pages.sh --already-built`。
  加锁（`var/rebang/.refresh.lock`；发布时再拿 `.box-scrape.lock`，与旧站抓取互斥）；一步失败保留上次数据继续；建站失败不替换、不发布。日志 `var/rebang/logs/`，最近一次结果 `var/rebang/logs/last-refresh.json`。
- `tools/publish_pages.sh` 把旧公开站 `site/` 与 `site-v11/`（放进 `rebang/` 子目录）一起强推 gh-pages。旧站树仍然要发：服务器 `news-sync` 的校验按旧站格式检查。**不要用 `REBANG_PUBLISH=0`**——根路径只读 `rebang/`，不带它整站会 404。
- 服务器：`news-sync.timer` 每 20 分钟拉 gh-pages → `/var/www/news.kwinweng.com`。nginx 用 `try_files /rebang$uri /rebang$uri/index.html =404` 把 `rebang/` 挂到根路径；旧站文件不再对外提供。`/rebang/...` 301 到 `/...`（浏览器保留 `#/item/<id>`）。`/mail/`、`/archive/`、`/__login/`、`/api/` 返回 404；`robots.txt` 全站 Disallow，响应头带 `X-Robots-Tag: noindex, nofollow`，页面本身也有 noindex。
- 深链：`https://news.kwinweng.com/#/item/<id>`（`REBANG_PUBLIC_BASE` 默认 `https://news.kwinweng.com/`，经 `--public-base` 写进 `data/meta.json`；8:30 私聊稿 `python3 -m rebang.push` 读它）。
- 旧阅读器：`shiguang-reader.service` 已 `disable --now`；`shiguang-reader-update.timer` 仍在跑（灵记的 `lingji-news-source` 只读它的 `topics.sqlite3`）；`shiguang-reader-ai.timer` 原本就是 disabled。

## 回退
1. 根路径回到旧阅读器：服务器恢复 `/etc/nginx/sites-available/news.kwinweng.com.conf.bak-20261115-160953-pre-root`（UTC 时间戳），`systemctl enable --now shiguang-reader.service`，`nginx -t && systemctl reload nginx`。阅读器数据备份在 `/root/backup-shiguang-reader-20261115-160953/`。
2. 更早的状态（只有 `/rebang/` 公开）：`.bak-20261115-151539-pre-rebang`；gh-pages 上线前的头在备份分支 `gh-pages-pre-rebang-20261115`。
3. 站点内容出问题：服务器上一版在 `/var/www/news.kwinweng.com.news-sync-previous`；或在 box 上把 `site-v11.prev` 换回 `site-v11` 后跑 `sh tools/publish_pages.sh --already-built`。
4. 代码：在 GitHub revert 合并 PR。
