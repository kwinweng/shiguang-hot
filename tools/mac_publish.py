"""Collect in a pinned checkout and publish a validated, fast-forward pair once."""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import tempfile
from urllib.parse import urlsplit


ROOT = Path(__file__).resolve().parents[1]
REFS = ('refs/heads/main', 'refs/heads/gh-pages')
SNAPSHOTS = ('refs/mac-publish/main', 'refs/mac-publish/gh-pages')
PUBLIC_META = 'https://news.kwinweng.com/data/meta.json'
META_PATH = 'rebang/data/meta.json'


CREDENTIALS = (('REBANG_WEIBO_COOKIE', 'weibo-cookie.txt', 'weibo'),
               ('REBANG_WEREAD_SESSION', 'weread-session.json', 'weread'))


def _owner_only(path, kind):
    """True only for a real (non-symlink) file/dir of this user with no group/other permission bits."""
    try:
        info = os.lstat(path)
    except OSError:
        return False
    return kind(info.st_mode) and info.st_uid == os.getuid() and not info.st_mode & 0o077


def source_credentials(home, state):
    """Pass the fixed owner-only files in ~/.config/rebang to the collectors by path, never by content.

    Environment overrides are ignored on purpose; anything missing, shared or symlinked falls back to
    the reserved non-existent path, so that collector reports "not configured" instead of guessing.
    """
    folder = Path(home) / '.config/rebang' if home else None
    usable = folder is not None and _owner_only(folder, stat.S_ISDIR)
    env, enabled = {}, []
    for key, name, slot in CREDENTIALS:
        path = folder / name if usable else None
        if path is not None and _owner_only(path, stat.S_ISREG):
            env[key] = str(path)
            enabled.append(slot)
        else:
            env[key] = str(state / 'no-source-credentials' / slot)
    return env, enabled


