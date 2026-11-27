// Videl account on the web: only for Pro features (batches for now). One-file
// tools never need it. Sign-in is an emailed 6-digit code, no password. The
// license server (license.videl.app) keeps the session in an HttpOnly cookie
// and counts the free batches per account per day, so clearing this site's
// data or a private window does not reset them.
import { h, announce } from "./ui.js";

const API = "https://license.videl.app";
const ORDER_KEY = "videl.order";

const MESSAGES = {
  bad_email: "That email address doesn't look right.",
  email_not_allowed: "Use a permanent email address, not a throwaway one.",
  too_many_codes: "Too many codes for this address. Wait an hour, then try again.",
  busy: "Sign-in is busy today. Please try again tomorrow.",
  email_failed: "The email could not be sent. Try again in a minute.",
  not_configured: "Sign-in isn't available right now. Try again later.",
  code_expired: "That code has expired. Ask for a new one.",
  too_many_tries: "Too many wrong tries. Ask for a new code.",
  wrong_code: "That code is not right. Check the email and try again.",
  too_many_files: "A free batch goes up to 10 files. Use fewer files, or get Videl Pro for any number.",
  limit_reached: "You have used today's 5 free batches. They come back at midnight (Cairo time), or get Videl Pro for no limit.",
  trial_used: "This account has already had its free trial.",
  no_such_license: "That license key was not found. Check it for typos.",
  revoked: "That license has been cancelled. Contact us on WhatsApp if you think that is a mistake.",
  trial_license: "A trial from the desktop or phone app stays on that device. Start the web trial instead.",
  lifetime_license: "Your license is permanent, so it never needs renewing.",
  rate_limited: "Too many requests. Wait a minute and try again.",
  bad_input: "Check your name, contact and reference: one is missing or too long.",
  preset_limit: "A free account keeps 3 saved presets. Delete one, or get Videl Pro to save any number.",
  preset_limit_pro: "An account keeps up to 100 saved presets. Delete one to save another.",
  bad_preset: "Give the preset a name of up to 40 characters.",
};

async function call(path, body) {
  let r;
  try {
    r = await fetch(API + path, {
      method: body ? "POST" : "GET", credentials: "include",
      headers: body ? { "Content-Type": "application/json" } : {},
      body: body ? JSON.stringify(body) : undefined,
    });
  } catch {
    const e = new Error("Could not reach Videl. Check your connection and try again.");
    e.code = "offline";
    throw e;
  }
  const data = await r.json().catch(() => ({}));
  if (!r.ok) {
    const e = new Error(MESSAGES[data.error] || data.message || "Something went wrong. Try again.");
    e.code = data.error;
    throw e;
  }
  return data;
}

let me;   // undefined: not asked yet; null: signed out
export async function getMe(force = false) {
  if (me === undefined || force) {
    try { me = await call("/me"); } catch { me = null; }
  }
  return me;
}

const field = (label, input, hint) => h("div", { class: "field" }, h("label", { for: input.id }, label), input, hint && h("p", { class: "hint" }, hint));
const errorLine = () => h("p", { class: "acct-error", role: "alert" });

