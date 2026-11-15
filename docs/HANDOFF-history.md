# 交接记录

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
