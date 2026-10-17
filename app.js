// Bookmarks never leave this origin's device storage. Separate build modes also
// prevent private bookmarks appearing when both builds share an origin.
const bookmarkKey = document.body.dataset.bookmarkScope === 'private' ? 'shiguang-favorites-private' : 'shiguang-favorites-public';
const bookmarkList = document.querySelector('#favorites-list');
function readBookmarks() {
  try {
    const saved = JSON.parse(localStorage.getItem(bookmarkKey) || '[]');
    return Array.isArray(saved) ? saved.filter(item => item && ['id','title','url','source','time','snippet'].every(key => typeof item[key] === 'string')) : [];
  } catch { return []; }
}
function bookmarkButton(item, remove = false) {
  const button = document.createElement('button');
  button.className = 'bookmark';
  button.dataset.bookmark = JSON.stringify(item);
  if (remove) button.textContent = '移除';
  return button;
}
function syncBookmarks() {
  const saved = readBookmarks();
  if (bookmarkList) {
    const focusedId = bookmarkList.contains(document.activeElement) ? document.activeElement?.dataset.bookmark : null;
    bookmarkList.replaceChildren();
    saved.forEach(item => {
      const card = document.createElement('article');
      card.className = 'card g-card';
      const title = document.createElement('h2');
      let url;
      try { url = new URL(item.url); } catch {}
      if (url && ['http:','https:'].includes(url.protocol)) {
        const anchor = document.createElement('a');
        anchor.href = url.href;
        anchor.textContent = item.title;
        anchor.target = '_blank';
        anchor.rel = 'noopener noreferrer';
        title.append(anchor);
      } else title.textContent = item.title;
      const meta = document.createElement('div');
      meta.className = 'meta';
      meta.textContent = `${item.source} · ${item.time}`;
      const snippet = document.createElement('p');
      snippet.textContent = item.snippet;
      const foot = document.createElement('div');
      foot.className = 'foot';
      foot.append(bookmarkButton(item, true));
      card.append(meta, title, snippet, foot);
      bookmarkList.append(card);
    });
    document.querySelector('#favorites-empty').hidden = saved.length > 0;
    if (focusedId) bookmarkList.querySelector('button')?.focus();
  }
  document.querySelectorAll('[data-bookmark]').forEach(button => {
    const item = JSON.parse(button.dataset.bookmark);
    const pressed = saved.some(savedItem => savedItem.id === item.id);
    button.setAttribute('aria-pressed', String(pressed));
    button.setAttribute('aria-label', pressed ? '取消收藏' : '收藏');
  });
}
document.addEventListener('click', event => {
  const button = event.target.closest('[data-bookmark]');
  if (!button) return;
  const item = JSON.parse(button.dataset.bookmark);
  const saved = readBookmarks();
  const next = saved.some(savedItem => savedItem.id === item.id) ? saved.filter(savedItem => savedItem.id !== item.id) : [item, ...saved];
  try {
    localStorage.setItem(bookmarkKey, JSON.stringify(next));
    syncBookmarks();
  } catch {
    let status = document.querySelector('#favorites-status');
    if (!status) {
      status = document.createElement('p');
      status.id = 'favorites-status';
      status.setAttribute('role', 'status');
      button.closest('article').append(status);
    }
    status.textContent = '这次没能保存，请检查设备存储空间和浏览器设置。';
  }
});
addEventListener('storage', event => { if (!event.key || event.key === bookmarkKey) syncBookmarks(); });
addEventListener('pageshow', syncBookmarks);
syncBookmarks();

