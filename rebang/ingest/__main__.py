import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

from rebang.contract import validate_items_envelope
from rebang.ingest.core import BEIJING, DEFAULT_CACHE, collect, write_envelope


def main(argv=None):
    p = argparse.ArgumentParser(prog='python3 -m rebang.ingest', description='资讯来源 → var/rebang/in/ingest.json')
    p.add_argument('--db', default='tg.db', help='tg.db 路径（只读打开）')
    p.add_argument('--media-root', default=None, help='tg.db 里 media/ 相对路径的根目录，默认 tg.db 所在目录')
    p.add_argument('--out', default='var/rebang/in/ingest.json')
    p.add_argument('--cache', default=str(DEFAULT_CACHE))
    p.add_argument('--days', type=int, default=14, help='只收最近 N 天（北京时间）')
    g = p.add_mutually_exclusive_group()
    g.add_argument('--no-fetch', action='store_true', help='不联网，订阅/Trending 读缓存')
    g.add_argument('--live', action='store_true', help='联网只读抓 7 个订阅/页面（默认即联网，此开关用于冒烟并打印条数）')
    p.add_argument('--now', default=None, help='ISO 时间，测试用')
    p.add_argument('--tgmeta', default='var/rebang/cache/tgmeta.json',
                   help='rebang.tgmeta 缓存（频道自己的话/引用/转发/表情/浏览/公开评论）；文件不在就跳过')
    p.add_argument('--no-tgmeta', action='store_true')
    a = p.parse_args(argv)
    now = datetime.fromisoformat(a.now) if a.now else datetime.now(BEIJING)
    envelope = collect(now, fetch=not a.no_fetch, db=a.db, media_root=a.media_root, cache=a.cache, days=a.days,
                       tgmeta=None if a.no_tgmeta or not Path(a.tgmeta).is_file() else a.tgmeta)
    errors = validate_items_envelope(envelope)
    if errors:
        print('契约校验失败：', *errors[:20], sep='\n  ', file=sys.stderr)
        return 1
    write_envelope(envelope, Path(a.out))
    counts = {}
    for item in envelope['items']:
        counts[item['channel']] = counts.get(item['channel'], 0) + 1
    print(json.dumps({'out': a.out, 'items': len(envelope['items']), 'by_channel': counts,
                      'highlights': sum(1 for i in envelope['items'] if i.get('highlight')),
                      'sources': envelope['sources']}, ensure_ascii=False, indent=1))
    return 0


if __name__ == '__main__':
    sys.exit(main())
