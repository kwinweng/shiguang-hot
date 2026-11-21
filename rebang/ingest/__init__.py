"""拾光资讯 v1 资讯来源接入：channels.json 里全部资讯来源 → rebang.items/1 条目（整源一频道）。

- TG 18 个：只读 tg.db（现有 shiguang/ingest/telegram.py 采集写入），图片用 tg.db 旁 media/ 的 14 天缓存。
- 官方订阅 6 个：shiguang.ingest.web.parse 解析；GitHub Trending：解析公开页。抓取结果缓存在
  var/rebang/cache/，--no-fetch 时读缓存（缓存没有就如实标 not_fetched，不编）。
- 现有成品 4 个（x / world / github / hot-daily）：shiguang.ingest.feeds.load_issues(local=True)，
  读盒子上的原始投递目录（/workspace/x-digest、/workspace/world-brief、/workspace/feeds-inbox/<id>）。
- 今日重点按 channels.json.highlights.rule 打标或归频道。
"""
from .core import collect, write_envelope  # noqa: F401

__all__ = ['collect', 'write_envelope']
