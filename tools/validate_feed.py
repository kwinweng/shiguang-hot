#!/usr/bin/env python3
"""校验原生 feed 路径，或通过配置适配并校验指定 source-id。"""
import argparse, json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from shiguang.config import config, directory
from shiguang.ingest.feeds import normalize, validate
p = argparse.ArgumentParser(description=__doc__)
p.add_argument('target'); args = p.parse_args()
path = Path(args.target)
errors = 0
if path.is_file():
    try:
        data = json.loads(path.read_text()); issues = [(data, path.parent)]
    except (OSError, ValueError) as ex: print('ERROR:', ex); raise SystemExit(1)
else:
    source = next((s for s in config()['sources'] if s['id'] == args.target and s['type'] == 'inbox'), None)
    if not source: print('ERROR: 来源不存在'); raise SystemExit(1)
    # Validate original inputs too; do not let the tolerant build loader hide invalid issues.
    issues = []
    for file in sorted(directory(source).glob('????-??-??/' + source.get('filename', 'feed.json'))):
        try: issues.append((normalize(json.loads(file.read_text()), source), file.parent))
        except (OSError, ValueError) as ex: print('ERROR:', file, ex); errors += 1
if not issues: print('ERROR: 没有可校验数据'); raise SystemExit(1)
for data, base in issues:
    err, warn = validate(data, base, source['id'] if not path.is_file() else None)
    if data.get('date') != base.name: err.append('目录日期与 date 不符')
    for msg in err: print('ERROR:', base, msg)
    for msg in warn: print('WARNING:', base, msg)
    errors += len(err)
print(f'{len(issues)} 期；{errors} 个错误')
raise SystemExit(1 if errors else 0)
