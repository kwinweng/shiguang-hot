"""Which source credential paths the Mac publisher hands to the collectors (paths only, never contents)."""
import importlib.util
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('mac_publish_under_test', ROOT / 'tools/mac_publish.py')
mac_publish = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mac_publish)


class SourceCredentialTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='mac-publish-cred-')
        self.addCleanup(temporary.cleanup)
        self.home = Path(temporary.name).resolve() / 'home'
        self.state = Path(temporary.name).resolve() / 'state'
        self.folder = self.home / '.config/rebang'
        self.folder.mkdir(parents=True, mode=0o700)
        self.folder.chmod(0o700)
        self.weibo = self.folder / 'weibo-cookie.txt'
        self.weread = self.folder / 'weread-session.json'

    def write(self, path, mode=0o600):
        path.write_text('secret-not-for-logs')
        path.chmod(mode)

    def sentinel(self, slot):
        return str(self.state / 'no-source-credentials' / slot)

    def resolve(self, home=None):
        return mac_publish.source_credentials(self.home if home is None else home, self.state)

    def test_missing_files_keep_reserved_paths(self):
        env, enabled = self.resolve()
        self.assertEqual(env, {'REBANG_WEIBO_COOKIE': self.sentinel('weibo'),
                               'REBANG_WEREAD_SESSION': self.sentinel('weread')})
        self.assertEqual(enabled, [])

    def test_owner_only_files_are_passed_by_path(self):
        self.write(self.weibo)
        self.write(self.weread)
        env, enabled = self.resolve()
        self.assertEqual(env, {'REBANG_WEIBO_COOKIE': str(self.weibo), 'REBANG_WEREAD_SESSION': str(self.weread)})
        self.assertEqual(enabled, ['weibo', 'weread'])
        self.assertNotIn('secret-not-for-logs', repr((env, enabled)))

    def test_each_credential_is_independent(self):
        self.write(self.weread)
        env, enabled = self.resolve()
        self.assertEqual(env['REBANG_WEIBO_COOKIE'], self.sentinel('weibo'))
        self.assertEqual(env['REBANG_WEREAD_SESSION'], str(self.weread))
        self.assertEqual(enabled, ['weread'])

    def test_group_or_world_readable_file_is_refused(self):
        for mode in (0o640, 0o604, 0o660):
            with self.subTest(mode=oct(mode)):
                self.write(self.weibo, mode)
                env, enabled = self.resolve()
                self.assertEqual(env['REBANG_WEIBO_COOKIE'], self.sentinel('weibo'))
                self.assertEqual(enabled, [])

    def test_shared_folder_is_refused(self):
        self.write(self.weibo)
        self.folder.chmod(0o755)
        self.addCleanup(self.folder.chmod, 0o700)
        env, enabled = self.resolve()
        self.assertEqual(env['REBANG_WEIBO_COOKIE'], self.sentinel('weibo'))
        self.assertEqual(enabled, [])

    def test_symlinks_are_refused(self):
        target = self.home / 'elsewhere.txt'
        self.write(target)
        self.weibo.symlink_to(target)
        env, _ = self.resolve()
        self.assertEqual(env['REBANG_WEIBO_COOKIE'], self.sentinel('weibo'))

        real = self.home / 'real-config'
        real.mkdir(mode=0o700)
        self.write(real / 'weread-session.json')
        linked_home = self.home / 'linked-home'
        (linked_home / '.config').mkdir(parents=True)
        (linked_home / '.config/rebang').symlink_to(real)
        env, enabled = self.resolve(linked_home)
        self.assertEqual(env['REBANG_WEREAD_SESSION'], self.sentinel('weread'))
        self.assertEqual(enabled, [])

    def test_directory_in_place_of_file_is_refused(self):
        self.weibo.mkdir(mode=0o700)
        env, _ = self.resolve()
        self.assertEqual(env['REBANG_WEIBO_COOKIE'], self.sentinel('weibo'))

    def test_other_owner_is_refused(self):
        self.write(self.weibo)
        with mock.patch.object(mac_publish.os, 'getuid', return_value=os.getuid() + 1):
            env, enabled = self.resolve()
        self.assertEqual(env['REBANG_WEIBO_COOKIE'], self.sentinel('weibo'))
        self.assertEqual(enabled, [])

    def test_no_home_and_environment_overrides_are_ignored(self):
        self.write(self.weibo)
        with mock.patch.dict(os.environ, {'REBANG_WEIBO_COOKIE': str(self.weibo),
                                          'REBANG_WEREAD_SESSION': str(self.weibo)}):
            env, enabled = mac_publish.source_credentials(None, self.state)
        self.assertEqual(env, {'REBANG_WEIBO_COOKIE': self.sentinel('weibo'),
                               'REBANG_WEREAD_SESSION': self.sentinel('weread')})
        self.assertEqual(enabled, [])


if __name__ == '__main__':
    unittest.main()
