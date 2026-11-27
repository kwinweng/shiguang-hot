"""X inbox receiver: synthetic local Git repositories only. No network, accounts or real exports."""
from datetime import datetime, timedelta, timezone
import gzip
import hashlib
import importlib
import io
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tarfile
import tempfile
import time
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
GIT = shutil.which('git')
BEIJING = timezone(timedelta(hours=8))
MIB = 1024 * 1024


def load(name):
    tools = str(ROOT / 'tools')
    if tools not in sys.path:
        sys.path.insert(0, tools)
    return importlib.import_module(name)


def x_response(count=2, prefix='p'):
    users = [{'id': 'u1', 'username': 'alice', 'name': 'Alice'}]
    data = [{'id': f'{prefix}{i}', 'author_id': 'u1', 'created_at': '2026-11-27T00:00:00.000Z',
             'text': f'hello {i}'} for i in range(count)]
    return json.dumps({'data': data, 'includes': {'users': users}, 'meta': {'result_count': count}}).encode()


def tar_gz(members):
    """members: (name, bytes) for regular files, or (name, TarInfo type, linkname)."""
    raw = io.BytesIO()
    with tarfile.open(fileobj=raw, mode='w', format=tarfile.USTAR_FORMAT) as archive:
        for member in members:
            info = tarfile.TarInfo(member[0])
            if len(member) == 3:
                info.type, info.linkname = member[1], member[2]
                archive.addfile(info)
            else:
                info.size = len(member[1])
                archive.addfile(info, io.BytesIO(member[1]))
    return gzip.compress(raw.getvalue(), mtime=0)


def stamp(minutes_ago):
    return (datetime.now(timezone.utc) - timedelta(minutes=minutes_ago)).astimezone(BEIJING)


def batch(minutes_ago=60, posts=2, members=None, **manifest_changes):
    """A valid manifest + bundle pair (the format verified offline on a real export)."""
    generated = stamp(minutes_ago).replace(microsecond=0)
    dump_id = (generated - timedelta(minutes=2)).strftime('%Y%m%dT%H%M')
    meta = json.dumps({'generated_at': generated.isoformat()}).encode()
    if members is None:
        members = [('posts.json', x_response(posts, prefix=dump_id)), ('_dump.json', meta)]
    bundle = tar_gz(members)
    manifest = dict(dump_id=dump_id, generated_at=generated.isoformat(),
                    files=sorted(m[0] for m in members), post_count=posts,
                    sha256=hashlib.sha256(bundle).hexdigest())
    manifest.update(manifest_changes)
    return dump_id, json.dumps(manifest).encode(), bundle


class InboxRepo:
    """A bare repository whose main branch we rewrite tree by tree (one commit per call)."""

    def __init__(self, root):
        self.path = root / 'inbox.git'
        self.url = self.path.as_uri()
        self.index = root / 'inbox-index'
        self.git('init', '--bare', '-b', 'main', str(self.path), bare=False)
        self.parent = None

    def git(self, *args, input=None, bare=True):
        prefix = ['--git-dir', str(self.path)] if bare else []
        env = dict(os.environ, GIT_INDEX_FILE=str(self.index), GIT_AUTHOR_NAME='Box', GIT_AUTHOR_EMAIL='box@localhost',
                   GIT_COMMITTER_NAME='Box', GIT_COMMITTER_EMAIL='box@localhost')
        return subprocess.run([GIT, *prefix, *args], env=env, input=input, check=True,
                              capture_output=True).stdout.decode().strip()

    def commit(self, entries):
        """entries: path -> bytes, or path -> (mode, bytes)."""
        if self.index.exists():
            self.index.unlink()
        self.git('read-tree', '--empty')
        for path, value in entries.items():
            mode, data = value if isinstance(value, tuple) else ('100644', value)
            blob = self.git('hash-object', '-w', '--stdin', input=data)
            self.git('update-index', '--add', '--cacheinfo', f'{mode},{blob},{path}')
        tree = self.git('write-tree')
        parents = ['-p', self.parent] if self.parent else []
        self.parent = self.git('commit-tree', tree, *parents, '-m', 'Export')
        self.git('update-ref', 'refs/heads/main', self.parent)

    def publish(self, *batches, extra=None):
        entries = {}
        for dump_id, manifest, bundle in batches:
            entries[f'dumps/{dump_id}.json'] = manifest
            entries[f'dumps/{dump_id}.tar.gz'] = bundle
        entries.update(extra or {})
        self.commit(entries)


