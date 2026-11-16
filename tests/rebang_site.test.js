// frontend-v11：web-v11/lib.js 纯函数单测（卡片、热搜失败态、译文、深链、北京时间）。
const test = require('node:test');
const assert = require('node:assert/strict');
const L = require('../web-v11/lib.js');

const base = {id: 'tnews365:1', kind: 'news', channel: 'current', source_id: 'tnews365', source_name: '竹新社',
  title: '标题', summary: '摘要', url: 'https://t.me/tnews365/1', published_at: '2026-11-15T11:00:00Z', lang: 'zh', translated: false};

test('无图卡片：标题 + 3 行摘要 + 来源时间；没有摘要如实说明', () => {
  const html = L.feedRowHTML({...base, image: null});
  assert.match(html, /class="feed-row noimg"/);
  assert.match(html, /<h3>标题<\/h3><p class="sum">摘要<\/p>/);
  assert.match(html, /竹新社<\/span><span>11月15日 19:00<\/span>/);
  assert.match(L.feedRowHTML({...base, summary: ''}), /<p class="sum none">这条没有正文摘要。<\/p>/);
  assert.doesNotMatch(L.feedRowHTML({...base, summary: '', image: {url: 'https://i/a.jpg', width: 200, height: 100}}), /这条没有正文摘要/);
});

test('有图卡片左图右文；有地址就显示，不再用短边限制挡住列表图', () => {
  assert.match(L.feedRowHTML({...base, image: {url: 'https://i/a.jpg', width: 1200, height: 675}}), /class="feed-row" .*<div class="thumb"><img src="https:\/\/i\/a.jpg"/);
  assert.match(L.feedRowHTML({...base, image: {url: 'https://i/a.jpg', width: 200, height: 100}}), /class="feed-row" .*<div class="thumb"><img src="https:\/\/i\/a.jpg"/);
  assert.doesNotMatch(L.feedRowHTML({...base, image: {url: 'https://i/a.jpg', width: 200, height: 100}}), /feed-row noimg/);
  assert.match(L.feedRowHTML({...base, image: {url: 'media/a.webp'}}), /<img src="media\/a.webp"/);
});

test('HTML 转义，不让内容注入标签', () => {
  assert.match(L.feedRowHTML({...base, title: '<b>x</b>'}), /&lt;b&gt;x&lt;\/b&gt;/);
});

test('译文优先并标「机器翻译」，原文保留可展开', () => {
  const it = {...base, lang: 'en', title: 'Hello', summary: 'World', translated: true,
    translation: {title: '你好', summary: '世界', engine: 't', label: '机器翻译'}};
  const d = L.display(it);
  assert.deepEqual([d.title, d.summary, d.translated, d.orig.title], ['你好', '世界', true, 'Hello']);
  assert.match(L.feedRowHTML(it), /<h3>你好<\/h3>.*<span class="mt-badge">机器翻译<\/span>/);
  const post = {...it, kind: 'post', blogger: {platform: 'x', handle: 'a', display_name: 'A', media: [], quote: null}};
  const card = L.tweetCardHTML(post, true);
  assert.match(card, /<span class="t-badge">机器翻译<\/span><button type="button" class="orig-btn"/);
  assert.match(card, /<div class="orig" [^>]*>World<\/div>/);
});

test('标题和摘要译文立刻生效，不必等正文；未译摘要不回退到英文', () => {
  const it = {...base, lang: 'en', title: 'Hello', summary: 'World preview', body: 'Long English body',
    translated: true, translation: {title: '你好', summary: '世界预览', engine: 't', label: '机器翻译', body_pending: true}};
  const d = L.display(it);
  assert.equal(d.title, '你好');
  assert.equal(d.summary, '世界预览');
  assert.equal(d.bodyPending, true);
  assert.equal(d.body, '世界预览');
  assert.equal(d.blocks, null);
  assert.match(L.feedRowHTML(it), /<h3>你好<\/h3><p class="sum">世界预览<\/p>/);
  assert.doesNotMatch(L.feedRowHTML(it), /Hello|World preview/);
  const titleOnly = {...it, translation: {title: '你好', summary: '', engine: 't', label: '机器翻译', body_pending: true}};
  assert.equal(L.display(titleOnly).title, '你好');
  assert.equal(L.display(titleOnly).summary, '');
  assert.doesNotMatch(L.feedRowHTML(titleOnly), /World preview|Hello/);
});


