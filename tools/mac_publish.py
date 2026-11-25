"""Collect in a detached checkout, publish a validated fast-forward pair once, and
follow main by trial-then-switch: a new main is first built in an isolated trial
after this round's real publish; only a later round switches the checkout to it."""
import argparse
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from urllib.parse import urlsplit


ROOT = Path(__file__).resolve().parents[1]
REFS = ('refs/heads/main', 'refs/heads/gh-pages')
SNAPSHOTS = ('refs/mac-publish/main', 'refs/mac-publish/gh-pages')
PUBLIC_META = 'https://news.kwinweng.com/data/meta.json'
META_PATH = 'rebang/data/meta.json'
TRIAL_TIMEOUT = 1200   # seconds for one whole trial build
TRIAL_ATTEMPTS = 3     # trials per code version before waiting for different code


class TrialFailed(Exception):
    pass


def write_json(path, value):
    temp = path.with_name(path.name + '.next')
    temp.write_text(json.dumps(value, indent=1) + '\n')
    temp.replace(path)


def run_cycle(code_sha, state, lock, trial_timeout=TRIAL_TIMEOUT):
    """Return 'switched' when the checkout moved to a trialled candidate; the caller re-executes."""
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

    def ok(*args):
        return subprocess.run(['git', *args], cwd=ROOT, env=env, stdout=subprocess.DEVNULL,
                              stderr=subprocess.DEVNULL).returncode == 0

    def is_ancestor(old, new):
        return ok('merge-base', '--is-ancestor', old, new)

    def same_code(one, other):
        # Data commits only replace tg.db, so everything else is the code version.
        return ok('diff', '--quiet', one, other, '--', '.', ':(exclude)tg.db')

    halt = state / 'HALT'
    if halt.exists():
        raise RuntimeError(f'HALT exists: {halt}; reconcile the local database and both remote refs before resuming')

    def halt_now(reason):
        with halt.open('x') as stream:
            stream.write(reason + '\n')
        raise RuntimeError(f'{reason}; stopped: {halt}')

    database = ROOT / 'tg.db'
    switch, aside = state / 'switch.json', state / 'tg.db.switching'
    candidate_file, trial_file = state / 'candidate.json', state / 'trial.json'

    def finish_switch():
        """Put the local database back after a code switch, whether it completed, failed or was killed."""
        plan = json.loads(switch.read_text())
        head = git('rev-parse', 'HEAD')
        if head not in (plan['from'], plan['to']):
            raise RuntimeError(f'HEAD {head} is neither side of the recorded code switch {plan}; reconcile manually')
        if aside.exists():
            if os.path.lexists(database):
                # Only a copy Git checked out may be replaced; anything else keeps both files for inspection.
                checked_out = {git('rev-parse', f'{commit}:tg.db') for commit in (plan['from'], plan['to'])}
                if database.is_symlink() or git('hash-object', '--no-filters', str(database)) not in checked_out:
                    raise RuntimeError(f'unexpected tg.db beside {aside} after a code switch; reconcile manually')
            os.replace(aside, database)
        switch.unlink()
        print(f'follow: code switch {plan["from"]} -> {plan["to"]} closed at HEAD={head}', flush=True)

    if switch.exists():
        finish_switch()

    if not re.fullmatch(r'[0-9a-f]{40}', code_sha):
        raise RuntimeError('--code-sha must be a full lowercase commit hash')
    head = git('rev-parse', 'HEAD')
    if (git('branch', '--show-current') or not is_ancestor(code_sha, head)
            or git('diff', '--name-only', 'HEAD', '--', '.', ':(exclude)tg.db')
            or git('diff', '--cached', '--name-only')
            or git('ls-files', '--others', '--exclude-standard')):
        raise RuntimeError('use a dedicated clean detached checkout at --code-sha or a descendant it followed '
                           '(only unstaged tg.db may differ)')
    if (state / 'no-source-credentials').exists():
        raise RuntimeError('the reserved no-source-credentials path must not exist')
    origin = git('remote', 'get-url', 'origin')
    if git('remote', 'get-url', '--push', '--all', 'origin').splitlines() != [origin]:
        raise RuntimeError('origin must have exactly one push URL, identical to the fetch URL')

    def fetch():
        # Snapshots are private scratch refs: force them so a rewritten main reaches the HALT check below.
        git('fetch', '--no-tags', '--refmap=', 'origin',
            *(f'+{source}:{dest}' for source, dest in zip(REFS, SNAPSHOTS)))
        return tuple(git('rev-parse', f'{ref}^{{commit}}') for ref in SNAPSHOTS)

    def normal_advance(old_main, new_main):
        """Someone else fast-forwarded main (a merge, docs included) without touching tg.db or our code's history."""
        def database_blob(commit):
            found = subprocess.run(['git', 'rev-parse', '--verify', '--quiet', f'{commit}:tg.db'], cwd=ROOT, env=env,
                                   stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
            return found.stdout.strip() if found.returncode == 0 else None

        return (new_main != old_main and is_ancestor(old_main, new_main) and is_ancestor(head, new_main)
                and database_blob(old_main) is not None and database_blob(old_main) == database_blob(new_main))

    observed = fetch()
    main_parent, pages_parent = observed
    record = state / 'refs.json'

    def remember(refs):
        temp = state / 'refs.next'
        temp.write_text(json.dumps(dict(zip(REFS, refs))) + '\n')
        temp.replace(record)

    if record.exists():
        recorded = json.loads(record.read_text())
        if recorded != dict(zip(REFS, observed)):
            if recorded.get(REFS[1]) == pages_parent and normal_advance(recorded.get(REFS[0], ''), main_parent):
                print(f'follow: main advanced normally {recorded[REFS[0]]}..{main_parent}', flush=True)
            else:
                halt_now(f'remote refs changed since the last local checkpoint: {observed}')
    elif not is_ancestor(head, main_parent):
        raise RuntimeError('remote main must contain the checked-out code before the first checkpoint')

    def check_database():
        if database.is_symlink() or not database.is_file() or any(
                os.path.lexists(ROOT / f'tg.db{suffix}') for suffix in ('-journal', '-wal', '-shm')):
            raise RuntimeError('tg.db must be a regular file with no SQLite journal/WAL/SHM; preserve it for inspection')

    def record_trial(**fields):
        write_json(trial_file, dict(fields, at=datetime.now(timezone.utc).isoformat()))

    def switch_code(target):
        # Git refuses to switch over a modified tg.db, so the local database waits beside the
        # checkout; switch.json lets the next start put it back after any interruption.
        check_database()
        write_json(switch, {'from': head, 'to': target})
        os.replace(database, aside)
        try:
            git('-c', 'core.hooksPath=/dev/null', 'checkout', '--quiet', '--detach', target)
        except subprocess.CalledProcessError as error:
            finish_switch()
            candidate_file.unlink()
            record_trial(sha=target, base=head, ok=False, attempts=TRIAL_ATTEMPTS,
                         reason=f'checkout failed: {error}')
            raise RuntimeError(f'code switch to {target} failed; kept {head} and dropped the candidate') from None
        finish_switch()
        candidate_file.unlink()
        print(f'follow: switched code {head} -> {target}; restarting with it', flush=True)
        return 'switched'

    def trial(target, baseline, timeout):
        """Build target's code in a throwaway clone from copies of this round's data; never push."""
        deadline = time.monotonic() + timeout
        area = state / 'trial'
        repo = area / 'repo'
        shutil.rmtree(area, ignore_errors=True)
        area.mkdir()
        # launchd stops a job with SIGTERM; turn it into an exception so the trial group is killed.
        previous = signal.signal(signal.SIGTERM, lambda *_: sys.exit(143))
        try:
            with (state / 'trial.log').open('wb') as log:
                def step(*args, cwd=repo, capture=False):
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise TrialFailed(f'timed out after {timeout}s')
                    log.write(f'== {" ".join(map(str, args))}\n'.encode())
                    log.flush()
                    # Own session and no lock fd: a stuck trial can be killed whole and never holds the lock.
                    process = subprocess.Popen(args, cwd=cwd, env=env, stdin=subprocess.DEVNULL,
                                               stdout=subprocess.PIPE if capture else log, stderr=log,
                                               start_new_session=True)
                    try:
                        output, _ = process.communicate(timeout=remaining)
                    except subprocess.TimeoutExpired:
                        raise TrialFailed(f'timed out after {timeout}s in {" ".join(map(str, args[:2]))}') from None
                    finally:
                        if process.poll() is None:
                            os.killpg(process.pid, signal.SIGKILL)
                            process.wait()
                    if capture:
                        log.write(output)
                    if process.returncode:
                        raise TrialFailed(f'{" ".join(map(str, args[:2]))} exited {process.returncode}; '
                                          f'see {state / "trial.log"}')
                    return output

                step('git', 'clone', '--quiet', '--shared', '--no-checkout', str(ROOT), str(repo), cwd=area)
                step('git', '-c', 'core.hooksPath=/dev/null', 'checkout', '--quiet', '--detach', target)
                shutil.copyfile(database, repo / 'tg.db')
                for name in ('media', 'var/rebang'):  # untracked inputs; APFS clones make the copy cheap
                    if (ROOT / name).is_dir():
                        (repo / name).parent.mkdir(parents=True, exist_ok=True)
                        step('cp', '-cR' if sys.platform == 'darwin' else '-R', str(ROOT / name), str(repo / name))
                step(sys.executable, 'pipeline.py')
                step('sh', 'tools/rebang_refresh.sh', '--no-publish')
                v11 = json.loads((repo / 'site-v11/data/meta.json').read_text())
                if v11['fixture'] is not False or v11['counts']['news'] < 1:
                    raise TrialFailed('trial v11 output is empty or a fixture')
                step(sys.executable, 'tools/write_build_info.py')
                if json.loads((repo / 'site/build-info.json').read_text())['source_commit'] != target:
                    raise TrialFailed('trial build-info does not name the trialled code')
                output = step('sh', 'tools/publish_pages.sh', '--dry-run', '--already-built', capture=True).decode()
                prepared = re.search(r'^Pages prepared: files=\d+ sha=([0-9a-f]+) dry-run=1$', output, re.M)
                if not prepared:
                    raise TrialFailed('trial publisher did not report a dry-run commit')
                pack = area / 'pack'
                pack.mkdir()
                step('git', 'archive', '--format=tar', f'--output={area / "pack.tar"}', prepared[1])
                step('tar', '-xf', str(area / 'pack.tar'), '-C', str(pack))
                # The receiver we know (the running code's copy) must accept it on top of what we just published.
                step('bash', str(ROOT / 'deploy/news-sync.sh'), '--source', str(pack), '--target', str(baseline),
                     '--dry-run', '--work-dir', str(area), cwd=area)
        finally:
            signal.signal(signal.SIGTERM, previous)
            shutil.rmtree(area, ignore_errors=True)

    def follow(target, baseline, timeout):
        """Trial main's newer code; success only records a candidate that the next round switches to."""
        last = json.loads(trial_file.read_text()) if trial_file.exists() else {}
        attempts = 1
        if (not last.get('ok') and last.get('sha') and ok('cat-file', '-e', f'{last["sha"]}^{{commit}}')
                and same_code(last['sha'], target)):
            attempts = last.get('attempts', TRIAL_ATTEMPTS) + 1
            if attempts > TRIAL_ATTEMPTS:
                print(f'follow: keeping {head}; trials of {target} code failed {TRIAL_ATTEMPTS} times, '
                      f'last: {last.get("reason")}', flush=True)
                return
        # Count the attempt first, so a trial that kills the whole process cannot repeat forever.
        record_trial(sha=target, base=head, ok=False, attempts=attempts, reason='interrupted before finishing')
        print(f'follow: trial {attempts}/{TRIAL_ATTEMPTS} of {target} started', flush=True)
        try:
            trial(target, baseline, timeout)
        except TrialFailed as error:
            reason = str(error)
        except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as error:
            reason = f'{type(error).__name__}: {error}'
        else:
            write_json(candidate_file, {'sha': target, 'base': head})
            record_trial(sha=target, base=head, ok=True, attempts=attempts, reason='')
            print(f'follow: trial passed for {target}; the next round switches to it', flush=True)
            return
        record_trial(sha=target, base=head, ok=False, attempts=attempts, reason=reason)
        print(f'follow: trial FAILED for {target}; keeping {head} and publishing as usual: {reason}', flush=True)

    # One switch per start: a restarted run publishes with what it has.
    if candidate_file.exists() and not os.environ.get('MAC_PUBLISH_RESTARTED'):
        target = json.loads(candidate_file.read_text())['sha']
        if target != head and is_ancestor(head, target) and is_ancestor(target, main_parent):
            return switch_code(target)
        print(f'follow: dropped candidate {target}; it is the running code or no longer between it and main',
              flush=True)
        candidate_file.unlink()

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
        if info['source_commit'] != head or info['database_sha256'] != db_sha:
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
        skip = 'main advanced normally during this round; nothing was published, the next round builds on it'

        def only_main_advanced():
            # Our atomic pair never landed if gh-pages is still the parent; main may only have
            # moved by a normal merge on top of the parent we built on.
            main_now, pages_now = fetch()
            return pages_now == pages_parent and normal_advance(main_parent, main_now)

        # Normal Git push detects changes after its own advertisement; this also
        # catches rewinds or unrelated writes already visible before that push.
        advertised = dict(line.split('\t')[::-1] for line in git('ls-remote', '--refs', 'origin', *REFS).splitlines())
        if advertised != dict(zip(REFS, observed)):
            if only_main_advanced():
                raise RuntimeError(skip)
            halt_now(f'remote refs moved during collection; observed={observed}, candidate={upcoming}; no push attempted')
        refspecs = [f'{new}:{ref}' for ref, old, new in zip(REFS, observed, upcoming) if new != old]
        # Leave this marker on rejection, ambiguous network result or interruption.
        with halt.open('x') as stream:
            stream.write(f'Push started; reconcile before resuming. Parents: {observed}; candidates: {upcoming}\n')
        try:
            run('git', 'push', '--atomic', '--no-follow-tags', 'origin', *refspecs)
        except subprocess.CalledProcessError:
            # A merge between ls-remote and push is a clean non-fast-forward rejection. Anything
            # else, including a failed re-fetch, keeps HALT.
            if only_main_advanced():
                halt.unlink()
                raise RuntimeError(skip) from None
            raise
        remember(upcoming)
        halt.unlink()
        print(f'published main={main_next} gh-pages={pages_next} database_sha256={db_sha}', flush=True)

        # Publishing is done; a trial can no longer delay or block it.
        if not same_code(head, main_parent):
            follow(main_parent, candidate, trial_timeout)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--code-sha', required=True,
                        help='full hash of the approved code; the checkout is it or a descendant it followed')
    parser.add_argument('--trial-timeout', type=int, default=TRIAL_TIMEOUT, help='seconds for one trial build')
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
            result = run_cycle(args.code_sha, state, lock.fileno(), args.trial_timeout)
        if result == 'switched':
            # The lock is released; start this round again with the switched code's own entry point.
            # A competing start may take the lock first; then this one just reports it as busy.
            sys.stdout.flush()
            os.execve('/bin/sh', ['/bin/sh', str(ROOT / 'tools/mac_publish.sh'), *sys.argv[1:]],
                      dict(os.environ, MAC_PUBLISH_RESTARTED='1'))
    except (OSError, RuntimeError, ValueError, KeyError, subprocess.CalledProcessError) as error:
        print(f'Mac publish failed: {error}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
