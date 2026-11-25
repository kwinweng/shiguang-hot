"""Offline coverage of the private inbox contract using a file:// bare remote."""
from datetime import datetime, timedelta, timezone
import gzip
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'tools/x_inbox_pull.py'
BEIJING = timezone(timedelta(hours=8))


@pytest.fixture
def inbox(tmp_path):
    return Inbox(tmp_path)


class Inbox:
    def __init__(self, root):
        self.sender = root / 'sender'
        self.sender.mkdir()
        self.remote = root / 'inbox.git'
        self.cache = root / 'mac state' / 'x-inbox.git'
        self.target = root / 'checkout/var/rebang/x-dump'
        self.env = dict(PATH=os.environ['PATH'], HOME=str(root), GIT_CONFIG_NOSYSTEM='1',
                        GIT_ALLOW_PROTOCOL='file')
        self.git('init', '--bare', str(self.remote))
        self.git('init', '-b', 'main')
        (self.sender / 'dumps').mkdir()

    def git(self, *args):
        return subprocess.run(['git', '-c', 'user.name=Fixture', '-c', 'user.email=fixture@localhost',
                               '-c', 'core.hooksPath=/dev/null', *args], cwd=self.sender, env=self.env,
                              check=True, capture_output=True, text=True).stdout.strip()

    def send(self, *, generated=None, dump_id=None, change=None):
        generated = generated or datetime.now(BEIJING)
        dump_id = dump_id or generated.astimezone(BEIJING).strftime('%Y%m%dT%H%M')
        stamp = generated.isoformat()
        posts = {'data': [{'id': '100', 'text': 'Offline post', 'author_id': '1', 'created_at': stamp}],
                 'includes': {'users': [{'id': '1', 'username': 'offline'}]}}
        members = {'posts.json': json.dumps(posts).encode(),
                   '_dump.json': json.dumps({'generated_at': stamp}).encode()}
        if change == 'missing marker':
            del members['_dump.json']
        elif change == 'invalid JSON':
            members['posts.json'] = b'{'
        elif change == 'empty posts':
            members['posts.json'] = b'{"data": []}'
        elif change == 'references only':
            members['quotes.json'] = members['posts.json']
            members['posts.json'] = b'{"data": []}'
        elif change == 'timestamp mismatch':
            members['_dump.json'] = json.dumps({'generated_at': (generated - timedelta(minutes=1)).isoformat()}).encode()
        elif change == 'oversize member':
            members['posts.json'] = b' ' * (8 * 1024 * 1024 + 1)
        elif change == 'absolute name':
            members['/outside.json'] = b'{}'
        elif change == 'parent path':
            members['../outside.json'] = b'{}'
        elif change == 'nested path':
            members['folder/inside.json'] = b'{}'
        elif change == 'case collision':
            members['Posts.json'] = b'{}'

        archive = io.BytesIO()
        fmt = tarfile.PAX_FORMAT if change == 'extended header' else tarfile.USTAR_FORMAT
        with tarfile.open(fileobj=archive, mode='w:gz', format=fmt) as out:
            for name, contents in members.items():
                member = tarfile.TarInfo(name)
                member.size = len(contents)
                if change == 'extended header' and name == 'posts.json':
                    member.pax_headers = {'comment': 'not part of the inbox contract'}
                out.addfile(member, io.BytesIO(contents))
            non_file = {'symlink': tarfile.SYMTYPE, 'hardlink': tarfile.LNKTYPE, 'device': tarfile.CHRTYPE}
            if change in non_file:
                member = tarfile.TarInfo('link.json')
                member.type = non_file[change]
                member.linkname = 'posts.json'
                out.addfile(member)
            if change == 'duplicate name':
                member = tarfile.TarInfo('posts.json')
                out.addfile(member)
        data = archive.getvalue()
        if change == 'truncated gzip':
            data = data[:-8]
        elif change == 'oversize archive':
            data = gzip.compress(gzip.decompress(data) + b'\0' * (32 * 1024 * 1024))
        bundle = self.sender / 'dumps' / f'{dump_id}.tar.gz'
        bundle.write_bytes(data)
        manifest = dict(dump_id=dump_id, generated_at=stamp, files=list(members), post_count=1,
                        sha256=hashlib.sha256(data).hexdigest())
        if change == 'wrong file list':
            manifest['files'].append('missing.json')
        elif change == 'wrong count':
            manifest['post_count'] = 2
        elif change == 'wrong hash':
            manifest['sha256'] = '0' * 64
        elif change == 'naive time':
            manifest['generated_at'] = generated.replace(tzinfo=None).isoformat()
        (self.sender / 'manifest.json').write_text(json.dumps(manifest))
        self.git('add', '.')
        self.git('commit', '-m', 'Update fixture inbox')
        self.git('push', self.remote.as_uri(), 'main')
        return dump_id

    def pull(self):
        return subprocess.run([sys.executable, '-I', str(SCRIPT), '--repo', self.remote.as_uri(),
                               '--cache', str(self.cache), '--target-root', str(self.target)],
                              env=self.env, cwd=self.sender, capture_output=True, timeout=15, text=True)


