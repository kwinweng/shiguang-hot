# 交接记录

## 2026-11-26～11-27 交接（11/28 从 HANDOFF 移入；其中 11/26–27 发布与复核记录原只存在未提交的本地副本）

### 最新发布状态（2026-11-27）
- **双源及 #94 新 Logo 已上线。** #93 合并 `60fd0ab3`；00:05 自然发布记录为 `source_commit=c814da47`（含 #93、#94）、`gh-pages=f7afcb26`，00:22 公网 `data/meta.json` 指纹 `fd4bc73b…` 与发布包一致，首页、JS、CSS 和三份图标亦一致。该轮公开数据未观察到重点正例；R3 未通过的结论不变。
- **#86 已按批准合并并切 Mini，公网和真实采集待验。** 用户确认候选 `1f909bf8`，合并 `ba0d8554` 与候选 tree 一致。Mini 在发布锁内备份数据库、状态及 plist，切换并重载原任务，数据库字节未变；仍等现有 :05 自然发布及之后的公网同步。微博 Cookie 和微信读书扫码由本人操作。
- **#86 测试与复核记录。** GPT-6.2 Sol 对 `16a8e4e2` 的限定 R3 通过，守卫 `unchanged`；复核环境因沙箱无法绑定本地端口，有一例未执行到断言，主线程聚焦 269/269。同步数据提交 `00b05d49` 后候选 `1f909bf8`，受审差异 SHA-256 仍为 `0c4cab8b…`，候选数据库对象与 main 一致。重跑全量 Python 889 过、2 跳过、144 子用例过，Node 50/50。
- **X：继续走 HTTPS 私库中转，Mini 最多留两批自管转储。** 用户转报盒子经代理访问 GitHub 网页和 API 均返回 200；未验证认证推送，未建例程。重做候选 `70291d9d` 已推功能分支，开发方全量 Python 753 过、2 跳过，Node 50/50；目前仍保留 24 批，需改为两批并独立复核，未开 PR、未上线。

