# frontend-v11 证据

- 截图：`capture.py <站点> <输出>` 对着设计检查点预览包（真实数据快照 + history 分支 features）在 390×844（2x、触摸）逐项操作截图，`capture-log.json` 记录每张图验证了什么、页面报错（本次为空）。
- `compare-v10-vs-v11.png`：左 v10 设计稿，右三张 v11（时事首屏、数码到底、即刻空状态）。`24-desktop-1280.png` 为 1280 宽。

## 契约变更请求（前端/构建依赖、契约里还没有的东西）

1. `image_local{path, rel?, width, height, alt?}`（sources-ingest 已产出）写进 `rebang.items/1`；构建后 `image.url` 可以是站内相对路径 `media/…`（现 schema 要求 http(s)，站点产物不再回头校验，但应在契约里说明）。
2. 信封级 `sources[]`（id/channel/status/reason）与博主信封 `platforms[{id,name,status,last_ok_at,reason?,accounts[]}]` 写进契约（现为各分支私下约定）。
3. 站点产物格式定名：`rebang.site-meta/1`（`data/meta.json`，含 `public_base`、`unavailable`、`note`、`fixture`、各频道 `banner`/`pages`）、`rebang.page/1`（`data/channel/<slug>/page-<n>.json`，`has_more`）、`rebang.site-bloggers/1`、`data/id-index.json`（id → 数据文件，深链用）。push-0830 读 `public_base` 依赖第 3 条。
4. 卡片摘要会去掉开头的裸链接（数码频道 TG 摘要常以 URL 开头）；更合适是 ingest 侧清掉，请 sources-ingest 评估。
