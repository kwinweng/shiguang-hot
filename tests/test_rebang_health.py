"""Offline coverage of the public source-health snapshot."""
import json
import sqlite3
from datetime import timedelta

import pytest

from rebang.contract import load_bloggers, load_channels
from rebang.ingest.core import collect
from rebang.site import builder
from tests.rebang_site_testdata import NOW, envelope


@pytest.fixture
def health_files(tmp_path):
    root = tmp_path / 'in'
    root.mkdir()
    old = (NOW - timedelta(days=3)).isoformat()
    current = NOW.isoformat()
    raw = 'https://private.invalid/api?token=SEKRIT /Users/private/.config/session'
    news = dict(envelope([], 'ingest'), sources=[
        {'id': 'tnews365', 'status': 'ok', 'count': 24, 'collection_ok': False,
         'fetched_at': current, 'last_ok_at': old, 'error': raw},
        {'id': 'bbc-world', 'status': 'error', 'count': 15, 'fetched_at': old, 'error': 'network'},
        {'id': 'guardian-world', 'status': 'cached', 'count': 22, 'fetched_at': old},
        {'id': 'apple-newsroom', 'status': 'empty', 'count': 0, 'fetched_at': current},
        {'id': 'google-blog', 'status': 'not_fetched', 'count': 0},
        {'id': 'hot-daily', 'status': 'ok', 'count': 0, 'fetched_at': current},
    ])
    names = {p['id']: [a['handle'] for a in p['accounts']] for p in load_bloggers()['platforms']}
    blogs = dict(envelope([], 'bloggers'), platforms=[
        {'id': 'weibo', 'status': 'ok', 'accounts': [
            {'handle': names['weibo'][0], 'status': 'ok', 'last_ok_at': current, 'count': 10, 'new': 4},
            {'handle': names['weibo'][1], 'status': 'login_expired', 'last_ok_at': old, 'count': 8,
             'error': 'weibo_cookie_expired', 'reason': raw, 'detail': raw, 'via': raw},
        ]},
        {'id': 'x', 'status': 'ok', 'accounts': [
            {'handle': names['x'][0], 'status': 'ok', 'last_ok_at': current, 'dump_at': old, 'count': 10, 'new': 2},
            {'handle': names['x'][1], 'status': 'error', 'error': 'x_dump_stale', 'dump_at': old, 'count': 0},
        ]},
        {'id': 'youtube', 'status': 'empty', 'accounts': [
            {'handle': handle, 'status': 'empty', 'last_ok_at': current, 'count': 0} for handle in names['youtube']
        ]},
    ])
    for entry in (news, blogs):
        (root / f'{entry["producer"]}.json').write_text(json.dumps(entry), encoding='utf-8')
    output = tmp_path / 'site'
    builder.build(output, root, now=NOW, hot_archive_dir=tmp_path / 'hot')
    return output / 'data'


@pytest.fixture
def health(health_files):
    return json.loads((health_files / 'health.json').read_text())


def test_health_contract_covers_news_channels_and_blogger_platforms(health):
    from rebang.contract import HEALTH_SCHEMA

    assert health['schema'] == HEALTH_SCHEMA
    assert health['generated_at'] == NOW.isoformat()
    assert {r['id']: r['group'] for r in health['sources'] if 'accounts' not in r} == {
        s['id']: c['name'] for c in load_channels()['channels'] for s in c['sources']
    }
    assert {r['id']: len(r['accounts']) for r in health['sources'] if 'accounts' in r} == {
        p['id']: len(p['accounts']) for p in load_bloggers()['platforms']
    }
    assert next(r for r in health['sources'] if r['id'] == 'zhihu')['status'] == 'not_configured'


def test_news_health_reuses_latest_run_and_retained_count(health):
    news = {r['id']: r for r in health['sources'] if 'accounts' not in r}
    old = (NOW - timedelta(days=3)).isoformat()
    assert (news['tnews365']['status'], news['tnews365']['last_ok_at'], news['tnews365']['count']) == ('failed', old, 24)
    assert (news['bbc-world']['status'], news['bbc-world']['last_ok_at'], news['bbc-world']['run_count']) == ('failed', old, 0)
    assert news['guardian-world']['status'] == 'stale'
    assert news['guardian-world']['run_count'] is None
    assert news['apple-newsroom']['status'] == 'ok'
    assert news['google-blog']['status'] == 'not_configured'


def test_platform_rollup_exposes_partial_failure_and_x_dump_age(health):
    platforms = {r['id']: r for r in health['sources'] if 'accounts' in r}
    assert (platforms['weibo']['status'], platforms['weibo']['last_ok_at'], platforms['weibo']['count']) == (
        'login_expired', NOW.isoformat(), 18)
    assert platforms['weibo']['run_count'] == 4
    assert platforms['weibo']['issue_since'] == (NOW - timedelta(days=3)).isoformat()
    assert platforms['x']['status'] == 'stale'
    assert platforms['x']['issue_since'] == (NOW - timedelta(days=3)).isoformat()
    assert platforms['youtube']['status'] == 'ok'