test('推文卡：没有互动数就不显示，不编数字', () => {
  const post = {...base, kind: 'post', blogger: {platform: 'x', handle: 'a', display_name: 'A', media: [], quote: null}};
  assert.doesNotMatch(L.tweetCardHTML(post, true), /class="metrics"/);
  const withM = {...post, blogger: {...post.blogger, metrics: {reply: 0, like: 12000}}};
  assert.match(L.tweetCardHTML(withM, true), /class="metrics">.*0<\/span><span>.*1\.2万<\/span><\/div>/);
});

const hot = {providers: [
  {id: 'baidu', name: '百度热搜', status: 'ok', fetched_at: '2026-11-15T12:45:00Z',
    items: [{rank: 1, title: '置顶条', url: 'https://b/1', pinned: true}, ...Array.from({length: 11}, (_, i) => ({rank: i + 2, title: 't' + (i + 2), url: 'https://b/' + (i + 2), pinned: false, hot_score: 7808372}))]},
  {id: 'zhihu', name: '知乎热榜', status: 'error', fetched_at: null, items: []},
  {id: 'bilibili', name: 'B 站热搜', status: 'empty', fetched_at: null, items: []}]};

test('热搜块：分家 tab，默认第一家成功的，前 10 条 + 展开', () => {
  const html = L.hotsearchHTML(hot, null, false);
  assert.equal((html.match(/role="tab"/g) || []).length, 3);
  assert.match(html, /data-hot="baidu" aria-selected="true" class="on"/);
  assert.equal((html.match(/<li>/g) || []).length, 10);
  assert.match(html, /<span class="rk">顶<\/span><span class="t">置顶条<\/span><span class="lbl pin">置顶<\/span>/);
  assert.match(html, /780\.8万/);
  assert.match(html, /展开全部 12 条/);
  assert.equal((L.hotsearchHTML(hot, null, true).match(/<li>/g) || []).length, 12);
  assert.match(html, /百度热搜 · 11月15日 20:45/);
});

test('热搜失败家显示「暂时取不到」，不编排名', () => {
  for (const id of ['zhihu', 'bilibili']) {
    const html = L.hotsearchHTML(hot, id, false);
    assert.match(html, /class="hot-empty"[^>]*>(知乎热榜|B 站热搜)暂时取不到/);
    assert.doesNotMatch(html, /<li>/);
    assert.match(html, new RegExp(`data-hot="${id}"[^>]*class="on bad"`));
  }
  assert.equal(L.hotsearchHTML({providers: []}), '');
});

test('banner：≤ 给定条数，带页码', () => {
  const its = [1, 2, 3].map(n => ({...base, id: 'a:' + n, image: {url: 'https://i/' + n + '.jpg', width: 1200, height: 700}}));
  const html = L.bannerHTML('current', its);
  assert.equal((html.match(/class="banner-slide"/g) || []).length, 3);
  assert.match(html, /1 \/ 3/);
  assert.equal(L.bannerHTML('current', []), '');
});

test('深链 #/item/<urlencoded id>（8:30 私聊稿）与旧式 #item-', () => {
  assert.equal(L.itemHash('FinanceNewsDaily:496634'), '#/item/FinanceNewsDaily%3A496634');
  assert.equal(L.parseItemHash('#/item/FinanceNewsDaily%3A496634'), 'FinanceNewsDaily:496634');
  assert.equal(L.parseItemHash('#item-x%3A1'), 'x:1');
  assert.equal(L.parseItemHash('#/item/%E0%A4%A'), null);
  assert.equal(L.parseItemHash('#feed'), null);
});

test('北京时间：日期分组跨 00:00、周几', () => {
  assert.equal(L.beijingDate('2026-11-15T15:59:59Z'), '2026-11-15');
  assert.equal(L.beijingDate('2026-11-15T16:00:00Z'), '2026-11-16');
  assert.equal(L.fmtDay('2026-11-15T16:30:00Z'), '11月16日 周一');
  assert.equal(L.fmtTime('2026-11-15T20:05:00+08:00'), '11月15日 20:05');
});

test('卡片摘要去掉开头裸链接', () => {
  const d = L.display({title: 't', summary: 'https://a.example/x?y=1 研究员发现问题'});
  assert.equal(d.summary, '研究员发现问题');
  assert.equal(L.display({title: 't', summary: '见 https://a.example/x'}).summary, '见 https://a.example/x');
});

