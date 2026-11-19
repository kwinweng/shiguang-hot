// 拾光热榜 — interactions. One plain script, no dependencies.
// Modules: motion helpers · toast · bookmarks · filters · expanding cards · times · photo viewer ·
// navigation sheet · scroll chrome · pull to refresh. Every animation checks reduced motion first.
(() => {
  'use strict';
  const root = document.documentElement;
  const body = document.body;
  const $ = (selector, scope = document) => scope.querySelector(selector);
  const $$ = (selector, scope = document) => [...scope.querySelectorAll(selector)];
  const reduced = matchMedia('(prefers-reduced-motion: reduce)');
  const EASE = 'cubic-bezier(.2,.8,.2,1)';
  root.classList.add('js-ready');

  // ---------- Motion helpers ----------
  const canTransition = () => !reduced.matches && typeof document.startViewTransition === 'function';
  // In-page transitions (filters, photo viewer) are short and leave the light alone; the 900ms
  // light cross-fade belongs to moving between pages. The page takes no taps while one runs.
  function localTransition(update) {
    root.classList.add('vt-local');
    const run = document.startViewTransition(update);
    run.finished.finally(() => root.classList.remove('vt-local'));
    return run;
  }
  function animateHeight(element, from, to) {
    if (reduced.matches || from === to) return Promise.resolve();
    element.style.overflow = 'hidden';
    const duration = Math.min(560, 240 + Math.abs(to - from) * 0.35);
    const animation = element.animate([{height: `${from}px`}, {height: `${to}px`}], {duration, easing: EASE});
    return animation.finished.catch(() => {}).then(() => { element.style.overflow = ''; });
  }
  // Tabler symbols from the page sprite (icons.py); a bookmark also carries its filled glyph.
  function icon(name, filled = false) {
    const ns = 'http://www.w3.org/2000/svg';
    const svg = document.createElementNS(ns, 'svg');
    svg.setAttribute('class', 'i');
    svg.setAttribute('aria-hidden', 'true');
    const use = document.createElementNS(ns, 'use');
    use.setAttribute('href', `#t-${name}`);
    svg.append(use);
    if (filled) {
      const fill = document.createElementNS(ns, 'use');
      fill.setAttribute('class', 'i__fill');
      fill.setAttribute('href', `#tf-${name}`);
      svg.append(fill);
    }
    return svg;
  }

  // ---------- Toast ----------
  const toast = (() => {
    const element = $('#toast');
    if (!element) return () => {};
    const text = $('.toast__text', element);
    const link = $('a.toast__action', element);
    const button = $('button.toast__action', element);
    let timer = 0;
    const hide = () => element.classList.remove('is-shown');
    return (message, action) => {
      clearTimeout(timer);
      text.textContent = message;
      link.hidden = button.hidden = true;
      if (action?.href) { link.href = action.href; link.textContent = action.label; link.hidden = false; }
      if (action?.run) {
        button.textContent = action.label; button.hidden = false;
        button.onclick = () => { action.run(); hide(); };
      }
      element.classList.remove('is-shown');
      void element.offsetWidth; // restart the entrance when toasts follow each other
      element.classList.add('is-shown');
      timer = setTimeout(hide, 3600);
    };
  })();

  // ---------- Bookmarks ----------
  // Saved only in this browser. Public and private builds use separate keys even on one origin.
  const bookmarkKey = body.dataset.bookmarkScope === 'private' ? 'shiguang-favorites-private' : 'shiguang-favorites-public';
  const favoritesList = $('#favorites-list');
  const favoritesUrl = body.dataset.favorites;
  const FIELDS = ['id', 'title', 'url', 'source', 'time', 'snippet'];

  function readBookmarks() {
    try {
      const saved = JSON.parse(localStorage.getItem(bookmarkKey) || '[]');
      return Array.isArray(saved) ? saved.filter(item => item && FIELDS.every(key => typeof item[key] === 'string')) : [];
    } catch { return []; }
  }
  function writeBookmarks(list) {
    try { localStorage.setItem(bookmarkKey, JSON.stringify(list)); return true; } catch { return false; }
  }

  function favoriteCard(item) {
    const card = document.createElement('article');
    card.className = 'g-card card card--text';
    const meta = document.createElement('div');
    meta.className = 'g-card__label';
    const who = document.createElement('span');
    who.className = 'g-card__who';
    const source = document.createElement('span');
    source.className = 'source';
    source.textContent = item.source;
    who.append(source);
    const time = document.createElement('time');
    time.textContent = item.time.replace('T', ' ').slice(5, 16);
    meta.append(who, time);
    const title = document.createElement('h2');
    title.className = 'card__title';
    let url;
    try { url = new URL(item.url); } catch {}
    if (url && ['http:', 'https:'].includes(url.protocol)) {
      const anchor = document.createElement('a');
      anchor.href = url.href; anchor.target = '_blank'; anchor.rel = 'noopener noreferrer';
      anchor.textContent = item.title;
      title.append(anchor);
    } else title.textContent = item.title;
    card.append(meta, title);
    if (item.snippet) {
      const snippet = document.createElement('p');
      snippet.className = 'card__body';
      snippet.textContent = item.snippet;
      card.append(snippet);
    }
    const actions = document.createElement('div');
    actions.className = 'card__actions';
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'icon-btn bookmark';
    button.dataset.bookmark = JSON.stringify(item);
    button.append(icon('bookmark', true));
    actions.append(button);
    card.append(actions);
    return card;
  }

  function syncBookmarks() {
    const saved = readBookmarks();
    const ids = new Set(saved.map(item => item.id));
    if (favoritesList) {
      const focused = favoritesList.contains(document.activeElement);
      favoritesList.replaceChildren(...saved.map(favoriteCard));
      $('#favorites-empty').hidden = saved.length > 0;
      if (focused) favoritesList.querySelector('button')?.focus();
    }
    $$('[data-bookmark]').forEach(button => {
      const pressed = ids.has(JSON.parse(button.dataset.bookmark).id);
      button.setAttribute('aria-pressed', String(pressed));
      button.setAttribute('aria-label', pressed ? '取消收藏' : '收藏');
    });
  }

  async function toggleBookmark(button) {
    const item = JSON.parse(button.dataset.bookmark);
    const saved = readBookmarks();
    const index = saved.findIndex(entry => entry.id === item.id);
    const next = index >= 0 ? saved.filter(entry => entry.id !== item.id) : [item, ...saved];
    if (!writeBookmarks(next)) {
      const status = $('#favorites-status');
      const message = '这次没能保存，请检查设备存储空间和浏览器设置。';
      if (status) status.textContent = message;
      toast(message);
      return;
    }
    if (index >= 0) {
      const card = favoritesList && button.closest('article');
      if (card && !reduced.matches) {
        await card.animate([{opacity: 1, scale: 1}, {opacity: 0, scale: .96}], {duration: 200, easing: EASE, fill: 'forwards'}).finished.catch(() => {});
        await animateHeight(card, card.offsetHeight, 0);
      }
      syncBookmarks();
      toast('已取消收藏', {label: '撤销', run: () => {
        const list = readBookmarks().filter(entry => entry.id !== item.id);
        list.splice(Math.min(index, list.length), 0, item);
        if (writeBookmarks(list)) syncBookmarks();
      }});
    } else {
      syncBookmarks();
      toast('已收藏', favoritesUrl && !favoritesList ? {label: '查看', href: favoritesUrl} : undefined);
    }
  }
  document.addEventListener('click', event => {
    const button = event.target.closest('[data-bookmark]');
    if (button) toggleBookmark(button);
  });
  addEventListener('storage', event => { if (!event.key || event.key === bookmarkKey) syncBookmarks(); });
  addEventListener('pageshow', syncBookmarks);
  syncBookmarks();

  // ---------- Filters ----------
  const articles = $$('article.news');
  const search = $('#q');
  const channel = $('#channel');
  let category = '';

  function filterNews() {
    const query = (search?.value || '').trim().toLocaleLowerCase();
    // Cards marked data-more only serve filters (or 展开全部): the plain stream stays the ranked one.
    const filtering = !!(category || channel?.value || query || root.dataset.all);
    let shown = 0;
    for (const article of articles) {
      article.hidden = !!(('more' in article.dataset && !filtering) ||
        (category && article.dataset.cat !== category) ||
        (channel?.value && article.dataset.ch !== channel.value) ||
        (query && !article.textContent.toLocaleLowerCase().includes(query)));
      if (!article.hidden) shown++;
    }
    const empty = $('#none');
    if (empty) empty.hidden = shown > 0 || articles.length === 0;
    updateExpanders();
  }
  function revealResults() {
    const line = $('.searchline');
    if (line && line.getBoundingClientRect().top < 0) line.scrollIntoView({block: 'start', behavior: reduced.matches ? 'auto' : 'smooth'});
  }
  $$('.filters .pill').forEach(chip => chip.addEventListener('click', () => {
    // Filters answer instantly: a transition here would swallow quick follow-up taps.
    category = chip.dataset.value;
    $$('.filters .pill').forEach(other => {
      other.classList.toggle('selected', other === chip);
      other.setAttribute('aria-pressed', String(other === chip));
    });
    filterNews();
    chip.scrollIntoView({inline: 'center', block: 'nearest', behavior: reduced.matches ? 'auto' : 'smooth'});
    revealResults();
  }));
  let typing = 0;
  search?.addEventListener('input', () => { clearTimeout(typing); typing = setTimeout(filterNews, 120); });
  channel?.addEventListener('change', () => { filterNews(); revealResults(); });
  // Other pages link to a filtered home: index.html?source=<channel or column id>&topic=<topic>.
  const wanted = new URLSearchParams(location.search);
  if (channel && wanted.get('source') && [...channel.options].some(option => option.value === wanted.get('source'))) {
    channel.value = wanted.get('source');
    filterNews();
  }
  const wantedTopic = wanted.get('topic') && $$('.filters .pill').find(chip => chip.dataset.value === wanted.get('topic'));
  if (wantedTopic) {
    category = wantedTopic.dataset.value;
    $$('.filters .pill').forEach(other => {
      other.classList.toggle('selected', other === wantedTopic);
      other.setAttribute('aria-pressed', String(other === wantedTopic));
    });
    filterNews();
  }

  // ---------- Expanding cards ----------
  // "展开全文" only appears when the clamped text really hides something.
  function updateExpanders() {
    for (const article of articles) {
      const button = $('.expand', article);
      const text = $('.card__body', article);
      if (!button || !text || article.hidden || article.classList.contains('expanded')) continue;
      button.hidden = text.scrollHeight <= text.clientHeight + 2;
    }
  }
  function setExpandLabel(button, expanded) {
    button.setAttribute('aria-expanded', String(expanded));
    button.querySelector('span').textContent = expanded ? '收起' : '展开全文';
  }
  document.addEventListener('click', async event => {
    const button = event.target.closest('.expand');
    if (!button) return;
    const article = button.closest('article');
    const text = $('.card__body', article);
    const from = text.getBoundingClientRect().height;
    if (!article.classList.contains('expanded')) {
      article.classList.add('expanded');
      setExpandLabel(button, true);
      animateHeight(text, from, text.getBoundingClientRect().height);
    } else {
      article.classList.remove('expanded');
      const to = text.getBoundingClientRect().height;
      article.classList.add('expanded');
      setExpandLabel(button, false);
      await animateHeight(text, from, to);
      article.classList.remove('expanded');
      const top = article.getBoundingClientRect().top;
      if (top < 0) article.scrollIntoView({block: 'start', behavior: reduced.matches ? 'auto' : 'smooth'});
    }
  });
  addEventListener('load', updateExpanders);
  addEventListener('resize', () => requestAnimationFrame(updateExpanders));

  // ---------- Times ----------
  // Recent items read as "N 分钟前"; older ones keep the build-time date and time. Items from the
  // last hour carry the sun 「新」 mark (the sun's job: in progress, today, new).
  function updateTimes() {
    for (const time of $$('time[datetime]')) {
      const moment = new Date(time.dateTime);
      if (Number.isNaN(moment.getTime())) continue;
      time.dataset.absolute ??= time.textContent;
      const minutes = Math.max(0, Math.floor((Date.now() - moment) / 60000));
      time.title = moment.toLocaleString('zh-CN', {timeZone: 'Asia/Shanghai'}) + '（北京时间）';
      time.textContent = minutes < 1 ? '刚刚' : minutes < 60 ? `${minutes} 分钟前` : minutes < 1440 ? `${Math.floor(minutes / 60)} 小时前` : time.dataset.absolute;
      const who = time.parentElement.querySelector('.g-card__who');
      const mark = who?.querySelector('.is-new');
      if (who && minutes < 60 && !mark) {
        const pill = document.createElement('span');
        pill.className = 'g-pill g-pill--sun is-new';
        pill.textContent = '新';
        who.append(pill);
      } else if (mark && minutes >= 60) mark.remove();
    }
  }

  // ---------- Images ----------
  for (const image of $$('.photo img')) {
    const done = () => image.classList.add('is-loaded');
    if (image.complete) done(); else { image.addEventListener('load', done, {once: true}); image.addEventListener('error', done, {once: true}); }
  }

  // ---------- Photo viewer ----------
  // The thumbnail morphs into the full view (View Transitions); drag down or tap outside to close.
  const lightbox = $('.lightbox');
  const big = lightbox && $('img', lightbox);
  let trigger = null;
  let group = [];
  let index = 0;
  function inView(element) {
    const box = element.getBoundingClientRect();
    return box.bottom > 0 && box.top < innerHeight;
  }
  // Count pill and desktop arrows exist only when the open post has several photos.
  const count = document.createElement('span');
  count.className = 'lightbox__count';
  count.hidden = true;
  const arrows = [-1, 1].map(delta => {
    const label = delta < 0 ? '上一张' : '下一张';
    const button = document.createElement('button');
    button.type = 'button';
    button.className = `g-round lightbox__nav lightbox__nav--${delta < 0 ? 'prev' : 'next'}`;
    button.dataset.step = String(delta);
    button.setAttribute('aria-label', label);
    button.hidden = true;
    return button;
  });
  if (lightbox && big) {
    lightbox.append(...arrows, count);
    for (const arrow of arrows) arrow.addEventListener('click', event => { event.stopPropagation(); step(Number(arrow.dataset.step)); });
  }
  function showPhoto(next) {
    index = next;
    big.src = group[index].dataset.image;
    big.alt = group[index].querySelector('img').alt;
    trigger = group[index];
    count.textContent = `${index + 1}/${group.length}`;
    arrows[0].disabled = index <= 0;
    arrows[1].disabled = index >= group.length - 1;
  }
  function step(delta) {
    if (!lightbox.open) return;
    const next = Math.min(group.length - 1, Math.max(0, index + delta));
    if (next !== index) showPhoto(next);
  }
  async function openPhoto(button) {
    const media = button.closest('.card__media');
    group = media ? $$('.photo', media) : [button];
    if (!group.includes(button)) group = [button];
    index = group.indexOf(button);
    trigger = button;
    big.src = button.dataset.image;
    big.alt = $('img', button).alt;
    count.textContent = `${index + 1}/${group.length}`;
    const many = group.length > 1;
    count.hidden = !many;
    for (const arrow of arrows) arrow.hidden = !many;
    arrows[0].disabled = index <= 0;
    arrows[1].disabled = index >= group.length - 1;
    if (!canTransition()) { lightbox.showModal(); return; }
    await big.decode().catch(() => {});
    lightbox.classList.add('is-morph');
    button.querySelector('img').style.viewTransitionName = 'lightbox-image';
    await localTransition(() => {
      button.querySelector('img').style.viewTransitionName = '';
      big.style.viewTransitionName = 'lightbox-image';
      lightbox.showModal();
    }).finished.catch(() => {});
    big.style.viewTransitionName = '';
    lightbox.classList.remove('is-morph');
  }
  async function closePhoto() {
    if (!lightbox.open) return;
    const thumb = trigger && $('img', trigger);
    if (canTransition() && thumb && inView(thumb)) {
      lightbox.classList.add('is-morph');
      big.style.viewTransitionName = 'lightbox-image';
      await localTransition(() => {
        big.style.viewTransitionName = '';
        thumb.style.viewTransitionName = 'lightbox-image';
        lightbox.close();
      }).finished.catch(() => {});
      thumb.style.viewTransitionName = '';
      lightbox.classList.remove('is-morph');
    } else lightbox.close();
    for (const prop of ['--drag', '--swipe-x']) {
      big.style.removeProperty(prop);
      lightbox.style.removeProperty(prop);
    }
    trigger?.focus({preventScroll: true});
  }

  // Shared drag-down-to-dismiss gesture: follows the finger, closes past a distance or on a flick.
  function dragToDismiss(handle, target, dismiss, distance) {
    let start = null;
    handle.addEventListener('pointerdown', event => {
      if (event.button !== 0 || event.target.closest('button,a')) return;
      start = {y: event.clientY, t: performance.now(), dy: 0};
      handle.setPointerCapture(event.pointerId);
      target.classList.add('is-dragging');
    });
    handle.addEventListener('pointermove', event => {
      if (!start) return;
      start.dy = Math.max(0, event.clientY - start.y);
      target.style.setProperty('--drag', `${start.dy}px`);
    });
    const end = () => {
      if (!start) return;
      const moved = start.dy;
      const speed = moved / Math.max(1, performance.now() - start.t);
      start = null;
      target.classList.remove('is-dragging');
      if (moved > distance || (moved > 24 && speed > 0.6)) dismiss();
      else target.style.removeProperty('--drag');
    };
    handle.addEventListener('pointerup', end);
    handle.addEventListener('pointercancel', end);
  }

  // Lightbox gesture: the axis locks after ~10px — horizontal swipes step, vertical drags dismiss.
  if (lightbox && big) {
    let start = null;
    big.addEventListener('pointerdown', event => {
      if (event.button !== 0) return;
      start = {x: event.clientX, y: event.clientY, t: performance.now(), axis: null, dx: 0, dy: 0};
      big.setPointerCapture(event.pointerId);
    });
    big.addEventListener('pointermove', event => {
      if (!start) return;
      const dx = event.clientX - start.x;
      const dy = event.clientY - start.y;
      if (!start.axis) {
        if (Math.abs(dx) < 10 && Math.abs(dy) < 10) return;
        start.axis = Math.abs(dx) > Math.abs(dy) ? 'x' : 'y';
        lightbox.classList.add('is-dragging');
      }
      if (start.axis === 'x') {
        start.dx = dx;
        if (group.length < 2) return;
        const limit = Math.max(80, (innerWidth - big.offsetWidth) / 2);
        big.style.setProperty('--swipe-x', `${Math.max(-limit, Math.min(limit, dx))}px`);
      } else {
        start.dy = Math.max(0, dy);
        big.style.setProperty('--drag', `${start.dy}px`);
      }
    });
    const end = () => {
      if (!start) return;
      const {axis, dx, dy, t} = start;
      const elapsed = Math.max(1, performance.now() - t);
      start = null;
      const dismiss = axis === 'y' && (dy > 110 || (dy > 24 && dy / elapsed > 0.6));
      if (!dismiss) lightbox.classList.remove('is-dragging');
      big.style.removeProperty('--swipe-x');
      if (!dismiss) big.style.removeProperty('--drag');
      if (!axis) return;
      if (axis === 'x') {
        if (group.length < 2) return;
        if (Math.abs(dx) > 60 || (Math.abs(dx) > 20 && Math.abs(dx) / elapsed > 0.5)) step(dx < 0 ? 1 : -1);
      } else if (dismiss) closePhoto();
    };
    big.addEventListener('pointerup', end);
    big.addEventListener('pointercancel', end);
    big.addEventListener('lostpointercapture', end);
    lightbox.addEventListener('close', () => {
      lightbox.classList.remove('is-dragging');
      big.style.removeProperty('--swipe-x');
      big.style.removeProperty('--drag');
    });
    lightbox.addEventListener('keydown', event => {
      if (event.key === 'ArrowLeft') { event.preventDefault(); step(-1); }
      else if (event.key === 'ArrowRight') { event.preventDefault(); step(1); }
    });
  }

  if (lightbox) {
    document.addEventListener('click', event => {
      const button = event.target.closest('.photo');
      if (button) openPhoto(button);
    });
    lightbox.addEventListener('click', event => {
      if (event.target.closest('.lightbox__nav')) return;
      if (event.target === lightbox || event.target.closest('[data-close]')) closePhoto();
    });
    lightbox.addEventListener('cancel', event => { event.preventDefault(); closePhoto(); });
  }

  // ---------- Navigation sheet ----------
  const sheet = $('#more-nav');
  const menuButton = $('#more-toggle');
  if (sheet && menuButton) {
    const close = () => sheet.open && sheet.close();
    menuButton.addEventListener('click', () => {
      if (sheet.open) close(); else { sheet.showModal(); menuButton.setAttribute('aria-expanded', 'true'); }
    });
    sheet.addEventListener('click', event => {
      if (event.target === sheet || event.target.closest('a,[data-close]')) close();
    });
    sheet.addEventListener('close', () => {
      menuButton.setAttribute('aria-expanded', 'false');
      setTimeout(() => sheet.style.removeProperty('--drag'), 450);
    });
    dragToDismiss($('.sheet__head', sheet), sheet, close, 90);
  }

  // ---------- Dialogs opened from a button (时光机) ----------
  $$('[data-dialog]').forEach(button => {
    const dialog = document.getElementById(button.dataset.dialog);
    if (!dialog) return;
    const close = () => dialog.open && dialog.close();
    button.addEventListener('click', () => { dialog.showModal(); button.setAttribute('aria-expanded', 'true'); });
    dialog.addEventListener('click', event => {
      if (event.target === dialog || event.target.closest('a,[data-close]')) close();
    });
    dialog.addEventListener('close', () => {
      button.setAttribute('aria-expanded', 'false');
      setTimeout(() => dialog.style.removeProperty('--drag'), 450);
    });
    const head = $('.sheet__head', dialog);
    if (head) dragToDismiss(head, dialog, close, 90);
    // Open on the month being shown.
    dialog.addEventListener('toggle', () => { if (dialog.open) $('[aria-current=page]', dialog)?.scrollIntoView({block: 'center'}); });
  });

  // ---------- 展开全部: a day's filter-only cards, without choosing a filter ----------
  $('.show-all')?.addEventListener('click', event => {
    root.dataset.all = '1';
    filterNews();
    event.currentTarget.closest('.more-link').hidden = true;
  });

  // ---------- 栏目: by channel / by tag ----------
  const views = $$('.view-switch [data-view]');
  if (views.length) {
    const show = key => {
      views.forEach(b => b.setAttribute('aria-pressed', String(b.dataset.view === key)));
      $$('[data-panel]').forEach(panel => { panel.hidden = panel.dataset.panel !== key; });
      try { localStorage.setItem('shiguang-columns-view', key); } catch (error) { /* private mode */ }
    };
    views.forEach(b => b.addEventListener('click', () => show(b.dataset.view)));
    let initial = location.hash.slice(1);
    if (!views.some(b => b.dataset.view === initial)) {
      try { initial = localStorage.getItem('shiguang-columns-view'); } catch (error) { initial = null; }
    }
    show(views.some(b => b.dataset.view === initial) ? initial : views[0].dataset.view);
  }

  // ---------- 热点: 24-hour timeline ----------
  // The bar under the marker is the hour being read. Dragging the bars jumps the list to that hour
  // (or the closest earlier hour with stories); scrolling the list moves the bars along.
  const timeline = $('[data-timeline]');
  if (timeline) {
    const track = $('.tl-track', timeline);
    const label = $('.tl-now', timeline);
    const cells = $$('.tl-hour', track);
    const anchors = $$('.tl-anchor');           // newest first
    const byKey = new Map(cells.map(cell => [cell.dataset.key, cell]));
    // Each direction mutes the other while it moves things itself: bars moved by the list must not
    // jump the list, and the list moved by the bars must not drag the bars.
    let current = null, trackQuiet = 0, listQuiet = 0, settle = 0, trailing = 0;
    const format = key => `${+key.slice(5, 7)}月${+key.slice(8, 10)}日 ${+key.slice(11)}:00`;
    const nearest = () => {
      const middle = track.getBoundingClientRect().left + track.clientWidth / 2;
      let best = null, distance = Infinity;
      for (const cell of cells) {
        const box = cell.getBoundingClientRect();
        const d = Math.abs(box.left + box.width / 2 - middle);
        if (d < distance) { distance = d; best = cell; }
      }
      return best;
    };
    const mark = cell => {
      if (!cell || cell === current) return;
      current?.classList.remove('is-current');
      current = cell;
      cell.classList.add('is-current');
      label.textContent = format(cell.dataset.key) + (cell.classList.contains('is-future') ? ' · 还没到' : '');
    };
    const centre = (cell, smooth) => {
      if (!cell) return;
      trackQuiet = performance.now() + 700;
      const box = cell.getBoundingClientRect(), frame = track.getBoundingClientRect();
      track.scrollBy({left: box.left + box.width / 2 - (frame.left + frame.width / 2), behavior: smooth && !reduced.matches ? 'smooth' : 'auto'});
      mark(cell);
    };
    // Where the list is read: just under the timeline once it is stuck below the top bar.
    const readLine = () => ($('.g-topbar')?.getBoundingClientRect().bottom || 0) + timeline.offsetHeight + 8;
    const jump = key => {
      const anchor = anchors.find(a => a.dataset.key <= key) || anchors.at(-1);
      if (!anchor) return;
      listQuiet = performance.now() + 300;
      // Instant: scrubbing should land where the finger stops, not chase it.
      scrollTo({top: anchor.getBoundingClientRect().top + scrollY - readLine(), behavior: 'instant'});
    };
    track.addEventListener('scroll', () => {
      requestAnimationFrame(() => mark(nearest()));
      if (performance.now() < trackQuiet) return;
      clearTimeout(settle);
      settle = setTimeout(() => { if (current && !current.classList.contains('is-future')) jump(current.dataset.key); }, 180);
    }, {passive: true});
    cells.forEach(cell => cell.addEventListener('click', event => {
      event.preventDefault();
      if (cell.classList.contains('is-future')) return;
      centre(cell, true);
      jump(cell.dataset.key);
    }));
    // Mouse drag (touch scrolls natively).
    let drag = null;
    track.addEventListener('pointerdown', event => {
      if (event.pointerType !== 'mouse') return;
      drag = {x: event.clientX, left: track.scrollLeft, moved: false};
      track.classList.add('is-dragging');
    });
    addEventListener('pointermove', event => {
      if (!drag) return;
      if (Math.abs(event.clientX - drag.x) > 3) drag.moved = true;
      track.scrollLeft = drag.left - (event.clientX - drag.x);
    });
    addEventListener('pointerup', () => {
      if (!drag) return;
      track.classList.remove('is-dragging');
      if (drag.moved) track.addEventListener('click', e => e.preventDefault(), {capture: true, once: true});
      drag = null;
    });
    // The list moves the bars: the last hour heading above the timeline's foot is the one being read.
    let ticking = false;
    const follow = () => {
      const line = readLine() + 4;
      let reading = anchors[0];
      for (const anchor of anchors) { if (anchor.getBoundingClientRect().top <= line) reading = anchor; else break; }
      const cell = reading && byKey.get(reading.dataset.key);
      if (cell && cell !== current) centre(cell, false);
    };
    addEventListener('scroll', () => {
      clearTimeout(trailing);
      trailing = setTimeout(follow, 160);   // always settle on where the list stopped
      if (ticking || performance.now() < listQuiet) return;
      ticking = true;
      requestAnimationFrame(() => { ticking = false; follow(); });
    }, {passive: true});
    // Start on the newest hour that has passed.
    centre(cells.filter(cell => !cell.classList.contains('is-future')).at(-1), false);
  }

  // ---------- Search button ----------
  $('#search-toggle')?.addEventListener('click', () => {
    if (search) {
      $('.searchline').scrollIntoView({block: 'start', behavior: reduced.matches ? 'auto' : 'smooth'});
      search.focus({preventScroll: true});
    } else location.href = $('.g-topbar__brand').getAttribute('href') + '#q';
  });
  if (location.hash === '#q' && search) search.focus();

  // ---------- Scroll chrome ----------
  // Past 30 of scroll the top bar's edge and the page name fade in; a stuck filter row continues
  // the edge. Tapping the current tab scrolls back to the top.
  const tabbar = $('nav.bottom');
  const header = $('.g-topbar');
  const filterbar = $('.filterbar');
  function measure() {
    if (tabbar) root.style.setProperty('--tab-bar-height', `${tabbar.offsetHeight + 8}px`);
  }
  if ('ResizeObserver' in window && tabbar) new ResizeObserver(measure).observe(tabbar);
  measure();
  let lastY = Math.max(0, scrollY), frame = 0;
  function onScroll() {
    frame = 0;
    const y = Math.max(0, scrollY);
    const delta = y - lastY;
    root.toggleAttribute('data-scrolled', y > 30);
    if (filterbar && header) filterbar.toggleAttribute('data-stuck', filterbar.getBoundingClientRect().top <= header.getBoundingClientRect().bottom + 0.5);
    lastY = y;
  }
  addEventListener('scroll', () => { if (!frame) frame = requestAnimationFrame(onScroll); }, {passive: true});
  onScroll();
  $$('.tab.active').forEach(tab => tab.addEventListener('click', event => {
    if (event.metaKey || event.ctrlKey || event.shiftKey) return;
    event.preventDefault();
    scrollTo({top: 0, behavior: reduced.matches ? 'auto' : 'smooth'});
  }));

  // ---------- Pull to refresh ----------
  if (tabbar && matchMedia('(pointer: coarse)').matches) {
    const refresh = document.createElement('div');
    refresh.className = 'pull-refresh glass';
    refresh.hidden = true;
    refresh.setAttribute('role', 'status');
    refresh.setAttribute('aria-live', 'polite');
    const sun = document.createElement('span');
    sun.className = 'sun';
    sun.append(icon('sun'));
    const label = document.createElement('span');
    label.textContent = '下拉刷新';
    refresh.append(sun, label);
    body.append(refresh);
    const THRESHOLD = 70;
    let gesture = null, refreshing = false;
    const horizontal = target => {
      for (let element = target; element instanceof Element; element = element.parentElement) {
        if (element.matches('.column-row,.filters,.archives,input,select,textarea,dialog')) return true;
        if (element.scrollWidth > element.clientWidth && /auto|scroll/.test(getComputedStyle(element).overflowX)) return true;
      }
      return false;
    };
    const reset = () => {
      gesture = null;
      if (refreshing) return;
      refresh.hidden = true;
      refresh.classList.remove('is-ready');
      refresh.style.removeProperty('--pull');
    };
    document.addEventListener('touchstart', event => {
      reset();
      if (refreshing || scrollY > 0 || event.touches.length !== 1 || $('dialog[open]') || horizontal(event.target)) return;
      gesture = {x: event.touches[0].clientX, y: event.touches[0].clientY, pull: 0, vertical: false};
    }, {passive: true});
    document.addEventListener('touchmove', event => {
      if (!gesture) return;
      if (event.touches.length !== 1) return reset();
      const dx = Math.abs(event.touches[0].clientX - gesture.x);
      const dy = event.touches[0].clientY - gesture.y;
      if (dy < 0 || dx > Math.abs(dy)) return reset();
      if (!gesture.vertical && dy < 8) return;
      gesture.vertical = true;
      if (event.cancelable) event.preventDefault();
      // Rubber band: resistance grows with distance.
      gesture.pull = Math.min(120, dy * 0.55 - dy * dy * 0.0006);
      refresh.hidden = false;
      refresh.style.setProperty('--pull', `${gesture.pull}px`);
      const ready = gesture.pull >= THRESHOLD;
      refresh.classList.toggle('is-ready', ready);
      label.textContent = ready ? '松开刷新' : '下拉刷新';
    }, {passive: false});
    document.addEventListener('touchend', () => {
      if (!gesture || gesture.pull < THRESHOLD) return reset();
      refreshing = true;
      gesture = null;
      refresh.style.setProperty('--pull', `${THRESHOLD}px`);
      refresh.classList.add('is-refreshing');
      label.textContent = '刷新中…';
      const url = new URL(location.href);
      url.searchParams.set('r', Date.now().toString());
      requestAnimationFrame(() => requestAnimationFrame(() => location.replace(url.href)));
    }, {passive: true});
    document.addEventListener('touchcancel', reset, {passive: true});
    addEventListener('pageshow', () => { refreshing = false; refresh.classList.remove('is-refreshing'); reset(); });
  }

  // ---------- Light per group ----------
  // 「光」: when the list scrolls into another group, the light changes to that group's photo
  // (900ms cross-fade, instant under reduced motion); outside any lit group it is the page's own.
  const lightLayer = $('.g-light');
  const leafGroups = $$('.group').filter(group => !group.querySelector('.group'));
  if (lightLayer && leafGroups.some(group => group.dataset.light) && 'IntersectionObserver' in window) {
    let shown = null;
    const showLight = group => {
      const key = group?.dataset.light ? group : null;
      if (key === shown) return;
      shown = key;
      const field = document.createElement('i');
      field.className = 'g-light__field';
      if (key) {
        field.style.setProperty('--light-image', `url("${key.dataset.light}")`);
        field.style.setProperty('--dark-image', `url("${key.dataset.lightDark}")`);
      }
      const old = $$('.g-light__field', lightLayer);
      lightLayer.append(field);
      if (reduced.matches) { old.forEach(layer => layer.remove()); return; }
      field.style.opacity = '0';
      requestAnimationFrame(() => {
        field.style.transition = 'opacity 900ms cubic-bezier(.45,0,.55,1)';
        field.style.opacity = '1';
        setTimeout(() => old.forEach(layer => layer.remove()), 950);
      });
    };
    // The group crossing a thin band just above the middle of the screen owns the light.
    const inBand = new Set();
    const watcher = new IntersectionObserver(entries => {
      entries.forEach(entry => (entry.isIntersecting ? inBand.add(entry.target) : inBand.delete(entry.target)));
      showLight([...inBand].pop() || null);
    }, {rootMargin: '-45% 0px -50% 0px'});
    leafGroups.forEach(group => watcher.observe(group));
  }

  // ---------- Photo strip ----------
  // Each print takes its photo's shape (ratio held within 0.56–1.78) once the size is known; the
  // dots follow the print nearest the start of the strip.
  for (const print of $$('.g-print')) {
    const image = $('img', print);
    const fit = () => {
      const ratio = image.naturalWidth && image.naturalHeight ? image.naturalWidth / image.naturalHeight : 0.75;
      print.style.width = `${Math.round(232 * Math.min(1.78, Math.max(0.56, ratio)))}px`;
    };
    if (image.complete && image.naturalWidth) fit(); else image.addEventListener('load', fit, {once: true});
  }
  for (const strip of $$('.g-strip')) {
    const dots = $$('.g-dots i', strip.parentElement);
    strip.addEventListener('scroll', () => {
      const prints = [...strip.children];
      let nearest = 0;
      prints.forEach((print, index) => {
        if (Math.abs(print.offsetLeft - strip.offsetLeft - strip.scrollLeft) < Math.abs(prints[nearest].offsetLeft - strip.offsetLeft - strip.scrollLeft)) nearest = index;
      });
      dots.forEach((dot, index) => dot.toggleAttribute('aria-current', index === nearest));
    }, {passive: true});
  }

  // ---------- Reading size ----------
  // Text on paper can grow to 18/33 and 19.5/36; only the reading text changes, never the interface.
  const READING_KEY = 'shiguang-reading';
  const setReading = size => {
    root.dataset.reading = size;
    $$('.reading-size [data-reading]').forEach(button => button.setAttribute('aria-pressed', String(button.dataset.reading === size)));
  };
  try { const saved = localStorage.getItem(READING_KEY); if (['1', '2', '3'].includes(saved)) setReading(saved); } catch {}
  $$('.reading-size [data-reading]').forEach(button => button.addEventListener('click', () => {
    setReading(button.dataset.reading);
    try { localStorage.setItem(READING_KEY, button.dataset.reading); } catch {}
  }));

  filterNews();
  updateTimes();
  setInterval(updateTimes, 60000);
})();
