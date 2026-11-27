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

/** "Batches: 3 of 5 free runs left today", or a Pro note; empty when signed out. */
export async function batchNote() {
  const acc = await getMe();
  if (!acc) return "Add several files for a batch: 5 free a day with a free account, no limit with Videl Pro.";
  return acc.pro ? "Videl Pro: batches with no limit." : `Batches: ${acc.runs_left} of ${acc.runs_per_day} free runs left today, up to ${acc.batch_files} files each.`;
}

const day = (ts) => new Date(ts * 1000).toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });
const PLAN = { monthly: "Monthly", yearly: "Yearly", lifetime: "Permanent", trial: "Trial" };

// The account page, /#/account --------------------------------------------------------------
export async function renderAccount(main) {
  const body = h("div", { class: "acct" }, h("p", { class: "hint" }, "Loading…"));
  main.replaceChildren(h("div", { class: "wrap report" },
    h("h1", {}, "Videl Pro"),
    h("p", { class: "cat-lede" }, "Every tool here is free one file at a time, with no account. Videl Pro adds batches of many files at once. One license works in the web app, the desktop app and the Android app."),
    body));
  const acc = await getMe(true);
  if (!acc) {
    body.replaceChildren(h("section", { class: "panel" },
      h("h2", {}, "Sign in"),
      h("p", {}, "A free account gives you 5 batches a day, up to 10 files each. No password: we email you a code."),
      h("div", { class: "acct-actions" },
        h("button", { class: "btn btn-primary", type: "button", onclick: async () => { if (await signIn()) renderAccount(main); } }, "Sign in with email"))));
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
  const pending = localStorage.getItem(ORDER_KEY);

  body.replaceChildren(
    h("section", { class: "panel" },
      h("h2", {}, acc.pro ? "Pro is active" : "Free account"),
      h("p", {}, status),
      h("p", { class: "hint" }, `Signed in as ${acc.email}.`),
      acc.key && h("p", {}, "License key: ", h("code", {}, acc.key),
        h("span", { class: "hint" }, " Enter it in the desktop or Android app to use Pro there too.")),
      h("div", { class: "acct-actions" },
        acc.trial_available && h("button", { class: "btn btn-primary", type: "button", onclick: act(() => call("/me/trial", {})) }, "Start 7-day trial"),
        acc.plan !== "lifetime" && !pending && h("button", { class: "btn", type: "button", onclick: () => buyPanel(main, body) }, acc.pro && acc.plan !== "trial" ? "Renew" : "Buy Pro"),
        h("button", { class: "btn btn-quiet", type: "button", onclick: act(async () => { await call("/auth/signout", {}); me = null; }) }, "Sign out"))),
    pending ? orderPanel(main, JSON.parse(pending)) : null,
    !acc.pro && h("section", { class: "panel" },
      h("h2", {}, "Already bought Pro?"),
      h("form", { class: "acct-form", onsubmit: (e) => { e.preventDefault(); act(() => call("/me/license", { key: key.value }))(); } },
        field("License key", key, "From the License page of the desktop or Android app, or your receipt."),
        h("button", { class: "btn btn-primary", type: "submit" }, "Use it here"))),
    err);
}

async function buyPanel(main, body) {
  let plans;
  try { plans = await call("/plans"); } catch (e) { body.append(h("p", { class: "acct-error" }, e.message)); return; }
  const err = errorLine();
  const name = h("input", { id: "b-name", type: "text", maxlength: 80, autocomplete: "name" });
  const contact = h("input", { id: "b-contact", type: "text", maxlength: 120, autocomplete: "email" });
  const plan = h("select", { id: "b-plan" },
    Object.entries(plans.prices).map(([id, price]) => h("option", { value: id, selected: id === "yearly" },
      `${PLAN[id]}: ${price} ${plans.currency}${id === "yearly" ? ", 2 months free" : " a month"}`)));
  const method = h("select", { id: "b-method" }, plans.methods.map((m) => h("option", { value: m.id }, m.label)));
  body.append(h("section", { class: "panel" },
    h("h2", {}, "Buy Videl Pro"),
    h("form", { class: "acct-form", onsubmit: async (e) => {
      e.preventDefault();
      err.textContent = "";
      try {
        const order = await call("/me/orders", { plan: plan.value, method: method.value, name: name.value, contact: contact.value });
        localStorage.setItem(ORDER_KEY, JSON.stringify(order));
        renderAccount(main);
      } catch (x) { err.textContent = x.message; }
    } },
      field("Plan", plan), field("Pay with", method),
      field("Your name", name, "Shown as \"Licensed to\" in the apps."),
      field("Email or phone", contact, "For your receipt and help."),
      h("button", { class: "btn btn-primary", type: "submit" }, "Continue")),
    err));
}

function orderPanel(main, order) {
  const err = errorLine();
  const ref = h("input", { id: "o-ref", type: "text", maxlength: 60, autocomplete: "off" });
  const state = h("p", { class: "hint" }, order.reference
    ? "Waiting for the payment to be confirmed, usually within 12 hours (10:00 to 22:00 Cairo time). This page checks by itself."
    : "Waiting for your payment. This page checks every 30 seconds.");
  const panel = h("section", { class: "panel" },
    h("h2", {}, `Order ${order.code}`),
    h("p", {}, `Send ${order.amount} ${order.currency} by ${order.pay_to.label} to `, h("strong", {}, order.pay_to.number), "."),
    h("p", {}, `Write ${order.code} in the transfer note. When it is sent, enter the transaction reference here.`),
    h("form", { class: "acct-form", onsubmit: async (e) => {
      e.preventDefault();
      err.textContent = "";
      try {
        await call(`/me/orders/${order.code}/reference`, { reference: ref.value });
        localStorage.setItem(ORDER_KEY, JSON.stringify({ ...order, reference: ref.value }));
        renderAccount(main);
      } catch (x) { err.textContent = x.message; }
    } }, field("Transaction reference", ref), h("button", { class: "btn btn-primary", type: "submit" }, "Send reference")),
    order.whatsapp && h("p", {}, h("a", { href: `https://wa.me/${order.whatsapp}?text=${encodeURIComponent(`Videl Pro order ${order.code}: payment receipt attached.`)}`, target: "_blank", rel: "noopener" }, "Send the receipt on WhatsApp")),
    state,
    h("button", { class: "btn btn-quiet", type: "button", onclick: () => { localStorage.removeItem(ORDER_KEY); renderAccount(main); } }, "Cancel order"),
    err);
  const timer = setInterval(async () => {
    if (!panel.isConnected) return clearInterval(timer);
    try {
      const r = await call(`/me/orders/${order.code}`);
      if (r.status === "paid" || r.status === "rejected") {
        clearInterval(timer);
        localStorage.removeItem(ORDER_KEY);
        if (r.status === "rejected") alert("This payment could not be confirmed. Contact us on WhatsApp with your order code.");
        renderAccount(main);
      }
    } catch { /* offline: try again next time */ }
  }, 30000);
  return panel;
}