test('推文详情：评论预览只在详情显示，引用带发布时间', () => {
  const it = {id: 'x:1', kind: 'post', title: '', summary: 'hi', url: 'https://x.com/a/status/1', source: 'x', published_at: '2026-11-15T10:00:00Z',
    blogger: {platform: 'x', handle: 'a', display_name: 'A', comments: [{author: 'B', text: '评论内容<b>', published_at: '2026-11-15T11:00:00Z'}],
      quote: {display_name: 'Q', text: '被引用', url: 'https://x.com/q/status/2', published_at: '2026-11-14T12:00:00Z'}}};
  const card = L.tweetCardHTML(it, true), detail = L.tweetCardHTML(it, false);
  assert.ok(!card.includes('评论内容'));
  assert.ok(detail.includes('评论内容&lt;b&gt;'));
  assert.ok(detail.includes('11月14日 20:00'));
});

// ---- v13（阿欢 2026-11-15 22:08–22:11）----
test('v13 顶栏：刷新时间同一天只写时间，跨天才带日期', () => {
  const now = new Date('2026-11-15T14:00:00Z');
  assert.equal(L.fmtRefreshed('2026-11-15T13:40:00Z', now), '21:40');
  assert.equal(L.fmtRefreshed('2026-11-14T13:40:00Z', now), '11月14日 21:40');
});

test('v13 TG 引用：频道自己的话在上，原帖在引用卡里；转发且没写话 → 标「转发」', () => {
  const base = {id: 'demo:1', kind: 'news', source_id: 'demo', source_name: '演示', url: 'https://t.me/demo/1', published_at: '2026-11-15T10:00:00+08:00', lang: 'zh'};
  const reply = L.feedRowHTML({...base, title: '频道的话', summary: '频道的评论', body: '频道的话\n频道的评论', quote: {kind: 'reply', source_name: '原频道', url: 'https://t.me/o/9', text: '原帖原文'}});
  assert.ok(reply.indexOf('频道的话') < reply.indexOf('原帖原文'));
  assert.match(reply, /class="q-card"/);
  assert.doesNotMatch(reply, /fwd-tag/);
  const fwd = L.feedRowHTML({...base, title: '原帖原文', summary: '', quote: {kind: 'forward', source_name: '别的频道', url: 'https://t.me/o/9', text: '原帖原文'}});
  assert.match(fwd, /<div class="fwd-tag">转发<\/div>/);
  assert.match(fwd, /转发自<\/span>别的频道/);
  assert.doesNotMatch(fwd, /<h3>/);
  const detail = L.quoteCardHTML({...base, quote: {kind: 'forward', source_name: '别的频道', url: 'https://t.me/o/9', text: 'x'}}, true);
  assert.match(detail, /<a class="q-card fwd" href="https:\/\/t.me\/o\/9"/, '详情里引用卡点开原帖');
});

test('v13 TG 互动：只显示页面上抓到的表情/浏览/评论数，没有就不显示', () => {
  const it = {tg: {views: 20200, views_label: '20.2K', reactions: [{emoji: '😁', count: 34, label: '34'}, {emoji: '👍', count: 1200, label: '1.2K'}, {emoji: '❤', count: 2, label: '2'}, {emoji: '🔥', count: 1, label: '1'}], comments_total: 12}};
  const card = L.tgStatsHTML(it, false);
  assert.ok(card.indexOf('👍') < card.indexOf('😁'), '按数量从多到少');
  assert.match(card, /\+1<\/span>/);
  assert.match(card, /20\.2K/);
  assert.match(card, /评论 12 条/);
  assert.equal(L.tgStatsHTML({}, true), '');
  assert.equal(L.tgStatsHTML({tg: {}}, true), '');
});

test('v13 公众号正文块：按原文顺序渲染；没存下的图如实说明', () => {
  const html = L.blocksHTML([{type: 'p', text: '一'}, {type: 'img', src: 'media/wechat/a.webp', width: 10, height: 5}, {type: 'h', level: 2, text: '二'},
    {type: 'quote', text: '三'}, {type: 'ul', items: ['四', '五']}, {type: 'img', src: 'https://mmbiz.qpic.cn/x', missing: true}]);
  const order = ['>一<', 'media/wechat/a.webp', '>二<', '>三<', '<li>四</li>', 'data-img-missing'].map(s => html.indexOf(s));
  assert.ok(order.every((v, i) => v >= 0 && (i === 0 || v > order[i - 1])), order.join(','));
  assert.doesNotMatch(html, /mmbiz\.qpic\.cn/, '公众号图床不外链');
});

