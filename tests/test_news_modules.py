"""PR B contracts: offline summaries, Beijing days, exact dedupe and public output."""
import json
import os
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from pipeline import sample_rows
from shiguang.config import config
from shiguang.model import BEIJING, Item
from shiguang.site.news_data import CATEGORIES, FlashProvider, MockProvider, daily_documents, messages, source_stats
from shiguang.site.build import build


class NewsModuleTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 10, 23, 12, tzinfo=BEIJING)
        self.sources = dict(a=dict(id='a',name='Public A',visibility='public',type='telegram',order=0),
                            b=dict(id='b',name='Public B',visibility='public',type='telegram',order=1),
                            mail=dict(id='mail',name='邮件精华',visibility='private',type='inbox',order=2))

    def item(self, native=1, **kwargs):
        values = dict(source_id='a',filter_key='a',category='AI',title='A headline',body='A body',
                      day='2026-10-22',ts='2026-10-22T15:59:59Z',url='https://t.me/test/1',native_id=native)
        values.update(kwargs)
        return Item(**values)

    def test_beijing_midnight_dedupe_and_private_filter(self):
        inputs = [self.item(),self.item(2),self.item(3,ts='2026-10-22T16:00:00Z',url='https://t.me/test/3'),
                  self.item(4,source_id='mail'),self.item(5,source_id='unknown')]
        rows = messages(inputs,self.sources)
        self.assertEqual(len(rows),2)
        self.assertEqual([r['day'] for r in rows],['2026-10-23','2026-10-22'])
        self.assertEqual(rows[0]['hour'],'2026-10-23 00:00')
        self.assertEqual(rows[0]['category'],'科技AI')
        self.assertEqual(list(daily_documents(rows,self.now)),['2026-10-22'])
        self.assertNotIn('邮件精华',json.dumps(rows,ensure_ascii=False))

    def test_exact_dedupe_uses_link_and_first_fifty_characters(self):
        rows = messages([self.item(1,body='x'*50+'a'), self.item(2,body='x'*50+'b'),
                         self.item(3,body='x'*49+'y'),self.item(4,url='https://t.me/test/4',body='x'*50)],self.sources)
        self.assertEqual(len(rows),3)

    def test_stats_stale_threshold_and_week(self):
        rows = messages([self.item(1,ts='2026-10-23T11:00:00+08:00'),
                         self.item(2,ts='2026-10-17T00:00:00+08:00',url='https://t.me/test/2'),
                         self.item(3,ts='2026-10-16T23:59:59+08:00',url='https://t.me/test/3'),
                         self.item(4,source_id='b',ts='2026-10-22T12:00:00+08:00',url='https://t.me/test/4')],self.sources)
        stats = source_stats(rows,self.sources,self.now)
        self.assertEqual((stats[0]['today_count'],stats[0]['seven_day_count'],stats[0]['status']),(1,2,'ok'))
        self.assertEqual(stats[1]['status'],'ok')
        self.assertEqual(source_stats(rows,self.sources,self.now,23)[1]['status'],'stale')
        self.assertEqual(len(stats),2)

    def test_mock_is_deterministic_categorized_and_backfillable(self):
        inputs = [self.item(n,title=f'Event {n}',category=CATEGORIES[n%5],url=f'https://t.me/test/{n}') for n in range(15)]
        rows = messages(inputs,self.sources)
        with patch('socket.socket',side_effect=AssertionError('network forbidden')):
            one = MockProvider().summarize('2026-10-22',rows)
            self.assertEqual(one,MockProvider().summarize('2026-10-22',rows))
        self.assertLessEqual(len(one['summary']),60)
        self.assertEqual(len(one['events']),10)
        self.assertEqual(set(e['category'] for e in one['events']),set(CATEGORIES))
        self.assertTrue(all(len(e['summary'].split('。'))>=3 for e in one['events']))
        self.assertEqual(one['stats']['total'],15)
        self.assertEqual(daily_documents(rows,self.now,'2026-10-23'),{})
        self.assertEqual(list(daily_documents(rows,self.now,'2026-10-16')),['2026-10-22'])
        with patch.dict(os.environ,{'FLASH_API_KEY':'test-only'}):
            stub = FlashProvider()
            self.assertEqual(stub.key,'test-only')
            with self.assertRaises(NotImplementedError): stub.summarize('2026-10-22',rows)

    def test_cross_source_event_links_and_counts(self):
        rows = messages([self.item(),self.item(2,source_id='b',url='https://t.me/test/2')],self.sources)
        event = MockProvider().summarize('2026-10-22',rows)['events'][0]
        self.assertEqual(event['source_count'],2)
        self.assertEqual(len(event['original_links']),2)

    def test_offline_sample_build_and_immutable_snapshot(self):
        cfg = config()
        rows = sample_rows(cfg,self.now)
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ,{'SITE_OUT':folder+'/site','NO_FETCH':'1','SITE_MODE':'public','MAIL_DIGEST':'0','SAMPLE_DATA':'1'}), patch('socket.socket',side_effect=AssertionError('network forbidden')):
            build(rows,[],self.now)
            root = Path(folder)/'site'
            live = json.loads((root/'data/live.json').read_text())
            self.assertTrue(live['sample'])
            self.assertEqual(len(live['messages']),48)
            self.assertTrue(all(r['type']=='telegram' for r in live['messages']))
            self.assertNotIn('邮件精华',(root/'data/sources.json').read_text())
            index = json.loads((root/'history/index.json').read_text())
            self.assertEqual(index['days'],[f'2026-10-{d}' for d in range(16,23)])
            day = root/'history/2026-10-22.json'
            before = day.read_bytes()
            build(rows[:-1],[],self.now)
            self.assertEqual(before,day.read_bytes())
            self.assertNotIn('news-calendar',(root/'today.html').read_text())
            self.assertNotIn('screens/look',(root/'index.html').read_text())


if __name__ == '__main__':
    unittest.main()
