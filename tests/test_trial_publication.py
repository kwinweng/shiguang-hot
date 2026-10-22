"""Trial publication acceptance: cleaning, dates, deduplication and public rendering."""
import hashlib
import sqlite3
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace

from bs4 import BeautifulSoup
from shiguang.model import BEIJING
from shiguang.ingest import trial
from shiguang.site import trials
from shiguang.site.render import Page, Site

NOW = datetime(2026, 10, 23, 12, tzinfo=BEIJING)


def row(source='earthsky', **values):
    cfg = next(s for s in trial.load()['sources'] if s['id'] == source)
    return dict(dict(source_id=source, section=cfg['section'], category=cfg['category'],
                     url='https://example.org/' + source, title=source + ' distinct title', summary='',
                     image_url=None, published_at=NOW.isoformat(), fetched_at=NOW.isoformat()), **values)


def page():
    return Page(Site({}, [], [], {}, False, NOW, [], {}), '', 'today')


class TrialPublicationTests(unittest.TestCase):
    def test_all_thirteen_sources_have_public_path(self):
        rows = []
        for source in trial.load()['sources']:
            values = {'title': 'New release ' + source['id']} if source['id'] == 'steam' else {}
            rows.append(row(source['id'], **values))
        items = trials.prepare(rows, NOW)
        self.assertEqual({i['source_id'] for i in items}, {s['id'] for s in trial.load()['sources']})
        self.assertEqual(items, sorted(items, key=lambda i: (i['sort_time'], i['url']), reverse=True))

    def test_apps_cleaning_tags_link_and_skip_log(self):
        self.assertEqual(trials.app_title('Ordinary App', 'body', ''), ('Ordinary App', []))
        title, tags = trials.app_title('标签：限免、工具、效率、生活', '标签：限免\n\nTiny Timer\nbody', '')
        self.assertEqual((title, tags), ('Tiny Timer', ['限免', '工具', '效率']))
        self.assertEqual(trials.app_title('标签：工具', '', 'https://apps.apple.com/cn/app/tiny-timer/id123')[0], 'tiny timer')
        with self.assertLogs('shiguang.site.trials', level='INFO') as log:
            self.assertEqual(trials.prepare([row('Apps_Share', title='标签：工具', summary='备注：免费')], NOW), [])
        self.assertIn('apps_share_untitled', log.output[0])

    def test_url_title_similarity_and_best_record(self):
        first = row(title='Ａｐｐ： Hello! ', url='https://example.org/app/?utm_source=x#fragment')
        better = row('sspai', title='app hello', url='https://example.org/other', image_url='https://example.org/a.jpg')
        first.update(category='apps', section='好玩', source_id='appinn')
        items = trials.prepare([first, better], NOW)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]['source_id'], 'sspai')
        duplicate = row('gcores', url='https://example.org/app')
        self.assertEqual(len(trials.prepare([first, duplicate], NOW)), 1)
        cross = row('9to5mac', url=first['url'], title=first['title'])
        self.assertEqual(len(trials.prepare([first, cross], NOW)), 2)
        near = row('earthsky', title='A night under the bright northern stars today')
        other = row('earthsky', title=near['title'] + '!', url='https://example.org/near')
        self.assertEqual(len(trials.prepare([near, other], NOW)), 1)
        other.update(title=near['title'] + 's', published_at=(NOW-timedelta(hours=49)).isoformat())
        self.assertEqual(len(trials.prepare([near, other], NOW)), 2)

    def test_dates_inclusive_end_unknown_expiry_and_no_fake_date(self):
        event = row('ucca', title='展览 2026.7.14 - 2027.1.31', published_at=None)
        item = trials.prepare([event], NOW)[0]
        self.assertEqual(item['date_label'], '展期 7/14–1/31')
        self.assertNotIn('<time', trials.card(item, NOW))
        event['title'] = '展览 2026.7.14 - 2026.10.22'
        self.assertEqual(trials.prepare([event], NOW), [])
        event['title'] = '展览 2026.7.14 - 2026.10.23'
        self.assertEqual(len(trials.prepare([event], NOW)), 1)
        event['title'] = '未知展览'
        event['fetched_at'] = (NOW-timedelta(days=14)).isoformat()
        self.assertEqual(trials.prepare([event], NOW), [])
        event['fetched_at'] = (NOW-timedelta(days=13)).isoformat()
        self.assertIn('最近收录', trials.card(trials.prepare([event], NOW)[0], NOW))
        self.assertEqual(trials.event_dates('2026.12.20–1.3', NOW)[1].isoformat(), '2027-01-03')
        self.assertIsNone(trials.event_dates('2026.2.30', NOW))

    def test_source_admission_and_safety(self):
        self.assertEqual(trials.prepare([row('steam', title='Weekly maintenance')], NOW), [])
        self.assertEqual(trials.prepare([row('steam', title='Team Fortress 2 Update Released')], NOW), [])
        self.assertEqual(len(trials.prepare([row('steam', title='Now Available on Steam - New Game')], NOW)), 1)
        self.assertEqual(len(trials.prepare([row('steam', title='Winter sale')], NOW)), 1)
        self.assertEqual(len(trials.prepare([row('steam', image_url='https://example.org/a')], NOW)), 1)
        self.assertEqual(trials.prepare([row('appinn', title='VPS 优惠码')], NOW), [])
        self.assertEqual(trials.prepare([row('appinn', title='CloudCone 充值赠送')], NOW), [])
        self.assertEqual(trials.prepare([row('Apps_Share', title='#互推')], NOW), [])
        self.assertEqual(trials.prepare([row('douban-events', title='上海活动')], NOW), [])
        self.assertEqual(trials.prepare([row(url='javascript:alert(1)')], NOW), [])
        self.assertEqual(trials.prepare([row(source_id='private-source')], NOW), [])

    def test_home_five_seven_days_empty_hidden_and_no_list_summary(self):
        rows = [row(url=f'https://example.org/{n}', title=f'{n} 独立天象事件 {chr(65+n)}',
                    published_at=(NOW-timedelta(hours=n)).isoformat()) for n in range(8)]
        rows += [row('9to5mac'), row('bambu-lab', published_at=(NOW-timedelta(days=8)).isoformat())]
        items = trials.prepare(rows, NOW)
        soup = BeautifulSoup(trials.home(items, page()), 'html.parser')
        self.assertEqual([len(s.select('article')) for s in soup.select('section')], [5, 1])
        self.assertEqual(len(soup.select('a.trial-more')), 2)
        self.assertEqual(trials.home([], page()), '')
        listing = trials.body(items, '好玩', page())
        self.assertNotIn('trial-summary', listing)
        self.assertIn('aria-label="观星"', listing)
        self.assertNotIn('软件与 App', listing)

    def test_textcard_icons_palette_and_escaped_external_links(self):
        for category, (key, glyph, label) in trials.CATEGORIES.items():
            source = next(s['id'] for s in trial.load()['sources'] if s['category'] == category)
            item = trials.prepare([row(source, title='<script>safe</script>', image_url='https://example.org/a.jpg')], NOW)[0]
            markup = trials.card(item, NOW)
            self.assertIn(f'var(--tc-{key}-bg)', markup)
            self.assertIn('class="phosphor"', markup)
            self.assertIn('target="_blank" rel="noopener noreferrer"', markup)
            self.assertNotIn('<script>', markup)
            self.assertIn('trial-textcard', markup)
        css = (Path(__file__).parents[1] / 'web/tokens.css').read_text()
        self.assertIn('--tc-star-bg:#EBEBF7', css)
        self.assertIn('--tc-star-icon:#4B4BAE', css)
        self.assertIn('[data-theme="dark"]', css)
        item['category'] = 'unknown'
        self.assertIn('trial-textcard', trials.card(item, NOW))
        self.assertNotIn('--tc--bg', trials.card(item, NOW))

    def test_catalogue_read_only_missing_table_and_unapproved_source(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'tg.db'
            self.assertEqual(trials.catalogue(NOW, path), [])
            with sqlite3.connect(path) as db:
                trial.ensure_table(db)
                db.execute('insert into trial_item values(?,?,?,?,?,?,?,?,?)', tuple(row().values()))
                db.commit()
            before = hashlib.sha256(path.read_bytes()).digest()
            self.assertEqual(len(trials.catalogue(NOW, path)), 1)
            self.assertEqual(hashlib.sha256(path.read_bytes()).digest(), before)

    def test_recollection_updates_details_without_resetting_first_seen_or_new_count(self):
        source = next(s for s in trial.load()['sources'] if s['id'] == 'earthsky')
        item = dict(url='https://example.org/stable', title='First title', body='old',
                    images=[], ts=None)
        batch = SimpleNamespace(now=NOW, new=0, progress=0,
                                get=lambda *args: SimpleNamespace(body=b''))
        with sqlite3.connect(':memory:') as db, patch.object(trial.web, 'parse', return_value=[item]):
            trial.ensure_table(db)
            trial.fetch(db, source, batch)
            first_seen = db.execute('select fetched_at from trial_item').fetchone()[0]
            batch.now += timedelta(days=1)
            item.update(title='New title', body='event details')
            trial.fetch(db, source, batch)
            self.assertEqual(batch.new, 1)
            self.assertEqual(db.execute('select title,summary,fetched_at from trial_item').fetchone(),
                             ('New title', 'event details', first_seen))

    def test_page_metadata_and_telegram_app_link_survive_collection(self):
        source = next(s for s in trial.load()['sources'] if s['id'] == 'douban-events')
        items = trial.parse_page('<li><a href="/event/123/">北京展览</a><p>2026.7.14–2027.1.31</p></li>', source)
        self.assertIn('2027.1.31', items[0]['body'])
        source = next(s for s in trial.load()['sources'] if s['id'] == 'Apps_Share')
        markup = ('<div class="tgme_widget_message" data-post="Apps_Share/123">'
                  '<div class="tgme_widget_message_text">标签：工具<br>'
                  '<a href="https://apps.apple.com/cn/app/tiny-timer/id123">应用下载</a></div></div>')
        item = trial.parse_telegram(markup, source)[0]
        self.assertEqual(trials.app_title(item['title'], item['body'], item['url'])[0], 'tiny timer')


if __name__ == '__main__':
    unittest.main()
