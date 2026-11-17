// Builds the bug-report email from ticket-email.html. Pure functions, so the
// Node test can run them without the Workers runtime.

// Mail clients show PNG, JPEG and WebP inline; BMP stays a plain attachment.
export const SHOT_CID = "screenshot";
export const inline = (shot) => !!shot && shot.type !== "image/bmp";

/**
 * Template values from the report. Both apps send
 *   subject "[Videl Bug] <type>: <title>"
 *   body    "Bug Type: ...\nReporter Email: ...\n\n--- Description ---\n<text>"
 * Anything that doesn't match that shape is passed through whole.
 */
export function ticketVariables(subject, body, reporter, shot, userAgent = "", now = new Date()) {
  const head = /^\[Videl Bug\]\s*([^:]+):\s*(.+)$/s.exec(subject);
  const marker = body.indexOf("--- Description ---");
  const source = sentFrom(body, userAgent);
  const description = (marker >= 0 ? body.slice(marker + 19) : body).replace(WEB_FOOTER, "").trim();
  const received = formatReceived(now);
  return {
    BUG_TYPE: escapeHtml(head ? head[1].trim() : "Bug"),
    TITLE: escapeHtml(head ? head[2].trim() : subject),
    REPORTER_EMAIL: escapeHtml(reporter || "Not provided"),
    RECEIVED_AT: received,
    SENT_FROM: escapeHtml(source.label) + (source.detail
      ? `<br><span style="font-size:12px;color:#5B6B86;">${escapeHtml(source.detail)}</span>` : ""),
    SCREENSHOT: !shot ? "None"
      : !inline(shot) ? escapeHtml(`Attached (${shot.name})`)
      : `${escapeHtml(shot.name)}<br><img src="cid:${SHOT_CID}" alt="Screenshot from the reporter" width="420" style="display:block;width:100%;max-width:420px;height:auto;margin-top:8px;border:1px solid #E3E8F2;border-radius:8px;">`,
    DESCRIPTION: escapeHtml(description || "No description was given."),
  };
}

// The web app ends its description with this line (web/js/report.js).
const WEB_FOOTER = /\s*Sent from the Videl web app\. Browser: (.*)$/s;

/**
 * Where a report came from, as { label, detail }. The web app names the browser
 * in the body; the apps are told apart by User-Agent: "Videl/<version> (<os>)"
 * from the desktop app, "Videl-Android/<version>" from Android. Builds before
 * 5.0.9 sent a bare "Videl" (desktop) or Dart's default agent (Android).
 */
export function sentFrom(body, userAgent = "") {
  const web = WEB_FOOTER.exec(body);
  if (web) return { label: `Web app, ${browserName(web[1])}`, detail: web[1].trim() };
  const app = /^Videl(-Android)?(?:\/(\S+))?(?:\s*\((.+)\))?/.exec(userAgent);
  if (app) {
    const name = app[1] ? "Android app" : "Desktop app";
    return { label: [name, app[2], app[3] && `on ${app[3]}`].filter(Boolean).join(" "), detail: "" };
  }
  if (/^Dart\//.test(userAgent)) return { label: "Android app", detail: "" };
  return { label: "Unknown", detail: userAgent };
}

function browserName(ua) {
  const pick = (rules) => rules.map(([re, name]) => { const m = re.exec(ua); return m && name + (m[1] ? ` ${m[1]}` : ""); }).find(Boolean);
  const browser = pick([[/Edg\w*\/(\d+)/, "Edge"], [/OPR\/(\d+)/, "Opera"], [/(?:Firefox|FxiOS)\/(\d+)/, "Firefox"],
    [/(?:Chrome|CriOS)\/(\d+)/, "Chrome"], [/Version\/(\d+).*Safari/, "Safari"]]) || "a browser";
  const os = pick([[/Android ([\d.]+)/, "Android"], [/iPhone|iPad/, "iOS"], [/Windows/, "Windows"], [/CrOS/, "ChromeOS"],
    [/Mac OS X/, "macOS"], [/Linux/, "Linux"]]);
  return os ? `${browser} on ${os}` : browser;
}

const formatReceived = (now) =>
  `${new Intl.DateTimeFormat("en-GB", { dateStyle: "medium", timeStyle: "short", timeZone: "UTC" }).format(now)} UTC`;

/** A short reference shared by the support email and the reporter's confirmation, like "VB-7K2Q9D". */
export function newReference() {
  const alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789";   // 32 letters, no 0/O or 1/I; 256 % 32 == 0, so unbiased
  return "VB-" + Array.from(crypto.getRandomValues(new Uint8Array(6)), (b) => alphabet[b % 32]).join("");
}

/**
 * The reporter's confirmation. Fixed wording plus the reference and time only:
 * nothing the reporter typed goes in, so the public form can't be used to send
 * a stranger arbitrary text from videl.app.
 */
export function confirmationEmail(template, reference, now = new Date()) {
  const received = formatReceived(now);
  return {
    subject: `We received your Videl bug report (${reference})`,
    html: renderTicket(template, { REFERENCE: reference, RECEIVED_AT: received }),
    text: `We received your bug report\n\nThanks for telling us about a problem in Videl. Your report reached the team, and we'll look into it.\n\nReference: ${reference}\nReceived: ${received}\n\nIf we need more details, we'll write to this address. Forgot something, like a step or another screenshot? Reply to this email.\n\nYou're getting this because this address was entered in the Videl bug reporter. If that wasn't you, ignore this email. An address gets at most one of these a day.`,
  };
}

/** True at most once a day per address. Only a hash of the address is stored. */
export async function claimConfirmation(kv, email) {
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(email.trim().toLowerCase()));
  const key = "confirm:" + Array.from(new Uint8Array(digest), (b) => b.toString(16).padStart(2, "0")).join("");
  if (await kv.get(key)) return false;
  await kv.put(key, "1", { expirationTtl: 86400 });
  return true;
}

/** Fills {{{NAME}}} placeholders. Values are already escaped by ticketVariables. */
export function renderTicket(template, vars) {
  return template.replace(/\{\{\{(\w+)\}\}\}/g, (_, name) => vars[name] ?? "");
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
}
