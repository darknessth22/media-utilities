import { h, icon, mark as logoMark, bindDrop, accepts, reducedMotion } from "./ui.js";
import { GROUPS, TOOLS, toolById } from "./tools/index.js";
import { renderWorkspace } from "./workspace.js";
import { renderReport } from "./report.js";

const main = document.getElementById("main");
let cleanup = null;
let pendingFiles = [];
let firstPaint = true;

const DESKTOP_URL = "https://videl.app/";
const LIVE_TOOLS = TOOLS.filter((t) => !t.soon);

// Desktop-only features, with the desktop app's own icons and colours.
const DESKTOP_FEATURES = [
  { icon: "download", color: "#3B82F6", name: "Downloader", note: "YouTube, Instagram, TikTok, Spotify and more" },
  { icon: "upscaler", color: "#0EA5E9", name: "AI image upscaler", note: "Enlarge photos 2x or 4x with Real-ESRGAN" },
  { icon: "video_upscaler", color: "#6366F1", name: "AI video upscaler", note: "Upscale whole videos on your graphics card" },
  { icon: "vocal_isolator", color: "#A855F7", name: "Vocal isolator", note: "Split vocals from the music" },
  { icon: "transcript", color: "#0891B2", name: "Transcripts", note: "Speech to subtitles, fully offline" },
  { icon: "photo_restore", color: "#FB7185", name: "Photo restore", note: "Heal scratches, colourise, fix faces" },
  { icon: "bg_eraser", color: "#10B981", name: "Object removal", note: "Erase objects, not just backgrounds" },
  { icon: "subtitles", color: "#14B8A6", name: "Burn-in subtitles", note: "Put captions into the video" },
  { icon: "jumpcut", color: "#F59E0B", name: "Jump cutter", note: "Cut the silences out automatically" },
  { icon: "image_editor", color: "#D946EF", name: "Image editor", note: "Colour grading, masks, multi-monitor wallpapers" },
];

/** "More in the desktop app": shown on Home and Tools. */
function desktopPromo() {
  return h("section", { class: "promo", "aria-labelledby": "promo-h" },
    h("div", { class: "promo-text" },
      h("h2", { id: "promo-h" }, "Need the AI tools? Get Videl for desktop"),
      h("p", {}, "The desktop app runs heavier AI on your own graphics card, adds the downloader, and has more than 25 tools plus screen tools like text extraction and a colour picker. It's free for Windows and Linux."),
      h("div", { class: "promo-actions" },
        h("a", { class: "btn btn-primary btn-lg", href: DESKTOP_URL, rel: "noopener" }, "Get the desktop app"))),
    h("ul", { class: "promo-list", "aria-label": "Only in the desktop app" },
      DESKTOP_FEATURES.map((f) => h("li", { class: "promo-item", style: `--tool:${f.color}` },
        icon(f.icon),
        h("div", {}, h("strong", {}, f.name), h("span", {}, f.note))))));
}

// Most used tools: counted on this device only. Defaults until there is history.
const DEFAULT_FAVOURITES = ["convert", "bg-eraser", "compress", "trim", "pdf-merge", "image-convert"];
const USAGE_KEY = "videl.usage";

function readUsage() {
  try { return JSON.parse(localStorage.getItem(USAGE_KEY)) || {}; } catch { return {}; }
}
function countUse(id) {
  try {
    const usage = readUsage();
    usage[id] = (usage[id] || 0) + 1;
    localStorage.setItem(USAGE_KEY, JSON.stringify(usage));
  } catch { /* private mode or storage blocked: favourites fall back to defaults */ }
}
function mostUsed(n = 6) {
  const usage = readUsage();
  const ranked = Object.entries(usage).sort((a, b) => b[1] - a[1]).map(([id]) => id);
  const ids = [...new Set([...ranked, ...DEFAULT_FAVOURITES])];
  return { tools: ids.map(toolById).filter((t) => t && !t.soon).slice(0, n), personal: ranked.length > 0 };
}

