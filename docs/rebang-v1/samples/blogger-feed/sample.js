/* 博主信息流样页渲染（纯静态，读 sample-data.js）。
   地址：feed.html?v=a|b（紧凑 / 大图）；&p=x 按平台筛；#u=a1 进某个博主的个人主页。
   交互约定沿用线上：博主页左右滑不做任何事（左右滑只在频道页换频道）；长按帖子 = 收藏 / 分享菜单；点头像或名字 = 个人主页。 */
(function () {
  const D = window.SAMPLE;
  const q = new URLSearchParams(location.search);
  const V = q.get('v') === 'b' ? 'b' : 'a';
  document.body.classList.add('v-' + V);
  const ICON_DIR = '../../../../web-v11/icons/';
  const P = {
    msg: '<path d="M2.992 16.342a2 2 0 0 1 .094 1.167l-1.065 3.29a1 1 0 0 0 1.236 1.168l3.413-.998a2 2 0 0 1 1.099.092 10 10 0 1 0-4.777-4.719"/>',
    rep: '<path d="m2 9 3-3 3 3"/><path d="M13 18H7a2 2 0 0 1-2-2V6"/><path d="m22 15-3 3-3-3"/><path d="M11 6h6a2 2 0 0 1 2 2v10"/>',
    heart: '<path d="M2 9.5a5.5 5.5 0 0 1 9.591-3.676.56.56 0 0 0 .818 0A5.49 5.49 0 0 1 22 9.5c0 2.29-1.5 4-3 5.5l-5.492 5.313a2 2 0 0 1-3 .019L5 15c-1.5-1.5-3-3.2-3-5.5"/>',
    bm: '<path d="M17 3a2 2 0 0 1 2 2v15a1 1 0 0 1-1.496.868l-4.512-2.578a2 2 0 0 0-1.984 0l-4.512 2.578A1 1 0 0 1 5 20V5a2 2 0 0 1 2-2z"/>',
    share: '<path d="M12 2v13"/><path d="m16 6-4-4-4 4"/><path d="M4 12v8a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-8"/>',
    dots: '<circle cx="12" cy="12" r="1"/><circle cx="19" cy="12" r="1"/><circle cx="5" cy="12" r="1"/>',
    search: '<path d="m21 21-4.34-4.34"/><circle cx="11" cy="11" r="8"/>',
    users: '<path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><path d="M16 3.128a4 4 0 0 1 0 7.744"/><path d="M22 21v-2a4 4 0 0 0-3-3.87"/><circle cx="9" cy="7" r="4"/>',
    news: '<path d="M15 18h-5"/><path d="M18 14h-8"/><path d="M4 22h16a2 2 0 0 0 2-2V4a2 2 0 0 0-2-2H8a2 2 0 0 0-2 2v16a2 2 0 0 1-4 0v-9a2 2 0 0 1 2-2h2"/><rect width="8" height="4" x="10" y="6" rx="1"/>',
    flame: '<path d="M12 3q1 4 4 6.5t3 5.5a1 1 0 0 1-14 0 5 5 0 0 1 1-3 1 1 0 0 0 5 0c0-2-1.5-3-1.5-5q0-2 2.5-4"/>',
    back: '<path d="m12 19-7-7 7-7"/><path d="M19 12H5"/>',
    ext: '<path d="M15 3h6v6"/><path d="M10 14 21 3"/><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/>',
    user: '<path d="M19 21v-2a4 4 0 0 0-4-4H9a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/>',
    filter: '<path d="M2 5h20"/><path d="M6 12h12"/><path d="M9 19h6"/>',
    play: '<path d="M6 4v16l14-8z"/>'
  };
  const ic = k => `<svg class="lucide" viewBox="0 0 24 24" aria-hidden="true">${P[k]}</svg>`;
  const esc = s => String(s == null ? '' : s).replace(/[&<>"']/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));
  const fmtN = n => !n ? '' : n >= 10000 ? (n / 10000).toFixed(1).replace(/\.0$/, '') + '万' : String(n);
  const plat = id => D.platforms.find(p => p.id === id) || {id, name: id};
  const pIcon = (id, cls = 'pico') => `<img class="${cls}" src="${ICON_DIR}${id}.svg" alt="${esc(plat(id).name)}">`;
  const av = (id, extra = '') => { const a = D.accounts[id]; return `<span class="av" style="--h:${a.hue}" data-u="${id}" ${extra}>${esc(a.name.replace(/^示例·/, '')[0])}</span>`; };
  const TAG = `<span class="sample-tag">样页 · ${V === 'a' ? 'A 紧凑版' : 'B 大图版'}</span>`;
  const atHandle = a => a.plat === 'x' ? '@' + a.handle : a.handle;

  function grid(n, hue, seed) {
    if (!n) return '';
    const show = V === 'b' && n > 4 ? 4 : n;
    const cls = V === 'b' && n > 4 ? 'nbig' : 'n' + Math.min(n, 9);
    let h = '';
    for (let i = 0; i < show; i++) {
      const extra = i === show - 1 && n > show ? `<span class="more-n">+${n - show}</span>` : '';
      h += `<div class="ph" style="--h:${(hue + seed * 37 + i * 23) % 360}" data-n="示例图 ${i + 1}">${extra}</div>`;
    }
    return `<div class="grid ${cls}">${h}</div>`;
  }
  function whoLine(a, id, time, small) {
    if (V === 'b' && !small) {
      return `<div class="who">${av(id)}<div class="lines"><div class="l1"><span class="nm" data-u="${id}">${esc(a.name)}</span></div>` +
        `<div class="l2">${pIcon(a.plat)}<span>${esc(plat(a.plat).name)}</span><span>·</span><span>${esc(time)}</span></div></div>` +
        `<button class="more" type="button" aria-label="更多" data-more>${ic('dots')}</button></div>`;
    }
    return `<div class="who">${small ? av(id) : ''}<span class="nm" data-u="${id}">${esc(a.name)}</span>${pIcon(a.plat)}` +
      `<span class="hd2">${esc(atHandle(a))}</span><span class="sep">·</span><span class="tm">${esc(time)}</span>` +
      (small ? '' : `<button class="more" type="button" aria-label="更多" data-more>${ic('dots')}</button>`) + '</div>';
  }
  function bodyHTML(text, id) {
    const long = text.length > 120 || (text.match(/\n/g) || []).length > 3;
    return `<div class="body${long ? ' fold' : ''}" data-body="${id}">${esc(text)}</div>` +
      (long ? `<button class="fold-btn" type="button" data-fold="${id}">全文</button>` : '');
  }
  function postHTML(p) {
    const a = D.accounts[p.acc];
    let m = '';
    if (p.title) m += `<div class="ttl">${esc(p.title)}</div>`;
    m += bodyHTML(p.text, p.id);
    if (p.mt) m += `<div class="mt"><span class="mt-badge">机器翻译</span><button class="orig-btn" type="button" data-orig="${p.id}">看原文</button></div><div class="orig" id="orig-${p.id}">${esc(p.orig)}</div>`;
    if (p.cover) m += `<div class="ph cover" style="--h:${a.hue}" data-n="示例封面"></div>`;
    m += grid(p.imgs, a.hue, p.id.length + Number(p.id.slice(1)));
    if (p.video) m += `<div class="vid"><div class="ph" style="--h:${a.hue}" data-n="示例视频封面"></div><span class="play"><i>${ic('play')}</i></span><span class="dur">${esc(p.video)}</span></div>`;
    if (p.quote) { const qa = D.accounts[p.quote.acc]; m += `<div class="quote" data-open="quote">${whoLine(qa, p.quote.acc, p.quote.time, true)}<div class="body">${esc(p.quote.text)}</div>${grid(p.quote.imgs, qa.hue, 3)}</div>`; }
    if (p.repost) { const ra = D.accounts[p.repost.acc]; m += `<div class="repost" data-open="repost"><div class="body"><span class="at" data-u="${p.repost.acc}">@${esc(ra.name)}</span>：${esc(p.repost.text)}</div>${grid(p.repost.imgs, ra.hue, 5)}</div>`; }
    const mt = p.metrics || {};
    const acts = V === 'b'
      ? `<div class="acts"><span>${ic('rep')}${fmtN(mt.repost) || '转发'}</span><span>${ic('msg')}${fmtN(mt.reply) || '评论'}</span><span>${ic('heart')}${fmtN(mt.like) || '赞'}</span><span>${ic('bm')}收藏</span></div>`
      : `<div class="acts"><span>${ic('msg')}${fmtN(mt.reply)}</span><span>${ic('rep')}${fmtN(mt.repost)}</span><span>${ic('heart')}${fmtN(mt.like)}</span><span class="r"><span>${ic('bm')}</span><span>${ic('share')}</span></span></div>`;
    if (V === 'b') return `<article class="post" data-id="${p.id}">${whoLine(a, p.acc, p.time)}${m}${acts}</article>`;
    return `<article class="post" data-id="${p.id}">${av(p.acc)}<div class="main">${whoLine(a, p.acc, p.time)}${m}${acts}</div></article>`;
  }
  const tabbar = `<nav class="tabbar" aria-label="底栏"><button type="button" data-tab="频道">${ic('news')}<b>频道</b></button><button type="button" class="on">${ic('users')}<b>博主</b></button><button type="button" data-tab="热搜">${ic('flame')}<b>热搜</b></button><button type="button" data-tab="收藏">${ic('bm')}<b>收藏</b></button></nav>`;

  function feedView(pf) {
    const posts = D.posts.filter(p => pf === 'all' || D.accounts[p.acc].plat === pf);
    const chips = [{id: 'all', name: '全部'}].concat(D.platforms).map(p =>
      `<button type="button" class="pchip${p.id === pf ? ' on' : ''}" data-plat="${p.id}">${p.id === 'all' ? '' : pIcon(p.id, '')}${esc(p.name)}</button>`).join('');
    const accs = Object.keys(D.accounts).filter(k => pf === 'all' || D.accounts[k].plat === pf);
    const stories = accs.map((k, i) => { const a = D.accounts[k]; return `<button type="button" class="story" data-u="${k}"><span class="avw">${av(k)}${i < 3 ? '<span class="dot"></span>' : ''}${pIcon(a.plat, 'pl')}</span><b>${esc(a.name.replace(/^示例·/, ''))}</b></button>`; }).join('');
    return `<div class="scroll" id="scroller"><header class="hd"><div class="hd-row"><h1>博主${TAG}</h1><button class="ibtn" type="button" aria-label="搜索博主">${ic('search')}</button><button class="ibtn" type="button" aria-label="全部博主">${ic('filter')}</button></div><div class="plats">${chips}</div></header>` +
      `<div class="stories">${stories}</div><div class="sec-gap"></div>` +
      `<div class="feed">${posts.map(postHTML).join('') || '<div class="end">这个平台暂时没有示例帖子</div>'}</div><div class="end">— 示例数据到底了 —</div></div>`;
  }
  function profileView(id, tab) {
    const a = D.accounts[id];
    let posts = D.posts.filter(p => p.acc === id);
    if (tab === 'img') posts = posts.filter(p => p.imgs || p.video || p.cover);
    return `<div class="scroll profile" id="scroller"><div class="cover-band">${TAG}<button class="back" type="button" aria-label="返回" data-back>${ic('back')}</button></div>` +
      `<div class="pf"><div class="pf-top">${av(id)}<button class="open-src" type="button">${ic('ext')}去${esc(plat(a.plat).name)}看主页</button></div>` +
      `<h2>${esc(a.name)}</h2><div class="handle">${pIcon(a.plat)}<span>${esc(plat(a.plat).name)} · ${esc(atHandle(a))}</span></div>` +
      `<p class="bio">${esc(a.bio)}</p><div class="stat"><span><b>${a.posts}</b>条已收录</span><span>最近更新 ${esc(a.last)}</span></div></div>` +
      `<div class="ptabs"><button type="button" class="${tab === 'img' ? '' : 'on'}" data-ptab="all">帖子</button><button type="button" class="${tab === 'img' ? 'on' : ''}" data-ptab="img">图片和视频</button></div>` +
      `<div class="feed">${posts.map(postHTML).join('') || '<div class="end">示例里这个博主没有这类帖子</div>'}</div><div class="end">— 示例数据到底了 —</div></div>`;
  }

  const app = document.getElementById('app');
  const state = {pf: q.get('p') || 'all', tab: 'all'};
  function render() {
    const m = location.hash.match(/u=(\w+)/);
    const u = m && D.accounts[m[1]] ? m[1] : null;
    app.innerHTML = (u ? profileView(u, state.tab) : feedView(state.pf)) + tabbar +
      '<div class="sheet" id="menu"><div class="box"><div class="handle"></div><div id="menuBody"></div></div></div><div class="toast" id="toast"></div>';
  }
  function toast(t) { const el = document.getElementById('toast'); el.textContent = t; el.classList.add('on'); clearTimeout(toast.t); toast.t = setTimeout(() => el.classList.remove('on'), 1800); }
  function openMenu(id) {
    const p = D.posts.find(x => x.id === id); const a = D.accounts[p.acc];
    document.getElementById('menuBody').innerHTML = `<div class="peek">${esc(a.name)}：${esc(p.title || p.text)}</div>` +
      `<button class="mi" type="button" data-mi="收藏">${ic('bm')}收藏</button><button class="mi" type="button" data-mi="分享">${ic('share')}分享</button>` +
      `<button class="mi" type="button" data-mi="u" data-u="${p.acc}">${ic('user')}看 ${esc(a.name)} 的主页</button><button class="mi" type="button" data-mi="原文">${ic('ext')}打开原文</button>`;
    document.getElementById('menu').classList.add('on');
  }
  const closeMenu = () => document.getElementById('menu').classList.remove('on');
  window.__openMenu = openMenu;   // 截图脚本用

  // 长按 500ms 出菜单；手指移动超过 10px 视为滚动，取消
  let lp = null;
  app.addEventListener('pointerdown', e => {
    const post = e.target.closest('.post'); if (!post || e.target.closest('button,[data-u]')) return;
    const x = e.clientX, y = e.clientY;
    post.classList.add('pressing');
    lp = {post, x, y, fired: false, t: setTimeout(() => { lp.fired = true; post.classList.remove('pressing'); openMenu(post.dataset.id); }, 500)};
  });
  const cancelLp = () => { if (lp) { clearTimeout(lp.t); lp.post.classList.remove('pressing'); } };
  app.addEventListener('pointermove', e => { if (lp && Math.hypot(e.clientX - lp.x, e.clientY - lp.y) > 10) { cancelLp(); lp = null; } });
  app.addEventListener('pointerup', cancelLp);
  app.addEventListener('pointercancel', () => { cancelLp(); lp = null; });
  app.addEventListener('contextmenu', e => { if (e.target.closest('.post')) e.preventDefault(); });

  app.addEventListener('click', e => {
    const t = e.target;
    if (lp && lp.fired) { lp = null; return; }
    lp = null;
    if (t.closest('#menu') && !t.closest('.box')) return closeMenu();
    const mi = t.closest('[data-mi]');
    if (mi) { closeMenu(); if (mi.dataset.mi === 'u') { location.hash = 'u=' + mi.dataset.u; return; } return toast(mi.dataset.mi === '原文' ? '样页：这里会打开原帖链接' : `样页：已${mi.dataset.mi}（只存本机）`); }
    const more = t.closest('[data-more]'); if (more) return openMenu(more.closest('.post').dataset.id);
    const u = t.closest('[data-u]'); if (u) { state.tab = 'all'; location.hash = 'u=' + u.dataset.u; return; }
    if (t.closest('[data-back]')) { history.length > 1 ? history.back() : (location.hash = ''); return; }
    const pc = t.closest('[data-plat]'); if (pc) { state.pf = pc.dataset.plat; render(); return; }
    const pt = t.closest('[data-ptab]'); if (pt) { state.tab = pt.dataset.ptab; const y = document.getElementById('scroller').scrollTop; render(); document.getElementById('scroller').scrollTop = y; return; }
    const fb = t.closest('[data-fold]');
    if (fb) { const b = app.querySelector(`[data-body="${fb.dataset.fold}"]`); const open = b.classList.toggle('fold'); fb.textContent = open ? '全文' : '收起'; return; }
    const ob = t.closest('[data-orig]');
    if (ob) { const o = document.getElementById('orig-' + ob.dataset.orig); ob.textContent = o.classList.toggle('on') ? '收起原文' : '看原文'; return; }
    if (t.closest('[data-tab]')) return toast(`样页：这里切到「${t.closest('[data-tab]').dataset.tab}」`);
    if (t.closest('.ph')) return toast('样页：点图进大图浏览（沿用现有大图查看）');
    if (t.closest('[data-open]')) return toast('样页：点卡片进被引用 / 被转发的原帖');
    if (t.closest('.post')) return toast('样页：点帖子进正文页（沿用现有正文页）');
  });
  window.addEventListener('hashchange', () => { render(); document.getElementById('scroller').scrollTop = 0; });
  render();
})();
