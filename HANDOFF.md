# HANDOFF
（拾光资讯 v11。更早的交接记录在 `docs/HANDOFF-history.md`；v11 各模块开发记录已并入 `docs/rebang-v1/MODULES.md`。）

## 目标
6 频道资讯站按 `docs/rebang-v1/CONTRACT.md` 稳定刷新；按 11/23 定的串行计划逐步改进。

## 2026-11-27 交接增量（北京时间）
- **#86 微信读书已验到真回包**：01:05 自然轮次后，公网 `data/health.json` 01:10:31 生成，5 个微信读书账号均为 `ok`、各 1 条；夕小瑶 10 条，共 15 条。未手动重触发；微博按用户要求暂缓。
- **官网中文发布门槛**：当前工作区有本地补丁和 [验收规格](docs/rebang-v1/CHINESE-NEWS-PUBLICATION.md)，未提交、未上线。R2 发现旧摘要无法证明来源，最终改为缺证即暂扣；聚焦验收通过，最终补丁未获独立复核放行。上生产前还须验证已批准的 Flash 回填能处理 Mini 的待译队列。
- **X**：基线 `70291d9d` 加原工作区未提交的两批限制，已在独立本地副本合入 #86。R2 后改为校验完整可读批次、优先保留可读备份、原子拒绝同名覆盖；最终 92 项离线通过，最终补丁未独立放行。旧工作区未改，未合并、未上线，未试推私库，不改生产任务或凭据。
- **来源评估**：三家公众号候选和 Telegram Telegraph / 即时预览的实证、回退和授权边界见 [来源调研](docs/rebang-v1/WEB-SOURCE-CANDIDATES.md)，均未接新来源。

## 此前状态（2026-11-25）
- **线上**：https://news.kwinweng.com/ 。11/24 晚发布已迁到 Mac mini（线程「迁移拾光资讯发布到 Mini」）：首轮手动发布线上核实为 `06d08d7c`（新闻约 2400 条、博主 293 条、仍 noindex）；系统级定时任务已装，每小时 :05 运行，首次自然运行（11/25 01:05）的结果尚未核实。线上代码版本看 gh-pages `build-info.json` 的 `source_commit`。
- **mini 发布器的停发问题**：代码固定在 `--code-sha`（`tools/mac_publish.py`，见 `docs/rebang-v1/MAC-PUBLISH.md`），`main` 一有非它自己推的提交（哪怕只改文档），下一轮就写 `.git/mac-publish/HALT` 停发。PR #83 经四轮复核仍有交接复杂度问题，阿欢 11/25 10:09 定先不做自动跟进：mini 保持当前手动换版本方案，每次合并后手动换版本、清停发标记；自动跟进另立新需求，后续按「先试跑、下一轮再切」的更简单思路排期重做。
- **GitHub Pages 已停用（11/25 00:40）**：旧 Pages 地址 404；`gh-pages` 分支保留，news.kwinweng.com 的同步照常（停用后第一轮自然同步 00:42 成功）。不要改或删 `gh-pages`。
- **仓库改名**：引用改名的分支 `chore/shiguang-news-repo-identity` 阿欢 11/25 同意全部合并（含代码里换成 `shiguang-news` 的仓库名）；GitHub 上真正改名放到 5 步之后。真正改名前，`tools/dispatch_hourly.py` 和 README 里的新地址用不了；服务器上的 `news-sync.sh` 是单独装的一份，不受合并影响，改名时须基于服务器现装版本做最小改动。细节见 `进度.md`。
- **采集缺口（11/23 23:10）**：X 16 个博主 0 条（没收到原始转储）；微博 6 个 0 条（疑似 Cookie 失效）；公众号 6 个只有「夕小瑶科技说」有内容（其余 5 个等微信读书扫码）。即刻、YouTube、博客、6 个新闻频道正常。
- **测试环境**：见 `AGENTS.md`「开发验收」。

