# 拾光热榜 v11 上线与运维（2026-11-15）

## 发布链路
- 代码：`main`（box 上生产克隆 `/workspace/shiguang-prod`，旧站抓取 `tools/box_scrape.sh` 每次运行前会 ff 到 origin/main）。
- 刷新：`sh tools/rebang_refresh.sh`（不需要 token）：t.me 附加信息 → 热搜+归档 → 博主（博客、公众号；X 读 `var/rebang/x-dump/` 最新转储）→ TG/RSS/官方源入库（自动用翻译缓存）→ 建 `site-v11/`（原子替换，保留 `site-v11.prev/`）→ `tools/publish_pages.sh --already-built`。
  加锁（`var/rebang/.refresh.lock`；发布时再拿 `.box-scrape.lock`，与旧站抓取互斥）；一步失败保留上次数据继续；建站失败不替换、不发布。日志 `var/rebang/logs/`，最近一次结果 `var/rebang/logs/last-refresh.json`。
- `tools/publish_pages.sh` 把旧公开站 `site/` 与 `site-v11/`（放进 `rebang/` 子目录）一起强推 gh-pages。旧站树保持原样，所以服务器 `news-sync` 校验与 reader 导入不受影响。`REBANG_PUBLISH=0` 可只发旧站。
- 服务器：`news-sync.timer` 每 20 分钟拉 gh-pages → `/var/www/news.kwinweng.com`；nginx `location ^~ /rebang/ { auth_basic off; … }` 公开 `https://news.kwinweng.com/rebang/`，其余路径（reader、旧站）保持原有密码保护。
- 深链：`https://news.kwinweng.com/rebang/#/item/<id>`（`--public-base` 写进 `data/meta.json`，8:30 私聊稿 `python3 -m rebang.push` 读它）。

## 回退
1. 只下线 v11：把 `site-v11` 改名（或 `REBANG_PUBLISH=0`）后跑一次 `sh tools/publish_pages.sh --already-built`；20 分钟内服务器同步掉 `rebang/`。
2. nginx：删掉 `/rebang/` 那个 location（备份文件见服务器 `/etc/nginx/sites-available/news.kwinweng.com.conf.bak-*`），`nginx -t && systemctl reload nginx`。
3. 代码：在 GitHub revert 合并 PR。
