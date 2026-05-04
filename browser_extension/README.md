# Videl Browser Extension

Adds a "Download with Videl" button over every `<video>` on the web. Click → URL is pushed to the local Videl desktop app, which jumps to the Downloader tab pre-populated with the link.

## How it works

1. A content script watches the page and overlays a small pill button on every visible `<video>`.
2. On click, the background service worker `POST`s `{page, src, title}` to `http://127.0.0.1:17654/url` — the local HTTP bridge inside the Videl desktop app.
3. Videl raises its window, navigates to the Downloader tab, and fills in the URL.

The bridge is loopback-only — it never accepts traffic from outside `127.0.0.1`.

## Install (unpacked, dev)

### Chrome / Edge / Brave
1. Open `chrome://extensions` (or `edge://extensions`).
2. Toggle **Developer mode** on.
3. Click **Load unpacked** and select this `browser_extension/` folder.

### Firefox (temporary)
1. Open `about:debugging#/runtime/this-firefox`.
2. Click **Load Temporary Add-on**.
3. Pick `manifest.json` inside this folder.
   *(Firefox MV3 support varies; for full Firefox compatibility a small manifest tweak may be needed.)*

## Usage

1. Make sure the Videl desktop app is running.
2. Visit any page with a video. A "Videl" button appears in the top-right of the player.
3. Click it. Videl pops to the front with the URL pre-loaded — pick quality, hit Download.

## Notes

- Page URL is preferred over `currentSrc` because most streaming sites (YouTube, Twitter, TikTok) use `blob:` URLs that yt-dlp can't read. yt-dlp's extractors operate on page URLs.
- The button is hidden for videos smaller than 160×90 (avatars, ad pixels, autoplay teasers).
- Icons (`icon16.png`, `icon48.png`, `icon128.png`) need to be added before publishing — copy the Videl logo at the matching sizes.
