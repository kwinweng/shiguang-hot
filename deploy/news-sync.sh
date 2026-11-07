#!/usr/bin/env bash
# Publish public static data only; never execute code from a received tree.
set -euo pipefail
umask 022
source_dir=
target=/var/www/news.kwinweng.com
dry_run=0
work_parent=
while (($#)); do
    case "$1" in
        --source|--target|--work-dir)
            (($# >= 2)) || { printf 'Missing value for %s\n' "$1" >&2; exit 2; }
            case "$1" in
                --source) source_dir=$2 ;;
                --target) target=$2 ;;
                --work-dir) work_parent=$2 ;;
            esac
            shift 2 ;;
        --dry-run) dry_run=1; shift ;;
        --help)
            printf '%s\n' 'Usage: news-sync.sh [--source LOCAL_DIR] [--target DIR] [--dry-run] [--work-dir DIR]' \
                'Default source: public GitHub gh-pages tarball (no credentials).' \
                'Dry-run validates in temporary storage and never writes the target.'
            exit 0 ;;
        *) printf 'Unknown option: %s\n' "$1" >&2; exit 2 ;;
    esac
done
[[ -z "$source_dir" || -d "$source_dir" ]] || { printf '--source must be a local directory\n' >&2; exit 2; }
[[ "$target" = /* && "$target" != / && -d "$target" && ! -L "$target" ]] || {
    printf 'Target must be an existing absolute directory, not a symlink or /\n' >&2; exit 2;
}
target=$(realpath -- "$target")
parent=$(dirname -- "$target")
if ((dry_run)); then
    work_parent=${work_parent:-${TMPDIR:-/tmp}}
else
    [[ -z "$work_parent" ]] || { printf '--work-dir is only supported with --dry-run\n' >&2; exit 2; }
    work_parent=$parent
fi
[[ -d "$work_parent" ]] || { printf 'Work directory must already exist\n' >&2; exit 2; }
work_parent=$(realpath -- "$work_parent")
[[ "$work_parent" != "$target" && "$work_parent" != "$target/"* ]] || {
    printf 'Work directory must be outside target\n' >&2; exit 2;
}
if ((!dry_run)); then
    exec 9>"$parent/.news-sync.lock"
    flock -n 9 || { printf 'Another sync is running\n' >&2; exit 1; }
fi
work=$(mktemp -d "$work_parent/.news-sync.XXXXXXXX")
cleanup() { rm -rf -- "$work"; }
trap cleanup EXIT
trap 'exit 1' HUP INT TERM
# The archive and extracted data each get a new empty directory, separate from this script.
mkdir "$work/download" "$work/site"
if [[ -z "$source_dir" ]]; then
    curl -q --fail --location --silent --show-error --proto '=https' --proto-redir '=https' \
        --connect-timeout 15 --max-time 180 --retry 2 \
        --output "$work/download/site.tar.gz" \
        https://codeload.github.com/kwinweng/shiguang-hot/tar.gz/refs/heads/gh-pages
fi
python3 -I - "$work/site" "$target" "$dry_run" "$source_dir" "$work/download/site.tar.gz" <<'PY'
import ctypes
import hashlib
import json
import math
import os
from pathlib import Path, PurePosixPath
import posixpath
import re
import shutil
import sys
import tarfile
from datetime import date, datetime, timedelta, timezone
from html.parser import HTMLParser
from urllib.parse import unquote, urlsplit, urlunsplit

stage, target = (Path(p) for p in sys.argv[1:3])
dry_run = sys.argv[3] == '1'


def site_name(name):
    parts = PurePosixPath(name).parts
    if any(p.startswith(('.env', 'id_')) or 'htpasswd' in p or p == '.git'
           or p in ('secrets.json', 'master.key') or p.endswith(('.db', '.sqlite', '.sqlite3', '.key'))
           or '.db-' in p or '.sqlite-' in p for p in parts):
        raise ValueError(f'non-site credential/database filename: {name}')


def inventory(root):
    result = {}
    for path in sorted(root.rglob('*')):
        name = path.relative_to(root).as_posix()
        site_name(name)
        if path.is_symlink():
            raise ValueError(f'symlink is not a site file: {name}')
        if path.is_dir():
            continue
        if not path.is_file():
            raise ValueError(f'non-regular site file: {name}')
        digest = hashlib.sha256()
        with path.open('rb') as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b''):
                digest.update(chunk)
        result[name] = digest.hexdigest()
    return result


if sys.argv[4]:
    source = Path(sys.argv[4]).resolve()
    # Check before copying: do not read credential files or follow links from local fixtures.
    inventory(source)
    shutil.copytree(source, stage, dirs_exist_ok=True)
else:
    with tarfile.open(sys.argv[5], 'r:gz') as archive:
        prefix = None
        for member in archive:
            path = PurePosixPath(member.name)
            if path.is_absolute() or '..' in path.parts or not path.parts:
                raise ValueError('unsafe archive path')
            prefix = prefix or path.parts[0]
            if path.parts[0] != prefix or not (member.isdir() or member.isfile()):
                raise ValueError('archive must contain one directory of regular files (no links)')
            if len(path.parts) == 1:
                if not member.isdir():
                    raise ValueError('archive root must be a directory')
                continue
            name = PurePosixPath(*path.parts[1:]).as_posix()
            site_name(name)
            destination = stage / name
            if member.isdir():
                destination.mkdir(parents=True, exist_ok=True)
            else:
                destination.parent.mkdir(parents=True, exist_ok=True)
                with archive.extractfile(member) as incoming, destination.open('xb') as output:
                    shutil.copyfileobj(incoming, output)


def structured(value, path):
    if isinstance(value, dict):
        for key, child in value.items():
            if (key in ('source', 'source_id', 'sourceId', 'channel') and child in ('mail', '邮件精华')
                    or key in ('scope', 'visibility', 'bookmark_scope') and child == 'private'):
                raise ValueError(f'private JSON source/scope marker: {path}')
            if key == 'sources' and isinstance(child, list):
                if any(v == 'mail' or isinstance(v, dict) and v.get('id') == 'mail' for v in child):
                    raise ValueError(f'mail JSON source marker: {path}')
            if key == 'joint' and isinstance(child, list) and any(v and v[0] == 'mail' for v in child):
                raise ValueError(f'mail JSON joint marker: {path}')
            if key in ('url', 'href', 'src', 'start_url') and isinstance(child, str):
                local_url(child, path)
            if key == 'html' and isinstance(child, str):
                markup(child, path)
            structured(child, path)
    elif isinstance(value, list):
        for child in value:
            structured(child, path)


def local_url(value, path):
    parts = urlsplit(value)
    if parts.scheme or parts.netloc or not parts.path:
        return value
    route = posixpath.normpath(posixpath.join(posixpath.dirname(path), unquote(parts.path)))
    if 'mail' in route.split('/'):
        raise ValueError(f'mail route: {path}')
    return urlunsplit(('', '', route, parts.query, parts.fragment))


class Markup(HTMLParser):
    def __init__(self, path):
        super().__init__(convert_charrefs=True)
        self.path = path
        self.tokens = []
        self.scope = None
        self.fallback_start = self.fallback_end = None
        self.div_depth = 0
        self.json_script = None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        for name in ('data-source', 'data-source-id', 'data-ch'):
            if attrs.get(name) in ('mail', '邮件精华'):
                raise ValueError(f'mail HTML source marker: {self.path}')
        for name in ('data-visibility', 'data-source-visibility', 'data-bookmark-scope'):
            if attrs.get(name) == 'private':
                raise ValueError(f'private HTML scope marker: {self.path}')
        if tag == 'body':
            self.scope = attrs.get('data-bookmark-scope')
        for name in ('href', 'src', 'action', 'data-image', 'data-favorites'):
            if attrs.get(name):
                attrs[name] = local_url(attrs[name], self.path)
        if attrs.get('data-bookmark'):
            structured(json.loads(attrs['data-bookmark']), self.path)
        if tag == 'script' and attrs.get('type') in ('application/json', 'application/ld+json'):
            self.json_script = []
        self.tokens.append(('start', tag, sorted(attrs.items())))
        if tag == 'div':
            if attrs.get('id') == 'news-fallback':
                self.fallback_start = len(self.tokens)
                self.div_depth = 1
            elif self.div_depth:
                self.div_depth += 1

    def handle_endtag(self, tag):
        if tag == 'div' and self.div_depth:
            self.div_depth -= 1
            if not self.div_depth:
                self.fallback_end = len(self.tokens)
        self.tokens.append(('end', tag))
        if tag == 'script' and self.json_script is not None:
            structured(json.loads(''.join(self.json_script)), self.path)
            self.json_script = None

    def handle_data(self, data):
        self.tokens.append(('text', data))
        if self.json_script is not None:
            self.json_script.append(data)


def markup(text, path):
    parser = Markup(path)
    parser.feed(text)
    parser.close()
    return parser


def current_day(root):
    # The old tree may be private. Only its latest nonempty content day is a baseline;
    # mail, private-only records, old pages and assets may all be removed by this migration.
    manifest = json.loads((root / 'archive/manifest.json').read_text())
    days = []
    for day in manifest['days']:
        date.fromisoformat(day)
        if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', day):
            raise ValueError('invalid current archive date')
        if json.loads((root / f'archive/data/{day}.json').read_text())['items']:
            days.append(day)
    if not days:
        raise ValueError('current archive has no content baseline')
    return max(days)


def candidate(root, digests):
    if markup((root / 'index.html').read_text(), 'index.html').scope != 'public':
        raise ValueError('index.html is not a public build')
    for path in root.rglob('*'):
        name = path.relative_to(root).as_posix()
        if 'mail' in path.relative_to(root).parts:
            raise ValueError(f'mail path: {name}')
        if path.is_file() and path.suffix in ('.json', '.webmanifest'):
            structured(json.loads(path.read_text()), name)
        elif path.is_file() and path.suffix in ('.html', '.svg'):
            markup(path.read_text(), name)
    manifest = json.loads((root / 'archive/manifest.json').read_text())
    if manifest.get('scope') != 'public' or manifest.get('schema') != 3:
        raise ValueError('expected public archive schema 3')
    days = manifest['days']
    if not isinstance(days, dict) or not days:
        raise ValueError('invalid archive days')
    expected = {f'archive/data/{day}.json' for day in days}
    if {p for p in digests if p.startswith('archive/data/')} != expected:
        raise ValueError('archive data files differ from manifest days')
    content_days = []
    for day, entry in days.items():
        date.fromisoformat(day)
        if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', day):
            raise ValueError('invalid archive date')
        name = f'archive/data/{day}.json'
        if digests[name] != entry['version']:
            raise ValueError(f'archive hash mismatch: {day}')
        payload = json.loads((root / name).read_text())
        if payload.get('scope') != 'public' or payload.get('schema') != 3 or payload.get('day') != day:
            raise ValueError(f'archive schema/scope/day mismatch: {day}')
        records = payload['items']
        if not isinstance(records, list):
            raise ValueError(f'invalid archive items: {day}')
        if records:
            content_days.append(day)
        html_name = f'archive/{day}.html'
        page = markup((root / html_name).read_text(), html_name)
        if page.scope != 'public' or page.fallback_start is None or page.fallback_end is None:
            raise ValueError(f'archive HTML scope/fallback missing: {day}')
        tokens = []
        for record in records:
            if record['day'] != day or not record['uid'] or not record['source'] or not record['html']:
                raise ValueError(f'invalid archive record: {day}')
            # Sidecar cards resolve relative to archive/data/, standalone cards to archive/.
            tokens.extend(markup(record['html'], name).tokens)
        if tokens != page.tokens[page.fallback_start:page.fallback_end]:
            raise ValueError(f'archive HTML differs from JSON: {day}')
    if not content_days:
        raise ValueError('archive has no content')
    live = json.loads((root / 'data/live.json').read_text())
    if live.get('sample') is not False or not isinstance(live.get('messages'), list) or not live['messages']:
        raise ValueError('empty or sample live data')
    updated = datetime.fromisoformat(live['updated'].replace('Z', '+00:00'))
    if updated.tzinfo is None:
        raise ValueError('live.updated must include a timezone')
    return updated, max(content_days)


try:
    before, after = inventory(target), inventory(stage)
    added = after.keys() - before.keys()
    removed = before.keys() - after.keys()
    changed = [p for p in before.keys() & after.keys() if before[p] != after[p]]
    print(json.dumps(dict(added=len(added), removed=len(removed), changed=len(changed),
                         unchanged=len(before.keys() & after.keys()) - len(changed)), sort_keys=True))
    for name in sorted(removed):
        print(f'DELETE {name}')
    old_day = current_day(target)
    new_updated, new_day = candidate(stage, after)
    print(f'current_content_day={old_day} candidate_content_day={new_day} candidate_updated={new_updated.isoformat()}')
    # Count guards catch truncated packages without retaining individual private history.
    public_files = sum('mail' not in PurePosixPath(p).parts for p in before)
    minimum = max(100, math.ceil(public_files * 0.5))
    print(f'candidate_files={len(after)} minimum_files={minimum}')
    if len(after) < minimum:
        raise ValueError('candidate file count is implausibly small')
    now = datetime.now(timezone.utc)
    if new_day < old_day:
        raise ValueError('candidate content date regresses')
    if new_updated > now + timedelta(minutes=10) or now - new_updated > timedelta(hours=2):
        raise ValueError('candidate live.updated is stale or in the future')
    beijing = timezone(timedelta(hours=8))
    if new_day > now.astimezone(beijing).date().isoformat() or new_day < (now.astimezone(beijing) - timedelta(hours=2)).date().isoformat():
        raise ValueError('candidate has no recent content day')
except (ValueError, KeyError, TypeError, OSError) as error:
    print(f'REFUSED {error}', file=sys.stderr)
    sys.exit(1)
print('validation=passed')
if dry_run:
    print('dry_run=true target_unchanged=true')
    sys.exit(0)
previous = target.with_name(target.name + '.news-sync-previous')
if previous.is_symlink() or (previous.exists() and not previous.is_dir()):
    raise ValueError(f'previous backup path is not a directory: {previous}')
# Normalize incoming modes and preserve the deployed root's owner/group for nginx.
owner = target.stat()
for path in [stage, *stage.rglob('*')]:
    os.chmod(path, 0o755 if path.is_dir() else 0o644)
    if (path.stat().st_uid, path.stat().st_gid) != (owner.st_uid, owner.st_gid):
        os.chown(path, owner.st_uid, owner.st_gid)
# Both trees are on one filesystem. Unsupported platforms/filesystems fail before publication.
libc = ctypes.CDLL(None, use_errno=True)
exchange = libc.renameat2
exchange.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
exchange.restype = ctypes.c_int
if exchange(-100, os.fsencode(stage), -100, os.fsencode(target), 2):
    code = ctypes.get_errno()
    raise OSError(code, os.strerror(code))
# Keep exactly one previous tree, including the private tree on the first migration.
if previous.exists():
    shutil.rmtree(previous)
os.rename(stage, previous)
print(f'published=true previous={previous}')
PY
