#!/usr/bin/env python3
"""Generate mock daily reviews offline. Schedule: 00:30 Asia/Shanghai, previous day."""
import argparse
import os
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from shiguang.config import ROOT, config
from shiguang.model import BEIJING, home_candidates
from shiguang.site.pages import Content
from shiguang.site.news_data import daily_documents, messages, write_json


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--backfill-from', type=lambda value: datetime.strptime(value, '%Y-%m-%d').date().isoformat())
    parser.add_argument('--output', type=Path, default=ROOT / 'history')
    parser.add_argument('--sample', action='store_true')
    args = parser.parse_args(argv)
    os.environ['NO_FETCH'] = '1'
    os.environ['SITE_MODE'] = 'public'
    os.environ.pop('MAIL_DIGEST', None)
    if args.sample:
        os.environ['SAMPLE_DATA'] = '1'
    from pipeline import collect
    now = datetime.now(BEIJING)
    cfg = config()
    rows, entries = collect(cfg, now)
    with tempfile.TemporaryDirectory() as directory:
        content = Content(cfg, False, rows, [], entries, now, Path(directory))
        items = list(content.stream)
        for sid, issues in content.issues.items():
            for issue in issues:
                source = content.sources[sid]
                items.extend(content.tagged(home_candidates(issue, source), source))
        floor = args.backfill_from or (now.date() - timedelta(days=1)).isoformat()
        docs = daily_documents(messages(items, content.sources), now, floor)
        for day, document in docs.items():
            write_json(args.output / f'{day}.json', document)
    print(f'Generated {len(docs)} mock days in {args.output}; 真实 AI 总结未验证，等新 key')


if __name__ == '__main__':
    main()