@unittest.skipUnless(GIT, 'git is required')
class XInboxPullTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='x-inbox-test-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.var = self.root / 'checkout/var/rebang'
        self.var.mkdir(parents=True)
        self.target = self.var / 'x-dump'
        self.work = self.var / '.x-inbox-work-test'
        self.work.mkdir()
        self.repo = InboxRepo(self.root)
        self.env = {key: os.environ[key] for key in ('PATH', 'HOME', 'TMPDIR') if key in os.environ}
        self.inbox = load('x_inbox')

    def pull(self, **options):
        options.setdefault('env', self.env)
        return self.inbox.pull(self.repo.url, self.work, self.target, **options)

    def installed(self):
        return sorted(p.name for p in self.target.iterdir()) if self.target.exists() else []

    def fake_git(self, script):
        """Put a git wrapper first on PATH; script runs before the real git (exec unless it exits)."""
        bin_dir = self.root / 'bin'
        bin_dir.mkdir(exist_ok=True)
        wrapper = bin_dir / 'git'
        wrapper.write_text(f'#!/bin/sh\n{script}\nexec {GIT} "$@"\n')
        wrapper.chmod(0o755)
        return dict(self.env, PATH=f'{bin_dir}:{self.env["PATH"]}')

    # --- normal path -------------------------------------------------------------------------

    def test_installs_newest_two_new_batches_oldest_first_with_owner_marker(self):
        batches = [batch(minutes_ago=m) for m in (300, 180, 60)]
        self.repo.publish(*batches)
        result = self.pull()
        self.assertIsNone(result['error'], result)
        newest_two = [b[0] for b in batches[1:]]
        self.assertEqual(result['installed'], newest_two)
        self.assertEqual(self.installed(), newest_two)
        for dump_id in newest_two:
            directory = self.target / dump_id
            self.assertEqual((directory / '.x-inbox-owned').read_text(), dump_id + '\n')
            self.assertEqual(sorted(p.name for p in directory.iterdir()), ['.x-inbox-owned', '_dump.json', 'posts.json'])
        sys.path.insert(0, str(ROOT))
        from rebang.bloggers.x import latest_dump, read_export
        self.assertEqual(latest_dump(self.target).name, newest_two[-1])
        (posts, _, _), failures = read_export(self.target / newest_two[-1], ())
        self.assertEqual((sum(p.get('_main') is True for p in posts.values()), failures), (2, {}))

    def test_existing_batch_is_never_overwritten(self):
        dump_id, manifest, bundle = batch()
        (self.target / dump_id).mkdir(parents=True)
        (self.target / dump_id / 'posts.json').write_text('manual')
        self.repo.publish((dump_id, manifest, bundle))
        result = self.pull()
        self.assertEqual((result['installed'], result['error']), ([], None))
        self.assertEqual((self.target / dump_id / 'posts.json').read_text(), 'manual')

    def test_newer_incomplete_manual_directory_does_not_block_an_eligible_batch(self):
        incoming = batch(minutes_ago=120)
        incomplete = self.target / batch(minutes_ago=60)[0]
        incomplete.mkdir(parents=True)
        (incomplete / 'posts.json').write_text('manual scratch')
        (incomplete / '_dump.json').write_text('{}')
        self.repo.publish(incoming)
        result = self.pull()
        self.assertEqual((result['installed'], result['error']), ([incoming[0]], None))
        self.assertEqual((incomplete / 'posts.json').read_text(), 'manual scratch')

    def test_replayed_older_batch_is_ignored(self):
        old, new = batch(minutes_ago=240), batch(minutes_ago=60)
        self.repo.publish(new)
        self.assertEqual(self.pull()['installed'], [new[0]])
        # The box re-sends an older export (e.g. one we already pruned or never saw): ignore it.
        self.repo.publish(old, new)
        result = self.pull()
        self.assertEqual((result['installed'], result['error']), ([], None))
        self.assertEqual(self.installed(), [new[0]])

    def test_unexpected_error_keeps_already_installed_batches_in_the_result(self):
        first, second = batch(minutes_ago=120), batch(minutes_ago=60)
        self.repo.publish(first, second)
        real = self.inbox.read_export
        calls = []

        def flaky(path, handles):
            calls.append(path)
            if len(calls) == 2:
                raise KeyError('reader bug')
            return real(path, handles)

        with mock.patch.object(self.inbox, 'read_export', flaky):
            result = self.pull()
        self.assertEqual((result['installed'], result['error']), ([first[0]], 'x_inbox_internal'))
        self.assertEqual(self.installed(), [first[0]])

    # --- bad batches -------------------------------------------------------------------------

    def assert_rejected(self, code, *batches, extra=None, **options):
        before = self.installed()
        self.repo.publish(*batches, extra=extra)
        result = self.pull(**options)
        self.assertEqual(result['error'], code, result)
        self.assertEqual(result['installed'], [])
        self.assertEqual(self.installed(), before)
        return result

    def test_half_written_bundle_fails_sha256(self):
        dump_id, manifest, bundle = batch()
        self.assert_rejected('x_inbox_sha256_mismatch', (dump_id, manifest, bundle[:len(bundle) // 2]))

    def test_bad_gzip_with_matching_hash_is_invalid(self):
        bundle = b'not a gzip stream'
        dump_id, manifest, _ = batch(sha256=hashlib.sha256(b'not a gzip stream').hexdigest())
        self.assert_rejected('x_inbox_invalid_batch', (dump_id, manifest, bundle))

    def test_oversized_bundle_is_rejected(self):
        huge = os.urandom(5 * MIB + 1)
        dump_id, manifest, _ = batch(sha256=hashlib.sha256(huge).hexdigest())
        self.assert_rejected('x_inbox_too_large', (dump_id, manifest, huge))

    def test_oversized_manifest_is_rejected(self):
        dump_id, _, bundle = batch()
        self.assert_rejected('x_inbox_too_large', (dump_id, b' ' * (64 * 1024 + 1), bundle))

    def test_bad_manifests_are_invalid(self):
        good_id, good_manifest, good_bundle = batch()
        cases = {
            'not json': b'{',
            'not an object': b'[]',
            'dump_id differs from file name': json.dumps(dict(json.loads(good_manifest), dump_id='20261127T0001')).encode(),
            'post count mismatch': json.dumps(dict(json.loads(good_manifest), post_count=3)).encode(),
            'file list mismatch': json.dumps(dict(json.loads(good_manifest), files=['posts.json'])).encode(),
            'no timezone': json.dumps(dict(json.loads(good_manifest), generated_at='2026-11-27T01:00:00')).encode(),
        }
        for label, manifest in cases.items():
            with self.subTest(label):
                self.assert_rejected('x_inbox_invalid_batch', (good_id, manifest, good_bundle))

    def test_unsafe_tar_members_are_invalid(self):
        meta_id, _, _ = batch()
        cases = {
            'path traversal': [('../evil.json', b'{}')],
            'nested path': [('sub/evil.json', b'{}')],
            'absolute path': [('/tmp/evil.json', b'{}')],
            'symlink member': [('link.json', tarfile.SYMTYPE, '/etc/passwd')],
            'hard link member': [('link.json', tarfile.LNKTYPE, 'posts.json')],
            'non-json member': [('notes.txt', b'hello')],
            'invalid json member': [('broken.json', b'{')],
        }
        for label, members in cases.items():
            with self.subTest(label):
                generated = stamp(60).replace(microsecond=0)
                base = [('posts.json', x_response()), ('_dump.json', json.dumps({'generated_at': generated.isoformat()}).encode())]
                dump_id, manifest, bundle = batch(members=base + members)
                self.assert_rejected('x_inbox_invalid_batch', (dump_id, manifest, bundle))

    def test_stale_batch_is_rejected(self):
        self.assert_rejected('x_inbox_stale', batch(minutes_ago=37 * 60))

    def test_repository_layout_must_be_exact(self):
        good = batch()
        dump_id, manifest, bundle = good
        cases = {
            'extra root file': dict(extra={'notes.txt': b'x'}),
            'script in dumps': dict(extra={'dumps/run.sh': b'echo'}),
            'nested directory': dict(extra={'dumps/sub/20261127T0000.json': b'{}'}),
            'symlinked bundle': dict(extra={f'dumps/{dump_id}.tar.gz': ('120000', b'../../etc/passwd')}),
            'executable bundle': dict(extra={f'dumps/{dump_id}.tar.gz': ('100755', bundle)}),
            'manifest without bundle': dict(extra={'dumps/20261127T0000.json': manifest}),
            'bad batch name': dict(extra={'dumps/2026-11-27.json': manifest, 'dumps/2026-11-27.tar.gz': bundle}),
        }
        for label, change in cases.items():
            with self.subTest(label):
                self.assert_rejected('x_inbox_layout', good, **change)

    # --- hard limits, timeouts and disk ------------------------------------------------------

    def test_low_disk_skips_without_fetching(self):
        self.repo.publish(batch())
        result = self.pull(min_free=1 << 62)
        self.assertEqual((result['error'], result['installed']), ('x_inbox_disk_low', []))
        self.assertEqual(list(self.work.iterdir()), [])

    def test_download_is_capped_on_disk(self):
        limit = 256 * 1024
        noise = os.urandom(4 * limit)
        dump_id, manifest, _ = batch(sha256=hashlib.sha256(noise).hexdigest())
        self.assert_rejected('x_inbox_fetch_failed', (dump_id, manifest, noise), download_limit=limit)
        sizes = [p.stat().st_size for p in self.work.rglob('*') if p.is_file() and not p.is_symlink()]
        self.assertLessEqual(max(sizes, default=0), limit)

    def test_git_runs_under_a_hard_file_size_limit(self):
        seen = self.root / 'ulimit'
        env = self.fake_git(f'{sys.executable} -I -c "import resource; '
                            f'print(*resource.getrlimit(resource.RLIMIT_FSIZE))" >> {seen}')
        self.repo.publish(batch())
        self.assertIsNone(self.pull(env=env, download_limit=512 * 1024)['error'])
        limits = set(seen.read_text().splitlines())
        self.assertEqual(limits, {f'{512 * 1024} {512 * 1024}'})  # soft and hard, every git call

    def test_unreachable_repository_is_one_error_code_without_url(self):
        self.repo.url = (self.root / 'missing.git').as_uri()
        result = self.pull()
        self.assertEqual((result['error'], result['installed']), ('x_inbox_fetch_failed', []))
        self.assertNotIn('missing.git', json.dumps(result))

    def test_timeout_kills_the_whole_git_process_group(self):
        pid_file = self.root / 'grandchild.pid'
        env = self.fake_git(f'case "$*" in *" clone "*) sleep 60 & echo $! > {pid_file}; wait;; esac')
        self.repo.publish(batch())
        started = time.monotonic()
        result = self.pull(env=env, timeout=1)
        self.assertLess(time.monotonic() - started, 15)
        self.assertEqual((result['error'], result['installed']), ('x_inbox_timeout', []))
        self.assertEqual(self.installed(), [])
        pid = int(pid_file.read_text())
        for _ in range(50):
            try:
                os.kill(pid, 0)
            except ProcessLookupError:
                break
            time.sleep(0.1)
        else:
            self.fail('git grandchild survived the deadline')

    # --- retention -----------------------------------------------------------------------------

    def test_retention_keeps_newest_two_owned_batches_and_never_touches_others(self):
        base = datetime(2026, 11, 1, tzinfo=BEIJING)
        owned = [(base + timedelta(hours=2 * i)).strftime('%Y%m%dT%H%M') for i in range(26)]
        for name in owned:
            (self.target / name).mkdir(parents=True)
            (self.target / name / 'posts.json').write_text('{}')
            (self.target / name / '.x-inbox-owned').write_text(name + '\n')
        manual = ['20261001T0000', 'manual-export']
        for name in manual:
            (self.target / name).mkdir()
            (self.target / name / 'posts.json').write_text('{}')
        wrong_marker = '20261002T0000'
        (self.target / wrong_marker).mkdir()
        (self.target / wrong_marker / '.x-inbox-owned').write_text('20261003T0000\n')
        outside = self.root / 'outside'
        outside.mkdir()
        (outside / '.x-inbox-owned').write_text('20261003T0000\n')
        (self.target / '20261003T0000').symlink_to(outside)

        new = batch()
        self.repo.publish(new)
        result = self.pull()
        self.assertEqual((result['installed'], result['error']), ([new[0]], None))
        kept_owned = sorted(owned + [new[0]])[-2:]
        expired = sorted(owned + [new[0]])[:-2]
        self.assertEqual(sorted(result['pruned']), expired)
        self.assertEqual(self.installed(), sorted(kept_owned + manual + [wrong_marker, '20261003T0000']))
        self.assertTrue((outside / '.x-inbox-owned').exists())
        # Expired batches leave reader view by rename into the work directory; the publisher deletes it.
        for name in expired:
            self.assertFalse((self.target / name).exists())
        self.assertEqual(len([p for p in self.work.rglob('posts.json')]), len(expired))

    def test_retention_preserves_a_readable_backup_over_a_damaged_newer_batch(self):
        old, damaged, replacement = [batch(minutes_ago=m) for m in (180, 120, 60)]
        self.repo.publish(old, damaged)
        self.assertEqual(self.pull()['installed'], [old[0], damaged[0]])
        (self.target / damaged[0] / 'posts.json').write_text('{}')
        self.repo.publish(replacement)
        result = self.pull()
        self.assertEqual((result['installed'], result['pruned']), ([replacement[0]], [damaged[0]]))
        self.assertEqual(self.installed(), [old[0], replacement[0]])

    def test_install_is_exclusive_even_if_an_empty_directory_appears_at_commit(self):
        incoming = batch()
        self.repo.publish(incoming)
        path = self.target / incoming[0]
        real = os.path.lexists

        def race(candidate):
            result = real(candidate)
            if Path(candidate) == path and self.target.is_dir() and not result:
                path.mkdir()
            return result

        with mock.patch.object(self.inbox.os.path, 'lexists', race):
            result = self.pull()
        self.assertEqual((result['installed'], result['error']), ([], None))
        self.assertEqual(list(path.iterdir()), [])

    def test_retention_does_not_run_when_disk_is_low(self):
        names = [(datetime(2026, 11, 1, tzinfo=BEIJING) + timedelta(hours=i)).strftime('%Y%m%dT%H%M') for i in range(25)]
        for name in names:
            (self.target / name).mkdir(parents=True)
            (self.target / name / '.x-inbox-owned').write_text(name + '\n')
        result = self.pull(min_free=1 << 62)
        self.assertEqual(result['error'], 'x_inbox_disk_low')
        self.assertEqual(result['pruned'], [])
        self.assertEqual(self.installed(), names)
        self.repo.url = (self.root / 'missing.git').as_uri()
        result = self.pull()
        self.assertEqual((result['error'], result['pruned']), ('x_inbox_fetch_failed', []))
        self.assertEqual(self.installed(), names)
        self.repo = InboxRepo(self.root / 'retry')
        self.repo.publish(batch())
        # A manual collision is not overwritten and can't authorize retirement of old batches.
        remote = batch(minutes_ago=95)
        (self.target / remote[0]).mkdir()
        names.append(remote[0])
        self.repo.publish(remote)
        result = self.pull()
        self.assertEqual((result['error'], result['pruned']), (None, []))
        self.assertEqual(self.installed(), names)

    def test_symlinked_target_root_is_refused(self):
        elsewhere = self.root / 'elsewhere'
        elsewhere.mkdir()
        self.target.symlink_to(elsewhere)
        self.repo.publish(batch())
        result = self.pull()
        self.assertEqual((result['error'], result['installed']), ('x_inbox_target_invalid', []))
        self.assertEqual(list(elsewhere.iterdir()), [])


@unittest.skipUnless(GIT, 'git is required')
class PublisherInboxStepTests(unittest.TestCase):
    """mac_publish.import_x_inbox: one result line, separate cleanup line, never raises."""

    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='x-inbox-step-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.checkout = self.root / 'checkout'
        self.checkout.mkdir()
        self.repo = InboxRepo(self.root)
        self.env = {key: os.environ[key] for key in ('PATH', 'HOME', 'TMPDIR') if key in os.environ}
        self.publish = load('mac_publish')

    def step(self, **options):
        output = io.StringIO()
        with mock.patch('sys.stdout', output):
            self.publish.import_x_inbox(self.repo.url, self.checkout, self.env, **options)
        return output.getvalue()

    def work_dirs(self):
        var = self.checkout / 'var/rebang'
        return sorted(p.name for p in var.iterdir() if p.name.startswith('.x-inbox-work-')) if var.exists() else []

    def test_success_line_and_no_work_directory_left(self):
        dump_id, *_ = new = batch()
        self.repo.publish(new)
        output = self.step()
        self.assertIn(f'x_inbox=ok installed={dump_id}', output)
        self.assertNotIn('x_inbox_cleanup', output)
        self.assertNotIn(self.repo.url, output)
        self.assertEqual(self.work_dirs(), [])

    def test_cleanup_failure_is_logged_separately_and_does_not_change_the_result(self):
        dump_id, *_ = new = batch()
        self.repo.publish(new)
        with mock.patch.object(self.publish.shutil, 'rmtree', side_effect=PermissionError('denied')):
            output = self.step()
        self.assertIn(f'x_inbox=ok installed={dump_id}', output)
        self.assertIn('x_inbox_cleanup=failed error=PermissionError', output)
        self.assertTrue((self.checkout / 'var/rebang/x-dump' / dump_id / 'posts.json').is_file())
        # The next round removes the leftover and still reports its own result honestly.
        output = self.step()
        self.assertIn('x_inbox=ok installed=none', output)
        self.assertNotIn('x_inbox_cleanup', output)
        self.assertEqual(self.work_dirs(), [])

    def test_failure_is_one_error_line_and_cleanup_still_runs(self):
        self.repo.url = (self.root / 'missing.git').as_uri()
        output = self.step()
        self.assertIn('x_inbox=error code=x_inbox_fetch_failed installed=none', output)
        self.assertNotIn('missing.git', output)
        self.assertEqual(self.work_dirs(), [])

    def test_unexpected_exception_becomes_internal_error(self):
        self.repo.publish(batch())
        inbox = load('x_inbox')
        with mock.patch.object(inbox, 'pull', side_effect=ValueError('boom')):
            output = self.step()
        self.assertIn('x_inbox=error code=x_inbox_internal installed=none', output)
        self.assertEqual(self.work_dirs(), [])

    def test_hard_kill_mid_clone_leaves_nothing_the_next_round_depends_on(self):
        # A previous round was SIGKILLed while git was writing: stale locks and a half pack remain.
        bin_dir = self.root / 'bin'
        bin_dir.mkdir()
        (bin_dir / 'git').write_text(f'#!/bin/sh\ncase "$*" in *" clone "*) echo $$ > {self.root}/cloning; exec sleep 60;; esac\n'
                                    f'exec {GIT} "$@"\n')
        (bin_dir / 'git').chmod(0o755)
        driver = (f'import sys; sys.path.insert(0, {str(ROOT / "tools")!r}); import mac_publish; '
                  f'mac_publish.import_x_inbox({self.repo.url!r}, __import__("pathlib").Path({str(self.checkout)!r}), '
                  f'dict(PATH={str(bin_dir)!r} + ":" + {self.env["PATH"]!r}))')
        self.repo.publish(batch())
        victim = subprocess.Popen([sys.executable, '-c', driver], start_new_session=True,
                                  stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            for _ in range(100):
                if (self.root / 'cloning').exists() and (self.root / 'cloning').read_text().strip():
                    break
                time.sleep(0.1)
            else:
                self.fail('clone did not start')
            # The git process sits in its own session; reap it after the test like a reboot would.
            orphan = int((self.root / 'cloning').read_text())
            self.addCleanup(lambda: subprocess.run(['kill', '-9', str(orphan)], capture_output=True))
            stale = self.work_dirs()
            self.assertEqual(len(stale), 1)
            (self.checkout / 'var/rebang' / stale[0] / 'shallow.lock').write_text('')
            os.killpg(victim.pid, signal.SIGKILL)
        finally:
            victim.wait(timeout=10)
        self.assertEqual(self.work_dirs(), stale)
        new = batch(minutes_ago=30)
        self.repo.publish(new)
        output = self.step()
        self.assertIn(f'installed={new[0]}', output)
        self.assertEqual(self.work_dirs(), [])


if __name__ == '__main__':
    unittest.main()
