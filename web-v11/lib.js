/* 拾光资讯 v1 前端纯函数（无 DOM 依赖，node --test 可直接 require）。
   时间一律按北京时间（Asia/Shanghai）显示；文案「不编」：没有正文就如实说没有。 */
(function (root) {
  'use strict';
  const TZ = 'Asia/Shanghai';
  const WEEK = ['周日', '周一', '周二', '周三', '周四', '周五', '周六'];
  const NO_SUMMARY = '这条没有正文摘要。';
  const NO_BODY = '这条没有正文，可以点「打开原文」看原始内容。';
  const BODY_PENDING = '全文译文还在准备，下面先放摘要。可打开原文阅读。';
  const HOT_FAIL = '暂时取不到。抓到之前这里空着，不编排名。';

  function esc(s) {
    const text = typeof s === 'string' || typeof s === 'number' ? String(s) : '';
    return text.replace(/[&<>"']/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));
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
  /** 顶栏「刷新于」：同一天只写时间（日期左上角已经写了），跨天才带日期 */
  function fmtRefreshed(v, now) {
    const d = toDate(v); if (!d) return '';
    const p = parts(d);
    return beijingDate(d) === beijingDate(now || new Date()) ? `${p.hour}:${p.minute}` : `${p.month}月${p.day}日 ${p.hour}:${p.minute}`;
  }
  /** 列表里的时间（v16）：1 小时内「N 分钟前」，24 小时内「N 小时前」，再早写「11月15日 20:42」 */
  function fmtWhen(v, now) {
    const d = toDate(v); if (!d) return '';
    const m = Math.floor(((now ? toDate(now) : new Date()) - d) / 60000);
    if (m < 0 || m >= 24 * 60) return fmtTime(d);
    if (m < 1) return '刚刚';
    if (m < 60) return m + ' 分钟前';
    return Math.floor(m / 60) + ' 小时前';
  }
  /** 详情页时间「2026年11月16日 22:44」 */
  function fmtFull(v) {
    const d = toDate(v); if (!d) return '';
    const p = parts(d);
    return `${p.year}年${p.month}月${p.day}日 ${p.hour}:${p.minute}`;
  }
  /** 博主日期分组标题「11.16 今天」「11.15 昨天」「11.12 周四」；today = 北京日期 YYYY-MM-DD */
  function dayLabel(day, today) {
    const [y, m, dd] = String(day).split('-').map(Number);
    if (!y) return '';
    const base = `${m}.${String(dd).padStart(2, '0')}`;
    const diff = Math.round((Date.parse(today + 'T00:00:00Z') - Date.UTC(y, m - 1, dd)) / 864e5);
    return base + ' ' + (diff === 0 ? '今天' : diff === 1 ? '昨天' : WEEK[new Date(Date.UTC(y, m - 1, dd)).getUTCDay()]);
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
    const tr = item.translation || {};
    const hasTr = !!(item.translated && (tr.title || tr.summary || tr.body || tr.blocks));
    const title = (hasTr && tr.title) ? tr.title : (item.title || '');
    // 标题已译、摘要还在排队时，列表不回退到英文预览
    const summary = cardText((hasTr && tr.summary) ? tr.summary : ((hasTr && (item.summary || '').trim()) ? '' : item.summary));
    const hasBodyTr = !!(tr.body || tr.blocks);
    const hasOrigBody = !!(item.body || (item.blocks && item.blocks.length));
    const bodyPending = !!(hasTr && hasOrigBody && !hasBodyTr) || !!tr.body_pending;
    // 全文还没译好时，详情不要先铺英文长文；列表和详情都用已有的中文摘要
    const body = hasBodyTr ? (tr.body || '') : (bodyPending ? summary : (item.body || ''));
    const blocks = tr.blocks || null;
    return {title, summary, body, blocks, bodyPending, translated: hasTr,
      label: hasTr ? (tr.label || '机器翻译') : '',
      orig: hasTr ? {title: item.title || '', summary: item.summary || '', body: item.body || '', blocks: item.blocks || null} : null};
  }
  /** 列表小图：有地址就显示。宽高限制只用于挑 banner，不挡住信息流里的图。 */
  function thumbOk(image) {
    return !!(image && image.url);
  }
  /** 列表一行元信息（v16）：来源 · 时间 · 浏览 · 评论 · 译 / 重点；拿不到的数不显示 */
  function metaLine(item, d) {
    const tg = item.tg || {};
    const views = tg.views != null ? `<span class="n" aria-label="浏览 ${esc(tg.views_label || tg.views)}">${icon('eye')}${esc(tg.views_label || fmtN(tg.views))}</span>` : '';
    const cmt = tg.comments_total ? `<span class="n" aria-label="评论 ${tg.comments_total} 条">${ICO.reply}${esc(fmtN(tg.comments_total))}</span>` : '';
    const hl = item.highlight ? '<span class="tag hl">重点</span>' : '';
    const mt = d.translated ? `<span class="tag mt-badge" title="${esc(d.label)}">译</span>` : '';
    return `<div class="f-meta"><span class="src">${esc(item.source_name)}</span><span>${esc(fmtWhen(item.published_at))}</span>${views}${cmt}${mt}${hl}</div>`;
  }
  /** TG 互动：表情回应 + 浏览数 + 评论数（都来自 t.me 公开页面；没有就不显示，不编） */
  function tgStatsHTML(item, full) {
    const tg = item.tg; if (!tg) return '';
    const rs = (tg.reactions || []).slice().sort((a, b) => b.count - a.count);
    const show = full ? rs : rs.slice(0, 3);
    const parts = show.map(r => `<span class="rx" title="${esc(r.emoji)} ${esc(r.label || r.count)}">${esc(r.emoji)}<b>${esc(r.label || fmtN(r.count))}</b></span>`);
    if (!full && rs.length > 3) parts.push(`<span class="rx more">+${rs.length - 3}</span>`);
    const views = tg.views != null ? `<span class="tv" aria-label="浏览 ${esc(tg.views_label || tg.views)}">${icon('eye')}${esc(tg.views_label || fmtN(tg.views))}</span>` : '';
    const cmt = tg.comments_total ? `<span class="tc" aria-label="评论 ${tg.comments_total} 条">${ICO.reply}${esc(fmtN(tg.comments_total))}</span>` : '';
    if (!parts.length && !views && !cmt) return '';
    return `<div class="tg-stats${full ? ' full' : ''}">${parts.join('')}${views}${cmt}</div>`;
  }
  /** TG 引用/转发卡：频道自己的话在上，原帖在卡里；转发且频道没写话 → 卡上方标「转发」。
      列表里整张卡点开详情；详情里引用卡是链接，点开 Telegram 原帖。 */
  function quoteCardHTML(item, inDetail) {
    const q = item.quote; if (!q) return '';
    const fwd = q.kind === 'forward';
    const head = `<div class="q-src"><span class="q-kind">${fwd ? '转发自' : '引用'}</span>${esc(q.source_name || '原帖')}</div>`;
    const text = q.text ? `<p class="q-text${inDetail ? '' : ' clamp'}">${esc(q.text)}</p>` : '<p class="q-text none">原帖没有文字（可能只有图片或视频）。</p>';
    if (inDetail && q.url) return `<a class="q-card${fwd ? ' fwd' : ''}" href="${esc(q.url)}" target="_blank" rel="noopener" data-quote-link>${head}${text}<span class="q-open">打开原帖 ›</span></a>`;
    return `<div class="q-card${fwd ? ' fwd' : ''}">${head}${text}</div>`;
  }
  /** 同类事件合并（第 5 步）：主条下折叠「另有 N 个来源」，点开列出其它来源，点某一条打开它的详情 */
  function dupHTML(item) {
    const list = Array.isArray(item.merged) ? item.merged.filter(m => m && m.id) : [];
    if (!list.length) return '';
    // 按 source_id 数来源（同名不同号的来源分开数）；只是同来源同链接的折叠不算「来源」
    const others = new Set(list.map(m => m.source_id || m.source_name).filter(n => n && n !== (item.source_id || item.source_name)));
    const label = others.size ? `另有 ${others.size} 个来源` : `另有 ${list.length} 条相同链接`;
    const rows = list.map(m => `<button type="button" class="dup-row" data-dup-id="${esc(m.id)}"><span class="src">${esc(m.source_name || m.source_id || '')}</span><span class="t">${esc(m.title_zh || m.title || '')}</span></button>`).join('');
    return `<div class="dup" data-dup><button type="button" class="dup-btn" data-dup-toggle aria-expanded="false">${label}</button><div class="dup-list" hidden>${rows}</div></div>`;
  }
  function isBareForward(item) { return !!(item.quote && item.quote.kind === 'forward' && !String(item.summary || '').trim() && !String(item.body || '').trim()); }
  function feedRowHTML(item) {
    const d = display(item);
    let body;
    if (isBareForward(item)) {
      body = `<div class="fwd-tag">转发</div>${quoteCardHTML(item, false)}${metaLine(item, d)}${dupHTML(item)}`;
    } else {
      const sum = d.summary.trim() ? `<p class="sum">${esc(d.summary)}</p>` :
        (item.quote || thumbOk(item.image) ? '' : `<p class="sum none">${NO_SUMMARY}</p>`);
      body = `<h3>${esc(d.title)}</h3>${sum}${quoteCardHTML(item, false)}${metaLine(item, d)}${dupHTML(item)}`;
    }
    if (thumbOk(item.image)) {
      return `<article class="feed-row" data-id="${esc(item.id)}"><div class="f-main">${body}</div><div class="thumb"><img src="${esc(item.image.url)}" alt="" loading="lazy" decoding="async" data-zoom="${esc(item.image.url)}"></div></article>`;
    }
    return `<article class="feed-row noimg" data-id="${esc(item.id)}">${body}</article>`;
  }
  /** 正文块（公众号/博客）：严格按原文顺序；没存下的公众号图如实说，不顶替 */
  function blocksHTML(blocks) {
    return (blocks || []).map(b => {
      if (b.type === 'p') return `<p class="b-p">${esc(b.text)}</p>`;
      if (b.type === 'h') return `<h4 class="b-h l${esc(b.level || 2)}">${esc(b.text)}</h4>`;
      if (b.type === 'quote') return `<blockquote class="b-q">${esc(b.text)}</blockquote>`;
      if (b.type === 'pre') return `<pre class="b-pre">${esc(b.text)}</pre>`;
      if (b.type === 'hr') return '<hr class="b-hr">';
      if (b.type === 'ul' || b.type === 'ol') return `<${b.type} class="b-list">${b.items.map(t => `<li>${esc(t)}</li>`).join('')}</${b.type}>`;
      if (b.type === 'img') {
        if (b.missing) return '<div class="b-img-missing" data-img-missing>这张图没存下来，点下方「打开原文」看。</div>';
        const dims = b.width && b.height ? ` width="${esc(b.width)}" height="${esc(b.height)}"` : '';
        return `<figure class="b-img"><img src="${esc(b.src)}" alt="${esc(b.alt || '')}" loading="lazy" decoding="async"${dims} data-zoom="${esc(b.src)}"></figure>`;
      }
      return '';
    }).join('');
  }
  function heroHTML(item) {
    const d = display(item);
    return `<article class="hero" data-id="${esc(item.id)}"><img src="${esc(item.image.url)}" alt="" data-zoom="${esc(item.image.url)}"><div class="cap"><div class="src">${esc(item.source_name)}${d.translated ? ' · ' + esc(d.label) : ''}</div><h3>${esc(d.title)}</h3>${dupHTML(item)}</div></article>`;
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
  /** 热搜家的短名：「百度热搜」→「百度」，「B 站热搜」→「B站」 */
  function hotShort(name) { return String(name || '').replace(/热搜|热榜/g, '').replace(/\s+/g, ''); }
  /** 热搜块（v16）：吸顶的「日期 + 三家分段」，下面是这家的榜单。status≠ok 的家显示「暂时取不到」；默认显示前 limit 条。
   *  opts.dates：日期一行的 HTML（放进吸顶区）；opts.note：替换默认的「百度 · 抓取于…」说明 */
  function hotsearchHTML(payload, activeId, expanded, limit = 10, opts = {}) {
    const providers = (payload && payload.providers) || [];
    if (!providers.length) return '';
    const active = providers.find(p => p.id === activeId) || providers.find(p => p.status === 'ok') || providers[0];
    const tabs = providers.map(p => {
      const n = p.status === 'ok' && (p.items || []).length ? `${p.items.length} 条` : '暂时取不到';
      return `<button type="button" role="tab" data-hot="${esc(p.id)}" aria-selected="${p.id === active.id}" class="${p.id === active.id ? 'on' : ''}${p.status === 'ok' ? '' : ' bad'}"><b>${esc(hotShort(p.name))}</b><small>${esc(n)}</small></button>`;
    }).join('');
    let body;
    if (active.status !== 'ok' || !(active.items || []).length) {
      body = `<p class="hot-empty" data-state="${esc(active.status)}">${esc(active.name)}${HOT_FAIL}</p>`;
    } else {
      const rows = expanded ? active.items : active.items.slice(0, limit);
      body = `<ol class="hot-list">${rows.map(e => `<li><a href="${esc(e.url)}" target="_blank" rel="noopener"><span class="rk${e.pinned ? ' pin-rk' : (Number(e.rank) <= 3 ? ' hi' : '')}"${e.pinned ? ' aria-label="置顶"' : ''}>${e.pinned ? icon('flame') : esc(e.rank)}</span><span class="t">${esc(e.title)}</span>${hotLabel(e)}</a></li>`).join('')}</ol>` +
        (active.items.length > limit ? `<button type="button" class="hot-more" data-hot-more="${expanded ? 0 : 1}">${expanded ? '收起' : `展开全部 ${active.items.length} 条`}</button>` : '');
    }
    const note = opts.note != null ? opts.note : (active.fetched_at ? `${hotShort(active.name)} · 抓取于 ${fmtWhen(active.fetched_at)}` : '');
    return `<section class="hot" aria-label="热搜"><div class="hot-top">${opts.dates || ''}<div class="hot-tabs" role="tablist">${tabs}</div></div>${note ? `<p class="hot-note">${esc(note)}</p>` : ''}${body}</section>`;
  }
  /** 全站唯一图标集：Lucide（ISC，v1.73.0 原样路径，见 LICENSES/lucide.txt 与 docs/rebang-v1/DESIGN-SYSTEM.md）。
   *  不引运行时依赖；index.html 里的静态图标用同一份路径。 */
  const LUCIDE = {
    'message-circle': '<path d="M2.992 16.342a2 2 0 0 1 .094 1.167l-1.065 3.29a1 1 0 0 0 1.236 1.168l3.413-.998a2 2 0 0 1 1.099.092 10 10 0 1 0-4.777-4.719"/>',
    'repeat-2': '<path d="m2 9 3-3 3 3"/><path d="M13 18H7a2 2 0 0 1-2-2V6"/><path d="m22 15-3 3-3-3"/><path d="M11 6h6a2 2 0 0 1 2 2v10"/>',
    'heart': '<path d="M2 9.5a5.5 5.5 0 0 1 9.591-3.676.56.56 0 0 0 .818 0A5.49 5.49 0 0 1 22 9.5c0 2.29-1.5 4-3 5.5l-5.492 5.313a2 2 0 0 1-3 .019L5 15c-1.5-1.5-3-3.2-3-5.5"/>',
    'play': '<path d="M5 5a2 2 0 0 1 3.008-1.728l11.997 6.998a2 2 0 0 1 .003 3.458l-12 7A2 2 0 0 1 5 19z"/>',
    'check': '<path d="M20 6 9 17l-5-5"/>',
    'eye': '<path d="M2.062 12.348a1 1 0 0 1 0-.696 10.75 10.75 0 0 1 19.876 0 1 1 0 0 1 0 .696 10.75 10.75 0 0 1-19.876 0"/><circle cx="12" cy="12" r="3"/>',
    'chevron-left': '<path d="m15 18-6-6 6-6"/>',
    'chevron-right': '<path d="m9 18 6-6-6-6"/>',
    'x': '<path d="M18 6 6 18"/><path d="m6 6 12 12"/>',
    'chevron-down': '<path d="m6 9 6 6 6-6"/>',
    'arrow-left': '<path d="m12 19-7-7 7-7"/><path d="M19 12H5"/>',
    'ellipsis': '<circle cx="12" cy="12" r="1"/><circle cx="19" cy="12" r="1"/><circle cx="5" cy="12" r="1"/>',
    'flame': '<path d="M12 3q1 4 4 6.5t3 5.5a1 1 0 0 1-14 0 5 5 0 0 1 1-3 1 1 0 0 0 5 0c0-2-1.5-3-1.5-5q0-2 2.5-4"/>',
    'bookmark': '<path d="M17 3a2 2 0 0 1 2 2v15a1 1 0 0 1-1.496.868l-4.512-2.578a2 2 0 0 0-1.984 0l-4.512 2.578A1 1 0 0 1 5 20V5a2 2 0 0 1 2-2z"/>',
    'bookmark-check': '<path d="M17 3a2 2 0 0 1 2 2v15a1 1 0 0 1-1.496.868l-4.512-2.578a2 2 0 0 0-1.984 0l-4.512 2.578A1 1 0 0 1 5 20V5a2 2 0 0 1 2-2z"/><path d="m9 10 2 2 4-4"/>',
    'share': '<path d="M12 2v13"/><path d="m16 6-4-4-4 4"/><path d="M4 12v8a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-8"/>',
    'link': '<path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"/><path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"/>',
    'external-link': '<path d="M15 3h6v6"/><path d="M10 14 21 3"/><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/>',
    'copy': '<rect width="14" height="14" x="8" y="8" rx="2" ry="2"/><path d="M4 16c-1.1 0-2-.9-2-2V4c0-1.1.9-2 2-2h10c1.1 0 2 .9 2 2"/>',
    'a-large-small': '<path d="m15 16 2.536-7.328a1.02 1.02 1 0 1 1.928 0L22 16"/><path d="M15.697 14h5.606"/><path d="m2 16 4.039-9.69a.5.5 0 0 1 .923 0L11 16"/><path d="M3.304 13h6.392"/>',
    'list-filter': '<path d="M2 5h20"/><path d="M6 12h12"/><path d="M9 19h6"/>',
  };
  function icon(name, attrs = '') {
    return `<svg class="lucide lucide-${name}"${attrs ? ' ' + attrs : ''} viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${LUCIDE[name]}</svg>`;
  }
  const ICO = {
    reply: icon('message-circle'),
    repost: icon('repeat-2'),
    like: icon('heart'),
    play: icon('play', 'fill="currentColor"'),
    check: icon('check', 'style="stroke-width:3"')
  };
  function fmtDur(ms) {
    const t = Math.round(Number(ms) / 1000);
    if (!Number.isFinite(t) || t <= 0) return '';
    return `${Math.floor(t / 60)}:${String(t % 60).padStart(2, '0')}`;
  }
  /** 推文媒体九宫格。视频/GIF 显示封面 + 播放标；data-media-list 带完整媒体清单（类型、地址、封面），
   *  点开后在全屏查看里直接播放；data-origin 是原帖链接，播放失败时给用户兜底 */
  function mediaGrid(media, origin) {
    if (!media || !media.length) return '';
    const list = media.filter(m => m && (m.url || m.preview_url));
    if (!list.length) return '';
    const show = list.slice(0, 4);
    const extra = list.length > 4 ? list.length - 4 : 0;
    const n = list.length >= 5 ? 5 : show.length;
    const all = list.map(m => m.preview_url || m.url);
    const items = list.map(m => {
      const vid = (m.type === 'video' || m.type === 'gif' || m.type === 'youtube') && m.url;
      return vid ? {t: m.type, u: m.url, p: m.preview_url || ''} : {t: 'image', u: m.preview_url || m.url};
    });
    return `<div class="media-grid n${n}" data-zoom-list="${esc(all.join('|'))}" data-media-list="${esc(JSON.stringify(items))}"${origin ? ` data-origin="${esc(origin)}"` : ''}>` + show.map((m, i) => {
      const vid = items[i].t !== 'image';
      const src = m.preview_url || m.url;
      const dur = vid && (m.type === 'video' || m.type === 'youtube') ? fmtDur(m.duration_ms) : '';
      const mark = vid ? `<div class="vid-mark" aria-label="${m.type === 'gif' ? '播放动图' : '播放视频'}"><i>${ICO.play}</i>${m.type === 'gif' ? '<span class="vid-dur">GIF</span>' : dur ? `<span class="vid-dur">${esc(dur)}</span>` : ''}</div>` : '';
      const img = vid && !m.preview_url ? `<video src="${esc(m.url)}#t=0.1" muted playsinline preload="metadata" data-media-i="${i}"></video>` : `<img src="${esc(src)}" alt="" loading="lazy" data-zoom="${esc(src)}" data-media-i="${i}">`;
      return `<div class="cell${vid ? ' is-vid' : ''}">${img}${mark}${i === show.length - 1 && extra ? `<div class="more-ph">+${extra}</div>` : ''}</div>`;
    }).join('') + '</div>';
  }
  function avatar(src, cls = '') {
    return src ? `<img class="${cls}" src="${esc(src)}" alt="">` : `<span class="av ${cls}"></span>`;
  }
  /** 「@账号」只给 X、微博这类账号名可读的平台；即刻的账号是 UUID，YouTube 是频道 id，微博的纯数字 uid 也不显示 */
  function atHandle(platform, handle) {
    if (!handle || !['x', 'weibo', 'blog'].includes(platform || 'x')) return '';
    if (platform === 'weibo' && /^\d+$/.test(String(handle))) return '';
    return '@' + esc(handle);
  }
  /** X / 微博等的「热门回复」（详情页和评论半屏共用）。按点赞排序，最多 10 条；没有就不出 */
  function xCommentsHTML(item, inSheet) {
    const b = item.blogger || {};
    const comments = (b.comments || []).slice(0, 10);
    if (!comments.length) return '';
    return `<div class="comments">${inSheet ? '' : `<h4>热门回复 <span class="meta">${comments.length}</span></h4>`}<p class="cmt-note">按点赞排序，最多 10 条。完整讨论请打开原文。</p>${comments.map(c => {
      const text = c.text_zh || c.text;
      const like = Number.isInteger(c.like) ? `<span class="meta c-like">${ICO.like}${esc(fmtN(c.like))}</span>` : '';
      const mt = c.text_zh ? '<span class="mt-badge">机器翻译</span>' : '';
      return `<div class="comment">${avatar(c.avatar, 'av')}<div class="c-main"><div class="nm c-nm">${esc(c.display_name || c.handle)} <span class="meta">@${esc(c.handle)}${c.published_at ? ' · ' + esc(fmtTime(c.published_at)) : ''}</span>${like}${mt}</div><div class="t-body">${esc(text)}</div></div></div>`;
    }).join('')}</div>`;
  }
  /** 博主列表里文章类帖子的封面缩略图（放在右边）；带媒体的帖子改在正文下面用 mediaGrid 多格显示（样页 A） */
  function postThumbHTML(item) {
    if (item.image && item.image.url) return `<div class="thumb"><img src="${esc(item.image.url)}" alt="" loading="lazy" decoding="async" data-zoom="${esc(item.image.url)}"></div>`;
    return '';
  }
  // 全平台先在建站端统一排序再切页；浏览器只合并队首，不再按毫秒重新解释时间。
  function comparePosts(a, b) { return a.feed_order - b.feed_order; }
  function bloggerAvatar(src) {
    return src ? `<img class="bl-avatar" src="${esc(src)}" alt="" loading="lazy">` : '<span class="bl-avatar" aria-hidden="true"></span>';
  }
  function postTranslation(d, key, badge) {
    if (!d.translated) return '';
    return `<div class="t-tools">${badge}<button type="button" class="orig-btn" aria-expanded="false" data-orig="${esc(key)}">看原文</button></div><div class="orig" data-orig-box="${esc(key)}">${esc(d.orig.body || d.orig.summary)}</div>`;
  }
  function postQuote(b, compact = false) {
    const q = b.quote;
    if (!q) return '';
    const who = esc(q.display_name || q.handle);
    const meta = [atHandle(b.platform, q.handle), q.published_at ? esc(fmtTime(q.published_at)) : ''].filter(Boolean).join(' · ');
    const author = compact ? `<div class="nm">${who}${meta ? ` <span class="meta">${meta}</span>` : ''}</div>` : `<div class="hd">${avatar(q.avatar, 'av')}<div><div class="nm">${who}</div><div class="meta">${meta}</div></div></div>`;
    return `<div class="quote">${author}<div class="t-body">${esc(q.text)}</div></div>`;
  }
  function postRowHTML(item, platformName) {
    const b = item.blogger || {};
    const d = display(item);
    const norm = x => String(x || '').replace(/[\s【】]/g, '');
    let text = cardText(d.summary || d.body || '').replace(/\s+/g, ' ').trim();
    if (d.title && text && norm(text).startsWith(norm(d.title))) text = text.slice(d.title.length).trim();
    if (d.title && norm(text) === norm(d.title)) text = '';
    const link = label => `<a href="${esc(itemHash(item.id))}" data-bl-item>${esc(label)}</a>`;
    const main = d.title ? `<h3 class="b-title">${link(d.title)}</h3>${text ? `<p class="b-sum">${esc(text.slice(0, 300))}</p>` : ''}` :
      `<p class="b-text">${link(text.slice(0, 400) || NO_SUMMARY)}</p>`;
    const m = b.metrics || {};
    const like = Number.isInteger(m.like) ? `<span class="n">${ICO.like}${fmtN(m.like)}</span>` : '';
    const reply = Number.isInteger(m.reply) ? `<span class="n">${ICO.reply}${fmtN(m.reply)}</span>` : '';
    const metrics = like || reply ? `<span class="metrics">${like}${reply}</span>` : '';
    const name = b.display_name || b.handle || item.source_name;
    const profile = b.platform && b.handle ? ` data-plat-of="${esc(b.platform)}" data-person="${esc(b.handle)}"` : '';
    const av = bloggerAvatar(b.avatar);
    const face = profile ? `<button type="button" class="bl-face"${profile} aria-label="查看${esc(name)}的帖子">${av}</button>` : av;
    const who = profile ? `<button type="button" class="bl-name"${profile}>${esc(name)}</button>` : `<span class="bl-name">${esc(name)}</span>`;
    const mt = postTranslation(d, `${item.id}-bl`, `<span class="tag mt-badge" title="${esc(d.label)}">译</span>`);
    const grid = mediaGrid(b.media, item.url);
    const th = grid ? '' : postThumbHTML(item);
    return `<article class="tweet brow${th || grid ? '' : ' noimg'}" data-id="${esc(item.id)}">${face}<div class="b-main">
      <div class="bl-who">${who}${b.verified ? `<span class="blue" title="认证">${ICO.check}</span>` : ''}${platformName ? `<span class="bl-platform">${esc(platformName)}</span>` : ''}<time datetime="${esc(item.published_at)}">${esc(fmtWhen(item.published_at))}</time><button type="button" class="bl-more" data-bl-menu aria-label="帖子菜单">${icon('ellipsis')}</button></div>
      <div class="bl-content"><div>${main}</div>${th}</div>${grid}${mt}${postQuote(b, true)}${metrics}</div></article>`;
  }
  /** 详情用完整推文卡。拿不到的互动数不显示。 */
  function tweetCardHTML(item, clamp) {
    if (clamp) return postRowHTML(item);
    const b = item.blogger || {};
    const d = display(item);
    const text = d.body || d.summary;
    const tools = postTranslation(d, `${item.id}-d`, `<span class="t-badge">${esc(d.label)}</span>`);
    const quote = postQuote(b);
    const cm = xCommentsHTML(item, false);
    const m = b.metrics || {};
    const metric = (k) => (Number.isInteger(m[k]) ? `<span>${ICO[k]}${fmtN(m[k])}<em>${({reply: '回复', repost: '转发', like: '点赞'})[k]}</em></span>` : '');
    const metrics = ['reply', 'repost', 'like'].some(k => Number.isInteger(m[k])) ? `<div class="metrics">${metric('reply')}${metric('repost')}${metric('like')}</div>` : '';
    const extra = ['view', 'bookmark', 'quote'].filter(k => Number.isInteger(m[k]) && m[k]).map(k => ({view: '浏览 ', bookmark: '收藏 ', quote: '引用 '}[k] + fmtN(m[k])));
    const title = d.title ? `<div class="b-title">${esc(d.title)}</div>` : '';
    return `<article class="tweet" data-id="${esc(item.id)}"><div class="hd">${avatar(b.avatar)}<div style="flex:1;min-width:0"><div class="nm">${esc(b.display_name || b.handle)} ${b.verified ? `<span class="blue" title="认证">${ICO.check}</span>` : ''}</div><div class="meta">${[atHandle(b.platform, b.handle), esc(fmtTime(item.published_at))].filter(Boolean).join(' · ')}</div></div></div>${title}<div class="t-body">${esc(text)}</div>${tools}${mediaGrid(b.media, item.url)}${quote}${metrics}${extra.length ? `<div class="detail-meta">${extra.map(esc).join(' · ')}</div>` : ''}${cm}</article>`;
  }
  /** 历史/收藏/搜索通用行 */
  function rowHTML(item) {
    const d = display(item);
    const real = item.image && item.image.url ? item.image.url : '';
    const img = real || (item.blogger && item.blogger.avatar) || '';
    const who = item.kind === 'post' ? (item.blogger.display_name || item.blogger.handle) : item.source_name;
    const title = d.title || d.summary;
    return `<article class="row-item${img ? '' : ' noimg'}" data-id="${esc(item.id)}">${img ? `<img src="${esc(img)}" alt="" loading="lazy"${real ? ` data-zoom="${esc(real)}"` : ''}>` : ''}<div><div class="src">${esc(who)} · ${esc(fmtTime(item.published_at))}</div><h3>${esc(title)}</h3></div></article>`;
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
  /** iOS 主屏幕 web app（standalone）的外壳几何。
   *  iOS 26/27 的 standalone（Safari 或 Chrome「添加到主屏幕」，内核都是 WebKit）有个 bug（WebKit 313800）：
   *  innerHeight / 100dvh / inset:0 只到「屏幕高 − 状态栏高」（17 Pro：874 − 62 = 812），但网页实际铺满整屏，
   *  下面那 62px 照样画 html 背景。外壳按视口排版，底栏就停在 812，下面空一大截。
   *  修法：外壳高度直接用整屏高度（超出视口那段 WebKit 照画），底栏照常垫 env(safe-area-inset-bottom) 让图标落在 Home 条上方。
   *  返回 {appH, safeBot}：appH = 外壳高度 px（null = 不改，照常 inset:0），safeBot = 底部内边距 px（null = 照常 env()）；
   *  不是 iOS standalone 整屏 → null。m = {standalone, ios, insetTop, insetBottom, screenW, screenH, innerW, innerH} */
  function standaloneGeometry(m) {
    if (!m || !m.standalone || !m.ios) return null;
    const portrait = m.innerH >= m.innerW;
    const long = Math.max(m.screenW || 0, m.screenH || 0), short = Math.min(m.screenW || 0, m.screenH || 0);
    const fullH = portrait ? long : short, fullW = portrait ? short : long;
    if (!fullH || Math.abs(fullW - m.innerW) > 2) return null;          // iPad 分屏/窗口：不是整屏，不猜
    const homeBar = portrait && fullH >= 812;                            // 全面屏 iPhone 竖屏才有 Home 条
    const safeBot = m.insetBottom > 0 ? null : (homeBar ? 20 : null);    // env() 错报 0（iOS 26.1 回归 / 27 新装图标）→ 至少留 20px
    const gap = Math.round(fullH - m.innerH);
    // 视口比屏幕矮，且页面画在状态栏下面（顶部安全区 > 0 说明视口从屏幕顶开始）→ 缺口在底部：外壳撑到整屏
    if (gap >= 2 && m.insetTop > 0) return {appH: fullH, safeBot};
    if (gap >= 2) return null;                                           // 状态栏不透明、视口从状态栏下开始：缺口在顶部，不动
    return safeBot === null ? null : {appH: null, safeBot};
  }

  const Lib = {TZ, NO_SUMMARY, NO_BODY, BODY_PENDING, HOT_FAIL, esc, beijingDate, fmtTime, fmtWhen, fmtFull, dayLabel, fmtDay, fmtRefreshed, fmtN, display, thumbOk,
    tgStatsHTML, quoteCardHTML, dupHTML, isBareForward, blocksHTML, feedRowHTML, heroHTML, bannerHTML, hotsearchHTML, hotShort, tweetCardHTML, postRowHTML, bloggerAvatar, comparePosts, xCommentsHTML, rowHTML, parseItemHash, itemHash, ICO, icon, mediaGrid, fmtDur, standaloneGeometry};
  if (typeof module !== 'undefined' && module.exports) module.exports = Lib;
  else root.RebangLib = Lib;
})(typeof window !== 'undefined' ? window : globalThis);
