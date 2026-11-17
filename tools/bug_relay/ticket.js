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

/** Fills {{{NAME}}} placeholders. Values are already escaped by ticketVariables. */
export function renderTicket(template, vars) {
  return template.replace(/\{\{\{(\w+)\}\}\}/g, (_, name) => vars[name] ?? "");
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
}
