"""Installed Mac publisher entry point. Keep this file outside the changing clone.

Worker v1: /bin/sh mac_publish.sh --worker-v1 LOCK_FD SOCKET_FD MAIN PAGES
in the dedicated clone. The worker sends b'1+' when ready, acknowledges b'G'
with b'A', and waits for b'C' (checkpoints saved). EOF cancels startup.
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


def supervise_worker(control, lock, socket_fd, launcher, main, pages):
    # This process is the group leader and holds the read end of a launcher-only
    # pipe. Even SIGKILL of the launcher closes the pipe and kills stalled code.
    control, lock, socket_fd = map(int, (control, lock, socket_fd))
    process = subprocess.Popen(('/bin/sh', launcher, '--worker-v1', str(lock), str(socket_fd), main, pages),
                               pass_fds=(lock, socket_fd))
    os.close(socket_fd)
    os.close(lock)
    if os.read(control, 1) != b'C':
        os.killpg(os.getpgrp(), signal.SIGKILL)
    os.close(control)
    status = process.wait()
    return 128 - status if status < 0 else status


def positive_seconds(text):
    seconds = float(text)
    if not math.isfinite(seconds) or seconds <= 0:
        raise argparse.ArgumentTypeError('timeout must be finite and positive')
    return seconds


def launch(root, state, lock, preflight_timeout, startup_timeout, legacy_entry):
    startup_env = {key: os.environ[key] for key in ('PATH', 'HOME', 'TMPDIR', 'SSH_AUTH_SOCK') if key in os.environ}
    startup_env['BOX_PYTHON'] = sys.executable
    git_env = dict(startup_env, GIT_TERMINAL_PROMPT='0', GIT_OPTIONAL_LOCKS='0')
    startup_deadline = None
    halt = state / 'HALT'
    if os.path.lexists(halt):
        raise RuntimeError(f'HALT exists: {halt}; reconcile the local database and both remote refs before resuming')

    def halt_now(reason):
        with halt.open('x') as stream:
            stream.write(reason + '\n')
        raise RuntimeError(f'{reason}; stopped: {halt}')

    def time_left():
        remaining = startup_deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError('publisher startup timed out')
        return remaining

    def run_git(*args, stdout=subprocess.PIPE):
        command = ('git', *args)
        options = dict(cwd=root, env=git_env, pass_fds=(lock,), stdout=stdout)
        if startup_deadline is None:
            return subprocess.run(command, check=True, **options).stdout
        time_left()
        process = subprocess.Popen(command, start_new_session=True, **options)
        try:
            output, _ = process.communicate(timeout=time_left())
        except BaseException:
            stop_group(process)
            raise
        if process.returncode:
            raise subprocess.CalledProcessError(process.returncode, command)
        return output

    def git(*args):
        return run_git(*args).decode().strip()

    try:
        git('config', '--get', 'core.sshCommand')
    except subprocess.CalledProcessError as error:
        if error.returncode != 1:
            raise
        git_env['GIT_SSH_COMMAND'] = 'ssh -o BatchMode=yes'

    def remote_refs():
        return dict(line.split('\t')[::-1] for line in git('ls-remote', '--refs', 'origin', *REFS).splitlines())

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

    def recover_database(*, interrupted=True):
        check_checkout()
        if os.path.lexists(saved_database):
            check_database(saved_database)
            saved_database.replace(database)
            if interrupted:
                print('restored local tg.db after an interrupted checkout', flush=True)
        check_database(database)

    recover_database()
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

    def check_remote():
        actual = remote_refs()
        if actual == observed:
            return True
        candidate = actual.get(REFS[0])
        if candidate and candidate != main and actual.get(REFS[1]) == pages:
            try:
                git('fetch', '--no-tags', '--refmap=', '--no-write-fetch-head', 'origin', REFS[0])
                git('merge-base', '--is-ancestor', main, candidate)
                same_database = database_blob(main) == database_blob(candidate)
                if same_database and remote_refs() == actual:
                    print(f'publish deferred: main fast-forward {main} -> {candidate}; retry next cycle', flush=True)
                    return False
            except (RuntimeError, subprocess.CalledProcessError):
                pass  # A fast-forward with the same database was not proven.
        halt_now(f'remote refs moved during code switch; expected={observed}, actual={actual}; no push attempted')

    with tempfile.TemporaryDirectory(prefix='boot-', dir=state) as name:
        work = Path(name)
        pending_db = work / 'tg.db'

        def copy_blob(blob):
            with pending_db.open('wb') as output:
                run_git('cat-file', 'blob', blob, stdout=output)

        def switch_checkout(target):
            current = git('rev-parse', 'HEAD')
            if current == target:
                return
            if database_blob(current) != database_blob(target):
                # Checkout needs the old tracked version. The original file is
                # stored outside the temp dir and survives uncatchable signals.
                copy_blob(database_blob(current))
                database.replace(saved_database)
            try:
                if saved_database.exists():
                    pending_db.replace(database)
                git('checkout', '--detach', '--no-overwrite-ignore', target)
            finally:
                if saved_database.exists() and (startup_deadline is None or time.monotonic() < startup_deadline):
                    recover_database(interrupted=False)
            print(f'code switched: {current} -> {target}', flush=True)

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
            nonlocal startup_deadline
            startup_deadline = None
            # Persist rejection before a possible rollback. Do not run old code
            # to publish against a remote whose newest code failed to start.
            save_state('boot.json', dict(good=good, bad=main))
            try:
                recover_database()
                switch_checkout(good)
            except (OSError, RuntimeError, subprocess.SubprocessError) as rollback_error:
                raise RuntimeError(f'publisher {stage} failed for candidate {main}: {error}; '
                                   f'rollback blocked: {rollback_error}') from rollback_error
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

        # The worker cannot publish before C. The supervisor owns its group
        # until then, so a dead launcher cannot leave an unapproved lock holder.
        parent, child = socket.socketpair()
        control_read, control_write = os.pipe()
        seed_backup = work / 'initial-tg.db'
        saved_checkpoint = False

        class StartupError(RuntimeError):
            pass

        def receive(expected, message):
            parent.settimeout(time_left())
            if parent.recv(1) != expected:
                raise StartupError(message)

        with parent, child, os.fdopen(control_read, 'rb') as control_in, os.fdopen(control_write, 'wb', buffering=0) as control:
            startup_deadline = time.monotonic() + startup_timeout
            worker_env = dict(startup_env, MAC_PUBLISH_ACK='1')
            try:
                process = subprocess.Popen((sys.executable, '-I', str(Path(__file__).resolve()),
                                            '--supervise-worker', str(control_in.fileno()), str(lock), str(child.fileno()),
                                            str(launcher), main, pages), cwd=root, env=worker_env, start_new_session=True,
                                           pass_fds=(control_in.fileno(), lock, child.fileno()))
            except OSError as error:
                reject('boot', error)
            try:
                child.close()
                control_in.close()
                try:
                    receive(b'1', 'worker did not become ready')
                    receive(b'+', 'worker does not support the startup acknowledgement')

                    if not check_remote():
                        return 0
                    # Persist the rollback anchor before changing the checkout.
                    if boot is None:
                        save_state('boot.json', dict(good=good, bad=None))
                    switch_checkout(main)
                    if not check_remote():
                        stop_group(process)
                        startup_deadline = None
                        switch_checkout(head)
                        return 0
                    parent.settimeout(time_left())
                    parent.sendall(b'G')
                    receive(b'A', 'worker did not acknowledge GO')

                    if checkpoint is None and current_blob != main_blob:
                        copy_blob(main_blob)
                        os.link(database, seed_backup)
                        pending_db.replace(database)
                    if checkpoint != observed:
                        save_state('refs.json', observed)
                        saved_checkpoint = True
                    save_state('boot.json', dict(good=main, bad=None))
                    parent.settimeout(time_left())
                    parent.sendall(b'C')
                except (OSError, StartupError, subprocess.TimeoutExpired) as error:
                    stop_group(process)
                    if seed_backup.exists():
                        seed_backup.replace(database)
                    if saved_checkpoint:
                        if checkpoint is None:
                            (state / 'refs.json').unlink()
                        else:
                            save_state('refs.json', checkpoint)
                    reject('boot', error)
                control.write(b'C')
                control.close()
                return process.wait()
            finally:
                if process.returncode is None:
                    stop_group(process)


def main():
    if sys.argv[1:2] == ['--supervise-worker']:
        return supervise_worker(*sys.argv[2:])
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
