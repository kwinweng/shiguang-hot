const test = require('node:test');
const assert = require('node:assert/strict');
const news = require('../web/news.js');
const modules = require('../web/modules.js');

test('duplicate and near duplicate summaries disappear, distinct text survives', () => {
  assert.equal(modules.distinctSummary('新产品今日发布！', '新产品今日发布'), '');
  assert.equal(modules.distinctSummary('新产品今天正式发布', '新产品今天正式发布。'), '');
  assert.equal(modules.distinctSummary('新产品发布', '价格与上市时间另行公布'), '价格与上市时间另行公布');
  assert.equal(modules.distinctSummary('标题', ''), '');
});

test('all six filters select category rather than source', () => {
  assert.deepEqual(news.categories,['全部','热门','科技','财经','国际','数码']);
  const rows = [{source:'a',category:'科技AI',hot:true},{source:'a',category:'社会'},
    {source:'b',category:'AI'},{category:'数码'},{category:'全球'},{category:'财经',source_count:2}];
  assert.equal(news.filter(rows,'全部').length,6);
  assert.equal(news.filter(rows,'科技').length,2);
  assert.equal(news.filter(rows,'国际').length,1);
  assert.equal(news.filter(rows,'数码').length,1);
  assert.equal(news.filter(rows,'热门').length,2);
  assert.equal(news.filter(rows,'财经').length,1);
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
