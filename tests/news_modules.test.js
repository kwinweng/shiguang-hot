const test = require('node:test');
const assert = require('node:assert/strict');
const news = require('../web/news.js');

test('all six filters select category rather than source', () => {
  assert.equal(news.categories.length,6);
  const rows = [{source:'a',category:'科技AI'},{source:'a',category:'社会'},{source:'b',category:'科技AI'}];
  assert.equal(news.filter(rows,'全部').length,3);
  assert.equal(news.filter(rows,'科技AI').length,2);
  assert.equal(news.filter(rows,'全球').length,0);
});
test('calendar enables only available days across leap years', () => {
  const days = news.monthDays('2024-02',['2024-02-29']);
  assert.equal(days.length,29);
  assert.deepEqual(days.filter(d=>d.enabled),[{day:'2024-02-29',enabled:true}]);
  assert.equal(news.monthDays('2026-02',[]).length,28);
});
test('public text and original URLs cannot inject markup or script URLs', () => {
  assert.equal(news.safe('javascript:alert(1)'),'');
  assert.equal(news.escape('<script>"&'), '&lt;script&gt;&quot;&amp;');
  assert.equal(news.safe('https://t.me/test/1'),'https://t.me/test/1');
});
