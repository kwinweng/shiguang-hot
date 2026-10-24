'use strict';

const params = new URLSearchParams(location.search);
const state = {
  theme: ['light', 'dark'].includes(params.get('t')) ? params.get('t') : (matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'),
  section: 'news',
  tab: 'live',
  category: '全部',
  channel: null,
  exploreTab: 'play',
  exploreTag: '全部',
  day: null,
  dayTab: 'hot',
  pickerMonth: null,
  status: 'ok',
};
const root = document.getElementById('app');
const escapeHTML = value => String(value).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const icon = (name, size = '') => {
  const key = (name || '').replace(/-line$/, '') + '_line';
  return `<span class="i ${size}">${ICONS[key] || ''}</span>`;
};

const CATEGORY_ICONS = { 全部: 'squares-four', 新闻: 'newspaper', 财经: 'chart-line-up', 消费: 'shopping-bag', 科技: 'cpu' };
const SECTIONS = [['news', 'house', '资讯'], ['explore', 'compass', '探索'], ['mine', 'user-circle', '我的']];
const NEWS_TABS = [['live', '实时'], ['hot', '热点'], ['review', '回顾']];
const EXPLORE_TABS = [['play', '好玩'], ['kan', '好看'], ['buy', '好买']];
const EXPLORE_KINDS = { play: '好玩', kan: '好看', buy: '好买' };
const KAN_TAGS = ['剧', '电影', '小说', '展览'];
const WEEKDAYS = '日一二三四五六';
const STAMP = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})/;

function buildEvent(item) {
  const m = STAMP.exec(item.ts);
  const year = Number(m[1]), month = Number(m[2]), day = Number(m[3]);
  return {
    id: `real-${item.id}`,
    itemId: item.id,
    category: item.category,
    title: item.title,
    summary: item.summary,
    image: item.image || null,
    sourceId: item.ch,
    sourceName: CHANNEL_NAMES[item.ch] || item.ch,
    dateKey: `${m[1]}-${m[2]}-${m[3]}`,
    date: `${month}月${day}日`,
    weekday: `周${WEEKDAYS[new Date(Date.UTC(year, month - 1, day)).getUTCDay()]}`,
    time: `${m[4]}:${m[5]}`,
    stamp: Date.parse(item.ts),
    count: 1,
  };
}

const EVENTS = REAL_ITEMS.map(buildEvent).sort((a, b) => b.stamp - a.stamp || b.itemId - a.itemId);
const NEWEST_STAMP = EVENTS[0].stamp;
EVENTS.forEach(event => {
  const ageHours = Math.max(0, (NEWEST_STAMP - event.stamp) / 3600000);
  event.heat = event.title.length * 2 + event.summary.length + Math.round(Math.max(0, 96 - ageHours) * 6);
});

// Per-day hot snapshot: every item of that day ranked with the same heat rule as 热点.
const HOT_SNAPSHOTS = {};
EVENTS.forEach(event => {
  (HOT_SNAPSHOTS[event.dateKey] || (HOT_SNAPSHOTS[event.dateKey] = [])).push(event);
});
Object.keys(HOT_SNAPSHOTS).forEach(day => {
  HOT_SNAPSHOTS[day].sort((a, b) => b.heat - a.heat || b.stamp - a.stamp);
  HOT_SNAPSHOTS[day] = HOT_SNAPSHOTS[day].map(event => event.itemId);
});
const SNAPSHOT_DAYS = Object.keys(HOT_SNAPSHOTS).sort();
const SNAPSHOT_RETENTION_DAYS = 90;

const NEWEST_BY_CHANNEL = {};
REAL_ITEMS.forEach(item => {
  if (!NEWEST_BY_CHANNEL[item.ch] || Date.parse(item.ts) > Date.parse(NEWEST_BY_CHANNEL[item.ch])) {
    NEWEST_BY_CHANNEL[item.ch] = item.ts;
  }
});
// Preview-only seed: a few channels were last read a few hours before their newest post.
const CHANNEL_SEED_HOURS = {
  xhqcankao: 6,
  freechinese: 4,
  HuaErJie1: 4,
  pelosi3: 2,
  CE_Observe: 2,
  zaihuapd: 2,
  NewlearnerChannel: 3,
};
const LAST_SEEN_KEY = 'rebang.lastSeen';

function seedLastSeen() {
  const seeded = {};
  CHANNELS.forEach(channel => {
    const newest = NEWEST_BY_CHANNEL[channel.id];
    if (!newest) return;
    const hours = CHANNEL_SEED_HOURS[channel.id];
    seeded[channel.id] = hours ? new Date(Date.parse(newest) - hours * 3600000).toISOString() : newest;
  });
  return seeded;
}
function readLastSeen() {
  try {
    const raw = localStorage.getItem(LAST_SEEN_KEY);
    if (raw) {
      const parsed = JSON.parse(raw);
      if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
        const seeded = seedLastSeen();
        let added = false;
        CHANNELS.forEach(channel => {
          if (typeof parsed[channel.id] !== 'string' && typeof seeded[channel.id] === 'string') {
            parsed[channel.id] = seeded[channel.id];
            added = true;
          }
        });
        if (added) {
          try { localStorage.setItem(LAST_SEEN_KEY, JSON.stringify(parsed)); } catch (error) {}
        }
        return parsed;
      }
    }
  } catch (error) {}
  const seeded = seedLastSeen();
  try { localStorage.setItem(LAST_SEEN_KEY, JSON.stringify(seeded)); } catch (error) {}
  return seeded;
}
function persistLastSeen() {
  try { localStorage.setItem(LAST_SEEN_KEY, JSON.stringify(lastSeen)); } catch (error) {}
}
function unreadCount(channelId) {
  const seen = Date.parse(lastSeen[channelId]);
  if (!Number.isFinite(seen)) return 0;
  return REAL_ITEMS.filter(item => item.ch === channelId && Date.parse(item.ts) > seen).length;
}
let lastSeen = readLastSeen();

