"""Import new X export batches from a read-only private Git inbox into var/rebang/x-dump.

Called by tools/mac_publish.py once per round, before collection, only when REBANG_X_INBOX_REPO
is set. Each round makes one fresh shallow bare clone inside a work directory that the publisher
creates and always deletes afterwards; there is no long-lived Git cache to repair after a crash.

Inbox layout (branch main): dumps/<dump_id>.json (manifest) + dumps/<dump_id>.tar.gz (bundle),
optionally README.md at the root. Nothing else. See docs/rebang-v1/X-INBOX.md.

pull() never raises for inbox problems: it returns one error code. Nothing here writes to the inbox.
"""
from datetime import datetime, timedelta, timezone
import gzip
import hashlib
import io
import json
import os
from pathlib import Path
import re
import resource
import shutil
import signal
import subprocess
import sys
import tarfile
import tempfile
import time
import zlib


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))  # pinned code checkout only; the publisher runs with -I
from rebang.bloggers import X_STALE_HOURS  # noqa: E402
from rebang.bloggers.x import read_export  # noqa: E402


MIB = 1024 * 1024
TIMEOUT = 120                 # seconds for the whole inbox step, Git included
MIN_FREE = 1024 * MIB         # skip the round when the x-dump filesystem has less free space
DOWNLOAD_LIMIT = 48 * MIB     # hard per-file size limit (RLIMIT_FSIZE) on every Git process
MAX_MANIFEST = 64 * 1024
MAX_BUNDLE = 5 * MIB
MAX_TAR = 32 * MIB            # decompressed, headers and padding included
MAX_MEMBER = 8 * MIB
MAX_MEMBERS = 128
MAX_TREE_ENTRIES = 64
MAX_NEW = 2                   # newest new batches imported per round
KEEP = 24                     # owned batches kept in x-dump
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
    def __init__(self, seconds):
        self.end = time.monotonic() + seconds

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


def git(args, *, env, deadline, limit, cwd=None):
    """Run git in its own process group under a file-size limit; kill the whole group on timeout.
    stderr is discarded so URLs or credential hints never reach the publisher's log."""
    command = ['git', '-c', 'protocol.allow=never', '-c', 'protocol.file.allow=always',
               '-c', 'protocol.https.allow=always', '-c', 'protocol.ssh.allow=always',
               '-c', 'credential.interactive=false', '-c', 'core.hooksPath=/dev/null',
               '-c', 'fetch.unpackLimit=1', '-c', 'transfer.unpackLimit=1',
               # A git orphaned by a killed publisher still gives up on its own.
               '-c', 'http.lowSpeedLimit=1000', '-c', 'http.lowSpeedTime=30', *args]
    child_env = dict(env, GIT_TERMINAL_PROMPT='0', LC_ALL='C',
                     GIT_SSH_COMMAND='ssh -o BatchMode=yes -o ControlMaster=no -o ControlPath=none '
                                     '-o ConnectTimeout=20 -o ServerAliveInterval=15 -o ServerAliveCountMax=2')
    process = subprocess.Popen(command, cwd=cwd, env=child_env, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                               stderr=subprocess.DEVNULL, start_new_session=True, preexec_fn=_limit_child(limit))
    try:
        output, _ = process.communicate(timeout=deadline.left())
    except subprocess.TimeoutExpired:
        raise InboxError('x_inbox_timeout') from None
    finally:
        if process.returncode is None:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.communicate()
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
    listing = git(['--git-dir', str(clone), 'ls-tree', '-r', '-z', '--long', '--full-tree', 'HEAD'],
                  env=env, deadline=deadline, limit=limit)
    entries = [line for line in listing.split(b'\0') if line]
    if len(entries) > MAX_TREE_ENTRIES:
        raise InboxError('x_inbox_layout')
    batches = {}
    for entry in entries:
        info, _, raw_path = entry.partition(b'\t')
        fields = info.split()
        try:
            path = raw_path.decode('ascii')
        except UnicodeDecodeError:
            raise InboxError('x_inbox_layout') from None
        # Regular non-executable blobs only: no symlinks (120000), submodules (160000) or scripts.
        if len(fields) != 4 or fields[0] != b'100644' or fields[1] != b'blob':
            raise InboxError('x_inbox_layout')
        if path == 'README.md':
            continue
        match = TREE_PATH.fullmatch(path)
        if not match:
            raise InboxError('x_inbox_layout')
        batches.setdefault(match[1], {})[match[2]] = (fields[2].decode(), int(fields[3]))
    if any(set(parts) != {'json', 'tar.gz'} for parts in batches.values()):
        raise InboxError('x_inbox_layout')  # a manifest without its bundle, or the reverse
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


