# 拾光热点

多来源资讯聚合站（Telegram 频道、推特爆款、GitHub 热门、环球要闻、今日重点等）。

- 线上版：https://kwinweng.github.io/tg-digest/
- 页面不在仓库里：每小时由 GitHub Actions（`.github/workflows/`）运行 `sitebuild.py` 生成到 `site/` 并部署到 Pages，所以仓库里看不到 HTML 成品，请以线上版为准。
- 样式与交互：`style.css`、`app.js`；页面模板：`render.py`；内容结构：`items.py`、`textclean.py`；组页与发布：`sitebuild.py`；环境光：`light.py`；底栏与来源配置：`sources.json`（`nav` 段）。
- 架构与接入新来源：`ARCHITECTURE.md`、`INGEST.md`。
- 设计规范：「光」视觉规范（sun #e3a01e 为唯一强调色，只作填充）+ 苹果液态玻璃风格。
- 本地预览：`NO_FETCH=1 python3 pipeline.py`（用现有 tg.db，不抓取）后打开 `site/index.html`；`python3 sitebuild.py` 只重建 inbox 栏目页。

`screenshot.png` 是 2026-10-17 的手机端截图。
