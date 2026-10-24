/* News history: day-sized requests, joint filtering, and a native pointer timeline. */
(function (host) {
  'use strict';
  const normalize = topic => ['全球', '环球'].includes(topic) ? '国际' : topic;
  const tech = ['AI', '科技', '数码', '开发者'];
  function matches(row, state) {
    return (!state.source || [row.source, row.alias].includes(state.source)) &&
      (!state.topic || (state.topic === '科技' && !state.sub ? tech.includes(normalize(row.topic)) :
        normalize(row.topic) === (state.sub || normalize(state.topic))));
  }
  function dates(manifest, state, today) {
    return Object.keys(manifest.days).filter(day => day <= today &&
      manifest.days[day].joint.some(([source, alias, topic]) => matches({source, alias, topic}, state))).sort().reverse();
  }
  function unique(rows) {
    const seen = new Set();
    return rows.filter(row => !seen.has(row.uid) && seen.add(row.uid));
  }
  function pointerIndex(y, top, height, count) {
    return Math.round(Math.max(0, Math.min(1, (y - top) / Math.max(1, height))) * Math.max(0, count - 1));
  }
  class DayStore {
    constructor(manifest, scope, fetchDay) {
      this.manifest = manifest; this.scope = scope; this.fetchDay = fetchDay;
      this.cache = new Map(); this.generation = 0;
    }
    invalidate() { this.generation++; }
    async load(day, state) {
      const generation = this.generation;
      const key = JSON.stringify([this.scope, this.manifest.version, day, state.source, state.topic, state.sub, 'loaded-dates']);
      let rows = this.cache.get(key);
      if (!rows) {
        const data = await this.fetchDay(day);
        if (data.schema !== 3 || data.scope !== this.scope || data.day !== day || !Array.isArray(data.items)) {
          throw new Error('存档格式损坏');
        }
        rows = unique(data.items).filter(row => matches(row, state));
        this.cache.set(key, rows);
      }
      return generation === this.generation ? rows : null;
    }
  }
  const api = {normalize, matches, dates, unique, pointerIndex, DayStore};
  if (typeof module !== 'undefined') module.exports = api;
  if (!host.document) return;
  const document = host.document;
  const shell = document.querySelector('#news-history');
  if (!shell) return;
  const $ = id => document.getElementById(id);
  const list = $('news-list'), status = $('news-status'), capsule = $('news-capsule');
  const base = new URL(shell.dataset.root || './', location.href);
  const today = new Intl.DateTimeFormat('en-CA', {timeZone: 'Asia/Shanghai', year: 'numeric', month: '2-digit', day: '2-digit'})
    .formatToParts(new Date()).reduce((value, part) => ({...value, [part.type]: part.value}), {});
  const todayISO = `${today.year}-${today.month}-${today.day}`;
  let manifest, store, state, available = [], loaded = [], rows = [], busy = false, failed = false;
  let preview = null, dragging = false, timer = 0, reading = null, epoch = 0;
  let autoReady = false;
  const expanded = new Set();
  const reduced = matchMedia('(prefers-reduced-motion: reduce)').matches;
  const dayLabel = day => new Date(`${day}T12:00:00+08:00`).toLocaleDateString('zh-CN',
    {timeZone: 'Asia/Shanghai', month: 'long', day: 'numeric', weekday: 'long'});
  const readLine = () => Math.max(0, document.querySelector('.g-topbar')?.getBoundingClientRect().bottom || 0,
    document.querySelector('.news-controls')?.getBoundingClientRect().bottom || 0) + 8;
  function snapshot() {
    const first = [...list.querySelectorAll('article[data-uid]')].find(card => card.getBoundingClientRect().bottom > readLine());
    return {news: {...state}, loaded: [...loaded], anchor: first?.dataset.uid,
      offset: first ? first.getBoundingClientRect().top - readLine() : 0};
  }
  function save(push = false) {
    const url = new URL(location.href);
    for (const key of ['day', 'source', 'topic', 'sub', 'q']) {
      if (state[key]) url.searchParams.set(key, state[key]); else url.searchParams.delete(key);
    }
    if (push) history.pushState(snapshot(), '', url); else history.replaceState(snapshot(), '', url);
  }
  function parseState() {
    const params = new URLSearchParams(location.search);
    const topic = normalize(params.get('topic') || '');
    const legacyTech = tech.includes(topic) && topic !== '科技';
    return {day: params.get('day') || shell.dataset.day, source: params.get('source') || '',
      topic: legacyTech ? '科技' : topic, sub: params.get('sub') || (legacyTech ? topic : ''), q: params.get('q') || ''};
  }
  async function json(path) {
    const response = await fetch(new URL(path, base));
    if (!response.ok) throw new Error(`存档加载失败 (${response.status})`);
    return response.json();
  }
  function selection() {
    available = dates(manifest, state, todayISO);
    capsule.disabled = !available.length;
    capsule.setAttribute('aria-valuemin', '0');
    capsule.setAttribute('aria-valuemax', String(Math.max(0, available.length - 1)));
    const calendar = $('news-dates');
    calendar.replaceChildren(...available.map(day => {
      const button = document.createElement('button');
      button.type = 'button'; button.textContent = dayLabel(day); button.dataset.day = day;
      button.onclick = () => { $('news-calendar').close(); jump(day); };
      return button;
    }));
    $('news-source').value = state.source;
    $('news-query').value = state.q;
    document.querySelectorAll('[data-news-topic]').forEach(button => {
      button.setAttribute('aria-pressed', String(button.dataset.newsTopic === state.topic));
    });
    $('news-tech').hidden = state.topic !== '科技';
    document.querySelectorAll('[data-news-sub]').forEach(button => {
      button.setAttribute('aria-pressed', String(button.dataset.newsSub === state.sub));
    });
  }
  function showDate(day, row = null) {
    if (!preview) {
      $('news-current').textContent = dayLabel(day);
      $('news-newer').disabled = !available.some(value => value > day);
    }
    const label = capsule.querySelector('span');
    label.textContent = !preview && day === todayISO && row?.precision === 'instant' ?
      new Date(row.moment).toLocaleTimeString('zh-CN', {timeZone: 'Asia/Shanghai', hour: '2-digit', minute: '2-digit'}) : dayLabel(day);
    if (preview) {
      const hint = document.createElement('small');
      hint.textContent = dragging ? '松手定位' : 'Enter 确认';
      label.append(hint);
    }
    capsule.setAttribute('aria-valuenow', String(Math.max(0, available.indexOf(day))));
    capsule.setAttribute('aria-valuetext', `${day} 北京时间`);
  }
  function syncReading() {
    if (preview || dragging) return;
    const card = [...list.querySelectorAll('article')].find(item => item.getClientRects().length &&
      item.getBoundingClientRect().bottom > readLine() && item.getBoundingClientRect().top < innerHeight);
    if (!card) return;
    reading = card.dataset.day; state.day = reading;
    showDate(reading, rows.find(row => row.uid === card.dataset.uid));
  }
  function makeCard(row) {
    const template = document.createElement('template');
    template.innerHTML = row.html;
    const card = template.content.querySelector('article');
    card.dataset.uid = row.uid; card.dataset.day = row.day;
    // Serialized HTML is relative to archive/data/, so old entry points share one data file.
    card.querySelectorAll('[href],[src],[data-image]').forEach(element => {
      for (const name of ['href', 'src', 'data-image']) {
        const value = element.getAttribute(name);
        if (value && !value.startsWith('#')) element.setAttribute(name, new URL(value, new URL('archive/data/', base)).href);
      }
    });
    card.querySelectorAll('img').forEach(image => {
      image.addEventListener('error', () => { image.closest('.card__media')?.remove(); card.classList.add('card--text'); }, {once: true});
    });
    return card;
  }
  function renderRows() {
    const query = state.q.trim().toLocaleLowerCase();
    const filtered = rows.filter(row => !query || (() => {
      const template = document.createElement('template'); template.innerHTML = row.html;
      return template.content.textContent.toLocaleLowerCase().includes(query);
    })());
    list.replaceChildren();
    const single = !!state.source || new Set(rows.map(row => row.source)).size < 2;
    let start = 0;
    while (start < filtered.length) {
      let end = start + 1;
      while (end < filtered.length && filtered[end].source === filtered[start].source && filtered[end].day === filtered[start].day) end++;
      const group = filtered.slice(start, end);
      const key = group[0].uid;
      group.slice(0, single || query ? group.length : 3).forEach(row => list.append(makeCard(row)));
      if (!single && !query && group.length > 3) {
        const details = document.createElement('details');
        details.open = expanded.has(key);
        const summary = document.createElement('summary'); summary.textContent = `同源更多 ${group.length - 3} 条`;
        details.append(summary, ...group.slice(3).map(makeCard));
        details.addEventListener('toggle', () => details.open ? expanded.add(key) : expanded.delete(key));
        list.append(details);
      }
      start = end;
    }
    status.textContent = filtered.length ? '' : !manifest.days[state.day] ? '这一天没有存档，请改日期。' :
      query ? '已加载日期没有搜索结果；未加载日期尚未搜索。' : '该日有存档，但当前条件无匹配。请改日期或清筛选。';
    const last = loaded.at(-1) || state.day;
    const earlier = available.find(day => day < last);
    $('news-retry').hidden = !earlier;
    $('news-newer').disabled = !available.some(day => day > state.day);
    if (!earlier && loaded.length) status.textContent += ' 已到最早存档。';
    dispatchEvent(new Event('pageshow'));
  }
  function position(anchor, offset = 0) {
    const card = [...list.querySelectorAll('article[data-uid]')].find(item => item.dataset.uid === anchor) || list.querySelector('article');
    if (card) scrollTo({top: card.getBoundingClientRect().top + scrollY - readLine() - offset, behavior: 'instant'});
  }
  async function load(day, replace, push = false, restore = null) {
    const token = ++epoch;
    const originalPosition = snapshot();
    busy = true; failed = false;
    status.textContent = `正在加载 ${day}…`;
    const targetState = {...state, day};
    try {
      const data = await store.load(day, targetState);
      if (!data || token !== epoch) return;
      $('news-fallback').hidden = true;
      const previousPosition = snapshot();
      if (replace) { rows = []; loaded = []; }
      rows = unique([...rows, ...data]); loaded.push(day);
      if (replace) state = targetState;
      renderRows();
      if (replace) position(restore?.anchor, restore?.offset);
      else if (previousPosition.anchor) position(previousPosition.anchor, previousPosition.offset);
      const first = [...list.querySelectorAll('article')].find(card => card.getClientRects().length &&
        card.getBoundingClientRect().bottom > readLine() && card.getBoundingClientRect().top < innerHeight);
      if (first) { reading = first.dataset.day; state.day = reading; }
      showDate(state.day, rows.find(row => row.uid === first?.dataset.uid));
      if (push) save(true); else save();
      $('news-retry').onclick = () => { failed = false; next(); };
    } catch (error) {
      if (token !== epoch) return;
      failed = true;
      status.textContent = `${day} ${error.message}。原内容已保留，请重试。`;
      if (originalPosition.anchor) position(originalPosition.anchor, originalPosition.offset);
      $('news-retry').hidden = false;
      $('news-retry').onclick = () => load(day, replace, push, restore);
    } finally {
      if (token === epoch) busy = false;
    }
  }
  function jump(day, push = true) {
    if (busy) { store.invalidate(); epoch++; busy = false; }
    if (!manifest.days[day] || !available.includes(day)) {
      state.day = day; rows = []; loaded = []; $('news-fallback').hidden = true;
      renderRows(); showDate(day); save(push); return;
    }
    return load(day, true, push);
  }
  function next() {
    if (busy || failed) return;
    const day = available.find(value => value < (loaded.at(-1) || state.day));
    if (day) load(day, false);
  }
  function change(patch) {
    save(); store.invalidate(); epoch++; busy = false; failed = false;
    state = {...state, ...patch}; rows = []; loaded = []; list.replaceChildren(); selection();
    jump(state.day);
  }
  function appear() {
    clearTimeout(timer); capsule.classList.add('is-visible');
    timer = setTimeout(() => {
      if (!dragging && !capsule.matches(':focus,:hover')) capsule.classList.remove('is-visible');
    }, 1000);
  }
  function cancel() {
    dragging = false; preview = null; capsule.classList.remove('is-held'); showDate(state.day); appear();
  }
  function commit() {
    const day = preview;
    cancel();
    if (day) jump(day);
  }
  function route() {
    document.documentElement.classList.toggle('news-view', location.hash.startsWith('#screens/') || location.pathname.includes('/archive/'));
    if (location.hash === '#screens/focus') location.href = new URL('hot.html', base).href;
  }
  async function init() {
    document.documentElement.classList.add('news-surface');
    route();
    manifest = await json('archive/manifest.json');
    if (manifest.schema !== 3 || manifest.scope !== document.body.dataset.bookmarkScope) throw new Error('存档范围不匹配');
    store = new DayStore(manifest, manifest.scope, day => json(`archive/data/${day}.json?v=${manifest.days[day].version}`));
    state = parseState();
    const source = $('news-source');
    const all = document.createElement('option'); all.value = ''; all.textContent = '全部来源'; source.append(all);
    manifest.sources.forEach(item => {
      const option = document.createElement('option'); option.value = item.id; option.textContent = item.name;
      source.append(option);
    });
    const alias = manifest.sources.find(item => item.alias === state.source);
    if (alias) state.source = alias.id;
    source.onchange = () => change({source: source.value});
    for (const value of ['', '国际', '财经', '科技', '汽车', '社会', '娱乐']) {
      const button = document.createElement('button'); button.type = 'button';
      button.dataset.newsTopic = value; button.textContent = value || '全部';
      button.onclick = () => change({topic: value, sub: ''}); $('news-topics').append(button);
    }
    for (const value of ['', ...tech]) {
      const button = document.createElement('button'); button.type = 'button';
      button.dataset.newsSub = value; button.textContent = value || '全部科技';
      button.onclick = () => change({sub: value}); $('news-tech').append(button);
    }
    $('news-query').oninput = () => { save(); state.q = $('news-query').value; renderRows(); syncReading(); save(true); };
    $('news-clear').onclick = () => change({source: '', topic: '', sub: '', q: ''});
    $('news-source-toggle').onclick = () => {
      source.hidden = !source.hidden; $('news-source-toggle').setAttribute('aria-expanded', String(!source.hidden));
      if (!source.hidden) source.focus();
    };
    $('news-search-toggle').onclick = () => { $('news-query').hidden = !$('news-query').hidden; if (!$('news-query').hidden) $('news-query').focus(); };
    $('news-date-toggle').onclick = () => $('news-calendar').showModal();
    $('news-calendar-close').onclick = () => $('news-calendar').close();
    $('news-today').onclick = () => { $('news-calendar').close(); jump(todayISO); };
    $('news-retry').onclick = () => { failed = false; next(); };
    $('news-newer').onclick = () => {
      const day = available.filter(value => value > state.day).at(-1);
      if (day) jump(day);
    };
    selection();
    let saved = history.state;
    if (!saved) {
      try {
        const returning = JSON.parse(sessionStorage.getItem(`news-return-${manifest.scope}`) || 'null');
        if (returning?.url === location.href) saved = returning.snapshot;
      } catch { /* A fresh day remains usable if storage is unavailable. */ }
    }
    const target = {...state};
    const restoring = saved?.news && JSON.stringify(saved.news) === JSON.stringify(state) && saved.loaded?.length;
    if (restoring) {
      for (let index = 0; index < saved.loaded.length; index++) await load(saved.loaded[index], index === 0);
      state = target; position(saved.anchor, saved.offset); showDate(state.day); save();
    } else {
      await jump(state.day, false);
    }
    if (!failed) $('news-fallback').hidden = true;
    document.documentElement.classList.add('news-ready');
    if ('IntersectionObserver' in host) new IntersectionObserver(entries => {
      if (autoReady && entries.some(entry => entry.isIntersecting)) next();
    }, {rootMargin: '120px'}).observe($('news-sentinel'));
    for (const event of ['wheel', 'touchmove', 'pointerdown', 'keydown']) {
      addEventListener(event, () => { autoReady = true; }, {passive: true});
    }
    capsule.addEventListener('pointerdown', event => {
      if (capsule.disabled || event.button !== 0) return;
      dragging = true; preview = state.day; clearTimeout(timer);
      capsule.classList.add('is-held', 'is-visible'); capsule.setPointerCapture(event.pointerId);
      showDate(preview);
    });
    capsule.addEventListener('pointermove', event => {
      if (!dragging) return;
      preview = available[pointerIndex(event.clientY, 80, innerHeight - 190, available.length)];
      showDate(preview);
    });
    capsule.addEventListener('pointerup', commit);
    capsule.addEventListener('pointercancel', cancel);
    capsule.addEventListener('lostpointercapture', () => { if (dragging) cancel(); });
    capsule.addEventListener('focus', appear);
    capsule.addEventListener('blur', appear);
    capsule.addEventListener('mouseenter', appear);
    capsule.addEventListener('mouseleave', appear);
    capsule.addEventListener('keydown', event => {
      let index = available.indexOf(preview || state.day);
      if (['ArrowUp', 'ArrowDown', 'Home', 'End'].includes(event.key)) {
        event.preventDefault();
        index = event.key === 'Home' ? 0 : event.key === 'End' ? available.length - 1 : index + (event.key === 'ArrowUp' ? -1 : 1);
        preview = available[Math.max(0, Math.min(available.length - 1, index))];
        capsule.classList.add('is-held', 'is-visible'); clearTimeout(timer); showDate(preview);
      } else if (event.key === 'Enter') { event.preventDefault(); commit(); }
      else if (event.key === 'Escape') { event.preventDefault(); cancel(); }
    });
    document.addEventListener('keydown', event => { if (event.key === 'Escape' && dragging) cancel(); });
    let ticking = false;
    addEventListener('scroll', () => {
      if (!autoReady) return;
      appear();
      if (autoReady && $('news-sentinel').getBoundingClientRect().top < innerHeight + 120) next();
      if (ticking || dragging || preview) return;
      ticking = true;
      requestAnimationFrame(() => {
        ticking = false;
        syncReading(); save();
      });
    }, {passive: true});
    addEventListener('popstate', async event => {
      store.invalidate(); epoch++; busy = false; state = event.state?.news || parseState(); selection();
      const target = {...state}; const restore = event.state;
      const daysToLoad = restore?.loaded?.length ? restore.loaded : [target.day];
      for (let index = 0; index < daysToLoad.length; index++) await load(daysToLoad[index], index === 0);
      state = target; position(restore?.anchor, restore?.offset); showDate(state.day); save();
    });
    addEventListener('pagehide', () => {
      save();
      try { sessionStorage.setItem(`news-return-${manifest.scope}`, JSON.stringify({url: location.href, snapshot: snapshot()})); } catch {}
    });
    addEventListener('hashchange', route);
    if (reduced) capsule.classList.add('reduced-motion');
  }
  init().catch(error => { status.textContent = `${error.message}。可阅读本页离线内容，请刷新重试。`; });
})(typeof window === 'undefined' ? globalThis : window);
