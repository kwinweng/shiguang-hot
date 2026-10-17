"""Regression checks for atomic site publication."""
import os
import signal
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from sitebuild import staged_output


class AtomicOutputTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.out = Path(self.temp.name) / 'site'
        (self.out / 'mail' / 'img').mkdir(parents=True)
        (self.out / 'mail' / 'img' / 'kept').write_bytes(b'media')
        (self.out / 'index.html').write_text('old')

    def assert_clean(self):
        self.assertEqual(list(self.out.parent.glob('site.tmp-*')), [])

    def test_publish_preserves_media_and_keeps_live_tree_until_commit(self):
        with staged_output(self.out) as temporary:
            (temporary / 'index.html').write_text('new')
            self.assertEqual((self.out / 'index.html').read_text(), 'old')
        self.assertEqual((self.out / 'index.html').read_text(), 'new')
        self.assertEqual((self.out / 'mail/img/kept').read_bytes(), b'media')
        self.assertFalse(self.out.is_symlink())
        self.assert_clean()

    def test_build_and_exchange_failures_leave_live_tree_intact(self):
        with self.assertRaises(RuntimeError):
            with staged_output(self.out):
                raise RuntimeError('failed build')
        with patch('sitebuild.ctypes.CDLL', side_effect=OSError('failed exchange')):
            with self.assertRaises(OSError):
                with staged_output(self.out):
                    pass
        self.assertEqual((self.out / 'index.html').read_text(), 'old')
        self.assert_clean()

    def test_termination_cleans_staging(self):
        code = '''
import os, signal, sys
from pathlib import Path
from sitebuild import staged_output
with staged_output(Path(sys.argv[1])):
    os.kill(os.getpid(), signal.SIGTERM)
'''
        result = subprocess.run([sys.executable, '-c', code, str(self.out)], cwd=Path(__file__).parent)
        self.assertEqual(result.returncode, 128 + signal.SIGTERM)
        self.assertEqual((self.out / 'index.html').read_text(), 'old')
        self.assert_clean()

    def test_first_build_and_abandoned_staging(self):
        out = self.out.parent / 'fresh'
        abandoned = out.with_name('fresh.tmp-abandoned')
        abandoned.mkdir()
        with staged_output(out) as temporary:
            (temporary / 'index.html').write_text('first')
        self.assertFalse(abandoned.exists())
        self.assertEqual((out / 'index.html').read_text(), 'first')


if __name__ == '__main__':
    unittest.main()
