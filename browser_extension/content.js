// Videl extension — content script.
// Watches the page for <video> elements and overlays a small
// "Download with Videl" button on the top-right of each video.
// Click → fire URL payload to the background worker, which posts
// it to the local Videl HTTP bridge.

(() => {
  const BUTTON_CLASS = "videl-download-btn";
  const WRAPPER_CLASS = "videl-btn-wrapper";
  const TAGGED_ATTR = "data-videl-tagged";

  function pickSrc(video) {
    // currentSrc is a `blob:` URL on most streaming sites (YouTube/Twitter/TikTok).
    // The Python side will reject blob:/data: — page URL is preferred there.
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
        page: location.href,
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

    return btn;
  }

  function attach(video) {
    if (video.getAttribute(TAGGED_ATTR) === "1") return;
    if (!video.isConnected) return;
    // Skip tiny or hidden videos (avatars, ad pixels).
    const r = video.getBoundingClientRect();
    if (r.width < 160 || r.height < 90) return;
    video.setAttribute(TAGGED_ATTR, "1");

    const parent = video.parentElement;
    if (!parent) return;

    // Need a positioned ancestor for the absolute-positioned overlay.
    const cs = getComputedStyle(parent);
    if (cs.position === "static") {
      parent.style.position = "relative";
    }

    const wrapper = document.createElement("div");
    wrapper.className = WRAPPER_CLASS;
    wrapper.appendChild(createButton(video));
    parent.appendChild(wrapper);
  }

  function scanAll(root) {
    const scope = root && root.querySelectorAll ? root : document;
    scope.querySelectorAll("video").forEach(attach);
  }

  // Initial scan.
  scanAll(document);

  // Watch for dynamically inserted videos (SPA navigation, lazy-load).
  const obs = new MutationObserver((muts) => {
    for (const m of muts) {
      if (m.type === "childList") {
        m.addedNodes.forEach((n) => {
          if (n.nodeType !== 1) return;
          if (n.tagName === "VIDEO") attach(n);
          else if (n.querySelectorAll) scanAll(n);
        });
      }
    }
  });
  obs.observe(document.documentElement, { childList: true, subtree: true });

  // Re-scan periodically for sites that swap <video> nodes without
  // mutating the DOM tree we observe (rare but happens on YouTube SPA).
  setInterval(() => scanAll(document), 4000);
})();
