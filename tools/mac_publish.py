"""Collect in a pinned checkout and publish a validated, fast-forward pair once.

The code stays at --code-sha. Remote main may move on by normal merges (fast-forward,
gh-pages and tg.db untouched); the next data commit is then built on the new main with
the same pinned code. Anything else stops with HALT. Switching code is a manual step."""
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
PUSH_TIMEOUT = 900
SKIPPED = 75  # EX_TEMPFAIL: nothing published, nothing stopped, the next round retries
SHA = re.compile(r'[0-9a-f]{40}')
# `git push --porcelain` summaries that mean the push was refused before any ref moved.
LEASE_REJECTED, ATOMIC_REJECTED = '[rejected] (stale info)', '[rejected] (atomic push failed)'


class Skipped(Exception):
    """Someone merged main normally during this round; publish again from the new main next round."""


def write_atomic(path, text):
    """Replace path in one step: a temporary file in the same directory, flushed, then renamed."""
    fd, temp = tempfile.mkstemp(prefix=f'.{path.name}.', dir=path.parent)
    try:
        with os.fdopen(fd, 'w') as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, path)
    except BaseException:
        if os.path.lexists(temp):
            os.unlink(temp)
        raise
    directory = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)


def clean_rejection(output, refs):
    """True only if porcelain output shows every ref refused client-side, at least one by the lease."""
    lines = output.splitlines()
    if not lines or lines[-1] != 'Done':
        return False
    status = {}
    for line in lines:
        fields = line.split('\t')
        if len(fields) == 3 and ':' in fields[1]:
            destination = fields[1].rsplit(':', 1)[1]
            if destination in status:
                return False
            status[destination] = (fields[0], fields[2])
    if set(status) != set(refs):
        return False
    if not all(flag == '!' and summary in (LEASE_REJECTED, ATOMIC_REJECTED) for flag, summary in status.values()):
        return False
    return any(summary == LEASE_REJECTED for _, summary in status.values())