const allExplore = () => [
  ...(window.PLAY || []).map(item => ({ ...item, kind: KAN_TAGS.includes(item.tag) ? 'kan' : 'play' })),
  ...(window.BUY || []).map(item => ({ ...item, kind: 'buy' })),
];
const exploreByKind = kind => allExplore().filter(item => item.kind === kind);
const exploreTags = kind => ['全部', ...new Set(exploreByKind(kind).map(item => item.tag))];

let lastFocus = null;
let pendingFocus = null;
let touchStart = null;
let ptrTimer = null;
const scrollMemory = { news: 0, explore: 0, mine: 0 };
let lastSection = state.section;

function filteredEvents() {
  if (state.status === 'empty') return [];
  return EVENTS.filter(event =>
    (state.category === '全部' || event.category === state.category) &&
    (!state.channel || event.sourceId === state.channel)
  );
}
function readRoute() {
  const parts = location.hash.slice(1).split('/');
  if (parts[0] === 'explore') {
    const item = allExplore().find(x => x.id === parts[1]);
    return item ? { type: 'explore', item } : null;
  }
  if (parts[0] === 'event' || parts[0] === 'source') {
    const event = EVENTS.find(e => e.id === parts[1]);
    if (event) return { type: parts[0], event };
  }
  if (parts[0] === 'about') return { type: 'about' };
  if (parts[0] === 'calendar') return { type: 'calendar' };
  if (parts[0] === 'group' && state.category !== '全部') return { type: 'group' };
  return null;
}
function openRoute(route) {
  lastFocus = document.activeElement;
  location.hash = route;
}
function closeRoute(resetScroll = false) {
  pendingFocus = lastFocus;
  lastFocus = null;
  const hadHash = !!location.hash;
  if (hadHash) location.hash = '';
  if (resetScroll) render(false);
  else if (!hadHash) render(true);
}
function selectCategory(value) {
  state.category = value;
  state.channel = null;
  state.status = 'ok';
  render();
  root.querySelector('.category-rail .on')?.scrollIntoView({ inline: 'center', block: 'nearest' });
}
function moveCategory(step) {
  if (state.day) return;
  const index = CATEGORIES.indexOf(state.category);
  const next = Math.min(CATEGORIES.length - 1, Math.max(0, index + step));
  if (next !== index) selectCategory(CATEGORIES[next]);
}
function moveExploreTab(step) {
  const index = EXPLORE_TABS.findIndex(([id]) => id === state.exploreTab);
  const next = Math.min(EXPLORE_TABS.length - 1, Math.max(0, index + step));
  if (next === index) return;
  state.exploreTab = EXPLORE_TABS[next][0];
  state.exploreTag = '全部';
  state.status = 'ok';
  render();
}

