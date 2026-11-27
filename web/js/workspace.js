// The shared tool workspace: files, preview, settings, run, results.
import { h, icon, mark as logoMark, dropArea, bindDrop, accepts, fmtBytes, fmtTime, saveBlob, announce } from "./ui.js";
import { cancelFFmpeg, zipBlobs } from "./engines.js";
import { allowBatch, batchNote } from "./account.js";
import { loadBitmap } from "./tools/image.js";
import { segment } from "./engines.js";
import { noteProblem } from "./report.js";

const isTimed = (f) => f.type.startsWith("video/") || f.type.startsWith("audio/") || /\.(mkv|mov|avi|flv|wmv|m4a|flac|opus)$/i.test(f.name);

/** Read duration and size from a media file using the browser's own decoder. */
function probe(file) {
  return new Promise((resolve) => {
    const el = document.createElement(file.type.startsWith("audio/") ? "audio" : "video");
    const url = URL.createObjectURL(file);
    const done = (info) => { URL.revokeObjectURL(url); resolve(info); };
    el.preload = "metadata";
    el.onloadedmetadata = () => done({ duration: el.duration, width: el.videoWidth || 0, height: el.videoHeight || 0 });
    el.onerror = () => done({ duration: 0, width: 0, height: 0 });
    el.src = url;
  });
}

/** A custom field's typed text as the value the tool uses, or null if it doesn't fit. */
export function customValue(c, text) {
  if (c.ratio) {
    const m = /^\s*(\d+(?:\.\d+)?)\s*[:x/]\s*(\d+(?:\.\d+)?)\s*$/i.exec(text);
    return m && Number(m[1]) > 0 && Number(m[2]) > 0 ? `${Number(m[1])}:${Number(m[2])}` : null;
  }
  const n = Number(text);
  return text.trim() !== "" && n >= c.min && n <= c.max && (!c.whole || Number.isInteger(n)) ? String(n) : null;
}

