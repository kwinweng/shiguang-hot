# 拾光热榜

多来源资讯聚合站。仓库里有两套站点，共用同一个 Telegram 采集库 `tg.db`：

| | 拾光热榜 v11（现行） | 旧站（保留运行，不再对外主推） |
|---|---|---|
| 线上 | https://news.kwinweng.com/ （2026-11-16 起根路径；`/rebang/` 301 到根；全站 noindex） | 仍随 gh-pages 根目录发布到 https://kwinweng.github.io/shiguang-hot/ （阿欢已批准关闭，API 无法关掉，需在仓库 Settings → Pages 把源改为 None）；news.kwinweng.com 不再提供 |
| 内容 | 6 频道（时事/环球/财经/科技与 AI/数码/工具与项目）+ 博主 + 热搜 + 收藏 + 搜索 | 资讯 / 探索 / 我的 |
| 代码 | `rebang/`（采集适配、建站、推送稿）、`web-v11/`（前端） | `pipeline.py`、`shiguang/`、`web/` |
| 产物 | `site-v11/`、`var/rebang/`（均不进 git） | `site/`（不进 git） |
| 文档 | [`docs/rebang-v1/`](docs/rebang-v1/) | [`docs/LEGACY-SITE.md`](docs/LEGACY-SITE.md)、`ARCHITECTURE.md`、`DESIGN.md`、`INGEST.md` |

## 先读哪些

1. [`AGENTS.md`](AGENTS.md)：谁能做什么、审批红绿灯。
2. [`HANDOFF.md`](HANDOFF.md)：现在做到哪、下一步。
3. [`DECISIONS.md`](DECISIONS.md) / [`NOT-DOING.md`](NOT-DOING.md)：阿欢亲口定的事和定了不做的事。
4. v11：[`docs/rebang-v1/CONTRACT.md`](docs/rebang-v1/CONTRACT.md)（数据契约）、[`docs/rebang-v1/MODULES.md`](docs/rebang-v1/MODULES.md)（各模块入口、输入输出、已知缺口）、[`docs/rebang-v1/OPERATIONS.md`](docs/rebang-v1/OPERATIONS.md)（发布链路、服务器、回退）。
5. 采集与发布：[`docs/BOX-SCRAPER-CUTOVER.md`](docs/BOX-SCRAPER-CUTOVER.md)（`tools/box_scrape.sh`）、[`docs/SOURCE-FETCH-OPERATIONS.md`](docs/SOURCE-FETCH-OPERATIONS.md)（逐来源小时配额、blocked）、[`deploy/README.md`](deploy/README.md)（服务器 news-sync）。

## 关键位置

| 要找 | 在哪 |
|---|---|
| v11 频道、来源、博主、热搜配置 | `rebang/contract/channels.json`、`bloggers.json`、`hotsearch.json`；校验 `rebang/contract/schema.py` |
| v11 一键刷新（抓取 → 建站 → 发布） | `tools/rebang_refresh.sh` |
| v11 静态站构建 | `rebang/site/`（`python3 -m rebang.site`） |
| v11 前端 | `web-v11/index.html`、`app.js`、`lib.js`、`app.css`、`features/`（收藏、搜索） |
| v11 图标（标签页 / 主屏 / 启动图 / 分享图；顶栏不用） | `web-v11/brand/`、`tools/build_rebang_icons.py` |
| 8:30 今日重点私聊稿 | `rebang/push/`（`python3 -m rebang.push --dry-run`） |
| 英文翻译回填 | `rebang/translate/`（`python3 -m rebang.translate pending` / `fill`） |
| TG 采集（写 `tg.db`）、旧站构建 | `pipeline.py`、`shiguang/ingest/telegram.py`、`shiguang/site/build.py` |
| 采集 + 数据提交 + 发布 gh-pages | `tools/box_scrape.sh` → `tools/persist_action_data.sh` → `tools/publish_pages.sh` |
| 服务器接收端 | `deploy/news-sync.sh`、`.service`、`.timer` |
| 测试 | `tests/`（`python3 -m pytest -q`；`node --test tests/*.test.js`） |

## 常用命令

```sh
sh tools/rebang_refresh.sh                 # v11 全流程（生产克隆里跑会发布）
sh tools/rebang_refresh.sh --no-publish    # 只抓取和建站
python3 -m rebang.site --out /tmp/site-v11 # 只建站（无 var/rebang/in 时读测试样例）
NO_FETCH=1 python3 pipeline.py             # 旧站离线构建到 site/
python3 -m pytest -q && node --test tests/*.test.js
```

已知基线：`tests/test_news_modules_browser.py` 的 dark 主题子用例在未改动的 main 上也失败。
