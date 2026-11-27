// frontend-v11：web-v11/lib.js 纯函数单测（卡片、热搜失败态、译文、深链、北京时间）。
const test = require('node:test');
const assert = require('node:assert/strict');
const L = require('../web-v11/lib.js');

const base = {id: 'tnews365:1', kind: 'news', channel: 'current', source_id: 'tnews365', source_name: '竹新社',
  title: '标题', summary: '摘要', url: 'https://t.me/tnews365/1', published_at: '2026-11-15T11:00:00Z', lang: 'zh', translated: false};

test('无图卡片：标题 + 摘要 + 来源时间；没有摘要如实说明', () => {
  const html = L.feedRowHTML({...base, image: null});
  assert.match(html, /class="feed-row noimg"/);
  assert.match(html, /<h3>标题<\/h3><p class="sum">摘要<\/p>/);
  assert.match(html, /竹新社<\/span><span class="when">11月15日 19:00<\/span>/);
  assert.match(L.feedRowHTML({...base, summary: ''}), /<p class="sum none">这条没有正文摘要。<\/p>/);
  assert.doesNotMatch(L.feedRowHTML({...base, summary: '', image: {url: 'https://i/a.jpg', width: 200, height: 100}}), /这条没有正文摘要/);
});

test('有图卡片：大图在上、小图在右；有地址就显示，不再用短边限制挡住列表图', () => {
  assert.match(L.feedRowHTML({...base, image: {url: 'https://i/a.jpg', width: 1200, height: 675}}), /class="feed-row cover" .*<div class="thumb" style="aspect-ratio:1200\/675"><img src="https:\/\/i\/a.jpg"/);
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
  assert.match(L.feedRowHTML(it), /<h3>你好<\/h3>.*<span class="tag mt-badge" title="机器翻译">译<\/span>/);
  const post = {...it, kind: 'post', blogger: {platform: 'x', handle: 'a', display_name: 'A', media: [], quote: null}};
  assert.match(L.tweetCardHTML(post, true), /<h3 class="b-title">.*你好<\/a><\/h3>.*<span class="tag mt-badge" title="机器翻译">译<\/span>/s);
  const card = L.tweetCardHTML(post, false);
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
  assert.doesNotMatch(L.tweetCardHTML(post, false), /class="metrics"/);
  const withM = {...post, blogger: {...post.blogger, metrics: {reply: 0, like: 12000}}};
  assert.match(L.tweetCardHTML(withM, true), /<span class="metrics"><span class="n">.*1\.2万<\/span><span class="n">.*0<\/span><\/span>/);
  assert.match(L.tweetCardHTML(withM, false), /class="metrics">.*0<em>回复<\/em><\/span><span>.*1\.2万<em>点赞<\/em><\/span><\/div>/);
  assert.doesNotMatch(L.tweetCardHTML(withM, false), /转发/);
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
  assert.match(html, /<span class="rk pin-rk" aria-label="置顶"><svg class="lucide lucide-flame"[^]*?<\/svg><\/span><span class="t">置顶条<\/span><span class="lbl pin">置顶<\/span>/);
  assert.match(html, /<span class="rk hi">2<\/span>/);
  assert.match(html, /<span class="rk">4<\/span>/);
  assert.match(html, /<b>百度<\/b><small>12 条<\/small>/);
  assert.match(html, /<b>知乎<\/b><small>暂时取不到<\/small>/);
  assert.match(html, /780\.8万/);
  assert.match(html, /展开全部 12 条/);
  assert.equal((L.hotsearchHTML(hot, null, true).match(/<li>/g) || []).length, 12);
  assert.match(html, /class="hot-note">百度 · 抓取于 /);
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

test('v16：缩略图一律在右边（正文在前、图在后）', () => {
  const row = L.feedRowHTML({...base, image: {url: 'https://i/a.jpg', width: 200, height: 100}});
  assert.ok(row.indexOf('class="f-main"') < row.indexOf('class="thumb"'));
  const post = {...base, kind: 'post', title: '', blogger: {platform: 'x', handle: 'a', display_name: 'A', avatar: 'https://i/av.jpg',
    media: [{type: 'image', url: 'https://i/1.jpg'}, {type: 'image', url: 'https://i/2.jpg'}], quote: null}};
  const b = L.postRowHTML(post);
  // 样页 A：帖子媒体在正文下面多格显示，每格可直接点开对应那一张
  assert.doesNotMatch(b, /class="thumb"/);
  assert.match(b, /<p class="b-text">/);
  assert.ok(b.indexOf('class="b-text"') < b.indexOf('class="media-grid n2"'));
  assert.match(b, /data-media-i="0"[\s\S]*data-media-i="1"/);
  const article = L.postRowHTML({...post, blogger: {...post.blogger, media: []}, image: {url: 'https://i/cover.jpg'}});
  assert.ok(article.indexOf('class="b-main"') < article.indexOf('class="thumb"'), '文章封面仍在右边');
  assert.match(L.postRowHTML({...post, blogger: {...post.blogger, media: []}}), /class="tweet brow noimg"/);
});

test('v16：相对时间只用在 24 小时内；日期头「今天/昨天/周X」；热搜短名', () => {
  const now = Date.parse('2026-11-16T14:00:00Z');
  assert.equal(L.fmtWhen('2026-11-16T13:59:40Z', now), '刚刚');
  assert.equal(L.fmtWhen('2026-11-16T13:30:00Z', now), '30 分钟前');
  assert.equal(L.fmtWhen('2026-11-16T09:00:00Z', now), '5 小时前');
  assert.equal(L.fmtWhen('2026-11-14T13:35:00Z', now), L.fmtTime('2026-11-14T13:35:00Z'));
  assert.equal(L.dayLabel('2026-11-16', '2026-11-16'), '11.16 今天');
  assert.equal(L.dayLabel('2026-11-15', '2026-11-16'), '11.15 昨天');
  assert.match(L.dayLabel('2026-11-12', '2026-11-16'), /^11\.12 周四$/);
  assert.deepEqual(['百度热搜', '知乎热榜', 'B 站热搜'].map(L.hotShort), ['百度', '知乎', 'B站']);
});

test('同类事件合并：主条下折叠「另有 N 个来源」，没有 merged 就不出；旧数据不受影响', () => {
  assert.doesNotMatch(L.feedRowHTML({...base}), /data-dup/);
  assert.doesNotMatch(L.feedRowHTML({...base, merged: []}), /data-dup/);
  const it = {...base, merged: [
    {id: 'zaihuapd:2', source_id: 'zaihuapd', source_name: '在花科技圈', title: 'Hello <b>', url: 'https://t.me/zaihuapd/2', published_at: base.published_at},
    {id: 'xhqcankao:3', source_id: 'xhqcankao', source_name: '风向旗参考快讯', title: 'Orig', title_zh: '译文标题', url: '', published_at: base.published_at},
  ]};
  const html = L.feedRowHTML(it);
  assert.match(html, /<button type="button" class="dup-btn" data-dup-toggle aria-expanded="false">另有 2 个来源<\/button><div class="dup-list" hidden>/);
  assert.match(html, /data-dup-id="zaihuapd:2"><span class="src">在花科技圈<\/span><span class="t">Hello &lt;b&gt;<\/span>/);
  assert.match(html, /data-dup-id="xhqcankao:3"><span class="src">风向旗参考快讯<\/span><span class="t">译文标题<\/span>/);
  // 同来源同链接（只是参数不同）的折叠：不说「来源」
  assert.match(L.feedRowHTML({...base, merged: [{id: 'tnews365:9', source_id: 'tnews365', source_name: '竹新社', title: 'x'}]}), /另有 1 条相同链接/);
});

test('同类事件合并：「另有 N 个来源」按 source_id 数，大图卡也有折叠入口', () => {
  // 两个来源显示名相同、source_id 不同：算 2 个来源
  const it = {...base, merged: [
    {id: 'a:1', source_id: 'a', source_name: '同名来源', title: 'x'},
    {id: 'b:1', source_id: 'b', source_name: '同名来源', title: 'y'},
  ]};
  assert.match(L.dupHTML(it), /另有 2 个来源/);
  // 和主条同 source_id、不同显示名：仍是同来源同链接
  assert.match(L.dupHTML({...base, merged: [{id: `${base.source_id}:9`, source_id: base.source_id, source_name: '别名', title: 'z'}]}), /另有 1 条相同链接/);
  const hero = L.heroHTML({...it, image: {url: 'https://img.test/h.png', width: 1200, height: 675}});
  assert.match(hero, /<article class="hero"[^>]*>.*<div class="dup" data-dup><button type="button" class="dup-btn" data-dup-toggle aria-expanded="false">另有 2 个来源<\/button>/);
  assert.doesNotMatch(L.heroHTML({...base, image: {url: 'https://img.test/h.png'}}), /data-dup/);
});

test('博主合流沿用建站顺序，不把同一毫秒内不同微秒当成同刻按 ID 排', () => {
  const posts = [
    {id: 'a', published_at: '2026-11-16T12:00:00.000001+08:00', feed_order: 1},
    {id: 'z', published_at: '2026-11-16T04:00:00.000002Z', feed_order: 0},
    {id: 'b', published_at: '2026-11-16T04:00:00.000001Z', feed_order: 2},
  ];
  assert.deepEqual(posts.sort(L.comparePosts).map(x => x.id), ['z', 'a', 'b']);
});

// 频道首页 A2（2026-11-28 确认）：大图在上、摘要按句收尾、平台图标按配置标
test('A2：够大的新闻配图放标题上方，视频只标「视频」不自动播；偏小的图（头像、图标一类）不放大', () => {
  const big = L.feedRowHTML({...base, image: {url: 'media/a.webp', width: 1280, height: 720}, tg: {media: [{type: 'video'}]}});
  assert.match(big, /<article class="feed-row cover"/);
  assert.ok(big.indexOf('class="thumb video"') < big.indexOf('<h3>'), '图在标题上方');
  assert.match(big, /<span class="vid-badge">视频<\/span>/);
  assert.doesNotMatch(big, /<video|autoplay/);
  assert.match(big, /<p class="sum">摘要<\/p>/, '有图时摘要照样显示');
  const unknown = L.feedRowHTML({...base, image: {url: 'media/b.webp'}});
  assert.match(unknown, /feed-row cover/);
  assert.doesNotMatch(unknown, /aspect-ratio|vid-badge/);
  const icon = L.feedRowHTML({...base, image: {url: 'https://i/logo.png', width: 64, height: 64}});
  assert.doesNotMatch(icon, /feed-row cover/);
  assert.ok(icon.indexOf('class="f-main"') < icon.indexOf('class="thumb"'), '小图仍在右边');
  assert.equal(L.coverOk({url: 'a', width: 180, height: 320}), true, '竖版视频封面');
  assert.equal(L.coverOk({url: 'a', width: 299, height: 299}), false);
  assert.equal(L.coverOk({url: 'a', width: 640, height: 149}), false, '细长横条');
  assert.equal(L.coverOk({url: 'a', width: 300, height: 150}), true);
  assert.equal(L.coverOk(null), false);
});

test('A2：短摘要整段显示，不限两行；长摘要按句子收住接「继续读」；和标题重复就不显示', () => {
  assert.deepEqual(L.excerpt('一句话就说完。', '标题'), {text: '一句话就说完。', more: false});
  assert.deepEqual(L.excerpt('  ', '标题'), {text: '', more: false});
  assert.deepEqual(L.excerpt('【韩国电视台直播事故】', '韩国电视台直播事故'), {text: '', more: false});
  const long = '美国宣布对多国加征关税。' + '这一措施将影响欧盟、日本和韩国的出口商，预计价格会上涨。'.repeat(6);
  const e = L.excerpt(long, '关税');
  assert.equal(e.more, true);
  assert.ok(/。$/.test(e.text), '在句末收住，不截半句');
  assert.ok([...e.text].length <= 140);
  const en = L.excerpt('Apple released iOS 3.5 today. It fixes many bugs and adds features. '.repeat(4), 'x');
  assert.ok(en.text.endsWith('features.'), '英文小数点不算句末');
  const run = L.excerpt('这是一个很长的第一句，'.repeat(20), 'x');
  assert.ok(run.more && run.text.endsWith('…') && [...run.text].length <= 141, '第一句太长就在停顿处收住');
  const row = L.feedRowHTML({...base, summary: long, image: null});
  assert.match(row, /<p class="sum">美国宣布对多国加征关税。.*<span class="more">继续读 ›<\/span><\/p>/);
  const dup = L.feedRowHTML({...base, title: '只有一句', summary: '只有一句', image: null});
  assert.doesNotMatch(dup, /class="sum/, '摘要和标题一样：不重复，也不说「没有摘要」');
});

test('A2：来源前的平台图标只按配置的来源类型标，不从 id 猜；浏览、评论数不进列表', () => {
  L.setSourcePlatforms([{source_platforms: {tnews365: 'telegram', shuangyunews_rss: 'telegram', 'github-blog': 'feed', 'github-trending': 'page'}}]);
  try {
    assert.match(L.feedRowHTML(base), /<img class="plat" src="icons\/telegram.svg" alt="Telegram"[^>]*><span class="src">竹新社<\/span>/);
    assert.match(L.feedRowHTML({...base, source_id: 'shuangyunews_rss'}), /icons\/telegram.svg/, 'id 带 rss 字样也按配置算 Telegram');
    assert.match(L.feedRowHTML({...base, source_id: 'github-blog'}), /icons\/blog.svg" alt="RSS"/);
    assert.doesNotMatch(L.feedRowHTML({...base, source_id: 'github-trending'}), /class="plat"/);
    assert.doesNotMatch(L.feedRowHTML({...base, source_id: 'unknown'}), /class="plat"/);
    const row = L.feedRowHTML({...base, tg: {views: 20200, views_label: '20.2K', comments_total: 5}});
    assert.doesNotMatch(row, /20\.2K|评论 5/);
    assert.match(row, /<span class="when">11月15日 19:00<\/span><\/div>/, '时间放在最后（靠右）');
  } finally { L.setSourcePlatforms([]); }
});

// A2 第一轮复核的复现场景，同类边界一并写上
test('A2 复核：lib.js 不用正则后行断言（iOS 16.4 前的 Safari 会整文件解析失败）', () => {
  const src = require('fs').readFileSync(require('path').join(__dirname, '../web-v11/lib.js'), 'utf8');
  assert.doesNotMatch(src, /\(\?<[=!]/);
});

test('A2 复核：只有和标题完全一样才省掉摘要；方向相反的数字、单个表情都留着', () => {
  assert.equal(L.excerpt('−5%', '市场预计 +5%').text, '−5%');
  assert.equal(L.excerpt('-5%', '市场预计 +5%').text, '-5%');
  assert.equal(L.excerpt('👍', '标题').text, '👍');
  assert.equal(L.excerpt('预计', '市场预计上涨').text, '预计', '只是标题的一部分也照样显示');
  assert.equal(L.excerpt('【韩国电视台直播事故】', '韩国电视台直播事故').text, '');
  assert.equal(L.excerpt('韩国电视台直播事故。', '韩国电视台直播事故').text, '');
  assert.equal(L.excerpt('……', '标题').text, '……', '全是标点也不当成和标题重复');
});

test('A2 复核：141–180 字的单句也收住并接「继续读」；停顿在前面也用，不截在词中间', () => {
  const one = '这次会议讨论了很多议题，' + '包括经济发展、社会保障、教育改革、医疗卫生、环境保护，'.repeat(5) + '最后达成共识。';
  assert.ok([...one].length > 140 && [...one].length <= 180, '前提：141–180 字');
  const e = L.excerpt(one, 'x');
  assert.equal(e.more, true);
  assert.ok(e.text.endsWith('…') && [...e.text].length <= 141);
  assert.ok(/，…$|、…$/.test(e.text) === false && /[^，、；：]…$/.test(e.text), '在停顿处收住，不把逗号留在末尾');
  const early = '会议结束后，' + '各方代表陆续离场并接受媒体采访表示对结果满意希望继续推进合作'.repeat(8) + '。';
  const r = L.excerpt(early, 'x');
  assert.equal(r.text, '会议结束后…', '唯一的停顿在很前面也在那里收，不硬截在词中间');
  const en = L.excerpt('word '.repeat(60).trim(), 'x');
  assert.ok(en.text.endsWith('word…'), '英文没有标点就在空格处收');
});

test('A2 复核：英文缩写、首字母、小写续句不算句末', () => {
  const pre = '前面的内容大约有一百多字，'.repeat(8) + '这是前文的最后一句。';
  const e = L.excerpt(pre + 'Dr. 王医生说情况已经稳定，后续还会继续观察。' + '补充说明。'.repeat(10), 'x');
  assert.ok(!e.text.endsWith('Dr.'), '不在 Dr. 后断开');
  assert.ok(e.text.endsWith('这是前文的最后一句。') || e.text.endsWith('后续还会继续观察。'));
  const s = 'The U.S. economy grew. J. K. Rowling said e.g. this works. Mr. Smith agreed. '.repeat(3) + 'End.';
  const r = L.excerpt(s, 'x');
  assert.ok(r.text.endsWith('agreed.') || r.text.endsWith('works.') || r.text.endsWith('grew.'), r.text);
  assert.ok(!/(U\.S\.|J\.|K\.|e\.g\.|Mr\.)$/.test(r.text));
});

test('A2 复核：只有封面的 TG 视频、小图视频都标「视频」；照片不标', () => {
  const posterOnly = L.feedRowHTML({...base, image: {url: 'media/v.webp', width: 800, height: 450}, tg: {video_unavailable: true, media: [{type: 'image', url: 'https://cdn/p.jpg'}]}});
  assert.match(posterOnly, /<span class="vid-badge">视频<\/span>/);
  const smallVideo = L.feedRowHTML({...base, image: {url: 'media/v.webp', width: 200, height: 100}, tg: {media: [{type: 'video', url: 'https://cdn/v.mp4'}]}});
  assert.doesNotMatch(smallVideo, /feed-row cover/);
  assert.match(smallVideo, /<div class="thumb video"><img[^>]*><span class="vid-badge">视频<\/span><\/div>/);
  const photo = L.feedRowHTML({...base, image: {url: 'media/p.webp', width: 800, height: 450}, tg: {media: [{type: 'image', url: 'https://cdn/p.jpg'}]}});
  assert.doesNotMatch(photo, /vid-badge/);
});

// A2 第二轮复核的复现场景
test('A2 复核 2：换行不算句末；首句过长时换行处也可作停顿', () => {
  const s = '据外媒报道：\n' + '当地时间周五上午，一列载有数百名乘客的列车在山区路段发生脱轨事故，救援人员已经赶到现场展开搜救，'.repeat(3) + '目前伤亡情况仍在统计中。';
  const e = L.excerpt(s, 'x');
  assert.equal(e.more, true);
  assert.ok([...e.text].length > 60 && e.text.endsWith('…'), e.text);
  assert.equal(L.excerpt('第一行。\n第二行内容。' + '补充说明。'.repeat(30), 'x').text.startsWith('第一行。\n第二行内容。'), true, '句号后的换行不影响按句收');
});