const articles = [...document.querySelectorAll('.news')];
const search = document.querySelector('#q');
const channel = document.querySelector('#channel');
let category = '';
function filterNews() {
  const query = (search?.value || '').trim().toLocaleLowerCase();
  let count = 0;
  articles.forEach(article => {
    article.hidden = !!((category && article.dataset.cat !== category) ||
      (channel?.value && article.dataset.ch !== channel.value) ||
      (query && !article.textContent.toLocaleLowerCase().includes(query)));
    if (!article.hidden) count++;
  });
  document.querySelectorAll('.dategroup').forEach(group => {
    let next = group.nextElementSibling;
    let visible = false;
    while (next && !next.classList.contains('dategroup')) {
      if (next.classList.contains('news') && !next.hidden) visible = true;
      next = next.nextElementSibling;
    }
    group.hidden = !visible;
  });
  const counter = document.querySelector('#n');
  if (counter) counter.textContent = count;
  const empty = document.querySelector('#none');
  if (empty) empty.hidden = count > 0;
}
document.querySelectorAll('.pill').forEach(button => button.addEventListener('click', () => {
  category = button.dataset.value;
  document.querySelectorAll('.pill').forEach(pill => {
    pill.classList.toggle('selected', pill === button);
    pill.setAttribute('aria-pressed', String(pill === button));
  });
  filterNews();
}));
search?.addEventListener('input', filterNews);
channel?.addEventListener('change', filterNews);
articles.forEach(article => {
  const button = article.querySelector('.expand');
  if (!button) return;
  button.addEventListener('click', () => {
    const expanded = article.classList.toggle('expanded');
    button.setAttribute('aria-expanded', expanded);
    button.textContent = expanded ? '收起全文 −' : '展开全文 ＋';
  });
});
function updateTimes() {
  document.querySelectorAll('time[datetime]').forEach(time => {
    const minutes = Math.max(0, Math.floor((Date.now() - new Date(time.dateTime)) / 60000));
    time.title = new Date(time.dateTime).toLocaleString('zh-CN', {timeZone: 'Asia/Shanghai'}) + '（北京时间）';
    time.textContent = minutes < 1 ? '刚刚' : minutes < 60 ? `${minutes} 分钟前` : minutes < 1440 ? `${Math.floor(minutes / 60)} 小时前` : `${Math.floor(minutes / 1440)} 天前`;
  });
}
filterNews();
updateTimes();
setInterval(updateTimes, 60000);
const lightbox = document.querySelector('.lightbox');
let photoTrigger;
document.querySelectorAll('.photo').forEach(button => button.addEventListener('click', () => {
  photoTrigger = button;
  lightbox.querySelector('img').src = button.dataset.image;
  lightbox.querySelector('img').alt = button.querySelector('img').alt;
  lightbox.showModal();
}));
lightbox?.querySelector('.lightbox-close').addEventListener('click', () => lightbox.close());
lightbox?.addEventListener('click', event => {
  if (event.target === lightbox) lightbox.close();
});
lightbox?.addEventListener('close', () => photoTrigger?.focus({preventScroll: true}));
document.querySelector('#theme')?.addEventListener('click', () => {
  const dark = document.documentElement.dataset.theme === 'dark' || (!document.documentElement.dataset.theme && matchMedia('(prefers-color-scheme: dark)').matches);
  document.documentElement.dataset.theme = dark ? 'light' : 'dark';
});
const morePanel = document.querySelector('#more-nav');
const moreToggle = document.querySelector('#more-toggle');
moreToggle?.setAttribute('aria-controls', 'more-nav');
moreToggle?.addEventListener('click', () => {
  if (morePanel.open) morePanel.close();
  else morePanel.showModal();
  moreToggle.setAttribute('aria-expanded', String(morePanel.open));
});
morePanel?.addEventListener('click', event => {
  if (event.target === morePanel || event.target.closest('a')) morePanel.close();
});
morePanel?.addEventListener('close', () => moreToggle?.setAttribute('aria-expanded', 'false'));
document.querySelector('#search-toggle')?.addEventListener('click', () => {
  if (search) { search.scrollIntoView({block: 'center'}); search.focus({preventScroll: true}); }
  else location.href = document.querySelector('.brand').getAttribute('href').replace('index.html', 'all.html') + '#q';
});

