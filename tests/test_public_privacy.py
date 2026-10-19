"""Public wording is allowed, while actual private-source output stays blocked."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from shiguang.site.build import verify_public


class PublicPrivacyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.private = dict(id='mail', name='Private digest', type='inbox', visibility='private')
        self.cfg = dict(sources=[self.private, dict(id='world', name='World', type='inbox', visibility='public')])
        self.loader = patch('shiguang.site.build.load_issues', return_value=[])
        self.loader.start()
        self.addCleanup(self.loader.stop)

    def write(self, name, text):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)

    def test_public_news_can_use_ordinary_mail_words_without_rewriting(self):
        body = 'AI scams include personalized phishing \u90ae\u4ef6 and text messages.'
        self.write('index.html', '<body data-bookmark-scope="public"><article data-ch="world">'
                   '<span data-source="world">World</span><p>' + body + '</p></article></body>')
        self.write('news.json', json.dumps(dict(source='world', body=body)))
        verify_public(self.root, self.cfg)
        self.assertIn(body, (self.root / 'index.html').read_text())

    def test_plain_text_names_markup_examples_and_external_links_are_not_source_markers(self):
        self.write('index.html', '<p>Private digest is mentioned by a public report. mail/index.html</p>'
                   '<pre>&lt;span data-source="mail"&gt;example&lt;/span&gt;</pre>'
                   '<a href="https://example.com/mail/index.html">External report</a>')
        verify_public(self.root, self.cfg)

    def test_private_source_markup_and_local_routes_are_rejected(self):
        examples = [
            '<article data-source="mail">short secret</article>',
            '<section data-source-id="mail">secret</section>',
            '<article data-ch="mail">secret</article>',
            '<body data-bookmark-scope="private"></body>',
            '<article data-visibility="private">secret</article>',
            '<a href="../mail/index.html">digest</a>',
            '<img src="../m%61il/img/secret.webp">',
            '<meta http-equiv="refresh" content="0; URL=../mail/index.html">',
            '<button data-bookmark="{&quot;source&quot;:&quot;Private digest&quot;}"></button>',
            '<script type="application/json">{"source_id":"mail"}</script>',
        ]
        for text in examples:
            with self.subTest(text=text):
                self.write('archive/day.html', text)
                with self.assertRaisesRegex(RuntimeError, r'private 标记: archive/day.html'):
                    verify_public(self.root, self.cfg)

    def test_json_source_fields_are_checked_after_decoding(self):
        for payload in [dict(source='mail'), dict(nested=[dict(source_id='mail')]),
                        dict(sources=['world', 'mail']), dict(visibility='private'),
                        dict(url='mail/index.html')]:
            with self.subTest(payload=payload):
                self.write('feed.json', json.dumps(payload))
                with self.assertRaisesRegex(RuntimeError, 'private 标记: feed.json'):
                    verify_public(self.root, self.cfg)

    def test_private_directory_and_anonymous_copied_body_stay_blocked(self):
        (self.root / 'mail').mkdir()
        with self.assertRaisesRegex(RuntimeError, 'private 目录'):
            verify_public(self.root, self.cfg)
        (self.root / 'mail').rmdir()
        secret = 'unique private story with enough text to identify the copied content'
        self.write('index.html', '<article data-source="world"><p>' + secret + '</p></article>')
        issue = dict(sections=[dict(items=[dict(title=secret)])])
        with patch('shiguang.site.build.load_issues', return_value=[(issue, self.root)]):
            with self.assertRaisesRegex(RuntimeError, 'private 内容'):
                verify_public(self.root, self.cfg)


if __name__ == '__main__':
    unittest.main()
