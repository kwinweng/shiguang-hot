# 拾光热榜

多来源资讯聚合站：Telegram 频道、推特爆款、GitHub 热门、环球要闻、今日重点，以及 RSS / YouTube，每 30 分钟更新。

- 线上版：https://kwinweng.github.io/shiguang-hot/
- 公开 `gh-pages` 是 `news.kwinweng.com` 与其 iOS reader 的唯一站点数据源。公开白名单包括新增的 8 个 Telegram 频道；历史归档从保留的 `tg.db` 全量重建，配图由 Box 本地媒体缓存复制发布。
- `mail`（邮件精华）已退役，不再采集或出页；它不属于公开历史来源，删除配置后仍由隐私检查永久禁止发布。
- `news.kwinweng.com` 每 20 分钟无凭据接收公开产物，经校验后原子替换静态树；安装、备份、reader 预检与回退见 [同步说明](deploy/README.md)。
- 页面：今日（含时光机）/ 热点（24 小时时间轴）/ 栏目（按渠道、按标签）/ 收藏。所有来源先变成同一种条目，再由页面按时间、渠道或标签去取。
- Box bot routine 每小时 :07/:37 构建 `site/` 并发布到 `gh-pages`；Pages 从分支根目录部署。切换与回滚见 [操作说明](docs/BOX-SCRAPER-CUTOVER.md)。
- 代码在 `shiguang/`（收内容 → 统一 → 加工 → 出页），样式和脚本在 `web/`，工具在 `tools/`，测试在 `tests/`。
- 架构、页面规则和 `sources.json` 字段：`ARCHITECTURE.md`；投递新内容：`INGEST.md`。
- 设计规范：「光」视觉规范 https://claude.ai/artifact/R2fskGqeaA8ozH9e7BHfNE ，对应关系见 `ARCHITECTURE.md` 的「视觉规范」。
- 本地预览：`NO_FETCH=1 python3 pipeline.py`，然后打开 `site/index.html`。

`screenshot.png` 是「今日」的手机端截图。