// One physical selection surface per control; native anchors keep navigation.
const reducedMotion = matchMedia('(prefers-reduced-motion: reduce)');
if (/Chrome|Chromium/.test(navigator.userAgent) && CSS.supports('backdrop-filter', 'url(#lg) blur(16px)')) document.documentElement.dataset.glassLens = '';
const selections = [...document.querySelectorAll('.bottom')].map(control => {
  const indicator = document.createElement('span');
  indicator.className = 'selection-pill';
  indicator.setAttribute('aria-hidden', 'true');
  control.prepend(indicator);
  const items = [...control.querySelectorAll('a,.pill')];
  let selected = control.querySelector('.active,.selected');
  function position(animate = false) {
    indicator.hidden = !selected;
    if (!selected) return;
    // Only user-driven moves should slide: browser repositioning (resize,
    // ResizeObserver, fonts, pageshow) snaps instead of animating a stale pill.
    if (!animate) control.classList.add('pill-instant');
    // Measure against the control's own border box (viewport-space rects are
    // immune to offsetParent mismatches and integer offset rounding) and
    // subtract the border width: the pill's absolute containing block is the
    // control's padding box (border box + border), same origin offsetTop/
    // offsetLeft use, so the translate lands the pill exactly on the active slot.
    const origin = control.getBoundingClientRect();
    const box = selected.getBoundingClientRect();
    const style = getComputedStyle(control);
    const offX = parseFloat(style.borderLeftWidth);
    const offY = parseFloat(style.borderTopWidth);
    indicator.style.setProperty('--pill-x', `${box.left - origin.left - offX}px`);
    indicator.style.setProperty('--pill-y', `${box.top - origin.top - offY}px`);
    indicator.style.setProperty('--pill-width', `${box.width}px`);
    indicator.style.setProperty('--pill-height', `${box.height}px`);
    if (!animate) {
      void indicator.offsetWidth;
      control.classList.remove('pill-instant');
    }
  }
  const reposition = () => position();
  items.forEach(item => {
    if (item.matches('button')) item.setAttribute('aria-pressed', String(item === selected));
    item.addEventListener('click', event => {
      if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
      selected = item;
      items.forEach(other => {
        other.classList.toggle(other.matches('button') ? 'selected' : 'active', other === item);
        if (other.matches('button')) other.setAttribute('aria-pressed', String(other === item));
      });
      position(true);
    });
    new ResizeObserver(reposition).observe(item);
  });
  position();
  requestAnimationFrame(() => { position(); control.classList.add('glass-ready'); });
  new ResizeObserver(reposition).observe(control);
  addEventListener('resize', reposition, {passive: true});
  addEventListener('load', reposition);
  if (document.fonts?.ready) document.fonts.ready.then(reposition);
  return position;
});
addEventListener('pageshow', () => selections.forEach(position => position()));
let sheenFrame = 0, pointerX = .24, pointerY = 0;
function updateSheen() {
  sheenFrame = 0;
  const root = document.documentElement;
  root.style.setProperty('--sheen-x', `${(18 + pointerX * 42).toFixed(1)}%`);
  root.style.setProperty('--sheen-y', `${(pointerY * 24 + Math.min(scrollY / Math.max(1, root.scrollHeight - innerHeight), 1) * 28).toFixed(1)}%`);
}
function scheduleSheen() {
  if (!reducedMotion.matches && !sheenFrame) sheenFrame = requestAnimationFrame(updateSheen);
}
addEventListener('pointermove', event => { pointerX = event.clientX / innerWidth; pointerY = event.clientY / innerHeight; scheduleSheen(); }, {passive:true});
addEventListener('scroll', scheduleSheen, {passive:true});
reducedMotion.addEventListener('change', () => {
  if (reducedMotion.matches) {
    cancelAnimationFrame(sheenFrame); sheenFrame = 0;
    document.documentElement.style.removeProperty('--sheen-x');
    document.documentElement.style.removeProperty('--sheen-y');
  } else scheduleSheen();
});

