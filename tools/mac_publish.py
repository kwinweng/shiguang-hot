"""Collect in a pinned checkout and publish a validated, fast-forward pair once.

The code stays at --code-sha. Remote main may move on by normal merges (fast-forward,
gh-pages and tg.db untouched); the next data commit is then built on the new main with
the same pinned code. Anything else stops with HALT. Switching code is a manual step."""
import argparse
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
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
X_INBOX_ENV = 'REBANG_X_INBOX_REPO'  # optional read-only X inbox; unset or empty = no inbox step at all
X_INBOX_WORK = '.x-inbox-work-'      # per-round work directories under var/rebang, always deleted


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


def import_x_inbox(repo, root, env):
    """Optional X inbox step before collection (docs/rebang-v1/X-INBOX.md). Prints one result line
    and, only if deleting work directories fails, one separate cleanup line. Never raises, never
    writes HALT and never touches tracked files: X problems must not stop other sources."""
    var = root / 'var/rebang'
    result = dict(installed=[], pruned=[], error='x_inbox_internal', prune_error=None)

    def cleanup():
        # All work directories, including ones left by a killed earlier round. Runs under the
        # publisher lock, so no other round is using them.
        failures = []
        try:
            leftovers = [p for p in var.iterdir() if p.name.startswith(X_INBOX_WORK)] if var.is_dir() else []
        except OSError as error:
            return [type(error).__name__]
        for path in leftovers:
            try:
                if path.is_symlink() or not path.is_dir():
                    path.unlink()
                else:
                    shutil.rmtree(path)
            except OSError as error:
                failures.append(type(error).__name__)
        return failures

    failures = []
    try:
        failures += cleanup()
        tools = str(ROOT / 'tools')
        if tools not in sys.path:
            sys.path.insert(0, tools)
        import x_inbox
        var.mkdir(parents=True, exist_ok=True)
        work = Path(tempfile.mkdtemp(prefix=X_INBOX_WORK, dir=var))
        result = x_inbox.pull(repo, work, var / 'x-dump', env=env)
    except Exception:  # noqa: BLE001 - any receiver bug is reported as one code, never a failed round
        pass
    finally:
        line = 'x_inbox=' + ('ok' if result['error'] is None else f'error code={result["error"]}')
        line += ' installed=' + (','.join(result['installed']) or 'none')
        if result['pruned']:
            line += f' pruned={len(result["pruned"])}'
        if result['prune_error']:
            line += f' prune_error={result["prune_error"]}'
        print(line, flush=True)
        failures += cleanup()
        if failures:
            print(f'x_inbox_cleanup=failed error={failures[0]} count={len(failures)}', flush=True)


def main_only_rejection(output, candidates):
    """True only for the one retryable receipt, line for line: Git's `To <url>` header, exactly two
    status lines (main refused client-side by its lease, gh-pages refused only as a consequence of
    --atomic, each naming our exact candidate), then `Done`. Anything else (gh-pages stale, a
    server-side refusal, a missing, extra, blank or truncated line) is False."""
    lines = output.splitlines()
    if len(lines) != 4 or not lines[0].startswith('To ') or lines[-1] != 'Done':
        return False
    status = {}
    for line in lines[1:3]:
        fields = line.split('\t')
        if len(fields) != 3 or ':' not in fields[1]:
            return False
        source, destination = fields[1].rsplit(':', 1)
        if destination in status:
            return False
        status[destination] = (fields[0], source, fields[2])
    expected = {REFS[0]: ('!', candidates[0], LEASE_REJECTED), REFS[1]: ('!', candidates[1], ATOMIC_REJECTED)}
    return status == expected


CREDENTIALS = (('REBANG_WEIBO_COOKIE', 'weibo-cookie.txt', 'weibo'),
               ('REBANG_WEREAD_SESSION', 'weread-session.json', 'weread'))


