"""python3 -m rebang.tgmeta [--store var/rebang/cache/tgmeta.json] [--channels a,b] [--fixtures DIR]

抓 channels.json 里所有 TG 频道的公开页面（只读，不登录），更新表情回应/浏览数/引用/转发/公开评论缓存。
"""
import argparse
import json
import sys
from pathlib import Path

from rebang.contract import load_channels

from . import DEFAULT_STORE, load_store, refresh, save_store


def tg_handles():
    out = []
    for c in load_channels()['channels']:
        for s in c.get('sources', []):
            if s.get('type') == 'telegram':
                out.append(s.get('handle') or s['id'])
    return out


def main(argv=None):
    p = argparse.ArgumentParser(prog='python3 -m rebang.tgmeta')
    p.add_argument('--store', default=str(DEFAULT_STORE))
    p.add_argument('--channels', default='')
    p.add_argument('--fixtures', help='离线：目录下 <频道>.html 当作 t.me/s 第一页，不联网')
    a = p.parse_args(argv)
    chans = [c for c in a.channels.split(',') if c] or tg_handles()
    get = None
    if a.fixtures:
        root = Path(a.fixtures)

        def get(url):   # noqa: E306
            name = url.split('/s/')[-1].split('?')[0] if '/s/' in url else '__none__'
            path = root / f'{name}.html'
            if '?before=' in url or not path.is_file():
                return '<html></html>'
            return path.read_text(encoding='utf-8')
    store = load_store(a.store)
    store, stats = refresh(chans, store=store, **({'get': get, 'sleep': 0} if get else {}), log=lambda s: print(s, file=sys.stderr))
    save_store(store, a.store)
    print(json.dumps({'store': a.store, 'channels': len(chans), **stats}, ensure_ascii=False, indent=1))
    return 0


if __name__ == '__main__':
    sys.exit(main())
