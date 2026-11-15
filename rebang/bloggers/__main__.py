"""python3 -m rebang.bloggers --out var/rebang/in/bloggers.json [--platform blog,x] [--weibo-cookie-file PATH]

默认联网（只读、低频）抓博客与 Wechat2RSS；X 读 --x-dump 目录（公开 X 读取工具的原始响应）。
登录类平台没配置时输出 not_configured，不报错、不编数据。
"""
import argparse
import json
import os
import sys
from collections import Counter
from pathlib import Path

from rebang.contract.schema import validate_items_envelope
from rebang.translate import Translator

from .run import ALL_PLATFORMS, Options, load_previous, run, write_atomic

ROOT = Path(__file__).resolve().parents[2]


def main(argv=None):
    ap = argparse.ArgumentParser(prog='python3 -m rebang.bloggers')
    ap.add_argument('--out', default=str(ROOT / 'var/rebang/in/bloggers.json'))
    ap.add_argument('--platform', default=','.join(ALL_PLATFORMS), help='逗号分隔：' + ','.join(ALL_PLATFORMS))
    ap.add_argument('--x-dump', default=os.environ.get('REBANG_X_DUMP', str(ROOT / 'var/rebang/x-dump')),
                    help='X 原始响应目录（取最新子目录）或单个文件')
    ap.add_argument('--jike-rsshub', default=os.environ.get('REBANG_JIKE_RSSHUB'), help='自建 RSSHub 根地址；不配 → not_configured')
    ap.add_argument('--weibo-cookie-file', default=None, help='仓库外 Cookie 文件路径（只检查存在，不读取）')
    ap.add_argument('--weibo-output', default=None, help='weibo-crawler 输出目录')
    ap.add_argument('--limit', type=int, default=10, help='每个账号最多条数')
    ap.add_argument('--pause', type=float, default=1.0, help='同平台账号之间的间隔秒数')
    ap.add_argument('--translate-engine', default=None, help='none|cache|openai-compatible（默认读 REBANG_TRANSLATE_ENGINE，否则 cache）')
    args = ap.parse_args(argv)
    platforms = tuple(p.strip() for p in args.platform.split(',') if p.strip())
    unknown = set(platforms) - set(ALL_PLATFORMS)
    if unknown:
        ap.error('未知平台：' + ','.join(sorted(unknown)))
    opts = Options(x_dump=args.x_dump, jike_rsshub=args.jike_rsshub, weibo_cookie_file=args.weibo_cookie_file,
                   weibo_output=args.weibo_output, limit=args.limit, pause=args.pause,
                   translator=Translator(engine=args.translate_engine))
    envelope = run(platforms, previous=load_previous(args.out), opts=opts)
    errors = validate_items_envelope(envelope)
    if errors:
        print(json.dumps({'ok': False, 'errors': errors[:20]}, ensure_ascii=False, indent=1))
        return 2
    write_atomic(args.out, envelope)
    count = Counter(i['blogger']['platform'] for i in envelope['items'])
    translated = sum(1 for i in envelope['items'] if i.get('translated'))
    foreign = sum(1 for i in envelope['items'] if not i['lang'].startswith('zh'))
    print(json.dumps({
        'ok': True, 'out': args.out, 'items': len(envelope['items']),
        'translated': f'{translated}/{foreign}',
        'platforms': [{'id': p['id'], 'status': p['status'], 'items': count.get(p['id'], 0),
                       'accounts': {a['handle']: a['status'] + (f"({a['error']})" if a.get('error') else '') for a in p['accounts']}}
                      for p in envelope['platforms']],
    }, ensure_ascii=False, indent=1))
    return 0


if __name__ == '__main__':
    sys.exit(main())
