"""Import new X export batches from a read-only private Git inbox into var/rebang/x-dump.

Called by tools/mac_publish.py once per round, before collection, only when REBANG_X_INBOX_REPO
is set. Each round makes one fresh shallow bare clone inside a work directory that the publisher
creates and cleans up under a single deadline; there is no long-lived Git cache to repair after a crash.

Inbox layout (branch main): dumps/<dump_id>.json (manifest) + dumps/<dump_id>.tar.gz (bundle),
optionally README.md at the root. Nothing else. See docs/rebang-v1/X-INBOX.md.

pull() never raises for inbox problems: it returns one error code. Nothing here writes to the inbox.
"""
import ctypes
from datetime import datetime, timedelta, timezone
import errno
import gzip
import hashlib
import io
import json
import os
from pathlib import Path
import re
import resource
import selectors
import shutil
import signal
import subprocess
import sys
import tarfile
import tempfile
import time
from urllib.parse import urlsplit
import zlib


def _watch_worker(end, publisher_pid):
    """Stay responsive even while the receiver is blocked in filesystem or Git I/O."""
    # Popen(start_new_session=True) did setsid(); the PID is also the process group ID.
    group = os.getpid()
    if os.getpgrp() != group:
        raise RuntimeError('receiver requires its own process group')
    receiver = os.fork()
    if not receiver:
        return  # receiver and Git stay in this group; both Python processes hold the publisher lock
    while True:
        exited, status = os.waitpid(receiver, os.WNOHANG)
        left = end - time.monotonic()
        if left <= 0 or os.getppid() != publisher_pid:
            os.killpg(group, signal.SIGKILL)
        if exited:
            os._exit(0 if status == 0 else 1)
        time.sleep(min(0.1, left))


if __name__ == '__main__':
    _WORKER_END = float(sys.argv[2])
    _watch_worker(_WORKER_END, int(sys.argv[3]))

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))  # pinned code checkout only; the publisher runs with -I
from rebang.bloggers import X_STALE_HOURS  # noqa: E402
from rebang.bloggers.x import dump_files, read_export  # noqa: E402


MIB = 1024 * 1024
MIN_FREE = 1024 * MIB         # skip the round when the x-dump filesystem has less free space
DOWNLOAD_LIMIT = 48 * MIB     # hard per-file size limit (RLIMIT_FSIZE) on every Git process
MAX_MANIFEST = 64 * 1024
MAX_BUNDLE = 5 * MIB
MAX_TAR = 32 * MIB            # decompressed, headers and padding included
MAX_MEMBER = 8 * MIB
MAX_MEMBERS = 128
MAX_TREE_ENTRIES = 64
MAX_TREE_BYTES = 8 * 1024     # room for 64 allowed paths even with SHA-256 object IDs
WORK_PREFIX = '.x-inbox-work-'
KEEP = 2                      # total entries allowed in x-dump
OWNER_MARKER = '.x-inbox-owned'
DUMP_ID = re.compile(r'[0-9]{8}T[0-9]{4}')
TREE_PATH = re.compile(r'dumps/([0-9]{8}T[0-9]{4})\.(json|tar\.gz)')
MEMBER_NAME = re.compile(r'[A-Za-z0-9_][A-Za-z0-9_.-]{0,94}\.json')
SHA256 = re.compile(r'[0-9a-f]{64}')
BEIJING = timezone(timedelta(hours=8))


class InboxError(Exception):
    def __init__(self, code):
        super().__init__(code)
        self.code = code


class Deadline:
    def __init__(self, end, *, worker=False):
        self.end = end
        self.worker = worker

    def left(self):
        left = self.end - time.monotonic()
        if left <= 0:
            raise InboxError('x_inbox_timeout')
        return left


def _limit_child(limit):
    def apply():
        # Ignored SIGXFSZ makes an oversized write fail with EFBIG instead of dumping core.
        signal.signal(signal.SIGXFSZ, signal.SIG_IGN)
        resource.setrlimit(resource.RLIMIT_FSIZE, (limit, limit))
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    return apply


def _tree_output(pipe, deadline):
    data = bytearray()
    entries = 0
    with selectors.DefaultSelector() as selector:
        selector.register(pipe, selectors.EVENT_READ)
        while True:
            if not selector.select(deadline.left()):
                raise InboxError('x_inbox_timeout')
            chunk = os.read(pipe.fileno(), min(4096, MAX_TREE_BYTES + 1 - len(data)))
            if not chunk:
                return data
            entries += chunk.count(b'\0')
            data.extend(chunk)
            if len(data) > MAX_TREE_BYTES or entries > MAX_TREE_ENTRIES:
                raise InboxError('x_inbox_layout')