function renderCategoryRail() {
  return `<div class="category-rail" role="group" aria-label="一级分类">${CATEGORIES.map(category =>
    `<button data-action="category" data-value="${category}" class="${state.category === category ? 'on' : ''}" aria-pressed="${state.category === category}">${icon(CATEGORY_ICONS[category], 'sm')}<span>${category}</span></button>`).join('')}</div>`;
}
function revealSelectedCategory() {
  const rail = root.querySelector('.category-rail');
  const selected = rail?.querySelector('button.on');
  if (!rail || !selected) return;
  const railBox = rail.getBoundingClientRect();
  const buttonBox = selected.getBoundingClientRect();
  const margin = parseFloat(getComputedStyle(rail).getPropertyValue('--rail-fade')) + 6;
  const offsetLeft = buttonBox.left - railBox.left + rail.scrollLeft;
  const offsetRight = offsetLeft + buttonBox.width;
  if (offsetLeft < rail.scrollLeft + margin) rail.scrollLeft = offsetLeft - margin;
  else if (offsetRight > rail.scrollLeft + rail.clientWidth - margin) rail.scrollLeft = offsetRight - rail.clientWidth + margin;
}
function updateRailFade(rail) {
  rail.classList.toggle('can-scroll-right', rail.scrollWidth - rail.clientWidth - rail.scrollLeft > 1);
}
function syncRailFades() {
  root.querySelectorAll('.category-rail').forEach(updateRailFade);
}
function categoryChannels() {
  return CHANNELS.filter(channel => channel.category === state.category);
}
function categoryUnreadTotal() {
  return categoryChannels().reduce((total, channel) => total + unreadCount(channel.id), 0);
}
function renderGroupButton() {
  if (state.category === '全部') return '';
  const unread = categoryUnreadTotal();
  const expanded = readRoute()?.type === 'group';
  const label = unread ? `选择群组，${unread} 条未读` : '选择群组';
  return `<button class="group-btn${state.channel ? ' on' : ''}" data-action="group" aria-label="${label}" aria-haspopup="dialog" aria-expanded="${expanded}">${icon('users-three')}<span class="group-label">群组</span>${unread ? `<span class="group-dot" aria-label="${unread} 条未读">${unread}</span>` : ''}</button>`;
}
function renderChannelTag() {
  const channel = CHANNELS.find(item => item.id === state.channel);
  if (!channel) return '';
  return `<span class="channel-tag"><span class="channel-tag-name">${escapeHTML(channel.name)}</span><button class="channel-tag-clear" data-action="clear-channel" aria-label="清除频道筛选">${icon('x', 'sm')}</button></span>`;
}
function renderFilters() {
  const actions = state.category === '全部' ? '' : `<div class="filter-actions">${renderChannelTag()}${renderGroupButton()}</div>`;
  return `<div class="filters">${renderCategoryRail()}${actions}</div>`;
}
function renderGroupSheet() {
  return `<div class="group-list">${categoryChannels().map(channel => {
    const unread = unreadCount(channel.id);
    return `<button class="group-option${state.channel === channel.id ? ' on' : ''}" data-action="pick-channel" data-ch="${channel.id}" data-value="${channel.id}" aria-pressed="${state.channel === channel.id}"><span class="group-option-name">${escapeHTML(channel.name)}</span>${unread ? `<span class="unread-badge" aria-label="${unread} 条未读">${unread}</span>` : ''}</button>`;
  }).join('')}</div>`;
}
function renderStory(event) {
  const merged = event.count > 1 ? `<span class="merged">${icon('users-three', 'sm')}${event.count} 个频道在说${icon('caret-right', 'sm')}</span>` : '';
  const image = event.image ? `<img class="feed-img" src="${escapeHTML(event.image)}" alt="" loading="lazy" decoding="async">` : '';
  return `<article class="story${event.image ? ' has-img' : ''}" data-event="${event.id}" data-category="${event.category}" data-ch="${event.sourceId}">
    <button class="story-button" data-action="event" data-value="${event.id}" aria-label="${escapeHTML(event.title)}，查看详情">
      <span class="story-category">${event.category}</span>
      <span class="story-text"><span class="story-title">${escapeHTML(event.title)}</span><span class="story-meta">${escapeHTML(event.sourceName)} · ${event.time}</span>${merged}</span>
      ${image}
    </button>
  </article>`;
}
function renderHotCard(event, index, maxHeat) {
  const top = index < 3;
  const width = ((event.heat / maxHeat) * 100).toFixed(2);
  return `<article class="hot-card ${top ? 'hot-top' : 'hot-row'}" data-event="${event.id}" data-category="${event.category}" data-ch="${event.sourceId}" data-heat="${event.heat}">
    <button class="hot-button" data-action="event" data-value="${event.id}" aria-label="${escapeHTML(event.title)}，查看详情">
      <span class="hot-rank">${String(index + 1).padStart(2, '0')}</span>
      <span class="hot-body">
        <span class="hot-title">${escapeHTML(event.title)}</span>
        ${event.count > 1 ? `<span class="hot-channels">${event.count} 个频道在说</span>` : ''}
        <span class="hot-heat" aria-hidden="true"><span class="hot-bar" style="width:${width}%"></span></span>
        ${top
          ? `<span class="hot-meta">${event.category} · ${escapeHTML(event.sourceName)} · ${event.time}</span>`
          : `<span class="hot-source">${escapeHTML(event.sourceName)} · ${event.time}</span>`}
      </span>
    </button>
  </article>`;
}
function groupReviewDays(events, limit = 5) {
  const groups = new Map();
  events.forEach(event => {
    if (!groups.has(event.dateKey)) {
      groups.set(event.dateKey, { dateKey: event.dateKey, date: event.date, weekday: event.weekday, items: [] });
    }
    groups.get(event.dateKey).items.push(event);
  });
  return [...groups.values()]
    .sort((a, b) => b.dateKey.localeCompare(a.dateKey))
    .map(group => {
      const items = group.items
        .slice()
        .sort((a, b) => b.heat - a.heat || b.stamp - a.stamp)
        .slice(0, limit)
        .sort((a, b) => b.stamp - a.stamp);
      return { ...group, items };
    });
}
function renderReviewItem(event) {
  return `<button class="review-item" data-action="event" data-value="${event.id}" data-category="${event.category}" data-ch="${event.sourceId}" aria-label="${escapeHTML(event.title)}，查看详情">
    <span class="review-time">${event.time}</span>
    <span><span class="review-title">${escapeHTML(event.title)}</span><span class="review-source">${escapeHTML(event.sourceName)}${event.count > 1 ? ` · ${event.count} 个频道在说` : ''}</span></span>
  </button>`;
}
function renderReviewDay(group) {
  return `<section class="review-day" data-day="${group.dateKey}">
    <header class="review-date"><h2>${group.date}</h2><span>${group.weekday}</span><small>${group.items.length} 件事</small></header>
    <div class="review-items">${group.items.map(renderReviewItem).join('')}</div>
  </section>`;
}
function renderFeed() {
  const events = filteredEvents();
  if (state.tab === 'hot') events.sort((a, b) => b.heat - a.heat || b.stamp - a.stamp);
  const groups = state.tab === 'review' ? groupReviewDays(events) : [];
  const label = state.tab === 'live' ? '最新动态' : state.tab === 'hot' ? '正在被关注' : '按天回顾';
  const headingIcon = state.tab === 'live' ? '<span class="live-dot"></span>' : icon(state.tab === 'hot' ? 'sparkle' : 'clock-counter-clockwise', 'sm');
  const rendered = groups.reduce((total, group) => total + group.items.length, 0);
  const count = state.status === 'error' ? '更新中断'
    : state.tab === 'review' ? `${groups.length} 天 · ${rendered} 件事`
    : `${events.length} 件事`;
  let body;
  if (state.status === 'error') {
    body = `<div class="empty">${icon('warning-circle')}<p>加载失败</p><button class="text-button" data-action="retry">重试</button></div>`;
  } else if (!events.length) {
    body = `<div class="empty">${icon('magnifying-glass')}<p>暂无相关内容</p><button class="text-button" data-action="clear">清除筛选</button></div>`;
  } else if (state.tab === 'live') {
    body = `<div class="stories">${events.map(renderStory).join('')}</div><div class="list-end">已看完本次内容 · 本地数据</div>`;
  } else if (state.tab === 'hot') {
    const maxHeat = Math.max(...events.map(event => event.heat));
    body = `<div class="hot-list">${events.map((event, index) => renderHotCard(event, index, maxHeat)).join('')}</div><div class="list-end">已看完本次内容 · 本地数据</div>`;
  } else {
    body = `<div class="review-timeline">${groups.map(renderReviewDay).join('')}</div><div class="list-end">已到最早一天 · 本地数据</div>`;
  }
  const tools = state.tab === 'review'
    ? `<span class="feed-tools"><span class="count" role="status">${count}</span><button class="icon-button calendar-btn" data-action="calendar" aria-label="选择日期">${icon('calendar-blank')}</button></span>`
    : `<span class="count" role="status">${count}</span>`;
  return `<div class="feed-heading"><span class="heading-label">${headingIcon}${label}</span>${tools}</div>${body}`;
}
function dayLabel(dateKey) {
  const [, month, day] = dateKey.split('-').map(Number);
  return `${month}月${day}日`;
}
function snapshotWindow() {
  const today = SNAPSHOT_DAYS[SNAPSHOT_DAYS.length - 1];
  const minDay = new Date(Date.parse(`${today}T00:00:00Z`) - (SNAPSHOT_RETENTION_DAYS - 1) * 86400000).toISOString().slice(0, 10);
  return { today, minDay, minMonth: minDay.slice(0, 7), maxMonth: today.slice(0, 7) };
}
function renderDatePicker() {
  const { today, minDay, minMonth, maxMonth } = snapshotWindow();
  const current = state.pickerMonth && state.pickerMonth >= minMonth && state.pickerMonth <= maxMonth ? state.pickerMonth : maxMonth;
  const [year, month] = current.split('-').map(Number);
  const lead = new Date(Date.UTC(year, month - 1, 1)).getUTCDay();
  const total = new Date(Date.UTC(year, month, 0)).getUTCDate();
  const weekdays = [...WEEKDAYS].map(day => `<span class="date-weekday">${day}</span>`).join('');
  const blanks = Array.from({ length: lead }, () => '<span class="date-blank" aria-hidden="true"></span>').join('');
  const days = Array.from({ length: total }, (_, index) => {
    const day = index + 1;
    const key = `${year}-${String(month).padStart(2, '0')}-${String(day).padStart(2, '0')}`;
    const hasSnapshot = key >= minDay && key <= today && !!HOT_SNAPSHOTS[key];
    return `<button class="date-day${hasSnapshot ? ' has-snapshot' : ''}${state.day === key ? ' on' : ''}" data-action="pick-day" data-day="${key}" data-value="${key}" ${hasSnapshot ? '' : 'disabled'} aria-label="${dayLabel(key)}${hasSnapshot ? '，有快照' : '，无快照'}">${day}</button>`;
  }).join('');
  const prev = current > minMonth;
  const next = current < maxMonth;
  return `<div class="date-picker">
    <div class="date-picker-month">
      <button class="icon-button" data-action="picker-month" data-value="-1" aria-label="上个月"${prev ? '' : ' disabled'}>${icon('caret-left')}</button>
      <span>${year}年${month}月 <small>近 ${SNAPSHOT_RETENTION_DAYS} 天</small></span>
      <button class="icon-button" data-action="picker-month" data-value="1" aria-label="下个月"${next ? '' : ' disabled'}>${icon('caret-right')}</button>
    </div>
    <div class="date-grid">${weekdays}${blanks}${days}</div>
    <p class="date-picker-note">只有存过热榜快照的日期可选；每日快照保留 ${SNAPSHOT_RETENTION_DAYS} 天。</p>
  </div>`;
}
function renderDayView() {
  const key = state.day;
  const events = (HOT_SNAPSHOTS[key] || []).map(itemId => EVENTS.find(event => event.itemId === itemId)).filter(Boolean);
  const label = dayLabel(key);
  const mode = state.dayTab === 'review' ? '回顾' : '热点';
  const tools = `<span class="feed-tools"><button class="text-button day-today" data-action="day-today">回到今天</button><button class="icon-button calendar-btn" data-action="calendar" aria-label="选择日期">${icon('calendar-blank')}</button></span>`;
  let body;
  if (state.dayTab === 'review') {
    const groups = groupReviewDays(events, Infinity);
    body = `<div class="review-timeline day-timeline">${groups.map(renderReviewDay).join('')}</div><div class="list-end">当日快照 · 保留 ${SNAPSHOT_RETENTION_DAYS} 天</div>`;
  } else {
    const maxHeat = Math.max(1, ...events.map(event => event.heat));
    body = `<div class="hot-list">${events.map((event, index) => renderHotCard(event, index, maxHeat)).join('')}</div><div class="list-end">当日快照 · 保留 ${SNAPSHOT_RETENTION_DAYS} 天</div>`;
  }
  const toggle = `<div class="day-toggle" role="group" aria-label="当日视图">${[['hot', '热点'], ['review', '回顾']].map(([id, text]) =>
    `<button data-action="day-tab" data-value="${id}" class="${state.dayTab === id ? 'on' : ''}" aria-pressed="${state.dayTab === id}">${text}</button>`).join('')}</div>`;
  return `<div class="feed-heading day-heading"><span class="heading-label">${icon('calendar-blank', 'sm')}<span class="day-title">${label} ${mode}</span></span>${tools}</div>
    <div class="day-toolbar">${toggle}<span class="day-count">${events.length} 件事</span></div>${body}`;
}
function renderNews() {
  const dateEvent = (state.day && EVENTS.find(event => event.dateKey === state.day)) || EVENTS[0];
  return `<nav class="feed-tabs" aria-label="资讯视图">${NEWS_TABS.map(([id, label]) =>
    `<button data-action="tab" data-value="${id}" class="${state.tab === id ? 'on' : ''}" aria-pressed="${state.tab === id}">${label}</button>`).join('')}<span class="tab-date">${dateEvent.date} ${dateEvent.weekday}</span></nav>
    ${state.day ? '' : renderFilters()}
    <main class="feed-scroll" aria-label="资讯列表">${state.day ? renderDayView() : renderFeed()}</main>`;
}
function renderExploreItem(item) {
  const price = item.kind === 'buy'
    ? `<span class="explore-price">${item.price ? escapeHTML(item.price) : '价格未核实'}${item.dl ? ` · ${escapeHTML(item.dl)}` : ''}</span>`
    : '';
  const meta = [item.when, item.where].filter(Boolean).join(' · ');
  return `<button class="explore-item${item.img ? ' has-img' : ''}" data-action="explore" data-value="${item.id}" aria-label="${escapeHTML(item.t)}，查看详情">
    <span class="explore-icon">${icon(item.ic)}</span>
    <span class="explore-body">
      <span class="explore-tag">${escapeHTML(item.tag)}</span>
      <span class="explore-title">${escapeHTML(item.t)}</span>
      <span class="explore-why">${escapeHTML(item.why)}</span>
      ${price}
      ${meta ? `<span class="explore-meta">${escapeHTML(meta)}</span>` : ''}
    </span>
    ${item.img ? `<img class="explore-img" src="img/explore/${escapeHTML(item.img)}" alt="">` : ''}
  </button>`;
}
function renderExplore() {
  const all = exploreByKind(state.exploreTab);
  const items = all.filter(item => state.exploreTag === '全部' || item.tag === state.exploreTag);
  const tags = exploreTags(state.exploreTab);
  return `<nav class="explore-tabs" aria-label="探索分类">${EXPLORE_TABS.map(([id, label]) =>
    `<button data-action="explore-tab" data-value="${id}" class="${state.exploreTab === id ? 'on' : ''}" aria-pressed="${state.exploreTab === id}">${label}</button>`).join('')}</nav>
    <div class="explore-chips category-rail" role="group" aria-label="探索标签">${tags.map(tag =>
      `<button data-action="explore-tag" data-value="${escapeHTML(tag)}" class="${state.exploreTag === tag ? 'on' : ''}" aria-pressed="${state.exploreTag === tag}">${escapeHTML(tag)}</button>`).join('')}</div>
    <main class="page-scroll explore-scroll" aria-label="探索列表">
      <div class="explore-heading"><span>${EXPLORE_KINDS[state.exploreTab]}</span><span class="explore-count" role="status">${items.length} 条</span></div>
      <div class="explore-list">${items.map(renderExploreItem).join('')}</div>
      <div class="list-end">这一期就这些 · 样刊 #2</div>
    </main>`;
}
function renderMine() {
  const channelCount = new Set(EVENTS.map(event => event.sourceId)).size;
  const dayCount = new Set(EVENTS.map(event => event.dateKey)).size;
  const newest = EVENTS[0];
  const oldest = EVENTS[EVENTS.length - 1];
  const dark = state.theme === 'dark';
  return `<main class="page-scroll mine-scroll" aria-label="我的">
    <div class="mine-profile">
      <img src="logo/d-tab.svg" alt="" width="52" height="52">
      <div><span class="mine-name">拾光热榜</span><span>本地离线原型 · B5</span></div>
    </div>
    <div class="mine-group">
      <button class="mine-row" role="switch" aria-checked="${dark}" aria-label="深色模式" data-action="theme" data-value="switch">
        <span class="mine-leading">${icon(dark ? 'sun' : 'moon')}<span>深色模式</span></span>
        <span class="theme-switch${dark ? ' on' : ''}" aria-hidden="true"><span class="knob"></span></span>
      </button>
      <button class="mine-row" data-action="about" data-value="mine-about"><span class="mine-leading">${icon('info')}<span>设计说明</span></span>${icon('caret-right', 'sm')}</button>
    </div>
    <div class="mine-group mine-stats">
      <div class="mine-stat"><span class="mine-number">${EVENTS.length}</span><span>条真实内容</span></div>
      <div class="mine-stat"><span class="mine-number">${dayCount}</span><span>天回顾</span></div>
      <div class="mine-stat"><span class="mine-number">${channelCount}</span><span>个来源频道</span></div>
    </div>
    <div class="mine-group">
      <div class="mine-row"><span class="mine-leading">${icon('newspaper')}<span>数据来源</span></span><span class="mine-value">${channelCount} 个公开 Telegram 频道</span></div>
      <div class="mine-row"><span class="mine-leading">${icon('clock-counter-clockwise')}<span>内容范围</span></span><span class="mine-value">${oldest.date} – ${newest.date}</span></div>
    </div>
    <p class="mine-note">页面完全离线，不含外网请求、字体或 CDN。数据来自本地备份，仅作展示层原型。</p>
  </main>`;
}
function renderBottomNav() {
  return `<nav class="bottom-nav" aria-label="主导航">${SECTIONS.map(([id, name, label]) =>
    `<button data-action="section" data-value="${id}" class="${state.section === id ? 'on' : ''}" aria-current="${state.section === id ? 'page' : 'false'}">${icon(name)}<span>${label}</span></button>`).join('')}</nav>`;
}
function renderAbout() {
  return `<p class="about-intro">一份资讯，<br>三个入口。</p>
    <div class="about-option"><span class="about-letter">${icon('newspaper', 'sm')}</span><div><h3>真实内容</h3><p>实时按发布时间倒序；热点用标题、正文长度与新鲜度算出热度；回顾按天分组，每天按热度取前 5 条，再按时间倒序展示。</p></div></div>
    <div class="about-option"><span class="about-letter">${icon('compass', 'sm')}</span><div><h3>资讯与探索</h3><p>底部三个入口：资讯看频道动态，探索看好玩、好看、好买，我的负责主题、数据范围与说明。</p></div></div>
    <div class="preview-tools"><p>预览状态</p><div><button data-action="status" data-value="ok">正常</button><button data-action="status" data-value="empty">空内容</button><button data-action="status" data-value="error">加载失败</button></div></div>
    <p class="sheet-note">全部内容来自本地数据备份。原文入口打开本地示例页，不访问外部网站。</p>`;
}
function sourceMarkup(event) {
  return `<article class="source-card">
    <div class="source-top">${icon('telegram-logo')}<span>${escapeHTML(event.sourceName)}</span></div>
    <div class="source-meta">@${event.sourceId} · ${event.date} ${event.time}</div>
    <p>${escapeHTML(event.summary)}</p>
    <a class="source-link" href="#source/${event.id}">查看原文${icon('caret-right', 'sm')}</a>
  </article>`;
}
function renderDetail(event) {
  return `<div class="detail-category">${icon(CATEGORY_ICONS[event.category], 'sm')}${event.category}</div>
    <h3 class="detail-title">${escapeHTML(event.title)}</h3>
    <p class="detail-meta">${escapeHTML(event.sourceName)} · ${event.date} ${event.time}</p>
    ${event.image ? `<img class="detail-image" src="${escapeHTML(event.image)}" alt="">` : ''}
    <p class="detail-copy">${escapeHTML(event.summary)}</p>
    <div class="section-heading"><span>${event.count > 1 ? `${event.count} 个频道在说` : '原文来源'}</span><small>1 条原文</small></div>
    ${sourceMarkup(event)}`;
}
function renderSource(event) {
  return `<div class="detail-category">${icon('telegram-logo', 'sm')}${escapeHTML(event.sourceName)}<span class="source-label">本地示例</span></div>
    <p class="detail-meta">@${event.sourceId} · ${event.date} ${event.time}</p>
    <h3 class="detail-title">${escapeHTML(event.title)}</h3>
    <p class="detail-copy">${escapeHTML(event.summary)}</p>
    <p class="sheet-note">原文来自公开 Telegram 频道的本地备份，不访问外部网站。</p>
    <a class="source-link" href="#event/${event.id}">${icon('arrow-left', 'sm')}返回事件</a>`;
}
function renderExploreDetail(item) {
  const meta = [item.when, item.where].filter(Boolean).join(' · ');
  const price = item.kind === 'buy'
    ? `<p class="explore-price">${item.price ? escapeHTML(item.price) : '价格未核实'}${item.dl ? ` · ${escapeHTML(item.dl)}` : ''}</p>`
    : '';
  const rows = (item.rows || []).map(([name, text]) => `<div class="explore-row"><span class="explore-row-title">${escapeHTML(name)}</span><p>${escapeHTML(text)}</p></div>`).join('');
  const unverified = (item.unv || []).length
    ? `<div class="explore-unv">${icon('warning-circle', 'sm')}<span>未核实：${item.unv.map(escapeHTML).join('；')}</span></div>`
    : '';
  const sources = (item.src || []).map(([name, url]) => `<div class="explore-source">${escapeHTML(name)} · ${escapeHTML(url)}</div>`).join('');
  return `<div class="detail-category">${icon(item.ic, 'sm')}${EXPLORE_KINDS[item.kind]} · ${escapeHTML(item.tag)}</div>
    <h3 class="detail-title">${escapeHTML(item.t)}</h3>
    ${meta ? `<p class="detail-meta">${escapeHTML(meta)}</p>` : ''}
    ${price}
    ${item.img ? `<img class="detail-image" src="img/explore/${escapeHTML(item.img)}" alt="">` : ''}
    <p class="detail-copy">${escapeHTML(item.why)}</p>
    ${rows}
    ${unverified}
    <div class="section-heading"><span>原文来源</span><small>本地摘录</small></div>
    ${sources}
    <p class="sheet-note">探索为人工挑选的样刊内容，事实以原文为准；页面不跳转外站。${item.kind === 'buy' ? '「好买」只做购买时机提醒，不提供下单。' : ''}</p>`;
}
function renderModal(route) {
  if (!route) return '';
  let title, body, back = '';
  if (route.type === 'about') { title = '设计说明'; body = renderAbout(); }
  else if (route.type === 'calendar') { title = '选择日期'; body = renderDatePicker(); }
  else if (route.type === 'group') { title = `${state.category} · 群组`; body = renderGroupSheet(); }
  else if (route.type === 'source') {
    title = '频道原文'; body = renderSource(route.event);
    back = `<a class="icon-button" aria-label="返回事件" href="#event/${route.event.id}">${icon('arrow-left')}</a>`;
  } else if (route.type === 'explore') { title = '探索详情'; body = renderExploreDetail(route.item); }
  else { title = '事件详情'; body = renderDetail(route.event); }
  const sheetClass = route.type === 'group' ? ' group-sheet' : '';
  return `<div class="overlay"><section class="sheet${sheetClass}" role="dialog" aria-modal="true" aria-labelledby="dialog-title" tabindex="-1"><div class="sheet-header">${back}<h2 id="dialog-title">${title}</h2><button class="icon-button" data-action="close" aria-label="关闭">${icon('x')}</button></div><div class="sheet-body">${body}</div></section></div>`;
}
function render(keepScroll = false, keepModalScroll = false) {
  const oldScroller = root.querySelector('.feed-scroll, .page-scroll');
  if (oldScroller) scrollMemory[lastSection] = oldScroller.scrollTop;
  const sheetScroll = keepModalScroll ? root.querySelector('.sheet-body')?.scrollTop || 0 : 0;
  const focused = document.activeElement;
  const focusAction = focused?.dataset?.action, focusValue = focused?.dataset?.value;
  const route = readRoute();
  const title = state.section === 'explore' ? '探索' : state.section === 'mine' ? '我的' : '拾光热榜';
  document.documentElement.dataset.theme = state.theme;
  root.innerHTML = `<div class="page-surface" ${route ? 'inert' : ''}>
    <nav class="preview-bar" aria-label="设计预览"><span class="preview-label">设计预览 · B5</span><button class="icon-button" data-action="about" data-value="bar" aria-label="查看设计说明">${icon('info')}</button></nav>
    <header class="brand"><img src="logo/d-tab.svg" alt="" width="32" height="32"><h1>${title}</h1><button class="icon-button" data-action="theme" data-value="header" aria-label="切换到${state.theme === 'light' ? '深' : '浅'}色模式">${icon(state.theme === 'light' ? 'moon' : 'sun')}</button></header>
    ${state.section === 'explore' ? renderExplore() : state.section === 'mine' ? renderMine() : renderNews()}
    ${renderBottomNav()}
  </div>${renderModal(route)}`;
  const scroller = root.querySelector('.feed-scroll, .page-scroll');
  if (scroller) {
    scroller.scrollTop = keepScroll ? (scrollMemory[state.section] || 0) : 0;
    if (!keepScroll) scrollMemory[state.section] = 0;
  }
  if (route) {
    root.querySelector('.sheet-body').scrollTop = sheetScroll;
    const match = keepModalScroll && [...root.querySelectorAll('.sheet [data-action]')].find(b => b.dataset.action === focusAction && b.dataset.value === focusValue);
    (match || root.querySelector('.sheet')).focus({ preventScroll: true });
    pendingFocus = null;
  } else if (pendingFocus) {
    const action = pendingFocus.dataset?.action, value = pendingFocus.dataset?.value;
    [...root.querySelectorAll('[data-action]')].find(b => b.dataset.action === action && b.dataset.value === value)?.focus({ preventScroll: true });
    pendingFocus = null;
  } else if (focusAction) {
    [...root.querySelectorAll('[data-action]')].find(b => b.dataset.action === focusAction && b.dataset.value === focusValue)?.focus({ preventScroll: true });
  }
  lastSection = state.section;
  revealSelectedCategory();
  syncRailFades();
}
function refreshFeed(scroller) {
  if (ptrTimer) return;
  const indicator = document.createElement('span');
  indicator.className = 'ptr-indicator ptr-refreshing';
  indicator.setAttribute('role', 'status');
  indicator.setAttribute('aria-label', '正在刷新');
  scroller.append(indicator);
  ptrTimer = setTimeout(() => {
    ptrTimer = null;
    render();
  }, 800);
}
root.addEventListener('click', event => {
  if (event.target.classList.contains('overlay')) { closeRoute(); return; }
  const button = event.target.closest('[data-action]');
  if (!button) return;
  const { action, value } = button.dataset;
  if (action === 'section') {
    if (state.section !== value) { state.section = value; state.status = 'ok'; render(true); }
    return;
  }
  if (action === 'event') { openRoute(`event/${value}`); return; }
  if (action === 'explore') { openRoute(`explore/${value}`); return; }
  if (action === 'about') { openRoute('about'); return; }
  if (action === 'close') { closeRoute(); return; }
  if (action === 'theme') {
    state.theme = state.theme === 'light' ? 'dark' : 'light';
    render(true);
    return;
  }
  if (action === 'tab') { state.tab = value; state.day = null; state.status = 'ok'; render(); return; }
  if (action === 'category') { selectCategory(value); return; }
  if (action === 'group') { openRoute('group'); return; }
  if (action === 'pick-channel') {
    state.channel = value;
    if (state.status !== 'error') {
      state.status = 'ok';
      lastSeen[value] = NEWEST_BY_CHANNEL[value];
      persistLastSeen();
    }
    closeRoute(true);
    return;
  }
  if (action === 'clear-channel') {
    state.channel = null;
    render();
    root.querySelector('.group-btn')?.focus({ preventScroll: true });
    return;
  }
  if (action === 'calendar') { state.pickerMonth = null; openRoute('calendar'); return; }
  if (action === 'picker-month') {
    const { minMonth, maxMonth } = snapshotWindow();
    const step = Number(value);
    if (!step) return;
    const current = state.pickerMonth && state.pickerMonth >= minMonth && state.pickerMonth <= maxMonth ? state.pickerMonth : maxMonth;
    const [year, month] = current.split('-').map(Number);
    const next = new Date(Date.UTC(year, month - 1 + step, 1)).toISOString().slice(0, 7);
    if (next < minMonth || next > maxMonth) return;
    state.pickerMonth = next;
    render(true, true);
    return;
  }
  if (action === 'pick-day') {
    if (!HOT_SNAPSHOTS[value]) return;
    state.day = value;
    state.dayTab = 'hot';
    state.category = '全部';
    state.channel = null;
    closeRoute(true);
    return;
  }
  if (action === 'day-tab') { state.dayTab = value; render(true); return; }
  if (action === 'day-today') { state.day = null; state.dayTab = 'hot'; render(); return; }
  if (action === 'explore-tab') { state.exploreTab = value; state.exploreTag = '全部'; state.status = 'ok'; render(); return; }
  if (action === 'explore-tag') { state.exploreTag = value; render(); return; }
  if (action === 'clear') { state.category = '全部'; state.channel = null; state.day = null; state.status = 'ok'; render(); return; }
  if (action === 'retry') { state.status = 'ok'; render(); return; }
  if (action === 'status') { state.status = value; closeRoute(); return; }
});
root.addEventListener('touchstart', event => {
  const zone = event.target.closest('.feed-scroll, .page-scroll');
  const kind = !zone ? null : zone.classList.contains('feed-scroll') ? 'feed' : zone.classList.contains('explore-scroll') ? 'explore' : 'page';
  touchStart = zone && event.touches.length === 1
    ? { x: event.touches[0].clientX, y: event.touches[0].clientY, scrollTop: zone.scrollTop, kind }
    : null;
}, { passive: true });
root.addEventListener('touchend', event => {
  if (!touchStart) return;
  const start = touchStart;
  const touch = event.changedTouches[0];
  const dx = touch.clientX - start.x;
  const dy = touch.clientY - start.y;
  touchStart = null;
  if (Math.abs(dx) > 50 && Math.abs(dx) > 1.5 * Math.abs(dy)) {
    if (start.kind === 'feed') { moveCategory(dx < 0 ? 1 : -1); return; }
    if (start.kind === 'explore') { moveExploreTab(dx < 0 ? 1 : -1); return; }
  }
  if (dy >= 50 && Math.abs(dy) > 1.5 * Math.abs(dx) && start.scrollTop === 0) {
    const zone = event.target.closest('.feed-scroll, .page-scroll');
    if (zone) refreshFeed(zone);
  }
}, { passive: true });
root.addEventListener('touchcancel', () => { touchStart = null; }, { passive: true });
root.addEventListener('scroll', event => {
  const rail = event.target.closest?.('.category-rail');
  if (rail) updateRailFade(rail);
}, { capture: true, passive: true });
document.addEventListener('keydown', event => {
  const dialog = root.querySelector('[role="dialog"]');
  if (!dialog) return;
  if (event.key === 'Escape') { event.preventDefault(); closeRoute(); }
  if (event.key === 'Tab') {
    const focusable = [...dialog.querySelectorAll('button:not(:disabled),a[href]')];
    const first = focusable[0], last = focusable[focusable.length - 1];
    if (event.shiftKey && (document.activeElement === first || document.activeElement === dialog)) { event.preventDefault(); last?.focus(); }
    else if (!event.shiftKey && (document.activeElement === last || document.activeElement === dialog)) { event.preventDefault(); first?.focus(); }
  }
});
window.addEventListener('hashchange', () => render(true));
render();
