"""Which source credential paths the Mac publisher hands to the collectors (paths only, never contents).

Edge cases (publisher preflight; the collectors repeat the same checks when they open, see
tests/test_private_credentials.py):
- missing files, owner-only files, each file independent, environment overrides ignored;
- HOME rewritten: the account home comes from the user database, not HOME;
- symlinks: the file, the rebang directory, ~/.config, and an ancestor of the home;
- replaceable ancestors: ~/.config group/other writable; rebang directory shared or not enterable;
- owners checked separately: rebang directory of another user, file of another user;
- ACL: allow entry on the file, any entry on the rebang directory, allow entry on ~/.config,
  deny-only entry on the home accepted (macOS default), ACL lookup failure refused;
- hard link, 0000 file, directory or FIFO in place of the file.
"""
import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('mac_publish_under_test', ROOT / 'tools/mac_publish.py')
mac_publish = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mac_publish)
helper = mac_publish.private_file
DARWIN = sys.platform == 'darwin'


def fake_owner(path, uid):
    """Make fstat report another owner for exactly this inode (cannot chown without root)."""
    target = os.lstat(path)
    real = os.fstat

    def fstat(fd):
        info = real(fd)
        if (info.st_dev, info.st_ino) == (target.st_dev, target.st_ino):
            values = list(info)
            values[4] = uid
            return os.stat_result(values)
        return info
    return mock.patch.object(helper.os, 'fstat', fstat)


class SourceCredentialTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='mac-publish-cred-')
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name).resolve()
        self.home = self.base / 'home'
        self.state = self.base / 'state'
        self.home.mkdir(mode=0o755)
        self.folder = self.home / '.config/rebang'
        self.folder.mkdir(parents=True, mode=0o700)
        self.folder.chmod(0o700)
        self.weibo = self.folder / 'weibo-cookie.txt'
        self.weread = self.folder / 'weread-session.json'
        # Leave everything removable for TemporaryDirectory.
        self.addCleanup(lambda: [p.chmod(0o700) for p in (self.folder, self.home / '.config') if p.is_dir()
                                 and not p.is_symlink()])

    def add_acl(self, rule, path):
        self.addCleanup(subprocess.run, ['chmod', '-N', str(path)], check=False)
        subprocess.run(['chmod', '+a', rule, str(path)], check=True)

    def write(self, path, mode=0o600):
        path.write_text('secret-not-for-logs')
        path.chmod(mode)

    def sentinel(self, slot):
        return str(self.state / 'no-source-credentials' / slot)

    def resolve(self, home=None):
        return mac_publish.source_credentials(self.state, self.home if home is None else home)

    def assert_refused(self, home=None, key='REBANG_WEIBO_COOKIE', slot='weibo'):
        env, enabled = self.resolve(home)
        self.assertEqual(env[key], self.sentinel(slot))
        self.assertNotIn(slot, enabled)

    # ---------- basics ----------

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

    def test_environment_overrides_are_ignored(self):
        self.write(self.weibo)
        account = self.base / 'account'
        account.mkdir(mode=0o755)
        with mock.patch.dict(os.environ, {'REBANG_WEIBO_COOKIE': str(self.weibo),
                                          'REBANG_WEREAD_SESSION': str(self.weibo)}), \
                mock.patch.object(helper.pwd, 'getpwuid', return_value=mock.Mock(pw_dir=str(account))):
            env, enabled = mac_publish.source_credentials(self.state)
        self.assertEqual(env, {'REBANG_WEIBO_COOKIE': self.sentinel('weibo'),
                               'REBANG_WEREAD_SESSION': self.sentinel('weread')})
        self.assertEqual(enabled, [])

    def test_rewritten_home_is_ignored_for_the_account_home(self):
        self.write(self.weibo)
        account = self.base / 'account'
        account.mkdir(mode=0o755)
        # HOME points at a folder with valid files, but the user database says the home is elsewhere.
        with mock.patch.dict(os.environ, {'HOME': str(self.home)}), \
                mock.patch.object(helper.pwd, 'getpwuid', return_value=mock.Mock(pw_dir=str(account))):
            env, enabled = mac_publish.source_credentials(self.state)
            self.assertEqual(enabled, [])
            self.assertEqual(env['REBANG_WEIBO_COOKIE'], self.sentinel('weibo'))
        with mock.patch.dict(os.environ, {'HOME': str(account)}), \
                mock.patch.object(helper.pwd, 'getpwuid', return_value=mock.Mock(pw_dir=str(self.home))):
            env, enabled = mac_publish.source_credentials(self.state)
        self.assertEqual((env['REBANG_WEIBO_COOKIE'], enabled), (str(self.weibo), ['weibo']))

    def test_account_without_user_database_entry_gets_no_credentials(self):
        self.write(self.weibo)
        with mock.patch.dict(os.environ, {'HOME': str(self.home)}), \
                mock.patch.object(helper.pwd, 'getpwuid', side_effect=KeyError('uid')):
            env, enabled = mac_publish.source_credentials(self.state)
        self.assertEqual((env['REBANG_WEIBO_COOKIE'], enabled), (self.sentinel('weibo'), []))

    # ---------- symlinks ----------

    def test_symlinked_file_is_refused(self):
        target = self.folder / 'elsewhere.txt'
        self.write(target)
        self.weibo.symlink_to(target)
        self.assert_refused()

    def test_symlinked_rebang_directory_is_refused(self):
        real = self.base / 'real-rebang'
        real.mkdir(mode=0o700)
        self.write(real / 'weread-session.json')
        linked_home = self.base / 'linked-home'
        (linked_home / '.config').mkdir(parents=True)
        (linked_home / '.config/rebang').symlink_to(real)
        self.assert_refused(linked_home, 'REBANG_WEREAD_SESSION', 'weread')

    def test_symlinked_config_directory_is_refused(self):
        real = self.base / 'real-config'
        (real / 'rebang').mkdir(parents=True, mode=0o700)
        (real / 'rebang').chmod(0o700)
        self.write(real / 'rebang/weibo-cookie.txt')
        linked_home = self.base / 'linked-home'
        linked_home.mkdir()
        (linked_home / '.config').symlink_to(real)
        self.assertTrue(os.path.isfile(linked_home / '.config/rebang/weibo-cookie.txt'))
        self.assert_refused(linked_home)

    def test_home_reached_through_a_symlinked_ancestor_is_refused(self):
        self.write(self.weibo)
        alias = self.base / 'alias'
        alias.symlink_to(self.base)
        self.assert_refused(alias / 'home')

    # ---------- replaceable or shared directories ----------

    def test_group_or_world_readable_file_is_refused(self):
        for mode in (0o640, 0o604, 0o660, 0o700 | 0o004):
            with self.subTest(mode=oct(mode)):
                self.write(self.weibo, mode)
                self.assert_refused()

    def test_shared_rebang_directory_is_refused(self):
        self.write(self.weibo)
        for mode in (0o755, 0o750, 0o701):
            with self.subTest(mode=oct(mode)):
                self.folder.chmod(mode)
                self.assert_refused()

    def test_writable_config_directory_is_refused(self):
        self.write(self.weibo)
        for mode in (0o775, 0o757):
            with self.subTest(mode=oct(mode)):
                (self.home / '.config').chmod(mode)
                self.assert_refused()
        (self.home / '.config').chmod(0o755)
        self.assertEqual(self.resolve()[1], ['weibo'])   # a readable, non-writable ~/.config is fine

    def test_rebang_directory_that_cannot_be_entered_is_refused(self):
        self.write(self.weibo)
        for mode in (0o600, 0o300):
            with self.subTest(mode=oct(mode)):
                self.folder.chmod(mode)
                self.assert_refused()

    # ---------- owners, checked separately ----------

    def test_rebang_directory_of_another_owner_is_refused(self):
        self.write(self.weibo)
        with fake_owner(self.folder, os.getuid() + 1):
            self.assert_refused()

    def test_config_directory_of_another_owner_is_refused(self):
        self.write(self.weibo)
        with fake_owner(self.home / '.config', os.getuid() + 1):
            self.assert_refused()

    def test_file_of_another_owner_is_refused(self):
        self.write(self.weibo)
        with fake_owner(self.weibo, os.getuid() + 1):
            self.assert_refused()
        self.assertEqual(self.resolve()[1], ['weibo'])

    # ---------- ACL ----------

    @unittest.skipUnless(DARWIN, 'macOS extended ACL')
    def test_file_with_allow_acl_is_refused(self):
        self.write(self.weibo)
        self.add_acl('everyone allow read', str(self.weibo))
        self.assert_refused()

    @unittest.skipUnless(DARWIN, 'macOS extended ACL')
    def test_file_with_deny_acl_is_refused_too(self):
        self.write(self.weibo)
        self.add_acl('everyone deny write', str(self.weibo))
        self.assert_refused()

    @unittest.skipUnless(DARWIN, 'macOS extended ACL')
    def test_rebang_directory_with_acl_is_refused(self):
        self.write(self.weibo)
        self.add_acl('everyone deny delete', str(self.folder))
        self.assert_refused()

    @unittest.skipUnless(DARWIN, 'macOS extended ACL')
    def test_ancestor_acl_allow_is_refused_but_deny_only_is_accepted(self):
        self.write(self.weibo)
        self.add_acl('group:everyone deny delete', str(self.home))
        self.assertEqual(self.resolve()[1], ['weibo'])   # what macOS puts on every home folder
        self.add_acl('everyone allow add_subdirectory,add_file,delete_child', str(self.home / '.config'))
        self.assert_refused()

    def test_unknown_acl_state_is_refused(self):
        self.write(self.weibo)

        def broken(fd):
            raise helper.PrivateFileError('acl_unknown')
        with mock.patch.object(helper, 'acl_tags', broken):
            self.assert_refused()

    # ---------- file shape ----------

    def test_hard_link_is_refused(self):
        self.write(self.weibo)
        os.link(self.weibo, self.folder / 'second-name')
        self.assert_refused()

    def test_unreadable_file_is_refused(self):
        if os.getuid() == 0:
            self.skipTest('root reads 0000 files')
        self.write(self.weibo, 0o000)
        self.assert_refused()

    def test_directory_in_place_of_file_is_refused(self):
        self.weibo.mkdir(mode=0o700)
        self.assert_refused()

    def test_fifo_in_place_of_file_is_refused_without_blocking(self):
        os.mkfifo(self.weibo, 0o600)
        self.assert_refused()


if __name__ == '__main__':
    unittest.main()