def run_cycle(code_sha, state, lock):
    # Do not inherit build overrides, Git ref/index overrides or source credential overrides.
    env = {key: os.environ[key] for key in ('PATH', 'HOME', 'TMPDIR', 'SSH_AUTH_SOCK') if key in os.environ}
    credentials, enabled = source_credentials(env.get('HOME'), state)
    env.update(BOX_PYTHON=sys.executable, TZ='Asia/Shanghai', SITE_MODE='public', MAIL_DIGEST='0',
               GIT_TERMINAL_PROMPT='0', GIT_SSH_COMMAND='ssh -o BatchMode=yes', GIT_OPTIONAL_LOCKS='0',
               **credentials)
    print(f'source_credentials={",".join(enabled) or "none"}', flush=True)

    def run(*args, capture=False, stdout=None, input=None, extra_env=None):
        result = subprocess.run(args, cwd=ROOT, env=dict(env, **(extra_env or {})), check=True,
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

    if (git('branch', '--show-current') or git('rev-parse', 'HEAD') != code_sha
            or git('diff', '--name-only', 'HEAD', '--', '.', ':(exclude)tg.db')
            or git('diff', '--cached', '--name-only')
            or git('ls-files', '--others', '--exclude-standard')):
        raise RuntimeError('use a dedicated clean detached checkout at --code-sha (only unstaged tg.db may differ)')
    if (state / 'no-source-credentials').exists():
        raise RuntimeError('the reserved no-source-credentials path must not exist')
    origin = git('remote', 'get-url', 'origin')
    if git('remote', 'get-url', '--push', '--all', 'origin').splitlines() != [origin]:
        raise RuntimeError('origin must have exactly one push URL, identical to the fetch URL')

    git('fetch', '--no-tags', '--refmap=', 'origin',
        *(f'{source}:{dest}' for source, dest in zip(REFS, SNAPSHOTS)))
    observed = tuple(git('rev-parse', f'{ref}^{{commit}}') for ref in SNAPSHOTS)
    main_parent, pages_parent = observed
    record = state / 'refs.json'

    def remember(refs):
        temp = state / 'refs.next'
        temp.write_text(json.dumps(dict(zip(REFS, refs))) + '\n')
        temp.replace(record)

    if record.exists() and json.loads(record.read_text()) != dict(zip(REFS, observed)):
        halt_now(f'remote refs changed since the last local checkpoint: {observed}')

    database = ROOT / 'tg.db'

    def check_database():
        if database.is_symlink() or not database.is_file() or any(
                os.path.lexists(ROOT / f'tg.db{suffix}') for suffix in ('-journal', '-wal', '-shm')):
            raise RuntimeError('tg.db must be a regular file with no SQLite journal/WAL/SHM; preserve it for inspection')

    check_database()
    with tempfile.TemporaryDirectory(prefix='cycle-', dir=state) as name:
        work = Path(name)
        if not record.exists():
            current_blob = git('hash-object', '--no-filters', str(database))
            main_blob = git('rev-parse', f'{main_parent}:tg.db')
            if current_blob != main_blob:
                if current_blob != git('rev-parse', 'HEAD:tg.db'):
                    raise RuntimeError('unrecognized local tg.db at initialization; do not overwrite it')
                with (work / 'tg.db').open('wb') as output:
                    run('git', 'cat-file', 'blob', main_blob, stdout=output)
                (work / 'tg.db').replace(database)
            remember(observed)

        if urlsplit(origin).scheme != 'file':
            actual = run('curl', '-qfsS', '--proto', '=https', '--max-time', '20',
                         '-H', 'Cache-Control: no-cache', PUBLIC_META, capture=True)
            expected = run('git', 'show', f'{pages_parent}:{META_PATH}', capture=True)
            if actual != expected:
                raise RuntimeError('public data/meta.json differs from the Pages parent; cannot use it as the receiver baseline')
            print(f'public_baseline_meta_sha256={hashlib.sha256(actual).hexdigest()}', flush=True)

        run(sys.executable, 'pipeline.py')
        meta = ROOT / 'site-v11/data/meta.json'
        previous = meta.stat() if meta.is_file() else None
        run('sh', 'tools/rebang_refresh.sh', '--no-publish')
        if previous and os.path.samestat(previous, meta.stat()):
            raise RuntimeError('refresh did not replace the v11 metadata')
        v11 = json.loads(meta.read_text())
        if v11['fixture'] is not False or v11['counts']['news'] < 1:
            raise RuntimeError('v11 output is empty or a fixture')
        check_database()
        run(sys.executable, 'tools/write_build_info.py')
        info = json.loads((ROOT / 'site/build-info.json').read_text())

        # A separate index starts at remote main, never at the code checkout.
        data_index = {'GIT_INDEX_FILE': str(work / 'index')}
        check_database()
        blob = git('hash-object', '-w', '--no-filters', str(database))
        with (work / 'db-blob').open('w+b') as raw_blob:
            run('git', 'cat-file', 'blob', blob, stdout=raw_blob)
            raw_blob.seek(0)
            db_sha = hashlib.file_digest(raw_blob, 'sha256').hexdigest()
        if info['source_commit'] != code_sha or info['database_sha256'] != db_sha:
            raise RuntimeError('packaged build inputs do not match the pinned code and Git database blob')
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

        upcoming = (main_next, pages_next)
        # Normal Git push detects changes after its own advertisement; this also
        # catches rewinds or unrelated writes already visible before that push.
        advertised = dict(line.split('\t')[::-1] for line in git('ls-remote', '--refs', 'origin', *REFS).splitlines())
        if advertised != dict(zip(REFS, observed)):
            halt_now(f'remote refs moved during collection; observed={observed}, candidate={upcoming}; no push attempted')
        refspecs = [f'{new}:{ref}' for ref, old, new in zip(REFS, observed, upcoming) if new != old]
        # Leave this marker on rejection, ambiguous network result or interruption.
        with halt.open('x') as stream:
            stream.write(f'Push started; reconcile before resuming. Parents: {observed}; candidates: {upcoming}\n')
        run('git', 'push', '--atomic', '--no-follow-tags', 'origin', *refspecs)
        remember(upcoming)
        halt.unlink()
        print(f'published main={main_next} gh-pages={pages_next} database_sha256={db_sha}', flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--code-sha', required=True, help='full commit hash of this detached checkout')
    args = parser.parse_args()
    try:
        # In a dedicated clone these files outlive temporary archives and worktrees.
        state = ROOT / '.git/mac-publish'
        if not (ROOT / '.git').is_dir() or any(key.startswith('GIT_') for key in os.environ):
            raise RuntimeError('use a dedicated clone without inherited Git environment variables')
        state.mkdir(mode=0o700, exist_ok=True)
        with (state / 'lock').open('a') as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise RuntimeError('Mac publisher is already running') from None
            run_cycle(args.code_sha, state, lock.fileno())
    except (OSError, RuntimeError, ValueError, KeyError, subprocess.CalledProcessError) as error:
        print(f'Mac publish failed: {error}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
