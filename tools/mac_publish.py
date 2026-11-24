"""Follow main in a dedicated checkout and publish a validated, fast-forward pair once."""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from urllib.parse import urlsplit


ROOT = Path(__file__).resolve().parents[1]
REFS = ('refs/heads/main', 'refs/heads/gh-pages')
SNAPSHOTS = ('refs/mac-publish/main', 'refs/mac-publish/gh-pages')
PUBLIC_META = 'https://news.kwinweng.com/data/meta.json'
META_PATH = 'rebang/data/meta.json'


def run_cycle(root, state, lock, handoff=None):
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
    if halt.exists():
        raise RuntimeError(f'HALT exists: {halt}; reconcile the local database and both remote refs before resuming')

    def halt_now(reason):
        with halt.open('x') as stream:
            stream.write(reason + '\n')
        raise RuntimeError(f'{reason}; stopped: {halt}')

    database = root / 'tg.db'
    saved_database = state / 'checkout-tg.db'

    def check_database(path=database):
        if path.is_symlink() or not path.is_file() or any(
                os.path.lexists(root / f'tg.db{suffix}') for suffix in ('-journal', '-wal', '-shm')):
            raise RuntimeError(f'{path.name} must be a regular file with no SQLite journal/WAL/SHM; preserve it for inspection')

    if os.path.lexists(saved_database):
        check_database(saved_database)
        saved_database.replace(database)
        print('restored local tg.db after an interrupted checkout', flush=True)
    check_database()

    code_sha = git('rev-parse', 'HEAD')
    if (git('branch', '--show-current')
            or git('diff', '--name-only', 'HEAD', '--', '.', ':(exclude)tg.db')
            or git('diff', '--cached', '--name-only')
            or git('ls-files', '--others', '--exclude-standard')):
        raise RuntimeError('use a dedicated clean detached checkout (only unstaged tg.db may differ)')
    if (state / 'no-source-credentials').exists():
        raise RuntimeError('the reserved no-source-credentials path must not exist')
    origin = git('remote', 'get-url', 'origin')
    if git('remote', 'get-url', '--push', '--all', 'origin').splitlines() != [origin]:
        raise RuntimeError('origin must have exactly one push URL, identical to the fetch URL')

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

    if handoff is not None:
        previous_head, *refs = handoff
        if code_sha != previous_head:
            raise RuntimeError('checkout does not match the publisher handoff')
        observed = tuple(refs)
        check_remote_refs(observed, 'during code switch')
    else:
        # Force only the private fetch refs so rewinds can be compared to the checkpoint.
        try:
            git('fetch', '--no-tags', '--refmap=', 'origin',
                *(f'+{source}:{dest}' for source, dest in zip(REFS, SNAPSHOTS)))
        except subprocess.CalledProcessError:
            missing = set(REFS) - remote_refs().keys()
            if missing:
                halt_now(f'remote refs missing: {sorted(missing)}')
            raise
        observed = tuple(git('rev-parse', f'{ref}^{{commit}}') for ref in SNAPSHOTS)
    main_parent, pages_parent = observed
    checkpoint = json.loads(record.read_text()) if record.exists() else None
    if checkpoint is not None:
        if checkpoint[REFS[1]] != pages_parent:
            halt_now(f'gh-pages changed since the last local checkpoint: {checkpoint[REFS[1]]} -> {pages_parent}')
        try:
            git('merge-base', '--is-ancestor', checkpoint[REFS[0]], main_parent)
        except subprocess.CalledProcessError as error:
            if error.returncode == 1:
                halt_now(f'main is not a fast-forward: {checkpoint[REFS[0]]} -> {main_parent}')
            raise

    def database_blob(commit):
        entry = git('ls-tree', commit, '--', 'tg.db').split()
        if entry[:2] != ['100644', 'blob']:
            raise RuntimeError(f'{commit} must track tg.db as a regular 100644 blob')
        return entry[2]

    def copy_blob(blob, path):
        with path.open('wb') as output:
            run('git', 'cat-file', 'blob', blob, stdout=output)

    with tempfile.TemporaryDirectory(prefix='cycle-', dir=state) as name:
        work = Path(name)
        pending_db = work / 'tg.db'
        main_blob = database_blob(main_parent)
        current_blob = git('hash-object', '--no-filters', str(database))
        if checkpoint is not None and checkpoint[REFS[0]] != main_parent:
            previous_blob = database_blob(checkpoint[REFS[0]])
            if main_blob != previous_blob and current_blob != main_blob:
                remote_copy = state / f'remote-tg-{main_parent}.db'
                copy_blob(main_blob, pending_db)
                pending_db.replace(remote_copy)
                halt_now(f'remote tg.db changed: checkpoint={previous_blob}, candidate={main_blob}, '
                         f'local={current_blob}, main={main_parent}; kept {database} and {remote_copy}')

        if code_sha != main_parent and handoff is None:
            # Boot the new publisher while the known-good entry is still installed.
            launcher = work / 'mac_publish.sh'
            candidate = work / 'mac_publish.py'
            try:
                for path in (launcher, candidate):
                    with path.open('wb') as output:
                        run('git', 'show', f'{main_parent}:tools/{path.name}', stdout=output)
                run('/bin/sh', '-n', str(launcher))
                run(sys.executable, '-I', '-m', 'py_compile', str(candidate))
                run(sys.executable, '-I', '-c', 'import runpy, sys; runpy.run_path(sys.argv[1])', str(candidate))
            except (OSError, subprocess.CalledProcessError) as error:
                raise RuntimeError(f'publisher preflight failed for candidate {main_parent}: {error}') from error
            started = work / 'started'
            try:
                subprocess.run(['/bin/sh', str(launcher), '--resume', str(lock), code_sha, *observed],
                               cwd=root, env=startup_env, pass_fds=(lock,), check=True)
            finally:
                if not started.is_file():
                    raise RuntimeError(f'publisher boot failed for candidate {main_parent} before startup confirmation') from None
            return

        head_blob = database_blob(code_sha) if code_sha != main_parent else main_blob
        if checkpoint is None and current_blob != main_blob:
            if current_blob != head_blob:
                raise RuntimeError('unrecognized local tg.db at initialization; do not overwrite it')
            copy_blob(main_blob, pending_db)
            pending_db.replace(database)
        if checkpoint != dict(zip(REFS, observed)):
            # A failed build can retry this baseline, but a later rewind must halt.
            remember(observed)

        if code_sha != main_parent:
            if head_blob != main_blob:
                # Give checkout the old tracked version and restore the exact local file.
                # Keep the saved copy outside the temporary directory for crash recovery.
                copy_blob(head_blob, pending_db)
                database.replace(saved_database)
            try:
                if saved_database.exists():
                    pending_db.replace(database)
                run('git', 'checkout', '--detach', '--no-overwrite-ignore', main_parent)
            finally:
                if saved_database.exists():
                    saved_database.replace(database)
            print(f'code switched: {code_sha} -> {main_parent}', flush=True)
            code_sha = main_parent
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
        main_next = git('commit-tree', data_tree, '-p', main_parent, '-m', 'Refresh public collection data') if changes else main_parent

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
            # Git can omit an up-to-date ref from the remote transaction.
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
    parser.add_argument('--code-sha', help='accepted for compatibility with existing launchd plists')
    parser.add_argument('--resume', nargs=4, help=argparse.SUPPRESS)
    args = parser.parse_args()
    try:
        # A staged publisher is launched with the dedicated clone as its cwd.
        root = ROOT if args.resume is None else Path.cwd()
        state = root / '.git/mac-publish'
        if not (root / '.git').is_dir() or any(key.startswith('GIT_') for key in os.environ):
            raise RuntimeError('use a dedicated clone without inherited Git environment variables')
        state.mkdir(mode=0o700, exist_ok=True)
        lock_path = state / 'lock'
        handoff = None
        if args.resume is None:
            lock = lock_path.open('a')
        else:
            fd_text, *handoff = args.resume
            lock_fd = int(fd_text)
            if not os.path.samestat(os.fstat(lock_fd), lock_path.stat()):
                raise RuntimeError('publisher handoff did not inherit the cycle lock')
            lock = os.fdopen(lock_fd, 'a')
        with lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise RuntimeError('Mac publisher is already running') from None
            if handoff is not None:
                Path(__file__).with_name('started').touch(exist_ok=False)
            run_cycle(root, state, lock.fileno(), handoff)
    except (OSError, RuntimeError, ValueError, KeyError, subprocess.CalledProcessError) as error:
        print(f'Mac publish failed: {error}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
