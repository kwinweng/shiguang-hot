/* Static published documents only. No ingestion runs in the browser. */
'use strict';
const Modules = (() => {
  const defaultTab = 'feed';
  const focusDay = (now = new Date()) => {
    const beijing = new Date(+now + 8 * 3600000);
    if (beijing.getUTCHours() < 22) beijing.setUTCDate(beijing.getUTCDate() - 1);
    return beijing.toISOString().slice(0, 10);
  };
  const addedCount = (before, after) => {
    const old = new Set(before.map(r => r.id));
    return new Set(after.filter(r => !old.has(r.id)).map(r => r.id)).size;
  };
  const notFoundLabel = '回到资讯';
  const distinctSummary = (title, summary) => {
    const normalize = value => String(value || '').normalize('NFKC').replace(/[\p{P}\p{Z}\s]/gu, '').toLowerCase();
    const a = normalize(title), b = normalize(summary);
    if (!b || a === b) return '';
    if (a && (a.includes(b) || b.includes(a)) && Math.min(a.length,b.length)/Math.max(a.length,b.length) >= .85) return '';
    const pairs = value => new Set(Array.from({length:Math.max(0,value.length-1)}, (_,i)=>value.slice(i,i+2)));
    const x = pairs(a), y = pairs(b);
    const same = [...x].filter(pair=>y.has(pair)).length;
    return x.size+y.size && 2*same/(x.size+y.size) >= .9 ? '' : summary;
  };
  const LAST_SEEN_KEY = 'rebang.lastSeen';
  const channelOf = r => String(r?.source_name || r?.source || '').trim();
  const newestByChannel = rows => {
    const map = new Map();
    for (const r of rows || []) {
      const ch = channelOf(r);
      const ms = Date.parse(r?.time || '');
      if (!ch || !Number.isFinite(ms)) continue;
      const prev = map.get(ch);
      if (!prev || ms > prev.ms) map.set(ch, {ms, iso:r.time});
    }
    return map;
  };
  const seedLastSeen = (rows, existing) => {
    const out = existing && typeof existing === 'object' ? {...existing} : {};
    const newest = newestByChannel(rows);
    let idx = 0;
    for (const [ch, info] of newest.entries()) {
      if (!out[ch] || !Number.isFinite(Date.parse(out[ch]))) {
        out[ch] = idx % 3 === 2 ? info.iso : new Date(info.ms - ((idx % 3) + 1) * 3 * 3600000).toISOString();
      }
      idx++;
    }
    return out;
  };
  const unreadCount = (rows, ch, lastSeen) => {
    if (!ch || !lastSeen || typeof lastSeen !== 'object') return 0;
    const seenMs = Date.parse(lastSeen[ch] || '');
    if (!Number.isFinite(seenMs)) return 0;
    let count = 0;
    for (const r of rows || []) {
      if (channelOf(r) === ch && Date.parse(r?.time || '') > seenMs) count++;
    }
    return count;
  };
  const categoryChannels = (rows, cat, filterFn) => {
    if (!cat || cat === '全部') return [];
    const filtered = typeof filterFn === 'function' ? filterFn(rows || [], cat) : (rows || []);
    const seen = new Set(), list = [];
    for (const r of filtered) {
      const ch = channelOf(r);
      if (ch && !seen.has(ch)) { seen.add(ch); list.push(ch); }
    }
    return list;
  };
  const categoryUnreadTotal = (rows, cat, lastSeen, filterFn) =>
    categoryChannels(rows, cat, filterFn).reduce((sum, ch) => sum + unreadCount(rows, ch, lastSeen), 0);
  const markChannelSeen = (rows, ch, lastSeen) => {
    const out = lastSeen && typeof lastSeen === 'object' ? {...lastSeen} : {};
    const info = newestByChannel(rows).get(ch);
    out[ch] = info ? info.iso : new Date().toISOString();
    return out;
  };
  return {
    defaultTab, focusDay, addedCount, notFoundLabel, distinctSummary,
    LAST_SEEN_KEY, channelOf, seedLastSeen, unreadCount, categoryChannels, categoryUnreadTotal, markChannelSeen
  };
})();
if (typeof module !== 'undefined') module.exports = Modules;
if (typeof document !== 'undefined') (() => {
  // Same locally embedded Phosphor paths as the approved prototype.
  Object.assign(window.ICONS, {
    'gear-six_line':"<svg viewBox=\"0 0 256 256\" fill=\"currentColor\" aria-hidden=\"true\"><path d=\"M128,80a48,48,0,1,0,48,48A48.05,48.05,0,0,0,128,80Zm0,80a32,32,0,1,1,32-32A32,32,0,0,1,128,160Zm109.94-52.79a8,8,0,0,0-3.89-5.4l-29.83-17-.12-33.62a8,8,0,0,0-2.83-6.08,111.91,111.91,0,0,0-36.72-20.67,8,8,0,0,0-6.46.59L128,41.85,97.88,25a8,8,0,0,0-6.47-.6A112.1,112.1,0,0,0,54.73,45.15a8,8,0,0,0-2.83,6.07l-.15,33.65-29.83,17a8,8,0,0,0-3.89,5.4,106.47,106.47,0,0,0,0,41.56,8,8,0,0,0,3.89,5.4l29.83,17,.12,33.62a8,8,0,0,0,2.83,6.08,111.91,111.91,0,0,0,36.72,20.67,8,8,0,0,0,6.46-.59L128,214.15,158.12,231a7.91,7.91,0,0,0,3.9,1,8.09,8.09,0,0,0,2.57-.42,112.1,112.1,0,0,0,36.68-20.73,8,8,0,0,0,2.83-6.07l.15-33.65,29.83-17a8,8,0,0,0,3.89-5.4A106.47,106.47,0,0,0,237.94,107.21Zm-15,34.91-28.57,16.25a8,8,0,0,0-3,3c-.58,1-1.19,2.06-1.81,3.06a7.94,7.94,0,0,0-1.22,4.21l-.15,32.25a95.89,95.89,0,0,1-25.37,14.3L134,199.13a8,8,0,0,0-3.91-1h-.19c-1.21,0-2.43,0-3.64,0a8.08,8.08,0,0,0-4.1,1l-28.84,16.1A96,96,0,0,1,67.88,201l-.11-32.2a8,8,0,0,0-1.22-4.22c-.62-1-1.23-2-1.8-3.06a8.09,8.09,0,0,0-3-3.06l-28.6-16.29a90.49,90.49,0,0,1,0-28.26L61.67,97.63a8,8,0,0,0,3-3c.58-1,1.19-2.06,1.81-3.06a7.94,7.94,0,0,0,1.22-4.21l.15-32.25a95.89,95.89,0,0,1,25.37-14.3L122,56.87a8,8,0,0,0,4.1,1c1.21,0,2.43,0,3.64,0a8.08,8.08,0,0,0,4.1-1l28.84-16.1A96,96,0,0,1,188.12,55l.11,32.2a8,8,0,0,0,1.22,4.22c.62,1,1.23,2,1.8,3.06a8.09,8.09,0,0,0,3,3.06l28.6,16.29A90.49,90.49,0,0,1,222.9,142.12Z\"/></svg>",
    'user-circle_line':'<svg viewBox="0 0 256 256" fill="currentColor" aria-hidden="true"><path d="M128,24A104,104,0,1,0,232,128,104.11,104.11,0,0,0,128,24ZM74.08,197.5a64,64,0,0,1,107.84,0,87.83,87.83,0,0,1-107.84,0ZM96,120a32,32,0,1,1,32,32A32,32,0,0,1,96,120Zm97.76,66.41a79.66,79.66,0,0,0-36.06-28.75,48,48,0,1,0-59.4,0,79.66,79.66,0,0,0-36.06,28.75,88,88,0,1,1,131.52,0Z"/></svg>',
    'user-circle_fill':'<svg viewBox="0 0 256 256" fill="currentColor" aria-hidden="true"><path d="M172,120a44,44,0,1,1-44-44A44.05,44.05,0,0,1,172,120Zm60,8A104,104,0,1,1,128,24,104.11,104.11,0,0,1,232,128Zm-16,0a88.09,88.09,0,0,0-91.47-87.93C77.43,41.89,39.87,81.12,40,128.25a87.65,87.65,0,0,0,22.24,58.16A79.71,79.71,0,0,1,84,165.1a4,4,0,0,1,4.83.32,59.83,59.83,0,0,0,78.28,0,4,4,0,0,1,4.83-.32,79.71,79.71,0,0,1,21.79,21.31A87.62,87.62,0,0,0,216,128Z"/></svg>'
  });
  const {escape:e, safe, icon, categories, icons, filter} = News;
  const main = document.getElementById('news');
  const status = document.getElementById('refresh-status');
  const storage = {
    get(key, fallback) { try { return JSON.parse(localStorage.getItem(key)) ?? fallback; } catch { return fallback; } },
    set(key, value) { try { localStorage.setItem(key, JSON.stringify(value)); } catch { /* Storage can be unavailable in private browsing. */ } }
  };
  const bookmarkKey = document.body?.dataset?.bookmarkScope === 'private' ? 'shiguang-favorites-private' : 'shiguang-favorites-public';
  let favorites = storage.get(bookmarkKey, []);
  if (!Array.isArray(favorites)) favorites = [];
  favorites = favorites.filter(r=>r && typeof r.id==='string' && typeof r.title==='string').map(r=>({
    ...r, link:r.link||r.url||'', source_name:r.source_name||r.source||'', summary:r.summary||r.snippet||''
  }));
  const isSaved = r => favorites.some(f=>f.id===r.id || (r.link && f.link===r.link && f.title===r.title));
  const cache = new Map();
  let generation = 0, refreshing = false, visible = [], startY = null, distance = 0, renderedFocusDay = null;
  let groupSheetOpen = false, datePickerOpen = false, lastLiveMessages = [];
  let lastSeen = storage.get(Modules.LAST_SEEN_KEY, null);
  let swipeStart = null;
  const skeleton = '<div class="skeleton" aria-label="加载中"></div>'.repeat(4);
  const load = async (path, fresh = false) => {
    if (!fresh && cache.has(path)) return cache.get(path);
    try {
      const response = await fetch(path, {cache:fresh ? 'no-store' : 'default'});
      if (!response.ok) throw new Error('数据暂时无法读取');
      const value = await response.json();
      cache.set(path, value);
      storage.set('rebang-cache:' + path, value);
      return value;
    } catch (error) {
      const saved = cache.get(path) || storage.get('rebang-cache:' + path, null);
      if (saved && !navigator.onLine) return saved;
      throw error;
    }
  };
  const back = (to = '#me', label = '返回') => `<a class="back" href="${e(to)}">${icon('arrow-left')}${e(label)}</a>`;
  const heading = title => `<div class="ph"><h1>${e(title)}</h1></div>`;
  const tabs = (items, selected) => `<nav class="seg" aria-label="${selected.startsWith('explore') ? '探索' : '资讯'}标签">${items.map(([path, name]) => `<a href="#${path}" ${path === selected ? 'aria-current="page"' : ''}>${name}</a>`).join('')}</nav>`;
  const newsTabs = selected => heading('资讯') + tabs([['feed','实时'],['focus','热点'],['review','回顾']], selected);
  const empty = text => `<div class="empty">${e(text)}</div>`;
  const notFound = () => empty('404 · 这个页面不存在') + `<a class="btn pri" href="#feed">${Modules.notFoundLabel}</a>`;
  const row = r => {
    const live = !r.section;
    const summary = Modules.distinctSummary(r.title, r.summary);
    return `<a class="row c${live?' live-row':''}" data-id="${e(r.id)}" href="#message/${encodeURIComponent(r.id)}?from=${encodeURIComponent(location.hash || '#feed')}"><div class="tx">${live?`<div class="meta">${[r.source_name,r.category,r.time?.slice(11,16)].filter(Boolean).map(e).join(' · ')}</div>`:`<span class="cc">${e(r.category)}</span>`}<b>${e(r.title.trim())}</b>${summary?`<p>${e(summary)}</p>`:''}${live?'':`<small>${e(r.time?.slice(0,16).replace('T',' ') || r.day)}${r.location ? ' · ' + e(r.location) : ''}</small>`}</div>${r.image ? `<img loading="lazy" src="${e(r.image)}" alt="">` : ''}</a>`;
  };
  const list = rows => rows.map(row).join('') || empty('暂无内容');
  const focusRows = rows => rows.map(r => `<details class="focus-row" data-id="${e(r.id)}"><summary><span class="cc">${e(r.category)}</span><span>${e(r.title)}</span>${icon('caret-down')}</summary><div class="focus-body"><p>${e(r.summary)}</p><small>来源：${e(r.source_name)}</small>${safe(r.link) ? `<a class="ext" href="${safe(r.link)}" target="_blank" rel="noopener noreferrer">打开原文</a>` : ''}<button class="btn" data-save="${e(r.id)}">${isSaved(r) ? '取消收藏' : '收藏'}</button></div></details>`).join('') || empty('这一天没有热点');
  const controls = (cat, count, allRows = [], activeCh = '') => {
    const flt = `<div class="flt" aria-label="按分类筛选">${categories.map((name,i) => `<button data-category="${name}" aria-label="${name}" aria-pressed="${cat===name}" class="${cat===name?'on':''}">${icon(icons[i],cat===name)}<span>${name}${i===0?' '+count:''}</span></button>`).join('')}</div>`;
    if (!cat || cat === '全部') return `<div class="filters">${flt}</div>`;
    const totalUnread = Modules.categoryUnreadTotal(allRows, cat, lastSeen, filter);
    const tag = activeCh ? `<span class="channel-tag"><span class="channel-tag-name">${e(activeCh)}</span><button type="button" class="channel-tag-clear" aria-label="清除频道筛选">${icon('x')}</button></span>` : '';
    const dot = totalUnread > 0 ? `<span class="group-dot">${totalUnread > 99 ? '99+' : totalUnread}</span>` : '';
    const btn = `<button type="button" class="group-btn${activeCh ? ' on' : ''}" aria-label="选择群组${totalUnread > 0 ? `，${totalUnread} 条未读` : ''}" aria-haspopup="dialog" aria-expanded="${groupSheetOpen ? 'true' : 'false'}">${icon('users-three', Boolean(activeCh))}<span>群组</span>${dot}</button>`;
    return `<div class="filters">${flt}<div class="filter-actions">${tag}${btn}</div></div>`;
  };
  const renderGroupSheet = (cat, allRows, activeCh) => {
    const channels = Modules.categoryChannels(allRows, cat, filter);
    return `<div class="overlay" data-overlay="group"><div class="sheet group-sheet" role="dialog" aria-modal="true" aria-label="${e(cat)} · 群组"><div class="sheet-header"><span>${e(cat)} · 群组</span><button type="button" class="sheet-close" aria-label="关闭">${icon('x')}</button></div><div class="sheet-body">${channels.map(c => {
      const u = Modules.unreadCount(allRows, c, lastSeen);
      return `<button type="button" class="group-option${activeCh === c ? ' on' : ''}" data-ch="${e(c)}"><span class="group-option-name">${e(c)}</span>${u > 0 ? `<span class="unread-badge" aria-label="${u} 条未读">${u}</span>` : ''}</button>`;
    }).join('')}</div></div></div>`;
  };
  const getRoute = () => {
    const [path, q = ''] = (location.hash.slice(1) || (main.dataset.notFound ? '404' : Modules.defaultTab)).split('?');
    return {path, parts:path.split('/'), query:new URLSearchParams(q)};
  };
  const beijingToday = () => new Date(Date.now()+8*3600000).toISOString().slice(0,10);
  const dateLabel = day => `${Number(day.slice(5,7))}月${Number(day.slice(8))}日`;
  const reviewNav = (day, days) => {
    const today = beijingToday();
    const yesterday = new Date(Date.parse(today)-86400000).toISOString().slice(0,10);
    const all = [...new Set([...days, today, yesterday, day])].filter(d=>d<=today).sort().reverse();
    return `<div class="review-bar"><nav class="date-strip" aria-label="回顾日期">${all.map(d=>`<a href="#review/${d}" ${d===day?'aria-current="date"':''}>${d===today?'今天':d===yesterday?'昨天':dateLabel(d)}</a>`).join('')}</nav><button type="button" class="calendar-btn" aria-label="选择日期" aria-haspopup="dialog" aria-expanded="${datePickerOpen ? 'true' : 'false'}">${icon('calendar-blank')}</button></div>`;
  };
  const renderDatePicker = (day, days) => {
    const today = beijingToday();
    const anchor = [...new Set([...(days || []), today, day])].filter(d => d <= today).sort().at(-1) || today;
    const anchorMs = Date.parse(anchor + 'T00:00:00Z');
    const available = new Set(days || []);
    const windowDays = [];
    for (let i = 89; i >= 0; i--) windowDays.push(new Date(anchorMs - i * 86400000).toISOString().slice(0, 10));
    const months = new Map();
    for (const d of windowDays) {
      const ym = d.slice(0, 7);
      if (!months.has(ym)) months.set(ym, []);
      months.get(ym).push(d);
    }
    const monthBlocks = [...months.entries()].reverse().map(([ym, list]) => {
      const [y, m] = ym.split('-').map(Number);
      const firstDow = new Date(Date.UTC(y, m - 1, Number(list[0].slice(8)))).getUTCDay();
      const blanks = '<span class="date-blank"></span>'.repeat(firstDow);
      const cells = list.map(d => {
        const has = available.has(d);
        return `<button type="button" class="date-day${has ? ' has-snapshot' : ''}${d === day ? ' on' : ''}" data-date="${d}" ${has ? '' : 'disabled'}>${Number(d.slice(8))}</button>`;
      }).join('');
      return `<div class="date-picker-month">${y}年${m}月</div><div class="date-grid">${['日','一','二','三','四','五','六'].map(w => `<span class="date-weekday">${w}</span>`).join('')}${blanks}${cells}</div>`;
    }).join('');
    return `<div class="overlay" data-overlay="date"><div class="sheet date-picker" role="dialog" aria-modal="true" aria-label="选择日期"><div class="sheet-header"><span>选择日期 · 近 90 天</span><button type="button" class="sheet-close" aria-label="关闭">${icon('x')}</button></div><div class="sheet-body">${monthBlocks}</div></div></div>`;
  };
  const themeButton = document.getElementById('theme');
  const applyTheme = explicit => {
    const pref = explicit || storage.get('rebang-theme', 'system');
    const theme = pref === 'system' ? (matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light') : pref;
    document.documentElement.dataset.theme = theme;
    if (themeButton) {
      const dark = theme === 'dark';
      const label = dark ? '切换到浅色模式' : '切换到深色模式';
      themeButton.innerHTML = icon(dark ? 'sun' : 'moon');
      themeButton.setAttribute('aria-label', label);
      themeButton.setAttribute('title', label);
    }
  };
  async function route(fresh = false, keepPosition = false) {
    const current = ++generation;
    const {path, parts, query} = getRoute();
    const oldVisible = visible;
    let rows = [], html = '', area = 'news';
    main.setAttribute('aria-busy', 'true');
    if (!fresh) status.textContent = '';
    if (!keepPosition) main.innerHTML = skeleton;
    try {
      if (parts[0] === 'feed' || parts[0] === 'today') {
        const live = await load('data/live.json', fresh);
        lastLiveMessages = live.messages || [];
        const seeded = Modules.seedLastSeen(lastLiveMessages, lastSeen);
        if (JSON.stringify(seeded) !== JSON.stringify(lastSeen)) {
          lastSeen = seeded;
          storage.set(Modules.LAST_SEEN_KEY, lastSeen);
        }
        const cat = query.get('category') || '全部';
        const ch = cat !== '全部' ? (query.get('channel') || '') : '';
        const catRows = filter(lastLiveMessages, cat);
        rows = ch ? catRows.filter(r => Modules.channelOf(r) === ch) : catRows;
        html = newsTabs('feed') + controls(cat, lastLiveMessages.length, lastLiveMessages, ch) + `<p class="sub">${e(live.updated.slice(0,16).replace('T',' '))} 更新</p>` + list(rows);
        if (groupSheetOpen && cat !== '全部') html += renderGroupSheet(cat, lastLiveMessages, ch);
      } else if (parts[0] === 'focus') {
        const doc = await load('data/focus.json', fresh);
        const day = Modules.focusDay();
        renderedFocusDay = day;
        rows = doc.days[day] || [];
        const before = day !== beijingToday();
        html = newsTabs('focus') + `<p class="sub">${dateLabel(day)}${before?'的热点 · 今晚 22:00 更新':' 22:00 日报'}</p>` + focusRows(rows);
      } else if (['review','history','day'].includes(parts[0])) {
        const index = await load('history/index.json', fresh);
        const day = /^\d{4}-\d{2}-\d{2}$/.test(parts[1] || '') ? parts[1] : index.days.at(-1) || beijingToday();
        html = newsTabs('review') + reviewNav(day, index.days);
        if (index.days.includes(day)) {
          const doc = await load(`history/${day}.json`, fresh);
          rows = doc.messages;
          html += doc.events.map(event => `<details class="review-event"><summary>${e(event.title)}</summary><p>${e(event.summary)}</p><small>${event.source_count} 个来源</small>${list(event.messages)}</details>`).join('') || empty('这一天没有热点');
        } else html += empty(day === beijingToday() ? '00:30 后生成' : '这一天暂无回顾');
        if (datePickerOpen) html += renderDatePicker(day, index.days);
      } else if (parts[0] === 'explore') {
        area = 'explore';
        const section = ['play','kan','buy'].includes(parts[1]) ? parts[1] : 'play';
        const doc = await load('data/explore.json', fresh);
        const own = doc.messages.filter(r=>r.section===section);
        const cats = [...new Set(own.map(r=>r.category))];
        rows = own.filter(r=>!query.get('category') || r.category===query.get('category'));
        html = heading('探索') + tabs([['explore/play','好玩'],['explore/kan','好看'],['explore/buy','好买']], 'explore/'+section);
        if (cats.length) html += `<div class="chips">${['',...cats].map(c=>`<button data-category="${e(c)}" aria-pressed="${(query.get('category')||'')===c}">${e(c||'全部')}</button>`).join('')}</div>`;
        html += rows.length ? list(rows) : own.length ? `<div class="empty">${icon('squares-four')}<h2>这个分类这期没有</h2><p>换个分类，或者看全部。</p><a class="empty-action" href="#explore/${section}">看全部</a></div>` : `<div class="empty">${icon(({play:'compass',kan:'television-simple',buy:'shopping-bag'})[section])}<h2>${({play:'今天还没挑到好玩的',kan:'今天还没挑到好看的',buy:'今天还没挑到值得买的'})[section]}</h2><p>每期内容挑好后一起更新。</p><a class="empty-action" href="#feed">先去看资讯</a></div>`;
      } else if (parts[0] === 'me') {
        area = 'me';
        html = heading('我的') + `<div class="me-list"><a href="#favorites">${icon('bookmark-simple')}收藏 <small>${favorites.length} 条</small>${icon('caret-right')}</a><a href="#settings">${icon('gear-six')}设置<small>${({system:'跟随系统',light:'亮色',dark:'暗色'})[storage.get('rebang-theme','system')]||'跟随系统'}</small>${icon('caret-right')}</a><a href="#about">${icon('info')}关于<small>v0.3</small>${icon('caret-right')}</a></div><p class="foot">不需要登录，收藏只存在这台设备上</p>`;
      } else if (parts[0] === 'favorites') {
        area = 'me'; rows = favorites;
        html = back() + heading('收藏') + (rows.length ? list(rows) : empty('还没收藏')+'<a class="btn" href="#explore/play">去逛探索</a>');
      } else if (parts[0] === 'settings') {
        area = 'me';
        html = back() + heading('设置') + '<p class="sub">只存在这台设备上</p><h2 class="sh">主题</h2><div class="options">' + [['system','跟随系统'],['light','亮色'],['dark','暗色']].map(([v,n])=>`<button data-theme-choice="${v}" aria-pressed="${storage.get('rebang-theme','system')===v}">${n}</button>`).join('') + '</div>';
      } else if (parts[0] === 'about') {
        area = 'me';
        html = back() + `<div class="about"><img src="favicon.svg" alt="拾光热榜 Logo D"><h1>拾光热榜</h1><p class="sub">版本 0.3</p></div><h2 class="sh">数据多久更新</h2><p>实时流 · 每 30 分钟<br>热点 · 每天 22:00 日报后<br>回顾 · 次日 00:30<br>探索 · 每期编好后更新</p><a class="btn" href="#sources">查看全部来源</a>`;
      } else if (parts[0] === 'sources' || parts[0] === 'source') {
        const doc = await load('data/sources.json', fresh);
        const source = doc.sources.find(s=>s.id===parts[1]);
        if (parts[0]==='source' && !source) html = notFound();
        else if (source) { rows=source.messages; html=back('#sources','来源')+heading(source.name)+list(rows); }
        else html = back('#about','关于')+heading('来源')+doc.sources.map(s=>`<a class="stat" href="#source/${e(s.id)}"><span>${e(s.name)} · 今天 ${s.today_count} 条 · 近7天 ${s.seven_day_count} 条</span>${icon('caret-right')}</a>`).join('');
      } else if (parts[0] === 'message') {
        const [sourceDoc, explore] = await Promise.all([load('data/sources.json',fresh),load('data/explore.json',fresh)]);
        const id = decodeURIComponent(parts[1] || '');
        let r = [...explore.messages,...sourceDoc.sources.flatMap(s=>s.messages),...favorites].find(r=>r.id===id);
        if (!r) {
          const index = await load('history/index.json',fresh);
          const day = index.message_days?.[id];
          if (day) r = (await load(`history/${day}.json`,fresh)).messages.find(r=>r.id===id);
        }
        if (!r) html=empty('这条内容找不到了')+back('#feed','返回资讯');
        else {
          rows=[r]; area=r.section?'explore':'news';
          const from = /^#(feed|focus|review|explore|favorites|source)(\/|\?|$)/.test(query.get('from') || '') ? query.get('from') : '#feed';
          html=back(from,'返回列表')+`<article class="dt"><small>${e(r.category)} · ${e(r.source_name)}</small><h1>${e(r.title)}</h1>${r.image?`<img src="${e(r.image)}" alt="">`:''}<p>${e(r.text||r.summary)}</p><button class="btn" data-save="${e(r.id)}">${isSaved(r)?'取消收藏':'收藏'}</button>${safe(r.link)?`<a class="btn pri" href="${safe(r.link)}" target="_blank" rel="noopener noreferrer">打开原文 ${icon('arrow-square-out')}</a>`:''}</article>`;
        }
      } else html=notFound();
      if (current !== generation) return false;
      visible=rows;
      main.innerHTML=(!navigator.onLine?'<div class="offline">没有网络，显示缓存的内容</div>':'')+html;
      document.querySelectorAll?.('[data-nav]').forEach(a=>{
        const active=a.dataset.nav===area;
        if (active) a.setAttribute('aria-current','page'); else a.removeAttribute('aria-current');
        a.innerHTML=icon(({news:'newspaper',explore:'compass',me:'user-circle'})[a.dataset.nav],active)+({news:'资讯',explore:'探索',me:'我的'})[a.dataset.nav];
      });
      main.querySelectorAll?.('img').forEach(img=>img.onerror=()=>img.remove());
      main.querySelectorAll?.('[data-category]').forEach(button=>button.onclick=()=>{
        groupSheetOpen=false;
        query.delete('channel');
        query.set('category',button.dataset.category);
        location.hash=path+'?'+query;
      });
      const groupBtn=main.querySelector?.('.group-btn');
      if (groupBtn) groupBtn.onclick=()=>{groupSheetOpen=!groupSheetOpen;route(false,true);};
      main.querySelectorAll?.('.group-option[data-ch]').forEach(button=>button.onclick=()=>{
        const ch=button.dataset.ch;
        lastSeen=Modules.markChannelSeen(lastLiveMessages,ch,lastSeen);
        storage.set(Modules.LAST_SEEN_KEY,lastSeen);
        groupSheetOpen=false;
        query.set('channel',ch);
        const nextHash=path+'?'+query;
        if (location.hash==='#'+nextHash) route(false,true);
        else location.hash=nextHash;
      });
      const clearBtn=main.querySelector?.('.channel-tag-clear');
      if (clearBtn) clearBtn.onclick=()=>{
        groupSheetOpen=false;
        query.delete('channel');
        const qs=query.toString();
        const nextHash=path+(qs?'?'+qs:'');
        if (location.hash==='#'+nextHash) route(false,true);
        else location.hash=nextHash;
      };
      const calBtn=main.querySelector?.('.calendar-btn');
      if (calBtn) calBtn.onclick=()=>{datePickerOpen=!datePickerOpen;route(false,true);};
      main.querySelectorAll?.('.date-day[data-date]').forEach(button=>button.onclick=()=>{
        if (button.disabled) return;
        datePickerOpen=false;
        const nextHash='review/'+button.dataset.date;
        if (location.hash==='#'+nextHash) route(false,true);
        else location.hash=nextHash;
      });
      main.querySelectorAll?.('.sheet-close').forEach(button=>button.onclick=()=>{
        groupSheetOpen=false;datePickerOpen=false;route(false,true);
      });
      main.querySelectorAll?.('.overlay').forEach(overlay=>overlay.onclick=event=>{
        if (event.target===overlay) { groupSheetOpen=false;datePickerOpen=false;route(false,true); }
      });
      main.querySelectorAll?.('[data-theme-choice]').forEach(button=>button.onclick=()=>{storage.set('rebang-theme',button.dataset.themeChoice);applyTheme();route();});
      main.querySelectorAll?.('[data-save]').forEach(button=>button.onclick=()=>{
        const r=rows.find(r=>r.id===button.dataset.save);
        if (isSaved(r)) favorites=favorites.filter(f=>!(f.id===r.id || (r.link && f.link===r.link && f.title===r.title))); else favorites.push(r);
        storage.set(bookmarkKey,favorites.map(f=>({...f,url:f.link,source:f.source_name,time:f.time||'',snippet:f.summary})));
        button.textContent=isSaved(r)?'取消收藏':'收藏';
      });
      if (!keepPosition) window.scrollTo?.(0,0);
      if (fresh) status.textContent=Modules.addedCount(oldVisible,rows)?`新增 ${Modules.addedCount(oldVisible,rows)} 条`:'已是最新';
      return true;
    } catch (error) {
      if (current===generation) { main.innerHTML=empty('加载失败：'+error.message)+'<button id="retry" class="btn">重试</button>'; document.getElementById('retry').onclick=()=>route(true); }
      return false;
    } finally { if (current===generation) main.removeAttribute('aria-busy'); }
  }
  const refreshable = () => /^(feed|focus|review|history|day|explore)$/.test(getRoute().parts[0]);
  const refresh = async () => {
    if (refreshing || !refreshable()) return;
    refreshing=true;status.textContent='正在刷新';
    const success=await route(true,true);
    if (!success) status.textContent='刷新失败，请重试';
    else if (!navigator.onLine) status.textContent='没有网络，显示缓存的内容';
    refreshing=false;
  };
  document.addEventListener?.('keydown',event=>{
    if (event.key==='Escape' && (groupSheetOpen || datePickerOpen)) {
      groupSheetOpen=false;datePickerOpen=false;route(false,true);
    }
  });
  document.addEventListener?.('touchstart',event=>{
    startY=window.scrollY<=0&&refreshable()?event.touches[0].clientY:null;
    distance=0;
    const t=event.touches?.[0];
    const target=event.target;
    const inStrip=target?.closest?.('.flt, .chips, .date-strip, .sheet, .overlay');
    swipeStart=t && !inStrip && !groupSheetOpen && !datePickerOpen ? {x:t.clientX,y:t.clientY} : null;
  },{passive:true});
  document.addEventListener?.('touchmove',event=>{
    if (startY===null || refreshing) return;
    const t=event.touches?.[0];
    if (swipeStart && t && Math.abs(t.clientX-swipeStart.x)>Math.abs(t.clientY-swipeStart.y)) {
      startY=null;distance=0;status.textContent='';return;
    }
    distance=Math.max(0,event.touches[0].clientY-startY);
    if (distance>10) { status.textContent=distance>=72?'松手刷新':'下拉刷新';event.preventDefault(); }
  },{passive:false});
  document.addEventListener?.('touchend',event=>{
    if(distance>=72)refresh();else if(!refreshing)status.textContent='';
    startY=null;distance=0;
    const t=event.changedTouches?.[0];
    if (swipeStart && t) {
      const dx=t.clientX-swipeStart.x, dy=t.clientY-swipeStart.y;
      if (Math.abs(dx)>50 && Math.abs(dx)>Math.abs(dy)*1.5) {
        const dir=dx<0?1:-1;
        const {path,parts,query}=getRoute();
        if (parts[0]==='feed' || parts[0]==='today') {
          const cur=query.get('category')||'全部';
          const idx=categories.indexOf(cur);
          const next=categories[Math.max(0,Math.min(categories.length-1,(idx===-1?0:idx)+dir))];
          if (next && next!==cur) {
            groupSheetOpen=false;query.delete('channel');query.set('category',next);
            location.hash=path+'?'+query;
          }
        } else if (parts[0]==='explore') {
          const sections=['play','kan','buy'];
          const cur=sections.includes(parts[1])?parts[1]:'play';
          const idx=sections.indexOf(cur);
          const next=sections[Math.max(0,Math.min(sections.length-1,idx+dir))];
          if (next && next!==cur) location.hash='explore/'+next;
        }
      }
    }
    swipeStart=null;
  },{passive:true});
  document.addEventListener?.('touchcancel',()=>{startY=null;distance=0;swipeStart=null;if(!refreshing)status.textContent='';},{passive:true});
  applyTheme();
  matchMedia('(prefers-color-scheme: dark)').addEventListener?.('change',()=>applyTheme());
  themeButton.onclick=()=>{const next=document.documentElement.dataset.theme==='dark'?'light':'dark';storage.set('rebang-theme',next);applyTheme(next);};
  addEventListener('hashchange',()=>route());
  addEventListener('online',()=>route(true,true));
  addEventListener('offline',()=>route(false,true));
  // A page left open across the Beijing publication boundary changes its date too.
  if (typeof setInterval !== 'undefined') setInterval(()=>{
    if (getRoute().parts[0]==='focus' && renderedFocusDay!==Modules.focusDay()) route(true,true);
  },60000)?.unref?.();
  route();
})();
