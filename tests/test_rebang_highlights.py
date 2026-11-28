"""固定时钟下的频道重点契约，全部使用合成报道。"""
import json
from datetime import timedelta, timezone

import pytest

from rebang.chinese_news import needs_translation
from rebang.site import builder as site
from tests.rebang_site_testdata import NOW, envelope, img, news


@pytest.fixture
def build(tmp_path, monkeypatch):
    incoming = tmp_path / 'in'
    incoming.mkdir()
    out = tmp_path / 'site'
    # 每轮都走真实搜索索引构建，归档仅写临时目录。
    from rebang.archive import build as build_archive

    def archive(items, dest, report):
        build_archive(items, dest, archive_dir=tmp_path / 'archive', generated_at=NOW)

    monkeypatch.setattr(site, '_run_archive', archive)

    def translated(items):
        # The highlights suite examines corroboration after the independent Chinese publication gate.
        return [dict(item, translated=True, translation={'title': '合成译文标题', 'summary': '合成译文摘要',
                     'summary_source': item['summary'], 'label': '机器翻译', 'engine': 'test'})
                if needs_translation(item) else item for item in items]

    def run(items, *, history=(), producer='test'):
        if history:
            build_archive(translated(history), tmp_path / 'archive-seed', archive_dir=tmp_path / 'archive', generated_at=NOW)
        (incoming / 'news.json').write_text(json.dumps(envelope(translated(items), producer=producer)), encoding='utf-8')
        site.build(out, incoming, now=NOW, hot_archive_dir=tmp_path / 'hot', web_dir=None)
        return {str(path.relative_to(out / 'data')): json.loads(path.read_text(encoding='utf-8'))
                for path in (out / 'data').rglob('*.json')}

    return run


def reports():
    return (
        news('bbc-world', 'world', 1, lang='en', title='Apple releases iOS 26.1',
             url='https://www.bbc.com/news/articles/test-story',
             summary='The software update became available to iPhone owners on Saturday.',
             body='The software update became available to iPhone owners on Saturday.'),
        news('macrumors', 'digital', 2, lang='en', title='Apple rolls out iOS 26.1',
             url='https://www.macrumors.com/2026/11/15/test-story/', minutes=10,
             summary='The new version can be downloaded from Software Update in Settings.',
             body='The new version can be downloaded from Software Update in Settings.'),
    )


def details(data):
    return {ident: next(item for item in (data[path]['items'] if path != 'meta.json' else
                                         [entry for channel in data[path]['channels'] for entry in channel['banner']])
                        if item['id'] == ident)
            for ident, path in data['id-index.json'].items()}


def highlighted(data):
    return {ident for ident, item in details(data).items() if item.get('highlight')}


def test_independent_reports_mark_page_banner_and_folded_details(build):
    bbc, mac = reports()
    mac['image'] = img(99)
    older_copy = news('tnews365', 'current', 3, minutes=20, lang='en', title=bbc['title'],
                      url=bbc['url'] + '?utm_source=tg', body='较早转发的正文。')
    newer_copy = news('freechinese', 'current', 4, minutes=15, lang='en', title=bbc['title'],
                      url=bbc['url'], body='折叠详情的正文。', highlight=True, highlight_date='2020-01-01')
    items = [bbc, newer_copy, mac, older_copy]
    data = build(items)
    assert highlighted(data) == {i['id'] for i in items}
    assert data['id-index.json'] == {
        bbc['id']: 'channel/world/page-1.json', mac['id']: 'meta.json',
        older_copy['id']: 'channel/current/merged.json', newer_copy['id']: 'channel/current/page-1.json',
    }
    resolved = details(data)
    assert resolved[newer_copy['id']]['merged'][0]['id'] == older_copy['id']
    assert resolved[older_copy['id']]['body'] == older_copy['body']
    assert {i['highlight_date'] for i in resolved.values()} == {NOW.date().isoformat()}
    assert {i['id'] for i in data['search-index.json']['entries']} >= set(resolved)
    assert data == build(list(reversed(items))) == build(items)


@pytest.mark.parametrize('offset, expected', [(86400, True), (86401, False), (-1, False)])
def test_inclusive_window_and_future(build, offset, expected):
    a, b = reports()
    b['published_at'] = (NOW - timedelta(seconds=offset)).astimezone(timezone.utc).isoformat()
    assert highlighted(build([a, b])) == ({a['id'], b['id']} if expected else set())


@pytest.mark.parametrize('changed', [
    {'title': 'Apple rolls out iOS 26.2'},
    {'title': 'Apple rolls out iPadOS 26.1'},
    {'title': 'Not Apple: Google rolls out iOS 26.1'},
    {'title': 'Apple does not release iOS 26.1'},
    {'title': 'Apple rolls out iOS 26.1?'},
    {'title': 'Apple may release iOS 26.1'},
    {'title': 'Apple announces iOS 26.1'},
    {'title': 'Apple rolls out iOS 26.1 in the UK'},
    {'title': 'Apple rolls out iOS 26.1 to 10,000 testers'},
    {'title': 'Apple rolls out iOS 26.1 on November 14'},
    {'title': 'Apple iOS 26.1 News'},
    {'summary': 'Correction: Apple has not released this update.'},
    {'body': 'Reporting by Reuters.'},
    {'published_at': '坏时间'},
])
def test_missing_or_conflicting_evidence_is_unmarked(build, changed):
    a, b = reports()
    b.update(changed, highlight=True, highlight_date='2026-11-15')
    assert highlighted(build([a, b])) == set()