def _load_private_file():
    # Stdlib-only helper shared with the collectors, loaded by path so the rebang package is not imported.
    spec = importlib.util.spec_from_file_location('rebang_private_file', ROOT / 'rebang/private_file.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


private_file = _load_private_file()


def source_credentials(state, home=None):
    """Pass the fixed owner-only files in <account home>/.config/rebang to the collectors by path, never by content.

    The home comes from the user database (not HOME); environment overrides are ignored on purpose.
    This is only a preflight: the collectors open the files again with the same checks on the same
    descriptor they read from. Anything missing, shared, linked or symlinked anywhere on the way sets
    the collector's environment variable to '' (explicitly disabled, never a fallback path), so that
    collector reports "not configured" instead of reading any other file.
    """
    if home is None:
        try:
            home = private_file.account_home()
        except (KeyError, OSError):
            home = None
    folder = Path(home) / '.config/rebang' if home else None
    env, enabled = {}, []
    for key, name, slot in CREDENTIALS:
        path = folder / name if folder else None
        if path is not None and private_file.check_private(path):
            env[key] = str(path)
            enabled.append(slot)
        else:
            env[key] = ''
    return env, enabled


def run_cycle(code_sha, state, lock, x_inbox_repo=''):
    # Do not inherit build overrides, Git ref/index overrides or source credential overrides.
    env = {key: os.environ[key] for key in ('PATH', 'HOME', 'TMPDIR', 'SSH_AUTH_SOCK') if key in os.environ}
    env.update(BOX_PYTHON=sys.executable, TZ='Asia/Shanghai', SITE_MODE='public', MAIL_DIGEST='0',
               GIT_TERMINAL_PROMPT='0', GIT_SSH_COMMAND='ssh -o BatchMode=yes', GIT_OPTIONAL_LOCKS='0')
    # Until collection starts, the collectors' credential variables are explicitly disabled ('').
    env.update({key: '' for key, _, _ in CREDENTIALS})

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
    origin = git('remote', 'get-url', 'origin')
    if git('remote', 'get-url', '--push', '--all', 'origin').splitlines() != [origin]:
        raise RuntimeError('origin must have exactly one push URL, identical to the fetch URL')

    def fetch():
        # Snapshots are private scratch refs; force them so a rewritten main reaches the checks below.
        # stderr is kept (in the C locale) so a missing remote branch can be told from a network error.
        fetched = subprocess.run(['git', 'fetch', '--no-tags', '--refmap=', 'origin',
                                  *(f'+{source}:{dest}' for source, dest in zip(REFS, SNAPSHOTS))],
                                 cwd=ROOT, env=dict(env, LC_ALL='C'), pass_fds=(lock,),
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        sys.stderr.write(fetched.stderr.decode(errors='replace'))
        sys.stderr.flush()
        if fetched.returncode:
            raise subprocess.CalledProcessError(fetched.returncode, fetched.args, fetched.stdout, fetched.stderr)
        return tuple(git('rev-parse', f'{ref}^{{commit}}') for ref in SNAPSHOTS)

    def ls_remote():
        """The two remote refs as advertised right now (missing refs are simply absent)."""
        listed = git('ls-remote', '--refs', 'origin', *REFS, extra_env={'LC_ALL': 'C'})
        return dict(line.split('\t')[::-1] for line in listed.splitlines())

    def normal_advance(old_main, new_main):
        """Someone else fast-forwarded main (e.g. a merge) without touching tg.db's mode, type or blob."""
        old_entry = database_entry(old_main)
        return (new_main != old_main and is_ancestor(old_main, new_main)
                and old_entry != '' and database_entry(new_main) == old_entry)

    def only_main_advanced(main_parent, pages_parent, main_seen=None):
        """Re-read the remote: gh-pages exactly as we built on, main only normally ahead of it.
        main_seen is a main value an earlier check already observed; it must sit on the same
        normal path (main_parent -> main_seen -> now). A re-read never overrides an earlier anomaly:
        callers only get here after gh-pages was seen at its baseline in every observation."""
        try:
            main_now, pages_now = fetch()
            if pages_now != pages_parent:
                return False
            if main_seen is None:
                return normal_advance(main_parent, main_now)
            return normal_advance(main_parent, main_seen) and (
                main_now == main_seen or normal_advance(main_seen, main_now))
        except (OSError, RuntimeError, subprocess.SubprocessError):
            return False

    record = state / 'refs.json'

    def remember(refs):
        write_atomic(record, json.dumps(dict(zip(REFS, refs))) + '\n')

    def is_commit(sha):
        found = subprocess.run(['git', 'rev-parse', '--verify', '--quiet', f'{sha}^{{commit}}'], cwd=ROOT,
                               env=env, pass_fds=(lock,), stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        return found.returncode == 0 and found.stdout.decode().strip() == sha

    # Validate the checkpoint before talking to the remote: a failed fetch is judged against it.
    recorded = None
    if os.path.lexists(record):
        try:
            recorded = json.loads(record.read_text())
            if (not isinstance(recorded, dict) or set(recorded) != set(REFS)
                    or not all(isinstance(value, str) and SHA.fullmatch(value) for value in recorded.values())):
                raise ValueError('unexpected structure')
            invalid = [value for value in recorded.values() if not is_commit(value)]
            if invalid:
                raise ValueError(f'not a usable local commit: {invalid}')
        except (OSError, ValueError, subprocess.SubprocessError) as error:
            halt_now(f'local checkpoint {record} is unreadable ({error}); preserved for inspection')

    try:
        observed = fetch()
    except subprocess.CalledProcessError as error:
        # Conservative: only "the remote cannot be reached at all, and nothing odd was seen" retries
        # without HALT. A missing branch reported by fetch stops at once; a later re-read never
        # overrides it. A reachable remote after a failed fetch also stops, whatever it shows.
        if "couldn't find remote ref" in (error.stderr or b'').decode(errors='replace'):
            halt_now("remote lacks a branch (fetch: couldn't find remote ref); "
                     'reconcile the remote branches before resuming')
        listed = subprocess.run(['git', 'ls-remote', '--refs', 'origin', *REFS], cwd=ROOT,
                                env=dict(env, LC_ALL='C'), pass_fds=(lock,), stdout=subprocess.PIPE)
        if listed.returncode:
            raise RuntimeError(f'remote unreachable (fetch exit {error.returncode}, ls-remote exit '
                               f'{listed.returncode}); no HALT, the next round retries') from None
        advertised = {}
        for line in listed.stdout.decode(errors='replace').splitlines():
            fields = line.split('\t')
            if len(fields) != 2 or not SHA.fullmatch(fields[0]) or fields[1] not in REFS or fields[1] in advertised:
                halt_now(f'unexpected ls-remote line {line!r} after a failed fetch')
            advertised[fields[1]] = fields[0]
        missing = [ref for ref in REFS if ref not in advertised]
        if missing:
            halt_now(f'remote is reachable but lacks {missing}; reconcile the remote branches before resuming')
        if recorded is not None and advertised[REFS[1]] != recorded[REFS[1]]:
            halt_now(f'gh-pages on the remote ({advertised[REFS[1]]}) differs from the checkpoint '
                     f'({recorded[REFS[1]]}) after a failed fetch')
        halt_now(f'fetch failed (exit {error.returncode}) although the remote is reachable '
                 f'(advertised={advertised}); cause unknown, reconcile before resuming')
    main_parent, pages_parent = observed

    if recorded is not None:
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

        if x_inbox_repo:
            import_x_inbox(x_inbox_repo, ROOT, env)
        credentials, enabled = source_credentials(state)
        env.update(credentials)
        # Local preflight only: the collectors re-check when they open, and the site shows what was read.
        print(f'source_credentials={",".join(enabled) or "none"}', flush=True)
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
        # Always a new data commit, empty when tg.db is unchanged: then main is a real update too,
        # so the server checks both old values inside one atomic transaction (an unchanged ref
        # would not be sent at all and could move unnoticed). The checkpoint records this commit,
        # which is how the next round recognises it as ours, empty or not.
        main_next = git('commit-tree', data_tree, '-p', main_parent, '-m', 'Refresh public collection data')

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
        if not all(new != old and is_ancestor(old, new) for old, new in zip(observed, upcoming)):
            raise RuntimeError('candidates are not new fast-forwards of the observed refs')
        skip = (f'main advanced normally during this round; nothing published, no HALT, checkpoint unchanged; '
                f'the next round builds on the new main. Built on {observed}')
        # Catch rewinds or unrelated writes already visible before the push. Skipping needs gh-pages
        # at its baseline here and again on re-read, and main on one normal path through both reads.
        advertised = ls_remote()
        if advertised != dict(zip(REFS, observed)):
            if (set(advertised) == set(REFS) and advertised[REFS[1]] == pages_parent
                    and only_main_advanced(main_parent, pages_parent, advertised[REFS[0]])):
                raise Skipped(skip)
            halt_now(f'remote refs moved during collection; observed={observed}, advertised={advertised}, '
                     f'candidate={upcoming}; no push attempted')
        # One atomic push with two real updates, each leased to the exact old value it was built on:
        # the client refuses a ref that already moved, and the server checks both old values in
        # one transaction, so a later move of either ref (including a rewind) refuses the whole push.
        leases = [f'--force-with-lease={ref}:{old}' for ref, old in zip(REFS, observed)]
        refspecs = [f'{new}:{ref}' for ref, new in zip(REFS, upcoming)]
        # Leave this marker on rejection, ambiguous network result or interruption.
        with halt.open('x') as stream:
            stream.write(f'Push started; reconcile before resuming. Parents: {observed}; candidates: {upcoming}\n')
            stream.flush()
            os.fsync(stream.fileno())
        pushed = subprocess.run(['git', 'push', '--atomic', '--porcelain', '--no-follow-tags', *leases,
                                 'origin', *refspecs], cwd=ROOT, env=dict(env, LC_ALL='C'), pass_fds=(lock,),
                                stdout=subprocess.PIPE, timeout=PUSH_TIMEOUT)
        output = pushed.stdout.decode(errors='replace')
        print(output, end='', flush=True)
        if pushed.returncode:
            # Only main refused by its lease (gh-pages merely carried along by --atomic), then a
            # re-read showing gh-pages still at baseline and a normal merge on main, is safe to
            # retry. HALT stays for anything else: gh-pages stale, server-side refusal (including
            # `atomic transaction failed`), disconnect, timeout, hook, truncated or unclear receipt.
            if (pushed.returncode == 1 and main_only_rejection(output, upcoming)
                    and only_main_advanced(main_parent, pages_parent)):
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
            run_cycle(args.code_sha, state, lock.fileno(), os.environ.get(X_INBOX_ENV, ''))
    except Skipped as skipped:
        print(f'Mac publish skipped: {skipped}', file=sys.stderr)
        return SKIPPED
    except (OSError, RuntimeError, ValueError, KeyError, subprocess.SubprocessError) as error:
        print(f'Mac publish failed: {error}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
