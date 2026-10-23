"""Run the public pipeline under a checkout-wide lock, or in an isolated copy."""
import argparse
import fcntl
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
from datetime import datetime
from contextlib import redirect_stdout, redirect_stderr


def positive(value):
    number = int(value)
    if number <= 0:
        raise argparse.ArgumentTypeError('limit must be positive')
    return number


def arguments(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--checkout', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--log-dir', type=Path, default=None)
    parser.add_argument('--dry-run', action='store_true', help='validate and print plan; no scrape or git')
    parser.add_argument('--test-dir', type=Path, help='new directory for isolated database, media and site; never git')
    parser.add_argument('--limit', type=positive, help='cap sources and HTTP calls; requires --test-dir')
    args = parser.parse_args(argv)
    if args.limit and not args.test_dir:
        parser.error('--limit requires --test-dir')
    args.checkout = args.checkout.resolve()
    if args.test_dir:
        args.test_dir = args.test_dir.resolve()
        if args.test_dir.exists() or args.test_dir.is_relative_to(args.checkout) or args.checkout.is_relative_to(args.test_dir):
            parser.error('--test-dir must be a new directory outside the checkout')
    if not (args.checkout / 'pipeline.py').is_file() or not (args.checkout / 'tg.db').is_file():
        parser.error('checkout requires pipeline.py and a known tg.db')
    return args


def isolated_copy(checkout, target):
    target.mkdir(parents=True)
    # Explicit allowlist: never copy .env, credentials, private inputs or Git metadata.
    for name in ('pipeline.py', 'sources.json', 'trial-sources.json', 'shiguang', 'web', 'public-feeds'):
        source = checkout / name
        if source.is_dir():
            shutil.copytree(source, target / name, ignore=shutil.ignore_patterns('__pycache__'))
        elif source.is_file():
            shutil.copy2(source, target / name)
    with sqlite3.connect(f'file:{checkout / "tg.db"}?mode=ro', uri=True) as source:
        with sqlite3.connect(target / 'tg.db') as destination:
            source.backup(destination)


def run_pipeline(root, limit=None):
    # A fresh interpreter ensures all module ROOT constants point at the isolated copy.
    program = '''
import runpy, sys
sys.path.insert(0, sys.argv[1])
if sys.argv[2]:
    from shiguang.ingest import http, scheduler, trial
    limit = int(sys.argv[2])
    original_request, original_run = http.request, scheduler.run
    remaining = [limit]
    def request(*args, **kwargs):
        if remaining[0] <= 0:
            raise http.FetchFailure('request_limit')
        remaining[0] -= 1
        return original_request(*args, **kwargs)
    def run(db, sources, **kwargs):
        sources = [s for s in sources if s['type'] in ('telegram', 'feed')][:limit]
        return original_run(db, sources, **kwargs)
    http.request, scheduler.run = request, run
    trial.run = lambda *args, **kwargs: None
runpy.run_path(sys.argv[1] + '/pipeline.py', run_name='__main__')
'''
    env = os.environ.copy()
    for name in ('SOURCES_OVERRIDE', 'SITE_OUT'):
        env.pop(name, None)
    env.update(TZ='Asia/Shanghai', SITE_MODE='public', MAIL_DIGEST='0', NO_FETCH='0', PYTHONUNBUFFERED='1')
    subprocess.run([sys.executable, '-c', program, str(root), str(limit or '')], cwd=root, env=env, check=True)


def execute(args):
    root = args.checkout
    if args.test_dir:
        isolated_copy(root, args.test_dir)
        run_pipeline(args.test_dir, args.limit)
        return
    def git(*values):
        return subprocess.check_output(['git', *values], cwd=root, text=True).strip()
    if git('branch', '--show-current') != 'main':
        raise RuntimeError('normal mode requires main')
    if git('status', '--porcelain', '--untracked-files=no'):
        raise RuntimeError('normal mode requires clean tracked files; preserve and resolve pending data first')
    subprocess.run(['git', 'fetch', 'origin', 'main'], cwd=root, check=True)
    subprocess.run(['git', 'merge', '--ff-only', 'origin/main'], cwd=root, check=True)
    run_pipeline(root)
    subprocess.run(['sh', 'tools/persist_action_data.sh'], cwd=root, check=True)


def main(argv=None):
    args = arguments(argv)
    if args.dry_run:
        print(f'checkout={args.checkout} output={args.test_dir or args.checkout} limit={args.limit} push={not bool(args.test_dir)}; dry-run: no execution')
        return 0
    logs = (args.log_dir or args.checkout / 'logs/box-scrape').resolve()
    logs.mkdir(parents=True, exist_ok=True)
    os.environ['TZ'] = 'Asia/Shanghai'
    import time
    time.tzset()
    with open(args.checkout / '.box-scrape.lock', 'a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print('box scrape busy; skipped')
            return 0
        logfile = logs / (datetime.now().strftime('%Y-%m-%dT%H%M%S') + f'-{os.getpid()}.log')
        print(f'log={logfile}', flush=True)
        with logfile.open('a', buffering=1) as output, redirect_stdout(output), redirect_stderr(output):
            # Child processes inherit file descriptors, not Python stream redirects.
            saved = os.dup(1), os.dup(2)
            try:
                os.dup2(output.fileno(), 1)
                os.dup2(output.fileno(), 2)
                print(f'start {datetime.now().isoformat()}', flush=True)
                execute(args)
                print(f'success {datetime.now().isoformat()}', flush=True)
            except Exception as error:
                print(f'failed: {type(error).__name__}: {error}', flush=True)
                return 1
            finally:
                os.dup2(saved[0], 1)
                os.dup2(saved[1], 2)
                for descriptor in saved:
                    os.close(descriptor)
    return 0


if __name__ == '__main__':
    sys.exit(main())
