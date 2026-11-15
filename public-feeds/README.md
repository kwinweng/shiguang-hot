此目录仅存放 sources.json 中 visibility=public 的规范化 feed.json 和压缩 webp 图片，保留最近 14 天。
由 /workspace/tg-local/publish_public.py 维护。最近一次数据提交是 `62a26398d`（2026-10-23 21:20 北京时间）；当天 `sync.sh` 改为 `publish_public.py --no-push`（备份 `sync.sh.bak-20261023-pause-push`），之后只准备文件、不再提交推送。无数据时不生成栏目；禁止放入 private 内容。

旧站公开构建（tools/box_scrape.sh，每小时 :07/:37）从这里读取期刊；推送本目录不会触发构建，下一轮采集时生效。GitHub Actions 已不再构建或部署。
发布前仍执行公开内容检查；成功构建的输入与时间记录在站点 build-info.json。运行方式见 ../docs/BOX-SCRAPER-CUTOVER.md。
