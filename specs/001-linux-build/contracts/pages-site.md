# Contract — GitHub Pages Site (`gh-pages` branch)

Single static `index.html` on `gh-pages`. No framework, no build step. This file defines the content + link contract; visual styling is at implementer discretion as long as the contract holds.

## Required sections (in order)

1. **`<head>`** — title `Videl — Offline Media Workstation` (or current title), meta description, favicon, viewport meta for mobile, OpenGraph tags for repo URL.
2. **Hero** — product name, tagline, primary CTA region containing the two platform download buttons.
3. **Download section** — TWO buttons (see Buttons below) + supported-platforms line.
4. **Features** — list every user-facing tool/capability present on `master`. MUST include at minimum:
   - Subtitle generation (with the post-overhaul UX language)
   - Transcript
   - Media downloader (with the post-overhaul UX language)
   - Vocal isolation / AI runtime (mention on-demand install)
   - Settings persistence + history
   - EN/AR with full RTL
   - In-app tutorial
   - Bug reporter
   - Smart updater
5. **Footer** — link to GitHub repo (`https://github.com/darknessth22/media-utilities`), license, version (optional).

## Buttons (FR-009, FR-010, FR-011)

```html
<a class="btn btn-windows" href="https://github.com/darknessth22/media-utilities/releases/latest/download/Videl_Setup.exe">
  Download for Windows
</a>
<a class="btn btn-linux" href="https://github.com/darknessth22/media-utilities/releases/latest/download/Videl-x86_64.AppImage">
  Download for Linux
</a>
```

- Both buttons MUST be visible above the fold on a 1366×768 desktop viewport.
- On a 375 px-wide mobile viewport, buttons MUST stack vertically, remain tappable (≥ 44 px tall), and not require horizontal scroll.
- Visual weight MUST be roughly equal — neither platform downplayed.
- Below the buttons, a single supported-platforms line: `Windows 10+ · Linux x86_64 (Ubuntu 22.04+ / glibc 2.35+)`.

## Link verification (SC-006)

At publish time, ALL of the following MUST return HTTP 200 (or redirect chain ending in 200):

- Both download asset URLs above.
- Repo link in the footer.
- Any anchor links (`#features`, etc.) used in nav.

A `curl -ILfsS` sweep on each link is the acceptance check.

## Caching

Add `<meta http-equiv="Cache-Control" content="no-cache">` and a query-string buster on CSS/JS hrefs (e.g. `?v=2026-05-18`) to mitigate stale-`index.html` caching seen by users on every release (edge case in spec).

## Out of scope

- Analytics, telemetry, cookie banners.
- Multi-page navigation.
- Translation of the site itself (Arabic UI is inside the app, not the marketing site).
