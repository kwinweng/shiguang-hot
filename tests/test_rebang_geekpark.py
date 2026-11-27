"""Offline coverage for the GeekPark feed and its public article view."""
import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

import pytest

from rebang.archive import build as build_archive
from rebang.contract import validate_items_envelope
from rebang.extract import ExtractCache
from rebang.ingest import collect
from rebang.site import builder
from rebang.translate import Cache, Translator
from tests.rebang_site_testdata import envelope, news

FEED = 'https://www.geekpark.net/rss'
ARTICLE = 'https://www.geekpark.net/news/100001'
FIXTURE = Path(__file__).parent / 'fixtures/rebang/ingest/geekpark-rss.xml'
NOW = datetime(2026, 11, 27, 3, tzinfo=timezone.utc)
DIGEST = '两款新手机发布，机器人公司融资｜极客早知道'


@pytest.fixture
def collect_feed(tmp_path):
    cache = tmp_path / 'ingest-cache'
    translation_cache = tmp_path / 'translate/cache.json'
    translator = Translator(engine='cache', cache=Cache(translation_cache))
    requests = []

    def run(xml=None, *, fetch=True):
        def get(url, now):
            if urlsplit(url).hostname == 'www.geekpark.net':
                requests.append(url)
            if url == FEED:
                return xml if xml is not None else FIXTURE.read_bytes()
            raise OSError('offline')

        return collect(NOW, fetch=fetch, db=tmp_path / 'absent.db', cache=cache, http_get=get,
                       inbox_loader=lambda sid: (),
                       translator=(translator.translate_detailed, translator.engine, translator.save))

    return run, cache, translation_cache, requests


def test_geekpark_keeps_reviews_and_filters_morning_roundups(collect_feed):
    run, _, _, _ = collect_feed
    result = run()
    assert validate_items_envelope(result) == []
    assert [i['id'] for i in result['items']] == ['geekpark:depth', 'geekpark:review']
    assert {i['channel'] for i in result['items']} == {'tech-ai'}
    status = next(s for s in result['sources'] if s['id'] == 'geekpark')
    assert (status['status'], status['count']) == ('ok', 2)


@pytest.mark.parametrize('title', ['极客早报：今天的科技新闻', '【早报】今天的科技新闻', '新闻汇总 | 早报'])
def test_geekpark_recognizes_early_brief_title_markers(collect_feed, title):
    run, _, _, _ = collect_feed
    xml = FIXTURE.read_text().replace(DIGEST, title).encode()
    assert [i['id'] for i in run(xml)['items']] == ['geekpark:depth', 'geekpark:review']


def test_geekpark_is_explicitly_chinese_and_skips_translation(collect_feed):
    run, _, translation_cache, _ = collect_feed
    result = run()
    # The legacy title heuristic treats a wholly quoted Chinese title as English.
    assert result['items'][0]['title'] == '《把模型装进口袋》'
    assert {i['lang'] for i in result['items']} == {'zh'}
    assert result['translation']['translated'] == 0
    assert Cache(translation_cache).pending == {}

    # A publisher-supplied product name can trip the stricter web language gate.
    xml = FIXTURE.read_text().replace('《把模型装进口袋》', 'Example Product Name 实测').encode()
    assert run(xml)['items'][0]['lang'] == 'zh'
    assert Cache(translation_cache).pending == {}


def test_geekpark_keeps_plain_short_summaries_and_never_fetches_articles(collect_feed):
    run, cache, _, requests = collect_feed
    result = run()
    assert requests == [FEED]
    assert result['extraction']['considered'] == 0
    depth, review = result['items']
    assert depth['summary'].startswith('我们比较了端侧模型的两种实现。')
    assert depth['summary'].endswith('…') and len(depth['summary']) == 301
    assert review['summary'].replace(' ', '') == '我们在地铁上试用了离线模式。'
    for item in result['items']:
        assert item['source_name'] == '极客公园'
        assert item['image'] is None and 'body' not in item and 'blocks' not in item
    saved = (cache / 'geekpark.json').read_text()
    assert 'images.example.test' not in saved and '此句只出现在长描述尾部' not in saved