def test_same_id_publisher_aggregator_and_legacy_issue_supply_no_second_vote(build):
    a, b = reports()
    repeated_source = dict(b, id='bbc-world:3', source_id='bbc-world', channel='world',
                           url='https://www.bbc.co.uk/news/articles/other')
    aliases = [news(sid, 'current', i, lang='en', title=b['title'], url=b['url'],
                    highlight=True, highlight_date='2026-11-15')
               for i, sid in enumerate(('tnews365', 'freechinese', 'hot-daily'), 5)]
    legacy_match = news('hot-daily', 'world', 9, url=a['url'], highlight=True, highlight_date='2026-11-15')
    data = build([a, dict(a), repeated_source, *aliases, legacy_match])
    assert highlighted(data) == set()
    assert a['id'] in data['id-index.json']
    assert legacy_match['id'] not in data['id-index.json']


@pytest.mark.parametrize('case', ['tracking', 'title', 'wire', 'platform', 'quoted'])
def test_republished_or_unattributed_material_does_not_count_twice(build, case):
    a, b = reports()
    if case == 'tracking':
        b['url'] = a['url'] + '?utm_campaign=rss'
    elif case == 'title':
        b['title'] = a['title']
    elif case == 'wire':
        b['body'] = 'Update below. ' + a['summary'] + ' Read more.'
    elif case == 'platform':
        a['url'], b['url'] = 'https://t.me/bbc/1', 'https://t.me/macrumors/2'
    else:
        b['summary'] = 'This report was originally published by BBC News.'
    assert highlighted(build([a, b])) == set()


def test_partial_event_does_not_bridge_versions(build):
    a, b = reports()
    bridge = news('guardian-world', 'world', 3, title='Apple releases iOS 26', lang='en',
                  url='https://www.theguardian.com/technology/test-story')
    b['title'] = 'Apple rolls out iOS 26.2'
    assert highlighted(build([a, bridge, b])) == set()


def test_conflicting_duplicate_id_does_not_depend_on_input_order(build):
    a, b = reports()
    conflicting = dict(a, title='Apple releases iOS 26.2')
    data = build([a, conflicting, b])
    assert data == build([conflicting, a, b])
    assert highlighted(data) == set()
    newer = dict(a, fetched_at=(NOW + timedelta(seconds=1)).isoformat())
    assert highlighted(build([a, conflicting, b, newer])) == {a['id'], b['id']}
    assert highlighted(build([newer, a, conflicting, b])) == {a['id'], b['id']}


def event_reports(title_a, title_b, body_a, body_b, *, lang='en'):
    return (
        news('bbc-world', 'world', 101, title=title_a, lang=lang,
             url='https://www.bbc.com/news/articles/synthetic-a', summary=body_a, body=body_a),
        news('guardian-world', 'world', 102, title=title_b, lang=lang, minutes=12,
             url='https://www.theguardian.com/world/synthetic-b', summary=body_b, body=body_b),
    )