def git(args, *, env, deadline, limit, cwd=None, tree=False):
    """Bound Git's disk writes and discard stderr, which may contain credential hints."""
    command = ['git', '-c', 'protocol.allow=never', '-c', 'protocol.file.allow=always',
               '-c', 'protocol.https.allow=always', '-c', 'protocol.ssh.allow=always',
               '-c', 'credential.interactive=false', '-c', 'core.hooksPath=/dev/null',
               '-c', 'fetch.unpackLimit=1', '-c', 'transfer.unpackLimit=1',
               '-c', 'http.lowSpeedLimit=1000', '-c', 'http.lowSpeedTime=30', *args]
    child_env = dict(env, GIT_TERMINAL_PROMPT='0', LC_ALL='C',
                     GIT_SSH_COMMAND='ssh -o BatchMode=yes -o ControlMaster=no -o ControlPath=none '
                                     '-o ConnectTimeout=20 -o ServerAliveInterval=15 -o ServerAliveCountMax=2')
    deadline.left()
    process = subprocess.Popen(command, cwd=cwd, env=child_env, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                               stderr=subprocess.DEVNULL, start_new_session=not deadline.worker,
                               preexec_fn=_limit_child(limit))
    try:
        if tree:
            output = _tree_output(process.stdout, deadline)
            process.wait(timeout=deadline.left())
        else:
            output, _ = process.communicate(timeout=deadline.left())
    except subprocess.TimeoutExpired:
        raise InboxError('x_inbox_timeout') from None
    finally:
        if process.returncode is None:
            try:
                if deadline.worker:
                    process.kill()  # the publisher supervises the whole worker group
                else:
                    os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            except PermissionError:
                # macOS can report EPERM for a group whose leader just exited.
                process.kill()
        process.stdout.close()
        if process.returncode is None:
            process.wait()
    if process.returncode:
        raise InboxError('x_inbox_fetch_failed')
    return output


def parse_json(raw):
    try:
        return json.loads(raw.decode('utf-8'), parse_constant=_reject_constant)
    except (ValueError, RecursionError):
        raise InboxError('x_inbox_invalid_batch') from None


def _reject_constant(_value):
    raise ValueError('non-JSON constant')


def _timestamp(raw):
    try:
        stamp = datetime.fromisoformat(raw)
        if stamp.tzinfo is not None:
            return stamp.astimezone(timezone.utc)
    except (TypeError, ValueError, OverflowError):
        pass
    raise InboxError('x_inbox_invalid_batch')


def read_tree(clone, *, env, deadline, limit):
    """Exact layout check from tree metadata only (nothing is checked out). Returns
    {dump_id: {'json': (blob, size), 'tar.gz': (blob, size)}}."""
    listing = git(['--git-dir', str(clone), 'ls-tree', '-r', '-t', '-z', '--long', '--full-tree', 'HEAD'],
                  env=env, deadline=deadline, limit=limit, tree=True)
    if listing and not listing.endswith(b'\0'):
        raise InboxError('x_inbox_layout')
    batches, seen = {}, set()
    for entry in listing.split(b'\0')[:-1]:
        info, _, raw_path = entry.partition(b'\t')
        fields = info.split()
        try:
            path = raw_path.decode('ascii')
        except UnicodeDecodeError:
            raise InboxError('x_inbox_layout') from None
        if path in seen or len(fields) != 4:
            raise InboxError('x_inbox_layout')
        seen.add(path)
        if path == 'dumps' and fields[:2] == [b'040000', b'tree']:
            continue
        # Regular non-executable blobs only: no symlinks, submodules or other trees.
        if fields[:2] != [b'100644', b'blob']:
            raise InboxError('x_inbox_layout')
        if path == 'README.md':
            continue
        match = TREE_PATH.fullmatch(path)
        if not match:
            raise InboxError('x_inbox_layout')
        batches.setdefault(match[1], {})[match[2]] = (fields[2].decode('ascii'), int(fields[3]))
    if bool(batches) != ('dumps' in seen) or any(set(parts) != {'json', 'tar.gz'} for parts in batches.values()):
        raise InboxError('x_inbox_layout')  # no stray dumps tree or unpaired manifests/bundles
    return batches


def read_blob(clone, blob, size, maximum, *, env, deadline, limit):
    if size > maximum:
        raise InboxError('x_inbox_too_large')
    data = git(['--git-dir', str(clone), 'cat-file', 'blob', blob], env=env, deadline=deadline, limit=limit)
    if len(data) != size:
        raise InboxError('x_inbox_fetch_failed')
    return data


