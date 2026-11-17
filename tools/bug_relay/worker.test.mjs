// Run: node tools/bug_relay/worker.test.mjs
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { claimConfirmation, confirmationEmail, newReference, renderTicket, sentFrom, ticketVariables } from "./ticket.js";

const now = new Date("2026-11-16T14:32:00Z");

// The shape the desktop app sends.
const v = ticketVariables(
  "[Videl Bug] Crash: Trim closes the app",
  "Bug Type: Crash\nReporter Email: a@b.co\n\n--- Description ---\nStep 1\n<script>x</script> & more",
  "a@b.co", { name: "shot <1>.png", type: "image/png" }, "Videl/5.0.9 (Windows 11)", now);
assert.equal(v.BUG_TYPE, "Crash");
assert.equal(v.TITLE, "Trim closes the app");
assert.equal(v.REPORTER_EMAIL, "a@b.co");
assert.match(v.SCREENSHOT, /^shot &lt;1&gt;\.png<br><img src="cid:screenshot"/);   // shown inline, name escaped
assert.equal(ticketVariables("s", "b", "", { name: "x.bmp", type: "image/bmp" }, "", now).SCREENSHOT, "Attached (x.bmp)");
assert.equal(v.DESCRIPTION, "Step 1\n&lt;script&gt;x&lt;/script&gt; &amp; more");
assert.equal(v.RECEIVED_AT, "16 Nov 2026, 14:32 UTC");
assert.equal(v.SENT_FROM, "Desktop app 5.0.9 on Windows 11");

// Anything else passes through whole, with fallbacks for the rest.
const w = ticketVariables("Something odd", "free text", "", null, "", now);
assert.deepEqual([w.BUG_TYPE, w.TITLE, w.DESCRIPTION, w.REPORTER_EMAIL, w.SCREENSHOT],
  ["Bug", "Something odd", "free text", "Not provided", "None"]);

// The web app's browser line moves out of the description into "Sent from".
const ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/157.0.0.0 Safari/537.36";
const web = ticketVariables("[Videl Bug] Feature Problem: test", `Bug Type: x\n\n--- Description ---\ntest\n\nSent from the Videl web app. Browser: ${ua}`, "", null, ua, now);
assert.equal(web.DESCRIPTION, "test");
assert.match(web.SENT_FROM, /^Web app, Chrome 157 on Windows<br><span[^>]*>Mozilla\/5\.0/);

// Every source the relay can see.
const from = (body, agent) => sentFrom(body, agent).label;
assert.equal(from("x", "Videl"), "Desktop app");                                // builds before 5.0.9
assert.equal(from("x", "Videl-Android/5.0.9"), "Android app 5.0.9");
assert.equal(from("x", "Dart/3.9 (dart:io)"), "Android app");                    // Android before 5.0.9
assert.equal(from("x", "curl/8"), "Unknown");
assert.equal(from("Sent from the Videl web app. Browser: Mozilla/5.0 (iPhone; CPU iPhone OS 19_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/19.0 Mobile/15E148 Safari/604.1", ""),
  "Web app, Safari 19 on iOS");
assert.equal(from("Sent from the Videl web app. Browser: Mozilla/5.0 (Linux; Android 16; Pixel 9) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/157.0.0.0 Mobile Safari/537.36", ""),
  "Web app, Chrome 157 on Android 16");

// References: "VB-" and six unambiguous characters, different each time.
const refs = new Set(Array.from({ length: 200 }, newReference));
assert.ok([...refs].every((r) => /^VB-[A-HJ-NP-Z2-9]{6}$/.test(r)));
assert.ok(refs.size > 190);

// The confirmation carries the reference and time, never anything the reporter typed.
const confirmTemplate = readFileSync(new URL("./confirm-email.html", import.meta.url), "utf8");
const c = confirmationEmail(confirmTemplate, "VB-ABC234", now);
assert.equal(c.subject, "We received your Videl bug report (VB-ABC234)");
assert.doesNotMatch(c.html, /\{\{\{/);
assert.match(c.html, /VB-ABC234/);
assert.match(c.html, /16 Nov 2026, 14:32 UTC/);
assert.match(c.text, /Reference: VB-ABC234/);
assert.equal(confirmationEmail.length, 2);   // (template, reference): no report fields can reach it

// At most one confirmation per address per day, case-insensitively, storing only a hash.
const store = new Map();
const kv = { get: async (k) => store.get(k) ?? null, put: async (k, v, o) => { store.set(k, v); assert.equal(o.expirationTtl, 86400); } };
assert.equal(await claimConfirmation(kv, "Someone@Example.com"), true);
assert.equal(await claimConfirmation(kv, " someone@example.com "), false);
assert.equal(await claimConfirmation(kv, "other@example.com"), true);
assert.ok([...store.keys()].every((k) => /^confirm:[0-9a-f]{64}$/.test(k)));

// Every placeholder in the real template gets filled.
const html = renderTicket(readFileSync(new URL("./ticket-email.html", import.meta.url), "utf8"), { ...v, REFERENCE: "VB-ABC234" });
assert.doesNotMatch(html, /\{\{\{/);
assert.match(html, /Trim closes the app/);
assert.match(html, /Desktop app 5\.0\.9 on Windows 11/);
assert.match(html, /app\.videl\.app\/assets\/videl-logo\.png/);

console.log("ok");