EVENTS = [
    pytest.param('Norland Central Bank cuts benchmark rate to 3.50%',
                 'Norland Central Bank lowers its benchmark rate to 3.5%',
                 'The committee voted after reviewing the latest figures for employment and household credit.',
                 'Governor Lorne described the decision at a briefing attended by regional business correspondents.',
                 ['Norland Central Bank raises its benchmark rate to 3.5%',
                  'Norland Central Bank plans to lower its benchmark rate to 3.5%',
                  'Norland Central Bank lowers its benchmark rate to 3.75%',
                  'Norland Central Bank lowers its benchmark rate by 3.5%',
                  'Norland Central Bank lowers its benchmark rate to 3.5 basis points',
                  'Norland Central Bank lowers its deposit rate to 3.5%',
                  'Westreach Central Bank lowers its benchmark rate to 3.5%'], id='rates-en'),
    pytest.param('松岚央行将基准利率下调至4.25%', '松岚央行下调基准利率至4.25％',
                 '委员会今天开会审议了消费、就业和信贷的最新数据。',
                 '央行行长在记者会上解释了本次投票，随后公布决议。',
                 ['松岚央行上调基准利率至4.25%', '传闻松岚央行下调基准利率至4.25%',
                  '松岚央行并未下调基准利率至4.25%', '松岚央行下调基准利率至4.50%',
                  '松岚央行下调存款利率至4.25%', '林州央行下调基准利率至4.25%'], id='rates-zh'),
    pytest.param('Northport officially opens Harbor Bridge', 'Harbor Bridge opens to traffic in Northport',
                 'City engineers removed the temporary barriers after completing a final inspection of both approach roads.',
                 'Drivers began crossing the new span before dawn while crews cleared detour signs.',
                 ['Harbor Bridge closes to traffic in Northport', 'Harbor Bridge will open to traffic in Northport',
                  'Harbor Bridge opens to traffic in Eastport', 'Ferry Bridge opens to traffic in Northport',
                  'Second Harbor Bridge opens to traffic in Northport',
                  'Harbor Bridge opens to traffic in Northport after $80 million upgrade'], id='infrastructure-en'),
    pytest.param('栖云市正式启用银湾大桥', '栖云市银湾大桥正式通车',
                 '交通部门在上午撤除了两岸的临时隔离设施。', '当地居民已可从新桥前往江对岸的车站。',
                 ['栖云市银湾大桥暂停通车', '栖云市银湾大桥计划通车', '河原市银湾大桥正式通车',
                  '栖云市银石大桥正式通车'], id='infrastructure-zh'),
    pytest.param('Alder Appeals Court rules in case 26-CV-471',
                 'Alder Appeals Court issues a ruling in case 26-CV-471',
                 'The three judges filed a written opinion after hearing arguments from counsel for the petitioner.',
                 'Court staff published the decision on the docket just ahead of the afternoon session.',
                 ['Alder Appeals Court will issue a ruling in case 26-CV-471',
                  'Alder Appeals Court vacates ruling in case 26-CV-471',
                  'Alder Appeals Court issues a ruling in case 26-CV-472',
                  'Birch Appeals Court issues a ruling in case 26-CV-471',
                  'Alder Appeals Court issues a ruling in case 26-CV-471 on damages'], id='court-en'),
    pytest.param('澄江法院对2026-CV-219号案件作出裁决', '澄江法院裁决2026-CV-219号案件',
                 '合议庭听取了当事各方陈述后公布书面意见。', '法庭书记员在午后将这份判决书登记进案卷。',
                 ['澄江法院拟裁决2026-CV-219号案件', '澄江法院撤销2026-CV-219号案件裁决',
                  '澄江法院裁决2026-CV-218号案件', '红河法院裁决2026-CV-219号案件'], id='court-zh'),
    pytest.param('Blue Oak releases Slate Studio 7.14.2', 'Blue Oak ships Slate Studio version 7.14.2',
                 'The desktop installer is available as a signed package in the company download centre.',
                 'Maintainers updated the online manual with instructions for migrating existing workspaces.',
                 ['Blue Oak withdraws Slate Studio version 7.14.2', 'Blue Oak plans to ship Slate Studio 7.14.2',
                  'Blue Oak ships Slate Studio version 7.14.3', 'Blue Oak ships Slate Studio 7.14.2 beta',
                  'Green Oak ships Slate Studio version 7.14.2', 'Blue Oak ships Slate Player version 7.14.2'], id='release-en'),
    pytest.param('青穗发布云笺 3.8.1', '青穗推出云笺 v3.8.1 版本',
                 '此次更新调整了同步队列，用户可以从应用内下载安装包。', '新版安装程序现已开放下载，开发团队也同步更新了迁移指南。',
                 ['青穗撤回云笺 v3.8.1 版本', '青穗计划推出云笺 v3.8.1 版本',
                  '青穗推出云笺 v3.8.2 版本', '青穗推出风笺 v3.8.1 版本',
                  '青穗推出云笺 v3.8.1 测试版'], id='release-zh'),
]


@pytest.mark.parametrize('title_a,title_b,body_a,body_b,nearby', EVENTS)
def test_specific_events_with_independent_original_reporting(build, title_a, title_b, body_a, body_b, nearby):
    lang = 'zh' if not title_a[0].isascii() else 'en'
    a, b = event_reports(title_a, title_b, body_a, body_b, lang=lang)
    data = build([a, b])
    assert highlighted(data) == {a['id'], b['id']}
    assert data == build([b, a]) == build([a, b])
    for title in nearby:
        assert highlighted(build([a, dict(b, title=title, highlight=True, highlight_date='2020-01-01')])) == set(), title
    assert highlighted(build([a, dict(b, body=body_a)])) == set()
    assert highlighted(build([a, dict(b, summary='', body='')])) == set()
    assert highlighted(build([a, dict(a), dict(b, url=a['url'] + '?utm_source=feed')])) == set()
    future = (NOW + timedelta(seconds=1)).isoformat()
    expired = (NOW - timedelta(hours=24, seconds=1)).isoformat()
    assert highlighted(build([a, dict(b, published_at=future)])) == set()
    assert highlighted(build([a, dict(b, published_at=expired)])) == set()


