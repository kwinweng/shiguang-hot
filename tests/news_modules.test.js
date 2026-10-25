const test = require('node:test');
const assert = require('node:assert/strict');
const news = require('../web/news.js');
const modules = require('../web/modules.js');
const {readFileSync} = require('node:fs');
const vm = require('node:vm');

for (const initial of ['light', 'dark']) {
  test(`theme toggle starts in ${initial} mode and updates icon and accessible action`, () => {
    const button = {setAttribute(name, value) { this[name] = value; }};
    const root = {dataset:{}};
    const context = vm.createContext({
      window:{}, document:{documentElement:root, body:{dataset:{}}, getElementById(id) {
        return id === 'theme' ? button : {dataset:{}, setAttribute() {}, removeAttribute() {}};
      }},
      matchMedia:() => ({matches:initial === 'dark'}),
      addEventListener() {}, location:{hash:'#feed'}, URLSearchParams,
      fetch:() => new Promise(() => {})
    });
    for (const asset of ['news-icons.js', 'news.js', 'modules.js']) {
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

test('B5 group filter channels, unread counts, and markChannelSeen update rebang.lastSeen', () => {
  assert.equal(modules.LAST_SEEN_KEY, 'rebang.lastSeen');
  const rows = [
    {id:'1', source:'tech_a', source_name:'科技资讯', category:'科技', time:'2026-10-25T10:00:00+08:00', hot:true},
    {id:'2', source:'tech_a', source_name:'科技资讯', category:'科技', time:'2026-10-25T08:00:00+08:00', hot:false},
    {id:'3', source:'tech_b', source_name:'开源快讯', category:'科技', time:'2026-10-25T09:00:00+08:00', hot:false},
    {id:'4', source:'fin_a', source_name:'财经早报', category:'财经', time:'2026-10-25T09:30:00+08:00', hot:false}
  ];
  assert.deepEqual(modules.categoryChannels(rows, '全部', news.filter), []);
  assert.deepEqual(modules.categoryChannels(rows, '科技', news.filter), ['科技资讯', '开源快讯']);
  const seeded = modules.seedLastSeen(rows, null);
  assert.ok(seeded['科技资讯']);
  assert.ok(seeded['开源快讯']);
  assert.equal(modules.unreadCount(rows, '科技资讯', seeded), 2);
  assert.equal(modules.unreadCount(rows, '开源快讯', seeded), 1);
  assert.equal(modules.categoryUnreadTotal(rows, '科技', seeded, news.filter), 3);
  const afterSeen = modules.markChannelSeen(rows, '科技资讯', seeded);
  assert.equal(afterSeen['科技资讯'], '2026-10-25T10:00:00+08:00');
  assert.equal(modules.unreadCount(rows, '科技资讯', afterSeen), 0);
  assert.equal(modules.categoryUnreadTotal(rows, '科技', afterSeen, news.filter), 1);
});

test('B5 CSS enforces transparent chips with bottom underline and uses only token variables', () => {
  const css = readFileSync(new URL('../web/news.css', `file://${__filename}`), 'utf8');
  assert.match(css, /\.flt button\{[^}]*background:transparent;border:0;border-radius:0/);
  assert.match(css, /\.chips button\{[^}]*background:transparent;border:0;border-radius:0/);
  assert.match(css, /\.group-sheet|\.group-option/);
  assert.match(css, /\.date-picker/);
});
