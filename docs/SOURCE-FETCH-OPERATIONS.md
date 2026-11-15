# 逐来源小时采集：运行说明

旧站采集器（`shiguang/ingest/`，由 `tools/box_scrape.sh` 每小时 :07/:37 调用）的配额、退避与 blocked 规则。依据 [PR #17 Spec r2 @ 32708dc](https://github.com/kwinweng/shiguang-hot/blob/32708dc900ae01bec72c78eb059c9a613fc037f2/docs/SPEC-hourly-source-dedupe-r1.md)（需求 [#16](https://github.com/kwinweng/shiguang-hot/issues/16)），2026-10-21 阿欢批准。测试：`tests/test_source_scheduler.py`（临时库、假 HTTP、可控时钟，不联网）。

## 实现边界

- 北京时间自然小时按**每源实际领取批次时间**计算，绝对时间以 UTC 保存。10:59 与 11:00 可以分别有一轮；11:07:30 与 12:07:10 都可领取。一次批次包含原有上限内的翻页和图片，不等于一个 HTTP 请求。
- Telegram 同一频道与 feed 完全相同的端点归为同一计划。只统一 scheme/host 大小写及无意义 fragment；保留路径、查询参数和顺序，不猜测相似标题或重定向别名。重复配置选稳定 ID 排序后的首项承载新条目，原条目 ID 和已有收藏不迁移。
- 本机先取得 `tg.db.fetch.lock`，再迁移/写库。忙碌时只读已有内容；SQLite 唯一 `(source_id,hour_key)` 约束与预先提交的领取记录保证同库额度。中断后的同小时批次不重开，下一次取得锁时记 interrupted。
- 新表 `source_fetch_meta`、`source_fetch_state`、`source_fetch_batch`、`fetch_resource_state` 全在原 `tg.db`。原有持久化路径能一并保存；没有改 workflow、生产配置或持久化脚本。版本或表结构损坏即停止，不静默重建。
- `NO_FETCH=1` 不取采集锁、不建表、不迁移、不创建 media 目录，不请求网络；新表不存在时仍按旧数据构建。
- 网络/内容失败按 1/2/4/8/12/24 小时退避，上限24小时；冷却从批次结束起算。完整成功才清零失败次数、更新成功时间；一次失败也占本小时额度。429 遵守有效 Retry-After，且不早于下一自然小时。
- 401/403、已识别的验证码或登录页面标 blocked，停止该入口，不自动恢复。其他源继续。部分有效条目保留；源级失败不等于隐私检查或数据库持久化失败，后两者继续阻断发布。
- feed 条件请求仅在对应解析结果的版本/摘要有效时使用。200 完整解析后，将条目与验证器一起提交；合法空 feed 同样有标记。304 不清空条目，不覆盖独立的图片失败；无有效物化记录却收到304，记录错误，下一合法批次才无条件请求。
- Telegram 保留原翻页、gap 和图片上限；不启用 TG 条件请求，避免入口304掩盖缺口。每批同资源最多一次网络尝试；图片复用有效文件、临时文件原子替换。调度路径图片串行，低于原6线程并发上限。
- 多图条目先登记全部图片工作，再开始下载；第一张 blocked/429 不丢后续待补图片。补图按原图片序号回到正确位置；成功转换后只复用缓存文件并释放原图响应内存，不在批次内累积所有原始图片正文。
- 不保存原始 HTTP 响应正文。继续使用原 msg/entry 的已解析内容；新资源元数据只保存验证器、物化摘要和必要图片引用。图片引用含公开原图 URL、条目关联和原发布时间，支持图片失败或媒体缓存丢失后独立补图，按原14天内容保留口径淘汰，不是第二份原始响应库。
- 批次完成明细保留7天；running/interrupted/blocked 等待核对记录保留。源状态、有效 feed 验证器和必要图片引用不因批次清理被删。现有条目及 gap 不因额度清理删除。
- 已无图片引用、超过14天且无需验证器的图片/TG页资源元数据会清理；保留 feed 验证器、条目、源额度及独立 gap。

仅承诺同一持久数据库及成功保存状态后的串行连续运行。旧数据库副本、状态丢失、跨机器独立数据库，以及 runner 在远端保存之前崩溃，不具备严格全局只抓一次保证。完整丢失的新状态无法与首次迁移可靠区分；必须恢复已知数据库并人工核对，不能靠删状态“修复”额度。

## blocked：谁看、怎么看

- 2026-10-21 阿欢确认：**总控负责 blocked 检查；解除 blocked、恢复采集须阿欢本人明确批准**。
- 采集器向构建 stderr 输出 `fetch_status {JSON}`：正常轮次含 source、attempt_id、hour_key、result、error_code、last_checked、last_success、next_eligible_at、requests、cache_hits、new；跳过轮次含 skip_reason，blocked 源持续输出 `source_status=blocked`。时间为 UTC。
- 检查方法：打开 box 采集日志筛 `fetch_status`，看 `result=blocked` 和 `result=skip` 且 `source_status=blocked`，另查 Pages 发布失败；不能只看退出码。日志不可读或没有状态行时报告「未取得源级健康证据」，不能记为健康。
- 采集器只输出状态，**没有内建通知**。通知链路（复用巡检与消息通道、在 #16 记录 `[总控 状态]`）当时等「拾光热榜流程优化」会话回传验收证据。issue [#16](https://github.com/kwinweng/shiguang-hot/issues/16) 仍开放，2026-10-21 的阶段记录是 `awaiting_notification_acceptance`，正文写「尚未验收通过」；之后没有新评论或关闭记录，**不能当成已验收**。采集日志在 `/workspace/shiguang-logs/`。

## 人工恢复与回滚

1. 总控核对原已准入公开入口确实恢复，无需登录/cookie/验证码绕过；保留可核查的时间与证据。不能通过换域名、代理、账号或新来源规避 blocked。
2. 总控将来源、原因、恢复证据与拟维护操作交阿欢本人另行明确批准。未获批准不解除 blocked、不恢复采集；Spec/开发批准、CI通过、机器评论都不是恢复批准。
3. 在对应数据库采集锁下先备份完整 `tg.db`，只更新获批来源的 blocked 状态/错误及下一可尝试时间（不早于维护时刻后的下一个北京时间自然小时）。保留 last_attempt、last_success、批次、内容及 gap；不删除额度行、不复制/重建状态。具体维护命令在获批时针对实际版本准备，仓库里没有解除命令或自动恢复按钮。
4. 等下一次获准正常运行；检查该源成功/部分失败/再次blocked，并在原记录补结论。

代码回滚时保留新数据库及内容，旧代码会忽略新表，同时也会忽略新额度规则。因此需要另行批准的维护安排，在恢复正常采集前核对影响；不通过回滚数据库恢复旧额度。原 box 试运行状态与这些产品采集表无关，本轮未读取或迁移。

## 试跑来源（trial，2026-10-22 起）

13 个试跑源只在 `trial-sources.json` 注册，在同一采集入口、同一锁和调度表里运行，身份前缀 `trial:`，与正式来源配额隔离，只写 `trial_item` 和状态表，不传给公开期刊发布器（旧站「探索」读它）。不自动切换 RSSHub、不下载图片、不请求 Steam JSON、豆瓣 JSON 或 Apple 文章页。网页无有效条目视为 invalid_content 并退避；401/403 及登录/验证码同样 blocked。统计：`python3 tools/trial_report.py --days 7`（只读，输出到终端和被 git 忽略的 `reports/trial/`）。

离线构建检查：

```sh
NO_FETCH=1 SITE_OUT=/tmp/shiguang-public python3 pipeline.py
SITE_MODE=private NO_FETCH=1 SITE_OUT=/tmp/shiguang-private python3 pipeline.py
```
