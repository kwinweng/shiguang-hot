import json

import pytest

from rebang.archive import build as build_archive
from rebang.chinese_news import needs_translation, public_item
from rebang.ingest.core import apply_translation
from rebang.site import builder
from tests.rebang_site_testdata import NOW, envelope, img, news


def article(n, **overrides):
    return news('bbc-world', 'world', n, title='English headline', summary='English summary',
                body='English article body', image=img(n), lang='en', **overrides)


def translation(title='合成译文标题', summary='合成译文摘要', **fields):
    return {'title': title, 'summary': summary, 'summary_source': 'English summary',
            'engine': 'test', 'label': '机器翻译', **fields}


def read(path):
    return json.loads(path.read_text())


def test_public_build_holds_untranslated_web_items_including_legacy_search(tmp_path, monkeypatch):
    archive = tmp_path / 'archive'
    legacy = article(5)
    # Seed pre-gate history directly; it must remain private and unchanged.
    archive.mkdir()
    day = archive / '2026-11-15.json'
    day.write_text(json.dumps({'date': '2026-11-15', 'items': [
        {'id': legacy['id'], 'first': legacy, 'latest': legacy}]}))
    monkeypatch.setattr(builder, '_run_archive', lambda items, out, report: build_archive(items, out, archive))
    inp, out = tmp_path / 'in', tmp_path / 'out'
    inp.mkdir()
    missing = article(1)
    echo = article(2, translated=True, translation=translation(title='English headline'))
    partial = article(3, translated=True, translation=translation(summary=''))
    ready = article(4, translated=True, translation=translation(body='English article body'))
    for item in (missing, echo, partial, ready):
        # If a bad rendition gets through it can be a banner, a folded row or a search result.
        item['url'] = ready['url']
    (inp / 'ingest.json').write_text(json.dumps(envelope([missing, echo, partial, ready])))
    builder.build(out, inp, now=NOW, web_dir=None, hot_archive_dir=None)
    data = out / 'data'
    assert set(read(data / 'id-index.json')) == {ready['id']}
    assert {entry['id'] for entry in read(data / 'search-index.json')['entries']} == {ready['id']}
    world = next(c for c in read(data / 'meta.json')['channels'] if c['slug'] == 'world')
    assert world['total'] == 1
    published = world['banner'][0]
    assert published['body'] == 'English article body'  # only available through explicit original control
    assert published['translation'].get('body') is None
    assert published['translation']['body_pending'] is True
    assert any(r['id'] == legacy['id'] for r in read(day)['items'])


@pytest.mark.parametrize('title', ['Example Product Name 实测', 'Example Product Name', '中文标题'])
def test_configured_chinese_source_uses_native_title_without_item_language(title):
    raw = news('geekpark', 'tech-ai', 1, title=title, lang='en', body='')
    assert not needs_translation(raw)
    assert public_item(raw) == raw
    assert public_item(dict(raw, summary='An untranslated preview.')) is None
    assert public_item(dict(raw, body='An untranslated whole paragraph.'))['translated'] is False