@pytest.mark.parametrize('title_a,title_b', [
    ('Silvercoast Reserve Bank lifts policy rate to 7.125%', 'Silvercoast Reserve Bank increases its policy rate to 7.125%'),
    ('Elmwick officially opens Copper Line', 'Copper Line enters service in Elmwick'),
    ('Pine Circuit Court issues a ruling in case 31-8802', 'Pine Circuit Court rules in case 31-8802'),
    ('Amber Ledger 14.3 released', 'Amber Ledger v14.3 is released'),
])
def test_event_identity_accepts_fresh_names_and_identifiers(build, title_a, title_b):
    _, _, body_a, body_b, _ = EVENTS[0].values
    a, b = event_reports(title_a, title_b, body_a, body_b)
    assert highlighted(build([a, b])) == {a['id'], b['id']}


def test_unspecified_benchmark_cannot_bridge_two_distinct_decisions(build):
    a, b = event_reports('Norland Central Bank cuts benchmark rate to 3.25%',
                         'Norland Central Bank lowers its benchmark rate to 3.75%',
                         'Voters on the committee reviewed the latest survey of merchants and households.',
                         'Officials shared their views on domestic credit before finishing deliberations this morning.')
    bridge = news('npr-world', 'world', 103, lang='en', title='Norland Central Bank lowers its benchmark rate',
                  url='https://www.npr.org/synthetic-c', body='Traders watched the official announcement from the press room today.')
    assert highlighted(build([a, bridge, b])) == set()


def test_unrecognized_title_and_unparseable_url_do_not_stop_build(build):
    a, b = reports()
    ordinary = news('bbc-world', 'world', 31, lang='en', title='Analysis: ' + 'Long headline ' * 300,
                    url='https://www.bbc.com/news/articles/ordinary?地区=海湾', highlight=True)
    malformed = news('bbc-world', 'world', 32, url='https://[missing-bracket', highlight=True)
    data = build([ordinary, malformed, a, b])
    assert highlighted(data) == {a['id'], b['id']}
    assert details(data)[ordinary['id']]['url'] == ordinary['url']
    assert malformed['id'] not in data['id-index.json']


def test_old_curator_mark_preserves_original_primary_and_all_public_routes(build):
    url = 'https://example.com/synthetic-fold'
    shared = {'title': '街道工程工作简报', 'url': url}
    older = news('tnews365', 'current', 31, minutes=9, **shared)
    marked = news('freechinese', 'current', 32, minutes=4, image=img(32), **shared)
    legacy = news('hot-daily', 'current', 33, minutes=2, highlight=True, highlight_date='2020-01-01', **shared)
    filler = [news('tnews365', 'current', i, minutes=i, highlight=True, highlight_date='2020-01-01')
              for i in range(40, 72)]
    data = build([older, legacy, marked, *filler])
    assert data['id-index.json'][marked['id']] == 'meta.json'
    assert data['id-index.json'][older['id']] == 'channel/current/merged.json'
    assert legacy['id'] not in data['id-index.json']
    assert details(data)[marked['id']]['merged'][0]['id'] == older['id']
    assert data['id-index.json'][filler[-1]['id']] == 'channel/current/page-2.json'
    assert all('highlight' not in item and 'highlight_date' not in item for item in details(data).values())
    search = {item['id']: item for item in data['search-index.json']['entries']}
    assert set(search) == set(details(data))
    assert all('highlight' not in item and 'highlight_date' not in item for item in search.values())


def test_new_badge_does_not_promote_folded_report(build):
    bbc, mac = reports()
    mac['image'] = img(99)
    primary = news('tnews365', 'current', 81, minutes=1441, title=bbc['title'], url=bbc['url'])
    current_copy = news('freechinese', 'current', 82, minutes=5, title=bbc['title'], url=bbc['url'])
    data = build([bbc, mac, primary, current_copy])
    assert highlighted(data) == {bbc['id'], mac['id'], current_copy['id']}
    assert data['id-index.json'] == {
        bbc['id']: 'channel/world/page-1.json', mac['id']: 'meta.json',
        primary['id']: 'channel/current/page-1.json', current_copy['id']: 'channel/current/merged.json',
    }
    assert details(data)[primary['id']]['merged'][0]['id'] == current_copy['id']


def test_search_fallback_for_historical_item_discards_old_badge(build):
    archived = news('bbc-world', 'world', 201, minutes=3000, highlight=True, highlight_date='2020-01-01')
    data = build([], history=[archived])
    assert archived['id'] not in data['id-index.json']
    entry, = data['search-index.json']['entries']
    assert entry['id'] == archived['id']
    assert entry['display_summary'] == archived['summary']
    assert 'highlight' not in entry and 'highlight_date' not in entry


@pytest.mark.parametrize('title_a,title_b', [
    ('City officially opens New Bridge', 'New Bridge opens to traffic in City'),
    ('The Central Bank cuts its benchmark rate to 6.7%', 'The Central Bank lowers its benchmark rate to 6.7%'),
    ('The Court rules in case 26-CV-471', 'The Court issues a ruling in case 26-CV-471'),
    ('Blue Oak plans releases Slate Studio 7.14.2', 'Blue Oak plans ships Slate Studio 7.14.2'),
    ('青穗未发布云笺 3.8.1', '青穗未推出云笺 v3.8.1 版本'),
])
def test_unidentified_entities_and_non_assertive_headlines_supply_no_vote(build, title_a, title_b):
    a, b = event_reports(title_a, title_b,
                         'The announcement was distributed yesterday afternoon in a written bulletin to the full press list.',
                         'Our correspondent arrived downtown just before the scheduled briefing with local reporters.')
    assert highlighted(build([a, b])) == set()


