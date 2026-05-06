// Videl extension — content script.
// Floats a "Download with Videl" button over every visible <video>.
// Wrapper lives on document.body with position:fixed and tracks the
// video's bounding rect each frame — sidesteps clipping / overflow /
// SPA re-renders that broke the old absolute-in-parent approach.

(() => {
  const BUTTON_CLASS = "videl-download-btn";
  const WRAPPER_CLASS = "videl-btn-wrapper";
  const VIDEO_ID_ATTR = "data-videl-id";
  let nextId = 1;

  // videoId -> { video, wrapper, lastTop, lastLeft, visible }
  const tracked = new Map();

  function pickSrc(video) {
    const cs = video.currentSrc || video.src || "";
    if (!cs) {
      const sourceEl = video.querySelector("source[src]");
      return sourceEl ? sourceEl.src : "";
    }
    return cs;
  }

  function videoTitle() {
    const og = document.querySelector('meta[property="og:title"]');
    if (og && og.content) return og.content;
    return document.title || "";
  }

  // Site-aware page URL: feed URLs (LinkedIn, FB, IG home) don't
  // identify a single video. Walk up to find the post permalink.
  function pageUrlFor(video) {
    const host = location.hostname;

if (host.includes("facebook.com")) {
      const a = video.closest('[role="article"]')?.querySelector('a[href*="/videos/"], a[href*="/reel/"], a[href*="/watch"], a[href*="/posts/"]');
      if (a) return a.href.split("?")[0];
    }

    if (host.includes("instagram.com")) {
      const a = video.closest("article")?.querySelector('a[href*="/reel/"], a[href*="/p/"]');
      if (a) return a.href;
    }

    return location.href;
  }

  function createButton(video) {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = BUTTON_CLASS;
    btn.title = "Download with Videl";
    btn.setAttribute("aria-label", "Download with Videl");
    const iconUrl = chrome.runtime.getURL("icon48.png");
    btn.innerHTML =
      '<img class="videl-icon" src="' + iconUrl + '" alt="" />' +
      '<span class="videl-label">Download with Videl</span>';

    btn.addEventListener("click", async (ev) => {
      ev.preventDefault();
      ev.stopPropagation();
      btn.classList.add("videl-busy");
      const payload = {
        page: pageUrlFor(video),
        src: pickSrc(video),
        title: videoTitle(),
      };
      try {
        const res = await chrome.runtime.sendMessage({
          type: "videl-send",
          payload,
        });
        btn.classList.remove("videl-busy");
        btn.classList.add(res && res.ok ? "videl-ok" : "videl-err");
        setTimeout(() => {
          btn.classList.remove("videl-ok", "videl-err");
        }, 1500);
      } catch (e) {
        btn.classList.remove("videl-busy");
        btn.classList.add("videl-err");
      }
    });
    // Stop site overlays (FB/IG) from swallowing the click.
    ["mousedown", "pointerdown", "touchstart"].forEach((t) => {
      btn.addEventListener(t, (e) => e.stopPropagation(), true);
    });

    return btn;
  }

  function getVideoId(video) {
    let id = video.getAttribute(VIDEO_ID_ATTR);
    if (!id) {
      id = String(nextId++);
      video.setAttribute(VIDEO_ID_ATTR, id);
    }
    return id;
  }

  function ensureTracked(video) {
    const id = getVideoId(video);
    if (tracked.has(id)) return;
    const wrapper = document.createElement("div");
    wrapper.className = WRAPPER_CLASS;
    wrapper.style.display = "none";
    wrapper.appendChild(createButton(video));
    document.body.appendChild(wrapper);
    tracked.set(id, { video, wrapper, lastTop: -1, lastLeft: -1, visible: false });
  }

  function scanAll() {
    document.querySelectorAll("video").forEach(ensureTracked);
    for (const [id, rec] of tracked) {
      if (!rec.video.isConnected) {
        rec.wrapper.remove();
        tracked.delete(id);
      }
    }
  }

  function syncPositions() {
    for (const rec of tracked.values()) {
      const r = rec.video.getBoundingClientRect();
      const visible =
        rec.video.isConnected &&
        r.width >= 160 &&
        r.height >= 90 &&
        r.bottom > 0 &&
        r.top < innerHeight &&
        r.right > 0 &&
        r.left < innerWidth;

      if (!visible) {
        if (rec.visible) {
          rec.wrapper.style.display = "none";
          rec.visible = false;
        }
        continue;
      }

      // top-right corner of video, in viewport coords.
      const top = Math.round(r.top + 10);
      const left = Math.round(r.right - 10); // right edge anchor
      if (top !== rec.lastTop || left !== rec.lastLeft) {
        rec.wrapper.style.top = top + "px";
        rec.wrapper.style.left = left + "px";
        rec.lastTop = top;
        rec.lastLeft = left;
      }
      if (!rec.visible) {
        rec.wrapper.style.display = "";
        rec.visible = true;
      }
    }
    requestAnimationFrame(syncPositions);
  }

  // Clean orphans from a previous injection (extension reload, SPA re-run).
  document.querySelectorAll("." + WRAPPER_CLASS).forEach((n) => n.remove());
  document.querySelectorAll("video[" + VIDEO_ID_ATTR + "]").forEach((v) => v.removeAttribute(VIDEO_ID_ATTR));

  scanAll();
  requestAnimationFrame(syncPositions);

  const obs = new MutationObserver(() => {
    if (obs._t) return;
    obs._t = setTimeout(() => {
      obs._t = null;
      scanAll();
    }, 200);
  });
  obs.observe(document.documentElement, { childList: true, subtree: true });

  setInterval(scanAll, 2000);
  window.addEventListener("yt-navigate-finish", scanAll);
  window.addEventListener("popstate", scanAll);
})();
