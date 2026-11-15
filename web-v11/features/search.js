'use strict';
(function () {
/**
 * 顶部搜索：纯前端匹配已上站的标题、说明、来源名，以及推文/条目的译文和原文。
 * 不为每条再写 AI 摘要。挂到 #search-panel。
 * 约定：window.Rebang.register('search', mount)。
 */
const HINT = '输入关键词，搜索标题、说明、来源，或推文的译文和原文。';
const PLACEHOLDER = '搜索标题、说明或来源';

function esc(value) {
  return String(value ?? '').replace(/[&<>"']/g, (ch) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  }[ch]));
}

function normalize(value) {
  return String(value || '').toLowerCase();
}

function fieldsOf(entry) {
  return [
    entry.title,
    entry.summary,
    entry.source_name,
    entry.display_title,
    entry.display_summary,
    entry.translation_title,
    entry.translation_summary,
    entry.original_title,
    entry.original_summary,
    entry.translation && entry.translation.title,
    entry.translation && entry.translation.summary,
  ].filter((value) => value != null && value !== '');
}

function match(entry, query) {
  const needle = normalize(query).trim();
  if (!needle) return false;
  return fieldsOf(entry).some((value) => normalize(value).includes(needle));
}

function search(entries, query) {
  const needle = normalize(query).trim();
  if (!needle) return [];
  return (entries || []).filter((entry) => match(entry, needle));
}

function displayTitle(entry) {
  return entry.display_title || (entry.translated && entry.translation && entry.translation.title)
    || entry.translation_title || entry.title || entry.summary || '';
}

function displaySummary(entry) {
  if (entry.display_summary) return entry.display_summary;
  if (entry.translated && entry.translation && entry.translation.summary) return entry.translation.summary;
  return entry.translation_summary || entry.summary || '';
}

function imageUrl(entry) {
  if (entry.image && typeof entry.image === 'object') return entry.image.url || '';
  return typeof entry.image === 'string' ? entry.image : '';
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

async function loadIndex(ctx) {
  if (ctx && Array.isArray(ctx.entries)) return ctx.entries;
  const dataBase = (ctx && ctx.dataBase) || 'data';
  const fn = (ctx && ctx.fetch) || fetch;
  const res = await fn(`${dataBase}/search-index.json`);
  if (!res || !res.ok) return [];
  const payload = await res.json();
  return (payload && payload.entries) || [];
}

function mount(el, ctx) {
  if (!el) return { query: async () => [] };
  const openItem = (ctx && ctx.openItem) || function () {};
  let entries = [];
  el.classList.add('overlay', 'rebang-search');
  el.innerHTML = `
    <div class="search-bar">
      <input id="q" data-search-input type="search" placeholder="${esc(PLACEHOLDER)}" autocomplete="off">
      <button class="cancel" type="button" data-search-close>取消</button>
    </div>
    <div class="sub"><div class="list" data-search-list></div></div>`;
  const input = el.querySelector('[data-search-input]');
  const listEl = el.querySelector('[data-search-list]');
  const closeBtn = el.querySelector('[data-search-close]');

  function render(query, hits) {
    el.dataset.searchQuery = query || '';
    el.dataset.searchCount = String(hits.length);
    if (!query) {
      listEl.innerHTML = `<p class="muted" data-search-hint>${esc(HINT)}</p>`;
      return hits;
    }
    if (!hits.length) {
      listEl.innerHTML = `<p class="muted" data-search-empty>没有找到「${esc(query)}」。</p>`;
      return hits;
    }
    listEl.innerHTML = hits.map((entry) => {
      const img = imageUrl(entry);
      const summary = displaySummary(entry);
      return `<article class="row-item${img ? '' : ' noimg'}" data-item-id="${esc(entry.id)}" data-search-hit="${esc(entry.id)}" role="button" tabindex="0">
        ${img ? `<img src="${esc(img)}" alt="">` : ''}
        <div>
          <div class="src">${esc(entry.source_name || '')}</div>
          <h3>${esc(displayTitle(entry))}</h3>
          ${summary ? `<p class="excerpt">${esc(summary)}</p>` : ''}
        </div>
      </article>`;
    }).join('');
    return hits;
  }

  function run() {
    const query = input.value.trim();
    return render(query, search(entries, query));
  }

  function open() {
    el.classList.add('on');
    render('', []);
    input.value = '';
    setTimeout(() => input.focus(), 50);
  }

  function close() {
    el.classList.remove('on');
    input.value = '';
    render('', []);
  }

  input.addEventListener('input', run);
  closeBtn.addEventListener('click', close);
  listEl.addEventListener('click', (event) => {
    const row = event.target.closest('[data-item-id]');
    if (!row) return;
    const item = entries.find((it) => it.id === row.getAttribute('data-item-id'));
    if (item) {
      close();
      openItem(item);
    }
  });

  const button = (ctx && ctx.searchButton) || (typeof document !== 'undefined' && document.getElementById('btnSearch'));
  if (button && !button.dataset.rebangSearchBound) {
    button.dataset.rebangSearchBound = '1';
    button.addEventListener('click', open);
  }

  const ready = loadIndex(ctx).then((loaded) => {
    entries = loaded;
    render('', []);
    return entries;
  });

  return { open, close, run, query: (text) => { input.value = text; return run(); }, ready, HINT, PLACEHOLDER };
}

const api = { match, search, fieldsOf, normalize, mount, loadIndex, HINT, PLACEHOLDER, displayTitle };

if (typeof module !== 'undefined' && module.exports) {
  module.exports = api;
}
if (typeof window !== 'undefined') {
  window.RebangSearch = api;
  register('search', mount);
}

})();
