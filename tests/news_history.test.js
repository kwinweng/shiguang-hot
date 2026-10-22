'use strict';
const {test} = require('node:test');
const assert = require('node:assert/strict');
const {matches, dates, unique, pointerIndex, DayStore} = require('../web/history.js');
const manifest = {version: 'v1', days: {
  '2026-10-22': {joint: [['world', 'world', '财经'], ['CE_Observe', 'alias', 'AI']]},
  '2026-10-20': {joint: [['world', 'world', 'AI']]},
  '2025-10-22': {joint: [['world', 'world', '全球']]},
  '2027-10-22': {joint: [['world', 'world', 'AI']]}
}};
const state = {source: 'world', topic: '科技', sub: '', q: ''};
test('joint dates reject independent-source/topic false positives and future days', () => {
  assert.deepEqual(dates(manifest, state, '2026-10-22'), ['2026-10-20']);
  assert.deepEqual(dates(manifest, {...state, topic: '环球'}, '2026-10-22'), ['2025-10-22']);
  assert.deepEqual(dates(manifest, {...state, source: 'blocked'}, '2026-10-22'), []);
  assert(matches({source: 'CE_Observe', alias: 'alias', topic: 'AI'}, {...state, source: 'alias', sub: 'AI'}));
});
test('UID deduplication and capsule boundary mapping skip missing days', () => {
  assert.deepEqual(unique([{uid: 'a'}, {uid: 'a'}, {uid: 'b'}]), [{uid: 'a'}, {uid: 'b'}]);
  assert.equal(pointerIndex(-10, 0, 100, 3), 0);
  assert.equal(pointerIndex(50, 0, 100, 3), 1);
  assert.equal(pointerIndex(150, 0, 100, 3), 2);
});
test('one direct day request, cache hit, and no intermediate history prefetch', async () => {
  const requests = [];
  const store = new DayStore(manifest, 'public', async day => {
    requests.push(day);
    return {schema: 3, scope: 'public', day, items: [{uid: day, source: 'world', topic: 'AI'}]};
  });
  await store.load('2025-10-22', state);
  await store.load('2025-10-22', state);
  assert.deepEqual(requests, ['2025-10-22']);
  await store.load('2025-10-22', {...state, source: 'CE_Observe'});
  assert.equal(requests.length, 2);
});
test('late old responses cannot enter the new query snapshot', async () => {
  let resolve;
  const store = new DayStore(manifest, 'public', () => new Promise(done => { resolve = done; }));
  const pending = store.load('2026-10-20', state);
  store.invalidate();
  resolve({schema: 3, scope: 'public', day: '2026-10-20', items: []});
  assert.equal(await pending, null);
});
test('network failures remain retryable; scope and corrupt data are rejected', async () => {
  let tries = 0;
  const store = new DayStore(manifest, 'public', async day => {
    if (++tries === 1) throw Error('offline');
    return {schema: 3, scope: 'public', day, items: []};
  });
  await assert.rejects(store.load('2026-10-20', state), /offline/);
  assert.deepEqual(await store.load('2026-10-20', state), []);
  const bad = new DayStore(manifest, 'public', async day => ({schema: 3, scope: 'private', day, items: []}));
  await assert.rejects(bad.load('2026-10-20', state), /存档格式损坏/);
});