def test_chinese_court_accepts_domestic_case_number_and_distinguishes_procedure(build):
    a, b = event_reports('澄江法院对（2026）澄01民终219号案件作出裁决',
                         '澄江法院裁决(2026)澄01民终219号案件',
                         '合议庭听取了当事各方陈述后公布书面意见。',
                         '法庭书记员在午后将这份判决书登记进案卷。', lang='zh')
    assert highlighted(build([a, b])) == {a['id'], b['id']}
    assert highlighted(build([a, dict(b, title=b['title'].replace('民终', '民初'))])) == set()


@pytest.mark.parametrize('credit', [
    'Source: BBC News', 'By the Northport Herald newsroom.', 'As reported by the Northport Herald.',
    'The Northport Herald reports that the committee voted today.',
    '来源：松岚日报', '据北港通讯社报道，委员会今天公布了决议。', '采编：松岚日报',
])
def test_explicit_external_attribution_with_an_own_domain_does_not_vote(build, credit):
    title_a, title_b, body_a, body_b, _ = EVENTS[0].values
    a, b = event_reports(title_a, title_b, body_a, body_b)
    b['body'] += '\n' + credit
    assert highlighted(build([a, b])) == set()


@pytest.mark.parametrize('conflict', [
    {'summary': 'The committee actually raised the benchmark rate from 3.25% to 3.5%.'},
    {'blocks': [{'type': 'p', 'text': 'The new rate applies only to overnight loans at participating banks.'}]},
    {'body': '委员会实际把基准利率从3.25%上调至3.5%。'},
    {'summary': 'The board lowered the deposit rate to 3.5%.'},
])
def test_visible_rate_conflict_prevents_corroboration(build, conflict):
    title_a, title_b, body_a, body_b, _ = EVENTS[0].values
    a, b = event_reports(title_a, title_b, body_a, body_b)
    b.update(conflict)
    assert highlighted(build([a, b])) == set()


@pytest.mark.parametrize('actor', ['某地央行', '当地一家央行', '一家地区性央行'])
def test_placeholder_bank_is_not_a_specific_event_actor(build, actor):
    title_a, title_b, body_a, body_b, _ = EVENTS[1].values
    assert highlighted(build(event_reports(title_a.replace('松岚央行', actor),
                                           title_b.replace('松岚央行', actor), body_a, body_b, lang='zh'))) == set()


@pytest.mark.parametrize('ts', [None, '坏时间', 'legacy'])
def test_cached_feed_without_proven_publication_time_cannot_vote(build, tmp_path, ts):
    from rebang.ingest.core import remote_items, source_table

    published = (NOW - timedelta(minutes=5)).isoformat() if ts == 'legacy' else ts
    fetched = (NOW - timedelta(days=3)).isoformat()
    sources = []
    title_a, title_b, body_a, body_b, _ = EVENTS[0].values
    for report in event_reports(title_a, title_b, body_a, body_b):
        sid = report['source_id']
        sources.append(source_table()[sid])
        entry = {'id': report['id'].split(':')[1], 'ts': published, 'title': report['title'],
                 'summary': report['summary'], 'url': report['url']}
        (tmp_path / f'{sid}.json').write_text(json.dumps({'fetched_at': fetched, 'entries': [entry]}))
    items, _ = remote_items(sources, NOW, NOW - timedelta(days=14), fetch=False, cache=tmp_path, http_get=None)
    assert len(items) == 2
    data = build(items)
    assert set(details(data)) == {i['id'] for i in items}
    assert highlighted(data) == set()


def test_legacy_collector_envelope_cannot_use_an_unproven_feed_clock(build):
    a, b = reports()
    data = build([a, b], producer='ingest')
    assert set(details(data)) == {a['id'], b['id']}
    assert highlighted(data) == set()


