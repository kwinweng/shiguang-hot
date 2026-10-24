const test = require('node:test');
const assert = require('node:assert/strict');
const news = require('../web/news.js');
const {readFileSync} = require('node:fs');
const vm = require('node:vm');

for (const initial of ['light', 'dark']) {
  test(`theme toggle starts in ${initial} mode and updates icon and accessible action`, () => {
    const button = {setAttribute(name, value) { this[name] = value; }};
    const root = {dataset:{}};
    const context = vm.createContext({
      window:{}, document:{documentElement:root, getElementById(id) {
        return id === 'theme' ? button : {setAttribute() {}};
      }},
      matchMedia:() => ({matches:initial === 'dark'}),
      addEventListener() {}, location:{hash:'#feed'}, URLSearchParams,
      fetch:() => new Promise(() => {})
    });
    for (const asset of ['news-icons.js', 'news.js']) {
      vm.runInContext(readFileSync(new URL('../web/' + asset, `file://${__filename}`), 'utf8'), context);
    }
    for (const mode of [initial, initial === 'dark' ? 'light' : 'dark', initial]) {
      assert.equal(root.dataset.theme, mode);
      const label = mode === 'dark' ? '切换到浅色模式' : '切换到深色模式';
      assert.equal(button['aria-label'], label);
      assert.equal(button.title, label);
      const glyph = mode === 'dark' ? 'sun_line' : 'moon_line';
      assert.match(context.window.ICONS[glyph], /<svg[^>]*aria-hidden="true"><path d="[^"]+"\/><\/svg>/);
      assert.equal(button.innerHTML, `<span class="ic">${context.window.ICONS[glyph]}</span>`);
      button.onclick();
    }
  });
}

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