def extract_members(bundle, output):
    """Plain USTAR regular files only, read from raw headers (tarfile never extracts anything)."""
    try:
        with gzip.GzipFile(fileobj=io.BytesIO(bundle)) as stream:
            raw = stream.read(MAX_TAR + 1)
    except (OSError, EOFError, zlib.error):
        raise InboxError('x_inbox_invalid_batch') from None
    if len(raw) > MAX_TAR:
        raise InboxError('x_inbox_too_large')
    names, pos = {}, 0
    while pos + 512 <= len(raw):
        header = raw[pos:pos + 512]
        if header == tarfile.NUL * 512:
            if len(raw) - pos < 1024 or len(raw) % 512 or raw.count(0, pos) != len(raw) - pos:
                raise InboxError('x_inbox_invalid_batch')
            return sorted(names.values())
        try:
            item = tarfile.TarInfo.frombuf(header, 'ascii', 'strict')
        except (tarfile.HeaderError, ValueError):
            raise InboxError('x_inbox_invalid_batch') from None
        if (item.type not in (tarfile.REGTYPE, tarfile.AREGTYPE) or header[257:265] != tarfile.POSIX_MAGIC
                or not MEMBER_NAME.fullmatch(item.name) or item.name.lower() in names):
            raise InboxError('x_inbox_invalid_batch')
        if len(names) >= MAX_MEMBERS or not 0 <= item.size <= MAX_MEMBER:
            raise InboxError('x_inbox_too_large')
        start = pos + 512
        pos = start + ((item.size + 511) // 512) * 512
        if pos > len(raw):
            raise InboxError('x_inbox_invalid_batch')
        contents = raw[start:start + item.size]
        parse_json(contents)
        (output / item.name).write_bytes(contents)
        names[item.name.lower()] = item.name
    raise InboxError('x_inbox_invalid_batch')


def validate(dump_id, manifest_raw, bundle, staging, now):
    """Everything is checked before the batch becomes visible. Returns the main post count."""
    manifest = parse_json(manifest_raw)
    if not isinstance(manifest, dict) or manifest.get('dump_id') != dump_id:
        raise InboxError('x_inbox_invalid_batch')
    sha256 = manifest.get('sha256')
    if not isinstance(sha256, str) or not SHA256.fullmatch(sha256):
        raise InboxError('x_inbox_invalid_batch')
    if sha256 != hashlib.sha256(bundle).hexdigest():
        raise InboxError('x_inbox_sha256_mismatch')
    stamp = _timestamp(manifest.get('generated_at'))
    max_age = timedelta(hours=X_STALE_HOURS)
    if stamp < now - max_age or stamp > now + timedelta(minutes=5):
        raise InboxError('x_inbox_stale')
    try:
        started = datetime.strptime(dump_id, '%Y%m%dT%H%M').replace(tzinfo=BEIJING)
    except ValueError:
        raise InboxError('x_inbox_invalid_batch') from None
    if not stamp - max_age <= started <= stamp:
        raise InboxError('x_inbox_invalid_batch')
    files = extract_members(bundle, staging)
    if '_dump.json' not in files:
        raise InboxError('x_inbox_invalid_batch')
    meta = parse_json((staging / '_dump.json').read_bytes())
    if not isinstance(meta, dict) or _timestamp(meta.get('generated_at')) != stamp:
        raise InboxError('x_inbox_invalid_batch')
    listed = manifest.get('files')
    if not isinstance(listed, list) or not all(isinstance(n, str) for n in listed) or sorted(listed) != files:
        raise InboxError('x_inbox_invalid_batch')
    (posts, _, _), _ = read_export(staging, ())
    count = sum(post.get('_main') is True for post in posts.values())
    if not count or type(manifest.get('post_count')) is not int or manifest['post_count'] != count:
        raise InboxError('x_inbox_invalid_batch')
    return count


def _owned(directory):
    if directory.is_symlink() or not directory.is_dir() or not DUMP_ID.fullmatch(directory.name):
        return False
    marker = directory / OWNER_MARKER
    try:
        return (not marker.is_symlink() and marker.is_file()
                and marker.stat().st_size == len(directory.name) + 1
                and marker.read_bytes() == (directory.name + '\n').encode())
    except OSError:
        return False


def _usable(directory, now):
    """Check replay freshness and rank already-owned backups, never count slots."""
    try:
        meta_file = directory / '_dump.json'
        if meta_file.is_symlink() or not meta_file.is_file() or meta_file.stat().st_size > MAX_MANIFEST:
            return False
        meta = parse_json(meta_file.read_bytes())
        stamp = _timestamp(meta.get('generated_at')) if isinstance(meta, dict) else None
        if stamp is None or not now - timedelta(hours=X_STALE_HOURS) <= stamp <= now + timedelta(minutes=5):
            return False
        files = dump_files(directory)
        if not files:
            return False
        if (len(files) > MAX_MEMBERS or any(f.is_symlink() or f.stat().st_size > MAX_MEMBER for f in files)
                or sum(f.stat().st_size for f in files) > MAX_TAR):
            return False
        (posts, _, _), _ = read_export(directory, ())
        return any(post.get('_main') is True for post in posts.values())
    except (InboxError, OSError, ValueError, TypeError, KeyError, OverflowError):
        return False


def _install_exclusive(source, target):
    """Atomic directory move; do not fall back to replacing a competing manual path."""
    libc = ctypes.CDLL(None, use_errno=True)
    try:
        if sys.platform == 'darwin':
            call = libc.renamex_np
            args = (os.fsencode(source), os.fsencode(target), 0x4)  # RENAME_EXCL
        elif sys.platform.startswith('linux'):
            call = libc.renameat2
            args = (-100, os.fsencode(source), -100, os.fsencode(target), 1)  # AT_FDCWD, RENAME_NOREPLACE
        else:
            raise InboxError('x_inbox_exclusive_unsupported')
    except AttributeError:
        raise InboxError('x_inbox_exclusive_unsupported') from None
    if call(*args) == 0:
        return True
    error = ctypes.get_errno()
    if error in (errno.EEXIST, errno.ENOTEMPTY):
        return False
    if error in (errno.ENOSYS, errno.ENOTSUP, errno.EINVAL):
        raise InboxError('x_inbox_exclusive_unsupported')
    raise OSError(error, os.strerror(error))


def _validate_repo(repo):
    # Check raw delimiters too: urlsplit strips certain control characters and
    # cannot distinguish an empty query/fragment from an absent delimiter.
    if re.search(r'[\x00-\x20\x7f\\?#]', repo):
        raise InboxError('x_inbox_repo_invalid')
    try:
        url = urlsplit(repo)
        url.port  # reject malformed ports without including their value in any log
    except ValueError:
        raise InboxError('x_inbox_repo_invalid') from None
    if '@' in url.netloc or '%' in url.netloc:
        raise InboxError('x_inbox_repo_invalid')
    if url.scheme == 'file' and repo.startswith('file://') and url.netloc in ('', 'localhost') and url.path.startswith('/'):
        return
    if url.scheme in ('https', 'ssh') and url.hostname and url.path.startswith('/'):
        return
    raise InboxError('x_inbox_repo_invalid')


def _local_entries(target_root, deadline):
    """Every immediate child counts, regardless of type or whether its target exists."""
    if target_root.is_symlink() or (target_root.exists() and not target_root.is_dir()):
        raise InboxError('x_inbox_target_invalid')
    try:
        entries = os.scandir(target_root)
    except FileNotFoundError:
        return []
    with entries:
        directories = []
        for entry in entries:
            deadline.left()
            directories.append(target_root / entry.name)
        return directories


def _prune_excess(entries, work, now, result, deadline):
    """Retire existing excess only; never free a slot to make an install possible."""
    owned = sorted((path for path in entries if _owned(path)),
                   key=lambda path: (_usable(path, now), path.name))
    try:
        for path in owned[:len(entries) - KEEP]:
            deadline.left()
            if not _owned(path):
                continue
            retired = work / 'retired'
            retired.mkdir(exist_ok=True)
            os.rename(path, retired / path.name)
            result['pruned'].append(path.name)
    except OSError as error:
        result['prune_error'] = type(error).__name__
        raise InboxError('x_inbox_prune_failed') from None


def pull(repo, work, target_root, *, env, timeout=120, min_free=MIN_FREE, download_limit=DOWNLOAD_LIMIT,
         now=None, deadline=None, on_install=None):
    """Return installed/pruned IDs and error codes. The publisher serializes this work."""
    deadline = deadline or Deadline(time.monotonic() + timeout)
    result = dict(installed=[], pruned=[], error=None, prune_error=None)
    now = now or datetime.now(timezone.utc)
    work, target_root = Path(work), Path(target_root)
    try:
        deadline.left()
        _validate_repo(repo)
        entries = _local_entries(target_root, deadline)
        slots = KEEP - len(entries)
        if slots < 0:
            round_dir = Path(tempfile.mkdtemp(prefix='round-', dir=work))
            _prune_excess(entries, round_dir, now, result, deadline)
        if slots <= 0:
            raise InboxError('x_inbox_slots_full')
        newest = max((p.name for p in entries if DUMP_ID.fullmatch(p.name)
                      and not p.is_symlink() and p.is_dir() and _usable(p, now)), default='')
        if shutil.disk_usage(target_root.parent).free < min_free:
            raise InboxError('x_inbox_disk_low')
        work = Path(tempfile.mkdtemp(prefix='round-', dir=work))
        clone = work / 'inbox.git'
        git(['clone', '--quiet', '--bare', '--depth=1', '--single-branch', '--branch=main', '--no-tags',
             '--', repo, str(clone)], env=env, deadline=deadline, limit=download_limit)
        batches = read_tree(clone, env=env, deadline=deadline, limit=download_limit)
        # Older than what we already have (or the same batch again): ignore, never overwrite.
        candidates = sorted(dump_id for dump_id in batches
                            if dump_id > newest and not os.path.lexists(target_root / dump_id))[-KEEP:]
        # With one opening, prefer the newest candidate; a bad newer bundle can still fall back.
        if slots == 1:
            candidates.reverse()
        for dump_id in candidates:
            deadline.left()
            parts = batches[dump_id]
            # Two private ancestors, so read_export's optional ../x-replies lookup stays inside work.
            staging = work / 'stage' / dump_id / 'batch'
            staging.mkdir(parents=True)
            try:
                manifest = read_blob(clone, *parts['json'], MAX_MANIFEST,
                                     env=env, deadline=deadline, limit=download_limit)
                bundle = read_blob(clone, *parts['tar.gz'], MAX_BUNDLE,
                                   env=env, deadline=deadline, limit=download_limit)
                validate(dump_id, manifest, bundle, staging, now)
            except InboxError as error:
                if error.code == 'x_inbox_timeout':
                    raise
                result['error'] = result['error'] or error.code
                continue
            (staging / OWNER_MARKER).write_text(dump_id + '\n', encoding='ascii')
            target_root.mkdir(mode=0o755, exist_ok=True)
            if len(_local_entries(target_root, deadline)) >= KEEP:
                raise InboxError('x_inbox_slots_full')
            deadline.left()
            if _install_exclusive(staging, target_root / dump_id):
                result['installed'].append(dump_id)
                if on_install:
                    on_install(dump_id)
                if len(result['installed']) == slots:
                    break
    except InboxError as error:
        if error.code == 'x_inbox_timeout' or result['error'] is None:
            result['error'] = error.code
    except Exception:  # noqa: BLE001 - keep what was installed; report one code, never raise
        result['error'] = result['error'] or 'x_inbox_internal'
    return result


def _cleanup_work(var):
    first, count = None, 0
    try:
        if var.is_dir():
            for path in var.iterdir():
                if not path.name.startswith(WORK_PREFIX):
                    continue
                try:
                    if path.is_symlink() or not path.is_dir():
                        path.unlink()
                    else:
                        shutil.rmtree(path)
                except OSError as error:
                    first = first or type(error).__name__
                    count += 1
    except OSError as error:
        first = first or type(error).__name__
        count += 1
    return first, count


def _receive(var, repo, env, deadline, report):
    """All receiver filesystem work runs inside the publisher's deadline."""
    failures = [_cleanup_work(var)]
    result = dict(installed=[], pruned=[], error='x_inbox_internal', prune_error=None)
    try:
        deadline.left()
        var.mkdir(parents=True, exist_ok=True)
        work = Path(tempfile.mkdtemp(prefix=WORK_PREFIX, dir=var))
        result = pull(repo, work, var / 'x-dump', env=env, deadline=deadline,
                      on_install=lambda dump_id: report(installed=dump_id))
    except InboxError as error:
        result['error'] = error.code
    except Exception:
        pass
    finally:
        report(result=dict(result, pruned=len(result['pruned'])))
        failures.append(_cleanup_work(var))
        errors = [name for name, _ in failures if name]
        if errors:
            report(cleanup=dict(error=errors[0], count=sum(count for _, count in failures)))


if __name__ == '__main__':
    _receive(Path(sys.argv[1]), os.environ.pop('REBANG_X_INBOX_REPO'), os.environ,
             Deadline(_WORKER_END, worker=True), lambda **event: print(json.dumps(event), flush=True))
