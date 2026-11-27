import json

from rebang.archive import build as build_archive
from rebang.contract import validate_items_envelope
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


def test_mixed_web_items_survive_ingest_contract_and_publish_with_chinese_previews(tmp_path, monkeypatch):
    repo = news('github-trending', 'tools', 1, lang='zh', title='example/project',
                summary='这是中文项目简介。', body='This repository has an English readme.')
    native_repo = news('github-trending', 'tools', 2, lang='zh', title='example/other',
                       summary='另一个中文项目。', body='')
    mixed = dict(article(3), lang='zh-Hant', title='中文新聞標題', summary='中文新聞摘要。',
                 body='This report is written in English.',
                 blocks=[{'type': 'p', 'text': 'This report is written in English.'}])
    mixed_summary = dict(article(4), lang='zh', title='中文标题配外文摘要',
                         summary='English report on the Chinese market 中国市场', body='中文正文已经就绪。')
    english = dict(article(5), source_id='google-blog', channel='tech-ai', id='google-blog:5',
                   summary='已有中文摘要。')
    held = dict(article(6), lang='zh', title='本条摘要尚未就绪', summary='This preview is not translated.', body='')
    items = [repo, native_repo, mixed, mixed_summary, english, held]
    texts = {repo['body']: '这是项目的中文全文。', mixed['body']: '这是报道的中文全文。',
             mixed_summary['summary']: '关于中国市场的报道。', english['title']: '科技新闻的中文标题',
             english['body']: '这是科技新闻的中文全文。'}
    calls = []

    def fake(batch, src):
        calls.extend(batch)
        return [texts.get(text) for text in batch]

    assert apply_translation(items, None) == 0
    assert all(item['lang'] == 'mul' for item in (repo, mixed, mixed_summary, held))
    for item in (repo, mixed):
        assert builder.public_item(item)['translated'] is False
    assert builder.public_item(mixed_summary) is None

    apply_translation(items, (fake, 'test'), tmp_path)
    assert validate_items_envelope(envelope(items)) == []
    assert set(calls) == set(texts) | {held['summary']}
    assert not native_repo['translated']
    assert not held['translated']
    assert repo['translation']['body'] == texts[repo['body']]
    assert mixed['translation']['blocks'][0]['text'] == texts[mixed['body']]
    assert not mixed_summary['translation'].get('body_pending')

    cached = [dict(item, translated=False, translation=None) for item in items]
    calls.clear()
    apply_translation(cached, (fake, 'test'), tmp_path)
    assert set(calls) == {held['summary']}
    assert validate_items_envelope(envelope(cached)) == []
    assert [item.get('translation') for item in cached] == [item.get('translation') for item in items]

    inp, out = tmp_path / 'in', tmp_path / 'out'
    inp.mkdir()
    (inp / 'ingest.json').write_text(json.dumps(envelope(items)))
    monkeypatch.setattr(builder, '_run_archive', lambda items, out, report: build_archive(items, out, tmp_path / 'archive'))
    monkeypatch.setenv('REBANG_TRANSLATE_CACHE', str(tmp_path / 'field-cache.json'))
    builder.build(out, inp, now=NOW, web_dir=None, hot_archive_dir=None)
    data = out / 'data'
    assert set(read(data / 'id-index.json')) == {item['id'] for item in items if item is not held}
    channels = {c['slug']: c for c in read(data / 'meta.json')['channels']}
    assert channels['world']['total'] == 2
    assert channels['tools']['total'] == 2
    assert channels['tech-ai']['total'] == 1
    results = {row['id']: row for row in read(data / 'search-index.json')['entries']}
    assert results[repo['id']]['display_title'] == repo['title']
    assert results[repo['id']]['display_summary'] == repo['summary']
    assert results[mixed['id']]['display_title'] == mixed['title']
    assert results[mixed_summary['id']]['display_summary'] == texts[mixed_summary['summary']]
    assert results[english['id']]['display_summary'] == english['summary']


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
