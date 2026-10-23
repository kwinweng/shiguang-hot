/* Live feed and completed-day reviews. All inputs are build-time public JSON. */
'use strict';
const News = (() => {
  const categories = ['全部', '热门', '科技', '财经', '国际', '数码'];
  const icons = ['squares-four', 'fire', 'cpu', 'chart-line-up', 'globe', 'device-mobile'];
  const category = value => ({全球:'国际', 环球:'国际', AI:'科技', 科技AI:'科技', '科技 AI':'科技', 开发者:'科技'})[value] || value;
  const escape = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const safe = value => /^https?:\/\//i.test(value || '') ? escape(value) : '';
  const icon = (name, fill = false) => `<span class="ic">${window.ICONS[name + (fill ? '_fill' : '_line')] || ''}</span>`;
  const filter = (rows, cat) => !cat || cat === '全部' ? rows : rows.filter(row =>
    cat === '热门' ? row.hot || row.source_count > 1 || row.category === '热门' : category(row.category) === category(cat));
  const monthDays = (month, available) => {
    const [year, m] = month.split('-').map(Number);
    return Array.from({length:new Date(Date.UTC(year, m, 0)).getUTCDate()}, (_, i) => {
      const day = `${month}-${String(i + 1).padStart(2, '0')}`;
      return {day, enabled:available.includes(day)};
    });
  };
  return {categories, icons, escape, safe, icon, filter, monthDays};
})();
if (typeof module !== 'undefined') module.exports = News;
if (typeof document !== 'undefined') {
  const {categories, icons, escape: e, safe, icon, filter, monthDays} = News;
  const main = document.getElementById('news');
  let live, sources, index, generation = 0;
  const cache = new Map();
  const load = async path => {
    if (cache.has(path)) return cache.get(path);
    const response = await fetch(path);
    if (!response.ok) throw new Error('数据暂时无法读取');
    const value = await response.json();
    cache.set(path, value);
    return value;
  };
  const back = (hash, label) => `<a class="back" href="${hash}">${icon('arrow-left')}${e(label)}</a>`;
  const heading = (title, right = '', compact = false) => `<div class="ph"><h1${compact ? ' class="h2"' : ''}>${e(title)}</h1><div class="acts">${right}</div></div>`;
  const controls = cat => `<div class="flt" aria-label="按分类筛选">${categories.map((name, i) => `<button data-category="${name}" aria-label="${name}" aria-pressed="${name === cat}" class="${name === cat ? 'on' : ''}">${icon(icons[i], name === cat)}<span>${name}</span></button>`).join('')}</div>`;
  const original = row => safe(row.link) ? `<a class="btn pri" href="${safe(row.link)}" target="_blank" rel="noopener noreferrer">看原文 ${icon('arrow-square-out')}</a>` : '';
  const row = r => `<a class="row" href="#message/${e(r.id)}?from=${encodeURIComponent(location.hash || '#feed')}">${r.image ? `<img loading="lazy" src="${e(r.image)}" alt="">` : ''}<div class="tx"><b>${e(r.title)}</b><p>${e(r.summary)}</p><small>${e(r.source_name)} · ${e(r.category)} · ${e(r.time.slice(11,16))}</small></div></a>`;
  const list = rows => {
    let hour = '';
    return rows.map(r => {
      const h = r.hour !== hour ? `<h2 class="hh">${e(r.hour.slice(11))}</h2>` : '';
      hour = r.hour;
      return h + row(r);
    }).join('') || '<p class="empty">暂无消息。</p>';
  };
  const params = () => {
    const [path, query = ''] = (location.hash.slice(1) || (location.pathname.endsWith('/today.html') ? 'today' : 'feed')).split('?');
    return {parts:path.split('/'), query:new URLSearchParams(query)};
  };
  const route = async () => {
    const current = ++generation;
    const {parts, query} = params();
    const cat = categories.includes(query.get('category')) ? query.get('category') : '全部';
    main.setAttribute('aria-busy', 'true');
    try {
      [live, sources, index] = await Promise.all([load('data/live.json'), load('data/sources.json'), load('history/index.json')]);
      let html = '';
      if (parts[0] === 'today') {
        const today = new Date(Date.parse(live.updated) + 8*3600000).toISOString().slice(0,10);
        const rows = sources.sources.filter(s=>s.type==='inbox').flatMap(s=>s.messages).filter(r=>r.day===today);
        html = back('#feed','实时流') + heading('今日') + '<p class="sub">今日简报</p>' + list(rows);
      } else if (parts[0] === 'sources') {
        html = back('#feed', '实时流') + heading('来源') + '<p class="sub">今天按北京时间 00:00 至今统计；近 7 天含今天。</p>';
        html += '<div class="th3"><span>来源</span><span>今天</span><span>近7天</span></div>';
        html += sources.sources.map(s => `<a class="srow" href="#source/${e(s.id)}"><div><b>${e(s.name)}</b><small>${e(({telegram:'TG',feed:'RSS',inbox:'期刊'})[s.type])} · ${s.status === 'stale' ? `超过 ${s.stale_hours} 小时无新内容` : '正常'}</small><small>最后更新 ${e(s.last_update?.slice(0,16).replace('T',' ') || '暂无')}</small></div><span>${s.today_count}</span><span>${s.seven_day_count}</span>${icon('caret-right')}</a>`).join('');
      } else if (parts[0] === 'source') {
        const source = sources.sources.find(s => s.id === parts[1]);
        if (!source) throw new Error('来源不存在');
        const scope = query.get('scope') || 'week';
        const day = query.get('day');
        const floor = new Date(Date.parse(live.updated) + 8*3600000 - 6*86400000).toISOString().slice(0,10);
        const today = new Date(Date.parse(live.updated) + 8*3600000).toISOString().slice(0,10);
        const own = day && index.days.includes(day) ? (await load(`history/${day}.json`)).messages.filter(r=>r.source===source.id) : source.messages;
        const rows = own.filter(r => day ? r.day === day : scope === 'today' ? r.day === today : r.day >= floor);
        html = back('#sources', '来源') + heading(source.name)
          + (source.type === 'telegram' && safe(source.url) ? `<a class="ext" href="${safe(source.url)}" target="_blank" rel="noopener noreferrer">在 Telegram 打开频道 ↗</a>` : '')
          + `<p class="sub">今天 ${source.today_count} 条 · 近7天 ${source.seven_day_count} 条</p><div class="scope"><a aria-current="${!day && scope === 'today'}" href="#source/${e(source.id)}?scope=today">今天</a><a aria-current="${!day && scope !== 'today'}" href="#source/${e(source.id)}?scope=week">近7天</a></div>` + list(rows);
      } else if (parts[0] === 'history') {
        const month = /^\d{4}-(0[1-9]|1[0-2])$/.test(parts[1] || '') ? parts[1] : (index.days.at(-1) || live.updated.slice(0,10)).slice(0,7);
        const [year, m] = month.split('-').map(Number);
        const shift = n => new Date(Date.UTC(year,m-1+n,1)).toISOString().slice(0,7);
        html = back('#feed','实时流') + heading('历史回顾') + '<p class="sub">北京时间每天 00:30 生成前一天总结</p>';
        html += `<div class="mh"><a class="back" aria-label="上个月" href="#history/${shift(-1)}">${icon('caret-left')}</a><b>${year} 年 ${m} 月</b><a class="back" aria-label="下个月" href="#history/${shift(1)}">${icon('caret-right')}</a></div><div class="cal">`;
        html += '日一二三四五六'.split('').map(w=>`<i>${w}</i>`).join('');
        html += '<span></span>'.repeat(new Date(Date.UTC(year,m-1,1)).getUTCDay());
        const today = new Date(Date.parse(live.updated) + 8*3600000).toISOString().slice(0,10);
        const selected = index.days.at(-1);
        html += monthDays(month,index.days).map(d=>d.enabled ? `<a class="${d.day === selected ? 'sel' : ''}" href="#day/${d.day}">${Number(d.day.slice(-2))}</a>` : `<span class="off${d.day === today ? ' td' : ''}" aria-disabled="true">${Number(d.day.slice(-2))}</span>`).join('') + '</div>';
        html += '<p class="leg">灰色日期暂无总结。今天的总结明早 00:30 生成。</p>';
        const latest = index.days.at(-1);
        if (latest) {
          const doc = await load(`history/${latest}.json`);
          html += `<a class="peek" href="#day/${latest}"><div><small>${e(latest)} · ${doc.stats.total} 条</small><b>${e(doc.summary)}</b></div>${icon('caret-right')}</a>`;
        }
      } else if (parts[0] === 'day') {
        const day = parts[1];
        if (!index.days.includes(day)) throw new Error('这一天暂无总结，明早 00:30 后再看。');
        const doc = await load(`history/${day}.json`);
        const position = index.days.indexOf(day);
        const nav = (offset, label, glyph) => index.days[position+offset] ? `<a aria-label="${label}" href="#day/${index.days[position+offset]}">${icon(glyph)}</a>` : `<span class="dis" aria-label="${label}不可用">${icon(glyph)}</span>`;
        const label = new Date(`${day}T12:00:00+08:00`).toLocaleDateString('zh-CN', {timeZone:'Asia/Shanghai', month:'long', day:'numeric', weekday:'short'});
        html = back(`#history/${day.slice(0,7)}`, '日历') + heading(label, nav(-1,'前一天','caret-left') + nav(1,'后一天','caret-right'), true);
        html += `<p class="sub">${doc.stats.total} 条消息 · ${Object.keys(doc.stats.sources).length} 个来源 · MOCK 样例总结</p>`;
        html += `<section class="day-summary"><h2>${doc.provider === 'mock' ? 'AI 摘要（样例）' : 'AI 摘要'}</h2><p>${e(doc.summary)}</p></section>`;
        const events = doc.events;
        const summaries = (members, title) => members.length ? `<h2 class="sh">${title}</h2>` + members.map(event => {
          const i = doc.events.indexOf(event);
          return `<article class="sum"><span class="no">${i+1}</span><div><a class="event-title" href="#event/${day}/${i}"><b>${e(event.title)}</b></a><p>${e(event.summary)}</p><small>${e(event.category)} · ${event.source_count} 个来源</small><details><summary>${event.messages.length} 条原消息 ${icon('caret-down')}</summary><ul>${event.messages.map(r=>`<li>${row(r)}</li>`).join('')}</ul></details></div></article>`;
        }).join('') : '';
        html += summaries(events, '热点');
        if (!events.length) html += '<p class="empty">该分类暂无事件。</p>';
        html += '<h2 class="sh">当天来源</h2>' + Object.entries(doc.stats.sources).map(([sid, count]) => {
          const name = doc.messages.find(r=>r.source===sid)?.source_name || sid;
          return `<a class="srow" href="#source/${encodeURIComponent(sid)}?day=${day}"><b>${e(name)}</b><span>${e(count)} 条</span>${icon('caret-right')}</a>`;
        }).join('');
        html += `<a class="btn" href="#feed?day=${day}&all=1">看当天全部原始消息</a>`;
        html += '<p class="foot">示例摘录按相同标题合并，可能不准确，请以原消息为准。</p>';
      } else if (parts[0] === 'message' || parts[0] === 'event') {
        let r, returnHash = /^#(feed|source|day)(\/|\?|$)/.test(query.get('from') || '') ? query.get('from') : '#feed';
        if (parts[0] === 'event') {
          if (!index.days.includes(parts[1])) throw new Error('事件不存在');
          const doc = await load(`history/${parts[1]}.json`);
          const event = doc.events[Number(parts[2])];
          if (!event) throw new Error('事件不存在');
          r = {...event.messages[0], ...event, source_name:event.messages[0]?.source_name || `${event.source_count} 个来源`, time:event.messages[0]?.time || doc.date, link:event.original_links[0]};
          returnHash = `#day/${doc.date}`;
        } else {
          r = sources.sources.flatMap(s=>s.messages).find(r=>r.id===parts[1]);
          if (!r) {
            for (const day of index.days) {
              const doc = await load(`history/${day}.json`);
              r = doc.messages.find(r=>r.id===parts[1]);
              if (r) { returnHash=`#day/${day}`; break; }
            }
          }
        }
        if (!r) throw new Error('消息不存在');
        html = back(returnHash,'返回列表') + `<article class="dt"><small>${e(r.source_name)} · ${e(r.time.slice(0,16).replace('T',' '))}</small><h1>${e(r.title)}</h1>${r.image ? `<img src="${e(r.image)}" alt="">` : ''}<h2>AI 摘要（样例）</h2><p>${e(r.summary)}</p>${original(r)}<p class="foot">${index.sample ? '示例摘录 · ' : ''}摘要可能不准确，请以原消息为准。</p></article>`;
      } else {
        let rows = live.messages;
        const day = query.get('day');
        if (day) {
          rows = rows.filter(r=>r.day===day);
          if (index.days.includes(day)) rows = (await load(`history/${day}.json`)).messages.filter(r=>query.get('all') === '1' || r.type==='telegram');
        }
        html = heading('资讯', `<a href="#history" aria-label="历史回顾">${icon('calendar-dots')}</a><a href="#sources" aria-label="来源">${icon('broadcast')}</a>`);
        html += `<p class="sub">${live.sample ? '示例数据 · ' : ''}${e(live.updated.slice(0,16).replace('T',' '))} 更新</p>` + controls(cat) + list(filter(rows,cat));
      }
      if (current !== generation) return;
      main.innerHTML = html;
      main.querySelectorAll('[data-category]').forEach(button => button.onclick = () => {
        const next = params();
        next.query.set('category',button.dataset.category);
        location.hash = next.parts.join('/') + '?' + next.query;
      });
      main.querySelectorAll('img').forEach(img => img.onerror = () => img.remove());
      window.scrollTo(0,0);
    } catch (error) {
      if (current === generation) {
        main.innerHTML = back('#feed','实时流') + `<p class="empty" role="alert">${e(error.message)}</p><button id="retry" class="btn">重试</button>`;
        document.getElementById('retry').onclick = route;
      }
    } finally {
      if (current === generation) main.removeAttribute('aria-busy');
    }
  };
  document.documentElement.dataset.theme = matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
  document.getElementById('theme').onclick = () => document.documentElement.dataset.theme = document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark';
  addEventListener('hashchange', route);
  route();
}
