"""Fetch and install the newest complete X export from a read-only Git inbox."""
import argparse
from datetime import datetime, timedelta, timezone
import fcntl
import gzip
import hashlib
import io
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import zlib


# The CLI runs with -I: import only from this trusted code checkout, never from the inbox.
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from rebang.bloggers import X_STALE_HOURS
from rebang.bloggers.x import read_export


DUMP_ID = re.compile(r'[0-9]{8}T[0-9]{4}')
MEMBER_NAME = re.compile(r'[A-Za-z0-9_][A-Za-z0-9_.-]{0,94}\.json')
CACHE_MARKER = '.x-inbox-cache-v1'
OWNER_MARKER = '.x-inbox-owned'
SNAPSHOT = 'refs/x-inbox/latest'
BEIJING = timezone(timedelta(hours=8))
MIB = 1024 * 1024


class InboxError(Exception):
    pass


def git(cache, *args):
    env = {key: os.environ[key] for key in ('PATH', 'HOME', 'TMPDIR', 'SSH_AUTH_SOCK') if key in os.environ}
    env.update(GIT_TERMINAL_PROMPT='0', GIT_SSH_COMMAND='ssh -o BatchMode=yes')
    try:
        return subprocess.run(
            ['git', '--git-dir', str(cache), '-c', 'credential.interactive=false',
             '-c', 'protocol.allow=never', '-c', 'protocol.file.allow=always',
             '-c', 'protocol.https.allow=always', '-c', 'protocol.ssh.allow=always', *args],
            env=env, check=True, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, timeout=45,
        ).stdout
    except subprocess.CalledProcessError:
        raise InboxError(f'git {args[0]} failed') from None
    except subprocess.TimeoutExpired:
        raise InboxError(f'git {args[0]} timed out') from None


def read_blob(cache, spec, limit):
    if int(git(cache, 'cat-file', '-s', spec)) > limit:
        raise InboxError('inbox Git blob exceeds size limit')
    return git(cache, 'cat-file', 'blob', spec)


def fetch_snapshot(repo, cache):
    cache.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    with (cache.parent / (cache.name + '.lock')).open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if not os.path.lexists(cache):
            cache.mkdir(mode=0o700)
            git(cache, 'init', '--bare')
            (cache / CACHE_MARKER).touch()
        if cache.is_symlink() or not (cache / CACHE_MARKER).is_file():
            raise InboxError('cache must be absent or initialized by this tool')
        git(cache, 'fetch', '--depth=1', '--no-tags', '--no-recurse-submodules', '--no-prune',
            '--no-write-fetch-head', '--refmap=', '--', repo, f'+refs/heads/main:{SNAPSHOT}')
        manifest = parse_json(read_blob(cache, f'{SNAPSHOT}:manifest.json', 64 * 1024))
        if not isinstance(manifest, dict) or not isinstance(manifest.get('dump_id'), str) or not DUMP_ID.fullmatch(manifest['dump_id']):
            raise InboxError('manifest has invalid dump_id')
        dump_id = manifest['dump_id']
        bundle = read_blob(cache, f'{SNAPSHOT}:dumps/{dump_id}.tar.gz', 16 * MIB)
    return manifest, bundle


def parse_json(raw):
    try:
        return json.loads(raw.decode('utf-8'), parse_constant=reject_json_constant)
    except (ValueError, RecursionError):
        raise InboxError('invalid JSON') from None


def reject_json_constant(_value):
    raise ValueError('non-JSON constant')


def generated_at(raw):
    try:
        stamp = datetime.fromisoformat(raw)
        if stamp.tzinfo is not None:
            return stamp.astimezone(timezone.utc)
    except (TypeError, ValueError, OverflowError):
        pass
    raise InboxError('generated_at must be ISO 8601 with a timezone')


