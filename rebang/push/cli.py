"""命令行：只把稿子打到 stdout，可选写入 --output。从不发送。"""
import argparse
import sys
from pathlib import Path

from .load import load_blogger_platforms, load_meta, load_published_items
from .render import render_brief
from .select import pick_highlights
from .timeutil import parse_now


def _base_url(args, site_dir):
    if args.base_url:
        return args.base_url
    meta = load_meta(site_dir)
    return meta.get('public_base') or meta.get('base_url') or ''


def build_parser():
    parser = argparse.ArgumentParser(description='生成 8:30 今日重点私聊稿（只生成，不发送、不建定时任务）')
    parser.add_argument('--site', default='site-v11', help='已上站目录，默认 site-v11')
    parser.add_argument('--now', default=None, help='带时区的 ISO 时间；缺省为当前北京时间')
    parser.add_argument('--dry-run', action='store_true', help='把稿子打印到 stdout（不发送）')
    parser.add_argument('--output', type=Path, help='把同一份稿子写入文件')
    parser.add_argument('--archive', type=Path, default=None, help='归档目录，默认 <repo>/var/rebang/archive')
    parser.add_argument('--base-url', default=None, help='站点链接前缀；缺省读 data/meta.json 的 public_base')
    return parser


def generate(site_dir, now, archive_dir=None, base_url=None):
    if base_url is None:
        meta = load_meta(site_dir)
        base_url = meta.get('public_base') or meta.get('base_url') or ''
    items = load_published_items(site_dir, now=now, archive_dir=archive_dir)
    selected = pick_highlights(items, now=now)
    platforms = load_blogger_platforms(site_dir)
    return render_brief(selected, now=now, base_url=base_url, platforms=platforms)


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        now = parse_now(args.now)
    except ValueError as error:
        print(error, file=sys.stderr)
        return 2
    text = generate(args.site, now, archive_dir=args.archive, base_url=_base_url(args, args.site))
    # 本模块没有发送能力；有无 --dry-run 都只输出。
    sys.stdout.write(text)
    if not text.endswith('\n'):
        sys.stdout.write('\n')
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text if text.endswith('\n') else text + '\n', encoding='utf-8')
    return 0