const bottomBar = document.querySelector('nav.bottom');
if (bottomBar) {
  const root = document.documentElement;
  const header = document.querySelector('header');
  function measureChrome() {
    root.style.setProperty('--tab-bar-height', `${bottomBar.offsetHeight + 22}px`);
    if (header) root.style.setProperty('--header-height', `${header.offsetHeight}px`);
  }
  const chromeObserver = new ResizeObserver(measureChrome);
  chromeObserver.observe(bottomBar);
  if (header) chromeObserver.observe(header);
  measureChrome();
  let lastY = Math.max(0, scrollY), direction = 0, distance = 0;
  function updateBottomBar() {
    const y = Math.max(0, scrollY);
    const delta = y - lastY;
    const nextDirection = Math.sign(delta);
    if (nextDirection !== direction) distance = 0;
    distance += Math.abs(delta);
    direction = nextDirection;
    const atEdge = y < 80 || y + innerHeight >= root.scrollHeight - 80;
    if (atEdge || document.querySelector('dialog[open]') || bottomBar.contains(document.activeElement)) {
      bottomBar.classList.remove('is-hidden');
    } else if (distance >= 8) {
      bottomBar.classList.toggle('is-hidden', delta > 0);
    }
    lastY = y;
  }
  addEventListener('scroll', updateBottomBar, {passive: true});
  bottomBar.addEventListener('focusin', () => bottomBar.classList.remove('is-hidden'));
  addEventListener('pageshow', updateBottomBar);

  const refresh = document.createElement('div');
  refresh.className = 'pull-refresh';
  refresh.hidden = true;
  refresh.setAttribute('role', 'status');
  refresh.setAttribute('aria-live', 'polite');
  refresh.innerHTML = '<span class="refresh-symbol" aria-hidden="true">↓</span><span class="refresh-label">下拉刷新</span>';
  document.body.append(refresh);
  const refreshLabel = refresh.querySelector('.refresh-label');
  let gesture = null, refreshing = false;
  function horizontalTarget(target) {
    for (let element = target; element instanceof Element; element = element.parentElement) {
      if (element.matches('.column-row,.filters,.archives,input,select,textarea,[contenteditable]')) return true;
      const overflow = getComputedStyle(element).overflowX;
      if (element.scrollWidth > element.clientWidth && /auto|scroll/.test(overflow)) return true;
    }
    return false;
  }
  function cancelPull() {
    gesture = null;
    if (!refreshing) {
      refresh.hidden = true;
      refresh.classList.remove('is-ready');
      refresh.style.removeProperty('--pull');
    }
  }
  document.addEventListener('touchstart', event => {
    cancelPull();
    if (refreshing || scrollY > 0 || event.touches.length !== 1 ||
        document.querySelector('dialog[open]') || horizontalTarget(event.target)) return;
    const touch = event.touches[0];
    gesture = {x: touch.clientX, y: touch.clientY, pull: 0, vertical: false};
  }, {passive: true});
  document.addEventListener('touchmove', event => {
    if (!gesture) return;
    if (event.touches.length !== 1 || document.querySelector('dialog[open]')) return cancelPull();
    const dx = Math.abs(event.touches[0].clientX - gesture.x);
    const dy = event.touches[0].clientY - gesture.y;
    if (dy < 0 || dx > Math.abs(dy)) return cancelPull();
    if (!gesture.vertical && dy < 8) return;
    gesture.vertical = true;
    if (event.cancelable) event.preventDefault();
    gesture.pull = Math.min(110, dy * .5);
    refresh.hidden = false;
    refresh.style.setProperty('--pull', `${gesture.pull}px`);
    refresh.classList.toggle('is-ready', gesture.pull >= 70);
    refreshLabel.textContent = gesture.pull >= 70 ? '松开刷新' : '下拉刷新';
  }, {passive: false});
  document.addEventListener('touchend', () => {
    if (!gesture || gesture.pull < 70 || document.querySelector('dialog[open]')) return cancelPull();
    refreshing = true;
    gesture = null;
    refresh.classList.add('is-refreshing');
    refreshLabel.textContent = '刷新中…';
    refresh.querySelector('.refresh-symbol').textContent = '↻';
    const url = new URL(location.href);
    url.searchParams.set('r', Date.now().toString());
    requestAnimationFrame(() => requestAnimationFrame(() => location.replace(url.href)));
  }, {passive: true});
  document.addEventListener('touchcancel', cancelPull, {passive: true});
  addEventListener('pageshow', () => {
    refreshing = false;
    refresh.classList.remove('is-refreshing');
    refresh.querySelector('.refresh-symbol').textContent = '↓';
    cancelPull();
  });
}
