// Run: node tools/bug_relay/worker.test.mjs
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { renderTicket, ticketVariables } from "./ticket.js";

const now = new Date("2026-11-16T14:32:00Z");

// The shape both apps send.
const v = ticketVariables(
  "[Videl Bug] Crash: Trim closes the app",
  "Bug Type: Crash\nReporter Email: a@b.co\n\n--- Description ---\nStep 1\n<script>x</script> & more",
  "a@b.co", { name: "shot <1>.png", type: "image/png" }, now);
assert.equal(v.BUG_TYPE, "Crash");
assert.equal(v.TITLE, "Trim closes the app");
assert.equal(v.REPORTER_EMAIL, "a@b.co");
assert.match(v.SCREENSHOT, /^shot &lt;1&gt;\.png<br><img src="cid:screenshot"/);   // shown inline, name escaped
assert.equal(ticketVariables("s", "b", "", { name: "x.bmp", type: "image/bmp" }, now).SCREENSHOT, "Attached (x.bmp)");
assert.equal(v.DESCRIPTION, "Step 1\n&lt;script&gt;x&lt;/script&gt; &amp; more");
assert.equal(v.RECEIVED_AT, "16 Nov 2026, 14:32 UTC");

// Anything else passes through whole, with fallbacks for the rest.
const w = ticketVariables("Something odd", "free text", "", null, now);
assert.deepEqual([w.BUG_TYPE, w.TITLE, w.DESCRIPTION, w.REPORTER_EMAIL, w.SCREENSHOT],
  ["Bug", "Something odd", "free text", "Not provided", "None"]);

// Every placeholder in the real template gets filled.
const html = renderTicket(readFileSync(new URL("./ticket-email.html", import.meta.url), "utf8"), v);
assert.doesNotMatch(html, /\{\{\{/);
assert.match(html, /Trim closes the app/);
assert.match(html, /app\.videl\.app\/assets\/videl-logo\.png/);

console.log("ok");
