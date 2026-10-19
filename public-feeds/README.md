此目录仅存放 sources.json 中 visibility=public 的规范化 feed.json 和压缩 webp 图片，保留最近 14 天。
由 /workspace/tg-local/publish_public.py 维护。无数据时不生成栏目；禁止放入 private 内容。

发布方式：推送到 main 的本目录变更会触发 hourly 工作流，以 NO_FETCH=1 从已存储数据全量构建并发布公开站，不再等待下一次定时采集。完整采集仍由 schedule 或 workflow_dispatch 触发；本目录推送不会同时刷新 TG 数据。

发布前仍执行公开内容检查。成功构建的输入与时间记录在站点 build-info.json，具体运行与外部定时接入见 ../docs/SCHEDULE-OPERATIONS.md。
