// Small DOM and formatting helpers shared by every view.

export function h(tag, attrs = {}, ...children) {
  const el = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs)) {
    if (value == null || value === false) continue;
    if (key === "class") el.className = value;
    else if (key === "style") el.style.cssText = value;
    else if (key.startsWith("on")) el.addEventListener(key.slice(2), value);
    else if (key === "html") el.innerHTML = value;
    else el.setAttribute(key, value === true ? "" : value);
  }
  for (const child of children.flat()) {
    if (child == null || child === false) continue;
    el.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return el;
}

export function icon(name) {
  // Absolute URL: a url() inside a custom property resolves against the
  // stylesheet that uses it (css/), not the page.
  const src = new URL(`assets/icons/${name}.svg`, document.baseURI).href;
  return h("span", { class: "icon", "aria-hidden": "true" },
    h("i", { style: `--src: url("${src}")` }));
}

/** The Videl logo mark. Set --p (0..1) on it to show progress. */
export function mark(extraClass = "") {
  const el = document.getElementById("mark-tpl").content.firstElementChild.cloneNode(true);
  if (extraClass) el.classList.add(...extraClass.split(" "));
  return el;
}

export const reducedMotion = () => window.matchMedia("(prefers-reduced-motion: reduce)").matches;

export function announce(text) {
  const live = document.getElementById("live");
  live.textContent = "";
  requestAnimationFrame(() => { live.textContent = text; });
}

export function fmtBytes(n) {
  if (n < 1024) return `${n} B`;
  const units = ["KB", "MB", "GB"];
  let i = -1;
  do { n /= 1024; i++; } while (n >= 1024 && i < units.length - 1);
  return `${n.toFixed(n >= 100 ? 0 : 1)} ${units[i]}`;
}

export function fmtTime(seconds) {
  if (!Number.isFinite(seconds)) return "0:00";
  const s = Math.max(0, seconds);
  const m = Math.floor(s / 60);
  const rest = s - m * 60;
  const hrs = Math.floor(m / 60);
  const mm = hrs ? String(m % 60).padStart(2, "0") : String(m);
  const ss = rest.toFixed(1).padStart(4, "0");
  return hrs ? `${hrs}:${mm}:${ss}` : `${mm}:${ss}`;
}

export function baseName(name) {
  const dot = name.lastIndexOf(".");
  return dot > 0 ? name.slice(0, dot) : name;
}

export function ext(name) {
  const dot = name.lastIndexOf(".");
  return dot > 0 ? name.slice(dot + 1).toLowerCase() : "";
}

export function saveBlob(blob, name) {
  const url = URL.createObjectURL(blob);
  const a = h("a", { href: url, download: name });
  document.body.append(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 60_000);
}

/** A drop area plus hidden file input. onFiles receives an array of File. */
export function dropArea({ accept, multiple, title, note, onFiles, className = "drop" }) {
  const input = h("input", { type: "file", accept, multiple, hidden: true });
  input.addEventListener("change", () => {
    if (input.files.length) onFiles([...input.files]);
    input.value = "";
  });
  const area = h("div", { class: className },
    title && h("strong", {}, title),
    note && h("span", {}, note),
    h("button", { class: "btn btn-sm", type: "button", onclick: () => input.click() },
      multiple ? "Choose files" : "Choose a file"),
    input);
  bindDrop(area, onFiles);
  return area;
}

export function bindDrop(el, onFiles) {
  let depth = 0;
  el.addEventListener("dragenter", (e) => { e.preventDefault(); depth++; el.classList.add("is-over"); });
  el.addEventListener("dragover", (e) => { e.preventDefault(); });
  el.addEventListener("dragleave", () => { if (--depth <= 0) { depth = 0; el.classList.remove("is-over"); } });
  el.addEventListener("drop", (e) => {
    e.preventDefault();
    depth = 0;
    el.classList.remove("is-over");
    const files = [...(e.dataTransfer?.files || [])];
    if (files.length) onFiles(files);
  });
}

/** Accept-attribute matcher, e.g. "video/*,.mkv". */
export function accepts(accept, file) {
  return accept.split(",").map((s) => s.trim()).some((rule) => {
    if (!rule) return false;
    if (rule.startsWith(".")) return file.name.toLowerCase().endsWith(rule);
    if (rule.endsWith("/*")) return file.type.startsWith(rule.slice(0, -1));
    return file.type === rule;
  });
}