// Routing ------------------------------------------------------------------------------
function route() {
  const [, kind, id] = location.hash.replace(/^#/, "").split("/");
  cleanup?.();
  cleanup = null;
  const tool = kind === "tool" ? toolById(id) : null;
  let page = "home";
  if (tool?.soon) { renderSoon(tool); page = tool.id; }
  else if (tool) { countUse(tool.id); cleanup = renderWorkspace(main, tool, pendingFiles.splice(0)); page = "tools"; }
  else if (kind === "tools") { renderTools(); page = "tools"; }
  else if (kind === "report") { renderReport(main); page = "report"; }
  else renderHome();
  for (const a of document.querySelectorAll("[data-nav]")) {
    if (a.dataset.nav === page) a.setAttribute("aria-current", "page"); else a.removeAttribute("aria-current");
  }
  document.title = tool ? `${tool.name} — Videl` : page === "tools" ? "All tools — Videl"
    : page === "report" ? "Report a bug — Videl" : "Videl — media tools in your browser";
  if (!firstPaint) { window.scrollTo(0, 0); main.focus({ preventScroll: true }); }
  firstPaint = false;
}

function navigate() {
  if (document.startViewTransition && !reducedMotion()) document.startViewTransition(route);
  else route();
}

// Home -----------------------------------------------------------------------------------
function renderHome() {
  // The reveal plays every time Home is shown, not only on a full reload.
  const mark = logoMark(reducedMotion() ? "" : "draw-in");
  const input = h("input", { type: "file", multiple: true, hidden: true,
    onchange: () => { if (input.files.length) suggest([...input.files]); input.value = ""; } });
  const suggestBox = h("div", { class: "home-suggest", "aria-live": "polite" });

  function suggest(files) {
    const first = files[0];
    const fits = LIVE_TOOLS.filter((t) => accepts(t.accept, first) && (files.length === 1 || t.multiple));
    const name = files.length > 1 ? `${files.length} files` : first.name;
    suggestBox.replaceChildren(h("div", { class: "suggest-card" },
      h("p", { class: "suggest-file" }, name),
      h("p", { class: "suggest-q" }, fits.length
        ? "What would you like to do with it?"
        : "None of the browser tools take this file type yet. Try a video, audio file, PDF or image."),
      h("div", { class: "suggest" },
        fits.map((t) => h("button", { class: "btn", type: "button", style: `--tool:${t.color}`,
          onclick: () => { pendingFiles = files; location.hash = `#/tool/${t.id}`; } }, icon(t.icon), t.name)),
        h("button", { class: "btn btn-quiet", type: "button", onclick: () => suggestBox.replaceChildren() }, "Clear"))));
    suggestBox.querySelector(".suggest .btn")?.focus();
  }

  const { tools: favourites, personal } = mostUsed();
  const page = h("div", { class: "wrap home" },
    h("section", { class: "home-hero" },
      h("div", { class: "home-mark" }, mark),
      h("h1", {}, "Media tools that never leave your browser"),
      h("p", { class: "home-lede" }, "Convert, trim and compress video, combine PDFs, rework images and remove backgrounds. Everything runs on your device, so your files stay private."),
      h("div", { class: "home-actions" },
        h("button", { class: "btn btn-primary btn-lg", type: "button", onclick: () => input.click() }, "Choose a file"),
        h("a", { class: "btn btn-lg", href: "#/tools" }, `Browse all ${LIVE_TOOLS.length} tools`)),
      h("p", { class: "home-drop-hint" }, "Or drop a file anywhere on this page."),
      suggestBox, input),
    h("section", { class: "home-fav", "aria-labelledby": "fav-h" },
      h("div", { class: "fav-head" },
        h("h2", { id: "fav-h" }, personal ? "Your most used" : "Most used"),
        h("a", { class: "btn btn-sm btn-quiet", href: "#/tools" }, "See all tools")),
      h("ul", { class: "cat-grid is-entering" }, favourites.map(tile))),
    desktopPromo());

  bindDrop(page, suggest);
  main.replaceChildren(page);
}

// Tools page ---------------------------------------------------------------------------
function renderTools() {
  main.replaceChildren(h("div", { class: "wrap tools-page" }, catalog(), desktopPromo()));
}

let activeTab = "all";

function catalog() {
  const tabs = [{ id: "all", name: "All tools" }, ...GROUPS];
  const count = (id) => TOOLS.filter((t) => id === "all" || t.group === id).length;
  const search = h("input", {
    type: "search", class: "cat-search-input", placeholder: "Find a tool, or a format like MP4", "aria-label": "Find a tool",
    autocomplete: "off", oninput: () => paint(true),
  });
  const indicator = h("span", { class: "cat-indicator", "aria-hidden": "true" });
  const tablist = h("div", { class: "cat-tabs", role: "tablist", "aria-label": "Tool categories" },
    tabs.map((t) => h("button", {
      class: "cat-tab", role: "tab", type: "button", id: `tab-${t.id}`, "data-tab": t.id,
      "aria-controls": "cat-grid", "aria-selected": String(t.id === activeTab), tabindex: t.id === activeTab ? "0" : "-1",
      onclick: () => select(t.id),
      onkeydown: (e) => {
        const i = tabs.findIndex((x) => x.id === activeTab);
        const next = { ArrowRight: i + 1, ArrowLeft: i - 1, Home: 0, End: tabs.length - 1 }[e.key];
        if (next == null) return;
        e.preventDefault();
        select(tabs[(next + tabs.length) % tabs.length].id, true);
      },
    }, t.name, h("span", { class: "cat-count num" }, count(t.id)))),
    indicator);
  const note = h("p", { class: "cat-note" });
  const grid = h("ul", { class: "cat-grid", id: "cat-grid", role: "tabpanel" });

  function select(id, focus = false) {
    activeTab = id;
    for (const b of tablist.querySelectorAll(".cat-tab")) {
      const on = b.dataset.tab === id;
      b.setAttribute("aria-selected", String(on));
      b.tabIndex = on ? 0 : -1;
      if (on && focus) b.focus();
    }
    paint(true);
  }

  function moveIndicator() {
    const on = tablist.querySelector('[aria-selected="true"]');
    if (!on) return;
    indicator.style.width = `${on.offsetWidth}px`;
    indicator.style.height = `${on.offsetHeight}px`;   // tabs wrap to two rows on phones
    indicator.style.transform = `translate(${on.offsetLeft}px, ${on.offsetTop}px)`;
  }

  function paint(animate) {
    const q = search.value.trim().toLowerCase();
    const group = GROUPS.find((g) => g.id === activeTab);
    // A search always covers every tool, whichever tab is open.
    const list = TOOLS.filter((t) => q
      ? [t.name, t.blurb, t.takes, t.gives].join(" ").toLowerCase().includes(q)
      : activeTab === "all" || t.group === activeTab);
    note.textContent = q
      ? `${list.length} ${list.length === 1 ? "tool matches" : "tools match"} across all categories.`
      : group?.note || "Everything here runs on your device. Pick a tool to start.";
    tablist.classList.toggle("is-searching", !!q);
    grid.setAttribute("aria-labelledby", `tab-${activeTab}`);
    // Restart the entrance animation on every change, including the first paint.
    grid.classList.remove("is-entering");
    if (animate && !reducedMotion()) { void grid.offsetWidth; grid.classList.add("is-entering"); }
    grid.replaceChildren(...(list.length ? list.map(tile) : [h("li", { class: "cat-empty" },
      h("strong", {}, `No tool matches “${search.value.trim()}”.`),
      h("span", {}, "Try a format such as MP4, PDF or PNG, or clear the search."))]));
    requestAnimationFrame(moveIndicator);
  }

  const section = h("section", { class: "catalog", "aria-labelledby": "cat-h" },
    h("div", { class: "cat-head" },
      h("div", {},
        h("h1", { id: "cat-h" }, "All tools"),
        h("p", { class: "cat-lede" }, "Every tool runs on your device. Files are never uploaded.")),
      h("label", { class: "cat-search" },
        h("span", { class: "cat-search-icon", "aria-hidden": "true", html: '<svg width="18" height="18" viewBox="0 0 24 24"><circle cx="11" cy="11" r="7" fill="none" stroke="currentColor" stroke-width="2"/><path d="M20 20l-3.5-3.5" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg>' }),
        search,
        h("kbd", { "aria-hidden": "true" }, "/"))),
    tablist, note, grid);

  window.addEventListener("resize", moveIndicator, { passive: true });
  paint(true);
  return section;
}

function tile(t) {
  return h("li", { class: "cat-item", style: `--tool:${t.color}` },
    h("a", { class: t.soon ? "tile is-soon" : "tile", href: `#/tool/${t.id}` },
      h("div", { class: "tile-top" },
        icon(t.icon),
        t.soon ? h("span", { class: "pill" }, "Coming next") : null),
      h("strong", { class: "tile-name" }, t.name),
      h("span", { class: "tile-blurb" }, t.blurb),
      h("span", { class: "tile-io" },
        h("span", {}, h("em", {}, "Takes "), t.takes),
        h("span", {}, h("em", {}, "Gives "), t.gives))));
}

// Coming next ---------------------------------------------------------------------
function renderSoon(tool) {
  main.replaceChildren(h("div", { class: "wrap" },
    h("section", { class: "soon" },
      h("span", { class: "pill" }, "Coming next"),
      h("h1", {}, tool.name),
      tool.soonText.map((t) => h("p", {}, t)),
      tool.id === "download" && h("div", { class: "fake-url", "aria-hidden": "true" },
        h("input", { type: "text", placeholder: "Paste a link from YouTube, Instagram, TikTok…", disabled: true, tabindex: "-1" }),
        h("button", { class: "btn btn-primary", type: "button", disabled: true, tabindex: "-1" }, "Download")),
      h("a", { class: "btn btn-primary", href: DESKTOP_URL, rel: "noopener" }, "Get the desktop app"),
      " ",
      h("a", { class: "btn btn-quiet", href: "#/tools" }, "Back to the tools"))));
}

// Tool tiles: a soft spotlight follows the pointer (one listener, rAF-throttled).
let spotFrame = 0;
document.addEventListener("pointermove", (e) => {
  const link = e.target.closest?.(".tile");
  if (!link || spotFrame) return;
  spotFrame = requestAnimationFrame(() => {
    spotFrame = 0;
    const r = link.getBoundingClientRect();
    link.style.setProperty("--mx", `${e.clientX - r.left}px`);
    link.style.setProperty("--my", `${e.clientY - r.top}px`);
  });
}, { passive: true });

// "/" jumps to the tool search.
document.addEventListener("keydown", (e) => {
  if (e.key !== "/" || e.target.closest?.("input, textarea, select")) return;
  const input = document.querySelector(".cat-search-input");
  e.preventDefault();
  if (input) input.focus();
  else { location.hash = "#/tools"; setTimeout(() => document.querySelector(".cat-search-input")?.focus(), 350); }
});

window.addEventListener("hashchange", navigate);
route();
