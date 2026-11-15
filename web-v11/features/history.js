'use strict';
(function () {
/**
 * 历史页：按北京日期翻看已上站条目。挂到 #view-history。
 * 约定：frontend 提供 window.Rebang.register(name, mount)；未合入前用测试桩。
 * mount(el, ctx) ctx.dataBase 默认 'data'；ctx.now 可注入当前时间；ctx.openItem(item) 打开详情。
 */
const EMPTY_MESSAGE = '这天没有内容';
const TZ = 'Asia/Shanghai';
const WEEK = ['周日', '周一', '周二', '周三', '周四', '周五', '周六'];

function beijingDate(value) {
  const date = value instanceof Date ? value : new Date(value);
  return new Intl.DateTimeFormat('en-CA', {
    timeZone: TZ, year: 'numeric', month: '2-digit', day: '2-digit',
  }).format(date);
}

function shiftDate(isoDate, days) {
  const [year, month, day] = isoDate.split('-').map(Number);
  const utc = new Date(Date.UTC(year, month - 1, day + days));
  const y = utc.getUTCFullYear();
  const m = String(utc.getUTCMonth() + 1).padStart(2, '0');
  const d = String(utc.getUTCDate()).padStart(2, '0');
  return `${y}-${m}-${d}`;
}

function formatDateLabel(isoDate) {
  const [year, month, day] = isoDate.split('-').map(Number);
  const utc = new Date(Date.UTC(year, month - 1, day, 4, 0, 0));
  return `${month}月${day}日 ${WEEK[utc.getUTCDay()]}`;
}

function esc(value) {
  return String(value ?? '').replace(/[&<>"']/g, (ch) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  }[ch]));
}

function displayTitle(item) {
  const trans = item.translated && item.translation;
  if (trans && trans.title) return trans.title;
  return item.title || item.summary || '';
}

function displaySummary(item) {
  const trans = item.translated && item.translation;
  if (trans && trans.summary) return trans.summary;
  return item.summary || '';
}

function imageUrl(item) {
  if (item.image && typeof item.image === 'object') return item.image.url || '';
  return typeof item.image === 'string' ? item.image : '';
}

function emptyPayload(date) {
  return { date, count: 0, empty: true, message: EMPTY_MESSAGE, items: [] };
}

async function fetchJson(url, fetchImpl) {
  const fn = fetchImpl || fetch;
  const res = await fn(url);
  if (!res || !res.ok) return null;
  return res.json();
}

function register(name, mountFn) {
  const root = typeof window !== 'undefined' ? window : globalThis;
  root.Rebang = root.Rebang || {};
  if (typeof root.Rebang.register === 'function') {
    root.Rebang.register(name, mountFn);
    return;
  }
  root.Rebang._queue = root.Rebang._queue || [];
  root.Rebang._queue.push([name, mountFn]);
}

function mount(el, ctx) {
  if (!el) return { open: async () => {} };
  const dataBase = (ctx && ctx.dataBase) || 'data';
  const fetchImpl = ctx && ctx.fetch;
  const openItem = (ctx && ctx.openItem) || function () {};
  let today = beijingDate((ctx && ctx.now) || new Date());
  let current = (ctx && ctx.date) || today;
  let indexDates = [];
  const state = { date: current, payload: emptyPayload(current) };

  el.innerHTML = `
    <div class="rebang-history sub">
      <div class="rebang-history-nav">
        <button type="button" class="rebang-history-prev" data-history-prev aria-label="前一天">前一天</button>
        <div class="rebang-history-current" data-history-label></div>
        <button type="button" class="rebang-history-next" data-history-next aria-label="后一天">后一天</button>
      </div>
      <div class="dates" data-history-dates></div>
      <div class="list" data-history-list></div>
    </div>`;

  const prevBtn = el.querySelector('[data-history-prev]');
  const nextBtn = el.querySelector('[data-history-next]');
  const labelEl = el.querySelector('[data-history-label]');
  const datesEl = el.querySelector('[data-history-dates]');
  const listEl = el.querySelector('[data-history-list]');

  function countOf(date) {
    const row = indexDates.find((d) => d.date === date);
    return row ? row.count : 0;
  }

  function renderShell() {
    el.dataset.historyDate = current;
    labelEl.textContent = formatDateLabel(current);
    prevBtn.disabled = false;
    nextBtn.disabled = current >= today;
    const chips = indexDates.slice();
    if (!chips.some((d) => d.date === current)) {
      chips.push({ date: current, count: countOf(current) });
      chips.sort((a, b) => b.date.localeCompare(a.date));
    }
    datesEl.innerHTML = chips.map((row) => (
      `<button type="button" class="chip${row.date === current ? ' on' : ''}" data-history-chip="${esc(row.date)}">${esc(formatDateLabel(row.date))}</button>`
    )).join('');
  }

  function renderList(payload) {
    state.date = current;
    state.payload = payload;
    el.dataset.historyDate = current;
    if (!payload || payload.empty || !payload.items || !payload.items.length) {
      el.dataset.historyEmpty = 'true';
      const message = (payload && payload.message) || EMPTY_MESSAGE;
      listEl.innerHTML = `<p class="muted" data-history-empty>${esc(formatDateLabel(current))} ${esc(message)}</p>`;
      return;
    }
    el.dataset.historyEmpty = 'false';
    listEl.innerHTML = payload.items.map((item) => {
      const img = imageUrl(item);
      const title = displayTitle(item);
      const summary = displaySummary(item);
      const when = item.published_at ? formatDateLabel(beijingDate(item.published_at)) : '';
      return `<article class="row-item${img ? '' : ' noimg'}" data-item-id="${esc(item.id)}" role="button" tabindex="0">
        ${img ? `<img src="${esc(img)}" alt="">` : ''}
        <div>
          <div class="src">${esc(item.source_name || '')}${when ? ' · ' + esc(when) : ''}</div>
          <h3>${esc(title)}</h3>
          ${summary ? `<p class="excerpt">${esc(summary)}</p>` : ''}
        </div>
      </article>`;
    }).join('');
  }

  async function show(date) {
    current = date;
    renderShell();
    listEl.innerHTML = '<p class="muted">正在加载…</p>';
    const payload = await fetchJson(`${dataBase}/history/${date}.json`, fetchImpl);
    if (!payload || payload.empty || !(payload.items || []).length) {
      renderList(payload && payload.message ? payload : emptyPayload(date));
      return state;
    }
    renderList(payload);
    return state;
  }

  datesEl.addEventListener('click', (event) => {
    const chip = event.target.closest('[data-history-chip]');
    if (chip) show(chip.getAttribute('data-history-chip'));
  });
  prevBtn.addEventListener('click', () => show(shiftDate(current, -1)));
  nextBtn.addEventListener('click', () => {
    const next = shiftDate(current, 1);
    if (next <= today) show(next);
  });
  listEl.addEventListener('click', (event) => {
    const row = event.target.closest('[data-item-id]');
    if (!row) return;
    const item = (state.payload.items || []).find((it) => it.id === row.getAttribute('data-item-id'));
    if (item) openItem(item);
  });

  async function boot() {
    const index = await fetchJson(`${dataBase}/history/index.json`, fetchImpl);
    indexDates = (index && index.dates) || [];
    if (!indexDates.some((d) => d.date === current) && indexDates.length && current === today) {
      // 今天还没有内容时，先停在今天，让空日期说明可见；用户可向前翻有内容的日期。
    }
    return show(current);
  }

  const ready = boot();
  return { show, ready, get date() { return current; }, EMPTY_MESSAGE, formatDateLabel };
}

const api = {
  mount, beijingDate, shiftDate, formatDateLabel, emptyPayload, EMPTY_MESSAGE, displayTitle,
};

if (typeof module !== 'undefined' && module.exports) {
  module.exports = api;
}
if (typeof window !== 'undefined') {
  window.RebangHistory = api;
  register('history', mount);
}

})();
