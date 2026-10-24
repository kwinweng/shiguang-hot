'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const {defaultTab, focusDay, addedCount, notFoundLabel} = require('../web/modules.js');
test('default opens news live', () => assert.equal(defaultTab, 'feed'));
test('hotspot date switches at Beijing 22:00, including year boundary', () => {
  assert.equal(focusDay(new Date('2026-10-24T21:59:59+08:00')), '2026-10-23');
  assert.equal(focusDay(new Date('2026-10-24T22:00:00+08:00')), '2026-10-24');
  assert.equal(focusDay(new Date('2027-01-01T00:01:00+08:00')), '2026-12-31');
});
test('refresh counts distinct new identities, not net length', () => {
  assert.equal(addedCount([{id:'a'},{id:'b'}], [{id:'b'},{id:'c'},{id:'c'}]), 1);
  assert.equal(addedCount([{id:'a'}], [{id:'a'}]), 0);
  assert.equal(addedCount([], [{id:'a'},{id:'b'}]), 2);
});
test('404 returns to news', () => assert.equal(notFoundLabel, '回到资讯'));
