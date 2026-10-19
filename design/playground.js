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
  const names = { look: "好看", play: "好玩", buy: "好买" };
  const templates = new Map();
  for (const [id, item] of items) {
    const panel = $(`[data-panel="${item.kind}"]`);
    const card = $(`[data-item="${id}"]`, panel);
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
    mode: "brief",
    saved: validSaved,
    savedFilter: "全部",
    filters: { look: "全部", play: "全部", buy: "全部" },
    queries: { look: "", play: "", buy: "" },
    dog: { play: false, buy: false },
    source: "全部",
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
  function setHash() {
    const hash =
      state.section === "screens"
        ? `#screens/${state.page}`
        : `#${state.section}`;
    history.replaceState(null, "", hash);
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
    $("[data-focus-link]").href = `?focus=1#screens/${key}`;
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
  function mode(key) {
    state.mode = key;
    $$("[data-mode]").forEach((button) => {
      button.setAttribute("aria-selected", String(button.dataset.mode === key));
      button.tabIndex = button.dataset.mode === key ? 0 : -1;
    });
    $$("[data-look-view]").forEach(
      (view) => (view.hidden = view.dataset.lookView !== key),
    );
    applyFilter("look");
  }
  const foldOpen = new WeakMap();
  function applyFilter(kind) {
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
      const match =
        (!query || text.includes(query)) &&
        (state.filters[kind] === "全部" ||
          (kind === "look" ? item.topic : item.group) ===
            state.filters[kind]) &&
        (!state.dog[kind] || item.dog) &&
        (kind !== "look" ||
          state.source === "全部" ||
          item.source === state.source);
      card.hidden = !match;
      if (
        match &&
        (kind !== "look" ||
          card.closest("[data-look-view]")?.dataset.lookView === state.mode)
      )
        count++;
    });
    $$("[data-group-section]", panel).forEach(
      (group) =>
        (group.hidden = !$$("[data-item]", group).some((card) => !card.hidden)),
    );
    $$(".source-fold", panel).forEach((fold) => {
      const forced = !!query || state.source !== "全部";
      fold.hidden = !$$("[data-item]", fold).some((card) => !card.hidden);
      if (forced) {
        if (!foldOpen.has(fold)) foldOpen.set(fold, fold.open);
        fold.open = true;
      } else if (foldOpen.has(fold)) {
        fold.open = foldOpen.get(fold);
        foldOpen.delete(fold);
      }
      $("summary", fold).hidden = state.source !== "全部";
    });
    const empty = $(`[data-no-results="${kind}"]`);
    if (empty)
      empty.hidden = count > 0 || (kind === "look" && state.mode === "columns");
    $$("[data-hour-heading]", panel).forEach((header) => {
      let next = header.nextElementSibling;
      let visible = false;
      while (next && !next.matches("[data-hour-heading]")) {
        if (next.matches("[data-item]") && !next.hidden) visible = true;
        next = next.nextElementSibling;
      }
      header.hidden = !visible;
    });
    ui.layout();
  }
  function reset(kind) {
    state.filters[kind] = "全部";
    state.queries[kind] = "";
    if (kind === "look") {
      state.source = "全部";
      $("[data-source]").value = "全部";
    } else state.dog[kind] = false;
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
  $("[data-source]").addEventListener("change", (event) => {
    state.source = event.target.value;
    applyFilter("look");
  });
  function route() {
    const [s, p] = (location.hash.slice(1) || "screens/today").split("/");
    section(s, false);
    if (s === "screens") page(p || "today", false);
  }
  addEventListener("hashchange", route);
  syncSaved();
  route();
  for (const k of ["look", "play", "buy"]) applyFilter(k);
  root.dataset.ready = "true";
})();
