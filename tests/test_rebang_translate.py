"""pending 排序：标题和摘要优先；单轮有条数上限。"""
import io
import json
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from rebang.translate import PENDING_LIMIT, Cache, list_pending
from rebang.translate.__main__ import main


class PendingOrderTests(unittest.TestCase):
    def test_titles_and_summaries_come_first(self):
        cache = Cache(Path(self._tmp()) / 'cache.json')
        cache.want('Long body text. ' * 80, 'en', 'body')
        cache.want('A comment about the post.', 'en', 'comment')
        cache.want('A summary or preview.', 'en', 'summary')
        cache.want('A short title', 'en', 'title')
        cache.want('untyped short title-like', 'en')
        rows = list_pending(cache)
        kinds = [r.get('kind') for r in rows]
        self.assertEqual(kinds[0], 'title')
        # 无 kind 的短句按标题档，排在摘要附近、正文之前
        self.assertLess(kinds.index('title'), kinds.index('summary'))
        self.assertLess(kinds.index('summary'), kinds.index('comment'))
        self.assertLess(kinds.index('comment'), kinds.index('body'))
        self.assertEqual(PENDING_LIMIT, 150)

    def test_untyped_short_tokens_are_not_treated_as_titles(self):
        cache = Cache(Path(self._tmp()) / 'cache.json')
        cache.want('Gaza', 'en')
        cache.want('A real list title about a protest', 'en')
        rows = list_pending(cache)
        self.assertEqual(rows[0]['src'], 'A real list title about a protest')
        self.assertEqual(rows[1]['src'], 'Gaza')

    def test_limit_truncates(self):
        cache = Cache(Path(self._tmp()) / 'cache.json')
        for i in range(5):
            cache.want(f'title {i}', 'en', 'title')
        for i in range(5):
            cache.want(('body %d ' % i) * 80, 'en', 'body')
        rows = list_pending(cache, 3)
        self.assertEqual(len(rows), 3)
        self.assertTrue(all(r.get('kind') == 'title' for r in rows))

    def test_cli_limit(self):
        root = Path(self._tmp())
        cache = Cache(root / 'cache.json')
        cache.want('title one', 'en', 'title')
        cache.want('huge body ' * 100, 'en', 'body')
        cache.save()
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = main(['pending', '--cache', str(root / 'cache.json'), '--limit', '1'])
        self.assertEqual(code, 0)
        rows = json.loads(buf.getvalue())
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['kind'], 'title')

    def _tmp(self):
        import tempfile
        d = tempfile.mkdtemp()
        self.addCleanup(lambda: __import__('shutil').rmtree(d, ignore_errors=True))
        return d


if __name__ == '__main__':
    unittest.main()