def test_fetches_and_installs_newest_snapshot_without_writing_remote(inbox):
    dump_id = inbox.send()
    before = inbox.git('--git-dir', str(inbox.remote), 'show-ref')
    result = inbox.pull()
    assert result.returncode == 0, result.stderr
    assert f'installed {dump_id}' in result.stdout
    assert [p.name for p in inbox.target.iterdir()] == [dump_id]
    assert json.loads((inbox.target / dump_id / 'posts.json').read_text())['data'][0]['id'] == '100'
    assert inbox.git('--git-dir', str(inbox.remote), 'show-ref') == before
    assert inbox.git('--git-dir', str(inbox.cache), 'rev-parse', '--is-bare-repository') == 'true'


@pytest.mark.parametrize(('change', 'reason'), [
    ('wrong hash', 'SHA-256'), ('parent path', 'unsafe member'), ('absolute name', 'unsafe member'),
    ('nested path', 'unsafe member'), ('symlink', 'not a regular file'), ('hardlink', 'not a regular file'),
    ('device', 'not a regular file'), ('extended header', 'not a regular file'),
    ('case collision', 'duplicate member'), ('duplicate name', 'duplicate member'),
    ('missing marker', '_dump.json'), ('invalid JSON', 'invalid JSON'), ('empty posts', 'no main posts'),
    ('references only', 'no main posts'), ('timestamp mismatch', 'generated_at mismatch'),
    ('wrong file list', 'file list mismatch'), ('wrong count', 'post count mismatch'),
    ('truncated gzip', 'invalid gzip'), ('oversize archive', 'tar exceeds'),
    ('oversize member', 'member exceeds'), ('naive time', 'timezone'),
])
def test_rejects_invalid_snapshot_without_touching_existing_dumps(inbox, change, reason):
    existing = inbox.target / 'other-producer'
    existing.mkdir(parents=True)
    (existing / 'posts.json').write_bytes(b'untouched')
    inbox.send(change=change)
    result = inbox.pull()
    assert result.returncode == 1, result.stderr
    assert reason in result.stderr
    assert [p.relative_to(inbox.target) for p in inbox.target.rglob('*')] == [Path('other-producer'),
                                                                            Path('other-producer/posts.json')]
    assert (existing / 'posts.json').read_bytes() == b'untouched'


@pytest.mark.parametrize(('offset', 'reason'), [(timedelta(hours=-37), 'older than 36 hours'),
                                                (timedelta(minutes=6), 'future')])
def test_rejects_stale_or_future_snapshot_without_creating_target(inbox, offset, reason):
    inbox.send(generated=datetime.now(BEIJING) + offset)
    result = inbox.pull()
    assert result.returncode == 1
    assert reason in result.stderr
    assert not inbox.target.exists()


def test_repeated_pull_keeps_existing_directory(inbox):
    dump_id = inbox.send()
    assert inbox.pull().returncode == 0
    target = inbox.target / dump_id
    original_inode = target.stat().st_ino
    result = inbox.pull()
    assert result.returncode == 0, result.stderr
    assert f'already present {dump_id}' in result.stdout
    assert target.stat().st_ino == original_inode


def test_existing_foreign_directory_is_neither_overwritten_nor_claimed(inbox):
    dump_id = inbox.send()
    target = inbox.target / dump_id
    target.mkdir(parents=True)
    result = inbox.pull()
    assert result.returncode == 0, result.stderr
    assert f'already present {dump_id}' in result.stdout
    assert list(target.iterdir()) == []


def test_retention_keeps_last_six_owned_and_leaves_other_producers_alone(inbox):
    foreign = inbox.target / '20010101T0000'
    foreign.mkdir(parents=True)
    outside = inbox.target.parent / 'outside'
    outside.mkdir()
    (outside / '.x-inbox-owned').write_text('20020101T0000\n')
    symlink = inbox.target / '20020101T0000'
    symlink.symlink_to(outside, target_is_directory=True)
    now = datetime.now(BEIJING)
    sent = []
    for i in range(8, 0, -1):
        sent.append(inbox.send(generated=now - timedelta(minutes=i)))
        result = inbox.pull()
        assert result.returncode == 0, result.stderr
    assert sorted(p.name for p in inbox.target.iterdir()) == [foreign.name, symlink.name] + sent[-6:]
    assert (outside / '.x-inbox-owned').is_file()
    inbox.send(generated=now, change='wrong hash')
    assert inbox.pull().returncode == 1
    assert sorted(p.name for p in inbox.target.iterdir()) == [foreign.name, symlink.name] + sent[-6:]
