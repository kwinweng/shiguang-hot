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
  document.querySelectorAll('.pill').forEach(pill => pill.classList.toggle('selected', pill === button));
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
const selections = [...document.querySelectorAll('.bottom,.desktop-nav.g-seg,.filters')].map(control => {
  const indicator = document.createElement('span');
  indicator.className = 'selection-pill';
  indicator.setAttribute('aria-hidden', 'true');
  control.prepend(indicator);
  const items = [...control.querySelectorAll('a,.pill')];
  let selected = control.querySelector('.active,.selected');
  function position() {
    indicator.hidden = !selected;
    if (!selected) return;
    indicator.style.setProperty('--pill-x', `${selected.offsetLeft}px`);
    indicator.style.setProperty('--pill-y', `${selected.offsetTop}px`);
    indicator.style.setProperty('--pill-width', `${selected.offsetWidth}px`);
    indicator.style.setProperty('--pill-height', `${selected.offsetHeight}px`);
  }
  items.forEach(item => {
    if (item.matches('button')) item.setAttribute('aria-pressed', String(item === selected));
    item.addEventListener('click', event => {
      if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
      selected = item;
      items.forEach(other => {
        other.classList.toggle(other.matches('button') ? 'selected' : 'active', other === item);
        if (other.matches('button')) other.setAttribute('aria-pressed', String(other === item));
      });
      position();
    });
  });
  position();
  requestAnimationFrame(() => control.classList.add('glass-ready'));
  new ResizeObserver(position).observe(control);
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