def test_configured_chinese_previews_reach_banner_channel_fold_and_archive(tmp_path, monkeypatch):
    archive = tmp_path / 'archive'
    monkeypatch.setenv('REBANG_TRANSLATE_CACHE', str(tmp_path / 'translation/cache.json'))
    monkeypatch.setattr(builder, '_run_archive', lambda items, out, report: build_archive(items, out, archive))
    inp, out = tmp_path / 'in', tmp_path / 'out'
    inp.mkdir()
    banner = news('geekpark', 'tech-ai', 1, title='Example Product Name 实测', image=img(1), body='')
    feed = news('geekpark', 'tech-ai', 2, title='Another Product Name', body='')
    folded = news('geekpark', 'tech-ai', 3, title='中文报道', body='')
    primary = news('zaihuapd', 'tech-ai', 4, url=folded['url'], title=folded['title'], fold_preferred=True)
    spoof = dict(article(5), lang='zh', title='Example Product Name 实测', summary='中文摘要')
    archived = news('geekpark', 'tech-ai', 6, title='Archived Product Name 实测', body='')
    build_archive([archived, spoof], tmp_path / 'seed', archive)
    (inp / 'ingest.json').write_text(json.dumps(envelope([banner, feed, folded, primary, spoof])))
    builder.build(out, inp, now=NOW, web_dir=None, hot_archive_dir=None)
    data = out / 'data'
    assert read(data / 'id-index.json') == {
        banner['id']: 'meta.json', feed['id']: 'channel/tech-ai/page-1.json',
        folded['id']: 'channel/tech-ai/merged.json', primary['id']: 'channel/tech-ai/page-1.json',
    }
    tech = next(c for c in read(data / 'meta.json')['channels'] if c['slug'] == 'tech-ai')
    assert [item['title'] for item in tech['banner']] == [banner['title']]
    feed_items = {item['id']: item for item in read(data / 'channel/tech-ai/page-1.json')['items']}
    assert feed_items[feed['id']]['title'] == feed['title']
    assert feed_items[primary['id']]['merged'][0]['chinese_release'] is True
    assert [item['title'] for item in read(data / 'channel/tech-ai/merged.json')['items']] == [folded['title']]
    entries = read(data / 'search-index.json')['entries']
    assert {entry['id']: entry['display_title'] for entry in entries} == {
        item['id']: item['title'] for item in (banner, feed, folded, primary, archived)
    }


def test_archive_only_uses_current_safe_rendition_for_same_id(tmp_path):
    archive, out = tmp_path / 'archive', tmp_path / 'out'
    good = article(1, translated=True, translation=translation())
    build_archive([good], out, archive)
    assert len(read(out / 'data/search-index.json')['entries']) == 1
    build_archive([article(1)], out, archive)
    assert read(out / 'data/search-index.json')['entries'] == []


def test_archived_only_item_recovers_from_exact_field_cache_without_rewriting_history(tmp_path, monkeypatch):
    from rebang.translate import Cache

    filename = tmp_path / 'translation/cache.json'
    monkeypatch.setenv('REBANG_TRANSLATE_CACHE', str(filename))
    archive, out = tmp_path / 'archive', tmp_path / 'out'
    raw = article(1)
    build_archive([raw], out, archive)
    day = archive / '2026-11-15.json'
    original = day.read_bytes()
    assert read(out / 'data/search-index.json')['entries'] == []
    cache = Cache(filename)
    cache.put(raw['title'], 'en', '补回的中文标题', 'test')
    cache.put(raw['summary'] + ' changed', 'en', '不能用于旧稿的译文', 'test')
    cache.save()
    build_archive([], out, archive)
    assert read(out / 'data/search-index.json')['entries'] == []
    cache.put(raw['summary'], 'en', '补回的中文摘要', 'test')
    cache.save()
    build_archive([], out, archive)
    (entry,) = read(out / 'data/search-index.json')['entries']
    assert entry['display_title'] == '补回的中文标题'
    assert entry['display_summary'] == '补回的中文摘要'
    assert day.read_bytes() == original


def test_archive_cache_lookup_uses_repair_slot_with_or_without_bad_shared_entry(tmp_path):
    from rebang.archive.build import _cache_lookup
    from rebang.translate import Cache

    for shared in (None, 'English headline'):
        cache = Cache(tmp_path / f'{bool(shared)}/cache.json')
        if shared:
            cache.put('English headline', 'en', shared, 'test')
        assert _cache_lookup(cache, 'English headline') is None
        cache.put('English headline', 'en-x-web-repair', '修复槽中文标题', 'test')
        assert _cache_lookup(cache, 'English headline')['zh'] == '修复槽中文标题'
    cache.put('English headline', 'en', '共享槽中文标题', 'test')
    assert _cache_lookup(cache, 'English headline')['zh'] == '共享槽中文标题'


