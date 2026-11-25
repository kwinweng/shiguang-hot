/* 拾光资讯 v1 新版前端（纯静态、无框架、无第三方依赖）。
   交互以 v10 设计稿为准：两种翻法、频道顶部 banner、信息流、时事热搜块、整页正文 + 返回原位、无限加载、刷新/下拉刷新。
   收藏 / 搜索由 web-v11/features/*.js 通过 Rebang.register(name, mount) 挂到 #view-favorites / #search-panel。
   2026-11-15 21:26 阿欢改：底栏「历史」→「热搜」（当前热搜 + 按北京日期回看），时事频道不再嵌热搜；
   2026-11-16 阿欢改：频道区、博主区各是一条一直往下刷的长流（见「一直往下刷」段），去掉「查看更多」整页；卡片去掉横滑收藏/分享，只留长按菜单。
   2026-11-15 22:08–22:11 阿欢改（v13）：各页标题吸顶；TG 引用/转发卡、表情回应/浏览/公开评论；详情上一条/下一条；
   卡片手势（左滑收藏、右滑分享、长按菜单）、详情左边缘右滑返回、所有列表下拉刷新、双击底栏回顶部；公众号正文按原文顺序；
   顶栏日期居左只写一次。手势优先级见下方「手势」段注释。 */