def run_cycle(code_sha, state, lock):
    # Do not inherit build overrides, Git ref/index overrides or source credentials.
    env = {key: os.environ[key] for key in ('PATH', 'HOME', 'TMPDIR', 'SSH_AUTH_SOCK') if key in os.environ}
    env.update(BOX_PYTHON=sys.executable, TZ='Asia/Shanghai', SITE_MODE='public', MAIL_DIGEST='0',
               GIT_TERMINAL_PROMPT='0', GIT_SSH_COMMAND='ssh -o BatchMode=yes', GIT_OPTIONAL_LOCKS='0',
               REBANG_WEIBO_COOKIE=str(state / 'no-source-credentials/weibo'),
               REBANG_WEREAD_SESSION=str(state / 'no-source-credentials/weread'))

    def run(*args, capture=False, stdout=None, input=None, extra_env=None):
        result = subprocess.run(args, cwd=ROOT, env=dict(env, **(extra_env or {})), check=True,
                                pass_fds=(lock,), input=input,
                                stdout=subprocess.PIPE if capture else stdout)
        return result.stdout

    def git(*args, **kwargs):
        return run('git', *args, capture=True, **kwargs).decode().strip()

    def is_ancestor(old, new):
        found = subprocess.run(['git', 'merge-base', '--is-ancestor', old, new], cwd=ROOT, env=env,
                               pass_fds=(lock,), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if found.returncode not in (0, 1):
            raise RuntimeError(f'cannot compare {old} and {new}')
        return found.returncode == 0

    def database_entry(commit):
        # Mode, type and blob of tg.db in the tree; empty if missing.
        return git('ls-tree', '--full-tree', commit, '--', 'tg.db')

    halt = state / 'HALT'
    if halt.exists():
        raise RuntimeError(f'HALT exists: {halt}; reconcile the local database and both remote refs before resuming')

    def halt_now(reason):
        with halt.open('x') as stream:
            stream.write(reason + '\n')
            stream.flush()
            os.fsync(stream.fileno())
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

    def fetch():
        # Snapshots are private scratch refs; force them so a rewritten main reaches the checks below.
        git('fetch', '--no-tags', '--refmap=', 'origin',
            *(f'+{source}:{dest}' for source, dest in zip(REFS, SNAPSHOTS)))
        return tuple(git('rev-parse', f'{ref}^{{commit}}') for ref in SNAPSHOTS)

    def normal_advance(old_main, new_main):
        """Someone else fast-forwarded main (e.g. a merge) without touching tg.db's mode, type or blob."""
        old_entry = database_entry(old_main)
        return (new_main != old_main and is_ancestor(old_main, new_main)
                and old_entry != '' and database_entry(new_main) == old_entry)

    def only_main_advanced(main_parent, pages_parent):
        """Re-read the remote: gh-pages exactly as we built on, main only normally ahead of it."""
        try:
            main_now, pages_now = fetch()
            return pages_now == pages_parent and normal_advance(main_parent, main_now)
        except (OSError, RuntimeError, subprocess.SubprocessError):
            return False

    observed = fetch()
    main_parent, pages_parent = observed
    record = state / 'refs.json'

    def remember(refs):
        write_atomic(record, json.dumps(dict(zip(REFS, refs))) + '\n')

    if os.path.lexists(record):
        try:
            recorded = json.loads(record.read_text())
            if (not isinstance(recorded, dict) or set(recorded) != set(REFS)
                    or not all(isinstance(value, str) and SHA.fullmatch(value) for value in recorded.values())):
                raise ValueError('unexpected structure')
        except (OSError, ValueError) as error:
            halt_now(f'local checkpoint {record} is unreadable ({error}); preserved for inspection')
        if recorded != dict(zip(REFS, observed)):
            if recorded[REFS[1]] == pages_parent and normal_advance(recorded[REFS[0]], main_parent):
                print(f'main advanced normally {recorded[REFS[0]]}..{main_parent}; '
                      f'publishing on it with pinned code {code_sha}', flush=True)
            else:
                halt_now(f'remote refs changed since the last local checkpoint: recorded={recorded}, '
                         f'observed={observed}')
    if not is_ancestor(code_sha, main_parent):
        raise RuntimeError(f'remote main must contain --code-sha {code_sha}; refusing without writing checkpoints')

    database = ROOT / 'tg.db'

    def check_database():
        if database.is_symlink() or not database.is_file() or any(
                os.path.lexists(ROOT / f'tg.db{suffix}') for suffix in ('-journal', '-wal', '-shm')):
            raise RuntimeError('tg.db must be a regular file with no SQLite journal/WAL/SHM; preserve it for inspection')

    check_database()
    with tempfile.TemporaryDirectory(prefix='cycle-', dir=state) as name:
        work = Path(name)
        if not os.path.lexists(record):
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
        if not all(is_ancestor(old, new) for old, new in zip(observed, upcoming)):
            raise RuntimeError('candidates are not fast-forwards of the observed refs')
        skip = (f'main advanced normally during this round; nothing published, no HALT; the next round '
                f'builds on the new main. Built on {observed}')
        # Catch rewinds or unrelated writes already visible before the push.
        advertised = dict(line.split('\t')[::-1] for line in git('ls-remote', '--refs', 'origin', *REFS).splitlines())
        if advertised != dict(zip(REFS, observed)):
            if only_main_advanced(*observed):
                raise Skipped(skip)
            halt_now(f'remote refs moved during collection; observed={observed}, candidate={upcoming}; no push attempted')
        # One atomic push names both refs, even an unchanged main, each with the exact old value it
        # was built on: any later move of either ref (including a rewind to an ancestor) is refused.
        leases = [f'--force-with-lease={ref}:{old}' for ref, old in zip(REFS, observed)]
        refspecs = [f'{new}:{ref}' for ref, new in zip(REFS, upcoming)]
        # Leave this marker on rejection, ambiguous network result or interruption.
        with halt.open('x') as stream:
            stream.write(f'Push started; reconcile before resuming. Parents: {observed}; candidates: {upcoming}\n')
            stream.flush()
            os.fsync(stream.fileno())
        pushed = subprocess.run(['git', 'push', '--atomic', '--porcelain', '--no-follow-tags', *leases,
                                 'origin', *refspecs], cwd=ROOT, env=env, pass_fds=(lock,),
                                stdout=subprocess.PIPE, timeout=PUSH_TIMEOUT)
        output = pushed.stdout.decode(errors='replace')
        print(output, end='', flush=True)
        if pushed.returncode:
            # Only a definite client-side refusal followed by a confirmed normal merge is safe to
            # retry; HALT stays for anything else (disconnect, timeout, hook, unclear result).
            if pushed.returncode == 1 and clean_rejection(output, REFS) and only_main_advanced(*observed):
                halt.unlink()
                raise Skipped(skip)
            raise RuntimeError(f'push failed (exit {pushed.returncode}); HALT kept: {halt}')
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
    except Skipped as skipped:
        print(f'Mac publish skipped: {skipped}', file=sys.stderr)
        return SKIPPED
    except (OSError, RuntimeError, ValueError, KeyError, subprocess.SubprocessError) as error:
        print(f'Mac publish failed: {error}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