def test_geekpark_cached_feed_drops_images_and_never_reuses_extracted_body(collect_feed):
    run, cache, _, _ = collect_feed
    fresh = run()
    path = cache / 'geekpark.json'
    saved = json.loads(path.read_text())
    saved['entries'][0]['summary'] += '此前缓存的长描述' * 100
    saved['entries'][0]['image'] = 'https://images.example.test/old.jpg'
    path.write_text(json.dumps(saved))
    extracts = ExtractCache(cache / 'extract/pages.json')
    extracts.put(ARTICLE, {'ok': True, 'body': '已缓存的长正文。' * 100,
                           'blocks': [{'type': 'img', 'src': 'https://images.example.test/extracted.jpg'}]})
    extracts.save()
    result = run(fetch=False)
    depth = result['items'][0]
    assert result['extraction']['considered'] == 0
    assert depth['image'] is None and 'body' not in depth and 'blocks' not in depth
    assert len(depth['summary']) == len(fresh['items'][0]['summary'])


def test_geekpark_mixed_titles_open_from_channel_fold_and_deep_link(collect_feed, tmp_path, monkeypatch):
    run, _, _, _ = collect_feed
    xml = (FIXTURE.read_text().replace('《把模型装进口袋》', 'Example Product Name 实测')
           .replace('实测一周，早报应用的离线阅读怎么样？', 'Another Product Name 实测'))
    start = xml.index('    <item>')
    end = xml.index('    </item>', start) + len('    </item>')
    result = run((xml[:end] + '\n' + xml[start:end] + xml[end:]).encode())
    assert [i['id'] for i in result['items']] == ['geekpark:depth', 'geekpark:review']
    depth, review = result['items']
    existing = news('zaihuapd', 'tech-ai', 1, url=ARTICLE, title=depth['title'],
                    published_at='2026-11-27T08:50:00+08:00')
    inp, out = tmp_path / 'in', tmp_path / 'site'
    inp.mkdir()
    (inp / 'ingest.json').write_text(json.dumps(result))
    (inp / 'existing.json').write_text(json.dumps(envelope([existing])))
    monkeypatch.setattr(builder, '_run_archive', lambda items, dest, report: build_archive(items, dest, tmp_path / 'archive'))
    report = builder.build(out, inp, now=NOW, hot_archive_dir=None)

    playwright = pytest.importorskip('playwright.sync_api')
    with playwright.sync_playwright() as pw, pw.chromium.launch() as browser:
        page = browser.new_page()

        def serve(route):
            url = urlsplit(route.request.url)
            path = out / url.path.lstrip('/')
            if url.netloc == 'rebang.test' and path.is_file():
                route.fulfill(path=path)
            else:
                route.abort()

        page.route('**/*', serve)
        page.goto('https://rebang.test/index.html')
        page.locator('#app:not([aria-busy])').wait_for()
        page.locator('#chBtn').click()
        page.locator('#dropList button').filter(has_text='科技').click()
        row = page.locator(f'.feed-row[data-id="{review["id"]}"]')
        playwright.expect(row.locator('h3')).to_have_text(review['title'])
        row.click()
        playwright.expect(page.locator('.art-title')).to_have_text(review['title'])
        page.locator('#btnBack').click()
        primary = page.locator(f'.feed-row[data-id="{existing["id"]}"]')
        primary.locator('.dup-btn').click()
        folded = primary.locator(f'[data-dup-id="{depth["id"]}"]')
        playwright.expect(folded.locator('.t')).to_have_text(depth['title'])
        folded.click()
        playwright.expect(page.locator('.art-title')).to_have_text(depth['title'])

        page.goto('about:blank')
        page.goto('https://rebang.test/index.html#/item/geekpark%3Adepth')
        playwright.expect(page.locator('.art-title')).to_have_text(depth['title'])
        playwright.expect(page.locator('.art-text')).to_have_text(depth['summary'])
        playwright.expect(page.locator('.d-who .nm')).to_have_text('极客公园')
        original = page.get_by_role('link', name='打开原文')
        playwright.expect(original).to_have_attribute('href', ARTICLE)
        playwright.expect(page.locator('.cover, .art-blocks, .art-pending, [data-art-orig]')).to_have_count(0)

    assert report['channels']['tech-ai']['merged'] == 1
    merged = json.loads((out / 'data/channel/tech-ai/merged.json').read_text())['items']
    assert [i['id'] for i in merged] == [depth['id']]
    assert merged[0]['summary'] == depth['summary']
    assert merged[0]['image'] is None and 'body' not in merged[0] and 'blocks' not in merged[0]
