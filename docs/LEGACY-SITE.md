# 旧站（v0）现状与历史

旧站是 `pipeline.py` + `shiguang/` + `web/` 生成的 `site/`。2026-11-16 起 news.kwinweng.com 只提供 v11，旧站不再从这里对外提供，但**还不能停**：

- `tools/box_scrape.sh`（工头「热榜抓取发布」例程，:07/:37）跑旧站流水线，把 TG 采集写进 `tg.db` 并提交 main；v11 的 TG 条目就读这个库。
- `tools/publish_pages.sh` 把 `site/` 放在 gh-pages 根目录、`site-v11/` 放在 `rebang/`。服务器 `news-sync` 的校验仍按旧站格式检查（`index.html` 的 public 标记、归档 manifest、`data/live.json` 新鲜度、文件数下限，见 [`deploy/README.md`](../deploy/README.md)），旧站树缺了就整次不发布。
- GitHub Pages（https://kwinweng.github.io/shiguang-hot/ ）仍从 gh-pages 根目录公开旧站。

架构与来源配置见 [`ARCHITECTURE.md`](../ARCHITECTURE.md)，视觉规范见 [`DESIGN.md`](../DESIGN.md)，期刊投递见 [`INGEST.md`](../INGEST.md)。

## 当前页面（2026-10-24 两模块版）

- 底栏三格：资讯 / 探索 / 我的；默认进资讯·实时。资讯标签：实时 / 热点（以北京时间 22:00 日报为界）/ 回顾（前后日期、横滑日期条，不做日历）。探索：好玩 / 好看 / 好买，只显示有真实数据的分类。我的：收藏、设置、关于。
- 六个标签都能下拉刷新：用 `cache: 'no-store'` 重读已发布数据，提示「新增 N 条」或「已是最新」，不现场抓取。
- 统一行布局 C、无图详情页、骨架/空态/出错重试/离线缓存/404「回到资讯」，亮暗两套。
- 不做：登录、评论、分享卡、推送、下单支付、个性化推荐。
- 检查：`python3 tools/check_two_modules.py` 生成 393×852 亮暗截图到 `docs/qa/two-modules-20261024/`。

## 数据文件

- `site/data/live.json`：最新在前的 TG 消息与北京时间小时分组（news-sync 要求非示例、非空、2 小时内更新）。`site/data/sources.json`：公开来源及当天/7 天计数。`site/data/explore.json`：探索条目（来自 `tg.db` 的 `trial_item`）。
- `history/YYYY-MM-DD.json`（回顾）：`python3 tools/daily_summary.py` 生成，设计为北京时间 00:30 跑前一天；摘要是 **MOCK**（相同标题合并、摘取原文），没有真实 AI 总结；`FlashProvider` 是未实现的占位。是否有例程在跑：未确认。
- 离线预览：`NO_FETCH=1 SITE_MODE=public python3 pipeline.py`；`SAMPLE_DATA=1` 强制用合成样例（标题前缀 `[示例]`）。

## 已不再使用的旧方案

- GitHub Actions 定时采集与 `tools/dispatch_hourly.py` 外部触发：已由 box 采集取代，`.github/workflows/hourly.yml` 只剩手动跑测试。`dispatch_hourly.py` 和测试还在仓库里，未接任何例程。
- 内网版（`SITE_MODE=private`，`/workspace/tg-local/sync.sh`）原先用 `/home/box/tools/shiguang-deploy/sync-news.sh` rsync 到服务器；该脚本 11/15 已加守卫默认跳过（它会覆盖公开树）。

## 旧站产品决定摘要（2026-10，已被 v11 取代）

| 编号 | 日期 | 决定 |
|---|---|---|
| RB-001 | 10-24 | 开发流程按 SOP v0.9（已由 `AGENTS.md` 现行规则取代） |
| RB-002～004 | 10-24 | 底栏资讯/探索/我的；资讯三标签均可下拉刷新；探索好玩/好看/好买 |
| RB-005 | 10-24 | 无图条目用 C 版式；logo 用 D 方案 |
| RB-006～008 | 10-23/24 | 历史回顾整页、按分类筛选；去掉旧资讯区和「看往日」日历；回顾页不做「今日重点」卡片 |
| RB-009 | 10-23 | 每小时抓取挪到自有机器执行 |
| RB-010～011 | 10-22 | 沿用灵记视觉系统 v0.2、图标 Phosphor；主色正红，支持暗色 |
| RB-012 | 10-22 | 信源调整：停 3 个、试接 13 个（`trial-sources.json`） |

旧站上线两周复盘标准（10-24 定）：一周至少 5 天打开；热点每天 22:30 前更新、两周断更不超过 1 次；实时最多晚半小时；探索每天有新条目。是否做过复盘：未确认。

已删除的旧规划/实现记录（Spec r1–r3、PR B 实现说明、两模块 Spec 与验收、旧 PLAN、Actions 定时方案）都在 Git 历史里，删除提交见 `docs/audit-20261116` 合并请求。
