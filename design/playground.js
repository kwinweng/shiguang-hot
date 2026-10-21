/* Review-only state. Never reads production datasets or production storage keys. */
(async () => {
  const ui = window.ShiguangUI;
  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) => [
    ...root.querySelectorAll(selector),
  ];
  const root = document.documentElement;
  root.classList.toggle(
    "focus-preview",
    new URLSearchParams(location.search).get("focus") === "1",
  );
  const prefix = "shiguang-design-v05:";
  let storageWarned = false;
  function read(key, fallback) {
    try {
      return JSON.parse(localStorage.getItem(prefix + key)) ?? fallback;
    } catch {
      return fallback;
    }
  }
  function write(key, value) {
    try {
      localStorage.setItem(prefix + key, JSON.stringify(value));
      return true;
    } catch {
      if (!storageWarned) {
        ui.toast("本机存储不可用；本次修改会在刷新后恢复。");
        storageWarned = true;
      }
      return false;
    }
  }
  let data;
  try {
    if (window.__SHIGUANG_DESIGN_SAMPLES__)
      data = window.__SHIGUANG_DESIGN_SAMPLES__;
    else {
      const response = await fetch("/design/samples.json", {
        cache: "no-store",
      });
      if (!response.ok) throw new Error("sample load");
      data = await response.json();
    }
    if (data.example !== true) throw new Error("not fixtures");
  } catch {
    ui.toast("示例未能载入，请刷新重试。");
    return;
  }
  const items = new Map(data.items.map((item) => [item.id, item]));
  const names = { look: "资讯", play: "好玩", buy: "好买" };
  const templates = new Map();
  for (const [id, item] of items) {
    const panel = $(`[data-panel="${item.kind}"]`);
    const card = $(`[data-item="${id}"]`, item.kind === "look" ? $("[data-news-templates]").content : panel);
    if (card) templates.set(id, card.cloneNode(true));
  }
  const saved = read("saved", {});
  const validSaved =
    saved && !Array.isArray(saved) && typeof saved === "object" ? saved : {};
  for (const id of Object.keys(validSaved))
    if (!items.has(id) || !Number.isFinite(validSaved[id]))
      delete validSaved[id];
  const state = {
    page: "today",
    section: "screens",
    news: window.ShiguangNews.createModel(data).normalize(new URLSearchParams(location.search)),
    saved: validSaved,
    savedFilter: "全部",
    filters: { play: "全部", buy: "全部" },
    queries: { play: "", buy: "" },
    dog: { play: false, buy: false },
  };
  const scrolls = {};
  let overrides = read("tokens", { light: {}, dark: {} });
  if (!overrides || !overrides.light || !overrides.dark)
    overrides = { light: {}, dark: {} };
  const prefs = read("prefs", {});
  function currentTheme() {
    return root.dataset.theme;
  }
  const tokenNames = [
    "--action",
    "--page",
    "--surface",
    "--radius-card",
    "--font-body",
    "--card-padding",
  ];
  function applyTokens() {
    tokenNames.forEach((name) => root.style.removeProperty(name));
    const theme = currentTheme();
    for (const [name, value] of Object.entries(overrides[theme] || {})) {
      const color = ["--action", "--page", "--surface"].includes(name);
      if (
        tokenNames.includes(name) &&
        (color ? /^#[\da-f]{6}$/i.test(value) : /^\d{1,2}px$/.test(value))
      )
        root.style.setProperty(name, value);
    }
    const style = getComputedStyle(root);
    $$("[data-token]").forEach((input) => {
      const value = style.getPropertyValue(input.dataset.token).trim();
      input.value = input.dataset.unit ? parseFloat(value) : value;
    });
    ui.layout();
  }
  function control(key, value) {
    if (
      !(
        {
          theme: ["light", "dark"],
          viewport: ["desktop", "phone"],
          density: ["comfortable", "compact"],
        }[key] || []
      ).includes(value)
    )
      return;
    if (key === "viewport") $(".device").dataset.viewport = value;
    else root.dataset[key] = value;
    $$(`[data-control="${key}"]`).forEach((button) =>
      button.setAttribute(
        "aria-pressed",
        String(button.dataset.value === value),
      ),
    );
    prefs[key] = value;
    write("prefs", prefs);
    applyTokens();
  }
  control("theme", prefs.theme || "light");
  control(
    "viewport",
    prefs.viewport || (innerWidth < 768 ? "phone" : "desktop"),
  );
  control("density", prefs.density || "comfortable");
  function persistSaved() {
    write("saved", state.saved);
    syncSaved();
  }
  function syncSaved() {
    $$("[data-save]").forEach((button) => {
      const yes = !!state.saved[button.dataset.save];
      button.setAttribute("aria-pressed", String(yes));
      button.setAttribute(
        "aria-label",
        `${yes ? "取消收藏" : "收藏"}：${items.get(button.dataset.save)?.title || "示例"}`,
      );
    });
    renderSaved();
  }
  function renderSaved() {
    const savedItems = Object.keys(state.saved)
      .filter((id) => items.has(id))
      .sort((a, b) => state.saved[b] - state.saved[a]);
    const kinds = ["look", "play", "buy"].filter((kind) =>
      savedItems.some((id) => items.get(id).kind === kind),
    );
    if (state.savedFilter !== "全部" && !kinds.includes(state.savedFilter))
      state.savedFilter = "全部";
    const filters = $("[data-saved-filters]");
    filters.replaceChildren();
    for (const value of ["全部", ...kinds]) {
      const button = document.createElement("button");
      button.className = "chip";
      button.textContent = names[value] || value;
      button.dataset.savedFilter = value;
      button.setAttribute("aria-pressed", String(value === state.savedFilter));
      filters.append(button);
    }
    const list = $("[data-saved-list]");
    list.replaceChildren();
    for (const id of savedItems) {
      const item = items.get(id);
      if (state.savedFilter !== "全部" && item.kind !== state.savedFilter)
        continue;
      const wrapper = document.createElement("section");
      const label = document.createElement("p");
      label.className = "collection-type";
      label.textContent = names[item.kind];
      const card = templates.get(id).cloneNode(true);
      const save = $("[data-save]", card);
      save.setAttribute("aria-pressed", "true");
      save.setAttribute("aria-label", `取消收藏：${item.title}`);
      wrapper.append(label, card);
      list.append(wrapper);
    }
    $("[data-saved-empty]").hidden = !!savedItems.length;
  }
  function toggleSave(id) {
    const previous = state.saved[id];
    if (previous) delete state.saved[id];
    else state.saved[id] = Date.now();
    persistSaved();
    ui.toast(previous ? "已取消收藏" : "已收藏到这台设备", () => {
      if (previous) state.saved[id] = previous;
      else delete state.saved[id];
      persistSaved();
    });
  }
  function setHash(replace = false) {
    const url = new URL(location.href);
    url.hash = state.section === 'screens' ? `screens/${state.page}` : state.section;
    const queryKeys = ['date','view','topic','subtopic','source','q'];
    queryKeys.forEach(k => url.searchParams.delete(k));
    if (state.section === 'screens' && state.page === 'look') url.search = newsModel.params(state.news, url.search).toString();
    if (url.href !== location.href) history[replace ? 'replaceState' : 'pushState'](null, '', url);
    updateFocusLink();
  }
  function updateFocusLink() {
    const url = new URL(location.href); url.hash = `screens/${state.page}`;
    ['date','view','topic','subtopic','source','q'].forEach(k => url.searchParams.delete(k));
    if (state.page === 'look') url.search = newsModel.params(state.news, url.search).toString();
    url.searchParams.set('focus','1'); $('[data-focus-link]').href = url.href;
  }
  function section(key, update = true) {
    if (!["foundations", "components", "patterns", "screens"].includes(key))
      key = "screens";
    state.section = key;
    $$(".review-panel").forEach((p) => (p.hidden = p.id !== key));
    $$("[data-section]").forEach((a) =>
      a.setAttribute(
        "aria-current",
        a.dataset.section === key ? "page" : "false",
      ),
    );
    if (update) setHash();
    ui.layout();
  }
  function page(key, update = true) {
    if (!["today", "look", "play", "buy", "saved"].includes(key)) return;
    const scroller = $(".app-scroll");
    scrolls[state.page] = scroller.scrollTop;
    state.page = key;
    updateFocusLink();
    $$(".app-panel").forEach(
      (panel) => (panel.hidden = panel.dataset.panel !== key),
    );
    $$("[data-page]")
      .filter((button) => button.closest(".bottom-nav,.screen-jumps"))
      .forEach((button) =>
        button.setAttribute(
          "aria-current",
          button.dataset.page === key ? "page" : "false",
        ),
      );
    section("screens", false);
    if (key === "saved") renderSaved();
    requestAnimationFrame(() => {
      scroller.scrollTop = scrolls[key] || 0;
      ui.layout();
    });
    if (update) setHash();
  }
  function mode(key) { setNews({view:key}); }
  // All query state below belongs to fixture news; other pages retain their own state.
  const foldStates = new Map();
  const newsModel = window.ShiguangNews.createModel(data);
  function node(tag, cls, text) {
    const result = document.createElement(tag);
    if (cls) result.className = cls;
    if (text !== undefined) result.textContent = text;
    return result;
  }
  function newsDateLabel(date) {
    return window.ShiguangNews.validDate(date) ? new Intl.DateTimeFormat('zh-CN', {
      timeZone: 'Asia/Shanghai', year: 'numeric', month: 'long', day: 'numeric',
    }).format(new Date(date + 'T00:00:00+08:00')) : '无效日期';
  }
  function newsCard(item, hero = false) {
    const card = templates.get(item.id).cloneNode(true);
    if (hero) {
      card.classList.add('hero-card');
      const badge = node('span', 'news-row-badge', '要闻');
      badge.setAttribute('aria-hidden', 'true');
      $('h3', card).prepend(badge);
    }
    return card;
  }
  function renderNews() {
    const result = newsModel.query(state.news);
    const n = result.state;
    state.news = n;
    const dateLabel = $('[data-news-date-label]');
    dateLabel.textContent = window.ShiguangNews.validDate(n.date) && n.date.slice(0,4) === data.date.slice(0,4)
      ? `${Number(n.date.slice(5,7))}月${Number(n.date.slice(8,10))}日` : newsDateLabel(n.date);
    dateLabel.closest('button').setAttribute('aria-label', newsDateLabel(n.date));
    $$('[data-mode]').forEach(b => {
      b.setAttribute('aria-selected', String(b.dataset.mode === n.view));
      b.tabIndex = b.dataset.mode === n.view ? 0 : -1;
    });
    $$('[data-look-view]').forEach(v => { v.hidden = v.dataset.lookView !== n.view; v.replaceChildren(); });
    $$('[data-filter-scope="look"]').forEach(b => b.setAttribute('aria-pressed', String(b.dataset.filter === n.topic)));
    $('[data-search="look"]').value = n.q;
    $('[data-source]').value = n.source;
    $('[data-subtopic]').value = n.subtopic;
    $('[data-subtopic-label]').hidden = n.topic !== '科技';
    const info = $('[data-news-source-info]');
    const source = newsModel.sources.get(n.source);
    info.hidden = !source || source.kind !== 'column';
    info.replaceChildren();
    if (!info.hidden) {
      info.append(node('span', '', source.name+' · '));
      const url = source.issues?.[n.date];
      if (url && /^https:\/\/example\.org\//.test(url)) {
        const link = node('a', 'source-link', '阅读完整期刊（示例）');
        link.href = url; link.target = '_blank'; link.rel = 'noopener noreferrer'; info.append(link);
      } else info.append(node('span', 'muted', '该日没有完整期刊示例'));
    }
    const empty = $('[data-news-empty]');
    empty.hidden = result.status === 'ok';
    const messages = {
      'invalid-date': ['日期格式不正确', '请从日历选择可用的示例日期。'],
      future: ['未来日期不可选', '不会用今天的资讯替代所选日期。'],
      missing: ['该日没有可用存档', '示例存档并不连续，请选择其他日期。'],
      'invalid-filter': ['这个筛选条件无法识别', '旧主题和来源别名会保留语义；无法识别的条件请手动清除。'],
      'hot-expired': ['该日期的热点未保留', '热点仅保留最近3个自然日；可查看所选日期的速览。'],
      'ineligible-source': ['此来源不参与热点', 'GitHub热门与推特爆款保留在速览，可切换视图或清除来源。'],
      'no-hot': ['这一天尚无热点事件', '该日仍在热点保留范围内，速览中的资讯可以正常查阅。'],
      'empty-archive': ['这一天的资讯存档为空', '这是一个有效的示例存档日，与日期没有存档的情况不同。'],
      'empty-hot': ['这一天没有匹配的热点', '日期仍在热点保留范围内。可清除筛选，或查看当日速览。'],
      'empty-brief': ['这一天没有匹配的资讯', '该日期有资讯存档；当前主题、来源或关键词没有匹配内容。'],
    };
    if (!empty.hidden) {
      const message = messages[result.status];
      $('h3', empty).textContent = message[0]; $('p', empty).textContent = message[1];
      $('[data-news-brief]', empty).hidden = n.view !== 'hot';
      $('[data-news-clear-source]', empty).hidden = result.status !== 'ineligible-source';
    }
    const count = n.view === 'hot' ? result.events.length : result.rows.length + (result.headline ? 1 : 0);
    $('[data-news-caption]').textContent = newsDateLabel(n.date)+' · '+(n.view === 'hot' ? `${count}个事件` : `${count}条资讯`)+(n.subtopic !== '全部' ? ' · '+n.subtopic : '')+' · 示例存档';
    if (n.view === 'brief') {
      const list = $('[data-look-view="brief"]');
      if (result.headline) list.append(newsCard(result.headline, true));
      for (const run of newsModel.runs(result.rows)) {
        if (run.length <= 3 || n.source !== '全部') {
          run.forEach(item => list.append(newsCard(item))); continue;
        }
        run.slice(0, 3).forEach(item => list.append(newsCard(item)));
        const fold = node('details', 'source-fold');
        const key = n.date+':'+run.map(i => i.id).join(',');
        fold.open = !!n.q || !!foldStates.get(key);
        const summary = node('summary', '', `${run[0].source} 连续${run.length}条 · 其余${run.length-3}条`);
        fold.append(summary);
        run.slice(3).forEach(item => fold.append(newsCard(item)));
        // Search opens matched runs, but never changes the reader's stored choice.
        fold.addEventListener('toggle', () => { if (!n.q && fold.isConnected) foldStates.set(key, fold.open); });
        list.append(fold);
      }
    } else if (n.view === 'hot' && result.events.length) {
      const list = $('[data-look-view="hot"]');
      const map = node('div', 'hour-map'); map.setAttribute('aria-label', '24小时示例时间轴');
      for (let hour = 0; hour < 24; hour++) {
        const h = String(hour).padStart(2, '0');
        const found = result.events.some(e => e.hour === h);
        const button = node('button'); button.dataset.hour = h;
        button.style.setProperty('--bar-height', found ? '36px' : '4px');
        button.setAttribute('aria-label', `${h}点，${found ? '有' : '无'}匹配事件`); button.disabled = !found; map.append(button);
      }
      list.append(node('p', 'news-result-caption', '按首次报道小时分段 · 小时内按既有热度排序'), map);
      const caption = node('div', 'hour-map-caption'); caption.append(node('span','','00:00'),node('span','','12:00'),node('span','','23:00')); list.append(caption);
      let hour;
      for (const event of result.events) {
        if (event.hour !== hour) {
          hour = event.hour;
          const heading = node('h3', 'timeline-hour', `${newsDateLabel(n.date)} · ${hour}:00`);
          heading.dataset.hourHeading = hour; list.append(heading);
        }
        const wrapper = node('section', 'news-event'); wrapper.dataset.event = event.id;
        wrapper.append(newsCard(event.representative));
        wrapper.append(node('p', 'event-context', `${event.sourceCount}个来源报道 · 热度${event.score}（示例）`));
        const members = node('details', 'event-members');
        members.open = !!n.q || n.source !== '全部';
        members.append(node('summary', '', `查看${event.members.length}份成员报道`));
        for (const item of event.members) {
          const row = node('div', 'event-member');
          const button = node('button', 'title-button', item.title); button.dataset.detail = item.id;
          row.append(button,node('span','small muted', `${item.source} · ${item.date} ${item.time}`));
          if ((n.q || n.source !== '全部') && event.matching.includes(item.id)) row.append(node('span','member-match','匹配报道'));
          members.append(row);
        }
        wrapper.append(members); list.append(wrapper);
      }
    }
    syncSaved(); ui.layout();
  }
  function setNews(patch, replace = false) {
    state.news = newsModel.normalize({ ...state.news, ...patch });
    renderNews(); setHash(replace);
  }
  const calendar = $('[data-news-date-dialog]');
  let calendarMonth = data.date.slice(0, 7), calendarOpener;
  function renderCalendar() {
    $('[data-calendar-month-label]').textContent = calendarMonth.replace('-', '年')+'月';
    const available = newsModel.dates.filter(d => d.startsWith(calendarMonth));
    const selected = available.includes(state.news.date) ? state.news.date : available[0];
    const grid = $('[data-calendar-grid]'); grid.replaceChildren();
    const [year, month] = calendarMonth.split('-').map(Number);
    const offset = (new Date(Date.UTC(year, month-1, 1)).getUTCDay()+6)%7;
    for (let i = 0; i < offset; i++) grid.append(node('span'));
    const days = new Date(Date.UTC(year, month, 0)).getUTCDate();
    for (let day = 1; day <= days; day++) {
      const date = `${calendarMonth}-${String(day).padStart(2, '0')}`;
      const button = node('button', 'calendar-day', String(day)); button.dataset.newsDate = date;
      button.disabled = newsModel.dateStatus(date) !== 'available';
      button.setAttribute('aria-label', newsDateLabel(date)+(button.disabled ? '，无可用示例存档' : '，有示例存档'));
      button.setAttribute('aria-pressed', String(date === state.news.date));
      if (date === data.date) button.setAttribute('aria-current', 'date');
      button.tabIndex = date === selected ? 0 : -1; grid.append(button);
    }
    $$('[data-calendar-month]').forEach(b => { b.disabled = +b.dataset.calendarMonth < 0 ? calendarMonth <= newsModel.dates[0].slice(0,7) : calendarMonth >= data.date.slice(0,7); });
    $$('[data-archive-day]').forEach(b => { b.disabled = !newsModel.adjacent(state.news.date, +b.dataset.archiveDay); });
  }
  function closeCalendar() { calendar.close(); calendarOpener?.focus(); }
  function chooseDate(date) { setNews({ date }); closeCalendar(); }
  calendar.addEventListener('cancel', event => { event.preventDefault(); closeCalendar(); });
  calendar.addEventListener('keydown', event => {
    if (!event.target.matches('[data-news-date]') || !['ArrowLeft','ArrowRight','ArrowUp','ArrowDown','Home','End'].includes(event.key)) return;
    event.preventDefault();
    const available = $$('[data-news-date]:not(:disabled)',calendar);
    const index = available.indexOf(event.target);
    const step = ['ArrowLeft','ArrowUp'].includes(event.key) ? -1 : 1;
    let next = event.key === 'Home' ? 0 : event.key === 'End' ? available.length-1 : Math.max(0,Math.min(available.length-1,index+step));
    if (['ArrowUp','ArrowDown'].includes(event.key)) {
      const target = new Date(event.target.dataset.newsDate+'T00:00:00Z');
      target.setUTCDate(target.getUTCDate()+step*7);
      const targetDate = target.toISOString().slice(0,10);
      const candidate = step < 0 ? available.filter(b => b.dataset.newsDate <= targetDate).at(-1) : available.find(b => b.dataset.newsDate >= targetDate);
      next = candidate ? available.indexOf(candidate) : index;
    }
    available.forEach(b => { b.tabIndex = -1; }); available[next].tabIndex=0; available[next].focus();
  });
  document.addEventListener('click', event => {
    const button = event.target.closest('button'); if (!button) return;
    if (button.hasAttribute('data-open-news-date')) {
      calendarOpener = button;
      calendarMonth = newsModel.dateStatus(state.news.date) === 'available' ? state.news.date.slice(0,7) : data.date.slice(0,7);
      renderCalendar(); calendar.showModal(); $('[data-news-date][tabindex="0"]')?.focus();
    }
    if (button.hasAttribute('data-close-news-date')) closeCalendar();
    if (button.dataset.newsDate) chooseDate(button.dataset.newsDate);
    if (button.dataset.archiveDay) chooseDate(newsModel.adjacent(state.news.date, +button.dataset.archiveDay));
    if (button.dataset.calendarMonth) {
      const [y,m] = calendarMonth.split('-').map(Number);
      const date = new Date(Date.UTC(y,m-1+Number(button.dataset.calendarMonth),1));
      calendarMonth = date.toISOString().slice(0,7); renderCalendar();
    }
    if (button.hasAttribute('data-news-today')) setNews({date:data.date});
    if (button.hasAttribute('data-news-brief')) setNews({view:'brief'});
    if (button.hasAttribute('data-news-clear-source')) setNews({source:'全部'});
  });
  function applyFilter(kind) {
    if (kind === "look") { renderNews(); return; }
    const panel = $(`[data-panel="${kind}"]`);
    const query = (state.queries[kind] || "").trim().toLocaleLowerCase();
    let count = 0;
    $$("[data-item]", panel).forEach((card) => {
      const item = items.get(card.dataset.item);
      const text = [
        item.title,
        item.reason,
        item.source,
        item.group,
        item.topic,
      ]
        .filter(Boolean)
        .join(" ")
        .toLocaleLowerCase();
      const match = (!query || text.includes(query)) &&
        (state.filters[kind] === '全部' || item.group === state.filters[kind]) &&
        (!state.dog[kind] || item.dog);
      card.hidden = !match;
      if (match) count++;
    });
    $$("[data-group-section]", panel).forEach(
      (group) =>
        (group.hidden = !$$("[data-item]", group).some((card) => !card.hidden)),
    );
    const empty = $(`[data-no-results="${kind}"]`);
    if (empty) empty.hidden = count > 0;
    ui.layout();
  }
  function reset(kind) {
    if (kind === "look") { setNews({topic:"全部",subtopic:"全部",source:"全部",q:"",view:["brief","hot"].includes(state.news.view)?state.news.view:"brief"}); return; }
    state.filters[kind] = "全部";
    state.queries[kind] = "";
    state.dog[kind] = false;
    const input = $(`[data-search="${kind}"]`);
    if (input) input.value = "";
    $$(`[data-filter-scope="${kind}"]`).forEach((b) =>
      b.setAttribute("aria-pressed", String(b.dataset.filter === "全部")),
    );
    const dog = $(`[data-dog="${kind}"]`);
    if (dog) dog.setAttribute("aria-pressed", "false");
    applyFilter(kind);
  }
  function detail(id) {
    const item = items.get(id);
    const original = templates.get(id);
    if (!item || !original) return;
    const fragment = document.createDocumentFragment();
    const title = document.createElement("h2");
    title.id = "detail-title";
    title.textContent = item.title;
    const label = document.createElement("p");
    label.className = "sample-note";
    label.textContent = "示例数据 · 用于视觉与交互评审，不是实时推荐。";
    fragment.append(title, label);
    const media = $(".media-wrap", original);
    if (media) {
      const image = media.cloneNode(true);
      $("[data-save]", image)?.remove();
      const open = $(".media-open", image);
      open.removeAttribute("data-detail");
      open.setAttribute("data-zoom", "true");
      open.setAttribute("aria-label", "放大样例图片");
      fragment.append(image);
    }
    const p = document.createElement("p");
    p.textContent = item.reason;
    fragment.append(p);
    if (item.kind === "look") {
      const context = document.createElement("p");
      context.className = "small muted";
      context.textContent = `${item.topic || "资讯"} · ${item.date} ${item.time || "仅日期"}`;
      fragment.append(context);
    }
    if (item.kind === "play") {
      const p = document.createElement("p");
      p.className = "small muted";
      p.textContent =
        item.image_label +
        "。原图出处见下方链接；样例不提供真实活动的时间、地址或预约信息。";
      fragment.append(p);
    }
    if (item.price) {
      const price = $(".price", original).cloneNode(true);
      fragment.append(price);
      const hint = document.createElement("p");
      hint.className = "small muted";
      hint.textContent =
        "虚构价格格式示例。此物件无品牌、不可购买，不对应真实官方定价。正式卡片仅在金额、地区、SKU 与官方依据核实后显示。";
      fragment.append(hint);
    }
    if (item.status) {
      const p = document.createElement("p");
      p.className = "status-label";
      p.textContent = item.status;
      fragment.append(p);
    }
    const actions = document.createElement("div");
    actions.className = "dialog-actions";
    actions.append(
      $(".source-link", original).cloneNode(true),
      $("[data-save]", original).cloneNode(true),
    );
    fragment.append(actions);
    ui.openDialog(fragment);
    syncSaved();
  }
  document.addEventListener("click", (event) => {
    const button = event.target.closest("button,a");
    if (!button) return;
    if (button.dataset.control)
      control(button.dataset.control, button.dataset.value);
    if (button.hasAttribute("data-news-all-today")) { state.news = newsModel.normalize(); renderNews(); }
    if (button.dataset.page) page(button.dataset.page);
    if (button.dataset.section) {
      event.preventDefault();
      section(button.dataset.section);
    }
    if (button.dataset.mode) mode(button.dataset.mode);
    if (button.dataset.save) toggleSave(button.dataset.save);
    if (button.dataset.savedFilter) {
      state.savedFilter = button.dataset.savedFilter;
      renderSaved();
    }
    if (button.dataset.detail) detail(button.dataset.detail);
    if (button.hasAttribute("data-zoom")) {
      const expanded = button.getAttribute("aria-expanded") === "true";
      button.setAttribute("aria-expanded", String(!expanded));
      button.classList.toggle("is-zoomed", !expanded);
    }
    if (button.dataset.filterScope) {
      const kind = button.dataset.filterScope;
      if (kind === "gallery")
        button
          .closest(".filter-row")
          .querySelectorAll("button")
          .forEach((b) => b.setAttribute("aria-pressed", String(b === button)));
      else if (kind === "look") { setNews({topic:button.dataset.filter,subtopic:"全部"}); }
      else {
        state.filters[kind] = button.dataset.filter;
        $$(`[data-filter-scope="${kind}"]`).forEach((b) =>
          b.setAttribute("aria-pressed", String(b === button)),
        );
        applyFilter(kind);
        $(".app-scroll").scrollTop = 0;
      }
    }
    if (button.dataset.dog) {
      const k = button.dataset.dog;
      state.dog[k] = !state.dog[k];
      button.setAttribute("aria-pressed", String(state.dog[k]));
      applyFilter(k);
    }
    if (button.dataset.reset) reset(button.dataset.reset);
    if (button.dataset.clearSearch) {
      const k = button.dataset.clearSearch;
      const input = $(`[data-search="${k}"]`);
      input.value = "";
      input.dispatchEvent(new Event("input", { bubbles: true }));
      input.focus();
    }
    if (button.hasAttribute("data-open-search")) {
      if (!["look", "play", "buy"].includes(state.page)) page("look");
      $(`[data-search="${state.page}"]`).focus();
    }
    if (button.dataset.hour) {
      const header = $(`[data-hour-heading="${button.dataset.hour}"]`);
      if (header && !header.hidden)
        header.scrollIntoView({
          behavior: ui.reduced() ? "instant" : "smooth",
          block: "start",
        });
      else ui.toast("这个小时没有示例热点");
    }
    if (button.hasAttribute("data-token-toggle")) {
      const editor = $(".token-editor");
      editor.hidden = !editor.hidden;
      button.setAttribute("aria-expanded", String(!editor.hidden));
    }
    if (button.hasAttribute("data-token-reset")) {
      overrides[currentTheme()] = {};
      write("tokens", overrides);
      applyTokens();
      ui.toast("当前主题已恢复默认 token");
    }
    if (button.hasAttribute("data-token-export")) {
      const declarations = tokenNames
        .map(
          (n) =>
            `  ${n}: ${getComputedStyle(root).getPropertyValue(n).trim()};`,
        )
        .join("\n");
      const blob = new Blob(
        [`:root[data-theme="${currentTheme()}"] {\n${declarations}\n}\n`],
        { type: "text/css" },
      );
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `shiguang-${currentTheme()}-tokens.css`;
      link.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
      ui.toast("已导出当前主题的审阅 token");
    }
    if (button.hasAttribute("data-reset-demo")) {
      state.saved = {};
      persistSaved();
      ui.toast("示例收藏已重置");
    }
  });
  document.addEventListener("input", (event) => {
    const input = event.target;
    if (input.dataset.search) {
      const k = input.dataset.search;
      if (k === "gallery")
        $("[data-gallery-feedback]").textContent = input.value
          ? `正在查找：${input.value}`
          : "输入后显示反馈，不影响 Screens。";
      else if (k === "look") setNews({q:input.value}, true);
      else {
        state.queries[k] = input.value;
        applyFilter(k);
      }
    }
    if (input.dataset.token) {
      overrides[currentTheme()][input.dataset.token] =
        input.value + (input.dataset.unit || "");
      write("tokens", overrides);
      applyTokens();
    }
  });
  $('[data-source]').addEventListener('change', event => setNews({source:event.target.value}));
  $('[data-subtopic]').addEventListener('change', event => setNews({subtopic:event.target.value}));
  function route() {
    const [s, p] = (location.hash.slice(1) || 'screens/today').split('/');
    if (s === 'screens' && p === 'look') state.news = newsModel.normalize(new URLSearchParams(location.search));
    section(s, false);
    if (s === 'screens') page(p || 'today', false);
    renderNews(); updateFocusLink();
  }
  addEventListener('hashchange', route);
  addEventListener('popstate', route);
  route();
  for (const k of ['play', 'buy']) applyFilter(k);
  root.dataset.ready = 'true';
})();
