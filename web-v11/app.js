/* 拾光热榜 v1 新版前端（纯静态、无框架、无第三方依赖）。
   交互以 v10 设计稿为准：两种翻法、频道顶部 banner、信息流、时事热搜块、整页正文 + 返回原位、无限加载、刷新/下拉刷新。
   收藏 / 搜索由 web-v11/features/*.js 通过 Rebang.register(name, mount) 挂到 #view-favorites / #search-panel。
   2026-11-15 21:26 阿欢改：底栏「历史」→「热搜」（当前热搜 + 按北京日期回看），时事频道不再嵌热搜；
   博主页加「Grok bot」渠道（今日重点/推特爆款/环球要闻/GitHub 热门）；每个频道、每个博主都有「查看更多」整页。 */
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

  const ctx = {
    dataBase: DATA,
    get now() { return new Date(); },
    openItem: (it) => openItem(it),
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
    return `<div class="ch-kicker"${mode === 'lr' ? ' style="padding:0"' : ''}><span class="idx">${i + 1} / ${channels().length}</span><span class="hint">${hint}</span></div>
      <div class="ch-row"><h2 class="ch">${L.esc(c.name)}</h2>${c.total ? `<button type="button" class="see-more" data-see="ch:${L.esc(c.slug)}">查看更多<span aria-hidden="true">›</span></button>` : ''}</div>
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
    $('#platName').textContent = p ? p.name : '';
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
  function articleHTML(it) {
    const d = L.display(it);
    const slot = '<div class="fav-slot" data-fav-slot></div>';
    const open = it.url ? `<a class="primary" href="${L.esc(it.url)}" target="_blank" rel="noopener">打开原文</a>` : '';
    if (it.kind === 'post' && !(it.blogger && it.blogger.platform === 'grok')) return `${L.tweetCardHTML(it, false)}<div class="actions">${slot}${open}</div>`;
    let text = (d.body || d.summary || '').trim();
    // TG 正文第一行常是「【标题】」，标题已单独显示，正文里不再重复
    const first = text.split('\n')[0].replace(/[【】\s]/g, '');
    if (first && first === d.title.replace(/[【】\s]/g, '')) text = text.slice(text.indexOf('\n') + 1 || text.length).trim();
    const orig = d.translated ? `<div class="art-tools"><button type="button" class="orig-btn" data-art-orig>看原文</button></div><div class="art-orig" data-art-orig-box><h4>${L.esc(d.orig.title)}</h4>${L.esc(d.orig.body || d.orig.summary)}</div>` : '';
    return `${it.image && it.image.url ? `<img class="cover" src="${L.esc(it.image.url)}" alt="${L.esc(it.image.alt || '')}">` : ''}
      <div class="src art-src"><span>${L.esc(it.source_name)} · ${L.esc(L.fmtTime(it.published_at))}</span>${it.highlight ? '<span class="t-badge">今日重点</span>' : ''}${d.translated ? `<span class="mt-badge">${L.esc(d.label)}</span>` : ''}</div>
      <h3 class="art-title">${L.esc(d.title)}</h3>
      <p class="art-text${text ? '' : ' none'}">${L.esc(text || L.NO_BODY)}</p>${orig}
      <div class="actions">${slot}${open}</div>`;
  }
  function attachFav(slot, it) {
    const handle = mounted.favorites || (registry.favorites && mountFeature('favorites'));
    if (handle && typeof handle.attachButton === 'function') return handle.attachButton(slot, it);
    if (window.RebangFavorites && window.RebangFavorites.attachButton) return window.RebangFavorites.attachButton(slot, it, {toast});
    slot.remove();
  }
  async function openItem(ref, opts = {}) {
    const id = typeof ref === 'string' ? ref : ref && ref.id;
    if (!id) return;
    let it = items.get(id) || (typeof ref === 'object' && ref.kind ? ref : null) || await findItem(id) || (typeof ref === 'object' ? ref : null);
    if (!it) { toast('这条已经不在最近一次发布的数据里了。'); return; }
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
    if (!opts.fromPop) history.pushState({article: id}, '', L.itemHash(id));
  }
  function closeArticle(opts = {}) {
    if (!articleOpen) return;
    articleOpen = false; articleId = null;
    $('#articleView').classList.remove('on');
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
  function stampRefresh(d) { $('#refreshed').textContent = `刷新于 ${L.fmtTime(d)}`; }
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
  function bindPullRefresh() {
    const targets = mode === 'lr' ? $$('.page-b') : [$('#channelRoot')];
    const ptr = $('#ptr');
    targets.forEach(el => {
      if (el._pAbort) el._pAbort.abort();
      const ac = new AbortController(); el._pAbort = ac;
      let sy, sx, axis, pull = 0;
      const setPtr = (show, txt, spin) => { ptr.style.top = $('.top').offsetHeight + 'px'; ptr.hidden = !show; ptr.classList.toggle('show', !!show); ptr.classList.toggle('spin', !!spin); if (txt) ptr.querySelector('.ptr-txt').textContent = txt; };
      el.addEventListener('touchstart', e => { const t = e.touches[0]; sy = t.clientY; sx = t.clientX; axis = null; pull = 0; }, {signal: ac.signal, passive: true});
      el.addEventListener('touchmove', e => {
        const t = e.touches[0]; const dy = t.clientY - sy, dx = t.clientX - sx;
        if (axis == null && (Math.abs(dy) > 8 || Math.abs(dx) > 8)) axis = (el.scrollTop <= 0 && dy > 0 && dy > Math.abs(dx) + 4) ? 'pull' : 'y';
        if (axis !== 'pull') return;
        if (e.cancelable) e.preventDefault();
        pull = Math.max(0, dy * 0.42); el.style.transform = 'translateY(' + Math.min(72, pull) + 'px)';
        setPtr(true, pull > 56 ? '松开刷新' : '下拉刷新', false);
      }, {signal: ac.signal, passive: false});
      const end = () => {
        if (axis == null && pull === 0) return;
        const go = axis === 'pull' && pull > 56; axis = null; pull = 0;
        el.style.transition = 'transform .28s cubic-bezier(.2,.8,.2,1)'; el.style.transform = 'translateY(0)';
        setTimeout(() => { el.style.transition = ''; el.style.transform = ''; }, 300);
        if (go) { setPtr(true, '正在刷新', true); doRefresh(); } else setPtr(false);
      };
      el.addEventListener('touchend', end, {signal: ac.signal, passive: true}); el.addEventListener('touchcancel', end, {signal: ac.signal, passive: true});
    });
  }
  function updateBannerPager(rail) {
    const pager = rail.closest('.banner-wrap').querySelector('.banner-pager');
    const n = rail.querySelectorAll('.banner-slide').length; const i = Math.min(n, Math.max(1, Math.round(rail.scrollLeft / (rail.clientWidth || 1)) + 1));
    pager.textContent = i + ' / ' + n; pager.setAttribute('aria-label', `第 ${i} 屏，共 ${n} 条`);
  }
  function bindGestures() {
    $$('.banner-rail').forEach(rail => { bindHSwipe(rail); rail.addEventListener('scroll', () => updateBannerPager(rail), {passive: true}); updateBannerPager(rail); });
    if (mode === 'lr') bindHSwipe($('#channelRoot'));
    bindPullRefresh();
  }

  /* ---------- 事件 ---------- */
  function onClick(e) {
    const t = e.target;
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
    if (card && !card.closest('#articleBody')) openItem(card.dataset.id);
  }

  async function boot() {
    $('#when').textContent = L.fmtDay(new Date());
    $$('.tabbar button').forEach(b => b.addEventListener('click', () => showView(b.dataset.view)));
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