def prune(target_root, work, keep):
    """Move expired owned batches out of reader view into the work directory (deleted later by the
    publisher). Only directories this receiver created, with a well-formed name, are touched."""
    if not target_root.is_dir() or target_root.is_symlink():
        return []
    owned = sorted(d.name for d in target_root.iterdir() if _owned(d))
    expired = owned[:-keep] if len(owned) > keep else []
    retired = work / 'retired'
    if expired:
        retired.mkdir(exist_ok=True)
    for name in expired:
        os.rename(target_root / name, retired / name)
    return expired


def pull(repo, work, target_root, *, env, timeout=TIMEOUT, min_free=MIN_FREE, download_limit=DOWNLOAD_LIMIT,
         keep=KEEP, max_new=MAX_NEW, now=None):
    """One inbox round. Returns dict(installed=[...], pruned=[...], error=None|code, prune_error=None|name).
    work must be an empty private directory on the same filesystem as target_root."""
    result = dict(installed=[], pruned=[], error=None, prune_error=None)
    deadline = Deadline(timeout)
    now = now or datetime.now(timezone.utc)
    work, target_root = Path(work), Path(target_root)
    try:
        if os.path.lexists(target_root) and (target_root.is_symlink() or not target_root.is_dir()):
            raise InboxError('x_inbox_target_invalid')
        if shutil.disk_usage(target_root.parent).free < min_free:
            raise InboxError('x_inbox_disk_low')
        work = Path(tempfile.mkdtemp(prefix='round-', dir=work))  # fresh even if work is reused
        clone = work / 'inbox.git'
        git(['clone', '--quiet', '--bare', '--depth=1', '--single-branch', '--branch=main', '--no-tags',
             '--', repo, str(clone)], env=env, deadline=deadline, limit=download_limit)
        batches = read_tree(clone, env=env, deadline=deadline, limit=download_limit)
        present = [d.name for d in target_root.iterdir()
                   if DUMP_ID.fullmatch(d.name) and not d.is_symlink() and d.is_dir()] if target_root.is_dir() else []
        newest = max(present, default='')
        # Older than what we already have (or the same batch again): ignore, never overwrite.
        candidates = sorted(dump_id for dump_id in batches if dump_id > newest)[-max_new:]
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
            except InboxError as error:  # skip this batch only; a newer valid one may still install
                result['error'] = result['error'] or error.code
                continue
            (staging / OWNER_MARKER).write_text(dump_id + '\n', encoding='ascii')
            deadline.left()
            target_root.mkdir(mode=0o755, exist_ok=True)
            if target_root.is_symlink():
                raise InboxError('x_inbox_target_invalid')
            if os.path.lexists(target_root / dump_id):
                continue
            os.rename(staging, target_root / dump_id)  # same filesystem: atomic, the commit point
            result['installed'].append(dump_id)
    except InboxError as error:
        result['error'] = result['error'] or error.code
    except Exception:  # noqa: BLE001 - keep what was installed; report one code, never raise
        result['error'] = result['error'] or 'x_inbox_internal'
    if result['error'] != 'x_inbox_target_invalid':
        try:
            result['pruned'] = prune(target_root, work, keep)
        except OSError as error:
            result['prune_error'] = type(error).__name__
    return result