@pytest.mark.parametrize('date_kind, expected', [
    ('rss', True), ('atom-published', True), ('atom-updated', False), ('atom-no-zone', False),
])
def test_feed_publication_provenance_survives_a_cache_roundtrip(build, tmp_path, date_kind, expected):
    from email.utils import format_datetime
    from xml.sax.saxutils import escape

    from rebang.ingest.core import remote_items, source_table

    posts = reports()
    sources = [source_table()[post['source_id']] for post in posts]
    contents = {}
    for (_, cfg), item in zip(sources, posts):
        title, desc, link = (escape(item[key]) for key in ('title', 'summary', 'url'))
        if date_kind == 'rss':
            contents[cfg['url']] = f'<rss><channel><item><title>{title}</title><link>{link}</link>' \
                f'<description>{desc}</description><pubDate>{format_datetime(NOW)}</pubDate></item></channel></rss>'
        else:
            field = 'updated' if date_kind == 'atom-updated' else 'published'
            date = NOW.replace(tzinfo=None) if date_kind == 'atom-no-zone' else NOW
            contents[cfg['url']] = f'<feed xmlns="http://www.w3.org/2005/Atom"><entry><title>{title}</title>' \
                f'<link href="{link}"/><summary>{desc}</summary><{field}>{date.isoformat()}</{field}></entry></feed>'
    floor = NOW - timedelta(days=14)
    items, _ = remote_items(sources, NOW, floor, fetch=True, cache=tmp_path,
                            http_get=lambda url, _: contents[url].encode())
    cached, _ = remote_items(sources, NOW, floor, fetch=False, cache=tmp_path, http_get=None)
    assert cached == items and len(cached) == 2
    assert highlighted(build(cached, producer='ingest')) == ({i['id'] for i in cached} if expected else set())


@pytest.mark.parametrize('kind', ['rss-source', 'rss-byline', 'atom-source', 'atom-author'])
def test_declared_feed_origin_is_not_lost_before_voting(build, tmp_path, kind):
    from email.utils import format_datetime
    from xml.sax.saxutils import escape
    from rebang.ingest.core import remote_items, source_table

    a, b = reports()
    sources = [source_table()[r['source_id']] for r in (a, b)]
    contents = {}
    for i, (row, (_, cfg)) in enumerate(zip((a, b), sources)):
        title, desc, url = (escape(row[k]) for k in ('title', 'summary', 'url'))
        credit = '' if i == 0 else {
            'rss-source': '<source url="https://bbc.com/rss">BBC News</source>',
            'rss-byline': '<dc:creator>External Wire Desk</dc:creator>',
            'atom-source': '<source><title>BBC News</title></source>',
            'atom-author': '<author><name>External Wire Desk</name></author>',
        }[kind]
        if kind.startswith('rss'):
            xml = (f'<rss xmlns:dc="http://purl.org/dc/elements/1.1/"><channel><item><title>{title}</title>'
                   f'<link>{url}</link><description>{desc}</description><pubDate>{format_datetime(NOW)}</pubDate>'
                   f'{credit}</item></channel></rss>')
        else:
            xml = (f'<feed xmlns="http://www.w3.org/2005/Atom"><entry><title>{title}</title><link href="{url}"/>'
                   f'<summary>{desc}</summary><published>{NOW.isoformat()}</published>{credit}</entry></feed>')
        contents[cfg['url']] = xml.encode()
    floor = NOW - timedelta(days=2)
    fresh, _ = remote_items(sources, NOW, floor, fetch=True, cache=tmp_path, http_get=lambda url, _: contents[url])
    cached, _ = remote_items(sources, NOW, floor, fetch=False, cache=tmp_path, http_get=None)
    assert cached == fresh and len(cached) == 2
    data = build(cached, producer='ingest')
    assert set(details(data)) == {i['id'] for i in fresh}
    assert highlighted(data) == set()
    assert all('feed_attribution' not in item for item in details(data).values())


@pytest.mark.parametrize('group,conflict', [
    (0, 'In the actual decision the benchmark rate rose from 3.25% to 3.5%.'),
    (0, 'The deposit rate was lowered to 3.5% in the morning decision.'),
    (2, 'Harbor Bridge remains closed to traffic in Northport after the latest inspection.'),
    (3, '银湾大桥目前仍处于封闭状态，施工人员还在进行最后一轮检查。'),
    (4, 'The court postponed the ruling in case 26-CV-471 until next month.'),
    (6, 'The release of Slate Studio 7.14.2 was withdrawn after the final checks.'),
    pytest.param(0, 'The committee raised the benchmark rate by 25 basis points today.', id='opposite-delta'),
    pytest.param(1, '央行今天把基准利率上调了二十五个基点。', id='opposite-delta-zh'),
    pytest.param(2, 'Harbor Bridge has yet to open to traffic in Northport.', id='opening-yet-to'),
    pytest.param(6, 'The update has yet to be released to users.', id='release-yet-to'),
    pytest.param(7, '维护方确认新版仍未正式发布，下载入口暂时没有开放。', id='release-still-pending-zh'),
])
def test_visible_facts_can_veto_each_event_class(build, group, conflict):
    t1, t2, text1, text2, _ = EVENTS[group].values
    a, b = event_reports(t1, t2, text1, text2, lang='en' if t1.isascii() else 'zh')
    assert highlighted(build([a, dict(b, body=conflict)])) == set()


