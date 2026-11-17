// Videl bug-report relay (Cloudflare Worker).
//
// Mail goes out through Cloudflare Email Service (the EMAIL binding in
// wrangler.toml), so there is no API key anywhere: nothing to leak from a public
// installer or APK. The binding can only deliver to the support inbox, so the
// relay cannot be abused as an open mail relay; the reporter's address goes into
// Reply-To instead of receiving a copy. Sending to a verified destination
// address is free on the Workers Free plan and counts toward no quota.
//
// A reporter who leaves an address also gets a short confirmation. Cloudflare's
// free plan can't mail arbitrary addresses, so that one goes through Resend
// (free tier, videl.app verified there) with the RESEND_API_KEY secret. Without
// the secret, confirmations are simply skipped. See claimConfirmation for the
// once-a-day-per-address limit.
//
// Deploy:  npx wrangler deploy -c tools/bug_relay/wrangler.toml   (from the repo root; see WORKFLOW.md)
// Secret:  npx wrangler secret put RESEND_API_KEY -c tools/bug_relay/wrangler.toml

import TEMPLATE from "./ticket-email.html";
import CONFIRM_TEMPLATE from "./confirm-email.html";
import { SHOT_CID, claimConfirmation, confirmationEmail, inline, newReference, renderTicket, sentFrom, ticketVariables } from "./ticket.js";

const SUPPORT = "videl.support@gmail.com";   // must match destination_address in wrangler.toml
const FROM = { email: "bugs@videl.app", name: "Videl Bug Reporter" };
const CONFIRM_FROM = "Videl <bugs@videl.app>";
const MAX_SUBJECT = 200;
const MAX_BODY = 20_000;
const MAX_IMAGE_BYTES = 5 * 1024 * 1024;
const IMAGE_TYPES = new Set(["image/png", "image/jpeg", "image/webp", "image/bmp"]);
const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

// Browsers may only call the relay from the Videl web app (the apps send no Origin).
// The local address is the test server in WORKFLOW.md.
const WEB_ORIGINS = new Set(["https://app.videl.app", "https://videl-web.mostafafares080.workers.dev", "http://127.0.0.1:8765"]);

export default {
  async fetch(request, env, ctx) {
    const origin = request.headers.get("Origin");
    const cors = WEB_ORIGINS.has(origin)
      ? { "Access-Control-Allow-Origin": origin, "Access-Control-Allow-Methods": "POST", "Access-Control-Allow-Headers": "Content-Type", "Access-Control-Max-Age": "86400", Vary: "Origin" }
      : {};
    const reply = (status, message) => respond(status, message, cors);
    const path = new URL(request.url).pathname;

    if (request.method === "OPTIONS" && path === "/report") return new Response(null, { status: 204, headers: cors });
    if (request.method !== "POST" || path !== "/report") {
      return reply(404, "Not found.");
    }

    if (env.LIMITER) {
      const ip = request.headers.get("cf-connecting-ip") || "unknown";
      const { success } = await env.LIMITER.limit({ key: ip });
      if (!success) return reply(429, "Too many reports. Try again in a minute.");
    }

    let report;
    try {
      report = await request.json();
    } catch {
      return reply(400, "Body must be JSON.");
    }

    const subject = String(report.subject || "").trim().slice(0, MAX_SUBJECT);
    const body = String(report.body || "").trim().slice(0, MAX_BODY);
    if (!subject || !body) return reply(400, "subject and body are required.");

    const reporter = String(report.reporter_email || "").trim();
    if (reporter && (reporter.length > 254 || !EMAIL_RE.test(reporter))) {
      return reply(400, "Invalid reporter email.");
    }

    const shot = report.screenshot;
    if (shot) {
      if (!IMAGE_TYPES.has(shot.type) || typeof shot.data !== "string") {
        return reply(400, "Screenshot must be PNG, JPEG, WebP or BMP.");
      }
      if ((shot.data.length * 3) / 4 > MAX_IMAGE_BYTES) {
        return reply(413, "Screenshot is larger than 5 MB.");
      }
      shot.name = String(shot.name || "screenshot").slice(0, 100);
    }

    if (!env.EMAIL) return reply(503, "Bug reporting is not configured.");
    const reference = newReference();
    try {
      await sendEmail(env, { subject, body, reporter, shot, reference, userAgent: request.headers.get("User-Agent") || "" });
    } catch (err) {
      console.error(err.message);
      return reply(502, "Could not deliver the report. Please try again later.");
    }
    // Only after the team has the report. Runs after the response, so the
    // reporter isn't kept waiting, and a failure here never fails the report.
    if (reporter && env.RESEND_API_KEY && env.CONFIRMATIONS) ctx.waitUntil(sendConfirmation(env, reporter, reference));
    return reply(202, "Report sent.");
  },
};

async function sendConfirmation(env, to, reference) {
  try {
    if (!(await claimConfirmation(env.CONFIRMATIONS, to))) return;
    const res = await fetch("https://api.resend.com/emails", {
      method: "POST",
      headers: { Authorization: `Bearer ${env.RESEND_API_KEY}`, "Content-Type": "application/json" },
      body: JSON.stringify({ from: CONFIRM_FROM, to: [to], reply_to: SUPPORT, ...confirmationEmail(CONFIRM_TEMPLATE, reference) }),
    });
    if (!res.ok) console.error(`Confirmation not sent (${res.status}): ${await res.text()}`);
  } catch (err) {
    console.error(`Confirmation not sent: ${err.message}`);
  }
}

async function sendEmail(env, { subject, body, reporter, shot, reference, userAgent }) {
  const source = sentFrom(body, userAgent);
  const text = `${source.detail ? body : `${body}\n\nSent from: ${source.label}`}\n\nReference: ${reference}`;   // the web app's body already names its source
  const mail = { from: FROM, to: SUPPORT, subject, text };
  if (reporter) mail.replyTo = reporter;

  // The designed email (ticket-email.html). The screenshot is embedded in the
  // body (cid:), so it still shows after a Gmail Reply, which drops attachments.
  // Content must be bytes: a string is sent as the file's literal text, which
  // is how a base64 string once arrived as a broken image.
  const attachments = shot ? [{
    content: Uint8Array.fromBase64 ? Uint8Array.fromBase64(shot.data) : Uint8Array.from(atob(shot.data), (c) => c.charCodeAt(0)),
    filename: shot.name,
    type: shot.type,
    ...(inline(shot) ? { disposition: "inline", contentId: SHOT_CID } : { disposition: "attachment" }),
  }] : undefined;
  try {
    await env.EMAIL.send({ ...mail, html: renderTicket(TEMPLATE, { ...ticketVariables(subject, body, reporter, shot, userAgent), REFERENCE: reference }), attachments });
    return;
  } catch (err) {
    console.error(`Designed send failed (${err.code}): ${err.message}`);
  }

  // Never lose a report because of the design or the screenshot: send the text alone.
  await env.EMAIL.send(shot ? { ...mail, text: `${text}\n\n(The screenshot could not be attached.)` } : mail);
}

function respond(status, message, cors) {
  return new Response(JSON.stringify({ message }), {
    status,
    headers: { "Content-Type": "application/json", ...cors },
  });
}
