// Report a bug: sends to the same relay as the desktop and Android apps
// (tools/bug_relay), in the same subject/body format, so it gets the same email.
import { h, announce, fmtBytes } from "./ui.js";

const RELAY = "https://videl-bug-relay.mostafafares080.workers.dev/report";
const TYPES = ["UI Problem", "Feature Problem", "Crash / Error", "Performance", "Other"];   // same as the apps
const SHOT_TYPES = ["image/png", "image/jpeg", "image/webp"];
const MAX_SHOT = 5 * 1024 * 1024;

let problem = null;

/** Called when a tool fails, so "Report this problem" can fill the form in. */
export function noteProblem(toolName, message) {
  problem = { toolName, message };
}

export function renderReport(main) {
  const prefill = problem;
  problem = null;

  const type = h("select", { id: "r-type", name: "type" },
    TYPES.map((t) => h("option", { value: t, selected: prefill && t === "Feature Problem" }, t)));
  const title = h("input", { id: "r-title", type: "text", required: true, maxlength: 120, autocomplete: "off",
    placeholder: "A short summary, like “Convert stops at 50%”",
    value: prefill ? `${prefill.toolName}: ${prefill.message}`.slice(0, 120) : "" });
  const desc = h("textarea", { id: "r-desc", required: true, rows: 7, maxlength: 5000,
    placeholder: "What did you do, what did you expect, and what happened instead?" },
    prefill ? `Tool: ${prefill.toolName}\nError: ${prefill.message}\n\nWhat I did:\n` : "");
  const email = h("input", { id: "r-email", type: "email", autocomplete: "email", placeholder: "you@example.com" });
  const shot = h("input", { id: "r-shot", type: "file", accept: SHOT_TYPES.join(","), onchange: showPreview });
  const preview = h("img", { class: "shot-preview", alt: "The screenshot that will be sent", hidden: true });
  const send = h("button", { class: "btn btn-primary btn-lg", type: "submit" }, "Send report");
  const status = h("p", { class: "report-status", role: "status" });

  const form = h("form", { class: "panel report-form", novalidate: true, onsubmit: submit },
    field("r-type", "Type of problem", type),
    field("r-title", "Title", title),
    field("r-desc", "What happened", desc),
    field("r-email", "Your email (optional)", email, "We'll send you a short confirmation, and only use it to reply about this report."),
    field("r-shot", "Screenshot (optional)", h("div", {}, shot, preview), "PNG, JPG or WebP, up to 5 MB. You can also paste one you just copied with Ctrl+V."),
    h("div", { class: "report-actions" }, send, status));

  main.replaceChildren(h("div", { class: "wrap report" },
    h("h1", {}, "Report a bug"),
    h("p", { class: "cat-lede" }, "Tell us what went wrong. The report goes straight to the Videl team. Your files are never sent, only what you write here and the screenshot, if you add one."),
    form));
  document.addEventListener("paste", onPaste);

  // Ctrl+V anywhere on the page takes a copied screenshot. In a text box, a
  // clipboard that also holds text is left alone so ordinary pasting still works.
  async function onPaste(e) {
    if (!form.isConnected) return document.removeEventListener("paste", onPaste);   // left the page
    const item = [...e.clipboardData.items].find((i) => i.kind === "file" && i.type.startsWith("image/"));
    if (!item) return;
    if (e.clipboardData.types.includes("text/plain") && e.target.closest?.("input, textarea")) return;
    e.preventDefault();
    let file = item.getAsFile();
    // Screenshots arrive as PNG; a full 4K one can pass the 5 MB limit, so re-encode those.
    if (!SHOT_TYPES.includes(file.type) || file.size > MAX_SHOT) file = await toJpeg(file);
    const dt = new DataTransfer();
    dt.items.add(new File([file], `pasted-screenshot.${file.type === "image/jpeg" ? "jpg" : "png"}`, { type: file.type }));
    shot.files = dt.files;
    showPreview();
    setStatus("Screenshot pasted.");
  }

  function showPreview() {
    const file = shot.files[0];
    if (preview.src) URL.revokeObjectURL(preview.src);
    preview.hidden = !file;
    if (file) preview.src = URL.createObjectURL(file);
  }

  async function submit(e) {
    e.preventDefault();
    const file = shot.files[0];
    const problemText =
      !title.value.trim() ? "Add a title." :
      !desc.value.trim() ? "Describe what happened." :
      email.value && !email.checkValidity() ? "That email address doesn't look right." :
      file && !SHOT_TYPES.includes(file.type) ? "The screenshot must be a PNG, JPG or WebP image." :
      file && file.size > MAX_SHOT ? `The screenshot is ${fmtBytes(file.size)}. The limit is 5 MB.` : "";
    if (problemText) return setStatus(problemText, true);

    send.disabled = true;
    setStatus("Sending…");
    const payload = {
      subject: `[Videl Bug] ${type.value}: ${title.value.trim()}`,
      body: `Bug Type: ${type.value}\nReporter Email: ${email.value.trim() || "(not provided)"}\n\n--- Description ---\n${desc.value.trim()}\n\nSent from the Videl web app. Browser: ${navigator.userAgent}`,
      reporter_email: email.value.trim(),
    };
    try {
      if (file) payload.screenshot = { name: file.name, type: file.type, data: await base64(file) };
      const res = await fetch(RELAY, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
      if (!res.ok) {
        const { message } = await res.json().catch(() => ({}));
        throw new Error(message || `The report couldn't be sent (HTTP ${res.status}).`);
      }
      form.replaceWith(h("div", { class: "panel report-done" },
        h("h2", {}, "Report sent"),
        h("p", {}, email.value.trim() ? "Thanks. We'll reply to your email if we need more details." : "Thanks. The team will look into it."),
        h("a", { class: "btn", href: "/#/tools" }, "Back to the tools")));
      announce("Report sent");
    } catch (err) {
      send.disabled = false;
      setStatus(err.message === "Failed to fetch" ? "The report couldn't be sent. Check your connection and try again." : err.message, true);
    }
  }

  function setStatus(text, isError = false) {
    status.textContent = text;
    status.classList.toggle("is-error", isError);
  }
}

function field(id, label, control, hint) {
  return h("div", { class: "field" }, h("label", { for: id }, label), control, hint ? h("span", { class: "hint" }, hint) : null);
}

async function toJpeg(file) {
  const bitmap = await createImageBitmap(file);
  const canvas = Object.assign(document.createElement("canvas"), { width: bitmap.width, height: bitmap.height });
  canvas.getContext("2d").drawImage(bitmap, 0, 0);
  const blob = await new Promise((resolve) => canvas.toBlob(resolve, "image/jpeg", 0.85));
  return new File([blob], "pasted-screenshot.jpg", { type: "image/jpeg" });
}

function base64(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result).split(",")[1]);
    reader.onerror = () => reject(new Error("The screenshot couldn't be read."));
    reader.readAsDataURL(file);
  });
}
