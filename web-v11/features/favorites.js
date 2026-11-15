'use strict';
(function () {
/**
 * 收藏：只在详情页提供按钮，记录存在本机 localStorage，键为条目 id。
 * 挂到 #view-favorites。换设备或清理数据会消失。
 * 约定：window.Rebang.register('favorites', mount)；详情页调用 attachButton(slot, item, ctx)。
 */
const STORAGE_KEY = 'rebang.favorites.v1';
const DEVICE_NOTE = '收藏按钮只在打开正文之后才会出现。记录只存在这台设备的浏览器里，换手机或清理数据会消失。';
const EMPTY_TEXT = '还没有收藏。打开一篇正文或一条推文，再点收藏。收藏只存在这台设备的浏览器里，换手机或清理数据会消失。';

function defaultStorage() {
  if (typeof localStorage !== 'undefined') return localStorage;
  throw new Error('没有可用的 localStorage');
}

function storageOf(ctx) {
  return (ctx && ctx.storage) || defaultStorage();
}

function esc(value) {
  return String(value ?? '').replace(/[&<>"']/g, (ch) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  }[ch]));
}

function snapshot(item) {
  const trans = item.translation && typeof item.translation === 'object' ? {
    title: item.translation.title || '',
    summary: item.translation.summary || '',
    label: item.translation.label || '',
  } : null;
  const image = item.image && typeof item.image === 'object' && item.image.url
    ? { url: item.image.url } : (typeof item.image === 'string' && item.image ? { url: item.image } : null);
  return {
    id: item.id,
    kind: item.kind || 'news',
    channel: item.channel == null ? null : item.channel,
    source_id: item.source_id || '',
    source_name: item.source_name || '',
    title: item.title || '',
    summary: item.summary || '',
    url: item.url || '',
    published_at: item.published_at || '',
    lang: item.lang || '',
    translated: !!item.translated,
    translation: item.translated ? trans : null,
    image,
  };
}

function load(storage) {
  const raw = storage.getItem(STORAGE_KEY);
  if (!raw) return [];
  try {
    const parsed = JSON.parse(raw);
    if (Array.isArray(parsed)) {
      // 兼容只存了 id 列表的旧格式。
      return parsed.map((entry) => (typeof entry === 'string' ? { id: entry } : entry)).filter((e) => e && e.id);
    }
    if (parsed && Array.isArray(parsed.items)) return parsed.items.filter((e) => e && e.id);
  } catch (error) {
    return [];
  }
  return [];
}

function save(items, storage) {
  storage.setItem(STORAGE_KEY, JSON.stringify({ version: 1, items }));
  return items;
}

function list(storage) {
  return load(storage);
}

function isFavorite(id, storage) {
  return load(storage).some((item) => item.id === id);
}

function add(item, storage) {
  if (!item || !item.id) return load(storage);
  const items = load(storage).filter((entry) => entry.id !== item.id);
  items.unshift(snapshot(item));
  return save(items, storage);
}

function remove(id, storage) {
  return save(load(storage).filter((entry) => entry.id !== id), storage);
}

function toggle(item, storage) {
  if (isFavorite(item.id, storage)) return { items: remove(item.id, storage), on: false };
  return { items: add(item, storage), on: true };
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

function renderList(el, items, openItem) {
  const listEl = el.querySelector('[data-favorites-list]');
  if (!items.length) {
    el.dataset.favoritesEmpty = 'true';
    listEl.innerHTML = `<p class="muted" data-favorites-empty>${esc(EMPTY_TEXT)}</p>`;
    return;
  }
  el.dataset.favoritesEmpty = 'false';
  listEl.innerHTML = items.map((item) => {
    const img = imageUrl(item);
    return `<article class="row-item${img ? '' : ' noimg'}" data-item-id="${esc(item.id)}" role="button" tabindex="0">
      ${img ? `<img src="${esc(img)}" alt="">` : ''}
      <div>
        <div class="src">${esc(item.source_name || '')}</div>
        <h3>${esc(displayTitle(item))}</h3>
        ${displaySummary(item) ? `<p class="excerpt">${esc(displaySummary(item))}</p>` : ''}
      </div>
    </article>`;
  }).join('');
}

function attachButton(host, item, ctx) {
  if (!host || !item) return null;
  const storage = storageOf(ctx);
  const onChange = ctx && ctx.onChange;
  const toast = ctx && ctx.toast;
  host.innerHTML = '';
  const btn = document.createElement('button');
  btn.type = 'button';
  btn.className = 'rebang-fav-btn fav';
  btn.setAttribute('data-favorite-button', item.id);
  function sync() {
    const on = isFavorite(item.id, storage);
    btn.classList.toggle('on', on);
    btn.textContent = on ? '取消收藏' : '收藏这条';
    btn.setAttribute('aria-pressed', on ? 'true' : 'false');
  }
  btn.addEventListener('click', (event) => {
    event.preventDefault();
    event.stopPropagation();
    const result = toggle(item, storage);
    sync();
    if (typeof onChange === 'function') onChange(result.items, result.on);
    if (typeof toast === 'function') {
      toast(result.on ? '已收藏，只存在这台设备的浏览器里，换手机或清理数据会消失' : '已取消收藏');
    }
  });
  sync();
  host.appendChild(btn);
  return btn;
}

function mount(el, ctx) {
  if (!el) return { refresh() {} };
  const storage = storageOf(ctx);
  const openItem = (ctx && ctx.openItem) || function () {};
  el.innerHTML = `
    <div class="rebang-favorites sub">
      <h2 class="ch" style="margin:0 0 8px">收藏</h2>
      <p class="desc" data-favorites-note style="margin:0 0 14px">${esc(DEVICE_NOTE)}</p>
      <div class="list" data-favorites-list></div>
    </div>`;
  function refresh() {
    const items = load(storage);
    renderList(el, items, openItem);
    return items;
  }
  el.querySelector('[data-favorites-list]').addEventListener('click', (event) => {
    const row = event.target.closest('[data-item-id]');
    if (!row) return;
    const item = load(storage).find((it) => it.id === row.getAttribute('data-item-id'));
    if (item) openItem(item);
  });
  refresh();
  if (ctx) ctx.onChange = (function (prev) {
    return function () {
      refresh();
      if (typeof prev === 'function') prev.apply(this, arguments);
    };
  }(ctx.onChange));
  return { refresh, attachButton: (host, item) => attachButton(host, item, { storage, onChange: refresh, toast: ctx && ctx.toast }) };
}

const api = {
  STORAGE_KEY, DEVICE_NOTE, EMPTY_TEXT, snapshot, load, save, list, isFavorite, add, remove, toggle,
  attachButton, mount, displayTitle,
};

if (typeof module !== 'undefined' && module.exports) {
  module.exports = api;
}
if (typeof window !== 'undefined') {
  window.RebangFavorites = api;
  register('favorites', mount);
}

})();
