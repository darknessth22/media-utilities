// Videl bug-report relay (Cloudflare Worker).
//
// The Resend key lives here as a Worker secret, never inside the app: a key
// baked into a public installer or APK can be extracted by anyone. The relay
// only ever mails the support inbox, so it cannot be abused as an open mail
// relay; the reporter's address goes into Reply-To instead of receiving a copy.
//
// Deploy:  npx wrangler deploy -c tools/bug_relay/wrangler.toml   (from the repo root; see WORKFLOW.md)
// Secret:  npx wrangler secret put RESEND_API_KEY -c tools/bug_relay/wrangler.toml

const SUPPORT = "videl.support@gmail.com";
const TEMPLATE_ID = "a0f0da5f-aa3b-4e0b-bef7-88c62380fc17";   // "Videl bug report" in Resend → Templates
const MAX_SUBJECT = 200;
const MAX_BODY = 20_000;
const MAX_IMAGE_BYTES = 5 * 1024 * 1024;
const IMAGE_TYPES = new Set(["image/png", "image/jpeg", "image/webp", "image/bmp"]);
const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

// Browsers may only call the relay from the Videl web app (the apps send no Origin).
// The local address is the test server in WORKFLOW.md.
const WEB_ORIGINS = new Set(["https://videl-web.mostafafares080.workers.dev", "http://127.0.0.1:8765"]);

export default {
  async fetch(request, env) {
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

    if (!env.RESEND_API_KEY) return reply(503, "Bug reporting is not configured.");
    try {
      await sendEmail(env, { subject, body, reporter, shot });
    } catch (err) {
      console.error(err.message);
      return reply(502, "Could not deliver the report. Please try again later.");
    }
    return reply(202, "Report sent.");
  },
};

async function sendEmail(env, { subject, body, reporter, shot }) {
  const base = { to: [SUPPORT] };
  if (reporter) base.reply_to = reporter;
  if (shot) base.attachments = [{ filename: shot.name, content: shot.data }];

  // The designed email (tools/bug_relay/ticket-email.html, stored in Resend).
  // The template sets From, Subject and preview text itself. The screenshot is
  // embedded in the body (cid:), so it shows without opening an attachment.
  const templated = await resend(env, {
    ...base,
    attachments: base.attachments?.map((a) => (inline(shot) ? { ...a, content_id: SHOT_CID } : a)),
    template: { id: TEMPLATE_ID, variables: ticketVariables(subject, body, reporter, shot) },
  });
  if (templated.ok) return;
  console.error(`Template send failed (${templated.status}): ${await templated.text()}`);

  // Never lose a report because the template is missing or broken: fall back to plain text.
  // Without a verified domain, Resend sends from onboarding@resend.dev and only
  // to the account owner's address -- which is exactly SUPPORT.
  const plain = await resend(env, { ...base, from: "Videl Bug Reporter <onboarding@resend.dev>", subject, text: body });
  if (!plain.ok) throw new Error(`Resend HTTP ${plain.status}: ${await plain.text()}`);
}

function resend(env, mail) {
  return fetch("https://api.resend.com/emails", {
    method: "POST",
    headers: { Authorization: `Bearer ${env.RESEND_API_KEY}`, "Content-Type": "application/json" },
    body: JSON.stringify(mail),
  });
}

/**
 * Template variables from the report. Both apps send
 *   subject "[Videl Bug] <type>: <title>"
 *   body    "Bug Type: ...\nReporter Email: ...\n\n--- Description ---\n<text>"
 * Anything that doesn't match that shape is passed through whole.
 */
export function ticketVariables(subject, body, reporter, shot, now = new Date()) {
  const head = /^\[Videl Bug\]\s*([^:]+):\s*(.+)$/s.exec(subject);
  const marker = body.indexOf("--- Description ---");
  const description = marker >= 0 ? body.slice(marker + 19).trim() : body;
  const received = new Intl.DateTimeFormat("en-GB", { dateStyle: "medium", timeStyle: "short", timeZone: "UTC" }).format(now);
  return {
    BUG_TYPE: escapeHtml(head ? head[1].trim() : "Bug"),
    TITLE: escapeHtml(head ? head[2].trim() : subject),
    REPORTER_EMAIL: escapeHtml(reporter || "Not provided"),
    RECEIVED_AT: `${received} UTC`,
    SCREENSHOT: !shot ? "None"
      : !inline(shot) ? escapeHtml(`Attached (${shot.name})`)
      : `${escapeHtml(shot.name)}<br><img src="cid:${SHOT_CID}" alt="Screenshot from the reporter" width="420" style="display:block;width:100%;max-width:420px;height:auto;margin-top:8px;border:1px solid #E3E8F2;border-radius:8px;">`,
    DESCRIPTION: escapeHtml(description || "No description was given."),
  };
}

// Mail clients show PNG, JPEG and WebP inline; BMP stays a plain attachment.
const SHOT_CID = "screenshot";
const inline = (shot) => !!shot && shot.type !== "image/bmp";

// Template variables go into the HTML as-is, so reporter text is escaped first.
function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
}

function respond(status, message, cors) {
  return new Response(JSON.stringify({ message }), {
    status,
    headers: { "Content-Type": "application/json", ...cors },
  });
}
