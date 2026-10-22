/* Shared v0.3 application. No framework; publication data stays separate from presentation. */
(() => {
  'use strict';
  const script = document.querySelector('script[src$="visual.js"]');
  const base = new URL(script?.dataset.root || './', location.href);
  const e = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const icons = typeof ICONS === 'undefined' ? {} : ICONS;
  // Phosphor 2.1.1, MIT. This navigation glyph is absent from the older generated set.
  icons['book-open-text_line'] = '<svg viewBox="0 0 256 256" fill="currentColor" aria-hidden="true"><path d="M232,48H160a40,40,0,0,0-32,16A40,40,0,0,0,96,48H24a8,8,0,0,0-8,8V200a8,8,0,0,0,8,8H96a24,24,0,0,1,24,24,8,8,0,0,0,16,0,24,24,0,0,1,24-24h72a8,8,0,0,0,8-8V56A8,8,0,0,0,232,48ZM96,192H32V64H96a24,24,0,0,1,24,24V200A39.81,39.81,0,0,0,96,192Zm128,0H160a39.81,39.81,0,0,0-24,8V88a24,24,0,0,1,24-24h64ZM160,88h40a8,8,0,0,1,0,16H160a8,8,0,0,1,0-16Zm48,40a8,8,0,0,1-8,8H160a8,8,0,0,1,0-16h40A8,8,0,0,1,208,128Zm0,32a8,8,0,0,1-8,8H160a8,8,0,0,1,0-16h40A8,8,0,0,1,208,160Z"/></svg>';
  icons['book-open-text_fill'] = '<svg viewBox="0 0 256 256" fill="currentColor" aria-hidden="true"><path d="M232,48H168a32,32,0,0,0-32,32v87.73a8.17,8.17,0,0,1-7.47,8.25,8,8,0,0,1-8.53-8V80A32,32,0,0,0,88,48H24a8,8,0,0,0-8,8V200a8,8,0,0,0,8,8H96a24,24,0,0,1,24,23.94,7.9,7.9,0,0,0,5.12,7.55A8,8,0,0,0,136,232a24,24,0,0,1,24-24h72a8,8,0,0,0,8-8V56A8,8,0,0,0,232,48ZM208,168H168.27a8.17,8.17,0,0,1-8.25-7.47,8,8,0,0,1,8-8.53h39.73a8.17,8.17,0,0,1,8.25,7.47A8,8,0,0,1,208,168Zm0-32H168.27a8.17,8.17,0,0,1-8.25-7.47,8,8,0,0,1,8-8.53h39.73a8.17,8.17,0,0,1,8.25,7.47A8,8,0,0,1,208,136Zm0-32H168.27A8.17,8.17,0,0,1,160,96.53,8,8,0,0,1,168,88h39.73A8.17,8.17,0,0,1,216,95.47,8,8,0,0,1,208,104Z"/></svg>';
  const icon = (name, selected = false) => `<span class="ic" aria-hidden="true">${icons[name + (selected ? '_fill' : '_line')] || icons['newspaper_line'] || ''}</span>`;
  const names = {today:'拾光热榜',news:'资讯',hot:'资讯',play:'好玩',buy:'好买',fav:'收藏',mag:'每日简报',search:'搜索',columns:'栏目',history:'最近看过'};
  const tabs = [['today','今日','house'],['news','资讯','book-open-text'],['play','好玩','compass'],['buy','好买','shopping-bag'],['fav','收藏','bookmark-simple']];
  const groups = {play:['全部','北京','全国和世界','线上','看读'],buy:['全部','数码','家居户外','3D 打印','狗狗','大促']};
  const palette = {apps:['app','app-window','应用'],shows:['show','television-simple','剧集'],games:['game','game-controller','游戏'],exhibitions:['expo','ticket','展览演出'],stargazing:['star','moon-stars','观星'],apple:['apple','apple-logo','苹果'],'3d-printing':['print','cube','3D 打印']};
  let data, app, items = [], page = 'today', source = '', category = '全部', group = '全部', query = '', limit = 20, selected = null;
  let modal, previousFocus, toastTimer, installPrompt, activeDay = '', calendarMonth = '', status = 'normal', navigation = [], masonryObservers = [];
  const scope = document.body.dataset.bookmarkScope || 'public';
  const preferred = matchMedia('(prefers-color-scheme: dark)');
  preferred.addEventListener('change',event=>{if(!new URLSearchParams(location.search).has('theme'))document.documentElement.dataset.theme=event.matches?'dark':'light';});
  const key = 'shiguang-favorites-' + scope;
  const historyKey = 'rebang-history-' + scope;
  const read = (name, fallback) => { try { return JSON.parse(localStorage.getItem(name)) || fallback; } catch { return fallback; } };
  const save = (name, value) => { try { localStorage.setItem(name, JSON.stringify(value)); return true; } catch { return false; } };
  const saved = () => read(key, []);
  const isSaved = item => saved().some(x => x.id === item.id);
  const url = value => new URL(value, base).href;
  const date = value => new Date(value || data.updated).toLocaleDateString('zh-CN', {month:'long',day:'numeric',weekday:'short',timeZone:'Asia/Shanghai'}).replace('日周','日 周');
  const time = value => !value?'':String(value).length<=10?'仅日期':String(value).slice(0,10)===(activeDay||data.today)?String(value).slice(11,16):String(value).replace('T',' ').slice(5,16);
  const button = (name, action, label = name) => `<button class="ibtn" ${action} aria-label="${e(label)}">${icon(name)}</button>`;
  const header = title => `<header class="ph"><h1>${e(title)}</h1><div>${button('calendar-blank','data-modal="cal"','选日期')}${button('magnifying-glass','data-go="search"','搜索')}${button('list','data-modal="drawer"','全部导航')}</div></header>`;
  const meta = item => `<div class="meta">${[item.source,palette[item.category]?.[2]||item.category,item.date_label || time(item.time)].filter(Boolean).map(e).join(' · ')}</div>`;
  const bookmark = item => `<button class="bmk ${isSaved(item)?'on':''}" data-save="${e(item.id)}" aria-label="${isSaved(item)?'取消收藏':'收藏'}" aria-pressed="${isSaved(item)}">${icon('bookmark-simple',isSaved(item))}</button>`;
  const row = item => `<article class="row" data-item="${e(item.id)}"><button class="row-open" data-open="${e(item.id)}">${item.image?`<img class="thumb" src="${e(url(item.image))}" alt="" loading="lazy">`:''}<span class="tx"><span class="tt">${e(item.title)}</span>${meta(item)}</span></button>${bookmark(item)}</article>`;
  function card(item) {
    const [color,glyph,label] = palette[item.category] || ['app','newspaper',item.category];
    return `<article class="gc" data-item="${e(item.id)}"><button class="card-open" data-open="${e(item.id)}">${item.image?`<img class="cover" src="${e(url(item.image))}" alt="" loading="lazy">`:`<span class="trial-textcard" style="--tc-bg:var(--tc-${color}-bg);--tc-icon:var(--tc-${color}-icon)"><span>${names[item.kind]} · ${e(label)}</span>${icon(glyph)}</span>`}<span class="gt">${e(item.title)}</span></button>${item.tags?.length?`<span class="tag">${item.tags.map(e).join(' · ')}</span>`:''}${item.summary?`<p class="gx">${e(item.summary)}</p>`:''}${item.price?`<p class="price">${e(item.price)}</p>`:''}<div class="gm">${meta(item)}${bookmark(item)}</div></article>`;
  }
  const masonry = list => `<div class="mas">${list.map(card).join('')}</div>`;
  const section = (title, list, target, cards = false) => `<section><div class="sh"><h2>${title}<span class="n">${list.length}</span></h2><button data-go="${target}">更多 ${icon('caret-right')}</button></div>${cards?masonry(list.slice(0,4)):list.slice(0,5).map(row).join('')}</section>`;
  const chips = (labels, current, attr) => `<nav class="chips" aria-label="分类">${labels.map(x=>`<button ${attr}="${e(x)}" aria-pressed="${x===current}" class="${x===current?'on':''}">${e(x)}</button>`).join('')}</nav>`;
  const switcher = () => `<nav class="chips" aria-label="资讯视图"><button data-go="news" class="${page==='news'?'on':''}">速览</button><button data-go="hot" class="${page==='hot'?'on':''}">热点</button></nav>`;
  const empty = (text='这里还没有内容。') => `<div class="empty"><p>${text}</p><button class="text-button" data-go="today">看看今日</button></div>`;
  const skeleton = () => `<div class="skeleton" role="status" aria-label="加载中">${Array.from({length:6},()=>'<div class="row"><i class="sk thumb"></i><div class="tx"><i class="sk"></i><i class="sk"></i></div></div>').join('')}</div>`;
  function newsRows(list) {
    let last = '';
    return list.map(item=>{const heading=item.day!==last?`<h2 class="day">${date(item.day+'T12:00:00+08:00')}</h2>`:'';last=item.day;return heading+row(item);}).join('');
  }
  function grouping(item) {
    if (item.group) return item.group;
    if (item.kind==='play') return item.category==='exhibitions'?'北京':item.category==='stargazing'?'全国和世界':['apps','games'].includes(item.category)?'线上':'看读';
    return item.category==='3d-printing'?'3D 打印':/狗|宠物/.test(item.title)?'狗狗':/折扣|优惠|促销/.test(item.title)?'大促':item.category==='apple'?'数码':'家居户外';
  }
  function filteredNews() {
    return data.news.filter(x=>(!activeDay || x.day===activeDay) && (!source || (source==='saved'?isSaved(x):x.source_id===source)) && (category==='全部'||x.category===category));
  }
  function ranking(list = data.news) {
    return `<ol class="ranking">${[...list].sort((a,b)=>(b.heat||0)-(a.heat||0)).slice(0,20).map((item,i)=>`<li><span class="rank">${i+1}</span><button data-open="${e(item.id)}"><span class="tt">${e(item.title)}</span>${meta(item)}</button><div class="trend ${item.change<0?'down':'up'}"><span>${e(item.heat || '—')}</span><svg viewBox="0 0 70 24" aria-label="过去72小时来源提及"><polyline points="${e(item.spark || '0,22 70,22')}" fill="none" stroke="currentColor" stroke-width="2"/></svg></div></li>`).join('')}</ol>`;
  }
  function columns() {
    const list = page==='columns-tag' ? [...new Set(items.map(x=>x.category))].map(name=>({name,id:name})) : data.sources;
    return chips(['按来源','按标签'],page==='columns-tag'?'按标签':'按来源','data-columns')+`<button class="column-row" data-go="mag">${icon('book-open-text')}<span><b>每日简报</b><span class="meta">${data.magazines.length} 条 · 栏目里的长内容</span></span>${icon('caret-right')}</button>`+list.map(s=>{const members=items.filter(x=>page==='columns-tag'?x.category===s.id:x.source_id===s.id);return `<button class="column-row" data-${page==='columns-tag'?'tag':'source-page'}="${e(s.id)}">${icon(/github/i.test(s.id)?'github-logo':/推特|twitter|^x$/i.test(s.name)?'x-logo':'telegram-logo')}<span><b>${e(s.name)}</b><span class="meta">${e(members[0]?.title || '暂无新内容')}</span></span><span class="meta">${members.filter(x=>x.day===data.today).length}</span>${icon('caret-right')}</button>`;}).join('');
  }
  function sourcePage() {
    const type = page.slice(4);
    const s = data.sources.find(s=>s.id===source) || data.sources.find(s=>type==='channel'?s.type==='telegram':new RegExp(type==='x'?'推特|twitter|^x$':type==='world'?'环球|world':type,'i').test(s.id+' '+s.name));
    const list = items.filter(x=>x.source_id===s?.id);
    const markets = data.markets || [];
    return `<div class="source-head">${icon(type==='github'?'github-logo':type==='x'?'x-logo':type==='world'?'globe':'telegram-logo')}<h1>${e(s?.name || ({github:'GitHub 热门',x:'推特爆款',world:'环球要闻',channel:'频道'}[type]))}</h1><p>${e(s?.description || '每日精选')} · ${time(data.updated)} 更新</p></div>`+(type==='world'?`<div class="markets">${markets.map(m=>`<div><span>${e(m.name)}</span><b>${e(m.value)}</b><span class="${/^[−-]/.test(String(m.change))?'down':'up'}">${e(m.change)}${String(m.change).includes('%')?'':'%'}</span></div>`).join('')}</div>`:'')+list.map(x=>type==='github'?`<article class="repo">${row(x)}<p class="meta">${icon('star')} ${e(x.stars ?? '—')} · ${e(x.language || '语言未提供')}</p></article>`:row(x)).join('')+(list.length?'':empty('此来源暂无已发布内容。'));
  }
  function content() {
    const news = filteredNews();
    if(!navigator.onLine&&!items.length)return `<div class="empty"><p>连不上网，这台设备上也还没有缓存。</p><p>连上网后打开一次，之后离线也能看。</p><button class="text-button" data-retry>重试</button></div>`;
    if (status==='loading') return skeleton();
    if (status==='empty') return empty();
    if (status==='error') return `<div class="failure" role="alert"><p>内容加载失败</p><p>无法读取本地缓存，请检查连接。</p><button data-retry>重试</button></div>`;
    if (page==='today') return `<p class="date">${date(data.updated)} · ${String(data.updated).slice(11,16)} 更新</p>`+section('资讯',news.filter(x=>x.image).concat(news.filter(x=>!x.image)),'news')+section('好玩',data.cards.filter(x=>x.kind==='play'),'play',true)+section('好买',data.cards.filter(x=>x.kind==='buy'),'buy',true);
    if (page==='news') return switcher()+`<nav class="fico" aria-label="来源筛选">${[['','全部','squares-four'],...data.sources.filter(s=>data.news.some(x=>x.source_id===s.id)).map(s=>[s.id,s.name,/github/i.test(s.id)?'github-logo':'telegram-logo']),['saved','收藏','bookmark-simple']].map(([id,label,glyph])=>`<button data-source="${e(id)}" aria-label="${e(label)}" aria-pressed="${source===id}" class="${source===id?'on':''}">${icon(glyph,source===id)}</button>`).join('')}</nav>`+chips(['全部',...new Set(data.news.map(x=>x.category))],category,'data-category')+newsRows(news.slice(0,limit))+(news.length>limit?'<button class="load-more" data-more>加载更多</button>':'<p class="end">到底了，已加载日期的资讯都在这里。</p>');
    if (page==='hot') return switcher()+ranking();
    if (['play','buy'].includes(page)) {const list=data.cards.filter(x=>x.kind===page&&(group==='全部'||grouping(x)===group));return chips(groups[page],group,'data-group')+(list.length?masonry(list):empty('这个分组还没有内容。'));}
    if (page==='fav') {const list=saved().map(x=>({...x,kind:x.kind||'news'}));return chips(['全部','资讯','好玩','好买'],category,'data-category')+(list.filter(x=>category==='全部'||names[x.kind]===category||category==='资讯'&&x.kind==='news').map(row).join('')||empty('还没有收藏，点书签留住喜欢的内容。'));}
    if (page==='mag') return data.magazines.map(x=>`<article class="mag" data-item="${e(x.id)}"><button data-open="${e(x.id)}">${x.image?`<img src="${e(url(x.image))}" alt="">`:''}<h2>${e(x.title)}</h2><p>${e(x.summary)}</p>${meta(x)}</button></article>`).join('')||empty('今天没有新的每日简报。');
    if (page==='detail') return selected?`${button('arrow-left','data-back','返回')}<article class="detail" data-item="${e(selected.id)}">${selected.image?`<button class="detail-image" data-modal="lightbox"><img src="${e(url(selected.image))}" alt="${e(selected.title)}"></button>`:''}<h1>${e(selected.title)}</h1>${meta(selected)}${selected.kind==='news'?'':`<p>${e(selected.summary)}</p>`}<div class="gm"><a class="text-button" href="${e(selected.url)}" target="_blank" rel="noopener noreferrer">阅读原文</a>${bookmark(selected)}</div></article>`:empty('条目已不在已加载内容中。');
    if (page==='search') {const results=items.filter(x=>(!activeDay||x.day===activeDay)&&(x.title+' '+x.summary+' '+x.source).toLocaleLowerCase().includes(query.toLocaleLowerCase()));return `<label class="search">${icon('magnifying-glass')}<input id="visual-query" type="search" aria-label="仅搜索已加载日期" placeholder="仅搜索已加载日期" value="${e(query)}"></label><p class="meta">只搜索已加载日期</p><div id="visual-results">${query?(results.map(row).join('')||empty('没有找到相关内容。')):empty('输入关键词，搜索已加载的内容。')}</div>`;}
    if (page.startsWith('columns')) return columns();
    if (page.startsWith('src-')) return sourcePage();
    if (page==='history') {let last='';return read(historyKey,[]).map(x=>{const d=x.viewed.slice(0,10),h=last!==d?`<h2 class="day">${date(x.viewed)}</h2>`:'';last=d;return h+row(x)+`<p class="meta">看于 ${x.viewed.slice(11,16)}</p>`;}).join('')||empty('还没有浏览记录。');}
    if (page==='first') return `<div class="first"><img class="app-icon" src="${url('icon-192.png')}" alt="拾光热榜"><h1>拾光热榜</h1><p>今日信息，留一份清晰。</p><p>资讯持续更新，好玩、好买每天一份。</p><p>收藏只存在这台设备，无需注册。</p><button class="primary" data-start>开始看今天</button><button data-modal="pwa">加到主屏幕</button></div>`;
    return empty();
  }
  function render() {
    if (!app) return;
    masonryObservers.forEach(observer=>observer.disconnect());masonryObservers=[];
    const current = page==='hot'?'news':page;
    const nav=cls=>`<nav class="${cls}" aria-label="主导航">${tabs.map(([id,label,glyph])=>`<button data-go="${id}" class="${current===id?'on':''}" ${current===id?'aria-current="page"':''}>${icon(glyph,current===id)}<span>${label}</span></button>`).join('')}</nav>`;
    app.innerHTML=`<aside class="sidebar"><a class="logo" href="${url('index.html')}">拾光热榜</a>${nav('side-nav')}<button data-go="columns">${icon('rows')}栏目</button><button data-go="history">${icon('clock-counter-clockwise')}最近看过</button><button data-modal="pwa">${icon('plus-square')}加到主屏幕</button></aside><div class="visual-scroll"><main class="visual-main">${!['detail','first'].includes(page)?header(names[page]|| (page.startsWith('columns')?'栏目':'')):''}${activeDay?`<div class="capsule">${date(activeDay+'T12:00:00+08:00')}<button data-today>回到今天</button></div>`:''}<div id="offline-banner"></div><div id="visual-content">${content()}</div></main><aside class="rail"><div class="sh"><h2>热点</h2></div>${ranking(data.news.slice(0,6))}<button data-go="columns">栏目 ${icon('caret-right')}</button></aside></div><div class="bar-backing" aria-hidden="true"></div>${nav('bar')}<dialog id="visual-dialog"></dialog><div id="visual-toast" role="status" aria-live="polite" hidden></div>`;
    modal=app.querySelector('dialog');
    modal.addEventListener('click',event=>{if(event.target===modal)closeModal();});
    modal.addEventListener('close',()=>{const notice=modal.querySelector('#visual-toast');if(notice)app.append(notice);previousFocus?.focus({preventScroll:true});});
    modal.addEventListener('keydown',event=>{
      if(event.key!=='Tab')return;
      const controls=[...modal.querySelectorAll('button:not(:disabled),a[href],input')].filter(x=>x.getClientRects().length);
      const first=controls[0],last=controls.at(-1);
      if(event.shiftKey&&document.activeElement===first){event.preventDefault();last?.focus();}
      else if(!event.shiftKey&&document.activeElement===last){event.preventDefault();first?.focus();}
    });
    app.querySelectorAll('img').forEach(image=>image.addEventListener('error',()=>{image.classList.add('image-failed');image.alt='图片暂不可用';},{once:true}));
    app.querySelectorAll('.mas').forEach(grid=>{
      if(typeof ResizeObserver==='undefined')return;
      const observer=new ResizeObserver(entries=>entries.forEach(({target})=>{target.style.gridRowEnd=`span ${Math.ceil((target.getBoundingClientRect().height+20)/21)}`;}));
      masonryObservers.push(observer);
      [...grid.children].forEach(card=>observer.observe(card));
    });
    if (!navigator.onLine) offline();
  }
  function go(target, remember = true) {
    if (remember) navigation.push({page,source,category,group,selected,scroll:scrollY});
    page=target;category='全部';group='全部';limit=20;status='normal';
    if(target==='today'){source='';activeDay='';calendarMonth='';}
    if(remember)history.pushState({visual:true},'',`#screens/${target}`);
    else history.replaceState({visual:true},'',`#screens/${target}`);
    render(); scrollTo(0,0);
  }
  function openItem(id) {
    const item=items.find(x=>x.id===id)||saved().find(x=>x.id===id);if(!item)return;
    const old=read(historyKey,[]).filter(x=>x.id!==id);
    save(historyKey,[{...item,viewed:new Date().toISOString()},...old].slice(0,200));
    go('detail');selected=item;render();
  }
  function closeModal() {modal.close();}
  function showModal(type) {
    previousFocus=document.activeElement;
    modal.className=type==='drawer'?'drawer':type==='lightbox'?'lightbox':'sheet';
    let inner='';
    if(type==='drawer') inner=`<div class="modal-head"><h2>拾光热榜</h2>${button('x','data-close-modal','关闭')}</div>${[...tabs.map(([id,label])=>[id,label]),['columns','栏目'],['mag','每日简报'],['history','最近看过']].map(([id,label])=>`<button class="drawer-link ${page===id?'on':''}" data-go="${id}">${icon(id==='columns'?'rows':id==='history'?'clock-counter-clockwise':tabs.find(x=>x[0]===id)?.[2]||'book-open-text',page===id)}${label}</button>`).join('')}<button data-modal="pwa" class="drawer-link">加到主屏幕</button><button data-settings class="drawer-link">设置</button>`;
    if(type==='cal') {
      const current=new Date((calendarMonth||activeDay||data.today)+'T12:00:00+08:00'),year=current.getFullYear(),month=current.getMonth();
      const start=new Date(year,month,1).getDay(),count=new Date(year,month+1,0).getDate();
      inner=`<div class="modal-head"><h2>看往日</h2>${button('x','data-close-modal','关闭')}</div><div class="calendar-month">${button('caret-left','data-month="-1"','上个月')}<span>${year} 年 ${month+1} 月</span>${button('caret-right','data-month="1"','下个月')}</div><div class="calendar">${'日一二三四五六'.split('').map(x=>`<span>${x}</span>`).join('')}${'<span></span>'.repeat(start)}${Array.from({length:count},(_,i)=>{const d=`${year}-${String(month+1).padStart(2,'0')}-${String(i+1).padStart(2,'0')}`;return `<button data-date="${d}" aria-label="${d}${data.days.includes(d)?' 有存档':' 没有存档'}" class="${d===(activeDay||data.today)?'selected':''} ${data.days.includes(d)?'':'unavailable'}">${i+1}</button>`;}).join('')}</div>`;
    }
    if(type==='pwa') inner=`<div class="modal-head"><h2>加到主屏幕</h2>${button('x','data-close-modal','关闭')}</div><img class="app-icon" src="${url('icon-192.png')}" alt="拾光热榜"><h2>把拾光热榜加到主屏幕</h2><p>全屏打开，离线也能看最近一次的内容。</p><ol class="install-steps"><li>点 Safari 的分享按钮</li><li>选择「添加到主屏幕」</li><li>点右上角「添加」</li></ol><button class="primary" data-install>${installPrompt?'安装':'知道了'}</button><button data-close-modal>以后再说</button>`;
    if(type==='lightbox') {const item=selected||items.find(x=>x.image);inner=`<div class="modal-head">${button('x','data-close-modal','关闭')}<span>1 / 1</span></div>${item?.image?`<img class="lightbox-image" src="${e(url(item.image))}" alt="${e(item.title)}"><div class="lightbox-footer"><p>${e(item.source)}</p><a href="${e(url(item.image))}" download>保存图片</a></div>`:empty('没有图片。')}`;}
    modal.setAttribute('aria-label',{drawer:'全部导航',cal:'选日期',pwa:'加到主屏幕',lightbox:'看大图'}[type]);
    modal.innerHTML=inner;if(!modal.open)modal.showModal();modal.querySelector('button')?.focus();
  }
  function toast(message, label, action) {
    clearTimeout(toastTimer);const element=app.querySelector('#visual-toast');element.hidden=false;
    if(modal.open)modal.append(element);
    element.innerHTML=`<span>${e(message)}</span>${label?`<button>${e(label)}</button>`:''}`;
    element.querySelector('button')?.addEventListener('click',()=>{action?.();element.hidden=true;});
    toastTimer=setTimeout(()=>element.hidden=true,2500);
  }
  async function refresh() {
    const main=app.querySelector('.visual-main');const indicator=document.createElement('div');indicator.className='ptr';indicator.textContent='正在更新…';main.prepend(indicator);
    try {const response=await fetch(url('visual-data.json'),{cache:'reload'});if(!response.ok)throw Error();const next=await response.json();accept(next);render();toast('已更新','回到顶部',()=>scrollTo(0,0));}
    catch {indicator.remove();toast('没更新成功','重试',refresh);}
  }
  function offline() {
    const element=app.querySelector('#offline-banner');if(!element)return;
    if(!items.length){element.innerHTML='';return;}
    element.innerHTML=`<div class="offline"><p>离线中，显示 ${time(data.updated)} 的缓存</p><button data-retry>重试</button></div>`;
  }
  function accept(next) {if(next.scope&&next.scope!==scope)throw Error('缓存范围不匹配');data=next;items=[...new Map([...data.news,...data.cards,...data.magazines].map(item=>[item.id,item])).values()];}
  function attach() {
    app.addEventListener('click',event=>{
      const t=event.target.closest('button,a');if(!t)return;const d=t.dataset;
      if(d.go){if(modal.open)closeModal();go(d.go);}
      if(d.open)openItem(d.open);
      if('back'in d){const old=navigation.pop();if(old){({page,source,category,group,selected}=old);history.replaceState({visual:true},'',`#screens/${page}`);render();scrollTo(0,old.scroll);}else go('today',false);}
      if(d.modal)showModal(d.modal);
      if('closeModal'in d)closeModal();
      if('source'in d){source=d.source;limit=20;render();}
      if(d.category){category=d.category;render();}
      if(d.group){group=d.group;render();}
      if(d.columns)go(d.columns==='按标签'?'columns-tag':'columns');
      if(d.sourcePage){source=d.sourcePage;const s=data.sources.find(s=>s.id===source);go(/github/i.test(source)?'src-github':/twitter|推特|^x$/i.test(source+' '+s?.name)?'src-x':/环球|world/i.test(source+' '+s?.name)?'src-world':'src-channel');}
      if(d.tag){category=d.tag;page='news';render();}
      if('more'in d){limit+=20;render();}
      if('today'in d){activeDay='';go('today');}
      if(d.date){if(data.days.includes(d.date)){activeDay=d.date;closeModal();go('news');}else toast('这一天没有存档');}
      if(d.month){const current=new Date((calendarMonth||activeDay||data.today)+'T12:00:00+08:00');current.setMonth(current.getMonth()+Number(d.month),1);calendarMonth=`${current.getFullYear()}-${String(current.getMonth()+1).padStart(2,'0')}-01`;showModal('cal');}
      if('retry'in d)refresh();
      if('start'in d){save('rebang-onboarded',true);go('today');}
      if('install'in d){if(installPrompt){installPrompt.prompt();installPrompt=null;}closeModal();}
      if('settings'in d)toast('外观跟随系统，收藏保存在这台设备。');
      if(d.save){const item=items.find(x=>x.id===d.save)||saved().find(x=>x.id===d.save);if(!item)return;const before=saved(),on=isSaved(item),next=on?before.filter(x=>x.id!==item.id):[{...item,snippet:item.summary||''},...before];if(!save(key,next)){toast('无法保存，请检查设备存储空间。');return;}render();toast(on?'已取消收藏':'已收藏',on?'撤销':'查看',()=>{if(on){save(key,before);render();}else go('fav');});}
    });
    app.addEventListener('input',event=>{if(event.target.id==='visual-query'){query=event.target.value;const start=event.target.selectionStart;render();const input=app.querySelector('#visual-query');input.focus();input.setSelectionRange(start,start);}});
    let startY=null;
    app.addEventListener('touchstart',event=>{if(scrollY===0&&!modal.open)startY=event.touches[0].clientY;},{passive:true});
    app.addEventListener('touchmove',event=>{if(startY!==null&&event.touches[0].clientY-startY>56&&!app.querySelector('.ptr')){const hint=document.createElement('div');hint.className='ptr';hint.textContent='松开刷新';app.querySelector('.visual-main').prepend(hint);}},{passive:true});
    app.addEventListener('touchend',()=>{if(app.querySelector('.ptr')){app.querySelector('.ptr').remove();refresh();}startY=null;});
    addEventListener('offline',offline);addEventListener('online',()=>{app.querySelector('#offline-banner').innerHTML='';refresh();});
    addEventListener('storage',()=>render());
    addEventListener('beforeinstallprompt',event=>{event.preventDefault();installPrompt=event;});
    addEventListener('popstate',event=>{if(event.state?.visual){const target=location.hash.replace(/^#screens\//,'');if(target){page=target;render();}}});
    addEventListener('hashchange',()=>{const target=location.hash.replace(/^#screens\//,'');if(target==='look'){go('news',false);return;}if(target)go(target,false);});
  }
  async function init() {
    // Keep standalone and no-data pages readable; activate only when this build published data.
    let next;
    try {const response=await fetch(url('visual-data.json'));if(!response.ok)return;next=await response.json();accept(next);save('rebang-cache-'+scope,next);}
    catch {
      next=read('rebang-cache-'+scope,null);
      if(!next){next={today:new Date().toISOString().slice(0,10),updated:new Date().toISOString(),news:[],cards:[],magazines:[],sources:[],days:[]};status='empty';}
      accept(next);
    }
    const path=location.pathname;const sourceId=path.slice(base.pathname.length).split('/')[0];
    const sourceInfo=data.sources.find(x=>x.id===sourceId);
    const archive=path.match(/\/archive\/(\d{4}-\d{2}-\d{2})\.html$/);
    const core=/\/(index|play|buy|favorites|hot|columns)\.html$/.test(path)||path.endsWith('/')||sourceInfo||archive;
    const route=location.hash.startsWith('#screens/')?location.hash.slice(9):'';
    if(!core&&!route)return;
    page=route==='look'?'news':route||({play:'play',buy:'buy',favorites:'fav',hot:'hot',columns:'columns'}[path.split('/').pop().split('.')[0]]||'today');
    if(sourceInfo&&!route){source=sourceId;page=/github/i.test(sourceId)?'src-github':/^x$/i.test(sourceId)?'src-x':/world/.test(sourceId)?'src-world':'src-channel';}
    if(archive){activeDay=archive[1];page='news';}
    const parameters=new URLSearchParams(location.search);
    if(parameters.has('source')){source=parameters.get('source');page='news';}
    if(parameters.has('topic')){category=parameters.get('topic');page='news';}
    document.documentElement.classList.add('visual-v03');
    app=document.createElement('div');app.id='visual-app';document.body.append(app);attach();render();
    if('serviceWorker' in navigator && ['https:','http:'].includes(location.protocol)) navigator.serviceWorker.register(url('sw.js')+'?scope='+scope,{scope:base.pathname}).catch(()=>{});
    window.rebang = {go,refresh,showModal,toast,get data(){return data;},get page(){return page;},
      // QA uses the same renderer and event handlers, with an explicit offline fixture catalogue.
      setState(state){if(state.data)accept(state.data);if(state.page)page=state.page;if(state.status)status=state.status;if('query'in state)query=state.query;if(state.item)selected=items.find(x=>x.id===state.item);if(state.day)activeDay=state.day;render();}};
    if(!read('rebang-onboarded',false)&&!route){save('rebang-onboarded',true);page='first';render();}
  }
  init();
})();