def extract_files(bundle, output):
    # Cap decompression before interpreting headers, including extensions and trailing padding.
    try:
        with gzip.GzipFile(fileobj=io.BytesIO(bundle)) as stream:
            raw = stream.read(32 * MIB + 1)
    except (OSError, EOFError, zlib.error):
        raise InboxError('invalid gzip') from None
    if len(raw) > 32 * MIB:
        raise InboxError('tar exceeds decompressed size limit')

    # Plain USTAR only. Inspect raw headers so tarfile cannot silently consume PAX/GNU
    # extensions or resolve links. Never use member names or modes for automatic extraction.
    names = {}
    pos = 0
    while pos + 512 <= len(raw):
        header = raw[pos:pos + 512]
        if header == tarfile.NUL * 512:
            if len(raw) - pos < 1024 or len(raw) % 512 or raw.count(0, pos) != len(raw) - pos:
                raise InboxError('invalid tar end padding')
            return sorted(names.values())
        try:
            item = tarfile.TarInfo.frombuf(header, 'ascii', 'strict')
        except (tarfile.HeaderError, ValueError):
            raise InboxError('invalid tar member header') from None
        if item.type not in (tarfile.REGTYPE, tarfile.AREGTYPE):
            raise InboxError('tar member is not a regular file')
        if header[257:265] != tarfile.POSIX_MAGIC:
            raise InboxError('tar must use USTAR format')
        if not MEMBER_NAME.fullmatch(item.name):
            raise InboxError('unsafe member name')
        folded = item.name.lower()
        if folded in names:
            raise InboxError('duplicate member name')
        if len(names) >= 128 or not 0 <= item.size <= 8 * MIB:
            raise InboxError('tar member exceeds size or count limit')
        start = pos + 512
        pos = start + ((item.size + 511) // 512) * 512
        if pos > len(raw):
            raise InboxError('truncated tar member')
        contents = raw[start:start + item.size]
        parse_json(contents)
        (output / item.name).write_bytes(contents)
        names[folded] = item.name
    raise InboxError('tar has no end marker')


def validate_snapshot(manifest, bundle, staging):
    dump_id = manifest['dump_id']
    sha256 = manifest.get('sha256')
    if sha256 != hashlib.sha256(bundle).hexdigest():
        raise InboxError('bundle SHA-256 mismatch')
    stamp = generated_at(manifest.get('generated_at'))
    now = datetime.now(timezone.utc)
    max_age = timedelta(hours=X_STALE_HOURS)
    if stamp < now - max_age:
        raise InboxError(f'dump is older than {X_STALE_HOURS} hours')
    if stamp > now + timedelta(minutes=5):
        raise InboxError('dump generated_at is in the future')
    # A dump can start before the manifest's generated_at, so don't require minute equality.
    # But reject impossible dates, and prevent a claimed directory name from outranking all future dumps.
    try:
        started = datetime.strptime(dump_id, '%Y%m%dT%H%M').replace(tzinfo=BEIJING)
    except ValueError:
        raise InboxError('dump_id is not a calendar timestamp') from None
    if not stamp - max_age <= started <= stamp:
        raise InboxError('dump_id is outside the allowed interval before generated_at (Beijing time)')

    actual_files = extract_files(bundle, staging)
    if '_dump.json' not in actual_files:
        raise InboxError('missing _dump.json')
    meta = parse_json((staging / '_dump.json').read_bytes())
    if not isinstance(meta, dict) or generated_at(meta.get('generated_at')) != stamp:
        raise InboxError('_dump.json generated_at mismatch')
    files = manifest.get('files')
    if (not isinstance(files, list) or not all(isinstance(name, str) for name in files)
            or sorted(files) != actual_files):
        raise InboxError('manifest file list mismatch')
    (posts, _, _), _ = read_export(staging, ())
    count = sum(post.get('_main') is True for post in posts.values())
    if not count:
        raise InboxError('export has no main posts')
    if type(manifest.get('post_count')) is not int or manifest['post_count'] != count:
        raise InboxError('manifest post count mismatch')
    return count


def prune_owned(target_root):
    owned = []
    for directory in target_root.iterdir():
        if not DUMP_ID.fullmatch(directory.name) or directory.is_symlink() or not directory.is_dir():
            continue
        marker = directory / OWNER_MARKER
        if not marker.is_symlink() and marker.is_file() and marker.stat().st_size == len(directory.name) + 1:
            if marker.read_bytes() == (directory.name + '\n').encode():
                owned.append(directory)
    for directory in sorted(owned)[:-6]:
        shutil.rmtree(directory)


def pull(repo, cache, target_root):
    cache_path, target_path = cache.resolve(), target_root.resolve()
    if cache_path == target_path or cache_path in target_path.parents or target_path in cache_path.parents:
        raise InboxError('cache and target must be separate, non-nested directories')
    manifest, bundle = fetch_snapshot(repo, cache.absolute())
    target_root = target_root.absolute()
    target_root.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    dump_id = manifest['dump_id']
    target = target_root / dump_id
    # Stage outside x-dump so the site's latest_dump cannot see an incomplete import.
    with tempfile.TemporaryDirectory(prefix='.x-inbox-', dir=target_root.parent) as temp:
        staging = Path(temp) / 'unpack' / 'dump'
        staging.mkdir(parents=True)
        count = validate_snapshot(manifest, bundle, staging)
        (staging / OWNER_MARKER).write_text(dump_id + '\n', encoding='ascii')
        with (target_root.parent / '.x-inbox-install.lock').open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            if target_root.is_symlink():
                raise InboxError('target root must not be a symlink')
            if os.path.lexists(target):
                print(f'X inbox: already present {dump_id}')
            else:
                target_root.mkdir(mode=0o700, exist_ok=True)
                staging.rename(target)
                print(f'X inbox: installed {dump_id} ({count} main posts)')
            prune_owned(target_root)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', required=True, help='read-only Git repository URL (main branch)')
    parser.add_argument('--cache', type=Path, required=True, help='local bare fetch cache, created if absent')
    parser.add_argument('--target-root', type=Path, required=True, help='destination x-dump root')
    args = parser.parse_args()
    try:
        pull(args.repo, args.cache, args.target_root)
    except InboxError as error:
        print(f'X inbox pull failed: {error}', file=sys.stderr)
        return 1
    except (OSError, ValueError, OverflowError, RecursionError, RuntimeError) as error:
        # No paths, command arguments or remote output in the publisher's logs.
        print(f'X inbox pull failed: {type(error).__name__}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
