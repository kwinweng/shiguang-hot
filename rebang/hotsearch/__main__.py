"""python3 -m rebang.hotsearch --out var/rebang/in/hotsearch.json [--fixtures DIR] [--live] [--archive DIR | --no-archive]

真实抓取默认同时按北京日期归档到 var/rebang/hotsearch-archive/（每天留最后一次可用的）；--fixtures 默认不归档。
"""
import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

from . import archive
from .collect import BEIJING, collect
from .http import FixtureHttp, LiveHttp


def main(argv=None):
    parser = argparse.ArgumentParser(description='采集百度 / 知乎 / B 站热搜，输出 rebang.hotsearch/1')
    parser.add_argument('--out', required=True, help='输出 JSON 路径')
    parser.add_argument('--fixtures', help='离线样本目录（<id>.json），不联网')
    parser.add_argument('--live', action='store_true', help='真实请求三家并在 stderr 打印条数与状态')
    parser.add_argument('--archive', help='热搜按日归档目录（真实抓取默认 var/rebang/hotsearch-archive）')
    parser.add_argument('--no-archive', action='store_true', help='不归档')
    args = parser.parse_args(argv)
    if args.live and args.fixtures:
        parser.error('--live 与 --fixtures 不能同时使用')
    if args.fixtures:
        http = FixtureHttp(args.fixtures)
    else:
        http = LiveHttp()
    now = datetime.now(BEIJING)
    payload = collect(now, http=http)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    _print_summary(payload, live=args.live or not args.fixtures)
    archive_dir = None if args.no_archive else (args.archive or (None if args.fixtures else archive.DEFAULT_DIR))
    if archive_dir:
        day = archive.save_snapshot(payload, archive_dir)
        sys.stderr.write(f'archive {day or "skipped"} -> {archive_dir}\n')
    return 0


def _print_summary(payload, live=False):
    prefix = 'live' if live else 'fixtures'
    lines = [f"{prefix} generated_at={payload.get('generated_at')}"]
    for provider in payload.get('providers') or []:
        error = provider.get('error') or ''
        lines.append(
            f"{provider.get('id')}\t{provider.get('status')}\t"
            f"items={len(provider.get('items') or [])}\t"
            f"fetched_at={provider.get('fetched_at')}\t{error}".rstrip()
        )
    sys.stderr.write('\n'.join(lines) + '\n')


if __name__ == '__main__':
    sys.exit(main())