export function renderWorkspace(main, tool, initialFiles = []) {
  const urls = new Set();
  const objectURL = (blob) => { const u = URL.createObjectURL(blob); urls.add(u); return u; };
  // A search page can preselect settings, e.g. /video-to-mp3 opens Convert set to MP3
  // (<html data-preset>, written by tools/web_tool_pages.py).
  const page = document.documentElement.dataset;
  const preset = page.tool === tool.id && page.preset ? JSON.parse(page.preset) : {};
  const values = { ...Object.fromEntries(tool.fields.map((f) => [f.key, f.value])), ...preset };
  // Choice fields with `custom` also offer "Custom", a typed value (see customBox).
  const customOn = new Set(tool.fields.filter((f) => f.custom && !f.options.some(([v]) => v === values[f.key])).map((f) => f.key));
  const badCustom = new Set();   // keys whose typed value is out of range
  const state = { files: [], probes: [], start: 0, end: 0, busy: false, results: [] };
  // A batch tool runs once per file. More than one file is Videl Pro, or one of
  // the free daily batches with a free account (account.js, allowBatch).
  const many = !!(tool.multiple || tool.batch);
  const batchLine = tool.batch ? h("p", { class: "hint batch-note" }) : null;
  const refreshBatchLine = () => batchLine && batchNote().then((t) => { batchLine.textContent = t; });

  // Layout ------------------------------------------------------------------
  const fileList = h("ul", { class: "files", "aria-label": "Files" });
  const previewBox = h("div");
  const drop = dropArea({
    accept: tool.accept,
    multiple: many,
    title: many ? "Drop files here" : "Drop a file here",
    note: "Stays on this device.",
    onFiles: addFiles,
  });
  const form = h("div", { class: "form" });
  const mark = logoMark();
  const statusTitle = h("strong", {}, "Add a file to start");
  const statusNote = h("span", {}, many ? `You can add several files.` : "");
  const status = h("div", { class: "status", role: "status" }, statusTitle, statusNote);
  const actionBtn = h("button", { class: "btn btn-primary", type: "button", disabled: true, onclick: onAction }, tool.action);
  const results = h("ul", { class: "results", "aria-label": "Results" });

  const steps = h("ol", { class: "steps", "aria-label": "Progress" },
    ["Add files", "Choose settings", "Save the result"].map((label, i) =>
      h("li", { "data-step": i + 1 }, h("span", { class: "step-dot num" }, i + 1), label)));

  main.replaceChildren(h("div", { class: "wrap ws", style: `--tool:${tool.color}` },
    h("div", { class: "ws-head" },
      h("a", { class: "btn btn-icon btn-quiet back", href: "/#/tools", "aria-label": "All tools", html: '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M15 18l-6-6 6-6"/></svg>' }),
      icon(tool.icon),
      h("div", { class: "ws-title" },
        // A tool's search page (/compress-video) gives it a fuller heading, "Compress video".
        h("h1", {}, (document.documentElement.dataset.tool === tool.id && document.documentElement.dataset.h1) || tool.name),
        h("p", {}, tool.blurb),
        h("p", { class: "ws-io" }, h("span", {}, h("em", {}, "Takes "), tool.takes), h("span", {}, h("em", {}, "Gives "), tool.gives))),
      steps),
    h("div", { class: "ws-grid" },
      h("section", { class: "panel", "aria-label": "Files" }, drop, batchLine, fileList, previewBox),
      h("section", { class: "panel", "aria-labelledby": "settings-h" }, h("h2", { id: "settings-h" }, "Settings"), form)),
    h("div", { class: "runbar" }, mark, status, actionBtn),
    results));
  bindDrop(main.querySelector(".ws-grid"), addFiles);

  renderForm();
  refreshBatchLine();
  if (initialFiles.length) addFiles(initialFiles);

  // Files --------------------------------------------------------------------
  async function addFiles(incoming) {
    if (state.busy) return;
    const ok = incoming.filter((f) => accepts(tool.accept, f));
    const rejected = incoming.length - ok.length;
    if (!ok.length) { setStatus("That file type doesn't work here", "Choose a different file.", true); return; }
    const chosen = many ? ok : ok.slice(0, 1);
    const probes = await Promise.all(chosen.map((f) => (isTimed(f) ? probe(f) : null)));
    if (many) { state.files.push(...chosen); state.probes.push(...probes); }
    else { state.files = chosen; state.probes = probes; }
    clearResults();
    renderFiles();
    renderPreview();
    if (rejected) setStatus("Some files were skipped", "Only matching file types were added.");
    else readyStatus();
  }

  function renderFiles() {
    drop.classList.toggle("is-compact", state.files.length > 0);
    drop.querySelector("strong").textContent = state.files.length
      ? (many ? "Drop more files here" : "Drop a different file here")
      : (many ? "Drop files here" : "Drop a file here");
    fileList.replaceChildren(...state.files.map((file, i) => {
      const p = state.probes[i];
      const meta = [fmtBytes(file.size), p?.duration ? fmtTime(p.duration) : null, p?.width ? `${p.width}×${p.height}` : null].filter(Boolean).join(", ");
      const move = (dir) => {
        const j = i + dir;
        [state.files[i], state.files[j]] = [state.files[j], state.files[i]];
        [state.probes[i], state.probes[j]] = [state.probes[j], state.probes[i]];
        renderFiles();
      };
      return h("li", { class: "file" },
        h("div", {}, h("div", { class: "file-name", title: file.name }, file.name), h("div", { class: "file-meta num" }, meta)),
        h("div", { class: "file-actions" },
          tool.reorder && i > 0 && h("button", { class: "btn btn-icon btn-quiet", type: "button", "aria-label": `Move ${file.name} up`, onclick: () => move(-1), html: chevron("M18 15l-6-6-6 6") }),
          tool.reorder && i < state.files.length - 1 && h("button", { class: "btn btn-icon btn-quiet", type: "button", "aria-label": `Move ${file.name} down`, onclick: () => move(1), html: chevron("M6 9l6 6 6-6") }),
          h("button", { class: "btn btn-icon btn-quiet", type: "button", "aria-label": `Remove ${file.name}`, disabled: state.busy,
            onclick: () => { state.files.splice(i, 1); state.probes.splice(i, 1); clearResults(); renderFiles(); renderPreview(); readyStatus(); },
            html: chevron("M6 6l12 12M18 6L6 18") })));
    }));
  }

  // Preview ------------------------------------------------------------------
  let liveBitmap = null;
  let liveMask = null;
  let previewToken = 0;
  state.split = 50;
  const masks = new Map();     // File -> subject mask, so settings changes never re-run the model

  /** Subject mask for a file, computed once. */
  function prepareMask(file, bitmap) {
    if (!masks.has(file)) {
      masks.set(file, segment(bitmap, engineStatus).catch((err) => { masks.delete(file); throw err; }));
    }
    return masks.get(file);
  }
  let liveTimer = 0;
  let liveCanvasBox = null;

  function renderPreview() {
    liveBitmap?.close?.();
    liveBitmap = null;
    previewToken++;               // abandon any detection still running for a removed file
    state.preparing = false;
    const file = state.files[0];
    if (!file || !tool.preview) { previewBox.replaceChildren(); return; }
    if (tool.preview === "video" || tool.preview === "timeline") {
      const media = h(file.type.startsWith("audio/") ? "audio" : "video", { src: objectURL(file), controls: true, preload: "metadata", playsinline: true });
      const box = h("div", { class: "preview" }, media);
      previewBox.replaceChildren(box);
      if (tool.preview === "timeline") previewBox.append(timeline(media, file, state.probes[0]?.duration || 0));
    } else if (tool.preview === "image") {
      previewBox.replaceChildren(h("div", { class: "preview" }, h("img", { src: objectURL(file), alt: `Preview of ${file.name}` })));
    } else if (tool.preview === "live") {
      liveCanvasBox = h("div");
      previewBox.replaceChildren(liveCanvasBox);
      loadBitmap(file).then((bmp) => { liveBitmap = bmp; renderLive(); })
        .catch((err) => setStatus("Couldn't open the image", err.message, true, true));
    } else if (tool.preview === "compare") {
      const token = ++previewToken;
      liveMask = null;
      liveCanvasBox = h("div", { class: "compare-slot" },
        h("div", { class: "preview" }, h("img", { src: objectURL(file), alt: `Preview of ${file.name}` })));
      previewBox.replaceChildren(liveCanvasBox);
      state.preparing = true;
      actionBtn.disabled = true;
      mark.setAttribute("class", "mark is-busy");
      loadBitmap(file)
        .then(async (bmp) => {
          liveBitmap = bmp;
          const mask = await prepareMask(file, bmp);
          if (token !== previewToken) return;
          liveMask = mask;
          state.preparing = false;
          readyStatus();
          renderLive();
        })
        .catch((err) => {
          if (token !== previewToken) return;
          state.preparing = false;
          mark.setAttribute("class", "mark is-error");
          setStatus("Couldn't find the subject", err.message, true, true);
        });
    }
  }

  function renderLive() {
    if (!liveBitmap) return;
    if (tool.preview === "compare") {
      if (!liveMask) return;
      const { canvas } = tool.live(liveBitmap, values, liveMask);
      liveCanvasBox.replaceChildren(compareView(objectURL(state.files[0]), canvas));
      return;
    }
    const out = tool.live(liveBitmap, values);
    const parts = [];
    if (out.canvas) {
      out.canvas.setAttribute("role", "img");
      out.canvas.setAttribute("aria-label", "Pixel art preview");
      parts.push(h("div", { class: "preview is-pixel" }, out.canvas));
    }
    if (out.palette) {
      const small = !!out.canvas;
      parts.push(h("div", { class: small ? "swatches is-small" : "swatches", "aria-label": small ? "Colours used" : "Palette" }, out.palette.map((hex) =>
        h("button", { class: "swatch", type: "button", title: `Copy ${hex}`, "aria-label": `Copy ${hex}`,
          onclick: async () => { await navigator.clipboard?.writeText(hex); announce(`Copied ${hex}`); setStatus(`Copied ${hex}`, "Paste it anywhere."); } },
          h("i", { style: `background:${hex}` }), small ? null : hex))));
    }
    liveCanvasBox.replaceChildren(...parts);
  }

  /** Original on the left, result on the right, split by a draggable (and keyboard) slider. */
  function compareView(beforeSrc, afterCanvas) {
    afterCanvas.setAttribute("role", "img");
    afterCanvas.setAttribute("aria-label", "Result with the background removed");
    const view = h("div", { class: "compare", style: `--split:${state.split}%` },
      h("img", { class: "compare-before", src: beforeSrc, alt: "Original photo" }),
      h("div", { class: "compare-after" }, afterCanvas),
      h("span", { class: "compare-line", "aria-hidden": "true" }),
      h("span", { class: "compare-tag tag-before", "aria-hidden": "true" }, "Original"),
      h("span", { class: "compare-tag tag-after", "aria-hidden": "true" }, "Result"));
    const range = h("input", {
      class: "compare-range", type: "range", min: 0, max: 100, value: state.split, "aria-label": "Compare original and result",
      oninput: (e) => { state.split = Number(e.target.value); view.style.setProperty("--split", `${state.split}%`); },
    });
    view.append(range);
    return view;
  }

  function scheduleLive() {
    if (tool.preview !== "live" && tool.preview !== "compare") return;
    clearTimeout(liveTimer);
    liveTimer = setTimeout(renderLive, 120);
  }

  // Trim / GIF timeline -----------------------------------------------------------
  function timeline(media, file, duration) {
    const max = tool.maxClip || Infinity;
    state.start = 0;
    state.end = Math.min(duration, max);
    const strip = h("div", { class: "strip" });
    const sel = h("div", { class: "sel" });
    const playhead = h("div", { class: "playhead" });
    const startH = h("button", { class: "handle handle-start", type: "button", role: "slider", "aria-label": "Clip start" });
    const endH = h("button", { class: "handle handle-end", type: "button", role: "slider", "aria-label": "Clip end" });
    sel.append(startH, endH);
    strip.append(sel, playhead);
    const startOut = h("b", { class: "num" }), lenOut = h("b", { class: "num" }), endOut = h("b", { class: "num" });
    const row = h("div", { class: "time-row" },
      h("span", {}, "Start ", startOut), h("span", {}, "Length ", lenOut), h("span", {}, "End ", endOut));

    const pct = (t) => (duration ? (t / duration) * 100 : 0);
    function paint() {
      sel.style.left = `${pct(state.start)}%`;
      sel.style.width = `${pct(state.end - state.start)}%`;
      startOut.textContent = fmtTime(state.start);
      endOut.textContent = fmtTime(state.end);
      lenOut.textContent = fmtTime(state.end - state.start);
      for (const [el, v] of [[startH, state.start], [endH, state.end]]) {
        el.setAttribute("aria-valuemin", "0");
        el.setAttribute("aria-valuemax", String(Math.round(duration)));
        el.setAttribute("aria-valuenow", v.toFixed(1));
        el.setAttribute("aria-valuetext", fmtTime(v));
      }
    }
    function set(which, t) {
      t = Math.max(0, Math.min(duration, t));
      if (which === "start") {
        state.start = Math.min(t, state.end - 0.1);
        if (state.end - state.start > max) state.end = state.start + max;
        media.currentTime = state.start;
      } else {
        state.end = Math.max(t, state.start + 0.1);
        if (state.end - state.start > max) state.start = state.end - max;
        media.currentTime = Math.max(state.start, state.end - 1);
      }
      paint();
    }
    const timeAt = (clientX) => {
      const r = strip.getBoundingClientRect();
      return ((clientX - r.left) / r.width) * duration;
    };
    for (const [el, which] of [[startH, "start"], [endH, "end"]]) {
      el.addEventListener("pointerdown", (e) => {
        e.preventDefault();
        el.setPointerCapture(e.pointerId);
        const move = (ev) => set(which, timeAt(ev.clientX));
        el.addEventListener("pointermove", move);
        el.addEventListener("pointerup", () => el.removeEventListener("pointermove", move), { once: true });
      });
      el.addEventListener("keydown", (e) => {
        const step = e.shiftKey ? 1 : 0.1;
        const cur = which === "start" ? state.start : state.end;
        if (e.key === "ArrowLeft" || e.key === "ArrowDown") { e.preventDefault(); set(which, cur - step); }
        if (e.key === "ArrowRight" || e.key === "ArrowUp") { e.preventDefault(); set(which, cur + step); }
      });
    }
    strip.addEventListener("pointerdown", (e) => {
      if (e.target.closest(".handle")) return;
      media.currentTime = Math.max(0, Math.min(duration, timeAt(e.clientX)));
    });
    media.addEventListener("timeupdate", () => { playhead.style.left = `${pct(media.currentTime)}%`; });
    paint();
    filmstrip(file, duration, strip);
    const note = h("p", { class: "preview-note" },
      tool.maxClip ? `Drag the handles to pick up to ${tool.maxClip} seconds.` : "Drag the handles, or select one and use the arrow keys. Hold Shift for 1-second steps.");
    return h("div", { class: "timeline" }, strip, row, note);
  }

  /** Eight thumbnails along the clip, drawn from a hidden video element. */
  async function filmstrip(file, duration, strip) {
    if (!file.type.startsWith("video/") || !duration) return;
    const v = document.createElement("video");
    v.muted = true;
    v.preload = "auto";
    v.src = objectURL(file);
    await new Promise((r) => { v.onloadeddata = r; v.onerror = r; });
    const frames = [];
    for (let i = 0; i < 8; i++) {
      const c = h("canvas", { width: 160, height: 90 });
      frames.push(c);
    }
    strip.prepend(...frames);
    for (const [i, c] of frames.entries()) {
      v.currentTime = Math.min(duration - 0.05, (duration / 8) * (i + 0.5));
      await new Promise((r) => { v.onseeked = r; setTimeout(r, 1500); });
      if (!strip.isConnected) return;
      c.getContext("2d").drawImage(v, 0, 0, c.width, c.height);
    }
    v.removeAttribute("src");
    v.load();
  }

  // Settings form -------------------------------------------------------------------
  function renderForm() {
    if (!tool.fields.length) {
      form.replaceChildren(h("p", { class: "hint" }, "No settings needed. Add the files in the order you want them, then run it."));
      return;
    }
    form.replaceChildren(...tool.fields.filter((f) => !f.when || f.when(values)).map(field));
  }

  function field(f) {
    const id = `f-${f.key}`;
    const hint = f.hint && h("p", { class: "hint", id: `${id}-hint` }, f.hint);
    const describedBy = f.hint ? `${id}-hint` : null;
    const visible = () => tool.fields.filter((x) => !x.when || x.when(values)).map((x) => x.key).join();
    const onChange = (v) => {
      const before = visible();
      values[f.key] = v;
      clearResults();
      // Rebuild only when a field appears or disappears, so focus stays put.
      if (visible() !== before) {
        renderForm();
        form.querySelector(`[name="${id}"]:checked, #${id}`)?.focus();
      }
      scheduleLive();
    };
    if (f.type === "seg") {
      const custom = customOn.has(f.key);
      // Moving between a listed choice and Custom adds or removes the typed box.
      const pick = (value, toCustom) => {
        if (toCustom === custom) return onChange(value);
        if (toCustom) customOn.add(f.key); else { customOn.delete(f.key); badCustom.delete(f.key); }
        values[f.key] = value;
        clearResults();
        renderForm();
        form.querySelector(toCustom ? `#${id}-custom` : `[name="${id}"]:checked`)?.focus();
        scheduleLive();
      };
      return h("div", { class: "field" },
        h("fieldset", { class: "seg", "aria-describedby": describedBy },
          h("legend", {}, f.label),
          f.options.map(([value, label]) => h("label", {},
            h("input", { type: "radio", name: id, value, checked: !custom && values[f.key] === value, onchange: () => pick(value, false) }),
            label)),
          f.custom && h("label", {},
            h("input", { type: "radio", name: id, value: "custom", checked: custom, onchange: () => pick(f.custom.value, true) }),
            "Custom")),
        custom && customBox(f, id),
        hint);
    }
    if (f.type === "color") {
      return h("div", { class: "field" },
        h("label", { for: id }, f.label),
        h("div", { class: "color-row" },
          h("input", { id, type: "color", value: values[f.key], "aria-describedby": describedBy,
            oninput: (e) => { values[f.key] = e.target.value.toUpperCase(); e.target.nextSibling.textContent = values[f.key]; clearResults(); scheduleLive(); } }),
          h("output", { class: "num", for: id }, values[f.key])),
        hint);
    }
    if (f.type === "select") {
      return h("div", { class: "field" },
        h("label", { for: id }, f.label),
        h("select", { id, "aria-describedby": describedBy, onchange: (e) => onChange(e.target.value) },
          f.options.map(([value, label]) => h("option", { value, selected: values[f.key] === value }, label))),
        hint);
    }
    if (f.type === "range") {
      const set = (n) => { values[f.key] = n; clearResults(); scheduleLive(); };
      const slider = h("input", { id, type: "range", min: f.min, max: f.max, step: f.step, value: values[f.key], "aria-describedby": describedBy,
        oninput: (e) => { exact.value = e.target.value; set(Number(e.target.value)); } });
      // The box takes an exact value. Typing outside the range is ignored, and leaving
      // the box shows the value in use again.
      const exact = h("input", { type: "number", class: "range-num", min: f.min, max: f.max, step: "any", value: values[f.key],
        "aria-label": `${f.label}, exact value`,
        oninput: (e) => {
          const n = Number(e.target.value);
          if (e.target.value === "" || !(n >= f.min && n <= f.max)) return;
          slider.value = n;
          set(n);
        },
        onchange: (e) => { e.target.value = values[f.key]; } });
      return h("div", { class: "field" },
        h("label", { for: id }, f.label),
        h("div", { class: "range-row" }, slider, exact, f.unit?.trim() && h("span", { class: "unit" }, f.unit.trim())),
        hint);
    }
    return h("div", { class: "field" },
      h("label", { for: id }, f.label),
      h("input", { id, type: "text", value: values[f.key], placeholder: f.placeholder, "aria-describedby": describedBy, autocomplete: "off",
        oninput: (e) => { values[f.key] = e.target.value; clearResults(); } }),
      hint);
  }

  // A typed value for a choice field: a number from custom.min to custom.max (whole
  // numbers only with custom.whole), or with custom.ratio a shape such as 3:2.
  function customBox(f, id) {
    const c = f.custom;
    badCustom.delete(f.key);   // the box starts from the last good value
    return h("div", { class: "custom-row" },
      h("input", { id: `${id}-custom`, type: c.ratio ? "text" : "number", value: values[f.key], min: c.min, max: c.max,
        step: "any", inputmode: c.ratio ? "text" : "decimal", autocomplete: "off",
        "aria-label": `${f.label}, custom value`, "aria-describedby": `${id}-range`,
        oninput: (e) => {
          const v = customValue(c, e.target.value);
          if (v === null) badCustom.add(f.key); else { badCustom.delete(f.key); values[f.key] = v; }
          e.target.setAttribute("aria-invalid", String(v === null));
          clearResults();
          scheduleLive();
        } }),
      c.unit && h("span", { class: "unit" }, c.unit),
      h("span", { class: "hint", id: `${id}-range` }, c.ratio ? "Width:height, such as 3:2" : `${c.min} to ${c.max}`));
  }

  // Run --------------------------------------------------------------------------------
  function problem() {
    const min = tool.minFiles || 1;
    if (state.files.length < min) return min > 1 ? `Add at least ${min} files.` : "Add a file to start.";
    if (tool.preview === "timeline" && state.end - state.start < 0.1) return "Pick a longer clip.";
    const bad = tool.fields.find((f) => badCustom.has(f.key) && (!f.when || f.when(values)));
    if (bad) return bad.custom.ratio ? `${bad.label}: type a shape such as 3:2.`
      : `${bad.label}: type a ${bad.custom.whole ? "whole number" : "number"} from ${bad.custom.min} to ${bad.custom.max}${bad.custom.unit ? ` ${bad.custom.unit}` : ""}.`;
    return tool.validate?.(state.files, values) || null;
  }

  function setStep(n) {
    for (const li of steps.children) {
      const k = Number(li.dataset.step);
      li.classList.toggle("is-done", k < n);
      if (k === n) li.setAttribute("aria-current", "step"); else li.removeAttribute("aria-current");
    }
  }

  function readyStatus() {
    if (state.busy || state.preparing) return;
    setStep(state.files.length ? 2 : 1);
    const issue = problem();
    actionBtn.disabled = !!issue;
    mark.setAttribute("class", "mark");
    mark.style.removeProperty("--p");
    if (issue) setStatus(issue, state.files.length ? "" : (many ? "You can add several files." : ""));
    else setStatus("Ready", "Everything runs on this device.");
  }

  /** failed: a real failure (not a wrong file or missing setting), so offer a bug report. */
  function setStatus(title, note = "", isError = false, failed = false) {
    statusTitle.textContent = title;
    statusNote.textContent = note;
    status.classList.toggle("is-error", isError);
    if (failed) {
      noteProblem(tool.name, note || title);
      statusNote.append(note ? " " : "", h("a", { href: "/#/report" }, "Report this problem"));
    }
  }

  function progress(p) {
    if (!mark.classList.contains("is-progress")) {
      mark.style.setProperty("--p", "0");
      mark.setAttribute("class", "mark is-progress");
      statusTitle.textContent = `${tool.action === "Apply" ? "Applying" : "Working"}…`;
    }
    mark.style.setProperty("--p", String(p));
    statusNote.textContent = `${Math.round(p * 100)}%`;
  }

  function engineStatus(s) {
    if (s.phase === "engine") {
      mark.setAttribute("class", "mark is-busy");
      const mb = s.total ? ` ${fmtBytes(s.loaded)} of ${fmtBytes(s.total)}` : "";
      setStatus("Loading the video engine", `First time only.${mb}`);
    } else if (s.phase === "model") {
      mark.setAttribute("class", "mark is-busy");
      setStatus("Downloading the AI model", `First time only. ${fmtBytes(s.loaded)} of ${fmtBytes(s.total)}`);
    } else if (s.phase === "runtime") {
      setStatus("Starting the AI engine", "This takes a few seconds the first time.");
    } else if (s.phase === "segment") {
      if (!state.busy) mark.setAttribute("class", "mark is-busy");
      setStatus("Finding the subject", "Runs on your device.");
    } else if (s.phase === "reading") {
      setStatus("Reading your files", "");
    } else if (s.phase === "working") {
      setStatus(`${tool.action === "Apply" ? "Applying" : "Working"}…`, "0%");
    }
  }

  const usesFFmpeg = () => tool.group === "video";

  async function onAction() {
    if (state.busy) {
      await cancelFFmpeg();
      return;
    }
    const issue = problem();
    if (issue) { setStatus(issue, "", true); return; }
    const batch = tool.batch && state.files.length > 1;
    if (batch && !(await allowBatch(state.files.length))) { refreshBatchLine(); return; }
    state.busy = true;
    clearResults();
    actionBtn.textContent = usesFFmpeg() ? "Cancel" : tool.action;
    actionBtn.disabled = !usesFFmpeg();
    mark.setAttribute("class", "mark is-busy");
    setStatus("Starting", "");
    const p0 = state.probes[0] || {};
    const meta = {
      duration: p0.duration || 0, width: p0.width, height: p0.height,
      durations: state.probes.map((p) => p?.duration || 0),
      start: state.start, end: state.end,
    };
    let cancelled = false;
    try {
      let out;
      if (batch) {
        out = [];
        const n = state.files.length;
        for (let i = 0; i < n; i++) {
          const p = state.probes[i] || {};
          const one = { ...meta, duration: p.duration || 0, width: p.width, height: p.height, durations: [p.duration || 0] };
          out.push(...await tool.run({ files: [state.files[i]], values, meta: one,
            progress: (x) => progress((i + x) / n), status: engineStatus, prepare: prepareMask }));
        }
      } else {
        out = await tool.run({ files: state.files, values, meta, progress, status: engineStatus, prepare: prepareMask });
      }
      state.results = out;
      mark.style.setProperty("--p", "1");
      mark.setAttribute("class", "mark is-progress is-done");
      setStatus("Done", out.length > 1 ? `${out.length} files ready to save.` : "Your file is ready to save.");
      announce("Done. Your file is ready to save.");
      renderResults();
    } catch (err) {
      cancelled = /terminate|called FFmpeg.terminate/i.test(err?.message || "");
      mark.setAttribute("class", cancelled ? "mark" : "mark is-error");
      setStatus(cancelled ? "Stopped" : "Something went wrong", cancelled ? "Nothing was saved." : err.message, !cancelled, !cancelled);
      if (!cancelled) console.error(err);
    } finally {
      state.busy = false;
      actionBtn.textContent = tool.action;
      actionBtn.disabled = false;
      refreshBatchLine();
    }
  }

  function renderResults() {
    const items = state.results.map(({ blob, name, compareTo }) => {
      const change = compareTo ? Math.round((1 - blob.size / compareTo) * 100) : null;
      const delta = change == null ? null : change > 0 ? h("b", {}, `${change}% smaller`) : `${-change}% larger`;
      return h("li", { class: "result" },
        h("div", {}, h("div", { class: "file-name", title: name }, name),
          h("div", { class: "file-meta num" }, fmtBytes(blob.size), delta && ", ", delta)),
        h("button", { class: "btn btn-sm", type: "button", onclick: () => saveBlob(blob, name) }, "Save"));
    });
    if (state.results.length > 1) {
      items.unshift(h("li", { class: "result" },
        h("div", {}, h("div", { class: "file-name" }, "All files"), h("div", { class: "file-meta" }, "One ZIP archive")),
        h("button", { class: "btn btn-sm btn-primary", type: "button",
          onclick: async () => saveBlob(await zipBlobs(state.results), `${tool.id}-files.zip`) }, "Save all")));
    }
    results.replaceChildren(...items);
    setStep(3);
    results.querySelector("button")?.focus({ preventScroll: true });
  }

  function clearResults() {
    if (state.busy) return;
    state.results = [];
    results.replaceChildren();
    readyStatus();
  }

  // Cleanup when the view changes.
  return () => {
    clearTimeout(liveTimer);
    liveBitmap?.close?.();
    for (const u of urls) URL.revokeObjectURL(u);
    if (state.busy && usesFFmpeg()) cancelFFmpeg();
  };
}

function chevron(d) {
  return `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="${d}"/></svg>`;
}