/** The sign-in sheet. Resolves with the account, or null when closed. */
export function signIn(why = "") {
  return new Promise((resolve) => {
    const email = h("input", { id: "si-email", type: "email", autocomplete: "email", required: true, placeholder: "you@example.com" });
    const code = h("input", { id: "si-code", type: "text", inputmode: "numeric", autocomplete: "one-time-code", maxlength: 6, placeholder: "123456" });
    const err = errorLine();
    const send = h("button", { class: "btn btn-primary", type: "submit" }, "Email me a code");
    const step1 = h("form", { class: "acct-form", onsubmit: async (e) => {
      e.preventDefault();
      err.textContent = "";
      send.disabled = true;
      try {
        await call("/auth/code", { email: email.value });
        step1.hidden = true;
        step2.hidden = false;
        hint2.textContent = `We sent a 6-digit code to ${email.value.trim()}. It works for 10 minutes.`;
        code.focus();
      } catch (x) { err.textContent = x.message; }
      send.disabled = false;
    } }, field("Email", email), send);
    const hint2 = h("p", { class: "hint" });
    const verify = h("button", { class: "btn btn-primary", type: "submit" }, "Sign in");
    const step2 = h("form", { class: "acct-form", hidden: true, onsubmit: async (e) => {
      e.preventDefault();
      err.textContent = "";
      verify.disabled = true;
      try {
        me = await call("/auth/verify", { email: email.value, code: code.value });
        presetCache = undefined;
        announce("Signed in.");
        dlg.close("ok");
      } catch (x) { err.textContent = x.message; }
      verify.disabled = false;
    } }, hint2, field("Code", code), verify,
      h("button", { class: "btn btn-quiet", type: "button", onclick: () => { step2.hidden = true; step1.hidden = false; } }, "Use a different email"));
    const dlg = h("dialog", { class: "acct-sheet", "aria-labelledby": "si-h" },
      h("h2", { id: "si-h" }, "Sign in to Videl"),
      h("p", { class: "hint" }, why || "No password: we email you a code."),
      step1, step2, err,
      h("button", { class: "btn btn-icon btn-quiet acct-close", type: "button", "aria-label": "Close", onclick: () => dlg.close() }, "✕"));
    dlg.addEventListener("close", () => { dlg.remove(); resolve(dlg.returnValue === "ok" ? me : null); });
    document.body.append(dlg);
    dlg.showModal();
    email.focus();
  });
}

/** "Get Pro" sheet for a refused batch. */
function limitSheet(message) {
  const dlg = h("dialog", { class: "acct-sheet", "aria-labelledby": "lim-h" },
    h("h2", { id: "lim-h" }, "Videl Pro"),
    h("p", {}, message),
    h("div", { class: "acct-actions" },
      h("a", { class: "btn btn-primary", href: "/#/account", onclick: () => dlg.close() }, "Get Pro"),
      h("button", { class: "btn", type: "button", onclick: () => dlg.close() }, "Not now")));
  dlg.addEventListener("close", () => dlg.remove());
  document.body.append(dlg);
  dlg.showModal();
}

/**
 * Before a batch of n files (n > 1): sign in if needed, then ask the server for
 * one of today's free runs (Pro: no limit). False when the batch must not start.
 */
export async function allowBatch(n) {
  let acc = await getMe();
  if (!acc) acc = await signIn("Batches of several files need a free Videl account: 5 free batches a day, or no limit with Videl Pro. One file at a time never needs an account.");
  if (!acc) return false;
  try {
    const r = await call("/use", { kind: "batch", files: n });
    me = { ...me, runs_left: r.runs_left };
    return true;
  } catch (e) {
    if (e.code === "signed_out") { me = null; return allowBatch(n); }
    limitSheet(e.message);
    return false;
  }
}

/**
 * "Batches: 3 of 5 free runs left today", or a Pro note. Asks the server each time
 * (opening a tool, after a run), so a used run, a new license or a revoked one shows.
 */
export async function batchNote() {
  const acc = await getMe(true);
  if (!acc) return "Add several files for a batch: 5 free a day with a free account, no limit with Videl Pro.";
  return acc.pro ? "Videl Pro: batches with no limit." : `Batches: ${acc.runs_left} of ${acc.runs_per_day} free runs left today, up to ${acc.batch_files} files each.`;
}

// Saved presets ---------------------------------------------------------------------------
// A tool's settings under a name, kept on the account (license server, /me/presets), so
// every browser signed in sees them: 3 on a free account, any number with Videl Pro.
let presetCache;   // { presets, limit } once loaded; signed out: never loaded
async function loadPresets(force = false) {
  if (!(await getMe())) return null;
  if (presetCache === undefined || force) {
    try { presetCache = await call("/me/presets"); } catch { return null; }
  }
  return presetCache;
}

/**
 * The saved-presets row in a tool's Settings panel. `read()` gives the settings to
 * save (null while one is invalid); `apply(values)` puts a preset's into the form.
 */
