"""Installed Mac publisher entry point. Keep this file outside the changing clone.

Worker v1: /bin/sh mac_publish.sh --worker-v1 LOCK_FD SOCKET_FD MAIN PAGES
in the dedicated clone. The worker sends b'1' when ready, then waits for b'G'
before touching the checkout, state or remote. EOF cancels the startup.
"""
import argparse
import fcntl
import json
import math
import os
from pathlib import Path
import re
import signal
import socket
import subprocess
import sys
import tempfile
import time


REFS = ('refs/heads/main', 'refs/heads/gh-pages')
SNAPSHOTS = ('refs/mac-publish/main', 'refs/mac-publish/gh-pages')
FETCH_SPECS = tuple(f'+{source}:{dest}' for source, dest in zip(REFS, SNAPSHOTS))
LEGACY_ENTRY = ('tools/mac_publish.sh', 'tools/mac_publish_launcher.py')


def stop_group(process):
    # Kill descendants even if the group's original process has already exited.
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    except PermissionError:
        # Darwin reports EPERM for a group containing only an unreaped zombie.
        if process.poll() is None:
            raise
    process.wait()


def positive_seconds(text):
    seconds = float(text)
    if not math.isfinite(seconds) or seconds <= 0:
        raise argparse.ArgumentTypeError('timeout must be finite and positive')
    return seconds


