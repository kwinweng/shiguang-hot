/* 拾光热榜 v1 前端纯函数（无 DOM 依赖，node --test 可直接 require）。
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
  /** 顶栏「刷新于」：同一天只写时间（日期左上角已经写了），跨天才带日期 */
  function fmtRefreshed(v, now) {
    const d = toDate(v); if (!d) return '';
    const p = parts(d);
    return beijingDate(d) === beijingDate(now || new Date()) ? `${p.hour}:${p.minute}` : `${p.month}月${p.day}日 ${p.hour}:${p.minute}`;
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
  function metaLine(item, d) {
    const hl = item.highlight ? '<span class="hl">今日重点</span>' : '';
    const mt = d.translated ? `<span class="mt-badge">${esc(d.label)}</span>` : '';
    return `<div class="f-meta"><span class="src">${esc(item.source_name)}</span><span>${esc(fmtTime(item.published_at))}</span>${hl}${mt}</div>`;
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
  function isBareForward(item) { return !!(item.quote && item.quote.kind === 'forward' && !String(item.summary || '').trim() && !String(item.body || '').trim()); }
  function feedRowHTML(item) {
    const d = display(item);
    let body;
    if (isBareForward(item)) {
      body = `<div class="fwd-tag">转发</div>${quoteCardHTML(item, false)}${metaLine(item, d)}${tgStatsHTML(item, false)}`;
    } else {
      const sum = d.summary.trim() ? `<p class="sum">${esc(d.summary)}</p>` :
        (item.quote || thumbOk(item.image) ? '' : `<p class="sum none">${NO_SUMMARY}</p>`);
      body = `<h3>${esc(d.title)}</h3>${sum}${quoteCardHTML(item, false)}${metaLine(item, d)}${tgStatsHTML(item, false)}`;
    }
    if (thumbOk(item.image)) {
      return `<article class="feed-row" data-id="${esc(item.id)}"><div class="thumb"><img src="${esc(item.image.url)}" alt="" loading="lazy" decoding="async" data-zoom="${esc(item.image.url)}"></div><div>${body}</div></article>`;
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
    return `<article class="hero" data-id="${esc(item.id)}"><img src="${esc(item.image.url)}" alt="" data-zoom="${esc(item.image.url)}"><div class="cap"><div class="src">${esc(item.source_name)}${d.translated ? ' · ' + esc(d.label) : ''}</div><h3>${esc(d.title)}</h3></div></article>`;
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
      const vid = (m.type === 'video' || m.type === 'gif') && m.url;
      return vid ? {t: m.type, u: m.url, p: m.preview_url || ''} : {t: 'image', u: m.preview_url || m.url};
    });
    return `<div class="media-grid n${n}" data-zoom-list="${esc(all.join('|'))}" data-media-list="${esc(JSON.stringify(items))}"${origin ? ` data-origin="${esc(origin)}"` : ''}>` + show.map((m, i) => {
      const vid = items[i].t !== 'image';
      const src = m.preview_url || m.url;
      const dur = vid && m.type === 'video' ? fmtDur(m.duration_ms) : '';
      const mark = vid ? `<div class="vid-mark" aria-label="${m.type === 'gif' ? '播放动图' : '播放视频'}"><i>${ICO.play}</i>${m.type === 'gif' ? '<span class="vid-dur">GIF</span>' : dur ? `<span class="vid-dur">${esc(dur)}</span>` : ''}</div>` : '';
      const img = vid && !m.preview_url ? `<video src="${esc(m.url)}#t=0.1" muted playsinline preload="metadata" data-media-i="${i}"></video>` : `<img src="${esc(src)}" alt="" loading="lazy" data-zoom="${esc(src)}" data-media-i="${i}">`;
      return `<div class="cell${vid ? ' is-vid' : ''}">${img}${mark}${i === show.length - 1 && extra ? `<div class="more-ph">+${extra}</div>` : ''}</div>`;
    }).join('') + '</div>';
  }
  function avatar(src, cls = '') {
    return src ? `<img class="${cls}" src="${esc(src)}" alt="">` : `<span class="av ${cls}"></span>`;
  }
  /** 「@账号」只给 X、微博这类账号名可读的平台；即刻的账号是 UUID，YouTube 是频道 id，不显示 */
  function atHandle(platform, handle) {
    if (!handle || !['x', 'weibo', 'blog'].includes(platform || 'x')) return '';
    return '@' + esc(handle);
  }
  /** 推文卡（v9/v10 样式）。拿不到的互动数不显示，不编数字 */
  function tweetCardHTML(item, clamp) {
    const b = item.blogger || {};
    const d = display(item);
    const text = d.body || d.summary;
    const key = `${item.id}-${clamp ? 'c' : 'd'}`;
    const tools = d.translated ? `<div class="t-tools"><span class="t-badge">${esc(d.label)}</span><button type="button" class="orig-btn" data-orig="${esc(key)}">看原文</button></div><div class="orig" data-orig-box="${esc(key)}">${esc(d.orig.body || d.orig.summary)}</div>` : '';
    const q = b.quote;
    const quote = q ? `<div class="quote"><div class="hd">${avatar(q.avatar, 'av')}<div><div class="nm">${esc(q.display_name || q.handle)}</div><div class="meta">${[atHandle(b.platform, q.handle), q.published_at ? esc(fmtTime(q.published_at)) : ''].filter(Boolean).join(' · ')}</div></div></div><div class="t-body">${esc(q.text)}</div></div>` : '';
    const comments = (b.comments || []).slice(0, 10);
    const cm = !clamp && comments.length ? `<div class="comments"><h4>热门回复</h4><p class="cmt-note">按点赞排序，最多 10 条。完整讨论请打开原文。</p>${comments.map(c => {
      const text = c.text_zh || c.text;
      const like = Number.isInteger(c.like) ? `<span class="meta c-like">♥ ${esc(fmtN(c.like))}</span>` : '';
      const mt = c.text_zh ? '<span class="mt-badge">机器翻译</span>' : '';
      return `<div class="comment">${avatar(c.avatar, 'av')}<div><div class="nm" style="font-size:13px">${esc(c.display_name || c.handle)} <span class="meta">@${esc(c.handle)}${c.published_at ? ' · ' + esc(fmtTime(c.published_at)) : ''}</span>${like}${mt}</div><div class="t-body">${esc(text)}</div></div></div>`;
    }).join('')}</div>` : '';
    const m = b.metrics || {};
    const metric = (k) => (Number.isInteger(m[k]) ? `<span>${ICO[k]}${fmtN(m[k])}</span>` : '');
    const metrics = ['reply', 'repost', 'like'].some(k => Number.isInteger(m[k])) ? `<div class="metrics">${metric('reply')}${metric('repost')}${metric('like')}</div>` : '';
    const extra = !clamp ? ['view', 'bookmark', 'quote'].filter(k => Number.isInteger(m[k]) && m[k]).map(k => ({view: '浏览 ', bookmark: '收藏 ', quote: '引用 '}[k] + fmtN(m[k]))) : [];
    const title = d.title ? `<div class="b-title">${esc(d.title)}</div>` : '';
    if (clamp && item.blocks && item.blocks.length) {
      // 文章类帖子（公众号/博客）：列表里只放标题、摘要和一张封面，正文按原文顺序在详情里
      const cover = item.image && item.image.url ? `<div class="post-cover"><img src="${esc(item.image.url)}" alt="" loading="lazy" data-zoom="${esc(item.image.url)}"></div>` : '';
      const sum = d.summary ? `<div class="t-body clamp">${esc(d.summary)}</div>` : '';
      return `<article class="tweet article-post" data-id="${esc(item.id)}"><div class="hd">${avatar(b.avatar)}<div style="flex:1;min-width:0"><div class="nm">${esc(b.display_name || b.handle)}</div><div class="meta">${esc(fmtTime(item.published_at))}${d.translated ? ' · ' + esc(d.label) : ''}</div></div></div>${title}${sum}${cover}</article>`;
    }
    return `<article class="tweet" data-id="${esc(item.id)}"><div class="hd">${avatar(b.avatar)}<div style="flex:1;min-width:0"><div class="nm">${esc(b.display_name || b.handle)} ${b.verified ? `<span class="blue" title="认证">${ICO.check}</span>` : ''}</div><div class="meta">${[atHandle(b.platform, b.handle), esc(fmtTime(item.published_at))].filter(Boolean).join(' · ')}</div></div></div>${title}<div class="t-body${clamp ? ' clamp' : ''}">${esc(text)}</div>${tools}${mediaGrid(b.media, item.url)}${quote}${metrics}${extra.length ? `<div class="detail-meta">${extra.map(esc).join(' · ')}</div>` : ''}${cm}</article>`;
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

  const Lib = {TZ, NO_SUMMARY, NO_BODY, BODY_PENDING, HOT_FAIL, esc, beijingDate, fmtTime, fmtDay, fmtRefreshed, fmtN, display, thumbOk,
    tgStatsHTML, quoteCardHTML, isBareForward, blocksHTML, feedRowHTML, heroHTML, bannerHTML, hotsearchHTML, tweetCardHTML, rowHTML, parseItemHash, itemHash, ICO, icon, mediaGrid, fmtDur};
  if (typeof module !== 'undefined' && module.exports) module.exports = Lib;
  else root.RebangLib = Lib;
})(typeof window !== 'undefined' ? window : globalThis);