@pytest.mark.parametrize('group,statement,expected', [
    pytest.param(0, 'The committee held the benchmark rate at 3.5% after the vote.', False, id='held-rate'),
    pytest.param(0, 'The benchmark rate remained unchanged after the meeting.', False, id='rate-unchanged'),
    pytest.param(0, 'The benchmark rate was kept at 3.5% after a unanimous vote.', False, id='rate-kept-passive'),
    pytest.param(1, '本次会议决定将基准利率维持在4.25%。', False, id='unchanged-zh'),
    pytest.param(0, 'The committee plans to cut the benchmark rate at its next meeting.', False, id='rate-plan'),
    pytest.param(2, 'Harbor Bridge is scheduled to open to traffic next week.', False, id='opening-planned'),
    pytest.param(2, 'The bridge opening is scheduled for next Monday.', False, id='opening-scheduled-for'),
    pytest.param(3, '交通部门确认，银湾大桥将于下周正式通车。', False, id='opening-planned-zh'),
    pytest.param(4, 'The judges will issue a ruling in case 26-CV-471 next Monday.', False, id='ruling-planned'),
    pytest.param(5, '澄江法院拟于下周对该案作出裁决。', False, id='ruling-planned-zh'),
    pytest.param(6, 'Slate Studio version 7.14.2 will be released next week.', False, id='release-planned'),
    pytest.param(6, 'The release of Slate Studio 7.14.2 is scheduled for Monday.', False, id='named-release-scheduled'),
    pytest.param(7, '团队计划在下月正式发布云笺 3.8.1。', False, id='release-planned-zh'),
    # The future action or the unchanged value belongs to something else.
    pytest.param(0, 'The committee held a briefing after cutting the benchmark rate to 3.5%.', True, id='held-briefing'),
    pytest.param(0, 'Bank fees remained unchanged after the cut in the benchmark rate.', True, id='unchanged-fees'),
    pytest.param(0, 'The exchange rate remained unchanged after the cut in the benchmark rate.', True, id='different-rate-held'),
    pytest.param(0, 'The benchmark rate is at 3.5% following the cut announced this morning.', True, id='current-level-is-not-a-hold'),
    pytest.param(1, '央行在本次会议上将基准利率下调至4.25%。', True, id='jiang-as-object-marker'),
    pytest.param(2, 'Now that the bridge is open, the city will publish daily traffic counts.', True, id='traffic-followup'),
    pytest.param(3, '银湾大桥已通车，交通部门将于下周公布通车首日的车流统计。', True, id='traffic-followup-zh'),
    pytest.param(6, 'The developers will open a support forum for people already using the new version.', True, id='support-followup'),
])
def test_hold_or_preview_is_not_a_completed_event(build, group, statement, expected):
    t1, t2, text1, text2, _ = EVENTS[group].values
    a, b = event_reports(t1, t2, text1, text2, lang='en' if t1.isascii() else 'zh')
    # A conflicting sentence may be in an original article block, not its headline or RSS summary.
    b['blocks'] = [{'type': 'p', 'text': statement}]
    data = build([a, b])
    ids = {a['id'], b['id']}
    assert set(details(data)) == ids
    assert highlighted(data) == (ids if expected else set())


def test_preview_does_not_supply_a_vote_or_hide_two_actual_reports(build):
    a, preview = event_reports('Bluewater opens Cedar Line', 'Cedar Line enters service in Bluewater',
                               'Passengers boarded the first train at sunrise and changed at the central station.',
                               'Cedar Line will open to the public next week after the final checks.')
    c = news('npr-world', 'world', 103, title='Bluewater inaugurates Cedar Line', lang='en',
             url='https://www.npr.org/rail/test-opening',
             summary='Drivers started regular service shortly before the morning commute along the full route.')
    assert highlighted(build([a, preview, c])) == {a['id'], c['id']}


def test_rate_delta_is_not_the_final_rate_and_unrelated_rises_are_not_a_veto(build):
    t1, t2, text1, _, _ = EVENTS[0].values
    a, b = event_reports(t1, t2, text1, 'Employment rose last quarter. The committee cut the benchmark rate by 25 basis points today.')
    assert highlighted(build([a, b])) == {a['id'], b['id']}


def test_private_meeting_is_not_a_closed_bridge(build):
    t1, t2, text1, text2, _ = EVENTS[2].values
    a, b = event_reports(t1, t2, text1, 'After a closed session, ' + text2)
    assert highlighted(build([a, b])) == {a['id'], b['id']}


def collect_fold_fixture(tmp_path, collector, monkeypatch):
    import sqlite3

    db = tmp_path / 'synthetic.db'
    with sqlite3.connect(db) as con:
        con.execute('create table msg (ch text, id int, ts text, text text)')
        con.executemany('insert into msg values (?, ?, ?, ?)', [
            ('tnews365', 1, (NOW - timedelta(minutes=9)).isoformat(), '岚城区交通简报\n两岸今日恢复通行。'),
            ('freechinese', 2, (NOW - timedelta(minutes=4)).isoformat(), '岚城区交通简报\n当地早间开放了施工路段。'),
        ])
    # Keep the real SQLite adapter and supply distinct tracking variants of the
    # same original article link before the historical matcher sees the items.
    telegram_items = collector.telegram_items
    link = 'https://example.com/synthetic-fold'

    def adapted_telegram_items(*args, **kwargs):
        items, statuses = telegram_items(*args, **kwargs)
        for item in items:
            item['url'] = link if item['id'] == 'freechinese:2' else link + '?utm_source=older'
        return items, statuses

    monkeypatch.setattr(collector, 'telegram_items', adapted_telegram_items)
    issues = [({'date': NOW.date().isoformat(), 'sections': [{'items': [{'link': link}]}]}, tmp_path)]
    env = collector.collect(NOW, db=db, cache=tmp_path / 'cold-cache', translator=None,
                            inbox_loader=lambda sid: issues if sid == 'hot-daily' else [])
    assert {item['id'] for item in env['items']} == {'tnews365:1', 'freechinese:2'}
    return env['items']