def launch(root, state, lock, preflight_timeout, startup_timeout, legacy_entry):
    startup_env = {key: os.environ[key] for key in ('PATH', 'HOME', 'TMPDIR', 'SSH_AUTH_SOCK') if key in os.environ}
    startup_env['BOX_PYTHON'] = sys.executable
    git_env = dict(startup_env, GIT_TERMINAL_PROMPT='0', GIT_SSH_COMMAND='ssh -o BatchMode=yes', GIT_OPTIONAL_LOCKS='0')
    halt = state / 'HALT'
    if os.path.lexists(halt):
        raise RuntimeError(f'HALT exists: {halt}; reconcile the local database and both remote refs before resuming')

    def halt_now(reason):
        with halt.open('x') as stream:
            stream.write(reason + '\n')
        raise RuntimeError(f'{reason}; stopped: {halt}')

    def git(*args, **kwargs):
        return subprocess.run(('git', *args), cwd=root, env=git_env, pass_fds=(lock,),
                              check=True, stdout=subprocess.PIPE, **kwargs).stdout.decode().strip()

    def remote_refs():
        return dict(line.split('\t')[::-1] for line in git('ls-remote', '--refs', 'origin', *REFS).splitlines())

    def check_remote(expected):
        actual = remote_refs()
        if actual != expected:
            halt_now(f'remote refs moved during code switch; expected={expected}, actual={actual}; no push attempted')

    def fetch(*specs, deepen=None):
        args = () if deepen is None else (f'--deepen={deepen}',)
        try:
            git('fetch', '--no-tags', '--refmap=', *args, 'origin', *specs)
        except subprocess.CalledProcessError:
            missing = set(REFS) - remote_refs().keys()
            if missing:
                halt_now(f'remote refs missing: {sorted(missing)}')
            raise

    def read_state(name):
        path = state / name
        return json.loads(path.read_text()) if path.exists() else None

    def save_state(name, data):
        temp = state / f'{name}.next'
        temp.write_text(json.dumps(data) + '\n')
        temp.replace(state / name)

    def commit_id(sha):
        if not isinstance(sha, str) or not re.fullmatch(r'[0-9a-f]{40}|[0-9a-f]{64}', sha):
            raise ValueError('invalid commit ID in publisher state')
        return sha

    def check_checkout():
        # The publisher cannot distinguish half-written files from operator edits or
        # tell whether a non-publisher Git process owns this lock. Never force/reset.
        if os.path.lexists(root / '.git/index.lock'):
            raise RuntimeError('Git index.lock exists; preserve checkout evidence and inspect under the publisher lock')
        if (git('branch', '--show-current')
                or git('diff', '--name-only', 'HEAD', '--', '.', ':(exclude)tg.db')
                or git('diff', '--cached', '--name-only')
                or git('ls-files', '--others', '--exclude-standard')):
            raise RuntimeError('use a dedicated clean detached checkout (only unstaged tg.db may differ)')

    database = root / 'tg.db'
    saved_database = state / 'checkout-tg.db'

    def check_database(path):
        if path.is_symlink() or not path.is_file() or any(
                os.path.lexists(root / f'tg.db{suffix}') for suffix in ('-journal', '-wal', '-shm')):
            raise RuntimeError(f'{path.name} must be a regular file with no SQLite journal/WAL/SHM; preserve it for inspection')

    check_checkout()
    if os.path.lexists(saved_database):
        check_database(saved_database)
        saved_database.replace(database)
        print('restored local tg.db after an interrupted checkout', flush=True)
    check_database(database)
    if os.path.lexists(state / 'no-source-credentials'):
        raise RuntimeError('the reserved no-source-credentials path must not exist')
    origin = git('remote', 'get-url', 'origin')
    if git('remote', 'get-url', '--push', '--all', 'origin').splitlines() != [origin]:
        raise RuntimeError('origin must have exactly one push URL, identical to the fetch URL')

    head = git('rev-parse', 'HEAD')
    checkpoint = read_state('refs.json')
    boot = read_state('boot.json')
    # On first install the operator has already approved the detached starting HEAD.
    good = commit_id(boot['good']) if boot is not None else head
    bad = commit_id(boot['bad']) if boot is not None and boot['bad'] is not None else None
    fetch(*FETCH_SPECS)
    main, pages = (git('rev-parse', f'{ref}^{{commit}}') for ref in SNAPSHOTS)
    observed = dict(zip(REFS, (main, pages)))
    if checkpoint is not None and checkpoint[REFS[1]] != pages:
        halt_now(f'gh-pages changed since the last local checkpoint: {checkpoint[REFS[1]]} -> {pages}')

    def is_ancestor(base):
        result = subprocess.run(('git', 'merge-base', '--is-ancestor', base, main), cwd=root, env=git_env,
                                capture_output=True)
        return result.returncode == 0

    # A shallow clone can say 'not ancestor' even when both commits exist. Prove
    # ancestry, deepening only main on demand, and never accept an unproven jump.
    bases = dict.fromkeys(sha for sha in (head, good, checkpoint[REFS[0]] if checkpoint is not None else None, bad)
                          if sha is not None)
    for deepen in (50, 150, 300, None):
        missing_proof = [commit_id(base) for base in bases if not is_ancestor(commit_id(base))]
        if not missing_proof:
            break
        shallow = git('rev-parse', '--is-shallow-repository') == 'true'
        if not shallow or deepen is None:
            detail = ' (shallow history: ancestry not proven after bounded deepening)' if shallow else ''
            halt_now(f'main is not a fast-forward: {missing_proof} -> {main}{detail}')
        fetch(FETCH_SPECS[0], deepen=deepen)
        if git('rev-parse', SNAPSHOTS[0]) != main:
            halt_now(f'remote refs moved during code switch while deepening main {main}')

    if legacy_entry and git('diff-tree', '--name-only', '-r', head, main, '--', *LEGACY_ENTRY):
        raise RuntimeError(f'candidate {main} changes the legacy entry; install the fixed launcher before switching')

    def database_blob(commit):
        entry = git('ls-tree', commit, '--', 'tg.db').split()
        if entry[:2] != ['100644', 'blob']:
            raise RuntimeError(f'{commit} must track tg.db as a regular 100644 blob')
        return entry[2]

    with tempfile.TemporaryDirectory(prefix='boot-', dir=state) as name:
        work = Path(name)
        pending_db = work / 'tg.db'

        def copy_blob(blob):
            with pending_db.open('wb') as output:
                subprocess.run(('git', 'cat-file', 'blob', blob), cwd=root, env=git_env, check=True,
                               pass_fds=(lock,), stdout=output)

        def switch_checkout(target):
            if head == target:
                return
            if database_blob(head) != database_blob(target):
                # Checkout needs the old tracked version. The original file is
                # stored outside the temp dir and survives uncatchable signals.
                copy_blob(database_blob(head))
                database.replace(saved_database)
            try:
                if saved_database.exists():
                    pending_db.replace(database)
                git('checkout', '--detach', '--no-overwrite-ignore', target)
            finally:
                if saved_database.exists():
                    check_checkout()
                    saved_database.replace(database)
            print(f'code switched: {head} -> {target}', flush=True)

        main_blob = database_blob(main)
        current_blob = git('hash-object', '--no-filters', str(database))
        if checkpoint is not None and checkpoint[REFS[0]] != main:
            previous_blob = database_blob(checkpoint[REFS[0]])
            if main_blob != previous_blob and current_blob != main_blob:
                remote_copy = state / f'remote-tg-{main}.db'
                copy_blob(main_blob)
                pending_db.replace(remote_copy)
                halt_now(f'remote tg.db changed: checkpoint={previous_blob}, candidate={main_blob}, '
                         f'local={current_blob}, main={main}; kept {database} and {remote_copy}')
        if checkpoint is None and current_blob not in (main_blob, database_blob(head)):
            raise RuntimeError('unrecognized local tg.db at initialization; do not overwrite it')

        def reject(stage, error):
            # Persist rejection before a possible rollback. Do not run old code
            # to publish against a remote whose newest code failed to start.
            save_state('boot.json', dict(good=good, bad=main))
            switch_checkout(good)
            raise RuntimeError(f'publisher {stage} failed for candidate {main}: {error}; retained known-good {good}')

        if main == bad:
            switch_checkout(good)
            raise RuntimeError(f'skipping rejected candidate {bad}; waiting for a newer main (known-good {good})')

        launcher = work / 'mac_publish.sh'
        worker = work / 'mac_publish.py'
        deadline = time.monotonic() + preflight_timeout

        def preflight(*args, env=startup_env, stdout=None):
            process = subprocess.Popen(args, cwd=root, env=env, stdout=stdout, start_new_session=True)
            try:
                result = process.wait(timeout=max(0, deadline - time.monotonic()))
                if result:
                    raise subprocess.CalledProcessError(result, args)
            except BaseException:
                stop_group(process)
                raise

        try:
            for path in (launcher, worker):
                with path.open('wb') as output:
                    preflight('git', 'show', f'{main}:tools/{path.name}', env=git_env, stdout=output)
            preflight('/bin/sh', '-n', str(launcher))
            preflight(sys.executable, '-I', '-m', 'py_compile', str(worker))
            preflight(sys.executable, '-I', '-c', 'import runpy, sys; runpy.run_path(sys.argv[1])', str(worker))
        except (OSError, subprocess.SubprocessError) as error:
            reject('preflight', error)

        # The worker cannot publish before GO. The fixed launcher retains the
        # lock until exit; the inherited copy also protects an in-flight publish
        # if the launcher is killed before it can clean up.
        parent, child = socket.socketpair()
        with parent, child:
            try:
                process = subprocess.Popen(('/bin/sh', str(launcher), '--worker-v1', str(lock), str(child.fileno()),
                                            main, pages), cwd=root, env=startup_env, start_new_session=True,
                                           pass_fds=(lock, child.fileno()))
            except OSError as error:
                reject('boot', error)
            try:
                child.close()
                parent.settimeout(startup_timeout)
                try:
                    if parent.recv(1) != b'1' or process.poll() is not None:
                        raise RuntimeError('worker did not acknowledge the v1 protocol')
                except (OSError, RuntimeError) as error:
                    stop_group(process)
                    reject('boot', error)

                check_remote(observed)
                # Persist the rollback anchor before changing the checkout.
                if boot is None:
                    save_state('boot.json', dict(good=good, bad=None))
                if checkpoint is None and current_blob != main_blob:
                    copy_blob(main_blob)
                    pending_db.replace(database)
                switch_checkout(main)
                check_remote(observed)
                if checkpoint != observed:
                    save_state('refs.json', observed)
                save_state('boot.json', dict(good=main, bad=None))
                parent.sendall(b'G')
                return process.wait()
            finally:
                if process.returncode is None:
                    stop_group(process)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--legacy-entry', action='store_true', help=argparse.SUPPRESS)
    parser.add_argument('--code-sha', help='accepted for compatibility with existing launchd plists')
    parser.add_argument('--preflight-timeout', type=positive_seconds, default=30, metavar='SECONDS')
    parser.add_argument('--startup-timeout', type=positive_seconds, default=30, metavar='SECONDS')
    args = parser.parse_args()
    root = Path.cwd().resolve()
    state = root / '.git/mac-publish'

    def interrupted(signum, _frame):
        raise RuntimeError(f'launcher interrupted by signal {signum}')

    for signum in (signal.SIGHUP, signal.SIGINT, signal.SIGTERM):
        signal.signal(signum, interrupted)
    try:
        if not (root / '.git').is_dir() or any(key.startswith('GIT_') for key in os.environ):
            raise RuntimeError('use a dedicated clone without inherited Git environment variables')
        os.umask(0o077)
        state.mkdir(mode=0o700, exist_ok=True)
        with (state / 'lock').open('a') as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise RuntimeError('Mac publisher is already running') from None
            return launch(root, state, lock.fileno(), args.preflight_timeout, args.startup_timeout, args.legacy_entry)
    except (OSError, RuntimeError, ValueError, KeyError, subprocess.SubprocessError) as error:
        print(f'Mac publish failed: {error}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