export function presetBar(tool, read, apply) {
  const chips = h("div", { class: "preset-chips" });
  const note = h("p", { class: "hint preset-note" });
  const err = errorLine();
  const name = h("input", { type: "text", maxlength: 40, autocomplete: "off", "aria-label": "Preset name",
    placeholder: "Name, such as Small for WhatsApp" });
  const saveBtn = h("button", { class: "btn btn-sm", type: "button", onclick: async () => {
    err.textContent = "";
    if (!read()) { err.textContent = "Fix the setting marked in red first."; return; }
    if (!(await getMe()) && !(await signIn("Saved presets need a free Videl account: 3 presets free, any number with Videl Pro."))) return;
    paint(await loadPresets(true));
    saveBtn.hidden = true;
    saveForm.hidden = false;
    name.focus();
  } }, "Save these settings");
  const closeForm = () => { saveForm.hidden = true; saveBtn.hidden = false; name.value = ""; };
  const saveForm = h("form", { class: "preset-save", hidden: true, onsubmit: async (e) => {
    e.preventDefault();
    err.textContent = "";
    const values = read();
    if (!values) { err.textContent = "Fix the setting marked in red first."; return; }
    try {
      paint(presetCache = await call("/me/presets", { tool: tool.id, name: name.value, values }));
      closeForm();
      announce("Preset saved.");
    } catch (x) {
      if (x.code === "preset_limit") limitSheet(x.message); else err.textContent = x.message;
    }
  } }, name,
    h("button", { class: "btn btn-sm btn-primary", type: "submit" }, "Save"),
    h("button", { class: "btn btn-sm btn-quiet", type: "button", onclick: closeForm }, "Cancel"));

  function paint(data) {
    const mine = data ? data.presets.filter((p) => p.tool === tool.id) : [];
    chips.replaceChildren(...mine.map((p) => h("span", { class: "preset-chip" },
      h("button", { class: "preset-apply", type: "button", title: "Use these settings",
        onclick: () => { apply(p.values); announce(`Settings from ${p.name}.`); } }, p.name),
      h("button", { class: "preset-del", type: "button", "aria-label": `Delete the preset ${p.name}`, onclick: async () => {
        if (!confirm(`Delete the preset "${p.name}"?`)) return;
        try { paint(presetCache = await call(`/me/presets/${p.id}/delete`, {})); } catch (x) { err.textContent = x.message; }
      } }, "×"))));
    note.textContent = !data ? "Save settings you use often and pick them again in one tap, with a free account."
      : data.limit == null ? ""
      : `${data.presets.length} of ${data.limit} saved presets on a free account, across all tools. Videl Pro saves any number.`;
  }

  paint(null);
  loadPresets().then((d) => d && paint(d));
  return h("div", { class: "presets", "aria-label": "Saved presets", role: "group" }, chips, saveBtn, saveForm, note, err);
}

const day = (ts) => new Date(ts * 1000).toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });
const PLAN = { monthly: "Monthly", yearly: "Yearly", lifetime: "Permanent", trial: "Trial" };

// The account page, /#/account --------------------------------------------------------------
// The first visit fades the panels in; later refreshes (after an action) keep the
// current panels until the new ones are ready, then cross-fade, so the page never
// drops back to "Loading…".
const reducedMotion = () => matchMedia("(prefers-reduced-motion: reduce)").matches;
const swap = (body, nodes) => {
  const kids = nodes.filter(Boolean);   // replaceChildren would print false/null as text
  if (!body.querySelector(".panel") || !document.startViewTransition || reducedMotion()) body.replaceChildren(...kids);
  else document.startViewTransition(() => body.replaceChildren(...kids));
};