## 串行计划（阿欢 11/23 确认，11/25 补 0.5 步和第 1 步形式；一步一分支，合并并核验线上后再合下一步）
0. ✅ `chore/t3-handover-rules`（PR #81）：规则、两个积压 PR。
0.5 ⏸️ `fix/mac-publish-follow-main`（PR #83，暂挂）：四轮跨模型复核仍有交接复杂度漏洞，阿欢 11/25 10:09 定先不做，保持手动换版本；后续另立新需求按「先试跑、下一轮再切」的更简单思路排期重做。mini 发布目录迁移（`~/projects/shiguang-news-publish`）与浅克隆放到下次手动换版本时一起做。
1. `feat/source-health-monitor`：统一来源健康表（各新闻频道、博主平台的最后成功时间、条数、状态、失败原因），**先做成网页里的健康看板**（阿欢 11/25），提醒渠道以后再接。
2. `fix/blogger-collection-recovery`：查清并恢复 X 原有转储供稿；微博新 Cookie、微信读书扫码时停下来请阿欢操作，验证真回包后合并。
3. `chore/source-audit-archive`：盘点 `sources.json`、`trial-sources.json`、`rebang/contract/*.json` 与旧站代码（TG 采集仍靠 `pipeline.py`/`shiguang/`，先迁移再归档），出「在用 / 归档 / 删除」清单和「环球」等薄弱频道的免登录来源建议。**清单先给阿欢过目再执行。**
4. `feat/blogger-twitter-feed`：博主页改成推特/微博手机版式信息流 + 个人用户流。**先做样页给阿欢确认。**
5. `feat/dedup-and-auto-highlights`：跨来源去重、同类事件合并（主条 + 折叠同源）；「今日重点」自动打分（多源交叉、来源权重、时效），只做筛选不做热点排行。**先确认打分偏好。**
6. 名字统一成 News、清除 hot/热榜（阿欢 11/25 01:36 定，取代「rebang 不改」）：产品叫「拾光资讯」，英文和技术标识一律 `shiguang-news`。清除范围含 GitHub 仓库、本地主仓与工作树、T3、remotes、服务器同步脚本、Air，以及 `rebang/` 模块、`site-v11` 产物、`gh-pages` 里的 `rebang/`、站点 `/rebang/`、`docs/rebang-v1`、`rebang_refresh.sh` 和测试/文档里的有效引用；历史记录保留原文。线上分「新旧并存 → 服务器切新路径并核验自然同步 → 删旧路径」三段，每段可回退；GitHub 改名、服务器/nginx、定时任务、删文件逐段请阿欢批准。方案见 `docs/rebang-v1/NEWS-RENAME-PLAN.md`。

## 其他待办
1. 采集断更恢复方案见 `docs/rebang-v1/COLLECTION-RECOVERY.md`（11/21）；11/22 晚起每小时数据提交与发布已恢复，执行主机待第 2 步一并查清。
2. 新需求待排期（阿欢 11/25 10:09）：合并 `main` 后自动给 Mac mini 发布器换版本，按「先试跑新版本、确认无误后下一轮再正式切换」的更简单思路重做（取代暂挂的 PR #83）。

## 已定的决定
- 开发、合并、上线由 T3 Code 接手，非高风险改动测试通过即合并上线再汇报（阿欢 11/23 破例，取代 11/15 仅 Grok、11/17 逐次批准）；见 `AGENTS.md`、`DECISIONS.md`。
- 一个来源只进一个频道，不按条拆；18 个 TG（去掉 reorx_share）；不做自动热点榜；YouTube、TG 评论楼/视频不在第一期（第二期已做评论楼和 YouTube 管道）；灵记快讯页 2026-11-16 砍掉（见 NOT-DOING）。
- 11/15 21:26 决定今日重点不进频道：当时放博主页 Grok bot。11/22 取消该平台分组，保留频道里同链接的条目只打「今日重点」标。
- 热搜：百度 + 知乎 + B 站，不要微博；每家独立、失败就空；放底栏「热搜」页，按北京日期归档 60 天（11/15 20:41 / 21:26）。
- 界面现为 v16 视觉（PR #74，白底红色强调，令牌见 `web-v11/app.css`；底栏 频道/博主/热搜/收藏）；左右模式下横滑只换频道，收藏/分享靠长按（11/15 23:05）；收藏只存本机浏览器；英文先显示译文、标「机器翻译」。
- 8:30 私聊：11/17 阿欢说「不做了」（见 NOT-DOING）；11/23 确认的计划里要「谁断更早上直接提醒你」，11/25 阿欢定第 1 步先做网页健康看板，提醒渠道以后再接。
- 新代码在 `rebang/`、`web-v11/`；旧 `shiguang/`、`web/`、`pipeline.py` 继续负责 TG 采集和旧站，行为不改。
- 新站归档（条目、热搜、翻译缓存、X dump、媒体）放在生产克隆的 `var/rebang/`，不进 git。

## 以后再说
- `public-feeds/` 最后一次数据提交是 `62a26398d`（2026-10-23 21:20 北京时间）。当天 `/workspace/tg-local/sync.sh` 改为调用 `publish_public.py --no-push`（改前备份 `sync.sh.bak-20261023-pause-push`），之后日志为 `public feeds prepared; no git mutation`。v11 直接读盒子上的原始成品目录，不受影响。
- 旧站回顾：盒子上未见调用 `tools/daily_summary.py` 的例程、cron 或近期日志。`site/history/` 由每次 `pipeline.py` 建站时的 `shiguang/site/news.py` 写入（摘要仍是 MOCK）；生产克隆没有仓库根目录的 `history/` 缓存。脚本还在，设计为 00:30 重跑前一天。
