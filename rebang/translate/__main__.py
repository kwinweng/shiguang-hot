"""译文缓存维护：
  python3 -m rebang.translate pending [--cache PATH]              # 打印待译原文（JSON）
  python3 -m rebang.translate fill FILE --engine NAME [--cache PATH]
FILE 为 JSON 数组 [{"src": 原文, "src_lang": "en", "zh": 译文}]，或 {key: 译文}（key 来自 pending）。
engine 写实际做翻译的东西（例如 grok-bot）。原文必须与 pending 里逐字一致才会入缓存。
"""
import argparse
import json
import sys

from . import Cache, text_key


def main(argv=None):
    ap = argparse.ArgumentParser(prog='python3 -m rebang.translate')
    ap.add_argument('cmd', choices=['pending', 'fill'])
    ap.add_argument('file', nargs='?')
    ap.add_argument('--engine')
    ap.add_argument('--cache')
    args = ap.parse_args(argv)
    cache = Cache(args.cache)
    if args.cmd == 'pending':
        json.dump([{'key': k, **v} for k, v in cache.pending.items()], sys.stdout, ensure_ascii=False, indent=1)
        print()
        return 0
    if not args.file or not args.engine:
        ap.error('fill 需要 FILE 与 --engine')
    data = json.load(open(args.file, encoding='utf-8'))
    added = skipped = 0
    if isinstance(data, dict):
        rows = []
        for key, zh in data.items():
            src = cache.pending.get(key)
            if src:
                rows.append({'src': src['src'], 'src_lang': src['src_lang'], 'zh': zh})
            else:
                skipped += 1
        data = rows
    for row in data:
        src, zh, lang = row.get('src'), row.get('zh'), row.get('src_lang', 'en')
        if isinstance(src, str) and isinstance(zh, str) and zh.strip() and text_key(src, lang) in cache.pending:
            cache.put(src, lang, zh.strip(), args.engine)
            added += 1
        else:
            skipped += 1
    cache.save()
    print(json.dumps({'added': added, 'skipped': skipped, 'pending_left': len(cache.pending)}))
    return 0


if __name__ == '__main__':
    sys.exit(main())