def test_recollection_keeps_legacy_primary_and_detail_routes(build, tmp_path, monkeypatch):
    from rebang.ingest import core

    collected = collect_fold_fixture(tmp_path, core, monkeypatch)
    assert all('highlight' not in item and 'highlight_date' not in item for item in collected)
    data = build(collected)
    assert data['id-index.json'] == {
        'freechinese:2': 'channel/current/page-1.json', 'tnews365:1': 'channel/current/merged.json',
    }
    resolved = details(data)
    assert [i['id'] for i in resolved['freechinese:2']['merged']] == ['tnews365:1']
    assert all(i['body'] == next(c['body'] for c in collected if c['id'] == ident) for ident, i in resolved.items())
    assert highlighted(data) == set()


def test_unchanged_recollection_leaves_the_archived_day_byte_identical(build, tmp_path):
    published = NOW - timedelta(days=3)
    first = news('bbc-world', 'world', 203, published_at=published.isoformat(), fetched_at=published.isoformat(),
                 highlight=True, highlight_date=published.date().isoformat())
    latest = dict(first, body='上次改稿时已经归档的正文。', fetched_at=(published + timedelta(hours=1)).isoformat())
    build([latest], history=[first])
    day = tmp_path / 'archive' / f'{published.date()}.json'
    before = day.read_bytes()
    assert json.loads(before)['items'] == [{'id': first['id'], 'first': first, 'latest': latest}]

    # 下一轮只是重抓，并非改稿。页面用新抓取时间、去旧标；不能因此触碰归档里的任何版本。
    incoming = {k: v for k, v in latest.items() if k not in ('highlight', 'highlight_date')}
    incoming.update(fold_preferred=True, published_at_verified=True, fetched_at=NOW.isoformat())
    data = build([incoming], producer='ingest')
    public = details(data)[first['id']]
    assert public['fetched_at'] == incoming['fetched_at'] and highlighted(data) == set()
    assert 'highlight_date' not in public and 'fold_preferred' not in public
    assert day.read_bytes() == before


def test_telegram_recollection_distinguishes_capture_time_from_changed_data(build, tmp_path):
    from rebang.tgmeta import merge_meta

    published = NOW - timedelta(days=2)
    old = news('tnews365', 'current', 204, published_at=published.isoformat(), highlight=True,
               highlight_date=published.date().isoformat(),
               tg=merge_meta({'views': 10, 'fetched_at': published.isoformat()})['tg'])
    build([], history=[old])
    path = tmp_path / 'archive' / f'{published.date()}.json'
    before = path.read_bytes()
    recapture = {k: v for k, v in old.items() if k not in ('highlight', 'highlight_date')}
    recapture['tg'] = merge_meta({'views': 10, 'fetched_at': NOW.isoformat()})['tg']
    assert not highlighted(build([recapture]))
    assert path.read_bytes() == before

    recapture['tg'] = merge_meta({'views': 11, 'fetched_at': NOW.isoformat()})['tg']
    build([recapture])
    record, = json.loads(path.read_bytes())['items']
    assert record['first'] == old and record['latest'] == recapture


def test_same_id_rebuild_preserves_legacy_history_and_accepts_body_updates(build, tmp_path):
    published = NOW - timedelta(days=3)
    old = news('bbc-world', 'world', 202, published_at=published.isoformat(), body='首次正文。',
               highlight=True, highlight_date=published.date().isoformat())
    archive = tmp_path / 'archive' / f'{published.date()}.json'
    assert highlighted(build([old], history=[old])) == set()
    record, = json.loads(archive.read_text())['items']
    assert record['first'] == record['latest'] == old

    # Recollection no longer emits the old marker. A real revision still follows
    # the archive's normal first/latest rules.
    revised = {k: v for k, v in old.items() if k not in ('highlight', 'highlight_date')}
    revised.update(body='补充了新的正文细节。', summary='更新后的摘要。', fetched_at=NOW.isoformat())
    build([revised])
    record, = json.loads(archive.read_text())['items']
    assert record['first'] == old and record['latest'] == revised
    fallback = build([])
    entry, = fallback['search-index.json']['entries']
    assert old['id'] not in fallback['id-index.json']
    assert entry['display_summary'] == revised['summary']
    assert 'highlight' not in entry and 'highlight_date' not in entry
