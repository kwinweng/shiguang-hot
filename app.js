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
