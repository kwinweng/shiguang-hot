/* 拾光热榜 v1 前端纯函数（无 DOM 依赖，node --test 可直接 require）。
   时间一律按北京时间（Asia/Shanghai）显示；文案「不编」：没有正文就如实说没有。 */
(function (root) {
  'use strict';
  const TZ = 'Asia/Shanghai';
  const WEEK = ['周日', '周一', '周二', '周三', '周四', '周五', '周六'];
  const NO_SUMMARY = '这条没有正文摘要。';
  const NO_BODY = '这条没有正文，可以点「打开原文」看原始内容。';
  const HOT_FAIL = '暂时取不到。抓到之前这里空着，不编排名。';

  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));
  }
  const parts = (date) => {
    const out = {};
    for (const p of new Intl.DateTimeFormat('en-US', {timeZone: TZ, year: 'numeric', month: 'numeric', day: 'numeric',
      hour: '2-digit', minute: '2-digit', hourCycle: 'h23', weekday: 'short'}).formatToParts(date)) out[p.type] = p.value;
    return out;
  };
  function toDate(v) { const d = v instanceof Date ? v : new Date(v); return isNaN(d) ? null : d; }
  /** 北京日期 YYYY-MM-DD */
  function beijingDate(v) {
    const d = toDate(v); if (!d) return '';
    const p = parts(d);
    return `${p.year}-${String(p.month).padStart(2, '0')}-${String(p.day).padStart(2, '0')}`;
  }
  /** 「11月15日 20:42」 */
  function fmtTime(v) {
    const d = toDate(v); if (!d) return '';
    const p = parts(d);
    return `${p.month}月${p.day}日 ${p.hour}:${p.minute}`;
  }
  /** 「11月15日 周日」 */
  function fmtDay(v) {
    const d = toDate(v); if (!d) return '';
    const p = parts(d);
    const [y, m, dd] = beijingDate(d).split('-').map(Number);
    return `${p.month}月${p.day}日 ${WEEK[new Date(Date.UTC(y, m - 1, dd)).getUTCDay()]}`;
  }
  function fmtN(n) {
    n = Number(n || 0);
    if (n >= 100000000) return (n / 100000000).toFixed(1).replace(/\.0$/, '') + '亿';
    if (n >= 10000) return (n / 10000).toFixed(1).replace(/\.0$/, '') + '万';
    return String(n);
  }
  /** 有译文先显示译文（标「机器翻译」），orig 保留原文供展开 */
  /** 卡片摘要：去掉开头裸露的链接（TG 频道常把原文链接放在第一行），正文页仍显示完整内容 */
  function cardText(t) { return String(t || '').replace(/^(?:\s*https?:\/\/\S+)+\s*/, ''); }
  function display(item) {
    const tr = item.translated && item.translation;
    const shown = tr ? {title: tr.title || '', summary: cardText(tr.summary), body: tr.body || ''} :
      {title: item.title || '', summary: cardText(item.summary), body: item.body || ''};
    return {...shown, translated: !!tr, label: tr ? (tr.label || '机器翻译') : '',
      orig: tr ? {title: item.title || '', summary: item.summary || '', body: item.body || ''} : null};
  }
  /** 卡片小图：有地址；已知宽高时须合格（短边≥240、比例 0.6–2.4），未知宽高先显示、坏图在前端退回无图 */
  function thumbOk(image) {
    if (!image || !image.url) return false;
    const {width: w, height: h} = image;
    if (w && h) return Math.min(w, h) >= 240 && w / h >= 0.6 && w / h <= 2.4;
    return true;
  }
  function metaLine(item, d) {
    const hl = item.highlight ? '<span class="hl">今日重点</span>' : '';
    const mt = d.translated ? `<span class="mt-badge">${esc(d.label)}</span>` : '';
    return `<div class="f-meta"><span class="src">${esc(item.source_name)}</span><span>${esc(fmtTime(item.published_at))}</span>${hl}${mt}</div>`;
  }
  function feedRowHTML(item) {
    const d = display(item);
    const sum = d.summary.trim() ? `<p class="sum">${esc(d.summary)}</p>` : `<p class="sum none">${NO_SUMMARY}</p>`;
    const body = `<h3>${esc(d.title)}</h3>${sum}${metaLine(item, d)}`;
    if (thumbOk(item.image)) {
      return `<article class="feed-row" data-id="${esc(item.id)}"><div class="thumb"><img src="${esc(item.image.url)}" alt="" loading="lazy" decoding="async"></div><div>${body}</div></article>`;
    }
    return `<article class="feed-row noimg" data-id="${esc(item.id)}">${body}</article>`;
  }
  function heroHTML(item) {
    const d = display(item);
    return `<article class="hero" data-id="${esc(item.id)}"><img src="${esc(item.image.url)}" alt=""><div class="cap"><div class="src">${esc(item.source_name)}${d.translated ? ' · ' + esc(d.label) : ''}</div><h3>${esc(d.title)}</h3></div></article>`;
  }
  function bannerHTML(slug, items) {
    if (!items || !items.length) return '';
    const slides = items.map(it => `<div class="banner-slide">${heroHTML(it)}</div>`).join('');
    return `<div class="banner-wrap" data-ch="${esc(slug)}"><div class="banner-rail" data-ch="${esc(slug)}">${slides}</div><div class="banner-pager" aria-label="第 1 屏，共 ${items.length} 条">1 / ${items.length}</div></div>`;
  }
  function hotLabel(entry) {
    if (entry.pinned) return '<span class="lbl pin">置顶</span>';
    if (entry.hot_label) return `<span class="lbl">${esc(entry.hot_label)}</span>`;
    if (entry.hot_score) return `<span class="lbl">${esc(fmtN(entry.hot_score))}</span>`;
    return '<span class="lbl"></span>';
  }
  /** 热搜块：分家 tab；status≠ok 的家显示「暂时取不到」；默认显示前 limit 条 */
  function hotsearchHTML(payload, activeId, expanded, limit = 10) {
    const providers = (payload && payload.providers) || [];
    if (!providers.length) return '';
    const active = providers.find(p => p.id === activeId) || providers.find(p => p.status === 'ok') || providers[0];
    const tabs = providers.map(p => `<button type="button" role="tab" data-hot="${esc(p.id)}" aria-selected="${p.id === active.id}" class="${p.id === active.id ? 'on' : ''}${p.status === 'ok' ? '' : ' bad'}">${esc(p.name)}</button>`).join('');
    let body;
    if (active.status !== 'ok' || !(active.items || []).length) {
      body = `<p class="hot-empty" data-state="${esc(active.status)}">${esc(active.name)}${HOT_FAIL}</p>`;
    } else {
      const rows = expanded ? active.items : active.items.slice(0, limit);
      body = `<ol class="hot-list">${rows.map(e => `<li><a href="${esc(e.url)}" target="_blank" rel="noopener"><span class="rk">${e.pinned ? '顶' : esc(e.rank)}</span><span class="t">${esc(e.title)}</span>${hotLabel(e)}</a></li>`).join('')}</ol>` +
        (active.items.length > limit ? `<button type="button" class="hot-more" data-hot-more="${expanded ? 0 : 1}">${expanded ? '收起' : `展开全部 ${active.items.length} 条`}</button>` : '');
    }
    const when = active.fetched_at ? `${esc(active.name)} · ${esc(fmtTime(active.fetched_at))}` : '';
    return `<section class="hot" aria-label="热搜"><div class="hot-hd"><span class="hot-ttl">热搜</span><span class="hot-time">${when}</span></div><div class="hot-tabs" role="tablist">${tabs}</div>${body}</section>`;
  }
  const ICO = {
    reply: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M4 12c0-3.3 3.1-6 8-6s8 2.7 8 6-3.1 6-8 6c-.7 0-1.4-.1-2-.2L6 19l.8-3.2C5.1 14.7 4 13.5 4 12z"/></svg>',
    repost: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M7 7h8l-2-2M17 17H9l2 2"/><path d="M15 5v5H7v4M9 19v-5h8V10"/></svg>',
    like: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M12 19s-7-4.4-7-9a4 4 0 0 1 7-2 4 4 0 0 1 7 2c0 4.6-7 9-7 9z"/></svg>',
    play: '<svg viewBox="0 0 24 24" fill="#111"><path d="M9 7v10l9-5z"/></svg>',
    check: '<svg viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="3"><path d="M6 12l4 4 8-8"/></svg>'
  };
  function mediaGrid(media) {
    if (!media || !media.length) return '';
    const show = media.slice(0, 4);
    const extra = media.length > 4 ? media.length - 4 : 0;
    const n = media.length >= 5 ? 5 : show.length;
    return `<div class="media-grid n${n}">` + show.map((m, i) => {
      const vid = m.type === 'video' || m.type === 'gif';
      const src = m.preview_url || m.url;
      return `<div class="cell"><img src="${esc(src)}" alt="" loading="lazy">${vid ? `<div class="vid-mark"><i>${ICO.play}</i></div>` : ''}${i === show.length - 1 && extra ? `<div class="more-ph">+${extra}</div>` : ''}</div>`;
    }).join('') + '</div>';
  }
  function avatar(src, cls = '') {
    return src ? `<img class="${cls}" src="${esc(src)}" alt="">` : `<span class="av ${cls}"></span>`;
  }
  /** 推文卡（v9/v10 样式）。拿不到的互动数不显示，不编数字 */
  function tweetCardHTML(item, clamp) {
    const b = item.blogger || {};
    const d = display(item);
    const text = d.body || d.summary;
    const key = `${item.id}-${clamp ? 'c' : 'd'}`;
    const tools = d.translated ? `<div class="t-tools"><span class="t-badge">${esc(d.label)}</span><button type="button" class="orig-btn" data-orig="${esc(key)}">看原文</button></div><div class="orig" data-orig-box="${esc(key)}">${esc(d.orig.body || d.orig.summary)}</div>` : '';
    const q = b.quote;
    const quote = q ? `<div class="quote"><div class="hd">${avatar(q.avatar, 'av')}<div><div class="nm">${esc(q.display_name || q.handle)}</div><div class="meta">@${esc(q.handle)}${q.published_at ? ' · ' + esc(fmtTime(q.published_at)) : ''}</div></div></div><div class="t-body">${esc(q.text)}</div></div>` : '';
    const cm = !clamp && (b.comments || []).length ? `<div class="comments"><h4>评论</h4><p class="cmt-note">只预览抓到的前几条，完整讨论请打开原文。</p>${b.comments.slice(0, 8).map(c => `<div class="comment">${avatar(c.avatar, 'av')}<div><div class="nm" style="font-size:13px">${esc(c.display_name || c.handle)} <span class="meta">@${esc(c.handle)}${c.published_at ? ' · ' + esc(fmtTime(c.published_at)) : ''}</span></div><div class="t-body">${esc(c.text)}</div></div></div>`).join('')}</div>` : '';
    const m = b.metrics || {};
    const metric = (k) => (Number.isInteger(m[k]) ? `<span>${ICO[k]}${fmtN(m[k])}</span>` : '');
    const metrics = ['reply', 'repost', 'like'].some(k => Number.isInteger(m[k])) ? `<div class="metrics">${metric('reply')}${metric('repost')}${metric('like')}</div>` : '';
    const extra = !clamp ? ['view', 'bookmark', 'quote'].filter(k => Number.isInteger(m[k]) && m[k]).map(k => ({view: '浏览 ', bookmark: '收藏 ', quote: '引用 '}[k] + fmtN(m[k]))) : [];
    const title = d.title ? `<div class="b-title">${esc(d.title)}</div>` : '';
    return `<article class="tweet" data-id="${esc(item.id)}"><div class="hd">${avatar(b.avatar)}<div style="flex:1;min-width:0"><div class="nm">${esc(b.display_name || b.handle)} ${b.verified ? `<span class="blue" title="认证">${ICO.check}</span>` : ''}</div><div class="meta">@${esc(b.handle)} · ${esc(fmtTime(item.published_at))}</div></div></div>${title}<div class="t-body${clamp ? ' clamp' : ''}">${esc(text)}</div>${tools}${mediaGrid(b.media)}${quote}${metrics}${extra.length ? `<div class="detail-meta">${extra.map(esc).join(' · ')}</div>` : ''}${cm}</article>`;
  }
  /** 历史/收藏/搜索通用行 */
  function rowHTML(item) {
    const d = display(item);
    const img = item.image && item.image.url ? item.image.url : (item.blogger && item.blogger.avatar) || '';
    const who = item.kind === 'post' ? (item.blogger.display_name || item.blogger.handle) : item.source_name;
    const title = d.title || d.summary;
    return `<article class="row-item${img ? '' : ' noimg'}" data-id="${esc(item.id)}">${img ? `<img src="${esc(img)}" alt="" loading="lazy">` : ''}<div><div class="src">${esc(who)} · ${esc(fmtTime(item.published_at))}</div><h3>${esc(title)}</h3></div></article>`;
  }
  /** 深链：#/item/<urlencoded id>（push-0830 私聊稿）与旧式 #item-<id> */
  function parseItemHash(hash) {
    const h = String(hash || '');
    let m = h.match(/^#\/item\/(.+)$/);
    if (m) { try { return decodeURIComponent(m[1]); } catch (e) { return null; } }
    m = h.match(/^#item-(.+)$/);
    if (m) { try { return decodeURIComponent(m[1]); } catch (e) { return null; } }
    return null;
  }
  function itemHash(id) { return '#/item/' + encodeURIComponent(id); }

  const Lib = {TZ, NO_SUMMARY, NO_BODY, HOT_FAIL, esc, beijingDate, fmtTime, fmtDay, fmtN, display, thumbOk,
    feedRowHTML, heroHTML, bannerHTML, hotsearchHTML, tweetCardHTML, rowHTML, parseItemHash, itemHash, ICO};
  if (typeof module !== 'undefined' && module.exports) module.exports = Lib;
  else root.RebangLib = Lib;
})(typeof window !== 'undefined' ? window : globalThis);
