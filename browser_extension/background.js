// Videl extension — background service worker.
// Receives video-URL payloads from content scripts and forwards them
// to the local Videl HTTP bridge running on 127.0.0.1:17654.

const VIDEL_ENDPOINT = "http://127.0.0.1:17654/url";
const VIDEL_PING = "http://127.0.0.1:17654/ping";

async function sendToVidel(payload) {
  try {
    const res = await fetch(VIDEL_ENDPOINT, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!res.ok) {
      return { ok: false, error: `HTTP ${res.status}` };
    }
    return { ok: true };
  } catch (e) {
    return { ok: false, error: String(e && e.message || e) };
  }
}

async function pingVidel() {
  try {
    const res = await fetch(VIDEL_PING, { method: "GET" });
    return res.ok;
  } catch (e) {
    return false;
  }
}

chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
  if (msg && msg.type === "videl-send") {
    sendToVidel(msg.payload).then(sendResponse);
    return true; // keep channel open for async response
  }
  if (msg && msg.type === "videl-ping") {
    pingVidel().then((ok) => sendResponse({ ok }));
    return true;
  }
  return false;
});