### 11/26 开发与复核记录（历史状态，以上述最新状态为准）
- **A 已上线并核验（11/26 23:22）。** 阿欢原话「同意 A 修复版直接合并上线」。[#92](https://github.com/kwinweng/shiguang-hot/pull/92)（分支头 `c38f5907`）合入 `eb49f87d`；Mini 专用 checkout 与定时任务固定到该版本（旧库备份 `~/projects/shiguang-news-publish/tg.db.bak-before-eb49f87d`）。23:05 自然发布推出 `main=458e4a3d`、`gh-pages=cc2901e8`，`build-info.json` 的 `source_commit=eb49f87d`；推送中的临时 HALT 自行清除。23:20 服务器同步后，公网 `data/meta.json` SHA-256 `06faa441…` 与 gh-pages 一致，`app.js`/`app.css`/`index.html`/`bloggers.json`/四个平台 `all/page-1.json` 逐字节一致，公网 `app.js` 含 `canRefresh`。390px Chromium 打开公网博主页：多平台混排、232 条节点、无脚本错误、无残留「正在刷新」。
- **双源最后一轮不通过，停在本地。** 阿欢原话「选 1，再给双源一轮复核」。受审提交 `789b6fa6` 的父提交是 `eb49f87d`，送审 diff SHA-256 `7d45adaf…`。实际执行 GPT-6.2 Sol；主线程验证 `review-guard verify` 为 `unchanged`，补丁指纹一致。主线程在该提交原样复跑 35 个离线建站/归档对照，27 个符合预期、8 个不符：4 例错标（利率上升却支持降息、精确到时刻的通车预告、明确未发的软件、两篇实报夹一篇通车预告），4 例漏标（实报提到后续减税、开放游客中心、发布安装指南〔英/中〕）。归档旧标一项已修好：只变抓取时间，日文件字节不变；正文或阅读数变更，`latest` 更新且 `first` 保留。四组仓内聚焦另跑 173 过、1 项环境跳过；送审前全量 Python 725 过、2 跳过，Node 50/50，均不能替代上述验收。**本轮不改双源代码，不开第四轮，不推送、不合并、不上线。**
- A 放行前的复核记录：`0e9870ce` 的 R3 为 GPT-6.2 Sol 只读，守卫 `unchanged`；第二轮四项均已修好，但首次加载中下拉会一直显示「正在刷新」。主线程在离线 Chromium 中用首读 200 和 503 两种情况复现；修复让手势与刷新按钮共用就绪条件，两个反例从红变绿，首读失败后可重试。增量 `1210f51c…`，聚焦 25 过、4 子用例过，完整 Python 611 过、2 项环境跳过、4 警告、133 子用例过，Node 50/50。最终修复未另做独立复核，A 的直接放行不适用于双源。
- 已出[规格与验收清单](docs/rebang-v1/RELEASE-QUEUE-2026-11-26.md)。以实际抓到的 `main=eaf84cf2` 为开发基线，正式博主页 A（简洁标题、点帖进原正文）、24 小时独立双源打标已分别派到独立工作区开发并测试；#86（`48c2606d`）另派离线发布预检。此处只记录已派发，不把测试、独立审阅或上线预记为通过。
- 博主页 A 候选：实现工作区 `t3-64868eb7-84cb1e971eab52fb`，在 `eaf84cf2` 上未提交的 4 个前端文件 + 2 个测试文件。开发方回报全量 Python 600 过、2 跳过、129 子测试过，Node 50 过；主线程重跑 Node 全量 50/50、离线手机交互/深链聚焦 13/13，`git diff --check` 通过。第 1 轮异家族只读审阅（GPT-6.2 Sol，守卫 unchanged）**不通过**，四个挡路项：同刻跨页排序与发布端相反、翻页遇换版混读新旧页、多图只显示首张、慢正文查找盖过新筛选。11/26 已先写红例（均在旧代码上失败）再修：同刻 ID 升序；博主分页写入与 meta 相同的 `built_at`，前端对不上就停下提示刷新（改了 `builder.py` 一行和 CONTRACT）；帖内多格；切筛选作废在途正文。Node 50 过，Python 全量 603 过、2 跳过。第 2 轮独立只读审阅实由 GPT-6.2 Sol 执行，主线程守卫 `unchanged`，差异仍为 `923ab793…`。**不通过，已到两轮上限，不合并不上线。** 多格媒体和慢正文取消通过回归；另复现旧索引漏掉新版平台、交错刷新把版本写回、末页消失后 404 重试无出口、亚毫秒排序反转。主线程已在受审版复现四项并补了深链/首次加载回归；保守版用同一指纹校验索引、分页与深链，旧刷新不能倒写，缺页有刷新出口，按建站端给出的顺序合流。隔离树全套 Python 610 过、2 跳过、4 条解析警告、131 子测试过；Node 50 过，`git diff --check` 通过，5 张测试截图另存。受审旧补丁保留，本地新补丁 `6ac3c75e…` **未经独立放行**；不追加第三轮，不合并不上线。
- 双源首版产品验收**未过**：主线程在真实 schema 的离线合成对照中，Apple 系统发行 2/2 有标，而降息、桥梁开通、案件裁决、中文降息这四组各 0/2。代码仅认一种 Apple 标题格式，不是全站新闻互证。未送正式复核、未提交或上线；已在独立工作区安排跨题材和中文补全，并增加替换主体、相反动作、近邻事件与原折叠主条兼容的验收要求。补全版已交回（工作区 `t3-81899f6f-d35bf72da834b7b2`，基线 `eaf84cf2`，未提交）：开发方报四类中英正例各 2/2、43 个近邻反例不标，Python 全量 642 过；主线程已用另四组替换主体/数字/编号的合成稿件逐组建站查实际正文：四组正例各 2/2，近邻事件、同稿、过期各 0/2；相关 pytest 107 过、1 个真实数据用例跳过。完整补丁 `fa6b0396…` 首轮 GPT-6.2 Sol 只读复核**不通过**，守卫 `unchanged`。六个挡路项：明示转载仍投票、标题与正文方向相反仍互证、含糊机构被视为专名、缺发布时间的缓存被视为当日、重新采集会换 #88 主条、同 ID 再入会抹掉历史旧标。修复候选已交回（工作区 `t3-b5ca707f-917f408dc6972a48`）；主线程再用真实 RSS/Atom 解析到建站的合成样本测出结构化出处丢失和明确反向正文仍打标，补了 11 项正反回归。第 2 轮送审差异 `42cd1f74…`：主线程聚焦 143 过、1 跳过；Python 全量 677 过、2 跳过、4 条解析警告，Node 49 过；截图另存。此前一版全量胶囊时钟失败 1 次、父提交没复现，不能认定是旧问题。
- **双源第 2 轮独立只读复核不通过，已到两轮上限。** 实际模型 GPT-6.2 Sol，主线程核验守卫 `unchanged`，补丁与送审指纹一致。审阅方原有 84 例通过，另测 4 例均失败，主线程在受审版逐例复现：正文明确说加息 25 个基点、桥尚未通车、软件尚未发布，却都给两篇报道打标；带旧标的新闻原样重采会抹掉归档 `latest` 的旧标。
- 双源只在本地作了保守修正（补丁 `7a8eaa13…`，不替代受审版）：正文明确反向或尚未发生就不计票；仅抓取时刻变动时保留旧新闻归档，日文件字节不变，正文或阅读数真的改变仍更新。复核方原版 4 条用例从 4 失败变 4 通过；聚焦 162 过、1 跳过，Python 全量 685 过、2 项环境跳过、4 条解析警告，Node 49 过。**本地修正版未经独立放行，不开第三轮；A 和双源均未提交、合并或上线，保持原顺序，不切 Mini。**
- **11/26 按要求继续修复和复测（仅本地）。** 双源新增 22 个中英用例，同一组在上一候选 `7a8eaa13…` 上 14 失败、8 通过；修正后 22/22 通过。利率维持不变，以及降息、通车、判决、发行的明确预告不当作实报；已发生事件的后续计划不因带 `will`/「将」被一律排除。混合三来源时，只给两篇实报打标，不给预告搭票。另用 6 组合成 RSS/Atom 走新读和缓存回读，各组结果一致；上轮独立复核的原版 4 例也全部通过。双源完整补丁 `11b1a629…`，本轮只改判定、测试和说明；聚焦 184 过、1 跳过，完整 Python 707 过、2 项环境跳过、4 条解析警告，Node 49 过。博主页 A 代码未改（仍为 `6ac3c75e…`）：换版/翻页/正文往返等聚焦 23 过，完整 Python 610 过、2 跳过、4 条解析警告，Node 50 过。这是重新自测，不是第三轮独立复核，A → 双源顺序和未放行状态不变；未提交、未合并、未上线。
- #86 离线预检已回：分支头 `48c2606d` 与指定 `main=eaf84cf2` 组合无冲突，候选 `01f05ad5` 聚焦 197 过，Python 全量 756 过、2 跳过、1 项为保护已有截图未跑；Node 49 过。主线程核对了组合的父提交和 `tg.db` 对象与该 main 一致。测试不代替已到上限的安全复核，#86 留分支，不堵 A → 双源。每次合前以当时实际 main 重测，公网对上这次合并才放下一项。全量改名沿用现有八段方案，待前序核验后再启动；本轮不改名、不改生产配置。

### X 供稿交接（2026-11-26）
- 长期方案 B：Grok 只导出，独立私库中转，Mini 只读收件且仍是唯一发布端。私库已建，Mini 的只读身份已验证；首份真包改走设备拷贝，与私库端到端验证区分。
- 草稿 [#91](https://github.com/kwinweng/shiguang-hot/pull/91) 仍在 `544af7f6`。两轮只读复核前后工作区指纹一致。半删批次、超时进程和发布锁已在本地修正；第二轮仍有三个挡路项：临时目录清理错误会误报、硬中断可能让 Git 缓存不能再用、缓存下载和累积缺少磁盘硬上限。**不合并，不在生产设置 `REBANG_X_INBOX_REPO`，不再开第三轮。**
- 保守落地只验单包：见功能工作区 `docs/rebang-v1/X-INBOX.md` 和 `tools/x_inbox_check.py`，两者的最新修正都还在本地。只读已交付的清单与包，不运行 Git，不装入生产。自动收件修正后的 Python 全量 616 过、2 跳过、99 个子用例过；加离线单包入口后聚焦 39 过、Node 49 过，Python 全量 621 过、2 跳过、99 个子用例过。
- **首份真包已离线通过（11/26 09:33，设备拷贝，不经 Git）。** Mini 收到批次 `20261126T0928`，时间 `2026-11-26T09:31:27+08:00`。独立核对清单（318 B、SHA-256 `1b23e4ec…`）和包（143411 B、`77bb4c72…`）与发件回执一致。裸 Python 缺 `bs4`；改用项目的离线 uv 3.11 依赖运行 `python -I -B tools/x_inbox_check.py`，校验 6 个 JSON 及元数据，并用 `read_export` 实读 75 条不重复主帖，通过。未将真实文件放入仓库、测试或发布目录。
- 发件方回报用 5/8 次调用，3 页各 25 条，第 3 页后仍有下一页；另取 75 条全文、36 条引用，未取热门回复。这是单包可用的证据，不是 24 小时抓全、线上恢复或持续交付的证明。不需为本次验收重抓。盒子到私库的 Git 写入仍未验证；不启自动收件、不改例程。

### #87 上线（2026-11-26 01:23）
- 合并 `74057b6a`，Mini 换版后 01:05 那一轮发布成功：gh-pages `source_commit` 为 `74057b6a`，公网 `/data/meta.json` 与发布包指纹一致（`f1dd30a8…`），首页 200，无 `HALT`。8 个新源在线上频道数据里都有条目（CNA 20、France 24 24、DW 11、NPR 10、Android Authority 50、MacRumors 20、selfh.st 3、It's FOSS 15，按来源名粗计）。

### 2026-11-27 交接增量（北京时间）
- **#86 微信读书已验到真回包**：01:05 自然轮次后，公网 `data/health.json` 01:10:31 生成，5 个微信读书账号均为 `ok`、各 1 条；夕小瑶 10 条，共 15 条。未手动重触发；微博按用户要求暂缓。
- **官网中文发布门槛**：当前工作区有本地补丁和 [验收规格](docs/rebang-v1/CHINESE-NEWS-PUBLICATION.md)，未提交、未上线。R2 发现旧摘要无法证明来源，最终改为缺证即暂扣；聚焦验收通过，最终补丁未获独立复核放行。上生产前还须验证已批准的 Flash 回填能处理 Mini 的待译队列。
- **X**：基线 `70291d9d` 加原工作区未提交的两批限制，已在独立本地副本合入 #86。R2 后改为校验完整可读批次、优先保留可读备份、原子拒绝同名覆盖；最终 92 项离线通过，最终补丁未独立放行。旧工作区未改，未合并、未上线，未试推私库，不改生产任务或凭据。
- **来源评估**：三家公众号候选和 Telegram Telegraph / 即时预览的实证、回退和授权边界见 [来源调研](docs/rebang-v1/WEB-SOURCE-CANDIDATES.md)，均未接新来源。

### 此前状态（2026-11-25）
- **线上**：https://news.kwinweng.com/ 。11/24 晚发布已迁到 Mac mini（线程「迁移拾光资讯发布到 Mini」）：首轮手动发布线上核实为 `06d08d7c`（新闻约 2400 条、博主 293 条、仍 noindex）；系统级定时任务已装，每小时 :05 运行，首次自然运行（11/25 01:05）的结果尚未核实。线上代码版本看 gh-pages `build-info.json` 的 `source_commit`。
- **mini 发布器的停发问题**：代码固定在 `--code-sha`（`tools/mac_publish.py`，见 `docs/rebang-v1/MAC-PUBLISH.md`），`main` 一有非它自己推的提交（哪怕只改文档），下一轮就写 `.git/mac-publish/HALT` 停发。PR #83 经四轮复核仍有交接复杂度问题，阿欢 11/25 10:09 定先不做自动跟进：mini 保持当前手动换版本方案，每次合并后手动换版本、清停发标记；自动跟进另立新需求，后续按「先试跑、下一轮再切」的更简单思路排期重做。
- **GitHub Pages 已停用（11/25 00:40）**：旧 Pages 地址 404；`gh-pages` 分支保留，news.kwinweng.com 的同步照常（停用后第一轮自然同步 00:42 成功）。不要改或删 `gh-pages`。
- **仓库改名**：引用改名的分支 `chore/shiguang-news-repo-identity` 阿欢 11/25 同意全部合并（含代码里换成 `shiguang-news` 的仓库名）；GitHub 上真正改名放到 5 步之后。真正改名前，`tools/dispatch_hourly.py` 和 README 里的新地址用不了；服务器上的 `news-sync.sh` 是单独装的一份，不受合并影响，改名时须基于服务器现装版本做最小改动。细节见 `进度.md`。
- **采集缺口（11/23 23:10）**：X 16 个博主 0 条（没收到原始转储）；微博 6 个 0 条（疑似 Cookie 失效）；公众号 6 个只有「夕小瑶科技说」有内容（其余 5 个等微信读书扫码）。即刻、YouTube、博客、6 个新闻频道正常。
- **测试环境**：见 `AGENTS.md`「开发验收」。

### 串行计划（阿欢 11/23 确认，11/25 补 0.5 步和第 1 步形式；一步一分支，合并并核验线上后再合下一步）
0. ✅ `chore/t3-handover-rules`（PR #81）：规则、两个积压 PR。
0.5 ⏸️ `fix/mac-publish-follow-main`（PR #83，暂挂）：四轮跨模型复核仍有交接复杂度漏洞，阿欢 11/25 10:09 定先不做，保持手动换版本；后续另立新需求按「先试跑、下一轮再切」的更简单思路排期重做。mini 发布目录迁移（`~/projects/shiguang-news-publish`）与浅克隆放到下次手动换版本时一起做。
1. `feat/source-health-monitor`：统一来源健康表（各新闻频道、博主平台的最后成功时间、条数、状态、失败原因），**先做成网页里的健康看板**（阿欢 11/25），提醒渠道以后再接。
2. `fix/blogger-collection-recovery`：查清并恢复 X 原有转储供稿；微博新 Cookie、微信读书扫码时停下来请阿欢操作，验证真回包后合并。
3. `chore/source-audit-archive`：盘点 `sources.json`、`trial-sources.json`、`rebang/contract/*.json` 与旧站代码（TG 采集仍靠 `pipeline.py`/`shiguang/`，先迁移再归档），出「在用 / 归档 / 删除」清单和「环球」等薄弱频道的免登录来源建议。**清单先给阿欢过目再执行。**
4. `feat/blogger-twitter-feed`：博主页改成推特/微博手机版式信息流 + 个人用户流。**先做样页给阿欢确认。**
5. `feat/dedup-and-auto-highlights`：跨来源去重、同类事件合并（主条 + 折叠同源）；「今日重点」自动打分（多源交叉、来源权重、时效），只做筛选不做热点排行。**先确认打分偏好。**
6. 名字统一成 News、清除 hot/热榜（阿欢 11/25 01:36 定，取代「rebang 不改」）：产品叫「拾光资讯」，英文和技术标识一律 `shiguang-news`。清除范围含 GitHub 仓库、本地主仓与工作树、T3、remotes、服务器同步脚本、Air，以及 `rebang/` 模块、`site-v11` 产物、`gh-pages` 里的 `rebang/`、站点 `/rebang/`、`docs/rebang-v1`、`rebang_refresh.sh` 和测试/文档里的有效引用；历史记录保留原文。线上分「新旧并存 → 服务器切新路径并核验自然同步 → 删旧路径」三段，每段可回退；GitHub 改名、服务器/nginx、定时任务、删文件逐段请阿欢批准。方案见 `docs/rebang-v1/NEWS-RENAME-PLAN.md`。

### 其他待办
1. 采集断更恢复方案见 `docs/rebang-v1/COLLECTION-RECOVERY.md`（11/21）；11/22 晚起每小时数据提交与发布已恢复，执行主机待第 2 步一并查清。
2. 新需求待排期（阿欢 11/25 10:09）：合并 `main` 后自动给 Mac mini 发布器换版本，按「先试跑新版本、确认无误后下一轮再正式切换」的更简单思路重做（取代暂挂的 PR #83）。


## 2026-11-22 Telegram 媒体与博主页修复候选
- Telegram 旧流程只缓存图片和视频封面，未把视频地址交给页面。候选从同一轮 `tgmeta` 公开页提取图及视频，复用网页查看器；不增加服务器端抓取请求，不改 `tg.db`。公开样本 `freechinese/113503` 的 MP4 已在手机尺寸 Chromium 实际播放；`tnews365/35797` 两张图能在查看器打开。`freechinese/113505` 的频道页和单帖挂件都只给封面（`Media is too big`），页面明确引导去 Telegram，不能承诺站内播放这类视频。
- X 目前没有新原稿：正在使用的 Mac 发布克隆没有默认 `var/rebang/x-dump`，目前能找到的本机开发转储是 11 月 18 日，超过 36 小时。旧刷新脚本还会在默认目录为空时直接跳过 X（包括已指定 `REBANG_X_DUMP` 的情形）。候选始终调用既有适配器、区分缺失/过期并保留上次成功帖子；按生成时点隔离回放旧转储，网页能显示 13 位博主的 80 条历史帖子，不算恢复持续采集。下一步是让已有供稿方送来一份新鲜转储做只读验收；若要新账号、接口、付费服务或调整任务，先报再做。
- 博主页 Grok bot 的配置、入口、图标、成品转帖路径已移除；不动旧站专用来源、8:30 稿或「今日重点」同链接打标。博主页改版另开分支。
- `shiguang-hot-ios` 的 `HotWebSession` 加载同一个线上网页，已允许内联媒体。共享改动影响 App，但不需改原生代码；未做 iOS 真机验收。未合并、部署或操作 LaunchAgent。未来获批合并前先安排在同一发布锁下核对 `main`、`gh-pages`、数据库和 `HALT`，另行校准检查点并确认固定运行代码如何切换；不要手删保护标记。
- 验证：Python 3.11 全量 445 通过、2 跳过，另有 87 个子测试通过；前端 39 通过。macOS 的默认 Python 3.9 不满足发布器的 Python 3.11+ 要求（缺 `hashlib.file_digest`），首次全跑还有 Steam RDF 失败；切到隔离的 3.11 环境后均通过。全量浏览器测试会重写 `docs/rebang-v1/evidence/history-favorites-search/` 三张历史截图，验完不要把这些产物混入 PR。

## 2026-11-21 采集断更
- 末次数据提交 `6313e1e3`，末次发布 `b0ed26e1`（11/20 01:20 北京时间）。旧采集例程暂停后，v11 刷新只重建新版产物，#77 按预期拒绝旧站 `live.json` 过期的组合包。盒子和服务器日志仍待核对；生产未恢复。
- 恢复候选在[采集断更恢复方案](docs/rebang-v1/COLLECTION-RECOVERY.md)。用 `box_scrape.sh --no-publish` 先完成真实采集与持久化，再由 v11 一次发布；单一例程须用外层锁。候选经独立技术评审（已验源 Opus 5.5）有条件通过，条件为单写入/单发布、外层互斥和盒子生产验收，见方案。合并、部署、例程和任何服务器变更另批。
- 本机用隔离 Git 和假 HTTP 验证真实旧流水线：新数据写入 `live.json`，#77 发布器 dry-run 通过，旧包仍拒绝。macOS 不能验证现有旧站的连续原子替换（main 用 Linux `renameat2`）；Mac 接管另做。采集测试夹具路径用 `resolve()`，避免 macOS `/var` 和 `/private/var` 指向同一临时目录却比较失败。

## 2026-11-21 对外更名一期（11/24 随第 0 步合并）
- [PR #78](https://github.com/kwinweng/shiguang-hot/pull/78) → `main`。新旧网页、PWA、分享、文档和测试统一为「拾光资讯」；`AGENTS.md` 按 14:47 确认改由 T3 agent 开发，审批红绿灯不变。
- 更名相关 pytest 60 通过、1 跳过（无真实 `var/rebang/in`）；前端 43 通过。macOS 全量 pytest 427 通过、7 失败、2 跳过；7 项均在干净的 `6313e1e3` 复现，dark 子用例在两边均通过。全量离线测试会改写 `docs/rebang-v1/evidence/history-favorites-search/` 下三张跟踪截图，本次已恢复，未提交截图。
- iOS 只在本地改显示名和提示并重新生成工程；主 Bundle ID 仍为 `com.kwinweng.shiguang-hot`，签名团队、描述文件、SKU 不变。仓库名、域名、`rebang` 路径和发布布局不变；未合并、部署、传 TestFlight 或操作采集例程。
- 下一步：等阿欢分别批准是否首次入库 `ios/` 和是否合并/发布 #78。采集恢复是另一任务。

## 2026-11-18 Mac 接管交接（PR #76，11/24 随第 0 步合并）


- **PR #73**（`290f744d`，11/16 23:48）：频道、博主各为连续长流；段间「下一个：X」，最后「内容已结束」；去掉全部「查看更多」。收藏、热搜只在各自页面无限下拉。
- **PR #74**（`f312142d`，11/17 01:28）：v16 视觉参考少数派，红色强调、白底、细分隔线、毛玻璃底栏，缩略图在右，X 头像无红边；热搜只叫百度/知乎/B站，日期用「今天」，顶栏无 logo，暗色跟随系统。旧 v10/v13 金色方向已被取代；实际令牌见 `web-v11/app.css`。
- **PR #75**（`f060942a`，11/17 10:01）：FREE 中文、双语新闻从环球移到时事。时事为竹新社、我的一张大字报、FREE 中文、双语新闻；环球为 BBC World、卫报 World。来源只归属一个频道，以 `rebang/contract/channels.json` 为准。
- **已定交互**：收藏、分享均长按卡片；横滑只切频道；图片可全屏、多图横滑；详情保留互动数、热门回复、TG 评论楼、X 引用卡片。
- **接管顺序与授权**：阿欢要求当前会话在 Mac 接管；先手动刷新并发布，线上核实成功后回报，再由阿欢通知旧机器停刷新循环和例程；旧任务停止确认前不启用新定时任务。目标为普通刷新、X+翻译各每 30 分钟。**08:30 私聊已由阿欢在 11/17 后续交接中取消，本机不创建；旧例程由阿欢在切换时暂停。** 站内今日重点整理来源保留。不要把这项授权扩大成任意代码合并或其他部署。

### 本机准备与阻塞

- **首次本机推送成功，但线上接管未通过：版本在观测前被覆盖**。11/17 23:53:52–23:54:14，`rebang_refresh.sh --no-fetch` 的 ingest/build/publish 全部成功，`failed` 为空。gh-pages SHA `454494cd5fabcd6386e2288aa1c77ed69a5faee8`，源码提交 `a951c7fc`，新站 `built_at=2026-11-17T23:53:53+08:00`，2579 条新闻、1027 条博主内容、pending 0；三家热搜在 23:53:30 均抓取成功。一次性核验两次仍见线上 23:39:37 版，随后发现 gh-pages 已被 `423e10bf`（23:55:54）替换，结果为 `publication_replaced_before_observed`，见 `var/rebang/logs/cutover-verification.json`。该覆盖版本的新站时间 23:55:50，旧站 build-info 指向原发布链路源码 `7177e323`；又一轮 `5d9da84c`（11/18 00:01:28）继续发布同一源码，浏览器实测线上已为 **11/18 00:01:25**（2578 条新闻、984 条博主内容，`fixture:false`），页面 meta、响应头及 robots.txt 的 noindex 均保留。提交的通用发布者名称不能单独证明具体执行主机；可以确定存在本次 Mac 发布之外的持续发布。本次没有盲目再次强推、没有改旧任务、没有创建新定时任务，也未报告接管成功。下一次发布须能覆盖服务器同步核验窗口；仍按阿欢既定顺序切换，不擅自先停旧任务。X 新读取、四份整理的持续接收、微博 Cookie、定时翻译的安全注入仍需落实。
- 已同步 `origin/main`（准备开始时 `296c8a14`，后续纳入 `59ba584` 自动数据），GitHub CLI 的功能分支与 gh-pages 写入均已实测。两个交接包均通过 `SHA256SUMS` 校验，运行缓存恢复到 `var/rebang/`，运行说明包仅隔离提取两份例程、翻译脚本和旧刷新循环；不复用 Linux 包里的虚拟环境或软链接。
- Mac 使用 `var/rebang/venv/bin/python`（Python 3.13），已安装现有运行依赖 beautifulsoup4、Pillow，以及验证/扫码所需 pytest、segno；安装 Homebrew `flock`。脚本运行需 `BOX_PYTHON="$PWD/var/rebang/venv/bin/python"`，PATH 需含 `/opt/homebrew/bin`。旧站已以 `NO_FETCH=1 SITE_MODE=public MAIL_DIGEST=0` 构建，并写出 `site/build-info.json`；没有运行会更新 `tg.db`、提交和发布的 `box_scrape.sh`。
- 接管最初的契约、站点、博主、今日重点测试 **105 passed**（Mac 修复后的 109 项结果见下文）。首次真实刷新仅跑 `--no-publish`；第一次因 T3 重启在 tgmeta 阶段终止，核实无残留进程后重跑。重跑于 **11/17 23:08:16–23:13:36** 完成，tgmeta、三家热搜、bloggers、ingest、build 均返回成功，`var/rebang/logs/last-refresh.json` 的 `failed` 为空，但语义检查发现四份整理输入全部为空，见下条。新站为真实数据（`fixture:false`），2573 条新闻、460 条博主帖子，不能以此覆盖线上完整内容。
- **23:14 早期预检（当时未推送；后续首次发布见上条）**：`publish_pages.sh --already-built --dry-run` 打包 1700 个文件，包含 `rebang/`。媒体重定位后 23:14:53 重建，1095 个站内媒体 URL 全部有对应文件，无缺失；`rebang.push --dry-run` 出 5 条根地址深链，仅出稿、未发送（其中新英文条目仍待翻译）。准备阶段浏览器读到的线上 `built_at` 为 11/17 22:49:19，2577 条新闻、1027 条帖子，meta + X-Robots-Tag + robots.txt 均保留 noindex。这是旧机器版本，**不是本机发布验收；当时未发布、未创建新定时任务**。当前切换状态以本节首条为准。
- **四份整理输入已补交并恢复**：最初缓存包仅有合并后的数据，首次 ingest 会丢掉 562 条整理帖子。阿欢随后交付 `rebang-digests-20261117.tar.gz`（23:24 快照），已校验 SHA256 并恢复到 `var/rebang/digests/20261117T2324/`。通过现有四个目录环境变量真实 ingest，world 173、x 138、hot-daily 118、github 133，共 **562 条全部恢复**。`HOT-DAILY_FEED_DIR` 名称含连字符，用 `env` 或 subprocess env 字典传入；不需要改适配器或 `sources.json`。原始资料仍由原「资讯」bot 每日生产，持续只读接收方式尚未落地，不能把今晚快照当成同步完成，见 `OPERATIONS.md`。
- **媒体迁移已验证**：包内 522 处本地媒体引用使用 `/workspace/shiguang-prod/...` 绝对路径；另有 699 处 TG 图片引用指向根目录 `media/`，这个目录不在 state 包内。已从现有 `origin/gh-pages` 的 `rebang/media/` 恢复缺少的公开图片（不改远端发布物）。原缓存 1221 处引用均能找到对应文件；刷新后的 bloggers 输入中仍有 517 处旧绝对路径，已仅对这些路径重定位到本机，修改前备份位于 `var/rebang/local-ops/before-media-relocation-20261117T231453/`。最终建站核对 1095 个站内媒体 URL，无缺失。后续再次恢复原包时仍需重定位，不能只看构建退出码。
- **登录与权限**：微信读书已由阿欢扫码登录，`weread status` 实测 `session:true, valid:true`，会话权限 `0600`。列表接口回 `-2041`，沿用现有 cover + 正文回退；首轮正文读取不稳定，复核时乱翻书、caoz 各抓到 1 条，夕小瑶公共源抓到 10 条；MacTalk、独立开发变现周刊、王建硕保留原快照各 1 条，未把缓存说成新抓取。恢复缓存时保留原 id 和时间，并修复 3 处旧媒体路径、补回 3 张原包图片。DeepSeek 密钥已由阿欢通过安全输入提供，仅传给翻译运行进程；23:38 实测 `deepseek-flash`（关闭思考）39/39 段成功、失败 0、pending 0，5 次请求、4182/2879 prompt/completion tokens。后续定时安全注入尚未配置。微博副号 Cookie 文件仍未到位，阿欢可直接拷到本机 `~/.config/rebang/weibo-cookie.txt`（0600），不经聊天；X API v2 新读取仍缺权限，不能转用旧 bot 的专有工具或擅自办理付费套餐。目前 X 仅读取已迁移的 dump。08:30 私聊已取消，无需投递渠道。凭据不查看、不打印、不提交。
- **Mac 连续建站兼容修复（待合并）**：旧站首次构建正常，目标 `site/` 已存在时 Linux 专用 `renameat2` 在 macOS 报 `symbol not found`。`shiguang/site/build.py` 已对 Darwin 使用系统 `renamex_np(RENAME_SWAP)`，Linux 保持 `renameat2(RENAME_EXCHANGE)`，两者均保留整树原子交换与失败不替换的契约。Mac 上 4 项既有原子构建回归通过；真实旧站连续重建两次成功，相关测试合计 **109 passed**。没有改成先删旧目录，也没有改变服务器发布方式。
- **TG 采集不能遗漏**：`rebang_refresh.sh` 的 ingest 只读 `tg.db`，tgmeta 只补公开元数据。新定时运行还需保留真正更新 `tg.db` 的既有采集步骤。`box_scrape.sh` 要求 `main` 且工作区干净，不能在有用户未跟踪文件的开发目录里强行运行或清理；旧机器仍写库时也不要启动第二个数据提交者。
- **持续供稿方案已验源，连接未落地**：独立技术方案来自 T3 子任务「四份每日整理持续供稿方案」，请求 `group/design-claude`，实测 `claude-opus-5-5`；`verify_t3_claude.py --task plan` 返回 `verified:true`，decision `57b8d9c3-adb7-49c7-a0ad-d7e5cb42de2f`。采用的准备方向是保留原资讯 bot 生产，新机器只读接收原始 JSON 与媒体，再用现有四个目录环境变量读取；不为源连接缺失另建生成器。尚缺四路实际源目录、可用且获授权的传输通道、产出时间/写入方式及媒体布局。本机手动入口已保留在 `var/rebang/local-ops/mac-refresh.sh`，固定当前 23:24 快照并传入 Python、PATH、时区和四路目录；仅做 shell 语法与目录检查，未再次运行发布，未创建调度。快照可验证发布链路，不能证明后续供稿或 X 实时读取就绪。方案较早的密钥/登录未就绪描述已由后续实测更新，当前状态以上方记录为准。

### 11/18 无需本人配合的准备与验证

- **本轮范围**：阿欢要求先完成不需要本人配合的部分。继续本地实现、真实只读采集及隔离验证；不据此合并 main、部署、切换旧任务或安装定时任务。
- **TG 真实采集已隔离验证**：使用既有 `box_scrape.py --test-dir <仓库外新目录> --limit 3`。三个来源各 1 次请求，全部 `ok`，FinanceNewsDaily 新增 6 条；隔离副本真实建站成功，原 `tg.db` 的 SHA256 前后相同，没有 Git 数据提交或发布。临时副本已清理，日志和摘要留在 `var/rebang/local-ops/validation-20261118/tg-logs/` 与 `tg-isolation.json`。正式 TG 数据写入仍须等旧写入者停止，并使用满足既有要求的干净 main。
- **公众号六个号本轮均实际抓取成功（00:23）**：先复现 MacTalk 正文读取 `network`，独立开发变现周刊正文约 3.6 MB；原代码吞掉正文错误，随后合并旧缓存并把本轮标 `ok`，会误更新 `last_ok_at`。现在正文请求启用 curl 压缩，正文错误或缺可验证发布时间交回原有失败保留逻辑：保留内容和上次成功时间，标本轮 error/stale。复测五个微信读书来源各取到 1 条、公共来源取到 10 条，缓存合并后共 16 条（MacTalk 2 条，其余保留原条数）。这证明本轮抓取成功，不代表每轮都有新发布文章。证据：`wechat-compressed-summary.json`。故障回归覆盖网络失败及正文无时间两条路径。
- **运行入口已纳入仓库**：`tools/rebang_mac_refresh.sh` 固定传入 Python、PATH、时区和整理根目录，支持未来以 `REBANG_DIGEST_ROOT` 指向同步目录；缺任一输入目录提前退出，实测未启动刷新。旧本机入口转发到仓库脚本。`tools/translate_deepseek.py` 复用已实测批量实现，去掉旧机器专属默认路径、把 usage log 放本机日志目录，仅放行精确模型名 `deepseek-flash`。密钥仍从环境变量读取，未变更存储或创建长期注入；离线验证覆盖真实 pending→HTTP 边界→缓存/usage log、错误保留及密钥不输出。
- **本地完整重建通过（00:25:10）**：使用 Mac 入口 `--no-fetch --no-publish`，ingest/build 全部成功，`fixture:false`，2575 条新闻、984 条博主内容，pending 0；扫描生成 JSON 中 3342 处媒体引用，无缺失。本轮跨日后按既有整理保留窗口收录 518 条，历史 562 条为 11/17 恢复时的数量，不要求跨日保持不变。没有再次发布。
- **回归与 Mac 避坑**：相关既有测试加新增回归合计 **131 passed，8 subtests passed**。首次运行 box_scrape 测试有 1 项因 macOS `/var`→`/private/var` 的路径别名比较失败；测试临时根目录统一 `resolve()` 后通过，未改生产采集逻辑。
- **YouTube 状态更正**：`DECISIONS.md` 11/16 15:49 已记本人确认 13 个频道全部启用，当前配置确有 13 个，缓存共 130 条。下方“名单为空/待确认”为更早历史，不是当前阻塞，无需再次找本人确认。

## 2026-11-16 状态
- **已上线**：https://news.kwinweng.com/ 根路径就是 v11（11/16 00:08 阿欢决定）；`/rebang/` 301 到根；全站 noindex（页面 meta、`X-Robots-Tag`、`robots.txt`）。旧的登录阅读器、`/mail/`、`/archive/` 已下线。`shiguang-reader-update.timer` 已于 00:32 `disable --now`（实际原是每 5 分钟跑，不是每天一次）；灵记 `lingji-news-source` 只读的 `topics.sqlite3` 从此不再更新。发布链路、服务器配置、回退见 `docs/rebang-v1/OPERATIONS.md`。2026-11-16 已按确认删除旧阅读器/旧站回滚备份；线上阅读器库和 unit 文件仍保留，因为灵记还在读这份库。
- 合并记录：PR #40（v13 合入 main）、#41（TG 转发来源名）、#42（搜索索引加载竞态）、#44（public_base 改为根地址）、#45（文档审计）、#46（袋鼠图标）、#47（去掉顶栏袋鼠，日期回到最左边）。标签页、加到主屏、启动图和分享图仍是袋鼠；顶栏只有日期，没有 logo。
- 线上验收（11/16 00:20 左右）：Playwright 390x844 真触摸 76/76（`docs/rebang-v1/evidence/integration-v13/capture.py`）；数据、媒体、脚本 200；深链 `https://news.kwinweng.com/#/item/<id>` 冷启动直达详情，旧 `/rebang/#/item/<id>` 跳转后同样可用。图标改动后复查 75/76，剩下的失败是部分英文新闻尚未翻译，与图标无关。
- 刷新：v11 现在由「X 博主 + 翻译」例程每 2 小时刷新并发布一次（提示词 `/workspace/rebang-v1-briefs/routine-x-translate.md`：写 X dump → `rebang_refresh.sh --no-publish` → DeepSeek Flash 翻译 → `rebang_refresh.sh --no-fetch` 发布；每轮简报在 `/workspace/rebang-v1-briefs/runs/x-translate-*.md`，11/16 01:52 起）。8:30 私聊例程也在跑（`routine-0830.md`，11/16 稿 `runs/push-2026-11-16.sent.txt`）。30 分钟一次的刷新还没加（盒子没有 cron，定时都靠 bot 例程）。旧站采集 `tools/box_scrape.sh` 仍由工头「热榜抓取发布」例程按 :07/:37 跑，继续写 `tg.db`、发布 gh-pages；它发布时会顺带把当时的 `site-v11/` 一起发出去，但不会重建 v11。
- **第一期收尾已上线（PR #53，squash `dd7824944`；11/16 13:50 建站发布，14:03 线上 built_at 13:50:40）**：博主页 X 视频/GIF 站内播放（查看器图视频混排、离开即暂停、播放失败给原帖链接；页面 referrer 改 same-origin，否则 video.twimg.com 回 403）；底栏切换卡顿修掉（4 倍降速长任务 335ms→61ms，`docs/rebang-v1/evidence/perf-0116/`）；设计令牌 + 全站 Lucide 图标 + 动效令牌与「减少动态效果」（`docs/rebang-v1/DESIGN-SYSTEM.md`）；修了刷新按钮倒转、查看器底栏按钮触摸误关、滚动时误弹长按菜单、正文译文没好时看不到原文、搜索索引里已清掉的本地图 404。线上核实（14:07）：`capture.py` 84/84、真数据视频检查 21/21、noindex（meta + X-Robots-Tag + robots.txt）仍在。没测：真 iPhone Safari、画中画/横屏。
- **第二期已上线（PR #55–#59，11/16 15:21 建站发布，15:41 线上 built_at 15:21:42）**：即刻 9/9 走公共 RSSHub（免登录，4 实例轮换，90 条）；TG 评论楼（每条最多 30 条公开评论、楼中楼、10 条以上折叠；线上 133 条带评论、623 条评论、70 条楼中楼，旧缓存按 6 小时窗口陆续补成新格式）；YouTube 管道与播放器已上（名单空，显示「频道名单待确认」，候选 `docs/rebang-v1/youtube-candidates.md`）；5 个公众号微信读书管道已备好，站上写「等扫码」；微博免登录方式全不通。线上 e2e `capture.py --phase2` 92/94，两条失败是新英文条目等翻译例程（`p2live-result.json`）。
- **第三期整理（11/16 16:00 前后）**：远程只留 `main`、`gh-pages`（以及进行中的 `grok/p3-*` 功能分支）；删了已合并的 `feat/rebang-ui-fulltext`、`feat/rebang-partial-translate`。盒子删了没合并的旧分支 `agent/hot-daily-publish`（11/07 旧站日报发布链，已被 main 取代）和 5 个 `backup/*` 旧 `tg.db` 快照提交，删前打包到 `/workspace/_archive/rebang-20261116/git/unmerged-local-branches.bundle`；盒子旧文件归档清单见 `/workspace/_archive/rebang-20261116/README.md`。旧站文档 `ARCHITECTURE.md`、`DESIGN.md`、`INGEST.md`、`PRIVATE_LOGIN.md` 和 `docs/LEGACY-SITE.md` 移到 `docs/legacy/`。
- **微博 6 个博主已上线（PR #69，squash `e942ae97d`；11/16 19:26 建站发布，19:42 线上 built_at 19:26:16）**：用 weibo.com 桌面版 ajax + 副号 Cookie（`~/.config/rebang/weibo-cookie.txt`，0600，不进仓库/日志），不用 weibo-crawler（m.weibo.cn 不认这份 Cookie）。线上每人 10 条。sinaimg 对浏览器只认 weibo.com Referer，所以图、封面、头像在抓取时存成本地副本 `var/rebang/media/weibo/`（约 240 张 / 38MB）；视频站内播不了，查看器给「打开原帖」。Cookie 失效（ok≠1/跳登录）→ 微博标 login_expired、保留上次内容、日志打 `weibo cookie expired`；换 Cookie 文件即可恢复。线上 `docs/rebang-v1/evidence/weibo/capture.py` 10/10。细节见 `docs/rebang-v1/MODULES.md` 微博条。
- **注意**：11/16 19:00 前后的建站数据里，公众号 6 个号有 5 个是 `login_expired`（微信读书会话失效），要阿欢重新扫码。

## 2026-11-15 拾光热榜 v11 开发与上线（原 HANDOFF 内容）

现产品名为「拾光资讯」；本节保留历史名称和上线记录。

- 集成分支 `feat/rebang-v1`（基于 origin/main 8b5c6735e）先写数据契约 `rebang/contract/`，再依次合入 6 个功能分支（顺序做的，不是并行）：sources-ingest 4d7969412、hotsearch 4716f832b、bloggers 730dd665f、frontend-v11 25ab6022e、history-favorites-search 04b3652f3、push-0830 cd1110730。各模块现状见 `docs/rebang-v1/MODULES.md`。
- 21:35 实抓：资讯 2584 条；热搜百度 51 / 知乎 30 / B 站 50；博主 151 条（英文 68/68 已译）。
- 21:26 改版 5 处（历史→热搜、博主页 Grok bot、查看更多、官方图标、英文全部机器翻译）；22:10–22:11 v13 七处（含顶栏日期只显示一次、居左）。设计检查点预览 daily-site-mocks `/rebang-v12/`、`/rebang-v13/`（一次性快照）。
- 测试基线：未改 origin/main 时 pytest 228 过 / 1 失败（`test_news_modules_browser` dark 子用例），node 13/13；v13 时 pytest 374 过 + 同一个基线失败，node 32/32，390x844 真触摸 76/76。
- 23:13 起合并 PR #40/#41/#42，v11 先以 `/rebang/` 上线；11/16 00:08 改为根路径（PR #44），旧阅读器下线。
- `f2e9c04` 不在 GitHub 远端（只在交接方本地），以 main 上的 `shiguang/ingest/telegram.py` 为复用基线。

## 2026-11-07 news 公开产物接收端

- 原私有同步方案由负责人明确决定替换：默认无凭据下载 public gh-pages，允许移除 mail 和 private-only 历史；保持 reader、认证和 nginx 配置不变。每 20 分钟下载、独立 staging 校验、Linux renameat2 原子交换，保留一版 previous。
- 守卫：public scope/schema 3、归档 SHA/HTML 一致、整树邮件标记禁止、非空 live、内容日不回退且近期、文件数至少 max(100, 当前排除 mail 文件数的一半)。旧 private UID/日期逐个保留已不符合迁移目标，不再要求。
- 实踩：Linux 会保留 `.news-sync.lock` 供后续进程锁同一 inode；临时清理断言应只检查 staging 目录，不能把持久锁文件判为泄漏或在运行中删除锁。
- 验证：Linux 同步 23/23（含权限、原子 inode 交换和 previous）；全套 228 项为 205 通过、21 可选浏览器跳过、2 个已在 origin/main 重现的 Steam RDF 失败。Node 13/13；Bash 语法与 diff 检查通过。
- 真实默认下载 dry-run 通过：现站 3162 文件，公开候选 2143，最低 1546；内容日 11-03→11-07。完整包约 76.3 MB，下载/校验约 32.4 秒，峰值 RSS 约 139 MiB；每轮完整下载产生网络和磁盘开销，不增加采集或模型调用。
- 迁移前静态 tar.gz 与 SQLite `.backup` 已独立保存于受限备份目录，数据库 quick_check=ok。临时 reader 副本导入 public 成功：new_versions=1100、rejected=0；11-04..11-07 均有记录、最新日 11-07。安装及 Box 最终验收待本 PR 的后续交接更新。

## 2026-11-07 公开数据源切换：白名单与邮件退役

- 负责人明确批准 `news.kwinweng.com` 及其 iOS reader 只接收 public gh-pages。8 个已配置 Telegram 频道加入 `ALLOWED`；`mail` 从活动配置移除，另设 `PRIVATE_RETIRED` 永久阻断，不能放进只保留公开历史的 `RETIRED`。
- 复用输出目录时主动删除退役邮件目录；归档按完整保留库重建，来源契约变化使历史页失效重建，新增频道媒体沿现有可见频道复制流程发布。隔离回归验证全部 8 频道的多个过去日期和图片，以及配置移除后邮件目录/标记仍被拒绝。
- 真实公开离线构建成功并通过 `verify_public`：8 频道共 482 条，逐来源归档数量与已提交库一致。此 Mac checkout 无 media 缓存，不能据本地构建宣称真实图片可用；需核验 Box gh-pages。
- 验证：Node 13/13；Linux 全套 205 项中 182 通过、21 项因无 Playwright 跳过、2 项 Steam RDF 失败，已在未修改 origin/main 独立重现（解析结果为空）。本次相关归档/隐私/feeds/原子构建回归通过。Mac 全套另有 Linux renameat2 缺失、临时目录实路径和既有浏览器/索引快照环境失败，不为本任务更改这些无关实现。
- 生产备份已创建并验证 SQLite quick_check=ok；生产安装与 Box 发布验收将在同步脚本 PR 记录。不在公开交接中记录服务器地址或私人内容。

## 2026-10-25 恢复 pelosi3（保持已停更的 liangjiahepost 停用）

- 恢复停用来源时，必须同时从 `shiguang/site/history.py` 的 `RETIRED` 移除，避免与 `sources.json` 双重注册。`pelosi3` 恢复顺序 56；`liangjiahepost`（10/22 停更）与 `titan_pain` 继续停用并保留在 `RETIRED`。
- 回归在公开和私有模式中写入旧消息，验证归档 JSON 无重复、归档 HTML 与活跃来源页正常呈现；停用来源仍只出现在归档。
- `python3 -m pytest -q` 通过：196 passed、58 subtests passed。指定 `NO_FETCH=1` 的公开、私有离线构建均成功，输出分别为 `/tmp/hot-tg10-public`、`/tmp/hot-tg10-private`，耗时约 16.4 秒、18.4 秒。
- 两模式真实构建均保留 `pelosi3` 的 120 条、`liangjiahepost` 的 32 条归档消息，每来源仅注册一次。私有构建出现 Pillow 透明调色板转 RGBA 警告，退出码仍为 0。
- 未改调度、未新增处理流程；未读取密钥文件，未发布、合并或部署。

## 2026-10-24 PR #31 有图探索条目修补

- 探索分类标签必须放在 `.tx` 内并独占一行；有图行使用正文、图片两列，不能沿用分类占左列的三列网格。无图及坏图仍保持全文宽度。
- `explore_messages()` 输出标题时执行 `strip()`，列表渲染再执行 `trim()`，兼容已有缓存数据；保留标题内部空格。
- 浏览器回归使用正常加载的图片，覆盖 320、393、1280 像素宽度、分类筛选、标签与正文位置、图片右对齐及标题首尾空白。截图位于 `/tmp/rebang-explore-image-desktop.png` 和 `/tmp/rebang-explore-image-mobile.png`。
- 验证：`python3 -m pytest -q`（196 passed、58 subtests）、`node --test tests/*.test.js`（9 passed）、`NO_FETCH=1 python3 pipeline.py` 均通过。
- Python 首轮在 `test_dirty_checkout_refused_at_sync_and_persist` 的 Git 索引字节快照比较中偶发失败；未改代码完整重跑通过。未扩大本次修补范围。
- 未读取密钥文件，未 push、合并、部署或操作 gh-pages。

## 2026-10-24 PR #31 第二轮修复

- 无图列表标题跨满整行，不保留图片占位；图片加载失败移除后同样恢复整行宽度。
- 回顾页移除顶部摘要卡片，保留日期导航和事件列表。
- 浏览器回归覆盖无图、坏图及 320、393、1280 像素宽度，并断言回顾页无摘要卡片。
- 验证：`python3 -m pytest -q`（195 passed、58 subtests）、`node --test tests/*.test.js`（9 passed）、`NO_FETCH=1 python3 pipeline.py` 均通过。
- 未读取密钥文件，未 push、合并、部署或操作 gh-pages。

## 2026-10-24 PR #31 第一轮修复

- 开始时没有 HANDOFF.md；`web/modules.js` 有中断遗留改动，已在其基础上继续。
- 探索真实内容保存在 `tg.db` 的 `trial_item`，不在收件箱 issues 中。构建只读现有表；缺库或缺表返回空，不创建表。分类名称与来源名称取公开 `trial-sources.json`，好看保持空，不新增来源。
- 不存在条目不能逐个请求所有历史日期。历史索引新增 ID 到日期映射，直接查对应归档；未知 ID 显示缺失状态。
- CSS 存在旧原型规则和末尾正式布局覆盖。实时行、筛选文字、品牌栏、字重需检查最终计算样式，不能只修改前面的规则。
- 未读取密钥文件；未合并 main、部署、操作 gh-pages 或 push。
- 验证：`python3 -m pytest -q`（194 passed、58 subtests）、Node 测试（13 passed）、`NO_FETCH=1 python3 pipeline.py` 通过。真实 iOS 安全区仍待实机确认。