export async function renderAccount(main) {
  let body = main.querySelector(".acct");
  if (!body) {
    body = h("div", { class: "acct is-entering" }, h("p", { class: "hint" }, "Loading…"));
    main.replaceChildren(h("div", { class: "wrap report" },
      h("h1", {}, "Videl Pro"),
      h("p", { class: "cat-lede" }, "Every tool here is free one file at a time, with no account. Videl Pro adds batches of many files at once and any number of saved presets. One license works in the web app, the desktop app and the Android app."),
      body));
  }
  let acc = await getMe(true);
  if (!acc) {
    swap(body, [h("section", { class: "panel" },
      h("h2", {}, "Sign in"),
      h("p", {}, "A free account gives you 5 batches a day, up to 10 files each. No password: we email you a code."),
      h("div", { class: "acct-actions" },
        h("button", { class: "btn btn-primary", type: "button", onclick: async () => { if (await signIn()) renderAccount(main); } }, "Sign in with email")))]);
    return;
  }
  const err = errorLine();
  const act = (fn) => async () => {
    err.textContent = "";
    try { await fn(); await renderAccount(main); } catch (e) { err.textContent = e.message; }
  };
  const status = acc.pro
    ? (acc.plan === "trial" ? `Pro trial, every Pro feature until ${day(acc.paid_until)}.`
      : acc.plan === "lifetime" ? "Pro, permanent license." : `Pro ${PLAN[acc.plan] || ""}, paid until ${day(acc.paid_until)}.`)
    : `Free: ${acc.runs_left} of ${acc.runs_per_day} batches left today, up to ${acc.batch_files} files each. They come back at midnight (Cairo time).`;
  const key = h("input", { id: "acct-key", type: "text", autocomplete: "off", placeholder: "VL-XXXX-XXXX-XXXX-XXXX" });
  let pending = null;
  try { pending = JSON.parse(localStorage.getItem(ORDER_KEY)); } catch { /* none */ }
  // The order may have been approved while the page was closed: ask before showing it.
  if (pending && await orderSettled(pending.code)) { pending = null; acc = await getMe(true) || acc; }

  swap(body, [
    h("section", { class: "panel" },
      h("h2", {}, acc.pro ? "Pro is active" : "Free account"),
      h("p", {}, status),
      h("p", { class: "hint" }, `Signed in as ${acc.email}.`),
      acc.key && h("p", {}, "License key: ", h("code", {}, acc.key),
        h("span", { class: "hint" }, " Enter it in the desktop or Android app to use Pro there too.")),
      h("div", { class: "acct-actions" },
        acc.trial_available && h("button", { class: "btn btn-primary", type: "button", onclick: act(() => call("/me/trial", {})) }, "Start 7-day trial"),
        acc.plan !== "lifetime" && !pending && h("button", { class: "btn", type: "button", onclick: () => buyPanel(main, body) }, acc.pro && acc.plan !== "trial" ? "Renew" : "Buy Pro"),
        h("button", { class: "btn btn-quiet", type: "button", onclick: act(async () => { await call("/auth/signout", {}); me = null; presetCache = undefined; }) }, "Sign out"))),
    pending && orderPanel(main, pending),
    !acc.pro && h("section", { class: "panel" },
      h("h2", {}, "Already bought Pro?"),
      h("form", { class: "acct-form", onsubmit: (e) => { e.preventDefault(); act(() => call("/me/license", { key: key.value }))(); } },
        field("License key", key, "From the License page of the desktop or Android app, or your receipt."),
        h("button", { class: "btn btn-primary", type: "submit" }, "Use it here"))),
    err,
  ]);
  setTimeout(() => body.classList.remove("is-entering"), 700);
}

/** Radio buttons drawn as cards: [{ value, title, detail, badge }]. */
function choiceCards(name, label, options, chosen) {
  return h("fieldset", { class: "choice-cards" },
    h("legend", {}, label),
    options.map((o) => h("label", { class: "choice" },
      h("input", { type: "radio", name, value: o.value, checked: o.value === chosen }),
      h("span", { class: "choice-title" }, o.title, o.badge && h("span", { class: "choice-badge" }, o.badge)),
      o.detail && h("span", { class: "choice-detail" }, o.detail))));
}

