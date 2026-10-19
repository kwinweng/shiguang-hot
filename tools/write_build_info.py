"""Record public build inputs, independently of the run's original event SHA."""
import hashlib
import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path


def write_info(root):
    def git(*args):
        return subprocess.check_output(['git', *args], cwd=root, text=True).strip()

    output = root / 'site'
    if not (output / 'index.html').is_file():
        raise RuntimeError('Build the public site before recording its inputs')
    info = {
        'schema': 'shiguang.build/1',
        'source_commit': git('rev-parse', 'HEAD'),
        'public_feeds_tree': git('rev-parse', 'HEAD:public-feeds'),
        'database_sha256': hashlib.sha256((root / 'tg.db').read_bytes()).hexdigest(),
        'built_at': datetime.now(timezone.utc).isoformat(),
        'event': os.environ.get('GITHUB_EVENT_NAME', 'local'),
        'run_id': os.environ.get('GITHUB_RUN_ID'),
    }
    (output / 'build-info.json').write_text(json.dumps(info, indent=2) + '\n')
    return info


if __name__ == '__main__':
    write_info(Path(__file__).resolve().parent.parent)
