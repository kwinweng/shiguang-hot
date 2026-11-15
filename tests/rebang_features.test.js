'use strict';
const { test } = require('node:test');
const assert = require('node:assert/strict');
const { readFileSync } = require('node:fs');
const { dirname, join } = require('node:path');

const root = join(dirname(__filename), '..');
const Favorites = require(join(root, 'web-v11/features/favorites.js'));
const Search = require(join(root, 'web-v11/features/search.js'));
const History = require(join(root, 'web-v11/features/history.js'));

function memoryStorage(initial) {
  const data = { ...(initial || {}) };
  return {
    getItem: (key) => (Object.prototype.hasOwnProperty.call(data, key) ? data[key] : null),
    setItem: (key, value) => { data[key] = String(value); },
    removeItem: (key) => { delete data[key]; },
    _data: data,
  };
}

const published = JSON.parse(readFileSync(join(root, 'tests/fixtures/rebang/archive/published-items.json'), 'utf8'));
const items = published.items;
const zhItem = items.find((it) => it.id === 'tnews365:1001');
const enItem = items.find((it) => it.id === 'bbc-world:abc123');
const postItem = items.find((it) => it.id === 'x-dotey:1');

const searchEntries = [
  {
    id: zhItem.id,
    title: zhItem.title,
    summary: zhItem.summary,
    source_name: zhItem.source_name,
    display_title: zhItem.title,
    display_summary: zhItem.summary,
    translation_title: '',
    translation_summary: '',
    original_title: '',
    original_summary: '',
  },
  {
    id: enItem.id,
    title: enItem.title,
    summary: enItem.summary,
    source_name: enItem.source_name,
    display_title: enItem.translation.title,
    display_summary: enItem.translation.summary,
    translation_title: enItem.translation.title,
    translation_summary: enItem.translation.summary,
    original_title: enItem.title,
    original_summary: enItem.summary,
    translated: true,
  },
  {
    id: postItem.id,
    title: postItem.title,
    summary: postItem.summary,
    source_name: postItem.source_name,
    display_title: postItem.summary,
    display_summary: postItem.summary,
  },
];

test('收藏增删后刷新存储仍在，取消后消失', () => {
  const storage = memoryStorage();
  Favorites.add(zhItem, storage);
  Favorites.add(enItem, storage);
  let saved = Favorites.load(storage);
  assert.deepEqual(saved.map((it) => it.id), [enItem.id, zhItem.id]);
  assert.equal(Favorites.isFavorite(zhItem.id, storage), true);

  const again = memoryStorage({ [Favorites.STORAGE_KEY]: storage.getItem(Favorites.STORAGE_KEY) });
  const persisted = Favorites.load(again);
  assert.equal(persisted.length, 2);
  assert.equal(persisted.find((it) => it.id === zhItem.id).title, '合成标题一');
  assert.ok(Favorites.DEVICE_NOTE.includes('换手机或清理数据会消失'));

  Favorites.toggle(zhItem, again);
  assert.equal(Favorites.isFavorite(zhItem.id, again), false);
  assert.deepEqual(Favorites.load(again).map((it) => it.id), [enItem.id]);
  assert.equal(Favorites.isFavorite(zhItem.id, storage), true);
});

test('搜索命中中文标题、英文原文与译文', () => {
  assert.deepEqual(Search.search(searchEntries, '合成标题一').map((it) => it.id), [zhItem.id]);
  assert.deepEqual(Search.search(searchEntries, 'SYNTHETIC HEADLINE').map((it) => it.id), [enItem.id]);
  assert.deepEqual(Search.search(searchEntries, '合成译文标题').map((it) => it.id), [enItem.id]);
  assert.deepEqual(Search.search(searchEntries, 'synthetic summary').map((it) => it.id), [enItem.id]);
  assert.deepEqual(Search.search(searchEntries, '竹新社').map((it) => it.id), [zhItem.id]);
  assert.deepEqual(Search.search(searchEntries, '合成推文正文').map((it) => it.id), [postItem.id]);
  assert.deepEqual(Search.search(searchEntries, '不存在的关键词'), []);
  assert.ok(!JSON.stringify(searchEntries).includes('ai_summary'));
});

test('北京日期在 00:00 边界切换，空日期文案固定', () => {
  assert.equal(History.beijingDate('2026-11-14T15:59:59Z'), '2026-11-14');
  assert.equal(History.beijingDate('2026-11-14T16:00:00Z'), '2026-11-15');
  assert.equal(History.shiftDate('2026-11-15', -1), '2026-11-14');
  assert.equal(History.EMPTY_MESSAGE, '这天没有内容');
  assert.equal(History.emptyPayload('2026-11-14').message, '这天没有内容');
});
