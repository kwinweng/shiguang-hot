# 拾光热点

多来源资讯聚合站：Telegram 频道、推特爆款、GitHub 热门、环球要闻、今日重点等，每小时更新。

- 线上版：https://kwinweng.github.io/tg-digest/
- 页面：收藏 / 日报 / 首页 / 热点 / 栏目。所有来源先变成同一种条目，再由这 5 个页面去取。
- 页面不在仓库里：GitHub Actions 每小时运行 `pipeline.py` 生成 `site/` 并部署到 Pages。
- 代码在 `shiguang/`（收内容 → 统一 → 加工 → 出页），样式和脚本在 `web/`，工具在 `tools/`，测试在 `tests/`。
- 架构、页面规则和 `sources.json` 字段：`ARCHITECTURE.md`；投递新内容：`INGEST.md`。
- 设计规范：「光」视觉规范 https://claude.ai/artifact/R2fskGqeaA8ozH9e7BHfNE ，对应关系见 `ARCHITECTURE.md` 的「视觉规范」。
- 本地预览：`NO_FETCH=1 python3 pipeline.py`，然后打开 `site/index.html`。

`screenshot.png` 是首页的手机端截图。
