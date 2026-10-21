/* Shared, framework-free UI primitives. No application or production storage. */
(() => {
  const reduced = () => matchMedia("(prefers-reduced-motion: reduce)").matches;
  let toastTimer;
  let toastFrame;
  function positionToast() {
    const el = document.querySelector(".toast");
    if (!el || el.hidden) return;
    const device = [...document.querySelectorAll(".device")].find(
      (node) => node.getClientRects().length,
    );
    const bounds = device?.getBoundingClientRect();
    const left = Math.max(16, bounds?.left + 16 || 16);
    const right = Math.min(innerWidth - 16, bounds?.right - 16 || innerWidth - 16);
    el.style.left = `${(left + right) / 2}px`;
    el.style.maxWidth = `${Math.min(420, Math.max(0, right - left))}px`;
    const viewport = window.visualViewport;
    const top = viewport?.offsetTop || 0;
    const bottom = viewport ? Math.min(innerHeight, top + viewport.height) : innerHeight;
    const nav = device?.querySelector(".bottom-nav")?.getBoundingClientRect();
    // Use the actual bar height, including safe-area/font changes, in both
    // the embedded device and full-screen preview. Never cover its buttons.
    const aboveNav = nav && nav.top < bottom && nav.top >= top + el.offsetHeight + 12;
    el.style.bottom = `${Math.max(24, innerHeight - bottom + 12, aboveNav ? innerHeight - nav.top + 12 : 0)}px`;
  }
  function scheduleToastPosition() {
    cancelAnimationFrame(toastFrame);
    toastFrame = requestAnimationFrame(positionToast);
  }
  const toastResize = new ResizeObserver(scheduleToastPosition);
  document.querySelectorAll(".device, .device .bottom-nav").forEach(
    (node) => toastResize.observe(node),
  );
  window.addEventListener("resize", scheduleToastPosition);
  window.visualViewport?.addEventListener("resize", scheduleToastPosition);
  window.visualViewport?.addEventListener("scroll", scheduleToastPosition);
  document.addEventListener("scroll", scheduleToastPosition, true);
  function toast(message, undo) {
    const el = document.querySelector(".toast");
    if (!el) return;
    clearTimeout(toastTimer);
    el.querySelector("span").textContent = message;
    const button = el.querySelector("button");
    button.hidden = !undo;
    button.onclick = () => {
      undo?.();
      el.hidden = true;
    };
    el.hidden = false;
    positionToast();
    toastTimer = setTimeout(
      () => {
        el.hidden = true;
      },
      undo ? 9000 : 3500,
    );
  }
  const heights = new WeakMap();
  function layoutGrid(grid) {
    if (!grid.getClientRects().length) return;
    grid.classList.add("is-measured");
    const gap =
      parseFloat(getComputedStyle(grid).getPropertyValue("--grid-gap")) || 12;
    for (const card of grid.children) {
      if (card.hidden) continue;
      const height = card.getBoundingClientRect().height;
      const span = Math.ceil(height + gap);
      if (heights.get(card) !== span) {
        heights.set(card, span);
        card.style.gridRowEnd = `span ${span}`;
      }
    }
  }
  let frame;
  function layout() {
    cancelAnimationFrame(frame);
    frame = requestAnimationFrame(() =>
      document.querySelectorAll(".masonry").forEach(layoutGrid),
    );
  }
  const resize = new ResizeObserver(layout);
  document
    .querySelectorAll(".masonry, .media-card")
    .forEach((el) => resize.observe(el));
  document.addEventListener("load", layout, true);
  document.addEventListener(
    "error",
    (event) => {
      if (
        !(event.target instanceof HTMLImageElement) ||
        !event.target.closest(".media-wrap")
      )
        return;
      const img = event.target;
      const placeholder = document.createElement("span");
      placeholder.className = "placeholder";
      placeholder.textContent = "图片暂时打不开 · 点开查看出处";
      img.hidden = true;
      img.after(placeholder);
      layout();
    },
    true,
  );
  document.fonts.ready.then(layout);
  document.addEventListener("keydown", (event) => {
    const tab = event.target.closest("[role=tab]");
    if (!tab || !["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key))
      return;
    const tabs = [
      ...tab
        .closest("[role=tablist]")
        .querySelectorAll("[role=tab]:not(:disabled)"),
    ];
    let index = tabs.indexOf(tab);
    index =
      event.key === "Home"
        ? 0
        : event.key === "End"
          ? tabs.length - 1
          : (index + (event.key === "ArrowRight" ? 1 : -1) + tabs.length) %
            tabs.length;
    event.preventDefault();
    tabs[index].focus();
    tabs[index].click();
  });
  let restoreFocus;
  const dialog = document.querySelector("[data-detail-dialog]");
  function openDialog(content) {
    if (!dialog) return;
    restoreFocus = document.activeElement;
    dialog.querySelector(".dialog-body").replaceChildren(content);
    dialog.showModal();
    dialog.scrollTop = 0;
    dialog.querySelector("[data-dialog-close]").focus();
  }
  function closeDialog() {
    dialog?.close();
  }
  dialog?.addEventListener("close", () => {
    restoreFocus?.isConnected && restoreFocus.focus({ preventScroll: true });
  });
  dialog?.addEventListener("click", (event) => {
    if (
      event.target === dialog &&
      (event.offsetX < 0 ||
        event.offsetX > dialog.clientWidth ||
        event.offsetY < 0 ||
        event.offsetY > dialog.clientHeight)
    )
      closeDialog();
  });
  document.addEventListener("click", (event) => {
    if (event.target.closest("[data-dialog-close]")) closeDialog();
    if (event.target.closest("[data-demo-toast]")) toast("示例操作已完成");
    if (event.target.closest("[data-demo-error]"))
      toast("示例：暂时无法完成，请重试", () => toast("重试示例已完成"));
    if (event.target.closest("[data-motion]"))
      document.querySelector("[data-motion-box]")?.classList.toggle("moved");
    const retry = event.target.closest("[data-retry-image]");
    if (retry) {
      retry
        .closest("[data-placeholder]")
        .replaceChildren(
          Object.assign(document.createElement("span"), {
            textContent: "图片占位示例 · 重试完成",
          }),
        );
    }
    const tab = event.target.closest("[data-demo-tab]");
    if (tab)
      tab.parentElement
        .querySelectorAll("[data-demo-tab]")
        .forEach((t) => t.setAttribute("aria-selected", String(t === tab)));
  });
  window.ShiguangUI = { toast, layout, openDialog, closeDialog, reduced };
  layout();
})();