async function buyPanel(main, body) {
  const open = body.querySelector(".buy-panel");
  if (open) { open.scrollIntoView({ behavior: reducedMotion() ? "auto" : "smooth", block: "nearest" }); return; }
  let plans;
  try { plans = await call("/plans"); } catch (e) { body.append(h("p", { class: "acct-error" }, e.message)); return; }
  const err = errorLine();
  const name = h("input", { id: "b-name", type: "text", maxlength: 80, autocomplete: "name" });
  const contact = h("input", { id: "b-contact", type: "text", maxlength: 120, autocomplete: "email" });
  const cur = plans.currency;
  const p = plans.prices;
  const per = { monthly: "a month", yearly: "a year" };
  const planCards = choiceCards("plan", "Plan", Object.keys(p).map((id) => ({
    value: id,
    title: PLAN[id] || id,
    detail: `${p[id]} ${cur}${per[id] ? ` ${per[id]}` : ""}`,
    badge: id === "yearly" && p.monthly ? "2 months free" : "",
  })), p.yearly ? "yearly" : Object.keys(p)[0]);
  const methodCards = choiceCards("method", "Pay with", plans.methods.map((m) => ({ value: m.id, title: m.label })), plans.methods[0]?.id);
  const panel = h("section", { class: "panel buy-panel" },
    h("h2", {}, "Buy Videl Pro"),
    h("form", { class: "acct-form", onsubmit: async (e) => {
      e.preventDefault();
      err.textContent = "";
      const f = new FormData(e.target);
      try {
        const order = await call("/me/orders", { plan: f.get("plan"), method: f.get("method"), name: name.value, contact: contact.value });
        localStorage.setItem(ORDER_KEY, JSON.stringify(order));
        renderAccount(main);
      } catch (x) { err.textContent = x.message; }
    } },
      planCards, methodCards,
      field("Your name", name, "Shown as \"Licensed to\" in the apps."),
      field("Email or phone", contact, "For your receipt and help."),
      h("div", { class: "acct-actions" },
        h("button", { class: "btn btn-primary", type: "submit" }, "Continue"),
        h("button", { class: "btn btn-quiet", type: "button", onclick: () => panel.remove() }, "Close"))),
    err);
  body.firstElementChild.after(panel);
  panel.scrollIntoView({ behavior: reducedMotion() ? "auto" : "smooth", block: "nearest" });
}

function orderPanel(main, order) {
  const err = errorLine();
  const ref = h("input", { id: "o-ref", type: "text", maxlength: 60, autocomplete: "off" });
  const sent = !!order.reference;
  const panel = h("section", { class: "panel" },
    h("h2", {}, `Order ${order.code}`),
    h("p", {}, `Send ${order.amount} ${order.currency} by ${order.pay_to.label} to `, h("strong", {}, order.pay_to.number), "."),
    sent
      ? h("p", {}, "Reference sent: ", h("code", {}, order.reference), ". Waiting for the payment to be confirmed, usually within 12 hours (10:00 to 22:00 Cairo time). This page checks by itself.")
      : h("p", {}, `Write ${order.code} in the transfer note. When it is sent, enter the transaction reference here.`),
    !sent && h("form", { class: "acct-form", onsubmit: async (e) => {
      e.preventDefault();
      err.textContent = "";
      try {
        await call(`/me/orders/${order.code}/reference`, { reference: ref.value });
        localStorage.setItem(ORDER_KEY, JSON.stringify({ ...order, reference: ref.value.trim() }));
        renderAccount(main);
      } catch (x) { err.textContent = x.message; }
    } }, field("Transaction reference", ref), h("button", { class: "btn btn-primary", type: "submit" }, "Send reference")),
    !sent && h("p", { class: "hint" }, "Waiting for your payment. This page checks every 30 seconds."),
    h("div", { class: "acct-actions" },
      order.whatsapp && h("a", { class: "btn", href: `https://wa.me/${order.whatsapp}?text=${encodeURIComponent(`Videl Pro order ${order.code}: payment receipt attached.`)}`, target: "_blank", rel: "noopener" }, "Send the receipt on WhatsApp"),
      h("button", { class: "btn btn-quiet", type: "button", onclick: () => { localStorage.removeItem(ORDER_KEY); renderAccount(main); } }, "Cancel order")),
    err);
  let seen = false;
  const timer = setInterval(async () => {
    if (panel.isConnected) seen = true;
    else { if (seen) clearInterval(timer); return; }
    if (await orderSettled(order.code)) { clearInterval(timer); renderAccount(main); }
  }, 30000);
  return panel;
}

/** True when the order is no longer pending (paid, rejected, or not this account's); forgets it. */
async function orderSettled(code) {
  let r;
  try { r = await call(`/me/orders/${code}`); } catch (e) {
    if (e.code !== "no_such_order") return false;   // offline: try again later
    r = { status: "gone" };
  }
  if (r.status === "pending") return false;
  localStorage.removeItem(ORDER_KEY);
  if (r.status === "paid") announce("Payment confirmed. Videl Pro is active.");
  if (r.status === "rejected") alert("This payment could not be confirmed. Contact us on WhatsApp with your order code.");
  return true;
}
