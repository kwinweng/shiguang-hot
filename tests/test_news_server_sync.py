"""Synthetic, offline receiver tests; only atomic publication requires Linux."""
import hashlib
import html
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tempfile
import unittest
from datetime import datetime, timedelta, timezone

SCRIPT = Path(__file__).resolve().parents[1] / 'deploy/news-sync.sh'
LINUX_ATOMIC = sys.platform == 'linux' and shutil.which('flock')


class NewsServerSyncTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='news-sync-test-')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.target = self.root / 'live'
        self.source = self.root / 'incoming'
        self.stamp = datetime.now(timezone.utc)
        self.day = self.stamp.astimezone(timezone(timedelta(hours=8))).date().isoformat()
        for root, scope in ((self.target, 'private'), (self.source, 'public')):
            (root / 'archive/data').mkdir(parents=True)
            (root / 'data').mkdir()
            (root / 'index.html').write_text(f'<body data-bookmark-scope="{scope}">site</body>')
            self.set_records(root, scope=scope)
            (root / 'data/live.json').write_text(json.dumps(dict(
                updated=self.stamp.isoformat(), sample=False, messages=[dict(id='existing-news', source='world')]
            )))
        # Keep production's >=100-file guard intact even with a one-story synthetic site.
        for root in (self.target, self.source):
            for number in range(95):
                (root / f'asset-{number}.css').write_text('/* synthetic asset */')
        (self.target / 'mail').mkdir()
        (self.target / 'mail/index.html').write_text('synthetic private mail')
        (self.target / 'history').mkdir()
        (self.target / 'history/private-only.html').write_text('synthetic private-only history')
        self.env = {'PATH': os.environ['PATH'], 'HOME': str(self.root), 'TMPDIR': str(self.root)}

    def set_records(self, root, scope='public', day=None, records=None):
        day = day or self.day
        if records is None:
            saved = html.escape(json.dumps(dict(id='existing-news', source='World')), quote=True)
            records = [dict(uid='existing-news', source='world', day=day,
                            html=f'<article data-source="world"><a href="../../world/index.html">Story</a>'
                                 f'<button data-bookmark="{saved}">Save</button></article>')]
            if scope == 'private':
                records.append(dict(uid='existing-mail', source='mail', day=day,
                                    html='<article data-source="mail">Mail</article>'))
        payload = json.dumps(dict(schema=3, scope=scope, day=day, items=records)).encode()
        (root / 'archive/data' / f'{day}.json').write_bytes(payload)
        (root / 'archive/manifest.json').write_text(json.dumps(dict(
            schema=3, scope=scope, days={day: dict(version=hashlib.sha256(payload).hexdigest())}
        )))
        markup = ''.join(r['html'].replace('../../world/', '../world/') for r in records)
        (root / 'archive' / f'{day}.html').write_text(
            f'<body data-bookmark-scope="{scope}"><div id="news-fallback">{markup}</div></body>')

    def snapshot(self, root):
        return {str(p.relative_to(root)): p.read_bytes() for p in root.rglob('*') if p.is_file()}

    def run_sync(self, dry=True, download=False):
        command = ['bash', str(SCRIPT), '--target', str(self.target)]
        if not download:
            command += ['--source', str(self.source)]
        if dry:
            command += ['--dry-run', '--work-dir', str(self.root)]
        # Running from the input tree also catches accidental local-module imports without -I.
        return subprocess.run(command, text=True, capture_output=True, timeout=30,
                              cwd=self.source, env=self.env)

    def assert_refused(self, marker):
        before = self.snapshot(self.target)
        result = self.run_sync(dry=not LINUX_ATOMIC)
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn(marker, result.stderr)
        self.assertEqual(self.snapshot(self.target), before)
        self.assertFalse([p for p in self.root.glob('.news-sync.*') if p.is_dir()])
        self.assertFalse(self.target.with_name('live.news-sync-previous').exists())

    def test_private_to_public_dry_run_allows_mail_and_private_history_deletion(self):
        before = self.snapshot(self.target)
        # Same size and mtime must still be detected as a content change.
        path = self.source / 'index.html'
        stat = path.stat()
        path.write_text(path.read_text().replace('site', 'NEWS'))
        os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns))
        result = self.run_sync()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('DELETE mail/index.html', result.stdout)
        self.assertIn('DELETE history/private-only.html', result.stdout)
        self.assertIn('validation=passed', result.stdout)
        self.assertIn('target_unchanged=true', result.stdout)
        self.assertEqual(self.snapshot(self.target), before)
        self.assertFalse([p for p in self.root.glob('.news-sync.*') if p.is_dir()])

    def test_private_only_archive_days_and_records_can_be_removed(self):
        manifest_path = self.target / 'archive/manifest.json'
        current = json.loads(manifest_path.read_text())
        old_day = (self.stamp - timedelta(days=3)).astimezone(timezone(timedelta(hours=8))).date().isoformat()
        # A public-source record existing only in the private baseline must not block migration.
        records = [dict(uid='private-only-world', source='world', day=old_day,
                        html='<article data-source="world">Old private-only snapshot</article>')]
        self.set_records(self.target, scope='private', day=old_day, records=records)
        older = json.loads(manifest_path.read_text())
        current['days'].update(older['days'])
        manifest_path.write_text(json.dumps(current))
        result = self.run_sync()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn(f'DELETE archive/data/{old_day}.json', result.stdout)
        self.assertIn(f'DELETE archive/{old_day}.html', result.stdout)

    def test_private_index_is_refused(self):
        (self.source / 'index.html').write_text('<body data-bookmark-scope="private">site</body>')
        self.assert_refused('private HTML scope')

    def test_private_manifest_is_refused(self):
        path = self.source / 'archive/manifest.json'
        manifest = json.loads(path.read_text())
        manifest['scope'] = 'private'
        path.write_text(json.dumps(manifest))
        self.assert_refused('private JSON source/scope')

    def test_manifest_schema_is_checked(self):
        path = self.source / 'archive/manifest.json'
        manifest = json.loads(path.read_text())
        manifest['schema'] = 2
        path.write_text(json.dumps(manifest))
        self.assert_refused('public archive schema 3')

    def test_mail_path_even_empty_directory_is_refused(self):
        (self.source / 'mail').mkdir()
        self.assert_refused('mail path')

    def test_mail_json_source_markers_are_refused(self):
        for value in (dict(source='mail'), dict(nested=[dict(source_id='mail')]),
                      dict(sourceId='mail'), dict(sources=['world', 'mail']),
                      dict(sources=[dict(id='mail')]), dict(joint=[['mail', '', '']])):
            with self.subTest(value=value):
                (self.source / 'leak.json').write_text(json.dumps(value))
                self.assert_refused('JSON')

    def test_mail_html_and_local_route_are_refused(self):
        for markup in ('<article data-source="mail">secret</article>',
                       '<a href="/%6dail/index.html">mail</a>',
                       '<script type="application/json">{"source_id":"mail"}</script>'):
            with self.subTest(markup=markup):
                (self.source / 'leak.html').write_text(markup)
                self.assert_refused('mail' if 'script' not in markup else 'JSON')

    def test_mail_html_inside_json_is_refused(self):
        (self.source / 'leak.json').write_text(json.dumps(dict(html='<article data-source="mail">secret</article>')))
        self.assert_refused('mail HTML')

    def test_empty_live_is_refused(self):
        path = self.source / 'data/live.json'
        live = json.loads(path.read_text())
        live['messages'] = []
        path.write_text(json.dumps(live))
        self.assert_refused('empty or sample live')

    def test_sample_and_stale_live_are_refused(self):
        path = self.source / 'data/live.json'
        live = json.loads(path.read_text())
        live['sample'] = True
        path.write_text(json.dumps(live))
        self.assert_refused('empty or sample live')
        live.update(sample=False, updated=(self.stamp - timedelta(hours=3)).isoformat())
        path.write_text(json.dumps(live))
        self.assert_refused('stale or in the future')

    def test_empty_archive_is_refused(self):
        self.set_records(self.source, records=[])
        self.assert_refused('archive has no content')

    def test_old_content_day_is_refused_even_with_fresh_live(self):
        for path in (self.source / 'archive/data').glob('*'):
            path.unlink()
        (self.source / 'archive' / f'{self.day}.html').unlink()
        old_day = (self.stamp - timedelta(days=2)).astimezone(timezone(timedelta(hours=8))).date().isoformat()
        self.set_records(self.source, day=old_day)
        self.assert_refused('content date regresses')

    def test_stale_content_is_refused_even_if_current_is_older(self):
        old_day = (self.stamp - timedelta(days=2)).astimezone(timezone(timedelta(hours=8))).date().isoformat()
        for root, scope in ((self.source, 'public'), (self.target, 'private')):
            (root / 'archive/data' / f'{self.day}.json').unlink()
            (root / 'archive' / f'{self.day}.html').unlink()
            self.set_records(root, scope=scope, day=old_day)
        self.assert_refused('no recent content day')

    def test_archive_hash_mismatch_is_refused(self):
        with (self.source / 'archive/data' / f'{self.day}.json').open('a') as stream:
            stream.write(' ')
        self.assert_refused('archive hash mismatch')

    def test_archive_html_mismatch_is_refused(self):
        path = self.source / 'archive' / f'{self.day}.html'
        path.write_text(path.read_text().replace('Story', 'OTHER'))
        self.assert_refused('HTML differs from JSON')

    def test_missing_html_and_unlisted_sidecar_are_refused(self):
        path = self.source / 'archive' / f'{self.day}.html'
        saved = path.read_text()
        path.unlink()
        self.assert_refused('No such file')
        path.write_text(saved)
        (self.source / 'archive/data/2020-01-01.json').write_text('{}')
        self.assert_refused('differ from manifest')

    def test_truncated_file_count_is_refused(self):
        for number in range(200):
            (self.target / f'page-{number}.html').write_text('old public page')
        self.assert_refused('file count is implausibly small')

    def test_public_baseline_requires_half_the_file_count(self):
        shutil.rmtree(self.target)
        shutil.copytree(self.source, self.target)
        for number in range(400):
            (self.target / f'page-{number}.html').write_text('old public page')
        for number in range(100):
            (self.source / f'page-{number}.html').write_text('retained public page')
        self.assert_refused('file count is implausibly small')

    def test_local_symlink_is_refused(self):
        (self.source / 'linked.html').symlink_to(self.target / 'index.html')
        self.assert_refused('symlink is not a site file')

    def prepare_download(self):
        archive = self.root / 'fixture.tar.gz'
        with tarfile.open(archive, 'w:gz') as stream:
            stream.add(self.source, arcname='shiguang-hot-gh-pages')
        tools = self.root / 'tools'
        tools.mkdir()
        curl = tools / 'curl'
        curl.write_text('#!/bin/bash\nset -eu\nprintf "%s\\n" "$@" > "$NEWS_SYNC_CURL_ARGS"\n'
                        'while [ "$1" != "--output" ]; do shift; done\n'
                        'cp "$NEWS_SYNC_FIXTURE" "$2"\n')
        curl.chmod(0o755)
        self.env.update(PATH=f'{tools}:{self.env["PATH"]}', NEWS_SYNC_FIXTURE=str(archive),
                        NEWS_SYNC_CURL_ARGS=str(self.root / 'curl-args'))
        return archive

    def test_default_download_is_credential_free_and_never_runs_received_code(self):
        (self.source / 'json.py').write_text('raise RuntimeError("untrusted json module executed")')
        sentinel = self.root / 'executed'
        (self.source / 'pipeline.py').write_text(f'open({str(sentinel)!r}, "w").write("bad")')
        self.prepare_download()
        before = self.snapshot(self.target)
        result = self.run_sync(download=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        args = (self.root / 'curl-args').read_text().splitlines()
        self.assertEqual(args[0], '-q')  # Ignore credential-bearing .curlrc files.
        self.assertEqual(args[-1], 'https://codeload.github.com/kwinweng/shiguang-hot/tar.gz/refs/heads/gh-pages')
        self.assertFalse(sentinel.exists())
        self.assertEqual(self.snapshot(self.target), before)
        self.assertFalse([p for p in self.root.glob('.news-sync.*') if p.is_dir()])

    def test_download_rejects_traversal_and_links(self):
        archive = self.prepare_download()
        for name, kind in (('../escaped', tarfile.REGTYPE),
                           ('shiguang-hot-gh-pages/linked', tarfile.SYMTYPE)):
            with self.subTest(name=name):
                with tarfile.open(archive, 'w:gz') as stream:
                    entry = tarfile.TarInfo(name)
                    entry.type = kind
                    if kind == tarfile.REGTYPE:
                        entry.size = 1
                        stream.addfile(entry, io.BytesIO(b'x'))
                    else:
                        entry.linkname = '/tmp/outside'
                        stream.addfile(entry)
                result = self.run_sync(download=True)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn('unsafe archive path' if kind == tarfile.REGTYPE else 'no links', result.stderr)
                self.assertFalse((self.root / 'escaped').exists())
                self.assertFalse([p for p in self.root.glob('.news-sync.*') if p.is_dir()])

    @unittest.skipUnless(LINUX_ATOMIC, 'Linux flock/renameat2 required')
    def test_atomic_private_to_public_removes_mail_and_retains_one_previous(self):
        before = self.snapshot(self.target)
        original = self.target.stat()
        # Incoming restrictive permissions must not make nginx lose access after exchange.
        (self.source / 'index.html').chmod(0o600)
        (self.source / 'archive').chmod(0o700)
        result = self.run_sync(False)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertNotEqual(self.target.stat().st_ino, original.st_ino)
        previous = self.target.with_name('live.news-sync-previous')
        self.assertEqual(previous.stat().st_ino, original.st_ino)
        self.assertEqual(self.snapshot(previous), before)
        self.assertFalse((self.target / 'mail').exists())
        self.assertFalse((self.target / 'history/private-only.html').exists())
        for path in [self.target, *self.target.rglob('*')]:
            self.assertEqual(path.stat().st_mode & 0o777, 0o755 if path.is_dir() else 0o644)
            self.assertEqual((path.stat().st_uid, path.stat().st_gid), (original.st_uid, original.st_gid))
        first = self.snapshot(self.target)
        (self.source / 'extra.html').write_text('second version')
        result = self.run_sync(False)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.snapshot(previous), first)
        self.assertEqual((self.target / 'extra.html').read_text(), 'second version')
        self.assertFalse([p for p in self.root.glob('.news-sync.*') if p.is_dir()])


if __name__ == '__main__':
    unittest.main()