(function () {
  'use strict';
  const L = window.RebangLib;

  /* ---------- iOS 主屏幕 web app：外壳撑满整屏、底栏贴底（见 lib.js standaloneGeometry）---------- */
  function insetProbe() {
    const probe = document.createElement('div');
    probe.style.cssText = 'position:fixed;left:0;top:0;width:0;height:0;visibility:hidden;pointer-events:none;padding-top:env(safe-area-inset-top,0px);padding-bottom:env(safe-area-inset-bottom,0px)';
    document.body.appendChild(probe);
    const cs = getComputedStyle(probe), r = {top: parseFloat(cs.paddingTop) || 0, bottom: parseFloat(cs.paddingBottom) || 0};
    probe.remove();
    return r;
  }
  function fitStandalone() {
    const de = document.documentElement;
    const standalone = navigator.standalone === true || !!(window.matchMedia && matchMedia('(display-mode: standalone)').matches);
    de.classList.toggle('is-standalone', standalone);
    const env = insetProbe(), fake = window.__rebangTestInsets;   // 只给验收脚本模拟真机安全区用（模拟器里 env() 恒为 0）
    const m = {standalone, ios: typeof navigator.standalone === 'boolean', insetTop: fake ? fake.top : env.top,
      insetBottom: fake ? fake.bottom : env.bottom, screenW: screen.width, screenH: screen.height,
      innerW: window.innerWidth, innerH: window.innerHeight};
    const g = L.standaloneGeometry(m);
    if (g && g.appH) { de.style.setProperty('--app-h', g.appH + 'px'); de.classList.add('app-fullscreen'); }
    else { de.style.removeProperty('--app-h'); de.classList.remove('app-fullscreen'); }
    if (g && g.safeBot !== null) de.style.setProperty('--safe-bot', g.safeBot + 'px'); else de.style.removeProperty('--safe-bot');
    m.geom = g;
    window.__rebangViewport = m;
    return m;
  }
  fitStandalone();
  ['resize', 'orientationchange', 'pageshow'].forEach(ev => window.addEventListener(ev, () => setTimeout(fitStandalone, 60)));
  if (window.visualViewport) visualViewport.addEventListener('resize', () => setTimeout(fitStandalone, 60));

  /* ---------- 诊断浮层：长按左上角标题 1 秒开/关（记在本机），或网址带 ?diag=1。主屏幕 app 打开时网址参数会丢，所以要长按 ---------- */
  const DIAG_KEY = 'rebang-v11-diag';
  function diagData() {
    const m = fitStandalone(), env = insetProbe(), de = document.documentElement, vv = window.visualViewport;
    const rect = sel => { const el = document.querySelector(sel); if (!el) return null; const r = el.getBoundingClientRect(); return {top: Math.round(r.top), bottom: Math.round(r.bottom), h: Math.round(r.height)}; };
    const mq = q => !!(window.matchMedia && matchMedia(q).matches);
    const bar = document.querySelector('.tabbar');
    return {
      standalone: m.standalone, navStandalone: navigator.standalone,
      displayMode: ['standalone', 'fullscreen', 'minimal-ui', 'browser'].find(d => mq(`(display-mode: ${d})`)) || '?',
      innerH: innerHeight, innerW: innerWidth, outerH: outerHeight, screen: `${screen.width}x${screen.height}`,
      vvH: vv ? Math.round(vv.height) : null, vvTop: vv ? Math.round(vv.offsetTop) : null, docClientH: de.clientHeight,
      safeTop: env.top, safeBot: env.bottom, geom: m.geom, appH: de.style.getPropertyValue('--app-h') || null,
      tabbar: rect('.tabbar'), tabbarPadBot: bar ? getComputedStyle(bar).paddingBottom : null,
      body: rect('body'), app: rect('#app'), dpr: devicePixelRatio, ua: navigator.userAgent,
    };
  }
  let diagTimer = 0;
  function diagRender() {
    let box = document.getElementById('diagBox');
    if (!box) {
      box = document.createElement('div');
      box.id = 'diagBox';
      box.innerHTML = '<a href="#/health">来源健康</a><pre></pre>';
      box.querySelector('a').addEventListener('click', e => { e.preventDefault(); openHealth(); });
      document.body.appendChild(box);
    }
    box.querySelector('pre').textContent = JSON.stringify(diagData(), null, 1);
  }
  function diagSet(on) {
    try { on ? localStorage.setItem(DIAG_KEY, '1') : localStorage.removeItem(DIAG_KEY); } catch (e) { /* 隐私模式 */ }
    clearInterval(diagTimer);
    if (on) { diagRender(); diagTimer = setInterval(diagRender, 1000); }
    else { const box = document.getElementById('diagBox'); if (box) box.remove(); }
  }
  function diagOn() { try { return localStorage.getItem(DIAG_KEY) === '1'; } catch (e) { return false; } }
  if (/[?&]diag=1/.test(location.search) || diagOn()) window.addEventListener('load', () => setTimeout(() => diagSet(true), 300));
  window.__rebangDiag = {data: diagData, set: diagSet};
  function bindDiagLongPress(el, onToggle) {
    if (!el) return;
    let t = 0, x = 0, y = 0, longPressed = false;
    const cancel = () => { clearTimeout(t); t = 0; };
    el.addEventListener('pointerdown', e => {
      if (!e.isPrimary || e.button !== 0) return;
      longPressed = false;
      x = e.clientX; y = e.clientY;
      cancel();
      t = setTimeout(() => { t = 0; longPressed = true; onToggle(); }, 1000);
    });
    el.addEventListener('pointermove', e => { if (t && Math.hypot(e.clientX - x, e.clientY - y) > 10) cancel(); });
    ['pointerup', 'pointercancel', 'pointerleave'].forEach(ev => el.addEventListener(ev, cancel));
    el.addEventListener('contextmenu', e => e.preventDefault());
    // 松手后补发的 click 归这次手势，下一次按下或键盘激活照常处理。
    el.addEventListener('click', e => {
      if (!longPressed || e.detail === 0) return;
      e.preventDefault();
      e.stopImmediatePropagation();
    }, true);
  }
  const DATA = 'data';
  const MKEY = 'rebang-v11-mode';
  const NOTE_KEY = 'rebang-v11-note-closed';
  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => [...r.querySelectorAll(s)];
  /* 动效令牌：与 app.css 的 --duration-* / --ease-out 一致（docs/rebang-v1/DESIGN-SYSTEM.md）。系统开了「减少动态效果」就全部归零 */
  const REDUCE = window.matchMedia ? window.matchMedia('(prefers-reduced-motion: reduce)') : {matches: false};
  const MOTION = {
    get fast() { return REDUCE.matches ? 0 : 150; }, get base() { return REDUCE.matches ? 0 : 200; }, get slow() { return REDUCE.matches ? 0 : 300; },
    ease: 'cubic-bezier(.2,.8,.2,1)',
    tr(prop, ms) { return ms ? `${prop} ${ms}ms ${this.ease}` : 'none'; }
  };

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
  const ch = {};                  // slug → {list, page, pages, total, loading, error}
  let articleOpen = false, articleId = null, returnState = null;
  let idIndex = null;
  let dataEpoch = 0;
  const pendingFindCtls = new Set();
  function abortPendingFinds() {
    pendingFindCtls.forEach(c => { try { c.abort(); } catch (e) {} });
    pendingFindCtls.clear();
  }
  let pendingList = null;         // 收藏/搜索模块点开条目时的同列表顺序（给详情的上一条/下一条）

  const ctx = {
    dataBase: DATA,
    get now() { return new Date(); },
    openItem: (it) => { const list = pendingList; pendingList = null; return openItem(it, {list}); },
    cancelOpen: () => { openSeq++; navSeq++; },
    toast: (t) => toast(t),
    fetch: (u, o) => fetch(u, o),
    searchButton: null,
  };

  async function getJSON(path, fresh, timeoutMs, trackFind) {
    const opts = fresh ? {cache: 'no-store'} : {};
    // timeoutMs：限时读（详情按 id 查完整条目用），超时就中止请求并报错，调用方回退快照
    const ctl = (timeoutMs || trackFind) && typeof AbortController !== 'undefined' ? new AbortController() : null;
    const timer = ctl && timeoutMs ? setTimeout(() => ctl.abort(), timeoutMs) : null;
    if (ctl) {
      opts.signal = ctl.signal;
      if (trackFind) pendingFindCtls.add(ctl);
    }
    try {
      const res = await fetch(`${DATA}/${path}${fresh ? (path.includes('?') ? '&' : '?') + 't=' + Date.now() : ''}`, Object.keys(opts).length ? opts : undefined);
      if (!res.ok) throw new Error(`${path}: HTTP ${res.status}`);
      return await res.json();
    } finally {
      if (timer) clearTimeout(timer);
      if (ctl && trackFind) pendingFindCtls.delete(ctl);
    }
  }
  function remember(list) { (list || []).forEach(it => it && it.id && items.set(it.id, it)); return list || []; }
  function toast(t) { const el = $('#toast'); el.textContent = t; el.classList.add('on'); clearTimeout(toast._t); toast._t = setTimeout(() => el.classList.remove('on'), 3200); }
  bindDiagLongPress(document.querySelector('#chBtn'), () => { const on = !diagOn(); diagSet(on); toast(on ? '诊断已打开（再长按左上角标题关闭）' : '诊断已关闭'); });
  function channels() { return (meta && meta.channels) || []; }

  /* ---------- 已读（v16）：点开过的条目在所有列表里变灰，只记在这台设备 ---------- */
  const READ_KEY = 'rebang-v11-read';
  const readSet = (() => { try { return new Set(JSON.parse(localStorage.getItem(READ_KEY) || '[]')); } catch (e) { return new Set(); } })();
  function markRead(scope) {
    if (!readSet.size) return;
    $$('[data-id], [data-item-id], .hot-list li[data-hid]', scope || document).forEach(el => {
      const id = el.dataset.id || el.dataset.itemId || el.dataset.hid;
      if (id && readSet.has(id) && !el.classList.contains('read') && !el.closest('#articleBody')) el.classList.add('read');
    });
  }
  function setRead(id) {
    if (!id || readSet.has(id)) return;
    readSet.add(id);
    try { localStorage.setItem(READ_KEY, JSON.stringify([...readSet].slice(-2000))); } catch (e) { /* 隐私模式 */ }
    setTimeout(() => $$(`[data-id="${CSS.escape(id)}"], [data-item-id="${CSS.escape(id)}"], .hot-list li[data-hid="${CSS.escape(id)}"]`).forEach(el => { if (!el.closest('#articleBody')) el.classList.add('read'); }), MOTION.slow);
  }

  /* ---------- 顶栏（v16）：左上角是当前频道/平台名 + 下拉箭头，没有 logo ---------- */
  function setTopName(name) {
    const el = $('#chName'); if (!el || el.textContent === name) return;
    el.textContent = name;
    if (!REDUCE.matches && el.animate) el.animate([{opacity: 0.2}, {opacity: 1}], {duration: MOTION.base, easing: MOTION.ease});
  }
  function updateTopName() {
    const v = currentView();
    if (v === 'channels') setTopName(channels()[curCh]?.name || '频道');
    else if (v === 'blogger') { const s = blSegs[Number($('#bloggerList').dataset.cur || 0)]; const p = s && platOf(s.plat); setTopName(p ? p.name : '博主'); }
    else if (v === 'hot') setTopName('热搜');
    else setTopName('收藏');
  }
  function dropOpen() { return $('#drop').classList.contains('on'); }
  function closeDrop() {
    $('#drop').classList.remove('on'); $('#dropMask').classList.remove('on');
    $('#drop').setAttribute('aria-hidden', 'true'); $('#chBtn').classList.remove('open'); $('#chBtn').setAttribute('aria-expanded', 'false');
  }
  function dropRow(attr, on, name, desc, count, ico) {
    return `<button type="button" ${attr} class="${on ? 'on' : ''}" role="option" aria-selected="${on}">${ico || ''}<div class="dt"><div class="dn">${L.esc(name)}</div>${desc ? `<div class="dd">${L.esc(desc)}</div>` : ''}</div>${count ? `<span class="dc">${L.esc(count)}</span>` : ''}${on ? `<span class="ck">${L.ICO.check}</span>` : ''}</button>`;
  }
  async function openDrop() {
    const v = currentView();
    if (v === 'favorites') return;
    let rows = '', note = '';
    if (v === 'channels') {
      rows = channels().map((c, i) => dropRow(`data-drop-ch="${i}"`, i === curCh, c.name, c.desc, c.total ? `${c.total} 条` : '')).join('');
      note = mode === 'lr' ? '左右滑动也能换频道；一直往下刷会自动接到下一个频道。' : '一直往下刷会自动接到下一个频道。';
    } else if (v === 'blogger') {
      await ensureBloggers();
      const cur = blSegs[Number($('#bloggerList').dataset.cur || 0)];
      rows = ((bloggers && bloggers.platforms) || []).map(p => dropRow(`data-drop-plat="${L.esc(p.id)}"`, cur ? cur.plat === p.id : p.id === plat, p.name, '', p.count ? `${p.count} 条` : '', platIcon(p))).join('');
      note = '一直往下刷会自动接到下一个平台。';
    } else if (v === 'hot') {
      rows = hotDayChips().map(c => dropRow(`data-hot-day="${c.date || ''}"`, (c.date || null) === hotDay, c.label, c.date ? '那天最后一次抓到的榜单' : '现在的热搜', '')).join('');
    }
    $('#dropList').innerHTML = rows;
    $('#dropNote').textContent = note; $('#dropNote').hidden = !note;
    $('#drop').classList.add('on'); $('#dropMask').classList.add('on'); $('#drop').setAttribute('aria-hidden', 'false');
    $('#chBtn').classList.add('open'); $('#chBtn').setAttribute('aria-expanded', 'true');
  }

  /* ---------- 数据 ---------- */
  async function loadPage(slug) {
    const st = ch[slug];
    if (st.loading || (st.page >= st.pages && st.page > 0)) return false;
    const epoch = dataEpoch;
    st.loading = true; st.error = null;
    try {
      const page = await getJSON(`channel/${slug}/page-${st.page + 1}.json`, epoch > 0);
      if (epoch !== dataEpoch) return false;
      st.list.push(...remember(page.items));
      st.page = page.page; st.pages = page.pages; st.total = page.total;
      return true;
    } catch (e) {
      if (epoch === dataEpoch) st.error = String(e.message || e);
      return false;
    } finally { if (epoch === dataEpoch) st.loading = false; }
  }
  async function loadAll(fresh) {
    meta = await getJSON('meta.json', fresh);
    updateHealthFreshness();
    channels().forEach(c => {
      remember(c.banner);
      ch[c.slug] = {list: [], page: 0, pages: c.pages || 1, total: c.feed_total || 0, loading: false, error: null};
    });
    await Promise.all([
      ...channels().map(c => loadPage(c.slug)),
      getJSON('hotsearch.json', fresh).then(h => { hot = h; }).catch(() => { hot = null; }),
    ]);
  }
  const FIND_TIMEOUT = 5000;   // 详情按 id 读 id-index / merged.json 的限时；超时回退收藏/搜索快照
  async function findItem(id) {
    const epoch = dataEpoch;
    if (items.has(id)) return items.get(id);
    try {
      let idx = idIndex;
      if (!idx) {
        const fetched = await getJSON('id-index.json', epoch > 0, FIND_TIMEOUT, true);
        if (epoch !== dataEpoch) return null;
        idIndex = idx = fetched;
      }
      const file = idx[id];
      if (!file) return null;
      const data = await getJSON(file, epoch > 0, FIND_TIMEOUT, true);
      if (epoch !== dataEpoch) return null;
      remember(data.items); remember((data.channels || []).flatMap(c => c.banner || []));
      return items.get(id) || null;
    } catch (e) { return null; }
  }

  /* ---------- 一直往下刷（2026-11-16 22:3x 阿欢）----------
     频道区、博主区各是一条不断的长流：每一段（一个频道 / 一个平台 / 一个博主）滑到底自动加载下一批；
     这一段全部加载完，出一条「下一个：<名字>」细分隔，紧接着就是下一段，顺序同顶部从左到右；最后一段刷完写「内容已结束」。
     频道区和博主区不串。段落顺序靠「闸门」保证：第 i 段只有在第 i-1 段可见且已加载完（或被左右滑 / 点图标直接跳到）时才显示，
     所以下一段永远接在上一段真正的末尾，不会出现在还没加载完的上一段中间。
     平滑：每批 30 条包成一个 .chunk，插进去先正常排版一帧，再加 content-visibility:auto（浏览器记住真实高度，离屏的批不再参与绘制），
     往回滚不会因为估算高度不准而跳。加载只在「哨兵从下方进入视口 1200px 内」时触发，视口上方的段落不会偷偷加载把内容往下推。 */
  const ENDED = '内容已结束';
  function chunkHTML(rows) { return rows.length ? `<div class="chunk">${rows.join('')}</div>` : ''; }
  function settleChunks(scope) {
    const fresh = $$('.chunk:not(.cv)', scope).filter(el => !el.closest('[hidden]'));   // 还没显示的段落先不加，等它显示、排过版再加
    if (!fresh.length) return;
    requestAnimationFrame(() => requestAnimationFrame(() => fresh.forEach(el => el.classList.add('cv'))));
  }
  function chainFoot(nextName) {
    return nextName ? `<div class="next-div" data-next-div><span>下一个：<b>${L.esc(nextName)}</b></span></div>` : `<div class="end-hint end-all" data-end="all"><span>${ENDED}</span></div>`;
  }
  /** 段落闸门：返回每段是否显示。exhausted(i)：第 i 段已经全部加载完；revealed(i)：被直接跳到过 */
  function gateList(n, exhausted, revealed) {
    const vis = [];
    for (let i = 0; i < n; i++) vis.push(i === 0 || revealed(i) || (vis[i - 1] && exhausted(i - 1)));
    return vis;
  }
  /** 哨兵进到视口下方 1200px 以内才加载；在视口上方、或被吸顶头盖着（已经滑过去的段落）不加载。stickyH：吸顶头高度 */
  function makeLoader(root, onHit, stickyH = () => 0) {
    return new IntersectionObserver(es => es.forEach(e => {
      if (!e.isIntersecting) return;
      const top = (e.rootBounds ? e.rootBounds.top : 0) + stickyH();
      if (e.boundingClientRect.bottom > top) onHit(e.target);
    }), {root, rootMargin: '0px 0px 1200px 0px', threshold: 0});
  }
  /** 往一段末尾插内容时保住读者正在看的位置：哨兵在视口上半（读者是从下面一段往回滚上来的）时，
   *  插完把滚动位置补上新增的高度，下面那段不会被顶下去。正常往下刷（哨兵在视口下方）不补。
   *  滚动容器都关了浏览器自带的 overflow-anchor，各家浏览器表现一致（Safari 本来就没有） */
  function keepPlace(scroller, sec, stickyH, mutate) {
    const sent = sec && sec.querySelector('.sentinel');
    let nxt = sec && sec.nextElementSibling; while (nxt && nxt.hidden) nxt = nxt.nextElementSibling;
    const r = scroller.getBoundingClientRect(), top = r.top + stickyH;
    // 这一段的开头已经滑过视口顶部、哨兵又在视口上半：读者在下面一段往回看。刚跳到的空段（开头就在顶部）不算
    const above = !!(sent && nxt && sec.getBoundingClientRect().top < top - 4 && sent.getBoundingClientRect().top < top + (r.bottom - top) / 2);
    const before = above ? nxt.getBoundingClientRect().top : 0;
    mutate();
    if (above) scroller.scrollTop += nxt.getBoundingClientRect().top - before;
  }
  /** 把 el 滚到 scroller 顶上（扣掉吸顶头的高度） */
  function scrollToEl(scroller, el, stickyH = 0) {
    scroller.scrollTop = Math.max(0, scroller.scrollTop + el.getBoundingClientRect().top - scroller.getBoundingClientRect().top - stickyH);
  }
  /* 跳段（左右滑换频道、点平台图标/人物）后先「钉住」目标段开头 1.5 秒：这期间上面那段如果还在补内容，补完再对齐一次，
     目标不会被顶下去。手指再碰屏幕就松开，不跟用户抢。 */
  let pin = null;
  function pinTo(scroller, el, stickyH) {
    pin = {scroller, el, stickyH, until: performance.now() + 1500};
    if (!scroller._pinBound) { scroller._pinBound = true; ['touchstart', 'wheel', 'mousedown'].forEach(ev => scroller.addEventListener(ev, () => { pin = null; }, {passive: true})); }
    scrollToEl(scroller, el, stickyH);
  }
  function repin() {
    if (!pin) return;
    if (performance.now() > pin.until || !pin.el.isConnected) { pin = null; return; }
    scrollToEl(pin.scroller, pin.el, pin.stickyH);
  }
  function slideIn(el, dir) {
    if (!dir || REDUCE.matches || !el.animate) return;
    el.animate([{transform: `translateX(${dir * 48}px)`, opacity: 0.35}, {transform: 'none', opacity: 1}], {duration: MOTION.base, easing: MOTION.ease});
  }

  /* ---------- 频道渲染 ---------- */
  function unavailableNote(c) {
    const bad = c.unavailable || [];
    if (!bad.length) return '';
    return `<div class="note">暂时取不到：${bad.map(s => L.esc(s.name || s.id)).join('、')}。抓到之前先空着。</div>`;
  }
  function chExhausted(slug) { const st = ch[slug]; return !st.error && !st.loading && st.page >= st.pages; }
  function feedFooter(slug) {
    const st = ch[slug];
    if (st.error) return `<div class="load-err">没加载出来。<button type="button" data-retry="${slug}">再试一次</button></div>`;
    if (st.page < st.pages) return `<div class="sentinel" data-ch="${slug}"></div><div class="load-hint" data-load="${slug}">正在加载…</div>`;
    const cs = channels(), i = cs.findIndex(c => c.slug === slug);
    return chainFoot(cs[i + 1] && cs[i + 1].name);
  }
  function channelInner(c) {
    const st = ch[c.slug];
    const empty = !c.banner.length && !st.total ? '<p class="muted">这一频道暂时还没有内容。</p>' : '';
    const description = [c.desc, `${c.total ?? st.total} 条`].filter(Boolean).join(' · ');
    return `<p class="desc">${L.esc(description)}</p>
      ${unavailableNote(c)}
      ${L.bannerHTML(c.slug, c.banner)}
      <div class="feed" data-ch="${c.slug}">${empty}<div class="feed-list">${chunkHTML(st.list.map(L.feedRowHTML))}</div><div class="feed-foot">${feedFooter(c.slug)}</div></div>`;
  }
  const chRevealed = new Set();
  function chSections() { return $$('#channelRoot > .ch-sec'); }
  function gateChannels() {
    const cs = channels();
    const vis = gateList(cs.length, i => chExhausted(cs[i].slug), i => chRevealed.has(cs[i].slug));
    chSections().forEach((sec, i) => { if (sec.hidden === vis[i]) { sec.hidden = !vis[i]; if (vis[i]) settleChunks(sec); } });
  }
  function applyMode() {
    $('#modeLR').classList.toggle('on', mode === 'lr');
    $('#modeUD').classList.toggle('on', mode === 'ud');
    $('#modeLR').setAttribute('aria-pressed', String(mode === 'lr'));
    $('#modeUD').setAttribute('aria-pressed', String(mode === 'ud'));
    const root = $('#channelRoot');
    root.classList.toggle('lr', mode === 'lr'); root.classList.toggle('ud', mode === 'ud');
  }
  function renderChannels() {
    const root = $('#channelRoot');
    root.className = 'feed-root';
    root.innerHTML = channels().map((c, i) => `<section class="ch-sec" data-ch="${c.slug}" data-i="${i}">${channelInner(c)}</section>`).join('');
    applyMode(); gateChannels();
    bindLoaders(); bindGestures(); fixBrokenThumbs(root); settleChunks(root); markRead(root);
    if (!root._spy) { root._spy = true; root.addEventListener('scroll', spyChannels, {passive: true}); }
    spyChannels();
  }
  function hostOf(slug) { return $(`#channelRoot > .ch-sec[data-ch="${slug}"]`); }
  function renderFeed(slug, from) {
    const host = hostOf(slug); if (!host) return;
    const list = host.querySelector('.feed-list');
    keepPlace($('#channelRoot'), host, 0, () => {
      list.insertAdjacentHTML('beforeend', chunkHTML(ch[slug].list.slice(from).map(L.feedRowHTML)));
      host.querySelector('.feed-foot').innerHTML = feedFooter(slug);
      gateChannels();
    });
    fixBrokenThumbs(list); settleChunks(list); markRead(list);
    repin(); observeSentinels();
  }
  function fixBrokenThumbs(scope) {
    $$('.feed-row .thumb img, .brow .thumb img', scope).forEach(img => {
      if (img._bound) return; img._bound = true;
      img.addEventListener('error', () => { const row = img.closest('.feed-row, .brow'), th = img.closest('.thumb'); if (th) th.remove(); if (row) row.classList.add('noimg'); }, {once: true});
    });
  }
  async function loadMore(slug) {
    const st = ch[slug];
    const before = st.list.length;
    if (!(await loadPage(slug)) && !st.error) return;
    renderFeed(slug, before);
  }
  let chObs = null;
  function bindLoaders() {
    if (chObs) chObs.disconnect();
    chObs = makeLoader($('#channelRoot'), el => { if (el.dataset.ch) loadMore(el.dataset.ch); });
    observeSentinels();
  }
  function observeSentinels() { if (chObs) $$('#channelRoot .sentinel').forEach(el => { if (!el._obs) { el._obs = true; chObs.observe(el); } }); }
  /* 顶栏标题跟随当前段；收缩只改字号，滚动容器的位置保持稳定。 */
  let curCh = 0, spyRaf = 0;
  function spyChannels() {
    if (spyRaf) return;
    spyRaf = requestAnimationFrame(() => {
      spyRaf = 0;
      const root = $('#channelRoot');
      if (currentView() !== 'channels') return;
      const top = root.getBoundingClientRect().top;
      const sections = chSections();
      if (!(pin && pin.scroller === root && performance.now() < pin.until)) {
        let at = 0;
        const atBottom = root.scrollTop > 0 && root.scrollTop + root.clientHeight >= root.scrollHeight - 4;
        sections.forEach((sec, i) => {
          if (!sec.hidden && (atBottom || sec.getBoundingClientRect().top <= top + 8)) at = i;
        });
        if (at !== curCh || root.dataset.cur === undefined) {
          curCh = at;
          root.dataset.cur = channels()[at]?.slug || '';
          updateTopName();
        }
      }
      const section = sections[curCh];
      $('#top').classList.toggle('channel-compact', !!section && top - section.getBoundingClientRect().top >= 24);
    });
  }
  function jumpChannel(i, dir) {
    const cs = channels(), root = $('#channelRoot');
    if (i < 0 || i >= cs.length) { toast(i < 0 ? '已经是第一个频道。' : '已经是最后一个频道。'); return false; }
    chRevealed.add(cs[i].slug); gateChannels();
    const sec = hostOf(cs[i].slug);
    pinTo(root, sec, 0);
    curCh = i; root.dataset.cur = cs[i].slug;
    updateTopName(); spyChannels();
    slideIn(root, dir);
    return true;
  }

  /* ---------- 博主（一条长流：平台按顶部图标从左到右；点某个人 = 这个平台按人分段，从这个人开始） ---------- */
  function platIcon(p) { return `<img class="plat-ico" src="${L.esc(p.icon || `icons/${p.id}.svg`)}" alt="" width="22" height="22">`; }
  function posts() { return (bloggers && bloggers.items) || []; }
  function platOf(id) { return ((bloggers && bloggers.platforms) || []).find(p => p.id === id); }
  function recentCount(id) {
    const built = builtAtMs();
    if (!Number.isFinite(built)) return 0;
    const since = built - 24 * 3600e3;
    return posts().filter(p => p.blogger.platform === id && window.RebangHealth.timeMs(p.published_at) >= since).length;
  }
  let blSegs = [];            // [{plat, pkey, handle, name, total, list, page, pages, loading, error, revealed}]
  function emptyText(p, acc) {
    const last = (x) => x && x.last_ok_at ? `上次成功抓取：${L.fmtTime(x.last_ok_at)}。` : '还没有成功抓取过。';
    let t;
    if (p && !p.accounts.length) t = `${p.name}：${p.reason || '本期名单为空'}。`;
    else if (p && !p.connected && p.status && p.status !== 'ok') t = `${p.name}暂时没有内容：${p.reason || p.status}。${last(p)}`;
    else if (p && !p.connected) t = `${p.name}的内容还没接上。${last(p)}`;
    else if (acc && acc.status && !['ok', 'empty'].includes(acc.status)) t = `${acc.name}暂时没有内容（${acc.reason || (acc.status === 'not_configured' ? '需要登录，还没接' : '这次没抓到')}）。${last(acc)}`;
    else if (acc) t = `${acc.name}最近没有新帖。${last(acc)}`;
    else t = '这一栏暂时还没有帖子。';
    return t.replace(/。。/g, '。');
  }
  const segCache = new Map();  // 「平台:人」→ 段（已加载的条目、页码）；点人物/全部重建长流时沿用，不重新加载
  function buildBlSegs() {
    blSegs = [];
    ((bloggers && bloggers.platforms) || []).forEach(p => {
      const seg = (acc) => { const k = `${p.id}:${acc ? acc.key : 'all'}`; if (!segCache.has(k)) segCache.set(k, mkSeg(acc)); const s = segCache.get(k); s.revealed = false; return s; };
      const mkSeg = (acc) => ({plat: p.id, pkey: acc ? acc.key : 'all', handle: acc ? acc.handle : 'all', name: acc ? acc.name : p.name,
        total: acc ? (acc.total || 0) : (p.count || 0), list: [], page: 0, pages: 1, loading: false, error: null, revealed: false});
      if (p.id === plat && person !== 'all' && p.accounts.length) p.accounts.forEach(a => blSegs.push(seg(a)));
      else blSegs.push(seg(null));
    });
    blSegs.forEach(s => { if (!s.total) s.pages = 0; if (s.error) s.error = null; });   // 没帖子的段不发请求，直接显示空态再接下一段
  }
  function segExhausted(s) { return !s.error && !s.loading && s.page >= s.pages; }
  function segDisplayName(s) { const p = platOf(s.plat); return s.pkey === 'all' ? (p ? p.name : s.plat) : `${s.name}（${p ? p.name : s.plat}）`; }
  function peopleRowHTML(p, sel) {
    if (!p || !p.accounts.length) return '';
    const mine = posts().filter(x => x.blogger.platform === p.id);
    const avatarOf = h => (mine.find(x => x.blogger.handle === h && x.blogger.avatar) || {blogger: {}}).blogger.avatar;
    return `<div class="people" data-people="${L.esc(p.id)}"><button type="button" class="ppl${sel === 'all' ? ' on' : ''}" data-plat-of="${L.esc(p.id)}" data-person="all"><span class="ph-av letter">全</span><span>全部</span></button>` +
      p.accounts.map(a => { const av = avatarOf(a.handle); return `<button type="button" class="ppl${sel === a.handle ? ' on' : ''}" data-plat-of="${L.esc(p.id)}" data-person="${L.esc(a.handle)}">${av ? `<img src="${L.esc(av)}" alt="">` : `<span class="ph-av letter">${L.esc((a.name || a.handle)[0])}</span>`}<span>${L.esc(a.name)}</span></button>`; }).join('') + '</div>';
  }
  function segFoot(i) {
    const s = blSegs[i];
    if (s.error) return `<div class="load-err">没加载出来。<button type="button" data-seg-retry="${i}">再试一次</button></div>`;
    if (s.page < s.pages) return `<div class="sentinel" data-seg="${i}"></div><div class="load-hint">正在加载…</div>`;
    const empty = !s.list.length ? (() => { const p = platOf(s.plat); const acc = p && s.pkey !== 'all' ? p.accounts.find(a => a.key === s.pkey) : null; return `<div class="empty-plat">${L.esc(emptyText(p, acc))}</div>`; })() : '';
    return empty + chainFoot(blSegs[i + 1] && segDisplayName(blSegs[i + 1]));
  }
  /** 一个平台一组：组头（平台名 + 人物行）+ 这个平台的段（「全部」一段，或点了某人后按人分段） */
  function groupsHTML() {
    let html = '';
    blSegs.forEach((s, i) => {
      if (i === 0 || blSegs[i - 1].plat !== s.plat) {
        const p = platOf(s.plat) || {name: s.plat, accounts: []};
        if (i) html += '</div>';
        const who = (p.accounts || []).length ? `${p.accounts.length} 位博主 · ` : '';
        html += `<div class="bl-group" data-group="${L.esc(s.plat)}"><div class="bl-plat-hd">${platIcon(p)}<h3>${L.esc(p.name)}</h3>${p.count || who ? `<span class="meta">${L.esc(who)}${p.count ? `共 ${L.esc(p.count)} 条` : ''}</span>` : ''}</div>${peopleRowHTML(p, s.pkey === 'all' ? 'all' : person)}`;
      }
      html += segHTML(s, i);
    });
    return html + (blSegs.length ? '</div>' : '');
  }
  function blSecs() { return $$('#bloggerList .bl-seg'); }
  function segHTML(s, i) {
    const accHd = s.pkey !== 'all' ? `<div class="bl-acc-hd">${L.esc(s.name)}${s.total ? ` <span class="meta">共 ${L.esc(s.total)} 条</span>` : ''}</div>` : '';
    return `<section class="bl-seg" data-seg="${i}" data-plat="${L.esc(s.plat)}" data-pkey="${L.esc(s.pkey)}" data-handle="${L.esc(s.handle)}">${accHd}<div class="bl-list list">${chunkHTML(segRows(s, 0))}</div><div class="bl-foot">${segFoot(i)}</div></section>`;
  }
  /** 一段里从第 from 条起的行；北京日期一变就插一条「11.16 今天　更新 N 篇」（N = 这一段那天的全部帖子数，来自 bloggers.json 全量清单） */
  function segRows(s, from) {
    const rows = [];
    let last = from > 0 && s.list[from - 1] ? L.beijingDate(s.list[from - 1].published_at) : null;
    const today = (meta && meta.today) || L.beijingDate(new Date());
    s.list.slice(from).forEach(x => {
      const d = L.beijingDate(x.published_at);
      if (d && d !== last) {
        last = d;
        if (!s.dayN) { s.dayN = {}; posts().forEach(p => { if (p.blogger.platform === s.plat && (s.pkey === 'all' || p.blogger.handle === s.handle)) { const k = L.beijingDate(p.published_at); s.dayN[k] = (s.dayN[k] || 0) + 1; } }); }
        const n = s.dayN[d] || 0;
        rows.push(`<div class="dayh" data-day="${d}"><b>${L.esc(L.dayLabel(d, today))}</b>${n ? `<span class="dpill">更新 ${n} 篇</span>` : ''}</div>`);
      }
      rows.push(L.postRowHTML(x));
    });
    return rows;
  }
  function gateBloggers() {
    const vis = gateList(blSegs.length, i => segExhausted(blSegs[i]), i => blSegs[i].revealed);
    blSecs().forEach((sec, i) => { if (sec.hidden === vis[i]) { sec.hidden = !vis[i]; if (vis[i]) settleChunks(sec); } });
    $$('#bloggerList > .bl-group').forEach(gr => { const h = !gr.querySelector('.bl-seg:not([hidden])'); if (gr.hidden !== h) gr.hidden = h; });
  }
  let blObs = null;
  function observeBlSentinels() { if (blObs) $$('#bloggerList .sentinel').forEach(el => { if (!el._obs) { el._obs = true; blObs.observe(el); } }); }
  function renderBloggers() {
    if (!bloggers) { $('#bloggerList').innerHTML = '<p class="muted">正在加载…</p>'; return; }
    $('#platChips').innerHTML = bloggers.platforms.map(p => {
      const n = recentCount(p.id);
      return `<button type="button" class="avb${p.id === plat ? ' on' : ''}" data-plat="${p.id}" aria-label="${L.esc(p.name)}" title="${L.esc(p.name)}"><span class="avc">${platIcon(p)}${n ? `<span class="unread" aria-label="${n} 条 24 小时内的新帖">${n}</span>` : ''}</span><b>${L.esc(p.name)}</b></button>`;
    }).join('');
    const nAcc = bloggers.platforms.reduce((a, p) => a + (p.accounts || []).length, 0);
    $('#blStat').textContent = `${nAcc} 位博主 · ${bloggers.platforms.length} 个平台的最新动态`;
    buildBlSegs();
    const list = $('#bloggerList');
    list.innerHTML = groupsHTML();
    delete list.dataset.cur;
    fixBrokenThumbs(list); markRead(list);
    if (blObs) blObs.disconnect();
    blObs = makeLoader($('#view-blogger .sub'), el => loadSeg(Number(el.dataset.seg)), blStickyH);
    gateBloggers(); observeBlSentinels();
    const sub = $('#view-blogger .sub');
    if (!sub._spy) { sub._spy = true; sub.addEventListener('scroll', spyBloggers, {passive: true}); }
    syncBlTop();
  }
  /* 博主页顶上是一块色带（暗色青灰 / 亮色暖灰）：色带在的时候顶栏藏起来，滑过色带顶栏才出来，写当前平台名 */
  function syncBlTop() {
    const band = $('#blBand');
    const show = currentView() === 'blogger' && !!band && band.getBoundingClientRect().bottom < $('#top').offsetHeight;
    $('#app').classList.toggle('top-show', show);
  }
  async function loadSeg(i) {
    const s = blSegs[i];
    if (!s || s.loading || s.page >= s.pages) return;
    const epoch = dataEpoch;
    s.loading = true; s.error = null;
    let fresh = [];
    try {
      const page = await getJSON(`blogger/${s.plat}/${s.pkey}/page-${s.page + 1}.json`, epoch > 0);
      if (epoch !== dataEpoch) return;
      const seen = new Set(s.list.map(x => x.id));
      fresh = remember(page.items).filter(x => !seen.has(x.id));
      s.list.push(...fresh); s.page = page.page; s.pages = page.pages;
    } catch (e) {
      if (epoch !== dataEpoch) return;
      s.error = String(e.message || e);
    } finally {
      if (epoch === dataEpoch) s.loading = false;
    }
    if (epoch !== dataEpoch) return;
    const at = blSegs.indexOf(s); if (at < 0) return;   // 期间长流重建过：数据已进缓存，下次显示时带上
    i = at;
    const sec = $(`#bloggerList .bl-seg[data-seg="${i}"]`); if (!sec) return;
    const box = sec.querySelector('.bl-list');
    keepPlace($('#view-blogger .sub'), sec, blStickyH(), () => {
      box.insertAdjacentHTML('beforeend', chunkHTML(segRows(s, s.list.length - fresh.length)));
      sec.querySelector('.bl-foot').innerHTML = segFoot(i);
      gateBloggers();
    });
    fixBrokenThumbs(box); settleChunks(box); markRead(box); repin(); observeBlSentinels();
  }
  function blStickyH() { return $('#top').offsetHeight; }   // 博主页的顶栏浮在列表上面（滑过色带后出现），跳段时目标停在它下面
  let blSpyRaf = 0;
  function spyBloggers() {
    if (blSpyRaf) return;
    blSpyRaf = requestAnimationFrame(() => {
      blSpyRaf = 0;
      syncBlTop();
      const sub = $('#view-blogger .sub'); if (!sub || !blSegs.length) return;
      if (pin && pin.scroller === sub && performance.now() < pin.until) return;
      const top = sub.getBoundingClientRect().top + blStickyH() + 8;
      let at = 0;
      blSecs().forEach((sec, i) => { if (!sec.hidden && sec.getBoundingClientRect().top <= top) at = i; });
      if (sub.scrollTop + sub.clientHeight >= sub.scrollHeight - 4) blSecs().forEach((sec, i) => { if (!sec.hidden) at = i; });   // 到底了：最后一段算当前
      markBlCurrent(at);
    });
  }
  function markBlCurrent(at) {
    const s = blSegs[at]; if (!s) return;
    const list = $('#bloggerList');
    if (list.dataset.cur === String(at)) return;
    list.dataset.cur = String(at);
    blSecs().forEach((sec, i) => sec.classList.toggle('cur', i === at));
    if (s.plat !== plat) { plat = s.plat; if (person !== 'all' && !blSegs.some(x => x.plat === plat && x.pkey !== 'all')) person = 'all'; }
    $$('#platChips [data-plat]').forEach(b => b.classList.toggle('on', b.dataset.plat === s.plat));
    const chip = $(`#platChips [data-plat="${CSS.escape(s.plat)}"]`);
    if (chip) { const r = chip.parentElement, cr = chip.getBoundingClientRect(), rr = r.getBoundingClientRect(); if (cr.left < rr.left || cr.right > rr.right) r.scrollLeft += cr.left - rr.left - 16; }   // 当前平台图标露出来
    if (s.pkey !== 'all') $$(`#bloggerList .people[data-people="${CSS.escape(s.plat)}"] .ppl`).forEach(b => b.classList.toggle('on', b.dataset.person === s.handle));
    if (currentView() === 'blogger') updateTopName();
  }
  function nextPlat() {
    const cur = blSegs[Number($('#bloggerList').dataset.cur || 0)];
    const i = cur ? blSegs.findIndex(s => s.plat !== cur.plat && blSegs.indexOf(cur) < blSegs.indexOf(s)) : 1;
    if (i < 0) { toast('已经是最后一个平台。'); return; }
    jumpSeg(i, 1);
  }
  /** 「全部」：所有平台和博主一览，点平台跳过去，点人 = 从这个人开始按人分段 */
  async function openAllBloggers() {
    await ensureBloggers();
    const ps = (bloggers && bloggers.platforms) || [];
    openSheet(`<div class="sh-title">全部博主<small>${ps.length} 个平台</small></div><div class="allb">${ps.map(p => `<div class="allp"><button type="button" class="allp-h" data-all-plat="${L.esc(p.id)}">${platIcon(p)}<b>${L.esc(p.name)}</b><span>${p.count ? `${L.esc(p.count)} 条` : ''}${L.icon('chevron-right')}</span></button>${(p.accounts || []).length ? `<div class="accs">${p.accounts.map(a => `<button type="button" class="${a.total ? '' : 'zero'}" data-plat-of="${L.esc(p.id)}" data-person="${L.esc(a.handle)}">${L.esc(a.name)}${a.total ? ` <i>${L.esc(a.total)}</i>` : ''}</button>`).join('')}</div>` : ''}</div>`).join('')}</div>`, {cls: 'tall'});
  }
  function jumpSeg(i, dir) {
    const s = blSegs[i]; if (!s) return;
    s.revealed = true; gateBloggers();
    const sec = $(`#bloggerList .bl-seg[data-seg="${i}"]`); if (!sec) return;
    const sub = $('#view-blogger .sub');
    // 这一组里前面没有显示的段：从组头（平台名 + 人物行）开始；否则从这一段开头开始
    const gr = sec.closest('.bl-group'), firstVis = gr && gr.querySelector('.bl-seg:not([hidden])');
    pinTo(sub, firstVis === sec ? gr : sec, blStickyH());
    if (!s.page && s.pages) loadSeg(i);
    markBlCurrent(i);
    slideIn($('#bloggerList'), dir);
  }
  function pickPlat(id) {
    if (person !== 'all') { person = 'all'; plat = id; renderBloggers(); }
    const i = blSegs.findIndex(s => s.plat === id);
    if (i >= 0) jumpSeg(i);
  }
  function pickPerson(id, handle) {
    plat = id; person = handle;
    renderBloggers();
    const i = blSegs.findIndex(s => s.plat === id && (handle === 'all' ? s.pkey === 'all' : s.handle === handle));
    if (i >= 0) jumpSeg(i);
  }
  async function ensureBloggers() {
    if (bloggers) return false;
    const epoch = dataEpoch;
    let data;
    try { data = await getJSON('bloggers.json', epoch > 0); } catch (e) { data = {platforms: [], items: []}; }
    if (epoch !== dataEpoch || bloggers) return false;
    bloggers = data;
    remember(bloggers.items);
    if (!platOf(plat) && bloggers.platforms[0]) plat = bloggers.platforms[0].id;
    renderBloggers();
    const i = blSegs.findIndex(s => s.plat === plat);
    if (i > 0) jumpSeg(i);
    return true;
  }

  /* ---------- 热搜（底栏，替换原历史页） ---------- */
  async function ensureHotIndex() {
    if (hotIndex) return hotIndex;
    const epoch = dataEpoch;
    let data;
    try { data = await getJSON('hotsearch/index.json', epoch > 0); } catch (e) { data = {dates: []}; }
    if (epoch !== dataEpoch) return hotIndex || {dates: []};
    hotIndex = data;
    return hotIndex;
  }
  function hotPayload() { return hotDay ? hotDays[hotDay] : hot; }
  /** 日期：「今天」+ 存下来的往日（「11月15日」） */
  function hotDayChips() {
    const today = (meta && meta.today) || L.beijingDate(new Date());
    const past = ((hotIndex && hotIndex.dates) || []).filter(d => d.date !== today);
    return [{date: null, label: '今天'}].concat(past.map(d => { const [, m, dd] = d.date.split('-').map(Number); return {date: d.date, label: `${m}月${dd}日`}; }));
  }
  function hotDatesHTML() {
    return `<div class="dates hot-dates" id="hotDates" role="tablist" aria-label="选日期">${hotDayChips().map(c => `<button type="button" role="tab" class="chip${(c.date || null) === hotDay ? ' on' : ''}" data-hot-day="${c.date || ''}" aria-selected="${(c.date || null) === hotDay}">${L.esc(c.label)}</button>`).join('')}</div>`;
  }
  /** 一行热搜的站内 id（已读变灰、长按收藏都用它）：外链地址的哈希 */
  function hotIdOf(href) { let h = 0; for (const c of String(href)) h = (h * 31 + c.charCodeAt(0)) >>> 0; return 'hot-' + h.toString(36); }
  function renderHotBody() {
    const host = $('#hotHost');
    const payload = hotPayload();
    if (hotDay && payload === undefined) { host.innerHTML = `<div class="hot-top">${hotDatesHTML()}</div><p class="muted">正在加载…</p>`; return; }
    if (!payload || !(payload.providers || []).length) { host.innerHTML = `<div class="hot-top">${hotDatesHTML()}</div><p class="muted">${hotDay ? '这天没有存下热搜。' : '热搜暂时没加载出来，稍后点右上角刷新再试。'}</p>`; return; }
    const act = (payload.providers || []).find(p => p.id === hotActive) || payload.providers.find(p => p.status === 'ok') || payload.providers[0];
    const note = hotDay && payload.generated_at ? `这是 ${L.fmtDay(hotDay + 'T12:00:00+08:00')} 最后一次抓到的榜单（${L.fmtTime(payload.generated_at)}）` :
      (act && act.status === 'ok' && (act.fetched_at || payload.generated_at) ? `${L.hotShort(act.name)} · 抓取于 ${L.fmtWhen(act.fetched_at || payload.generated_at)}` : '');
    const end = act && act.status === 'ok' && (act.items || []).length ? `<div class="end-hint end-all" data-end="hot"><span>${ENDED}</span></div>` : '';
    host.innerHTML = `${L.hotsearchHTML(payload, hotActive, false, 1000, {dates: hotDatesHTML(), note})}${end}`;
    $$('.hot-list li', host).forEach(li => { const a = li.querySelector('a'); if (a) li.dataset.hid = hotIdOf(a.href); });
    markRead(host);
  }
  async function renderHot() {
    await ensureHotIndex();
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

  /* ---------- 旧「查看更多」整页链接（#/more/ch:<频道> 或 #/more/bl:<平台>:<人>）：直接跳到长流里那一段 ---------- */
  async function openMoreLink(key) {
    const [type, a, b] = String(key).split(':');
    if (type === 'ch') {
      const i = channels().findIndex(c => c.slug === a);
      showView('channels');
      if (i >= 0) jumpChannel(i);
    } else if (type === 'bl') {
      showView('blogger');
      await ensureBloggers();
      const p = platOf(a);
      if (!p) return;
      const acc = b && b !== 'all' ? p.accounts.find(x => x.key === b) : null;
      pickPerson(p.id, acc ? acc.handle : 'all');
    }
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
    $('#app').dataset.tab = name;
    closeDrop(); updateTopName(); syncBlTop();
    if (name === 'channels') spyChannels();
    if (name === 'blogger') ensureBloggers();
    if (name === 'hot') renderHot();
    if (name === 'favorites') mountFeature(name);
    if (!keepArticle) closeArticle();   // 详情没开、还在加载时也要作废在途的打开
  }

  /* ---------- 正文（整页）与返回原位 ---------- */
  function captureScroll() {
    const root = $('#channelRoot');
    const st = {view: currentView(), mode, search: $('#search-panel').classList.contains('on')};
    st.bannersX = $$('.banner-rail').map(c => c.scrollLeft);
    st.pagerY = root.scrollTop;
    st.subY = $$('.view.on .sub, .view.on [class*="sub"]').map(s => s.scrollTop);
    st.searchY = $$('#search-panel .sub').map(s => s.scrollTop);
    return st;
  }
  function restoreScroll(st) {
    if (!st) return;
    if (st.view && currentView() !== st.view) showView(st.view, true);
    const apply = () => {
      const root = $('#channelRoot');
      {
        root.scrollTop = st.pagerY || 0;
        const rails = $$('.banner-rail'); (st.bannersX || []).forEach((x, i) => { if (rails[i]) rails[i].scrollLeft = x; });
      }
      const subs = $$('.view.on .sub, .view.on [class*="sub"]'); (st.subY || []).forEach((y, i) => { if (subs[i]) subs[i].scrollTop = y; });
      if (st.search) { $('#search-panel').classList.add('on'); const ss = $$('#search-panel .sub'); (st.searchY || []).forEach((y, i) => { if (ss[i]) ss[i].scrollTop = y; }); }
    };
    apply(); requestAnimationFrame(() => requestAnimationFrame(apply));
  }
  /** TG 评论楼：讨论组公开挂件里能看到的评论，按时间从早到晚；楼中楼显示「回复 某人」和被回复的原话。
   *  先放 COMMENT_FOLD 条，其余点「展开」再显示；没有公开评论就不出这一块，不编。 */
  const COMMENT_FOLD = 10;
  function commentsHTML(it) {
    const tg = it.tg || {};
    const list = tg.comments || [];
    if (!list.length) return '';
    const total = tg.comments_total && tg.comments_total > list.length ? tg.comments_total : list.length;
    const note = total > list.length ? `共 ${L.esc(L.fmtN(total))} 条，这里是 Telegram 公开页面上能看到的最近 ${list.length} 条。` : `共 ${list.length} 条，来自 Telegram 公开页面。`;
    const base = (it.url || '').split('?')[0];
    const rows = list.map((c, i) => {
      const name = (c.display_name || '').trim() || '匿名';
      const reply = c.reply_to || c.reply_text ? `<div class="c-reply">${c.reply_to ? `<b>${L.esc(c.reply_to)}</b>` : ''}${c.reply_text ? `<span>${L.esc(c.reply_text)}</span>` : ''}</div>` : '';
      const when = c.published_at ? `<span class="meta">${L.esc(L.fmtTime(c.published_at))}</span>` : '';
      const link = base && Number.isInteger(c.id) ? ` <a class="meta c-open" href="${L.esc(base)}?comment=${c.id}" target="_blank" rel="noopener">原楼</a>` : '';
      return `<div class="comment${i < list.length - COMMENT_FOLD ? ' c-fold' : ''}"><span class="av letter">${L.esc(name[0])}</span><div class="c-main"><div class="nm c-nm">${L.esc(name)}${c.reply_to ? ' <span class="meta">回复</span>' : ''} ${when}${link}</div>${reply}<div class="t-body">${L.esc(c.text)}</div></div></div>`;
    }).join('');
    const hidden = Math.max(0, list.length - COMMENT_FOLD);
    const more = hidden ? `<button type="button" class="more-btn c-more" data-cmt-more>展开更早的 ${hidden} 条</button>` : '';
    return `<section class="tg-comments${hidden ? ' folded' : ''}" data-tg-comments><h4>评论楼 <span class="meta">${L.esc(L.fmtN(total))}</span></h4><p class="cmt-note">${note}<a href="${L.esc(it.url)}" target="_blank" rel="noopener">在 Telegram 看全部</a></p>${more}${rows}</section>`;
  }
  /* 正文页（v16）：大标题 → 作者行（头像 / 名字 / 完整时间）→ 机器翻译标记 + 看原文 → 配图 → 正文（字号可调）→ 引用卡、互动、评论 */
  function artMeta(it) {
    const b = it.blogger || {};
    const isPost = it.kind === 'post';
    const name = (isPost && (b.display_name || b.handle)) || it.source_name || '';
    const av = isPost && b.avatar ? `<img class="av" src="${L.esc(b.avatar)}" alt="">` : `<span class="av letter">${L.esc((name || '?')[0])}</span>`;
    const p = isPost ? platOf(b.platform) : null;
    const sub = [L.fmtFull(it.published_at), p ? p.name : ''].filter(Boolean).join(' · ');
    return `<div class="d-meta">${av}<div class="d-who"><div class="nm">${L.esc(name)}</div><div class="tm">${L.esc(sub)}</div></div>${it.highlight ? '<span class="mt-badge hlb">今日重点</span>' : ''}</div>`;
  }
  function paras(text) { return String(text || '').split(/\n+/).map(x => x.trim()).filter(Boolean).map(x => `<p>${L.esc(x)}</p>`).join(''); }
  function mtRow(d, origHTML) {
    if (!d.translated) return '';
    return `<div class="mt-row art-tools"><span class="mt-badge">${L.esc(d.label)}</span>${origHTML ? '<button type="button" class="orig-btn" data-art-orig>看原文</button>' : ''}</div>${origHTML ? `<div class="art-orig" data-art-orig-box>${origHTML}</div>` : ''}`;
  }
  function artActions(it) {
    const slot = '<div class="fav-slot" data-fav-slot></div>';
    const open = it.url ? `<a class="primary d-src" href="${L.esc(it.url)}" target="_blank" rel="noopener">${L.icon('external-link')}打开原文</a>` : '';
    return `<div class="actions">${slot}${open}</div>`;
  }
  function articleHTML(it) {
    const d = L.display(it);
    const blocks = d.blocks || (d.bodyPending ? null : it.blocks);
    const title = d.title ? `<h3 class="art-title">${L.esc(d.title)}</h3>` : '';
    const cover = it.image && it.image.url ? `<img class="cover" src="${L.esc(it.image.url)}" alt="${L.esc(it.image.alt || '')}" data-zoom="${L.esc(it.image.url)}">` : '';
    const tgMedia = it.tg && it.tg.media;
    const gallery = tgMedia && (tgMedia.length > 1 || tgMedia.some(m => m.type === 'video')) ? L.mediaGrid(tgMedia, it.url) : cover;
    const media = gallery + (it.tg && it.tg.video_unavailable ? `<p class="muted"><a href="${L.esc(it.url)}" target="_blank" rel="noopener">在 Telegram 查看无法内播的视频</a></p>` : '');
    if (d.bodyPending && !(d.blocks && d.blocks.length) && it.kind !== 'post') {
      // 全文译文没好时，原文照样能看
      const ob = d.orig ? (it.blocks && it.blocks.length ? `<div class="art-blocks">${L.blocksHTML(it.blocks)}</div>` : L.esc(d.orig.body || d.orig.summary || '')) : '';
      return `${title}${artMeta(it)}${mtRow(d, ob ? `<h4>${L.esc(d.orig.title || '')}</h4>${ob}` : '')}${media}<p class="art-pending">${L.esc(L.BODY_PENDING)}</p>${d.summary ? `<div class="art-text">${paras(d.summary)}</div>` : ''}${artActions(it)}`;
    }
    if (blocks && blocks.length) {
      // 公众号 / 博客 / 抽出的新闻正文：按原文顺序；有译文 blocks 时直接显示中文，原文可展开
      const origBlocks = d.translated && it.blocks && d.blocks ? `<div class="art-blocks">${L.blocksHTML(it.blocks)}</div>` : '';
      return `${title}${artMeta(it)}${mtRow(d, origBlocks)}${it.tg ? media : ''}<div class="art-blocks" data-blocks>${L.blocksHTML(blocks)}</div>${artActions(it)}`;
    }
    if (it.kind === 'post') return `${L.tweetCardHTML(it, false)}${artActions(it)}`;
    let text = (d.body || d.summary || '').trim();
    // TG 正文第一行常是「【标题】」，标题已单独显示，正文里不再重复
    const first = text.split('\n')[0].replace(/[【】\s]/g, '');
    if (first && first === d.title.replace(/[【】\s]/g, '')) text = text.slice(text.indexOf('\n') + 1 || text.length).trim();
    const orig = d.translated ? `<h4>${L.esc(d.orig.title)}</h4>${L.esc(d.orig.body || d.orig.summary)}` : '';
    const bare = L.isBareForward(it);
    const pending = d.bodyPending ? `<p class="art-pending">${L.esc(L.BODY_PENDING)}</p>` : '';
    const main = bare ? '<div class="fwd-tag">转发</div>' :
      `${pending}${text || !it.quote ? `<div class="art-text${text ? '' : ' none'}">${text ? paras(text) : `<p>${L.esc(L.NO_BODY)}</p>`}</div>` : ''}`;
    return `${bare ? '' : title}${artMeta(it)}${mtRow(d, orig)}${media}${main}${L.quoteCardHTML(it, true)}${L.tgStatsHTML(it, true)}${commentsHTML(it)}${artActions(it)}`;
  }
  /** 评论数：TG 评论总数 / 抓到的评论 / X 回复数；都没有就 0（按钮上只写「评论」） */
  function cmtCount(it) {
    const tg = it.tg || {}, b = it.blogger || {};
    return tg.comments_total || (tg.comments || []).length || (b.comments || []).length || ((b.metrics || {}).reply) || 0;
  }

  /* ---------- 底部半屏（v16）：评论、分享、字号、更多 ---------- */
  function openSheet(html, opts = {}) {
    const sh = $('#actSheet');
    $('#actBody').innerHTML = html;
    sh.querySelector('.box').className = 'box act-box' + (opts.half ? ' half' : '') + (opts.cls ? ' ' + opts.cls : '');
    sh.classList.add('on'); sh.setAttribute('aria-hidden', 'false');
    $('#actBody').scrollTop = 0;
  }
  function closeSheet() { const sh = $('#actSheet'); sh.classList.remove('on'); sh.setAttribute('aria-hidden', 'true'); }
  let artItem = null;
  function curItem() { return articleOpen ? artItem : null; }
  function openComments(it) {
    const tg = it.tg || {}, b = it.blogger || {};
    const n = cmtCount(it);
    let body;
    if ((tg.comments || []).length) body = commentsHTML(it).replace(' folded', '').replace(/<button type="button" class="more-btn c-more" data-cmt-more>[^<]*<\/button>/, '');
    else if ((b.comments || []).length) body = L.xCommentsHTML(it, true);
    else body = `<div class="empty-cmt">暂时没有抓到公开评论。${it.url ? `<a class="d-link" href="${L.esc(it.url)}" target="_blank" rel="noopener">到原文看讨论 ›</a>` : ''}</div>`;
    const ttl = (tg.comments || []).length ? '评论楼' : (b.comments || []).length ? '热门回复' : '评论';
    openSheet(`<div class="sh-title">${ttl}${n ? `<small>${L.esc(L.fmtN(n))} 条</small>` : ''}</div><div class="cmts">${body}</div>`, {half: true});
  }
  function openShare(it) {
    openSheet(`<div class="sh-title">分享<small>${L.esc(it.source_name || ((it.blogger || {}).display_name) || '')}</small></div><div class="share-grid">
      <button type="button" data-act="sys"><span>${L.icon('share')}</span>系统分享</button><button type="button" data-act="copy"><span>${L.icon('link')}</span>复制链接</button>
      <button type="button" data-act="text"><span>${L.icon('copy')}</span>复制标题</button>${it.url ? `<button type="button" data-act="open"><span>${L.icon('external-link')}</span>打开原文</button>` : ''}</div><button type="button" class="sh-cancel" data-act="x">取消</button>`);
  }
  const FONT_KEY = 'rebang-v11-font', FONT_DEF = 18;
  function setFont(v) {
    v = Math.max(14, Math.min(26, Number(v) || FONT_DEF));
    document.documentElement.style.setProperty('--rfs', v + 'px');
    try { if (v === FONT_DEF) localStorage.removeItem(FONT_KEY); else localStorage.setItem(FONT_KEY, String(v)); } catch (e) { /* 隐私模式 */ }
    return v;
  }
  try { if (localStorage.getItem(FONT_KEY)) setFont(localStorage.getItem(FONT_KEY)); } catch (e) { /* 隐私模式 */ }
  function fontNow() { return parseInt(getComputedStyle(document.documentElement).getPropertyValue('--rfs'), 10) || FONT_DEF; }
  function openFont() {
    const v = fontNow();
    openSheet(`<div class="sh-title">字号<small id="fontV">${v}px</small></div><div class="font-sh"><div class="font-row"><span class="a1">A</span><input type="range" min="14" max="26" step="1" value="${v}" id="fontRange" aria-label="正文字号"><span class="a2">A</span></div>
      <div class="font-prev">拖动滑块调整正文字号，正文会立即变化，下次打开也照这个字号。</div><div class="font-btns"><button type="button" data-act="font-def">默认字号</button><button type="button" class="pri" data-act="x">完成</button></div></div>`);
    $('#fontRange').oninput = e => { $('#fontV').textContent = setFont(e.target.value) + 'px'; };
  }
  function openArtMore(it) {
    openSheet(`<div class="menu-list"><button type="button" data-act="font">${L.icon('a-large-small')}字号</button><button type="button" data-act="copy">${L.icon('link')}复制链接</button>${it.url ? `<button type="button" data-act="open">${L.icon('external-link')}打开原文</button>` : ''}</div><button type="button" class="sh-cancel" data-act="x">取消</button>`);
  }
  async function onSheet(e) {
    const sh = $('#actSheet');
    if (performance.now() < suppressClickUntil) return;
    const b = e.target.closest('[data-act], [data-all-plat], [data-person]');
    if (!b) { if (e.target === sh) closeSheet(); return; }
    if (b.dataset.allPlat) { closeSheet(); pickPlat(b.dataset.allPlat); return; }
    if (b.dataset.person) { closeSheet(); pickPerson(b.dataset.platOf || plat, b.dataset.person); return; }
    const act = b.dataset.act, it = curItem();
    if (act === 'font') { openFont(); return; }
    if (act === 'font-def') { const r = $('#fontRange'); if (r) { r.value = FONT_DEF; } $('#fontV').textContent = setFont(FONT_DEF) + 'px'; return; }
    closeSheet();
    if (!it || act === 'x') return;
    if (act === 'sys') shareItem(it);
    else if (act === 'copy') toast(await copyText(linkOf(it)) ? '链接已复制。' : '没能复制链接。');
    else if (act === 'text') { const t = (L.display(it).title || it.title || '') + ' ' + linkOf(it); toast(await copyText(t.trim()) ? '已复制标题和链接。' : '没能复制。'); }
    else if (act === 'open' && it.url) window.open(it.url, '_blank', 'noopener');
  }
  function syncArtFav() {
    const F = window.RebangFavorites, btn = $('#dFav');
    const on = !!(articleId && F && F.isFavorite && F.isFavorite(articleId));
    btn.classList.toggle('faved', on); btn.setAttribute('aria-pressed', String(on)); btn.setAttribute('aria-label', on ? '取消收藏' : '收藏');
    btn.innerHTML = L.icon(on ? 'bookmark-check' : 'bookmark');
  }
  function attachFav(slot, it) {
    const handle = mounted.favorites || (registry.favorites && mountFeature('favorites'));
    if (handle && typeof handle.attachButton === 'function') return handle.attachButton(slot, it);
    if (window.RebangFavorites && window.RebangFavorites.attachButton) return window.RebangFavorites.attachButton(slot, it, {toast});
    slot.remove();
  }
  /* 详情里的「上一条 / 下一条」：在打开它的那个列表里按顺序走（频道信息流、banner、查看更多、博主、收藏、搜索结果） */
  let navList = null;   // {ids, at}
  const LIST_SCOPE = '.feed-list, .banner-rail, #bloggerList, .hot-list, [data-favorites-list], #search-panel';
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
    return `<button type="button" class="art-nav-btn" data-nav="-1" aria-label="上一条"${prev ? '' : ' disabled'}>${L.icon('chevron-left')}</button>` +
      (at >= 0 ? `<span class="art-nav-pos">${at + 1} / ${navList.ids.length}</span>` : '') +
      `<button type="button" class="art-nav-btn" data-nav="1" aria-label="下一条"${next ? '' : ' disabled'}>${L.icon('chevron-right')}</button>`;
  }
  function renderNav() { const el = $('#artNav'); el.hidden = !(navList && navList.ids.includes(articleId)); el.innerHTML = el.hidden ? '' : navHTML(); }
  async function step(dir) {
    if (!navList || !articleOpen) return false;
    const at = navList.ids.indexOf(articleId), to = navList.ids[at + dir];
    if (at < 0 || !to) { toast(dir > 0 ? '已经是这个列表的最后一条。' : '已经是这个列表的第一条。'); return false; }
    const snap = (mounted.search && typeof mounted.search.getItem === 'function' ? mounted.search.getItem(to) : null) || null;
    await openItem(snap || to, {replace: true, keepNav: true});
    return true;
  }
  // 作废令牌：每次打开详情、关闭详情（返回按钮、右滑、切页）、来源状态、搜索、浏览器前进后退都递增；
  // 异步读完发现已不是最新一次，就丢弃结果（不打开详情、不改地址栏），包括正文还没显示的情况
  let openSeq = 0;
  let navSeq = 0;       // 仅用户导航递增，刷新不递增；用于区分刷新取消的深链与更新的用户导航
  let articleGen = 0;   // 每次实际打开/关闭正文时递增，给右滑关闭动画绑定当前正文实例
  async function openItem(ref, opts = {}) {
    const id = typeof ref === 'string' ? ref : ref && ref.id;
    if (!id) return;
    const seq = ++openSeq;
    const myNav = ++navSeq;
    // 进入 await 之前先记下返回位置：调用方（如搜索）可能紧接着就把自己的层收起来
    const ret = !opts.fromPop && !(articleOpen && articleId === id) ? (articleOpen ? returnState : captureScroll()) : null;
    // 先按 id 经 id-index 读本次发布的完整条目（被折叠的条目在 merged.json 里，带正文和「今日重点」标）；
    // 读不到（或超时）再用收藏/搜索传进来的快照兜底
    let it = await findItem(id) || (typeof ref === 'object' ? ref : null);
    if (seq !== openSeq) {
      if ((opts.fromPop || opts.replaceHash) && myNav === navSeq && L.parseItemHash(location.hash) === id) {
        if (articleOpen) closeArticle({fromPop: true});
        history.replaceState({home: true}, '', location.pathname + location.search);
      }
      return;
    }
    if (!it) {
      const fav = window.RebangFavorites && window.RebangFavorites.load ? window.RebangFavorites.load().find(x => x.id === id) : null;
      const hit = mounted.search && typeof mounted.search.getItem === 'function' ? mounted.search.getItem(id) : null;
      if (fav || hit) it = fav || hit;
      else {
        if (opts.fromPop || opts.replaceHash) {
          if (articleOpen) closeArticle({fromPop: true});
          if (L.parseItemHash(location.hash) || (history.state && history.state.article)) {
            history.replaceState({home: true}, '', location.pathname + location.search);
          }
        }
        toast('这条已经不在最近一次发布的数据里了。');
        return;
      }
    }
    if (!opts.keepNav && !opts.fromPop) navList = opts.list ? {ids: opts.list} : null;
    if (ret) returnState = ret;
    $('#search-panel').classList.remove('on');
    $('#articleTitle').textContent = it.kind === 'post' ? ((it.blogger && it.blogger.display_name) || '帖子') : (L.display(it).title || '正文');
    const body = $('#articleBody');
    body.innerHTML = articleHTML(it);
    const slot = body.querySelector('[data-fav-slot]');
    if (slot) attachFav(slot, it);
    const av = $('#articleView');
    av.style.transition = ''; av.style.transform = '';
    av.classList.add('on');
    body.scrollTop = 0; $('#artBar').classList.remove('solid');
    articleOpen = true; articleId = id; artItem = it; articleGen++;
    const n = cmtCount(it); $('#dCmtN').textContent = n ? L.fmtN(n) : '评论';
    syncArtFav(); setRead(id);
    renderNav();
    if (opts.replaceHash || (opts.replace && history.state && history.state.article)) history.replaceState({article: id}, '', L.itemHash(id));
    else if (!opts.fromPop) history.pushState({article: id}, '', L.itemHash(id));
  }
  function closeArticle(opts = {}) {
    openSeq++; navSeq++;               // 离开详情：在途的打开（如「下一条」、慢深链）一律作废
    if (!articleOpen) {
      if (!opts.fromPop && (L.parseItemHash(location.hash) || (history.state && history.state.article))) {
        history.replaceState({home: true}, '', location.pathname + location.search);
      }
      return;
    }
    articleOpen = false; articleId = null; artItem = null; articleGen++;
    closeSheet();
    $('#articleView').classList.remove('on');
    $('#articleView').style.transition = '';
    $('#articleView').style.transform = '';
    restoreScroll(returnState);
    if (!opts.fromPop) {
      if (history.state && history.state.article) history.back();
      else if (L.parseItemHash(location.hash)) history.replaceState({home: true}, '', location.pathname + location.search);
    }
  }
  const HEALTH_HASH = '#/health';
  let healthLoad = 0, healthSnapshot = null;
  function updateHealthFreshness() {
    const now = Date.now();
    const freshness = window.RebangHealth.snapshotFreshness;
    const warningFor = state => state === 'unknown' ? '数据时间未知' : state === 'stale' ? '数据已过期' : '';
    const openSnapshot = healthSnapshot && $('#healthView').open;
    const snapshotState = openSnapshot ? freshness(healthSnapshot.generated_at, now) : null;
    if (meta) {
      const entry = $('#healthEntry');
      const count = entry.querySelector('.health-entry-count');
      const {total, issues} = meta.health_summary || {};
      const known = Number.isInteger(total) && Number.isInteger(issues) && total > 0 && issues >= 0 && issues <= total;
      const state = freshness(meta.built_at, now);
      const warning = warningFor(state) || warningFor(snapshotState);
      const needsAttention = Boolean(warning) || (known && issues > 0);
      entry.classList.toggle('has-issues', needsAttention);
      count.textContent = warning || (needsAttention ? issues : '');
      count.hidden = !needsAttention;
      if (warning) entry.setAttribute('aria-label', `来源状态，${warning}`);
      else if (known) entry.setAttribute('aria-label', needsAttention ? `来源状态，${issues} 个来源需处理` : '来源状态，全部健康');
      else entry.removeAttribute('aria-label');
    }
    if (openSnapshot) {
      const timestamp = healthSnapshot.generated_at;
      const state = snapshotState;
      const stamp = $('#healthStamp');
      stamp.textContent = state === 'unknown' ? '数据时间未知' :
        `${state === 'stale' ? '数据已过期 · ' : ''}数据更新于 ${L.fmtFull(timestamp)}（北京时间）`;
      stamp.hidden = false;
      const overview = $('#healthBody .health-overview[data-healthy-count]');
      if (overview) {
        const warning = state !== 'fresh' || Boolean($('#healthBody .health-data-warning'));
        overview.dataset.overview = warning ? 'warning' : 'ok';
        overview.firstElementChild.textContent = `${overview.dataset.healthyCount} 个${warning ? '可用来源记录为正常' : '来源全部正常'}`;
      }
    }
  }
  function filterHealth(event) {
    event.target.closest('.health-age')?.focus();
    const selected = event.target.closest('[data-health-filter]');
    if (!selected) return;
    const body = event.currentTarget;
    const status = selected.dataset.healthFilter;
    if (selected.getAttribute('aria-pressed') === 'true') return;
    const showIssues = status === 'issues';
    $$('[data-health-filter]', body).forEach(button => button.setAttribute('aria-pressed', button === selected));
    $$('[data-health-group]', body).forEach(group => {
      group.hidden = !showIssues && group.dataset.healthGroup !== status;
      group.querySelector('summary').hidden = !showIssues;
      group.open = !showIssues || group.dataset.healthGroup !== 'ok';
    });
    body.scrollTop = 0;
  }
  async function openHealth(fromPop = false) {
    openSeq++; navSeq++;
    const dialog = $('#healthView');
    if (dialog.open) return;
    if (!fromPop) history.pushState({health: true}, '', HEALTH_HASH);
    const body = $('#healthBody'), stamp = $('#healthStamp');
    const load = ++healthLoad;
    healthSnapshot = null;
    stamp.hidden = true;
    body.innerHTML = '<p class="muted" role="status">正在加载来源健康…</p>';
    dialog.showModal();
    body.scrollTop = 0;
    try {
      const data = await getJSON('health.json');
      if (load !== healthLoad || !dialog.open) return;
      if (data.schema !== 'rebang.source-health/1' || !Array.isArray(data.sources)) throw new Error('Invalid health snapshot');
      const now = Date.now();
      body.innerHTML = window.RebangHealth.healthHTML(data.sources, now,
        window.RebangHealth.snapshotFreshness(data.generated_at, now) !== 'fresh');
      healthSnapshot = data;
      updateHealthFreshness();
    } catch (e) {
      if (load === healthLoad && dialog.open) body.innerHTML = '<p class="muted" role="status">健康数据暂时加载不出来。</p>';
    }
  }
  function leaveHealth() {
    if (history.state && history.state.health) history.back();
    else location.hash = '';
  }
  window.addEventListener('popstate', e => {
    openSeq++; navSeq++;               // 浏览器前进/后退：先作废在途的详情打开；要打开详情的分支下面会重新开
    if (location.hash === HEALTH_HASH) { openHealth(true); return; }
    const health = $('#healthView');
    if (health.open) { health.close(); updateHealthFreshness(); }
    const st = e.state || {};
    const hashId = !e.state ? L.parseItemHash(location.hash) : null;
    if (st.article) openItem(st.article, {fromPop: true});
    else if (/^#\/more\//.test(location.hash)) {
      // 旧「查看更多」链接（例如私聊稿里的）在已开着的页面里点开：跳到长流里那一段
      if (articleOpen) closeArticle({fromPop: true});
      const key = location.hash.slice(7);
      history.replaceState({home: true}, '', location.pathname + location.search);
      try { openMoreLink(decodeURIComponent(key)); } catch (err) { /* 坏链接 */ }
    } else if (hashId) {
      // 已开着的页面里再点一次私聊稿链接（只改了 #/item/…）：加载成功后才把历史条目替换成 {article}，失败时保持正文与地址栏一致
      openItem(hashId, {replaceHash: true});
    } else if (articleOpen) closeArticle({fromPop: true});
  });

  /* ---------- 刷新 ---------- */
  // meta.built_at 统一在这里校验：坏值、缺时区都当作未知，不交给 new Date()。
  function builtAtMs() { return meta ? window.RebangHealth.timeMs(meta.built_at) : NaN; }
  function stampRefresh(d) {
    const ms = d instanceof Date ? d.getTime() : NaN;
    $('#refreshed').textContent = Number.isFinite(ms) ? `刷新于 ${L.fmtRefreshed(d)}` : '刷新时间未知';
  }
  async function doRefresh() {
    const btn = $('#btnRefresh');
    btn.classList.remove('spin'); void btn.offsetWidth; btn.classList.add('spin'); setTimeout(() => btn.classList.remove('spin'), MOTION.slow + 50);
    const NOTE = '刷新拿到的是最近一次发布的数据。';
    const old = meta && meta.built_at;
    let fresh;
    try { fresh = await getJSON('meta.json', true); } catch (e) { updateHealthFreshness(); toast('刷新失败，网络或站点暂时连不上。'); hidePtr(); return; }
    stampRefresh(new Date());
    if (fresh.built_at !== old) {
      const idx = curCh, blAt = Number($('#bloggerList').dataset.cur || 0);
      dataEpoch++; openSeq++; abortPendingFinds();
      items.clear(); idIndex = null; bloggers = null; segCache.clear(); hotIndex = null; Object.keys(hotDays).forEach(k => delete hotDays[k]);
      await loadAll(true);
      renderChannels();
      if (currentView() === 'hot') renderHot();
      if (idx > 0) jumpChannel(Math.min(idx, channels().length - 1));
      if (currentView() === 'blogger') { await ensureBloggers(); if (blAt > 0 && blSegs[blAt]) jumpSeg(Math.min(blAt, blSegs.length - 1)); }
      toast('有新内容，已更新。' + NOTE);
    } else {
      meta = fresh;
      updateHealthFreshness();
      toast('没有新内容，已是最新。' + NOTE);
    }
    hidePtr();
  }
  function hidePtr() { const p = $('#ptr'); p.classList.remove('spin', 'show'); p.hidden = true; }

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
    const dur = REDUCE.matches ? 1 : (ms != null ? ms : Math.min(MOTION.slow, MOTION.fast + Math.abs(dist) * 0.25)); const t0 = performance.now();
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
      skip = false;
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
      if (scroller.style.transform) { scroller.style.transition = MOTION.tr('transform', MOTION.slow); scroller.style.transform = 'translateX(0)'; setTimeout(() => { scroller.style.transition = ''; scroller.style.transform = ''; }, MOTION.slow + 20); }
      const w = scroller.clientWidth || 1, raw = scroller.scrollLeft, max = Math.max(0, scroller.scrollWidth - scroller.clientWidth);
      let idx = Math.round(raw / w); if (Math.abs(vel) > 0.35) idx = vel < 0 ? Math.ceil(raw / w) : Math.floor(raw / w);
      animateScrollX(scroller, Math.max(0, Math.min(max, idx * w)));
      setTimeout(() => scroller.classList.remove('is-drag'), MOTION.base + 20);
    };
    scroller.addEventListener('touchend', end, opt); scroller.addEventListener('touchcancel', end, opt);
    scroller.addEventListener('scroll', () => updateHInd(scroller), opt);
  }
  /* ---------- 手势总表（2026-11-15 22:08 阿欢要求「定好优先级并测试」）----------
     一次触摸只归一种手势，先按「从哪里开始」判，再按「先往哪个方向动」判（动 8px 后锁定方向）：
       1. 详情页：从屏幕左边缘 24px 内开始往右滑 → 返回；其余横滑 → 上一条 / 下一条（详情页里没有频道和 banner 横滑）。
       2. banner 区域里横滑 → 只翻 banner（bindHSwipe，换频道不接手）。
       3. 横向可滚的条（平台图标、日期、人物、热搜 tab）→ 原生横滚，谁也不接手。
       4. 「左右」模式的频道长流 → 横滑只换频道（跳到上一个/下一个频道的开头）；「上下」模式横滑什么也不做。
       5. 卡片没有横滑动作（2026-11-16 22:47 阿欢：去掉左滑收藏/右滑分享）。收藏、分享等一律长按卡片弹菜单，频道/博主/收藏/热搜/搜索结果都一样。
       6. 竖向：列表已在最顶上且往下拉 → 下拉刷新；否则正常滚动。
       7. 长按卡片 0.5 秒且手指几乎没动（< 8px）→ 卡片菜单（收藏/分享/复制链接/打开原文）；之后的点击不再打开详情。
       8. 底栏同一个按钮 0.35 秒内点两下 → 当前页回到顶部（点一下照常切页）。 */
  const EDGE = 24, LOCK = 8, CH_SWIPE = 64, PULL_GO = 56, LONG_MS = 500;
  const CARD_SEL = '.feed-row, .tweet, .row-item, .hero, .hot-list li';
  const HSCROLL_SEL = '.chips, .dates, .people, .hot-tabs, .banner-rail, .banner-wrap, .accs, .drop, pre, .b-pre';
  const SCROLLER_SEL = '.feed-root, .sub, .article-body';
  let g = null, suppressClickUntil = 0;
  /** 热搜一行没有站内条目：用它的外链拼一个只读条目（收藏里点开显示标题 +「打开原文」，分享给外链） */
  function hotItem(li) {
    const a = li.querySelector('a'); if (!a || !a.href) return null;
    const sec = li.closest('.hot'), tab = sec && sec.querySelector('.hot-tabs .on b');
    const title = (li.querySelector('.t') || a).textContent.trim();
    return {id: hotIdOf(a.href), kind: 'news', hot: true, title, summary: '', url: a.href, source_name: tab ? `${tab.textContent.trim()}热搜` : '热搜', published_at: ''};
  }
  function cardItem(card) {
    if (card && card.matches('.hot-list li')) return hotItem(card);
    const id = card && (card.dataset.id || card.dataset.itemId);
    if (!id) return null;
    if (items.get(id)) return items.get(id);
    const fav = window.RebangFavorites && window.RebangFavorites.load ? window.RebangFavorites.load().find(x => x.id === id) : null;
    return fav || {id};
  }
  function linkOf(it) { if (it.hot) return it.url; return location.origin + location.pathname + L.itemHash(it.id); }
  async function copyText(t) {
    try { await navigator.clipboard.writeText(t); return true; } catch (e) {
      const ta = document.createElement('textarea'); ta.value = t; ta.setAttribute('readonly', ''); ta.style.position = 'fixed'; ta.style.opacity = '0';
      document.body.appendChild(ta); ta.select(); let ok = false; try { ok = document.execCommand('copy'); } catch (e2) { ok = false; } ta.remove(); return ok;
    }
  }
  async function shareItem(it) {
    const url = linkOf(it), title = L.display(it).title || it.title || '拾光资讯';
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
    if (articleId === it.id) syncArtFav();
    toast(res.on ? '已收藏，只存在这台设备的浏览器里。' : '已取消收藏。');
  }
  function openMenu(card) {
    const it = cardItem(card); if (!it) return;
    const F = window.RebangFavorites;
    const on = F && F.isFavorite ? F.isFavorite(it.id) : false;
    const full = items.get(it.id) || it;
    const menu = $('#cardMenu');
    const prev = L.display(full).title || full.title || String(L.display(full).summary || '').slice(0, 90);
    menu.querySelector('.box').innerHTML = `<div class="handle"></div>${prev ? `<div class="menu-ttl">${L.esc(prev)}</div>` : ''}
      <div class="menu-list"><button type="button" data-menu="fav" class="${on ? 'red' : ''}">${L.icon(on ? 'bookmark-check' : 'bookmark')}<span>${on ? '取消收藏' : '收藏'}</span></button><button type="button" data-menu="share">${L.icon('share')}<span>分享</span></button>
      <button type="button" data-menu="copy">${L.icon('link')}<span>复制链接</span></button>${full.url ? `<button type="button" data-menu="open">${L.icon('external-link')}<span>打开原文</span></button>` : ''}</div><button type="button" data-menu="cancel" class="cancel sh-cancel">取消</button>`;
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
  function onTouchStart(e) {
    if (zoom.open || e.target.closest('#zoomView')) { g = null; return; }
    if (e.touches.length !== 1) { g = null; return; }
    const t = e.touches[0], target = e.target;
    const inArticle = !!target.closest('#articleView');
    // 「另有 N 个来源」折叠控件不算卡片：按住它不弹卡片菜单
    const card = !inArticle && !target.closest('[data-dup]') ? target.closest(CARD_SEL) : null;
    g = {x0: t.clientX, y0: t.clientY, x: t.clientX, y: t.clientY, t0: performance.now(), axis: null, target, card,
      inArticle, edge: inArticle && t.clientX <= EDGE, hscroll: !!target.closest(HSCROLL_SEL),
      lrChannels: !!target.closest('.feed-root.lr'), scroller: target.closest(SCROLLER_SEL), kind: null, long: null};
    if (card) g.long = setTimeout(() => { if (g && !g.axis) { g.kind = 'menu'; suppressClickUntil = performance.now() + 60000; if (navigator.vibrate) navigator.vibrate(10); card.classList.add('press'); setTimeout(() => card.classList.remove('press'), MOTION.slow); openMenu(card); } }, LONG_MS);
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
        else if (g.hscroll) g.kind = null;                                                                         // 规则 2–3
        else if (g.lrChannels) g.kind = 'chswipe';                                                                 // 规则 4（规则 5：卡片不接横滑）
      } else if (dy > 0 && g.scroller && g.scroller.scrollTop <= 0 && !g.inArticle) g.kind = 'pull';            // 规则 6
    }
    if (!g.kind || g.kind === 'menu') return;
    if (e.cancelable) e.preventDefault();
    if (g.kind === 'back') { $('#articleView').style.transform = `translateX(${Math.max(0, dx)}px)`; }
    else if (g.kind === 'step') { $('#articleBody').style.transform = `translateX(${dx * 0.35}px)`; }
    else if (g.kind === 'chswipe') { $('#channelRoot').style.transform = `translateX(${dx * 0.3}px)`; } else if (g.kind === 'pull') {
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
      const gen = articleGen;
      if (dx > 80) {
        openSeq++; navSeq++;
        av.style.transition = MOTION.tr('transform', MOTION.fast);
        av.style.transform = 'translateX(100%)';
        setTimeout(() => {
          if (articleGen !== gen) return;
          av.style.transition = '';
          if (articleOpen) closeArticle();
        }, MOTION.fast);
      }
      else { av.style.transition = MOTION.tr('transform', MOTION.base); av.style.transform = ''; setTimeout(() => { if (articleGen === gen) av.style.transition = ''; }, MOTION.base); }
    } else if (s0.kind === 'step') {
      const body = $('#articleBody'); body.style.transform = '';
      if (Math.abs(dx) > 60) step(dx < 0 ? 1 : -1);
    } else if (s0.kind === 'chswipe') {
      const root = $('#channelRoot');
      suppressClickUntil = performance.now() + 300;
      root.style.transition = MOTION.tr('transform', MOTION.fast); root.style.transform = '';
      setTimeout(() => { root.style.transition = ''; }, MOTION.fast + 10);
      if (Math.abs(dx) >= CH_SWIPE) jumpChannel(curCh + (dx < 0 ? 1 : -1), dx < 0 ? 1 : -1);
    } else if (s0.kind === 'pull') {
      const el = s0.scroller; const go = (s0.pull || 0) > PULL_GO;
      el.style.transition = MOTION.tr('transform', MOTION.slow); el.style.transform = 'translateY(0)';
      setTimeout(() => { el.style.transition = ''; el.style.transform = ''; }, MOTION.slow);
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
    // 列表一滚动就取消长按计时：有的浏览器滚动开始后不再派发 touchmove，手指停住会被误判成长按弹菜单
    app.addEventListener('scroll', () => { if (g && g.long && g.kind !== 'menu') { clearTimeout(g.long); g.long = null; } }, {passive: true, capture: true});
  }
  function scrollTopOf(view) {
    if (view === 'channels') return $('#channelRoot');
    if (view === 'favorites') return $('#view-favorites .sub');
    return $(`#view-${view} .sub`);
  }
  let lastTab = {view: null, t: 0};
  function onTab(view) {
    const now = performance.now();
    if (lastTab.view === view && now - lastTab.t < 350 && currentView() === view) {
      const el = scrollTopOf(view); if (el) el.scrollTo({top: 0, behavior: REDUCE.matches ? 'auto' : 'smooth'});
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
  }

  /* ---------- 图片/视频全屏查看（现有栈，不另加依赖）：点开、左右滑、图片双指缩放、点空白或下滑关闭 ----------
   * 视频用原生 <video controls playsinline>，不自动出声；GIF 静音循环；离开当前一项就暂停；
   * 播放出错保留封面，并给出原帖链接。 */
  const zoom = {items: [], urls: [], i: 0, open: false, scale: 1, tx: 0, ty: 0, start: null, origin: ''};
  function zoomUrlsFrom(el) {
    const mgrid = el.closest('[data-media-list]');
    if (mgrid) {
      let items = [];
      try { items = JSON.parse(mgrid.dataset.mediaList).map(m => ({type: m.t, src: m.u, poster: m.p || ''})).filter(m => m.src); } catch (e) { items = []; }
      if (items.length) {
        const i = Number(el.dataset.mediaI);
        return {items, i: Number.isInteger(i) && i >= 0 && i < items.length ? i : 0, origin: mgrid.dataset.origin || ''};
      }
    }
    const asImages = (urls, i) => ({items: urls.map(u => ({type: 'image', src: u})), i, origin: ''});
    const grid = el.closest('[data-zoom-list]');
    if (grid && grid.dataset.zoomList) {
      const urls = grid.dataset.zoomList.split('|').filter(Boolean);
      const i = Math.max(0, urls.indexOf(el.dataset.zoom || el.src));
      return asImages(urls, i < 0 ? 0 : i);
    }
    const scope = el.closest('.article-body, .tweet, .feed-row, .hero, .row-item, .more-body, .art-orig') || document;
    const urls = [];
    scope.querySelectorAll('img[data-zoom]').forEach(x => { const u = x.dataset.zoom || x.currentSrc || x.src; if (u && !urls.includes(u)) urls.push(u); });
    const cur = el.dataset.zoom || el.currentSrc || el.src;
    const i = Math.max(0, urls.indexOf(cur));
    return asImages(urls.length ? urls : [cur], i < 0 ? 0 : i);
  }
  function zoomCur() { return zoom.items[zoom.i] || {type: 'image'}; }
  function zoomPaint() {
    const stage = $('#zoomStage'), el = stage.firstElementChild;
    if (el) el.style.transform = `translate(${zoom.tx}px, ${zoom.ty}px) scale(${zoom.scale})`;
    $('#zoomCount').textContent = `${zoom.i + 1} / ${zoom.items.length}`;
    $('#zoomPrev').disabled = zoom.items.length < 2;
    $('#zoomNext').disabled = zoom.items.length < 2;
  }
  /** 停掉舞台上的视频：移出 DOM 的 <video> 在部分浏览器里会继续出声，所以先暂停再卸地址 */
  function zoomStopMedia() {
    $$('#zoomStage video').forEach(v => { try { v.pause(); v.removeAttribute('src'); v.load(); } catch (e) { /* 已卸载 */ } });
    $$('#zoomStage iframe').forEach(f => { try { f.src = 'about:blank'; } catch (e) { /* 已卸载 */ } });
  }
  function zoomVideoFail(v) {
    const m = zoomCur();
    const box = v.closest('.zoom-media');
    if (!box || box.dataset.failed) return;
    box.dataset.failed = '1';
    zoomStopMedia();
    const link = zoom.origin || m.src;
    box.className = 'zoom-media zoom-fail';
    box.innerHTML = `${m.poster ? `<img src="${L.esc(m.poster)}" alt="">` : ''}<p>视频暂时播不了${link ? ` · <a href="${L.esc(link)}" target="_blank" rel="noopener">${zoom.origin ? '打开原帖' : '打开视频文件'}</a>` : ''}</p>`;
  }
  function zoomGo(i) {
    if (!zoom.items.length) return;
    zoomStopMedia();
    zoom.i = (i + zoom.items.length) % zoom.items.length;
    zoom.scale = 1; zoom.tx = 0; zoom.ty = 0;
    const stage = $('#zoomStage'), m = zoomCur();
    const poster = m.poster ? ` poster="${L.esc(m.poster)}"` : '';
    if (m.type === 'video') {
      stage.innerHTML = `<div class="zoom-media is-video"><video src="${L.esc(m.src)}"${poster} controls playsinline preload="metadata"></video></div>`;
    } else if (m.type === 'youtube') {
      // YouTube 用 youtube-nocookie 嵌入播放器，点播放才出声；页面整体 referrer 是 same-origin，
      // 嵌入播放器没有来源会报「播放器配置错误」，所以这一个 iframe 单独带来源域名（不带路径）。
      const open = zoom.origin || m.src;
      stage.innerHTML = `<div class="zoom-media is-video is-yt"><div class="yt-frame"><iframe src="${L.esc(m.src)}?playsinline=1&rel=0" title="YouTube 视频" allow="encrypted-media; picture-in-picture; fullscreen" allowfullscreen referrerpolicy="strict-origin-when-cross-origin" loading="eager"></iframe></div>${open ? `<p class="yt-open"><a href="${L.esc(open)}" target="_blank" rel="noopener">播不了？在 YouTube 打开</a></p>` : ''}</div>`;
    } else if (m.type === 'gif') {
      stage.innerHTML = `<div class="zoom-media is-gif"><video src="${L.esc(m.src)}"${poster} autoplay muted loop playsinline preload="auto"></video></div>`;
    } else {
      stage.innerHTML = `<img src="${L.esc(m.src)}" alt="">`;
    }
    const v = stage.querySelector('video');
    if (v) {
      v.addEventListener('error', () => zoomVideoFail(v));
      if (m.type === 'gif') { v.muted = true; const p = v.play(); if (p && p.catch) p.catch(() => {}); }
    }
    zoomPaint();
  }
  function openZoom(el) {
    const got = zoomUrlsFrom(el);
    zoom.items = got.items; zoom.urls = got.items.map(m => m.src); zoom.i = got.i; zoom.origin = got.origin;
    zoom.open = true; zoom.scale = 1; zoom.tx = 0; zoom.ty = 0;
    const view = $('#zoomView'); view.hidden = false; view.classList.add('on');
    zoomGo(zoom.i);
  }
  function closeZoom() {
    zoom.open = false; zoom.start = null;
    zoomStopMedia();
    const view = $('#zoomView'); view.classList.remove('on'); view.hidden = true;
    $('#zoomStage').innerHTML = '';
  }
  /** 触点落在原生播放控件（视频底部一条）或兜底链接上：交给浏览器，不当成滑动/关闭 */
  function zoomNativeTouch(ev) {
    const t = ev.target;
    if (t.closest && t.closest('.zoom-fail a, .yt-open a, .yt-frame')) return true;
    const v = t.closest && t.closest('.zoom-media.is-video video');
    if (!v || !ev.touches || !ev.touches.length) return false;
    const r = v.getBoundingClientRect();
    return ev.touches[0].clientY > r.bottom - 64;
  }
  function bindZoom() {
    const view = $('#zoomView'), stage = $('#zoomStage');
    $('#zoomPrev').onclick = ev => { ev.stopPropagation(); zoomGo(zoom.i - 1); };
    $('#zoomNext').onclick = ev => { ev.stopPropagation(); zoomGo(zoom.i + 1); };
    view.addEventListener('click', ev => { if (ev.target === view || ev.target === stage || ev.target === stage.querySelector('img') && zoom.scale <= 1) { /* tap handled in touchend */ } });
    $('#zoomClose').onclick = ev => { ev.stopPropagation(); closeZoom(); };
    view.addEventListener('touchstart', ev => {
      ev.stopPropagation();
      if (ev.target.closest && ev.target.closest('#zoomClose, .zoom-bar button')) { zoom.start = null; return; }
      if (zoomNativeTouch(ev)) { zoom.start = {mode: 'native'}; return; }
      const pts = ev.touches;
      if (pts.length === 2 && zoomCur().type === 'image') {
        const dx = pts[1].clientX - pts[0].clientX, dy = pts[1].clientY - pts[0].clientY;
        zoom.start = {mode: 'pinch', dist: Math.hypot(dx, dy), scale: zoom.scale, x: (pts[0].clientX + pts[1].clientX) / 2, y: (pts[0].clientY + pts[1].clientY) / 2, tx: zoom.tx, ty: zoom.ty};
      } else if (pts.length === 1) {
        zoom.start = {mode: 'drag', x: pts[0].clientX, y: pts[0].clientY, tx: zoom.tx, ty: zoom.ty, t0: performance.now(), moved: false,
          onMedia: !!(ev.target.closest && ev.target.closest('.zoom-media'))};
      }
    }, {passive: false});
    view.addEventListener('touchmove', ev => {
      ev.stopPropagation();
      if (zoom.start && zoom.start.mode === 'native') return;   // 拖进度条等原生操作
      ev.preventDefault();
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
        const tap = !s.moved || (Math.abs(dx) < 10 && Math.abs(dy) < 10 && dt < 350);
        if (tap && s.onMedia) return;   // 点在视频上：交给原生控件播放/暂停，不关闭
        if (tap) { closeZoom(); return; }
        if (dy > 80 && Math.abs(dy) > Math.abs(dx)) { closeZoom(); return; }
        if (Math.abs(dx) > 60 && zoom.items.length > 1) zoomGo(zoom.i + (dx < 0 ? 1 : -1));
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
    const zhit = t.closest('img[data-zoom], .media-grid .cell, .thumb .cell, .post-cover, .feed-row .thumb, .brow .thumb, .b-img');
    if (zhit && !zoom.open) {
      const cell = zhit.closest('[data-media-list] .cell') || (zhit.matches('[data-media-list]') ? zhit.querySelector('.cell') : null);
      const mel = cell && cell.querySelector('[data-media-i]');
      if (mel) { e.preventDefault(); e.stopPropagation(); openZoom(mel); return; }
      const img = zhit.matches && zhit.matches('img') ? zhit : zhit.querySelector('img[data-zoom], img');
      if (img && (img.dataset.zoom || img.src)) { e.preventDefault(); e.stopPropagation(); openZoom(img); return; }
    }
    const nav = t.closest('[data-nav]'); if (nav) { step(Number(nav.dataset.nav)); return; }
    const bb = t.closest('[data-b]');
    if (bb) { const k = bb.dataset.b; if (k === 'fav') onTab('favorites'); else if (k === 'filter') openDrop(); else if (k === 'next') nextPlat(); else if (k === 'all') openAllBloggers(); return; }
    const hotA = t.closest('.hot-list a'); if (hotA) { const li = hotA.closest('li'); if (li && li.dataset.hid) setRead(li.dataset.hid); return; }
    const orig = t.closest('[data-orig]');
    if (orig) { e.stopPropagation(); const box = $(`[data-orig-box="${CSS.escape(orig.dataset.orig)}"]`); if (box) { const on = box.classList.toggle('on'); orig.textContent = on ? '收起原文' : '看原文'; } return; }
    const dupT = t.closest('[data-dup-toggle]');
    if (dupT) { e.stopPropagation(); const box = dupT.closest('[data-dup]'); const listEl = box && box.querySelector('.dup-list'); if (listEl) { listEl.hidden = !listEl.hidden; dupT.setAttribute('aria-expanded', String(!listEl.hidden)); box.classList.toggle('on', !listEl.hidden); } return; }
    const dupR = t.closest('[data-dup-id]');
    if (dupR) { e.stopPropagation(); openItem(dupR.dataset.dupId); return; }
    const cmore = t.closest('[data-cmt-more]');
    if (cmore) { const sec = cmore.closest('[data-tg-comments]'); if (sec) sec.classList.remove('folded'); cmore.remove(); return; }
    const artOrig = t.closest('[data-art-orig]');
    if (artOrig) { const box = $('[data-art-orig-box]'); const on = box.classList.toggle('on'); artOrig.textContent = on ? '收起原文' : '看原文'; return; }
    const tab = t.closest('[data-hot]');
    if (tab) { hotActive = tab.dataset.hot; renderHotBody(); return; }
    const day = t.closest('[data-hot-day]');
    if (day) { pickHotDay(day.dataset.hotDay); return; }
    const r = t.closest('[data-retry]'); if (r) { ch[r.dataset.retry].error = null; loadMore(r.dataset.retry); return; }
    const sr = t.closest('[data-seg-retry]'); if (sr) { const i = Number(sr.dataset.segRetry); if (blSegs[i]) { blSegs[i].error = null; loadSeg(i); } return; }
    const pl = t.closest('#platChips [data-plat]'); if (pl) { pickPlat(pl.dataset.plat); return; }
    const pe = t.closest('[data-person]'); if (pe) { pickPerson(pe.dataset.platOf || plat, pe.dataset.person); return; }
    if (t.closest('a,button')) return;
    const card = t.closest('[data-id]');
    if (card && !card.closest('#articleBody')) openItem(card.dataset.id, {list: listContext(card)});
  }

  async function boot() {
    $$('.tabbar button').forEach(b => b.addEventListener('click', () => onTab(b.dataset.view)));
    bindTouch();
    bindZoom();
    $('#cardMenu').addEventListener('click', onMenu);
    $('#actSheet').addEventListener('click', onSheet);
    // 顶栏：点标题开/关下拉（频道 / 平台 / 日期）；点遮罩关
    $('#chBtn').addEventListener('click', () => { if (dropOpen()) closeDrop(); else openDrop(); });
    $('#dropMask').addEventListener('click', closeDrop);
    $('#dropList').addEventListener('click', e => {
      const b = e.target.closest('button'); if (!b) return;
      closeDrop();
      if (b.dataset.dropCh != null) { showView('channels'); jumpChannel(Number(b.dataset.dropCh)); }
      else if (b.dataset.dropPlat) pickPlat(b.dataset.dropPlat);
      else if (b.dataset.hotDay != null) pickHotDay(b.dataset.hotDay);
    });
    document.addEventListener('keydown', e => { if (e.key === 'Escape') { if (dropOpen()) closeDrop(); else if ($('#actSheet').classList.contains('on')) closeSheet(); } });
    // 正文底部浮条
    $('#dFont').onclick = openFont;
    $('#dFav').onclick = () => { const it = curItem(); if (it) toggleFav(it); };
    $('#dShare').onclick = () => { const it = curItem(); if (it) openShare(it); };
    $('#dCmt').onclick = () => { const it = curItem(); if (it) openComments(it); };
    $('#btnArtMore').onclick = () => { const it = curItem(); if (it) openArtMore(it); };
    $('#articleBody').addEventListener('scroll', () => { $('#artBar').classList.toggle('solid', $('#articleBody').scrollTop > 60); }, {passive: true});
    // 收藏 / 搜索模块自己渲染的列表也标已读
    if (window.MutationObserver) ['#view-favorites', '#search-panel'].forEach(sel => { const el = $(sel); if (el) new MutationObserver(() => markRead(el)).observe(el, {childList: true, subtree: true}); });
    // 收藏 / 搜索模块自己的列表（data-item-id）点开时，也带上「上一条/下一条」的列表
    document.addEventListener('click', e => {
      const row = e.target.closest('[data-item-id]');
      if (row && performance.now() >= suppressClickUntil) pendingList = listContext(row);
      else if (row) { e.preventDefault(); e.stopImmediatePropagation(); }
    }, true);
    // 两种翻法共用同一条长流，只是「左右」多了横滑换频道；切换不重建，位置不动
    $('#modeLR').onclick = () => { if (mode !== 'lr') { mode = 'lr'; localStorage.setItem(MKEY, mode); applyMode(); } closeDrop(); };
    $('#modeUD').onclick = () => { if (mode !== 'ud') { mode = 'ud'; localStorage.setItem(MKEY, mode); applyMode(); } closeDrop(); };
    $('#btnRefresh').onclick = doRefresh;
    $('#btnBack').onclick = () => closeArticle();
    document.querySelector('.app').addEventListener('click', onClick);
    $('#healthEntry').addEventListener('click', e => {
      if (e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
      e.preventDefault();
      openHealth();
    });
    $('#healthBody').addEventListener('click', filterHealth);
    $('#healthBack').onclick = leaveHealth;
    document.addEventListener('visibilitychange', () => { if (!document.hidden) updateHealthFreshness(); });
    setInterval(updateHealthFreshness, 60_000);
    $('#healthView').addEventListener('cancel', e => { e.preventDefault(); leaveHealth(); });
    const deepHealth = location.hash === HEALTH_HASH;
    const deep = L.parseItemHash(location.hash);
    const deepMore = (location.hash.match(/^#\/more\/(.+)$/) || [])[1];
    if (deepHealth && history.state && history.state.health) openHealth(true);
    else {
      if (!history.state || !history.state.home) history.replaceState({home: true}, '', location.pathname + location.search);
      if (deepHealth) openHealth();
    }
    const bootSeq = openSeq;
    try { await loadAll(false); } catch (e) {
      $('#channelRoot').innerHTML = `<p class="muted" style="padding:16px">数据没加载出来（${L.esc(e.message)}）。稍后点右上角刷新再试。</p>`;
      $('#app').removeAttribute('aria-busy'); return;
    }
    stampRefresh(new Date(builtAtMs()));
    const note = meta.note || (meta.fixture ? '这是用测试样例数据构建的页面，不是真实内容。' : '');
    if (note && sessionStorage.getItem(NOTE_KEY) !== note) {
      const box = $('#previewNote'); box.querySelector('span').textContent = note; box.hidden = false;
      box.querySelector('button').onclick = () => { box.hidden = true; sessionStorage.setItem(NOTE_KEY, note); };
    }
    renderChannels();
    $('#app').dataset.tab = currentView(); updateTopName();
    booted = true;
    ctx.searchButton = $('#btnSearch');
    if (registry.search) mountFeature('search');
    else $('#btnSearch').onclick = () => toast('搜索功能还没接入。');
    $('#app').removeAttribute('aria-busy');
    if (deep && openSeq === bootSeq) openItem(deep);
    else if (deepMore && openSeq === bootSeq) { try { openMoreLink(decodeURIComponent(deepMore)); } catch (e) { /* 坏链接就留在首页 */ } }
  }
  window.Rebang.openItem = (x) => openItem(x);
  window.Rebang.ctx = ctx;
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot); else boot();
})();