def test_ingest_retries_a_sticky_partial_render_when_summary_becomes_available(tmp_path):
    texts = {'English headline': '合成译文标题'}

    def fake(batch, src):
        return [texts.get(t) for t in batch]

    first, second = article(1), article(1)
    apply_translation([first], (fake, 'test'), tmp_path)
    assert first['translation']['summary'] == ''
    texts['English summary'] = '合成译文摘要'
    apply_translation([second], (fake, 'test'), tmp_path)
    assert second['translation']['summary'] == '合成译文摘要'


def test_mixed_language_website_uses_original_only_when_default_fields_are_chinese():
    from rebang.chinese_news import public_item

    original = dict(article(1), lang='zh', title='这是一条中文新闻', summary='', body='https://example.com')
    assert public_item(original) == original
    assert public_item(dict(original, summary='A preview still written in English')) is None
    assert public_item(dict(original, body='中文导语。\nAn untranslated whole paragraph.'))['translated'] is False
    candidate = dict(article(1), translated=True,
                     translation=translation(body='这是中文全文。', blocks=[{'type': 'p', 'text': 'English body'}]))
    safe = public_item(candidate)
    assert safe['translation']['body'] == '这是中文全文。'
    assert 'blocks' not in safe['translation']
    assert 'blocks' in candidate['translation']
    pre = [{'type': 'p', 'text': '下面是安装命令。'}, {'type': 'pre', 'text': 'npm install example'}]
    chinese_with_code = dict(original, blocks=pre, body='下面是安装命令。\n\nnpm install example')
    safe_code = public_item(chinese_with_code)
    assert safe_code['title'] == chinese_with_code['title']
    assert not safe_code['translated']  # frontend shows the code only under explicit original expansion
    for echo in ('OpenAI launches new model in 中国人工智能市场', 'OpenAI Launches New Model In 中国人工智能市场'):
        assert public_item(dict(candidate, summary=echo, translation=translation(summary=echo, summary_source=echo))) is None
        assert public_item(dict(candidate, body=echo, translation=translation(body=echo)))['translation']['body_pending']
    stale = translation(summary='第一段。第二段。')
    stale.pop('summary_source')
    assert public_item(dict(candidate, summary='First paragraph.', translation=stale)) is None


def test_github_repository_identifier_with_usable_chinese_preview_needs_no_translation():
    from rebang.chinese_news import public_item

    repo = news('github-trending', 'tools', 7, lang='zh', title='example/project',
                summary='这是中文项目简介。', body='这是中文正文。')
    assert public_item(repo) == repo
    assert public_item(dict(repo, summary='An English project summary')) is None


def test_translated_fulltext_does_not_replace_translation_of_shorter_summary(tmp_path):
    from rebang.chinese_news import public_item

    raw = dict(article(1), summary='First paragraph.', body='First paragraph.\nSecond paragraph.')
    translated = {'English headline': '合成译文标题', raw['body']: '第一段。第二段。'}
    apply_translation([raw], (lambda batch, src: [translated.get(t) for t in batch], 'test'), tmp_path)
    assert raw['translation']['body'] == '第一段。第二段。'
    assert raw['translation']['summary'] == ''
    assert public_item(raw) is None


def test_bad_shared_cache_requeues_web_field_once_without_overwriting_other_consumers(tmp_path):
    from rebang.translate import Cache, Translator, list_pending

    filename = tmp_path / 'cache.json'
    cache = Cache(filename)
    cache.put('English summary', 'en', 'English summary', 'test')
    cache.save()
    translator = Translator('cache', cache=Cache(filename))
    assert translator.translate_detailed(['English summary'], 'en', ['web:summary']) is None
    translator.save()
    cache = Cache(filename)
    (row,) = list_pending(cache)
    assert row['kind'] == 'summary'
    assert row['src_lang'] != 'en'
    cache.put(row['src'], row['src_lang'], '合成中文摘要。', 'test')
    cache.save()
    translator = Translator('cache', cache=Cache(filename))
    assert translator.translate_detailed(['English summary'], 'en', ['web:summary'])[0] == ['合成中文摘要。']
    assert translator.translate_detailed(['English summary'], 'en', ['summary'])[0] == ['English summary']
    assert list_pending(translator.cache) == []
