"""Worker v1: publish a validated, fast-forward pair from the selected checkout."""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import sys
import tempfile
from urllib.parse import urlsplit


REFS = ('refs/heads/main', 'refs/heads/gh-pages')
PUBLIC_META = 'https://news.kwinweng.com/data/meta.json'
META_PATH = 'rebang/data/meta.json'


def run_cycle(root, state, lock, observed):
    # Do not inherit build overrides, Git ref/index overrides or source credentials.
    startup_env = {key: os.environ[key] for key in ('PATH', 'HOME', 'TMPDIR', 'SSH_AUTH_SOCK') if key in os.environ}
    startup_env['BOX_PYTHON'] = sys.executable
    env = dict(startup_env, TZ='Asia/Shanghai', SITE_MODE='public', MAIL_DIGEST='0',
               GIT_TERMINAL_PROMPT='0', GIT_SSH_COMMAND='ssh -o BatchMode=yes', GIT_OPTIONAL_LOCKS='0',
               REBANG_WEIBO_COOKIE=str(state / 'no-source-credentials/weibo'),
               REBANG_WEREAD_SESSION=str(state / 'no-source-credentials/weread'))

    def run(*args, capture=False, stdout=None, input=None, extra_env=None):
        result = subprocess.run(args, cwd=root, env=dict(env, **(extra_env or {})), check=True,
                                pass_fds=(lock,), input=input,
                                stdout=subprocess.PIPE if capture else stdout)
        return result.stdout

    def git(*args, **kwargs):
        return run('git', *args, capture=True, **kwargs).decode().strip()

    halt = state / 'HALT'
    def halt_now(reason):
        with halt.open('x') as stream:
            stream.write(reason + '\n')
        raise RuntimeError(f'{reason}; stopped: {halt}')

    database = root / 'tg.db'
    def check_database(path=database):
        if path.is_symlink() or not path.is_file() or any(
                os.path.lexists(root / f'tg.db{suffix}') for suffix in ('-journal', '-wal', '-shm')):
            raise RuntimeError(f'{path.name} must be a regular file with no SQLite journal/WAL/SHM; preserve it for inspection')

    main_parent, pages_parent = observed
    code_sha = git('rev-parse', 'HEAD')
    if code_sha != main_parent:
        raise RuntimeError('checkout does not match the launcher-selected commit')
    origin = git('remote', 'get-url', 'origin')

    record = state / 'refs.json'

    def remember(refs):
        temp = state / 'refs.next'
        temp.write_text(json.dumps(dict(zip(REFS, refs))) + '\n')
        temp.replace(record)

    def remote_refs():
        return dict(line.split('\t')[::-1] for line in git('ls-remote', '--refs', 'origin', *REFS).splitlines())

    def check_remote_refs(expected, phase):
        actual = remote_refs()
        if actual != dict(zip(REFS, expected)):
            halt_now(f'remote refs moved {phase}; expected={expected}, actual={actual}; no push attempted')

    check_remote_refs(observed, 'during code switch')

    print(f'building source_commit={code_sha} gh-pages_parent={pages_parent}', flush=True)

    def prepare(work):
        if urlsplit(origin).scheme != 'file':
            actual = run('curl', '-qfsS', '--proto', '=https', '--max-time', '20',
                         '-H', 'Cache-Control: no-cache', PUBLIC_META, capture=True)
            expected = run('git', 'show', f'{pages_parent}:{META_PATH}', capture=True)
            if actual != expected:
                raise RuntimeError('public data/meta.json differs from the Pages parent; cannot use it as the receiver baseline')
            print(f'public_baseline_meta_sha256={hashlib.sha256(actual).hexdigest()}', flush=True)

        run(sys.executable, 'pipeline.py')
        meta = root / 'site-v11/data/meta.json'
        previous = meta.stat() if meta.is_file() else None
        run('sh', 'tools/rebang_refresh.sh', '--no-publish')
        if previous and os.path.samestat(previous, meta.stat()):
            raise RuntimeError('refresh did not replace the v11 metadata')
        v11 = json.loads(meta.read_text())
        if v11['fixture'] is not False or v11['counts']['news'] < 1:
            raise RuntimeError('v11 output is empty or a fixture')
        check_database()
        run(sys.executable, 'tools/write_build_info.py')
        info = json.loads((root / 'site/build-info.json').read_text())

        # A separate index starts at remote main, never at the code checkout.
        data_index = {'GIT_INDEX_FILE': str(work / 'index')}
        check_database()
        blob = git('hash-object', '-w', '--no-filters', str(database))
        with (work / 'db-blob').open('w+b') as raw_blob:
            run('git', 'cat-file', 'blob', blob, stdout=raw_blob)
            raw_blob.seek(0)
            db_sha = hashlib.file_digest(raw_blob, 'sha256').hexdigest()
        if info['source_commit'] != code_sha or info['database_sha256'] != db_sha:
            raise RuntimeError('packaged build inputs do not match the checked-out code and Git database blob')
        git('read-tree', main_parent, extra_env=data_index)
        git('update-index', '--cacheinfo', f'100644,{blob},tg.db', extra_env=data_index)
        data_tree = git('write-tree', extra_env=data_index)
        changes = git('diff-tree', '--no-commit-id', '--name-only', '-r', main_parent, data_tree)
        if changes not in ('', 'tg.db'):
            raise RuntimeError('data tree changes files other than tg.db')
        # Git omits unchanged refs from the server transaction, even with leases.
        message = 'Refresh public collection data' if changes else 'Refresh public collection data (no db change)'
        main_next = git('commit-tree', data_tree, '-p', main_parent, '-m', message)

        output = run('sh', 'tools/publish_pages.sh', '--dry-run', '--already-built', capture=True).decode()
        print(output, end='', flush=True)
        prepared = re.search(r'^Pages prepared: files=\d+ sha=([0-9a-f]+) dry-run=1$', output, re.M)
        if not prepared:
            raise RuntimeError('publisher did not report a dry-run commit')
        tree = git('rev-parse', f'{prepared[1]}^{{tree}}')
        pages_next = git('commit-tree', tree, '-p', pages_parent, '-m', 'Publish validated public site')
        if git('rev-parse', f'{pages_next}^{{tree}}') != tree:
            raise RuntimeError('Pages candidate tree differs from the dry-run tree')

        for label, commit in (('candidate', pages_next), ('baseline', pages_parent)):
            directory = work / label
            directory.mkdir()
            archive = work / f'{label}.tar'
            run('git', 'archive', '--format=tar', f'--output={archive}', commit)
            run('tar', '-xf', str(archive), '-C', str(directory))
        candidate = work / 'candidate'
        run('bash', 'deploy/news-sync.sh', '--source', str(candidate), '--target', str(work / 'baseline'),
            '--dry-run', '--work-dir', str(work))
        if (json.loads((candidate / 'build-info.json').read_text()) != info
                or json.loads((candidate / META_PATH).read_text()) != v11):
            raise RuntimeError('archive build metadata differs from this cycle')

        return (main_next, pages_next), db_sha

    with tempfile.TemporaryDirectory(prefix='cycle-', dir=state) as name:
        try:
            upcoming, db_sha = prepare(Path(name))
        except (OSError, RuntimeError, ValueError, KeyError, subprocess.CalledProcessError) as error:
            print(f'collection, build or validation failed at source_commit={code_sha}: {error}', file=sys.stderr)
            check_remote_refs(observed, 'during collection or build')
            raise
        check_remote_refs(observed, 'during collection or build')
        leases = [f'--force-with-lease={ref}:{old}' for ref, old in zip(REFS, observed)]
        refspecs = [f'{new}:{ref}' for ref, new in zip(REFS, upcoming)]
        # Leave this marker on rejection, ambiguous network result or interruption.
        with halt.open('x') as stream:
            stream.write(f'Push started; reconcile before resuming. Parents: {observed}; candidates: {upcoming}\n')
        try:
            run('git', 'push', '--atomic', '--no-follow-tags', *leases, 'origin', *refspecs)
        finally:
            # Keep HALT unless the push succeeded and both exact targets are visible.
            actual = remote_refs()
            if actual != dict(zip(REFS, upcoming)):
                reason = f'remote refs moved after push or push failed; expected={upcoming}, actual={actual}'
                with halt.open('a') as stream:
                    stream.write(reason + '\n')
                raise RuntimeError(reason) from None
        remember(upcoming)
        halt.unlink()
        print(f'published main={upcoming[0]} gh-pages={upcoming[1]} database_sha256={db_sha}', flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--worker-v1', nargs=4, required=True, metavar=('LOCK_FD', 'SOCKET_FD', 'MAIN', 'PAGES'))
    args = parser.parse_args()
    try:
        lock_fd, socket_fd, main, pages = args.worker_v1
        lock_fd, socket_fd = int(lock_fd), int(socket_fd)
        root = Path.cwd().resolve()
        state = root / '.git/mac-publish'
        if not os.path.samestat(os.fstat(lock_fd), (state / 'lock').stat()):
            raise RuntimeError('worker did not inherit the cycle lock')
        with os.fdopen(lock_fd, 'a') as lock, socket.socket(fileno=socket_fd) as gate:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise RuntimeError('worker did not inherit the held cycle lock') from None
            gate.sendall(b'1')
            if gate.recv(1) != b'G':
                raise RuntimeError('publisher startup cancelled by the fixed launcher')
            gate.close()
            run_cycle(root, state, lock.fileno(), (main, pages))
    except (OSError, RuntimeError, ValueError, KeyError, subprocess.CalledProcessError) as error:
        print(f'Mac publish failed: {error}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