test('推文视频：封面 + 播放标 + 时长，媒体清单带视频地址和原帖链接；没封面时用 <video> 首帧', () => {
  const media = [
    {type: 'image', url: 'https://pbs/a.jpg'},
    {type: 'video', url: 'https://video.twimg.com/v.mp4', preview_url: 'https://pbs/v.jpg', duration_ms: 42000},
    {type: 'gif', url: 'https://video.twimg.com/g.mp4'},
  ];
  const html = L.mediaGrid(media, 'https://x.com/a/status/1');
  assert.match(html, /data-origin="https:\/\/x.com\/a\/status\/1"/);
  assert.match(html, /<img src="https:\/\/pbs\/v.jpg"[^>]*data-media-i="1">/);
  assert.match(html, /<span class="vid-dur">0:42<\/span>/);
  assert.match(html, /<video src="https:\/\/video.twimg.com\/g.mp4#t=0.1" muted playsinline preload="metadata" data-media-i="2">/);
  const list = JSON.parse(html.match(/data-media-list="([^"]+)"/)[1].replace(/&quot;/g, '"').replace(/&amp;/g, '&'));
  assert.deepEqual(list, [
    {t: 'image', u: 'https://pbs/a.jpg'},
    {t: 'video', u: 'https://video.twimg.com/v.mp4', p: 'https://pbs/v.jpg'},
    {t: 'gif', u: 'https://video.twimg.com/g.mp4', p: ''},
  ]);
  assert.equal(L.mediaGrid([]), '');
  assert.equal(L.fmtDur(0), '');
  assert.equal(L.fmtDur(125400), '2:05');
});

test('微博卡片：数字 uid 不显示「@」，个性域名照常显示；转发原帖只显示昵称', () => {
  const post = {...base, kind: 'post', source_id: 'weibo-1560906700', summary: '这是为啥', body: '这是为啥',
    blogger: {platform: 'weibo', handle: '1560906700', display_name: '阑夕', media: [],
      quote: {handle: '1708942053', display_name: '都市报道', text: '原帖正文'}}};
  const card = L.tweetCardHTML(post, false);
  assert.match(card, /<div class="nm">阑夕 /);
  assert.doesNotMatch(card, /@1560906700|@1708942053/);
  assert.match(card, /<div class="nm">都市报道<\/div>/);
  const custom = {...post, blogger: {...post.blogger, handle: 'linfcstmr', quote: null}};
  assert.match(L.tweetCardHTML(custom, false), /@linfcstmr/);
});

test('standaloneGeometry：iOS 主屏幕 web app 外壳撑满整屏、底栏贴底', () => {
  const base = {standalone: true, ios: true, insetTop: 62, insetBottom: 34, screenW: 402, screenH: 874, innerW: 402};
  // 阿欢的 iPhone 17 Pro（WebKit 313800）：视口 812、屏幕 874 → 外壳 874，底栏照常垫 env()（34）
  assert.deepEqual(L.standaloneGeometry({...base, innerH: 812}), {appH: 874, safeBot: null});
  // 同上但 env() 错报 0 → 外壳 874，底部至少 20
  assert.deepEqual(L.standaloneGeometry({...base, insetBottom: 0, innerH: 812}), {appH: 874, safeBot: 20});
  // 视口就是整屏：照常
  assert.equal(L.standaloneGeometry({...base, innerH: 874}), null);
  // 整屏但 env() 报 0（iOS 26.1 回归）→ 只兜底 20px
  assert.deepEqual(L.standaloneGeometry({...base, insetBottom: 0, innerH: 874}), {appH: null, safeBot: 20});
  // 状态栏不透明（视口从状态栏下开始），缺口在顶部：不动
  assert.equal(L.standaloneGeometry({...base, insetTop: 0, innerH: 812}), null);
  // 横屏：屏幕短边 402、视口 402 → 整屏，照常
  assert.equal(L.standaloneGeometry({...base, innerW: 874, innerH: 402, insetBottom: 21}), null);
  // iPad 分屏窗口不是整屏：不猜
  assert.equal(L.standaloneGeometry({...base, screenW: 1024, screenH: 1366, innerW: 600, innerH: 1300}), null);
  // 浏览器标签页（Safari / iOS Chrome）、桌面、安卓：不覆盖
  assert.equal(L.standaloneGeometry({...base, standalone: false, innerH: 683}), null);
  assert.equal(L.standaloneGeometry({...base, ios: false, innerH: 800}), null);
});
