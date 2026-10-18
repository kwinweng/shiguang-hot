# 拾光热榜

多来源资讯聚合站：Telegram 频道、推特爆款、GitHub 热门、环球要闻、今日重点，以及 RSS / YouTube，每 30 分钟更新。

- 线上版：https://kwinweng.github.io/shiguang-hot/
- 页面：今日（含时光机）/ 热点（24 小时时间轴）/ 栏目（按渠道、按标签）/ 收藏。所有来源先变成同一种条目，再由页面按时间、渠道或标签去取。
- 页面不在仓库里：GitHub Actions 每 30 分钟运行 `pipeline.py` 生成 `site/` 并部署到 Pages。
- 代码在 `shiguang/`（收内容 → 统一 → 加工 → 出页），样式和脚本在 `web/`，工具在 `tools/`，测试在 `tests/`。
- 架构、页面规则和 `sources.json` 字段：`ARCHITECTURE.md`；投递新内容：`INGEST.md`。
- 设计规范：「光」视觉规范 https://claude.ai/artifact/R2fskGqeaA8ozH9e7BHfNE ，对应关系见 `ARCHITECTURE.md` 的「视觉规范」。
- 本地预览：`NO_FETCH=1 python3 pipeline.py`，然后打开 `site/index.html`。

`screenshot.png` 是「今日」的手机端截图。
