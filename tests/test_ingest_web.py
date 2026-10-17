"""RSS / YouTube feed parsing, the hot stream and the timeline markup."""
import unittest
from datetime import datetime

from shiguang.enrich.hot import hot_stream
from shiguang.ingest.web import parse
from shiguang.model import BEIJING, from_entry
from shiguang.site import render

RSS = b'''<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:media="http://search.yahoo.com/mrss/"><channel><title>Blog</title>
<item><title>First &amp; best</title><link>https://example.com/1</link><guid>id-1</guid>
<pubDate>Fri, 16 Oct 2026 10:00:00 GMT</pubDate><description>&lt;p&gt;Hello &lt;b&gt;world&lt;/b&gt;&lt;img src="https://example.com/a.jpg"&gt;&lt;/p&gt;</description></item>
<item><title>Second</title><link>https://example.com/2</link><pubDate>Sat, 17 Oct 2026 08:30:00 +0800</pubDate>
<enclosure url="https://example.com/b.png" type="image/png"/></item>
<item><title></title><description></description><pubDate>Sat, 17 Oct 2026 09:00:00 +0800</pubDate></item>
<item><title>No date</title></item>
</channel></rss>'''

YOUTUBE = b'''<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom" xmlns:media="http://search.yahoo.com/mrss/" xmlns:yt="http://www.youtube.com/xml/schemas/2015">
<title>Channel</title>
<entry><id>yt:video:abc</id><title>A video</title><link rel="alternate" href="https://www.youtube.com/watch?v=abc"/>
<published>2026-10-17T02:00:00+00:00</published>
<media:group><media:title>A video</media:title><media:description>What it is about.</media:description>
<media:thumbnail url="https://i.ytimg.com/vi/abc/hqdefault.jpg" width="480" height="360"/></media:group></entry>
</feed>'''


class FeedParseTests(unittest.TestCase):
    def test_rss(self):
        entries = parse(RSS)
        self.assertEqual([e['title'] for e in entries], ['Second', 'First & best'])   # newest first; empty and undated dropped
        first = entries[1]
        self.assertEqual((first['id'], first['url'], first['body']), ('id-1', 'https://example.com/1', 'Hello world'))
        self.assertEqual(first['images'], ['https://example.com/a.jpg'])
        self.assertEqual(first['ts'].isoformat(), '2026-10-16T18:00:00+08:00')
        self.assertEqual(entries[0]['images'], ['https://example.com/b.png'])
        self.assertEqual(entries[0]['id'], 'https://example.com/2')               # no guid: the link

    def test_youtube_atom(self):
        [video] = parse(YOUTUBE)
        self.assertEqual((video['id'], video['title'], video['body']), ('yt:video:abc', 'A video', 'What it is about.'))
        self.assertEqual(video['url'], 'https://www.youtube.com/watch?v=abc')
        self.assertEqual(video['images'], ['https://i.ytimg.com/vi/abc/hqdefault.jpg'])
        item = from_entry(dict(video, source='yt', ts=video['ts'].isoformat()), dict(id='yt', name='YouTube'))
        self.assertEqual((item.day, item.filter_key, item.title), ('2026-10-17', 'yt', 'A video'))


class HotStreamTests(unittest.TestCase):
    def row(self, ch, i, hour, text):
        return dict(ch=ch, id=i, ts=f'2026-10-17T{hour:02}:00:00+08:00', title=text[:20], text=text, day='2026-10-17')

    def test_story_reported_twice_appears_once_with_reach(self):
        story = '美联储宣布降息二十五个基点，市场普遍预期年内还将继续降息，美元指数应声走低。'
        rows = [self.row('a', 1, 9, story), self.row('b', 2, 10, '快讯：' + story), self.row('c', 3, 11, '一只猫咪在屋顶晒太阳')]
        hot = hot_stream(rows, datetime(2026, 10, 17, 12, tzinfo=BEIJING), ['美联储', '降息'])
        self.assertEqual([(r['id'], r['sources']) for r in hot], [(1, 2)])           # first report, two channels
        self.assertGreaterEqual(hot[0]['heat'], 6)

    def test_window_and_threshold(self):
        story = '某地发生重大事件，多家媒体持续跟进报道，事件细节仍在进一步核实之中。'
        rows = [self.row('a', 1, 0, story), self.row('b', 2, 23, story)]           # 23 hours apart: two stories
        self.assertEqual(hot_stream(rows, datetime(2026, 10, 17, 23, 30, tzinfo=BEIJING)), [])


class TimelineTests(unittest.TestCase):
    def test_bars_links_and_future(self):
        html = render.timeline(None, {'2026-10-17-09': 2, '2026-10-17-10': 1}, ['2026-10-16', '2026-10-17'], '2026-10-17-10')
        self.assertEqual(html.count('data-key='), 48)
        self.assertIn('href="#h-2026-10-17-09" data-key="2026-10-17-09" style="--n:1.00"', html)
        self.assertIn('style="--n:0.50"', html)
        self.assertIn('class="tl-hour is-future" data-key="2026-10-17-11"', html)
        self.assertIn('id="h-2026-10-17-09"', render.hour_heading('2026-10-17-09'))


if __name__ == '__main__':
    unittest.main()
