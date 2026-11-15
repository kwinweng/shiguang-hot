/* 拾光热榜 v1 新版前端（纯静态、无框架、无第三方依赖）。
   交互以 v10 设计稿为准：两种翻法、频道顶部 banner、信息流、时事热搜块、整页正文 + 返回原位、无限加载、刷新/下拉刷新。
   收藏 / 搜索由 web-v11/features/*.js 通过 Rebang.register(name, mount) 挂到 #view-favorites / #search-panel。
   2026-11-15 21:26 阿欢改：底栏「历史」→「热搜」（当前热搜 + 按北京日期回看），时事频道不再嵌热搜；
   博主页加「Grok bot」渠道（今日重点/推特爆款/环球要闻/GitHub 热门）；每个频道、每个博主都有「查看更多」整页。
   2026-11-15 22:08–22:11 阿欢改（v13）：各页标题吸顶；TG 引用/转发卡、表情回应/浏览/公开评论；详情上一条/下一条；
   卡片手势（左滑收藏、右滑分享、长按菜单）、详情左边缘右滑返回、所有列表下拉刷新、双击底栏回顶部；公众号正文按原文顺序；
   顶栏日期居左只写一次。手势优先级见下方「手势」段注释。 */
(function () {
  'use strict';
  const L = window.RebangLib;
  const DATA = 'data';
  const MKEY = 'rebang-v11-mode';
  const NOTE_KEY = 'rebang-v11-note-closed';
  const UD_FIRST = 6;     // 上下看频道：每个频道先放几条
  const UD_STEP = 20;     // 「继续看」每次加几条
  const BL_PREVIEW = 10;  // 博主页每个平台 / 每个人先放几条，其余点「查看更多」
  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => [...r.querySelectorAll(s)];

  /* ---------- 功能模块注册（features 先到会进 _queue） ---------- */
  let booted = false;
  const registry = {};
  const mounted = {};
  const pre = window.Rebang || {};
  const Rebang = window.Rebang = Object.assign(pre, {
    register(name, mount) {
      registry[name] = mount;
      if (booted && name === 'search') mountFeature('search');
      if (booted && currentView() === name) mountFeature(name);
    },
  });
  (pre._queue || []).splice(0).forEach(([n, m]) => Rebang.register(n, m));

  /* ---------- 状态 ---------- */
  let meta = null;
  let hot = null;
  let hotActive = null;
  let hotDay = null;              // null = 现在（data/hotsearch.json），否则 YYYY-MM-DD
  let hotIndex = null;
  const hotDays = {};
  let bloggers = null;
  let plat = 'x';
  let person = 'all';
  let mode = localStorage.getItem(MKEY) === 'ud' ? 'ud' : 'lr';
  const items = new Map();        // id → 完整条目
  const ch = {};                  // slug → {list, page, pages, total, shown, loading, error}
  let articleOpen = false, articleId = null, returnState = null;
  let more = null;                // 「查看更多」整页：{key, title, type:'ch'|'bl', slug|plat+pkey, list, page, pages, total, loading, error}
  let idIndex = null;
  let pendingList = null;         // 收藏/搜索模块点开条目时的同列表顺序（给详情的上一条/下一条）

  const ctx = {
    dataBase: DATA,
    get now() { return new Date(); },
    openItem: (it) => { const list = pendingList; pendingList = null; return openItem(it, {list}); },
    toast: (t) => toast(t),
    fetch: (u, o) => fetch(u, o),
    searchButton: null,
  };

  async function getJSON(path, fresh) {
    const res = await fetch(`${DATA}/${path}${fresh ? (path.includes('?') ? '&' : '?') + 't=' + Date.now() : ''}`, fresh ? {cache: 'no-store'} : undefined);
    if (!res.ok) throw new Error(`${path}: HTTP ${res.status}`);
    return res.json();
  }
  function remember(list) { (list || []).forEach(it => it && it.id && items.set(it.id, it)); return list || []; }
  function toast(t) { const el = $('#toast'); el.textContent = t; el.classList.add('on'); clearTimeout(toast._t); toast._t = setTimeout(() => el.classList.remove('on'), 3200); }
  function channels() { return (meta && meta.channels) || []; }

  /* ---------- 数据 ---------- */
  async function loadPage(slug) {
    const st = ch[slug];
    if (st.loading || (st.page >= st.pages && st.page > 0)) return false;
    st.loading = true; st.error = null;
    try {
      const page = await getJSON(`channel/${slug}/page-${st.page + 1}.json`);
      st.list.push(...remember(page.items));
      st.page = page.page; st.pages = page.pages; st.total = page.total;
      return true;
    } catch (e) {
      st.error = String(e.message || e);
      return false;
    } finally { st.loading = false; }
  }
  async function loadAll(fresh) {
    meta = await getJSON('meta.json', fresh);
    channels().forEach(c => {
      remember(c.banner);
      ch[c.slug] = {list: [], page: 0, pages: c.pages || 1, total: c.feed_total || 0, shown: UD_FIRST, loading: false, error: null};
    });
    await Promise.all([
      ...channels().map(c => loadPage(c.slug)),
      getJSON('hotsearch.json', fresh).then(h => { hot = h; }).catch(() => { hot = null; }),
    ]);
  }
  async function findItem(id) {
    if (items.has(id)) return items.get(id);
    try {
      idIndex = idIndex || await getJSON('id-index.json');
      const file = idIndex[id];
      if (!file) return null;
      const data = await getJSON(file);
      remember(data.items); remember((data.channels || []).flatMap(c => c.banner || []));
      return items.get(id) || null;
    } catch (e) { return null; }
  }

  /* ---------- 频道渲染 ---------- */
  function unavailableNote(c) {
    const bad = c.unavailable || [];
    if (!bad.length) return '';
    return `<div class="note">暂时取不到：${bad.map(s => L.esc(s.name || s.id)).join('、')}。抓到之前先空着。</div>`;
  }
  function feedFooter(slug) {
    const st = ch[slug];
    if (st.error) return `<div class="load-err">没加载出来。<button type="button" data-retry="${slug}">再试一次</button></div>`;
    if (mode === 'ud') {
      const left = st.total - Math.min(st.shown, st.total);
      if (left > 0) return `<button type="button" class="more-btn" data-more="${slug}">继续看「${L.esc(nameOf(slug))}」（还有 ${left} 条）</button>`;
      return st.total ? `<div class="end-hint" data-end="${slug}">没有更多了</div>` : '';
    }
    if (st.page < st.pages) return `<div class="sentinel" data-ch="${slug}"></div><div class="load-hint" data-load="${slug}">下滑加载更多</div>`;
    return `<div class="end-hint" data-end="${slug}">没有更多了</div>`;
  }
  function nameOf(slug) { const c = channels().find(x => x.slug === slug); return c ? c.name : slug; }
  function visibleFeed(slug) { const st = ch[slug]; return mode === 'ud' ? st.list.slice(0, st.shown) : st.list; }
  function channelInner(c, i) {
    const st = ch[c.slug];
    const feed = visibleFeed(c.slug);
    const empty = !c.banner.length && !st.total ? '<p class="muted">这一频道暂时还没有内容。</p>' : '';
    const hint = mode === 'ud' ? '左右滑顶部图，下滑看下一频道' : (i < channels().length - 1 ? '左滑看下一频道' : '已经是最后一个频道');
    return `<div class="ch-head"><div class="ch-kicker"${mode === 'lr' ? ' style="padding:0"' : ''}><span class="idx">${i + 1} / ${channels().length}</span><span class="hint">${hint}</span></div>
      <div class="ch-row"><h2 class="ch">${L.esc(c.name)}</h2>${c.total ? `<button type="button" class="see-more" data-see="ch:${L.esc(c.slug)}">查看更多<span aria-hidden="true">›</span></button>` : ''}</div></div>
      <p class="desc">${L.esc(c.desc || '')}</p>
      ${unavailableNote(c)}
      ${L.bannerHTML(c.slug, c.banner)}
      <div class="feed" data-ch="${c.slug}">${empty}<div class="feed-list">${feed.map(L.feedRowHTML).join('')}</div><div class="feed-foot">${feedFooter(c.slug)}</div></div>`;
  }
  function renderChannels() {
    $('#modeLR').classList.toggle('on', mode === 'lr');
    $('#modeUD').classList.toggle('on', mode === 'ud');
    $('#modeLR').setAttribute('aria-pressed', String(mode === 'lr'));
    $('#modeUD').setAttribute('aria-pressed', String(mode === 'ud'));
    const root = $('#channelRoot');
    if (mode === 'ud') {
      root.className = 'pager-a';
      root.innerHTML = channels().map((c, i) => `<section class="block-a" data-ch="${c.slug}">${channelInner(c, i)}</section>`).join('') +
        '<div class="end-hint" data-end="channels">没有更多了</div>';
    } else {
      root.className = 'pager-b';
      root.innerHTML = channels().map((c, i) => `<article class="page-b" data-ch="${c.slug}">${channelInner(c, i)}</article>`).join('');
    }
    bindLoaders(); bindGestures(); fixBrokenThumbs(root);
  }
  function hostOf(slug) { return mode === 'lr' ? $(`.page-b[data-ch="${slug}"]`) : $(`.block-a[data-ch="${slug}"]`); }
  function renderFeed(slug, from) {
    const host = hostOf(slug); if (!host) return;
    const list = host.querySelector('.feed-list');
    const feed = visibleFeed(slug);
    list.insertAdjacentHTML('beforeend', feed.slice(from).map(L.feedRowHTML).join(''));
    host.querySelector('.feed-foot').innerHTML = feedFooter(slug);
    fixBrokenThumbs(list);
    bindLoaders();
  }
  function fixBrokenThumbs(scope) {
    $$('.feed-row .thumb img', scope).forEach(img => {
      if (img._bound) return; img._bound = true;
      img.addEventListener('error', () => { const row = img.closest('.feed-row'); img.closest('.thumb').remove(); row.classList.add('noimg'); }, {once: true});
    });
  }
  async function loadMore(slug) {
    const st = ch[slug];
    const before = visibleFeed(slug).length;
    if (mode === 'ud') {
      st.shown += UD_STEP;
      while (st.list.length < Math.min(st.shown, st.total) && st.page < st.pages && !st.error) { if (!(await loadPage(slug))) break; }
    } else if (!(await loadPage(slug)) && !st.error) return;
    renderFeed(slug, before);
  }
  let observers = [];
  function bindLoaders() {
    observers.forEach(o => o.disconnect()); observers = [];
    if (mode !== 'lr') return;
    $$('.page-b').forEach(page => {
      const obs = new IntersectionObserver(es => es.forEach(e => { if (e.isIntersecting && e.target.dataset.ch) loadMore(e.target.dataset.ch); }), {root: page, rootMargin: '600px 0px', threshold: 0});
      page.querySelectorAll('.sentinel').forEach(el => obs.observe(el));
      observers.push(obs);
    });
  }

  /* ---------- 博主 ---------- */
  function platIcon(p) { return `<img class="plat-ico" src="${L.esc(p.icon || `icons/${p.id}.svg`)}" alt="" width="22" height="22">`; }
  function posts() { return (bloggers && bloggers.items) || []; }
  function platOf(id) { return ((bloggers && bloggers.platforms) || []).find(p => p.id === id); }
  function recentCount(id) {
    const since = new Date(meta.built_at).getTime() - 24 * 3600e3;
    return posts().filter(p => p.blogger.platform === id && new Date(p.published_at).getTime() >= since).length;
  }
  function renderBloggers() {
    if (!bloggers) { $('#bloggerList').innerHTML = '<p class="muted">正在加载…</p>'; return; }
    $('#platChips').innerHTML = bloggers.platforms.map(p => {
      const n = recentCount(p.id);
      return `<button type="button" class="chip logo${p.id === plat ? ' on' : ''}" data-plat="${p.id}" aria-label="${L.esc(p.name)}" title="${L.esc(p.name)}">${platIcon(p)}${n ? `<span class="unread" aria-label="${n} 条 24 小时内的新帖">${n}</span>` : ''}</button>`;
    }).join('');
    const p = platOf(plat);
    const mine = posts().filter(x => x.blogger.platform === plat);
    const avatarOf = h => (mine.find(x => x.blogger.handle === h && x.blogger.avatar) || {blogger: {}}).blogger.avatar;
    $('#peopleRow').innerHTML = p && p.accounts.length ? `<button type="button" class="ppl${person === 'all' ? ' on' : ''}" data-person="all"><span class="ph-av letter">全</span><span>全部</span></button>` +
      p.accounts.map(a => { const av = avatarOf(a.handle); return `<button type="button" class="ppl${person === a.handle ? ' on' : ''}" data-person="${L.esc(a.handle)}">${av ? `<img src="${L.esc(av)}" alt="">` : `<span class="ph-av letter">${L.esc((a.name || a.handle)[0])}</span>`}<span>${L.esc(a.name)}</span></button>`; }).join('') : '';
    let list = mine;
    if (person !== 'all') list = list.filter(x => x.blogger.handle === person);
    let empty = '';
    if (!list.length) {
      const acc = p && p.accounts.find(a => a.handle === person);
      const last = (x) => x && x.last_ok_at ? `上次成功抓取：${L.fmtTime(x.last_ok_at)}。` : '还没有成功抓取过。';
      if (p && !p.accounts.length) empty = `${p.name}：${p.reason || '本期名单为空'}。`;
      else if (p && !p.connected && p.status && p.status !== 'ok') empty = `${p.name}暂时没有内容：${p.reason || p.status}。${last(p)}`;
      else if (p && !p.connected) empty = `${p.name}的内容还没接上。${last(p)}`;
      else if (acc && acc.status && !['ok', 'empty'].includes(acc.status)) empty = `${acc.name}暂时没有内容（${acc.status === 'not_configured' ? '需要登录，第一期先不接' : '这次没抓到'}）。${last(acc)}`;
      else if (acc) empty = `${acc.name}最近没有新帖。${last(acc)}`;
      else empty = '这一栏暂时还没有帖子。';
      empty = empty.replace(/。。/g, '。');
    }
    const acc = p && person !== 'all' ? p.accounts.find(a => a.handle === person) : null;
    const total = acc ? (acc.total || 0) : (p ? p.count : 0);
    const key = acc ? acc.key : 'all';
    const who = acc ? acc.name : (p ? p.name : '');
    const moreBtn = total ? `<button type="button" class="more-btn see-more-bl" data-see="bl:${L.esc(plat)}:${L.esc(key)}">查看更多「${L.esc(who)}」（共 ${total} 条）</button>` : '';
    $('#bloggerList').innerHTML = empty ? `<div class="empty-plat">${L.esc(empty)}</div>` : list.slice(0, BL_PREVIEW).map(postCardHTML).join('') + moreBtn;
  }
  /** Grok bot 渠道是我们整理的成品（有标题、摘要、配图），按资讯卡显示；其余平台按推文卡 */
  function postCardHTML(x) { return x.blogger && x.blogger.platform === 'grok' ? L.feedRowHTML(x) : L.tweetCardHTML(x, true); }
  async function ensureBloggers() {
    if (bloggers) return;
    try { bloggers = await getJSON('bloggers.json'); remember(bloggers.items); } catch (e) { bloggers = {platforms: [], items: []}; }
    if (!platOf(plat) && bloggers.platforms[0]) plat = bloggers.platforms[0].id;
    renderBloggers();
  }

  /* ---------- 热搜（底栏，替换原历史页） ---------- */
  async function ensureHotIndex() {
    if (hotIndex) return hotIndex;
    try { hotIndex = await getJSON('hotsearch/index.json'); } catch (e) { hotIndex = {dates: []}; }
    return hotIndex;
  }
  function hotPayload() { return hotDay ? hotDays[hotDay] : hot; }
  function renderHotBody() {
    const host = $('#hotHost');
    const payload = hotPayload();
    if (hotDay && payload === undefined) { host.innerHTML = '<p class="muted">正在加载…</p>'; return; }
    if (!payload || !(payload.providers || []).length) { host.innerHTML = `<p class="muted">${hotDay ? '这天没有存下热搜。' : '热搜暂时没加载出来，稍后点右上角刷新再试。'}</p>`; return; }
    const when = payload.generated_at ? (hotDay ? `这是 ${L.fmtDay(hotDay + 'T12:00:00+08:00')} 最后一次抓到的榜单（${L.fmtTime(payload.generated_at)}）。` : `抓取于 ${L.fmtTime(payload.generated_at)}。`) : '';
    host.innerHTML = `${when ? `<p class="hot-day-note">${L.esc(when)}</p>` : ''}${L.hotsearchHTML(payload, hotActive, false, 1000)}`;
  }
  async function renderHot() {
    const idx = await ensureHotIndex();
    const today = (meta && meta.today) || L.beijingDate(new Date());
    const past = (idx.dates || []).filter(d => d.date !== today);
    const chips = [{date: null, label: '今天 · 现在'}].concat(past.map(d => ({date: d.date, label: L.fmtDay(d.date + 'T12:00:00+08:00')})));
    $('#hotDates').innerHTML = chips.map(c => `<button type="button" role="tab" class="chip${(c.date || null) === hotDay ? ' on' : ''}" data-hot-day="${c.date || ''}" aria-selected="${(c.date || null) === hotDay}">${L.esc(c.label)}</button>`).join('');
    $('#view-hot').dataset.hotDay = hotDay || 'now';
    renderHotBody();
  }
  async function pickHotDay(day) {
    hotDay = day || null;
    renderHot();
    if (hotDay && hotDays[hotDay] === undefined) {
      try { hotDays[hotDay] = await getJSON(`hotsearch/${hotDay}.json`); } catch (e) { hotDays[hotDay] = null; }
      if (hotDay === day) renderHotBody();
    }
  }

  /* ---------- 查看更多（频道 / 博主整页，无限下滑到「没有更多了」） ---------- */
  function moreSpec(key) {
    const [type, a, b] = String(key).split(':');
    if (type === 'ch') { const c = channels().find(x => x.slug === a); return c ? {key, type, slug: a, title: c.name, total: c.total, head: c.banner || []} : null; }
    if (type === 'bl') {
      const p = platOf(a); if (!p) return null;
      const acc = b === 'all' ? null : p.accounts.find(x => x.key === b);
      if (b !== 'all' && !acc) return null;
      return {key, type, plat: a, pkey: b, title: acc ? `${acc.name} · ${p.name}` : p.name, total: acc ? acc.total : p.count, head: []};
    }
    return null;
  }
  function morePath(m, n) { return m.type === 'ch' ? `channel/${m.slug}/page-${n}.json` : `blogger/${m.plat}/${m.pkey}/page-${n}.json`; }
  function moreRow(it) { return it.kind === 'post' ? postCardHTML(it) : L.feedRowHTML(it); }
  function moreFoot() {
    if (more.error) return `<div class="load-err">没加载出来。<button type="button" data-more-retry>再试一次</button></div>`;
    if (more.page < more.pages) return '<div class="more-sentinel"></div><div class="load-hint">下滑加载更多</div>';
    return more.list.length ? '<div class="end-hint" data-end="more">没有更多了</div>' : '<p class="muted" style="padding:16px">这里暂时还没有内容。</p>';
  }
  let moreObs = null;
  function bindMoreLoader() {
    if (moreObs) moreObs.disconnect();
    const el = $('#moreBody .more-sentinel'); if (!el) return;
    moreObs = new IntersectionObserver(es => es.forEach(e => { if (e.isIntersecting) loadMorePage(); }), {root: $('#moreBody'), rootMargin: '600px 0px', threshold: 0});
    moreObs.observe(el);
  }
  async function loadMorePage() {
    const m = more; if (!m || m.loading || (m.page >= m.pages && m.page > 0)) return;
    m.loading = true; m.error = null;
    const before = m.list.length;
    try {
      const page = await getJSON(morePath(m, m.page + 1));
      if (more !== m) return;
      const seen = new Set(m.list.map(x => x.id));
      m.list.push(...remember(page.items).filter(x => !seen.has(x.id)));
      m.page = page.page; m.pages = page.pages;
    } catch (e) { m.error = String(e.message || e); } finally { m.loading = false; }
    if (more !== m) return;
    const body = $('#moreBody');
    body.querySelector('.more-list').insertAdjacentHTML('beforeend', m.list.slice(before).map(moreRow).join(''));
    body.querySelector('.more-foot').innerHTML = moreFoot();
    fixBrokenThumbs(body); bindMoreLoader();
    if (m.page < m.pages && body.scrollHeight <= body.clientHeight + 40) loadMorePage();
  }
  async function openMore(key, opts = {}) {
    if (key.startsWith('bl:')) await ensureBloggers();
    const spec = moreSpec(key);
    if (!spec) { toast('这一栏找不到了。'); return; }
    more = {...spec, list: remember(spec.head.slice()), page: 0, pages: 1, loading: false, error: null};
    $('#moreTitle').textContent = `${spec.title} · 全部 ${spec.total || 0} 条`;
    const body = $('#moreBody');
    body.innerHTML = `<h2 class="ch more-h">${L.esc(spec.title)}</h2><p class="desc more-desc">全部 ${spec.total || 0} 条，按时间从新到旧。</p><div class="more-list">${more.list.map(moreRow).join('')}</div><div class="more-foot"></div>`;
    body.scrollTop = 0;
    $('#moreView').classList.add('on');
    $('#moreView').dataset.moreKey = key;
    if (!opts.fromPop) history.pushState({more: key}, '', '#/more/' + encodeURIComponent(key));
    await loadMorePage();
  }
  function closeMore(opts = {}) {
    if (!more) return;
    more = null; if (moreObs) moreObs.disconnect();
    $('#moreView').classList.remove('on');
    delete $('#moreView').dataset.moreKey;
    if (!opts.fromPop && history.state && history.state.more) history.back();
  }

  /* ---------- 视图与功能挂载 ---------- */
  const MOUNT_EL = {favorites: '#view-favorites', search: '#search-panel'};
  const PLACEHOLDER = {favorites: '收藏功能还没接入。'};
  function mountFeature(name) {
    const el = $(MOUNT_EL[name]);
    if (!el) return null;
    if (mounted[name]) { const h = mounted[name]; if (h && typeof h.refresh === 'function') h.refresh(); return h; }
    if (!registry[name]) {
      if (PLACEHOLDER[name] && !el.innerHTML.trim()) el.innerHTML = `<div class="sub"><p class="muted">${PLACEHOLDER[name]}</p></div>`;
      return null;
    }
    el.innerHTML = '';
    mounted[name] = registry[name](el, ctx) || {};
    return mounted[name];
  }
  function currentView() { const v = $$('.view').find(el => el.classList.contains('on')); return v ? v.id.replace('view-', '') : 'channels'; }
  function showView(name, keepArticle) {
    $$('.view').forEach(v => v.classList.toggle('on', v.id === 'view-' + name));
    $$('.tabbar button').forEach(b => { b.classList.toggle('on', b.dataset.view === name); b.setAttribute('aria-current', b.dataset.view === name ? 'page' : 'false'); });
    if (name === 'blogger') ensureBloggers().then(renderBloggers);
    if (name === 'hot') renderHot();
    if (name === 'favorites') mountFeature(name);
    if (!keepArticle && articleOpen) closeArticle();
    if (!keepArticle && more) closeMore();
  }

  /* ---------- 正文（整页）与返回原位 ---------- */
  function captureScroll() {
    const root = $('#channelRoot');
    const st = {view: currentView(), mode, search: $('#search-panel').classList.contains('on')};
    st.bannersX = $$('.banner-rail').map(c => c.scrollLeft);
    if (mode === 'lr') { st.pagerX = root.scrollLeft; st.pagesY = $$('.page-b').map(p => p.scrollTop); } else st.pagerY = root.scrollTop;
    st.subY = $$('.view.on .sub, .view.on [class*="sub"]').map(s => s.scrollTop);
    st.searchY = $$('#search-panel .sub').map(s => s.scrollTop);
    st.moreY = more ? $('#moreBody').scrollTop : null;
    return st;
  }
  function restoreScroll(st) {
    if (!st) return;
    if (st.view && currentView() !== st.view) showView(st.view, true);
    const apply = () => {
      const root = $('#channelRoot');
      if (st.mode === mode) {
        if (mode === 'lr') { root.scrollLeft = st.pagerX || 0; const pages = $$('.page-b'); (st.pagesY || []).forEach((y, i) => { if (pages[i]) pages[i].scrollTop = y; }); } else root.scrollTop = st.pagerY || 0;
        const rails = $$('.banner-rail'); (st.bannersX || []).forEach((x, i) => { if (rails[i]) rails[i].scrollLeft = x; });
      }
      const subs = $$('.view.on .sub, .view.on [class*="sub"]'); (st.subY || []).forEach((y, i) => { if (subs[i]) subs[i].scrollTop = y; });
      if (st.search) { $('#search-panel').classList.add('on'); const ss = $$('#search-panel .sub'); (st.searchY || []).forEach((y, i) => { if (ss[i]) ss[i].scrollTop = y; }); }
      if (st.moreY != null && more) $('#moreBody').scrollTop = st.moreY;
    };
    apply(); requestAnimationFrame(() => requestAnimationFrame(apply));
  }
  function commentsHTML(it) {
    const tg = it.tg || {};
    const list = tg.comments || [];
    if (!list.length) return '';   // 频道没开公开评论，或挂件里没有可见评论：不显示，不编
    const total = tg.comments_total ? `共 ${L.esc(L.fmtN(tg.comments_total))} 条，` : '';
    return `<section class="tg-comments" data-tg-comments><h4>评论</h4><p class="cmt-note">${total}这里只显示 Telegram 公开页面上能看到的最近 ${list.length} 条。<a href="${L.esc(it.url)}" target="_blank" rel="noopener">在 Telegram 看全部</a></p>${list.map(c => `<div class="comment"><span class="av letter">${L.esc((c.display_name || '?').trim()[0] || '?')}</span><div><div class="nm" style="font-size:13px">${L.esc(c.display_name)}${c.reply_to ? ` <span class="meta">回复 ${L.esc(c.reply_to)}</span>` : ''}${c.published_at ? ` <span class="meta">· ${L.esc(L.fmtTime(c.published_at))}</span>` : ''}</div><div class="t-body">${L.esc(c.text)}</div></div></div>`).join('')}</section>`;
  }
  function articleHTML(it) {
    const d = L.display(it);
    const slot = '<div class="fav-slot" data-fav-slot></div>';
    const open = it.url ? `<a class="primary" href="${L.esc(it.url)}" target="_blank" rel="noopener">打开原文</a>` : '';
    const isGrok = it.kind === 'post' && it.blogger && it.blogger.platform === 'grok';
    const blocks = d.blocks || it.blocks;
    if (blocks && blocks.length && !(it.kind === 'post' && isGrok)) {
      // 公众号 / 博客 / 抽出的新闻正文：按原文顺序；有译文 blocks 时直接显示中文，原文可展开
      const b = it.blogger || {};
      const who = (b.display_name || it.source_name);
      const origBlocks = d.translated && it.blocks && d.blocks ? `<div class="art-tools"><button type="button" class="orig-btn" data-art-orig>看原文</button></div><div class="art-orig" data-art-orig-box><div class="art-blocks">${L.blocksHTML(it.blocks)}</div></div>` : '';
      return `<div class="src art-src"><span>${L.esc(who)} · ${L.esc(L.fmtTime(it.published_at))}</span>${d.translated ? `<span class="mt-badge">${L.esc(d.label)}</span>` : ''}</div>
        <h3 class="art-title">${L.esc(d.title)}</h3><div class="art-blocks" data-blocks>${L.blocksHTML(blocks)}</div>${origBlocks}
        <div class="actions">${slot}${open}</div>`;
    }
    if (it.kind === 'post' && !isGrok) return `${L.tweetCardHTML(it, false)}<div class="actions">${slot}${open}</div>`;
    let text = (d.body || d.summary || '').trim();
    // TG 正文第一行常是「【标题】」，标题已单独显示，正文里不再重复
    const first = text.split('\n')[0].replace(/[【】\s]/g, '');
    if (first && first === d.title.replace(/[【】\s]/g, '')) text = text.slice(text.indexOf('\n') + 1 || text.length).trim();
    const orig = d.translated ? `<div class="art-tools"><button type="button" class="orig-btn" data-art-orig>看原文</button></div><div class="art-orig" data-art-orig-box><h4>${L.esc(d.orig.title)}</h4>${L.esc(d.orig.body || d.orig.summary)}</div>` : '';
    const bare = L.isBareForward(it);
    const cover = it.image && it.image.url ? `<img class="cover" src="${L.esc(it.image.url)}" alt="${L.esc(it.image.alt || '')}" data-zoom="${L.esc(it.image.url)}">` : '';
    const head = `${cover}
      <div class="src art-src"><span>${L.esc(it.source_name)} · ${L.esc(L.fmtTime(it.published_at))}</span>${it.highlight ? '<span class="t-badge">今日重点</span>' : ''}${d.translated ? `<span class="mt-badge">${L.esc(d.label)}</span>` : ''}</div>`;
    const main = bare ? '<div class="fwd-tag">转发</div>' :
      `<h3 class="art-title">${L.esc(d.title)}</h3>${text || !it.quote ? `<p class="art-text${text ? '' : ' none'}">${L.esc(text || L.NO_BODY)}</p>` : ''}${orig}`;
    return `${head}${main}${L.quoteCardHTML(it, true)}${L.tgStatsHTML(it, true)}${commentsHTML(it)}
      <div class="actions">${slot}${open}</div>`;
  }
  function attachFav(slot, it) {
    const handle = mounted.favorites || (registry.favorites && mountFeature('favorites'));
    if (handle && typeof handle.attachButton === 'function') return handle.attachButton(slot, it);
    if (window.RebangFavorites && window.RebangFavorites.attachButton) return window.RebangFavorites.attachButton(slot, it, {toast});
    slot.remove();
  }
  /* 详情里的「上一条 / 下一条」：在打开它的那个列表里按顺序走（频道信息流、banner、查看更多、博主、收藏、搜索结果） */
  let navList = null;   // {ids, at}
  const LIST_SCOPE = '.feed-list, .banner-rail, .more-list, #bloggerList, [data-favorites-list], #search-panel';
  function listContext(card) {
    const scope = card && card.closest(LIST_SCOPE);
    if (!scope) return null;
    const ids = [];
    scope.querySelectorAll('[data-id], [data-item-id]').forEach(el => { const id = el.dataset.id || el.dataset.itemId; if (id && !ids.includes(id)) ids.push(id); });
    return ids.length > 1 ? ids : null;
  }
  function navHTML() {
    const at = navList ? navList.ids.indexOf(articleId) : -1;
    const prev = at > 0, next = at >= 0 && at < navList.ids.length - 1;
    return `<button type="button" class="art-nav-btn" data-nav="-1" aria-label="上一条"${prev ? '' : ' disabled'}><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M15 5l-7 7 7 7"/></svg></button>` +
      (at >= 0 ? `<span class="art-nav-pos">${at + 1} / ${navList.ids.length}</span>` : '') +
      `<button type="button" class="art-nav-btn" data-nav="1" aria-label="下一条"${next ? '' : ' disabled'}><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M9 5l7 7-7 7"/></svg></button>`;
  }
  function renderNav() { const el = $('#artNav'); el.hidden = !(navList && navList.ids.includes(articleId)); el.innerHTML = el.hidden ? '' : navHTML(); }
  async function step(dir) {
    if (!navList || !articleOpen) return false;
    const at = navList.ids.indexOf(articleId), to = navList.ids[at + dir];
    if (at < 0 || !to) { toast(dir > 0 ? '已经是这个列表的最后一条。' : '已经是这个列表的第一条。'); return false; }
    await openItem(to, {replace: true, keepNav: true});
    return true;
  }
  async function openItem(ref, opts = {}) {
    const id = typeof ref === 'string' ? ref : ref && ref.id;
    if (!id) return;
    let it = items.get(id) || (typeof ref === 'object' && ref.kind ? ref : null) || await findItem(id) || (typeof ref === 'object' ? ref : null);
    if (!it) {
      const fav = window.RebangFavorites && window.RebangFavorites.load ? window.RebangFavorites.load().find(x => x.id === id) : null;
      if (fav) it = fav; else { toast('这条已经不在最近一次发布的数据里了。'); return; }
    }
    if (!opts.keepNav && !opts.fromPop) navList = opts.list ? {ids: opts.list} : null;
    if (!opts.fromPop && !(articleOpen && articleId === id)) returnState = articleOpen ? returnState : captureScroll();
    $('#search-panel').classList.remove('on');
    const grok = it.kind === 'post' && it.blogger && it.blogger.platform === 'grok';
    $('#articleTitle').textContent = it.kind === 'post' && !grok ? ((it.blogger && it.blogger.display_name) || '帖子') : (L.display(it).title || '正文');
    const body = $('#articleBody');
    body.innerHTML = articleHTML(it);
    const slot = body.querySelector('[data-fav-slot]');
    if (slot) attachFav(slot, it);
    $('#articleView').classList.add('on');
    body.scrollTop = 0;
    articleOpen = true; articleId = id;
    renderNav();
    if (opts.replace && history.state && history.state.article) history.replaceState({article: id}, '', L.itemHash(id));
    else if (!opts.fromPop) history.pushState({article: id}, '', L.itemHash(id));
  }
  function closeArticle(opts = {}) {
    if (!articleOpen) return;
    articleOpen = false; articleId = null;
    $('#articleView').classList.remove('on');
    $('#articleView').style.transform = '';
    restoreScroll(returnState);
    if (!opts.fromPop && history.state && history.state.article) history.back();
  }
  window.addEventListener('popstate', e => {
    const st = e.state || {};
    const hashId = !e.state ? L.parseItemHash(location.hash) : null;
    if (st.article) openItem(st.article, {fromPop: true});
    else if (st.more) {
      if (articleOpen) closeArticle({fromPop: true});
      if (!more || more.key !== st.more) openMore(st.more, {fromPop: true});
    } else if (hashId) {
      // 已开着的页面里再点一次私聊稿链接（只改了 #/item/…）：直接打开详情，返回回到原来的位置
      if (!articleOpen) returnState = captureScroll();
      history.replaceState({article: hashId}, '', L.itemHash(hashId));
      openItem(hashId, {fromPop: true});
    } else { if (articleOpen) closeArticle({fromPop: true}); if (more) closeMore({fromPop: true}); }
  });

  /* ---------- 刷新 ---------- */
  function stampRefresh(d) { $('#refreshed').textContent = `刷新于 ${L.fmtRefreshed(d)}`; }
  async function doRefresh() {
    const btn = $('#btnRefresh');
    btn.classList.remove('spin'); void btn.offsetWidth; btn.classList.add('spin'); setTimeout(() => btn.classList.remove('spin'), 450);
    const NOTE = '刷新拿到的是最近一次发布的数据。';
    const old = meta && meta.built_at;
    let fresh;
    try { fresh = await getJSON('meta.json', true); } catch (e) { toast('刷新失败，网络或站点暂时连不上。'); hidePtr(); return; }
    stampRefresh(new Date());
    if (fresh.built_at !== old) {
      const idx = currentChannelIndex();
      items.clear(); idIndex = null; bloggers = null; hotIndex = null; Object.keys(hotDays).forEach(k => delete hotDays[k]);
      await loadAll(true);
      renderChannels();
      if (currentView() === 'hot') renderHot();
      if (currentView() === 'blogger') ensureBloggers();
      if (mode === 'lr') $('#channelRoot').scrollLeft = idx * $('#channelRoot').clientWidth;
      toast('有新内容，已更新。' + NOTE);
    } else toast('没有新内容，已是最新。' + NOTE);
    hidePtr();
  }
  function hidePtr() { const p = $('#ptr'); p.classList.remove('spin', 'show'); p.hidden = true; }
  function currentChannelIndex() { const r = $('#channelRoot'); return mode === 'lr' ? Math.round(r.scrollLeft / (r.clientWidth || 1)) : 0; }

  /* ---------- 手势（沿用 v10：跟手、回弹、动量翻页；banner 内横滑不交给换频道） ---------- */
  function ensureHInd(s) { let ind = s.querySelector(':scope > .h-ind'); if (!ind) { ind = document.createElement('div'); ind.className = 'h-ind'; ind.innerHTML = '<i></i>'; ind.setAttribute('aria-hidden', 'true'); s.appendChild(ind); } return ind; }
  function updateHInd(s) {
    const ind = s.querySelector(':scope > .h-ind'); if (!ind) return;
    const thumb = ind.querySelector('i'); const cw = s.clientWidth, sw = s.scrollWidth, sl = s.scrollLeft;
    const track = ind.clientWidth || Math.max(0, cw - 32); const w = Math.max(24, track * (sw > cw ? cw / sw : 1));
    thumb.style.width = w + 'px'; thumb.style.transform = 'translateX(' + (track - w) * (Math.max(0, sl) / Math.max(1, sw - cw)) + 'px)';
  }
  function animateScrollX(el, to, ms) {
    const from = el.scrollLeft, dist = to - from;
    if (Math.abs(dist) < 1) { el.scrollLeft = to; return; }
    const dur = ms != null ? ms : Math.min(340, 180 + Math.abs(dist) * 0.25); const t0 = performance.now();
    el.style.scrollSnapType = 'none';
    (function frame(now) { const p = Math.min(1, (now - t0) / dur); el.scrollLeft = from + dist * (1 - Math.pow(1 - p, 3)); updateHInd(el); if (p < 1) requestAnimationFrame(frame); else { el.scrollLeft = to; el.style.scrollSnapType = 'x mandatory'; } })(t0);
  }
  function bindHSwipe(scroller) {
    if (!scroller) return;
    if (scroller._gAbort) scroller._gAbort.abort();
    const ac = new AbortController(); scroller._gAbort = ac;
    ensureHInd(scroller); updateHInd(scroller);
    let sx, sy, sl, axis, lastX, lastT, vel, dragging, skip = false;
    const opt = {signal: ac.signal, passive: true};
    scroller.addEventListener('touchstart', e => {
      skip = !!(scroller.classList.contains('pager-b') && e.target.closest && e.target.closest('.banner-rail, .banner-wrap, .hot-tabs'));
      if (skip) return;
      const t = e.touches[0]; sx = t.clientX; sy = t.clientY; sl = scroller.scrollLeft; axis = null; lastT = performance.now(); lastX = sx; vel = 0; dragging = false;
      scroller.style.scrollSnapType = 'none'; scroller.style.transform = '';
    }, opt);
    scroller.addEventListener('touchmove', e => {
      if (skip) return;
      const t = e.touches[0]; const dx = t.clientX - sx, dy = t.clientY - sy;
      if (!axis) { if (Math.abs(dx) + Math.abs(dy) < 8) return; axis = Math.abs(dx) > Math.abs(dy) + 4 ? 'x' : 'y'; }
      if (axis !== 'x') return;
      if (e.cancelable) e.preventDefault();
      dragging = true; scroller.classList.add('is-drag');
      const now = performance.now(); vel = (t.clientX - lastX) / Math.max(1, now - lastT); lastX = t.clientX; lastT = now;
      const max = Math.max(0, scroller.scrollWidth - scroller.clientWidth);
      let next = sl - dx, extra = 0;
      if (next < 0) { extra = next * 0.32; next = 0; } else if (next > max) { extra = (next - max) * 0.32; next = max; }
      scroller.scrollLeft = next; scroller.style.transform = extra ? 'translateX(' + (-extra) + 'px)' : ''; updateHInd(scroller);
    }, {signal: ac.signal, passive: false});
    const end = () => {
      if (skip) { skip = false; return; }
      if (!dragging && axis == null) { scroller.style.scrollSnapType = 'x mandatory'; return; }
      dragging = false; axis = null;
      if (scroller.style.transform) { scroller.style.transition = 'transform .32s cubic-bezier(.2,.8,.2,1)'; scroller.style.transform = 'translateX(0)'; setTimeout(() => { scroller.style.transition = ''; scroller.style.transform = ''; }, 340); }
      const w = scroller.clientWidth || 1, raw = scroller.scrollLeft, max = Math.max(0, scroller.scrollWidth - scroller.clientWidth);
      let idx = Math.round(raw / w); if (Math.abs(vel) > 0.35) idx = vel < 0 ? Math.ceil(raw / w) : Math.floor(raw / w);
      animateScrollX(scroller, Math.max(0, Math.min(max, idx * w)));
      setTimeout(() => scroller.classList.remove('is-drag'), 220);
    };
    scroller.addEventListener('touchend', end, opt); scroller.addEventListener('touchcancel', end, opt);
    scroller.addEventListener('scroll', () => updateHInd(scroller), opt);
  }
  /* ---------- 手势总表（2026-11-15 22:08 阿欢要求「定好优先级并测试」）----------
     一次触摸只归一种手势，先按「从哪里开始」判，再按「先往哪个方向动」判（动 8px 后锁定方向）：
       1. 详情页：从屏幕左边缘 24px 内开始往右滑 → 返回；其余横滑 → 上一条 / 下一条（详情页里没有频道和 banner 横滑）。
       2. banner 区域里横滑 → 只翻 banner（bindHSwipe，换频道不接手）。
       3. 横向可滚的条（平台图标、日期、人物、热搜 tab）→ 原生横滚，谁也不接手。
       4. 「左右」模式的频道页 → 横滑只换频道；这里卡片不做左滑收藏/右滑分享（用长按菜单收藏/分享）。
       5. 其余列表里的卡片（上下模式频道、查看更多、博主、收藏、搜索结果）→ 横滑是卡片动作：左滑收藏，右滑分享（拉过 72px 松手才生效）。
       6. 竖向：列表已在最顶上且往下拉 → 下拉刷新；否则正常滚动。
       7. 长按卡片 0.5 秒且手指几乎没动（< 8px）→ 卡片菜单（收藏/分享/复制链接/打开原文）；之后的点击不再打开详情。
       8. 底栏同一个按钮 0.35 秒内点两下 → 当前页回到顶部（点一下照常切页）。 */
  const EDGE = 24, LOCK = 8, CARD_ACT = 72, PULL_GO = 56, LONG_MS = 500;
  const CARD_SEL = '.feed-row, .tweet, .row-item, .hero';
  const HSCROLL_SEL = '.chips, .dates, .people, .hot-tabs, .banner-rail, .banner-wrap, pre, .b-pre';
  const SCROLLER_SEL = '.page-b, .pager-a, .sub, .more-body, .article-body';
  let g = null, suppressClickUntil = 0;
  function cardItem(card) {
    const id = card && (card.dataset.id || card.dataset.itemId);
    if (!id) return null;
    if (items.get(id)) return items.get(id);
    const fav = window.RebangFavorites && window.RebangFavorites.load ? window.RebangFavorites.load().find(x => x.id === id) : null;
    return fav || {id};
  }
  function linkOf(it) { return location.origin + location.pathname + L.itemHash(it.id); }
  async function copyText(t) {
    try { await navigator.clipboard.writeText(t); return true; } catch (e) {
      const ta = document.createElement('textarea'); ta.value = t; ta.setAttribute('readonly', ''); ta.style.position = 'fixed'; ta.style.opacity = '0';
      document.body.appendChild(ta); ta.select(); let ok = false; try { ok = document.execCommand('copy'); } catch (e2) { ok = false; } ta.remove(); return ok;
    }
  }
  async function shareItem(it) {
    const url = linkOf(it), title = L.display(it).title || it.title || '拾光热榜';
    if (navigator.share) { try { await navigator.share({title, url}); return; } catch (e) { if (e && e.name === 'AbortError') return; } }
    toast(await copyText(url) ? '已复制这条的链接，可以粘贴分享。' : '没能复制链接，请长按卡片选「复制链接」再试。');
  }
  function toggleFav(it) {
    const F = window.RebangFavorites;
    if (!F || !F.toggle) { toast('收藏功能还没接入。'); return; }
    const full = items.get(it.id) || it;
    const res = F.toggle(full);
    if (mounted.favorites && mounted.favorites.refresh) mounted.favorites.refresh();
    const btn = $('#articleBody [data-favorite-button]');
    if (btn && articleId === it.id) { btn.classList.toggle('on', res.on); btn.textContent = res.on ? '取消收藏' : '收藏这条'; btn.setAttribute('aria-pressed', String(res.on)); }
    toast(res.on ? '已收藏，只存在这台设备的浏览器里。' : '已取消收藏。');
  }
  function openMenu(card) {
    const it = cardItem(card); if (!it) return;
    const F = window.RebangFavorites;
    const on = F && F.isFavorite ? F.isFavorite(it.id) : false;
    const full = items.get(it.id) || it;
    const menu = $('#cardMenu');
    menu.querySelector('.box').innerHTML = `<div class="handle"></div><div class="menu-ttl">${L.esc(L.display(full).title || full.title || '')}</div>
      <button type="button" data-menu="fav">${on ? '取消收藏' : '收藏'}</button><button type="button" data-menu="share">分享</button>
      <button type="button" data-menu="copy">复制链接</button>${full.url ? '<button type="button" data-menu="open">打开原文</button>' : ''}<button type="button" data-menu="cancel" class="cancel">取消</button>`;
    menu._item = full; menu.classList.add('on'); menu.setAttribute('aria-hidden', 'false');
  }
  function closeMenu() { const m = $('#cardMenu'); m.classList.remove('on'); m.setAttribute('aria-hidden', 'true'); m._item = null; }
  async function onMenu(e) {
    const m = $('#cardMenu');
    if (performance.now() < suppressClickUntil) return;   // 长按松手时浏览器补发的那次点击会落在菜单遮罩上，不能当成「点空白关闭」
    const b = e.target.closest('[data-menu]');
    if (!b) { if (e.target === m) closeMenu(); return; }
    const it = m._item; const act = b.dataset.menu; closeMenu();
    if (!it || act === 'cancel') return;
    if (act === 'fav') toggleFav(it);
    else if (act === 'share') shareItem(it);
    else if (act === 'copy') toast(await copyText(linkOf(it)) ? '链接已复制。' : '没能复制链接。');
    else if (act === 'open' && it.url) window.open(it.url, '_blank', 'noopener');
  }
  function setPtr(show, txt, spin) { const ptr = $('#ptr'); ptr.style.top = $('.top').offsetHeight + 'px'; ptr.hidden = !show; ptr.classList.toggle('show', !!show); ptr.classList.toggle('spin', !!spin); if (txt) ptr.querySelector('.ptr-txt').textContent = txt; }
  function resetCard(card) { if (!card) return; card.style.transition = 'transform .22s cubic-bezier(.2,.8,.2,1)'; card.style.transform = ''; delete card.dataset.swipe; setTimeout(() => { card.style.transition = ''; card.classList.remove('swiping'); }, 230); }
  function onTouchStart(e) {
    if (zoom.open || e.target.closest('#zoomView')) { g = null; return; }
    if (e.touches.length !== 1) { g = null; return; }
    const t = e.touches[0], target = e.target;
    const inArticle = !!target.closest('#articleView');
    const card = !inArticle ? target.closest(CARD_SEL) : null;
    g = {x0: t.clientX, y0: t.clientY, x: t.clientX, y: t.clientY, t0: performance.now(), axis: null, target, card,
      inArticle, edge: inArticle && t.clientX <= EDGE, hscroll: !!target.closest(HSCROLL_SEL),
      lrChannels: !!target.closest('.pager-b'), scroller: target.closest(SCROLLER_SEL), kind: null, long: null};
    if (card) g.long = setTimeout(() => { if (g && !g.axis) { g.kind = 'menu'; suppressClickUntil = performance.now() + 60000; if (navigator.vibrate) navigator.vibrate(10); openMenu(card); } }, LONG_MS);
  }
  function onTouchMove(e) {
    if (!g) return;
    const t = e.touches[0]; g.x = t.clientX; g.y = t.clientY;
    const dx = g.x - g.x0, dy = g.y - g.y0;
    if (!g.axis) {
      if (Math.abs(dx) < LOCK && Math.abs(dy) < LOCK) return;
      clearTimeout(g.long);
      if (g.kind === 'menu') return;
      g.axis = Math.abs(dx) > Math.abs(dy) + 4 ? 'x' : 'y';
      if (g.axis === 'x') {
        if (g.inArticle) g.kind = g.edge && dx > 0 ? 'back' : (g.hscroll ? null : 'step');                       // 规则 1
        else if (g.hscroll || g.lrChannels) g.kind = null;                                                         // 规则 2–4
        else if (g.card && g.card.closest('.pager-a, .more-list, #bloggerList, [data-favorites-list], #search-panel')) g.kind = 'card';  // 规则 5
      } else if (dy > 0 && g.scroller && g.scroller.scrollTop <= 0 && !g.inArticle) g.kind = 'pull';            // 规则 6
    }
    if (!g.kind || g.kind === 'menu') return;
    if (e.cancelable) e.preventDefault();
    if (g.kind === 'back') { $('#articleView').style.transform = `translateX(${Math.max(0, dx)}px)`; }
    else if (g.kind === 'step') { $('#articleBody').style.transform = `translateX(${dx * 0.35}px)`; }
    else if (g.kind === 'card') {
      const c = g.card; c.classList.add('swiping');
      const x = Math.max(-120, Math.min(120, dx)); c.style.transform = `translateX(${x}px)`;
      c.dataset.swipe = x < -CARD_ACT ? 'fav-go' : x < 0 ? 'fav' : x > CARD_ACT ? 'share-go' : 'share';
    } else if (g.kind === 'pull') {
      g.pull = Math.max(0, dy * 0.42); g.scroller.style.transform = `translateY(${Math.min(72, g.pull)}px)`;
      setPtr(true, g.pull > PULL_GO ? '松开刷新' : '下拉刷新', false);
    }
  }
  function onTouchEnd() {
    if (!g) return;
    clearTimeout(g.long);
    const s0 = g; g = null;
    const dx = s0.x - s0.x0;
    if (s0.kind === 'menu') { suppressClickUntil = performance.now() + 250; return; }   // 只吞掉松手时补发的那一下点击
    if (s0.kind === 'back') {
      const av = $('#articleView');
      if (dx > 80) { av.style.transition = 'transform .18s ease-out'; av.style.transform = 'translateX(100%)'; setTimeout(() => { av.style.transition = ''; closeArticle(); }, 180); }
      else { av.style.transition = 'transform .2s'; av.style.transform = ''; setTimeout(() => { av.style.transition = ''; }, 200); }
    } else if (s0.kind === 'step') {
      const body = $('#articleBody'); body.style.transform = '';
      if (Math.abs(dx) > 60) step(dx < 0 ? 1 : -1);
    } else if (s0.kind === 'card') {
      const c = s0.card, it = cardItem(c);
      suppressClickUntil = performance.now() + 400;
      if (dx <= -CARD_ACT && it) toggleFav(it);
      else if (dx >= CARD_ACT && it) shareItem(it);
      resetCard(c);
    } else if (s0.kind === 'pull') {
      const el = s0.scroller; const go = (s0.pull || 0) > PULL_GO;
      el.style.transition = 'transform .28s cubic-bezier(.2,.8,.2,1)'; el.style.transform = 'translateY(0)';
      setTimeout(() => { el.style.transition = ''; el.style.transform = ''; }, 300);
      if (go) { setPtr(true, '正在刷新', true); doRefresh(); } else setPtr(false);
    }
  }
  function bindTouch() {
    const app = $('.app');
    app.addEventListener('touchstart', onTouchStart, {passive: true});
    app.addEventListener('touchmove', onTouchMove, {passive: false});
    app.addEventListener('touchend', onTouchEnd, {passive: true});
    app.addEventListener('touchcancel', onTouchEnd, {passive: true});
    app.addEventListener('contextmenu', e => { if (e.target.closest(CARD_SEL)) e.preventDefault(); });
  }
  function scrollTopOf(view) {
    if (view === 'channels') { const r = $('#channelRoot'); return mode === 'lr' ? $$('.page-b')[currentChannelIndex()] : r; }
    if (view === 'favorites') return $('#view-favorites .sub');
    return $(`#view-${view} .sub`);
  }
  let lastTab = {view: null, t: 0};
  function onTab(view) {
    const now = performance.now();
    if (lastTab.view === view && now - lastTab.t < 350 && currentView() === view) {
      const el = scrollTopOf(view); if (el) el.scrollTo({top: 0, behavior: 'smooth'});
      lastTab = {view: null, t: 0}; return;
    }
    lastTab = {view, t: now};
    showView(view);
  }
  function updateBannerPager(rail) {
    const pager = rail.closest('.banner-wrap').querySelector('.banner-pager');
    const n = rail.querySelectorAll('.banner-slide').length; const i = Math.min(n, Math.max(1, Math.round(rail.scrollLeft / (rail.clientWidth || 1)) + 1));
    pager.textContent = i + ' / ' + n; pager.setAttribute('aria-label', `第 ${i} 屏，共 ${n} 条`);
  }
  function bindGestures() {
    $$('.banner-rail').forEach(rail => { bindHSwipe(rail); rail.addEventListener('scroll', () => updateBannerPager(rail), {passive: true}); updateBannerPager(rail); });
    const root = $('#channelRoot');
    if (mode === 'lr') bindHSwipe(root);
    else if (root._gAbort) { root._gAbort.abort(); root._gAbort = null; root.style.transform = ''; root.classList.remove('is-drag'); }   // 上下模式：频道横滑解绑，横滑留给卡片
  }

  /* ---------- 图片全屏查看（现有栈，不另加依赖）：点开、左右滑、双指缩放、点空白或下滑关闭 ---------- */
  const zoom = {urls: [], i: 0, open: false, scale: 1, tx: 0, ty: 0, start: null};
  function zoomUrlsFrom(img) {
    const grid = img.closest('[data-zoom-list]');
    if (grid && grid.dataset.zoomList) {
      const urls = grid.dataset.zoomList.split('|').filter(Boolean);
      const i = Math.max(0, urls.indexOf(img.dataset.zoom || img.src));
      return {urls, i: i < 0 ? 0 : i};
    }
    const scope = img.closest('.article-body, .tweet, .feed-row, .hero, .row-item, .more-body, .art-orig') || document;
    const urls = [];
    scope.querySelectorAll('img[data-zoom]').forEach(el => { const u = el.dataset.zoom || el.currentSrc || el.src; if (u && !urls.includes(u)) urls.push(u); });
    const cur = img.dataset.zoom || img.currentSrc || img.src;
    const i = Math.max(0, urls.indexOf(cur));
    return {urls: urls.length ? urls : [cur], i: i < 0 ? 0 : i};
  }
  function zoomPaint() {
    const stage = $('#zoomStage'), img = stage.querySelector('img');
    if (!img) return;
    img.style.transform = `translate(${zoom.tx}px, ${zoom.ty}px) scale(${zoom.scale})`;
    $('#zoomCount').textContent = `${zoom.i + 1} / ${zoom.urls.length}`;
    $('#zoomPrev').disabled = zoom.urls.length < 2;
    $('#zoomNext').disabled = zoom.urls.length < 2;
  }
  function zoomGo(i) {
    if (!zoom.urls.length) return;
    zoom.i = (i + zoom.urls.length) % zoom.urls.length;
    zoom.scale = 1; zoom.tx = 0; zoom.ty = 0;
    const stage = $('#zoomStage');
    stage.innerHTML = `<img src="${L.esc(zoom.urls[zoom.i])}" alt="">`;
    zoomPaint();
  }
  function openZoom(img) {
    const got = zoomUrlsFrom(img);
    zoom.urls = got.urls; zoom.i = got.i; zoom.open = true; zoom.scale = 1; zoom.tx = 0; zoom.ty = 0;
    const view = $('#zoomView'); view.hidden = false; view.classList.add('on');
    zoomGo(zoom.i);
  }
  function closeZoom() {
    zoom.open = false; zoom.start = null;
    const view = $('#zoomView'); view.classList.remove('on'); view.hidden = true;
    $('#zoomStage').innerHTML = '';
  }
  function bindZoom() {
    const view = $('#zoomView'), stage = $('#zoomStage');
    $('#zoomPrev').onclick = ev => { ev.stopPropagation(); zoomGo(zoom.i - 1); };
    $('#zoomNext').onclick = ev => { ev.stopPropagation(); zoomGo(zoom.i + 1); };
    view.addEventListener('click', ev => { if (ev.target === view || ev.target === stage || ev.target === stage.querySelector('img') && zoom.scale <= 1) { /* tap handled in touchend */ } });
    view.addEventListener('touchstart', ev => {
      ev.stopPropagation();
      const pts = ev.touches;
      if (pts.length === 2) {
        const dx = pts[1].clientX - pts[0].clientX, dy = pts[1].clientY - pts[0].clientY;
        zoom.start = {mode: 'pinch', dist: Math.hypot(dx, dy), scale: zoom.scale, x: (pts[0].clientX + pts[1].clientX) / 2, y: (pts[0].clientY + pts[1].clientY) / 2, tx: zoom.tx, ty: zoom.ty};
      } else if (pts.length === 1) {
        zoom.start = {mode: 'drag', x: pts[0].clientX, y: pts[0].clientY, tx: zoom.tx, ty: zoom.ty, t0: performance.now(), moved: false};
      }
    }, {passive: false});
    view.addEventListener('touchmove', ev => {
      ev.preventDefault(); ev.stopPropagation();
      if (!zoom.start) return;
      const pts = ev.touches;
      if (zoom.start.mode === 'pinch' && pts.length === 2) {
        const dist = Math.hypot(pts[1].clientX - pts[0].clientX, pts[1].clientY - pts[0].clientY);
        zoom.scale = Math.max(1, Math.min(5, zoom.start.scale * (dist / (zoom.start.dist || 1))));
        if (zoom.scale === 1) { zoom.tx = 0; zoom.ty = 0; }
        zoomPaint();
      } else if (zoom.start.mode === 'drag' && pts.length === 1) {
        const dx = pts[0].clientX - zoom.start.x, dy = pts[0].clientY - zoom.start.y;
        if (Math.abs(dx) > 6 || Math.abs(dy) > 6) zoom.start.moved = true;
        if (zoom.scale > 1) { zoom.tx = zoom.start.tx + dx; zoom.ty = zoom.start.ty + dy; }
        else { zoom.tx = dx * 0.9; zoom.ty = dy * 0.9; }
        zoomPaint();
      }
    }, {passive: false});
    view.addEventListener('touchend', ev => {
      ev.stopPropagation();
      const s = zoom.start; zoom.start = null;
      if (!s) return;
      if (s.mode === 'drag' && zoom.scale <= 1) {
        const dx = zoom.tx, dy = zoom.ty, dt = performance.now() - s.t0;
        zoom.tx = 0; zoom.ty = 0; zoomPaint();
        if (!s.moved || (Math.abs(dx) < 10 && Math.abs(dy) < 10 && dt < 350)) { closeZoom(); return; }
        if (dy > 80 && Math.abs(dy) > Math.abs(dx)) { closeZoom(); return; }
        if (Math.abs(dx) > 60 && zoom.urls.length > 1) zoomGo(zoom.i + (dx < 0 ? 1 : -1));
        else zoomPaint();
      }
    });
    view.addEventListener('touchcancel', () => { zoom.start = null; if (zoom.scale <= 1) { zoom.tx = 0; zoom.ty = 0; zoomPaint(); } });
    document.addEventListener('keydown', ev => {
      if (!zoom.open) return;
      if (ev.key === 'Escape') closeZoom();
      else if (ev.key === 'ArrowLeft') zoomGo(zoom.i - 1);
      else if (ev.key === 'ArrowRight') zoomGo(zoom.i + 1);
    });
  }

  /* ---------- 事件 ---------- */
  function onClick(e) {
    const t = e.target;
    if (performance.now() < suppressClickUntil) { e.preventDefault(); e.stopPropagation(); return; }
    const zhit = t.closest('img[data-zoom], .media-grid .cell, .post-cover, .feed-row .thumb, .b-img');
    if (zhit && !zoom.open) {
      const img = zhit.matches && zhit.matches('img') ? zhit : zhit.querySelector('img[data-zoom], img');
      if (img && (img.dataset.zoom || img.src)) { e.preventDefault(); e.stopPropagation(); openZoom(img); return; }
    }
    const nav = t.closest('[data-nav]'); if (nav) { step(Number(nav.dataset.nav)); return; }
    const orig = t.closest('[data-orig]');
    if (orig) { e.stopPropagation(); const box = $(`[data-orig-box="${CSS.escape(orig.dataset.orig)}"]`); if (box) { const on = box.classList.toggle('on'); orig.textContent = on ? '收起原文' : '看原文'; } return; }
    const artOrig = t.closest('[data-art-orig]');
    if (artOrig) { const box = $('[data-art-orig-box]'); const on = box.classList.toggle('on'); artOrig.textContent = on ? '收起原文' : '看原文'; return; }
    const tab = t.closest('[data-hot]');
    if (tab) { hotActive = tab.dataset.hot; renderHotBody(); return; }
    const day = t.closest('[data-hot-day]');
    if (day) { pickHotDay(day.dataset.hotDay); return; }
    const see = t.closest('[data-see]');
    if (see) { openMore(see.dataset.see); return; }
    if (t.closest('[data-more-retry]')) { if (more) { more.error = null; loadMorePage(); } return; }
    const m = t.closest('[data-more]'); if (m) { loadMore(m.dataset.more); return; }
    const r = t.closest('[data-retry]'); if (r) { ch[r.dataset.retry].error = null; loadMore(r.dataset.retry); return; }
    const pl = t.closest('[data-plat]'); if (pl) { plat = pl.dataset.plat; person = 'all'; renderBloggers(); return; }
    const pe = t.closest('[data-person]'); if (pe) { person = pe.dataset.person; renderBloggers(); return; }
    if (t.closest('a,button')) return;
    const card = t.closest('[data-id]');
    if (card && !card.closest('#articleBody')) openItem(card.dataset.id, {list: listContext(card)});
  }

  async function boot() {
    $('#when').textContent = L.fmtDay(new Date());
    $$('.tabbar button').forEach(b => b.addEventListener('click', () => onTab(b.dataset.view)));
    bindTouch();
    bindZoom();
    $('#cardMenu').addEventListener('click', onMenu);
    // 收藏 / 搜索模块自己的列表（data-item-id）点开时，也带上「上一条/下一条」的列表
    document.addEventListener('click', e => {
      const row = e.target.closest('[data-item-id]');
      if (row && performance.now() >= suppressClickUntil) pendingList = listContext(row);
      else if (row) { e.preventDefault(); e.stopImmediatePropagation(); }
    }, true);
    $('#modeLR').onclick = () => { if (mode !== 'lr') { mode = 'lr'; localStorage.setItem(MKEY, mode); renderChannels(); } };
    $('#modeUD').onclick = () => { if (mode !== 'ud') { mode = 'ud'; localStorage.setItem(MKEY, mode); channels().forEach(c => { ch[c.slug].shown = Math.max(UD_FIRST, Math.min(ch[c.slug].shown, ch[c.slug].list.length)); }); renderChannels(); } };
    $('#btnRefresh').onclick = doRefresh;
    $('#btnBack').onclick = () => closeArticle();
    $('#btnMoreBack').onclick = () => closeMore();
    document.querySelector('.app').addEventListener('click', onClick);
    const deep = L.parseItemHash(location.hash);
    const deepMore = (location.hash.match(/^#\/more\/(.+)$/) || [])[1];
    if (!history.state || !history.state.home) history.replaceState({home: true}, '', location.pathname + location.search);
    try { await loadAll(false); } catch (e) {
      $('#channelRoot').innerHTML = `<p class="muted" style="padding:16px">数据没加载出来（${L.esc(e.message)}）。稍后点右上角刷新再试。</p>`;
      $('#app').removeAttribute('aria-busy'); return;
    }
    stampRefresh(meta.built_at);
    const note = meta.note || (meta.fixture ? '这是用测试样例数据构建的页面，不是真实内容。' : '');
    if (note && sessionStorage.getItem(NOTE_KEY) !== note) {
      const box = $('#previewNote'); box.querySelector('span').textContent = note; box.hidden = false;
      box.querySelector('button').onclick = () => { box.hidden = true; sessionStorage.setItem(NOTE_KEY, note); };
    }
    renderChannels();
    booted = true;
    ctx.searchButton = $('#btnSearch');
    if (registry.search) mountFeature('search');
    else $('#btnSearch').onclick = () => toast('搜索功能还没接入。');
    $('#app').removeAttribute('aria-busy');
    if (deep) openItem(deep);
    else if (deepMore) { try { openMore(decodeURIComponent(deepMore)); } catch (e) { /* 坏链接就留在首页 */ } }
  }
  window.Rebang.openItem = (x) => openItem(x);
  window.Rebang.ctx = ctx;
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot); else boot();
})();