def test_health_omits_raw_errors_configuration_and_input_metadata(health):
    text = json.dumps(health, ensure_ascii=False)
    for value in ('SEKRIT', 'private.invalid', '/Users/', 'http', 'Cookie', 'detail', 'via'):
        assert value not in text
    rows = {r['id']: r for r in health['sources']}
    assert rows['tnews365']['reason'] == 'Telegram 本轮采集失败'
    assert rows['bbc-world']['reason'] == '网络连接失败'


def test_tg_success_survives_an_overwritten_failed_status(tmp_path):
    database = tmp_path / 'fixture.sqlite'
    cache = tmp_path / 'cache'
    with sqlite3.connect(database) as con:
        con.execute('create table msg(ch text, id int, ts text, text text)')
        con.execute('create table status(ch text primary key, ok int, err text, at text)')
        con.execute('insert into status values (?, ?, ?, ?)', ('tnews365', 1, None, NOW.isoformat()))
        con.commit()
        first = collect(NOW, db=database, cache=cache, inbox_loader=lambda _: [], translator=None)
        later = NOW + timedelta(hours=1)
        con.execute('update status set ok=0, err=?, at=?', ('private error', later.isoformat()))
    second = collect(later, db=database, cache=cache, inbox_loader=lambda _: [], translator=None)
    row = lambda result: next(r for r in result['sources'] if r['id'] == 'tnews365')
    assert row(first)['last_ok_at'] == NOW.isoformat()
    assert row(second)['last_ok_at'] == NOW.isoformat()
    assert row(second)['collection_ok'] is False


def test_home_metadata_summarizes_the_same_top_level_sources(health_files, health):
    meta = json.loads((health_files / 'meta.json').read_text())
    rows = health['sources']
    assert meta['health_summary'] == {'total': len(rows), 'issues': sum(row['status'] != 'ok' for row in rows)}
    assert set(meta['health_summary']) == {'total', 'issues'}


def test_health_rejects_bad_times_and_distinguishes_unknown_status():
    from rebang.site.health import build_health

    future = (NOW + timedelta(hours=1)).isoformat()
    old = (NOW - timedelta(hours=40)).isoformat()
    handle = next(p for p in load_bloggers()['platforms'] if p['id'] == 'x')['accounts'][0]['handle']
    for dump_at in (None, 'broken', future, old):
        result = build_health([('test.json', {
            'sources': [
                {'id': 'bbc-world', 'status': 'ok', 'fetched_at': future},
                {'id': 'guardian-world', 'status': 'ok', 'fetched_at': '9999-12-31T23:00:00+00:00'},
                {'id': 'apple-newsroom', 'status': 'new-state', 'fetched_at': NOW.isoformat()},
                {'id': 'google-blog', 'status': 'not_fetched'},
            ],
            'platforms': [{'id': 'x', 'accounts': [
                {'handle': handle, 'status': 'error', 'error': 'x_dump_stale', 'last_ok_at': old, 'dump_at': dump_at},
            ]}],
        })], [], NOW)
        rows = {r['id']: r for r in result['sources']}
        for sid in ('bbc-world', 'guardian-world'):
            assert (rows[sid]['status'], rows[sid]['last_ok_at']) == ('failed', None)
        assert rows['apple-newsroom']['status'] == 'unknown'
        assert rows['google-blog']['status'] == 'not_configured'
        x = next(r for r in rows['x']['accounts'] if r['id'] == f'x-{handle}')
        assert x['status'] == ('stale' if dump_at == old else 'failed')
        assert ('超过 36 小时' in x['reason']) == (dump_at == old)


def test_ingest_ignores_extreme_and_future_telegram_success_times(tmp_path):
    db = tmp_path / 'fixture.sqlite'
    cache = tmp_path / 'cache'
    cache.mkdir()
    future = (NOW + timedelta(days=2)).isoformat()
    (cache / 'telegram-health.json').write_text(json.dumps({'tnews365': future}))
    with sqlite3.connect(db) as con:
        con.execute('create table msg(ch text, id int, ts text, text text)')
        con.execute('create table status(ch text primary key, ok int, err text, at text)')
        con.execute('insert into status values (?, ?, ?, ?)', ('tnews365', 1, None, '9999-12-31T23:00:00+00:00'))
    options = dict(db=db, cache=cache, inbox_loader=lambda _: [], translator=None)
    result = collect(NOW, **options)
    row = next(r for r in result['sources'] if r['id'] == 'tnews365')
    assert row['last_ok_at'] is None
    assert json.loads((cache / 'telegram-health.json').read_text()) == {}
    with sqlite3.connect(db) as con:
        con.execute('update status set at=?', (NOW.isoformat(),))
    result = collect(NOW, **options)
    assert next(r for r in result['sources'] if r['id'] == 'tnews365')['last_ok_at'] == NOW.isoformat()
