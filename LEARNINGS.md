# Videl — Learnings & Decisions

Hard-won facts that are **not obvious from the code**. Read the section for the area you are touching before changing it.
Related documents: [ARCHITECTURE.md](ARCHITECTURE.md) covers how Videl works, and [WORKFLOW.md](WORKFLOW.md) covers how changes ship.

**Keeping it current:** when a bug teaches something a future change could trip over, or a decision is made with a reason, add one bullet in the right section, in the same commit. Overwrite a bullet when it stops being true, rather than appending a contradiction.

---

## Decisions (and why)

- **All features free, no licence or trial.** Removed 2026-05-10 (`core/license.py`, pro gate, keygen tools). Don't reintroduce gating unless asked.
- **Bug reports go through a Cloudflare Worker relay** (`tools/bug_relay/`, 2026-11-16). The SendGrid key used to be baked into every installer and APK, where anyone could extract it. The relay holds all delivery keys as Worker secrets, only reaches the support inbox (the reporter goes in Reply-To, because sending them a copy would make it an open relay), and rate-limits by IP. Never put a mail-service or any other third-party key back into the app or the build.
- **Delivery is Cloudflare Email Service** (since 2026-11-17, when the domain `videl.app` arrived). Before that: SendGrid ended its free plan (every send failed with 401 "Maximum credits exceeded", so the bug reporter was silently broken from about June 2026), then Resend, whose free tier allowed 100 emails a day and only to the owner's address. Cloudflare sends to a **verified destination address** for free on every plan, outside any quota, with no API key. Sending to arbitrary recipients would need Workers Paid ($5 a month), so the reporter's confirmation goes through Resend's free tier instead (videl.app verified there, 100 a day). User decision 2026-11-17.
- **Installer and update signing kept** (Ed25519). Public key in `core/_signing.py`, private key in CI secret `VIDEL_PRIV_KEY_PEM`. Protects against a compromised release pipeline.
- **Delta updates** use content-addressed blobs sharded across 16 rolling releases `files-store-0..f` (GitHub caps a release at 1000 assets; a build has ~2400 blobs). The shard releases are `--prerelease --latest=false`. 0-byte files get no blob (GitHub rejects empty assets). The apply step uses robocopy merge, **never `/MIR`**, and relaunches via `explorer.exe` to drop elevation. Linux stays a full AppImage download.
- **yt-dlp updates independently of Videl.** It's installed to `%LOCALAPPDATA%/Videl/ytdlp` from the **GitHub master tarball** with `--force-reinstall` (PyPI stable lags extractor fixes by weeks), plus `curl_cffi`. `activate_user_ytdlp()` must run before any `import yt_dlp`.
- **Transcript = upstream whisper.cpp prebuilt binaries** from `ggml-org/whisper.cpp` releases. Rejected: `pywhispercpp` (CPU-only wheels) and `faster-whisper` (the user's call). Asset names change between releases, so verify them through the GitHub API when bumping `_WHISPER_VERSION`.
- **Photo Restore heal = Microsoft BOPB via `zeroscratches`.** Five heuristic OpenCV attempts hit the same ceiling. Colorize = DDColor ONNX (Natural/Vivid). Faces = RestoreFormer++. Upscaling is deliberately left to the Upscaler tab.
- **Photo Restore faces = RestoreFormer++ (2026-11-25), not CodeFormer.** CodeFormer's S-Lab licence is non-commercial. In a side-by-side test on old photos RestoreFormer++ was as sharp, faster (8.7 s vs 14.4 s on GPU) and more faithful (CodeFormer invented glasses on a face). GFPGAN v1.4 was also tested and is softer. The RestoreFormer++ checkpoint is Lightning format: take the `state_dict` keys under `vqvae.` and load with `strict=True`. It has no fidelity input, so the slider blends the original face back in. The old CodeFormer code fed BGR crops to an RGB model (purple lips): convert facexlib crops to RGB first.
- **PyMuPDF stays despite AGPL** (2026-11-25, the user's call on quality). Replacing it would need pypdf + pypdfium2 + pdfplumber, with slower, weaker layout extraction for PDF→DOCX. It blocks a closed Pro module in the same app.
- **Markdown is write-only** (an output format plus a live viewer through Qt `setMarkdown`). MD→DOCX/PDF/PPTX was built and rejected.
- **No download server for the web app** (2026-11-18). A Hetzner server in Helsinki could download TikTok, Instagram, X, LinkedIn and Twitch, but YouTube answered every link with "Sign in to confirm you're not a bot" (IPv4 and IPv6) and Facebook demanded a login; the same links worked from home. The only fixes are cookies from accounts that get banned, home-IP proxies at 3 to 5 USD per GB, or dodging YouTube's bot check, all rejected, as is asking visitors for their cookies (a login cookie opens the whole Google or Facebook account). So the web Downloader hands links to the desktop app instead. A home laptop as the server, with daily limits, is the user's possible later option. Details and numbers: `specs/002-downloader-server/spec.md`.
- **Browser bridge accepts unauthenticated loopback POSTs.** A token was added once and reverted by the user, because the extension expects plain POST. Don't re-add one without asking.
- **Settings folder on Windows/macOS stays `media-utilities`** (`core/settings.py`). Renaming it breaks existing installs. Linux uses `Videl`.

## Removed or rejected — don't rebuild from old notes

- 2D-to-3D Deconstructor
- Lively video wallpaper
- Cutout tool (the selection belongs inside BG Eraser)
- Markdown as an input format
- OCR text layer in PDF to PPTX
- Licence / trial system
- DeOldify (needs torch < 1.4)

The user preference behind several of these: **enrich the feature that was named; don't spawn a sibling tool.**

## Build & packaging

- Bundled asset paths always go through `core.paths.resource_path(...)`. Never `os.path.dirname(__file__)` + `..`: Windows collapses `..` lexically, but Linux walks real directories, so icons vanish in the AppImage.
- Anything imported at startup must be in **both** `requirements.txt` and `requirements-build.txt`. AI libraries go in `manifests/`, never the app requirements.
- Release builds are pinned by `constraints-build.txt` (plus `python-version: "3.12.10"` for the Windows job; Linux stays on `"3.12"` because its update is a full AppImage anyway). Before this, `>=` requirements let each CI build pull the newest PySide6, PyMuPDF and Playwright, and the v5.0.8 delta update was about 740 MB of the app's 1 GB for a few MB of real changes. yt-dlp stays unpinned on purpose: it breaks often, and each release should bundle the newest.
- AI components install with `--no-deps`, so **every** transitive dependency must be listed in the manifest (e.g. `codeformer-pip` also needs `lpips` and `gdown`).
- torch lives in `ai_packages/torch_runtime/`. Child scripts must put it on `sys.path` after the component's own directory.
- The gyan.dev FFmpeg zip pinned in `build_config.json` periodically returns 404 (they keep a rolling window). Update all four fields from the `.sha256` sidecar. Don't switch to the floating URL.
- `videl_pro/restore.py` ships its child script as a string. A test `ast.parse`s it, because syntax errors there pass every import check.
- `markdown` (PyPI) is only installed transitively. Fine for tests (`importorskip`), never for runtime code.

## Qt / GUI

- **Rounded corners on frameless windows.** The main window rounds through Windows 11 itself (`_round_window_corners` in `gui/app.py`: `DwmSetWindowAttribute`, `DWMWA_WINDOW_CORNER_PREFERENCE` = `DWMWCP_ROUND`, called in every `showEvent` because Qt can recreate the native window); Windows squares the corners when maximized or snapped and adds its thin border. Painting a rounded shape on a translucent window would break snapping and the resize grip. The splash is the exception: it never resizes, so it paints its own rounded card with a soft shadow on a `WA_TranslucentBackground` window (`_RADIUS`, `_MARGIN` in `gui/pages/splash_screen.py`). Windows 10 and Linux keep square corners on the main window.
- **Home drop suggestions** (2026-11-24): dropping on Home used to jump straight to one tool picked by extension (Convert for almost everything) and never loaded the file into it. It now lists every tool that takes the file, like the web app. When a tool gains or loses a file type, update its set in `core/drop_suggest.py`, or Home will suggest it for files it refuses. Replaced buttons must be detached with `setParent(None)`, not only `deleteLater()`: until the event loop deletes them they stay in place and clickable, and a stale button opened the wrong tool.

- **Ctrl+V outside a text field never reaches the page**: the window-wide `paste_url` shortcut takes it. Pages that want a paste get it through that handler: `_paste_url_from_clipboard` calls the current page's `paste_screenshot()` if it has one (the bug reporter does). Inside a text field the field consumes Ctrl+V first, so the bug reporter catches it with an event filter, and only when the clipboard holds an image and no text, so text pasting is untouched.
- **A `QShortcut` never fires while minimised**, in any context. Anything that must work from the tray needs an OS hotkey (`core/hotkey.py`, `RegisterHotKey`).
- `RegisterHotKey` claims a combination **exclusively** across the whole OS. Global = Ctrl+Shift+B, in-app = Ctrl+B. A global hotkey must **not** restore the window.
- **Never `grabMouse()`/`grabKeyboard()` on an overlay.** The grab is system-wide; a missed release froze the whole desktop.
- `showFullScreen()` covers **one** screen. Desktop-wide overlays need `show()` + `setGeometry(union of all screens)`.
- `QKeySequence("NotAKey")` is non-empty. Validate with `Key_unknown` and an empty `toString()`.
- `SettingsSection` emits the **same** `UserSettings` object it holds, so compare derived values, not `old.x == new.x`.
- Create QTimers and state **before** widgets whose constructors emit signals (`setPlainText` emits `textChanged`).
- Wire worker cleanup to `finished`, not `result`/`error`, or an "already running" guard can stick.
- RapidOCR must be **constructed on the GUI thread** (it hangs inside a QThread). Inference from a worker is fine.
- A widget that paints its own colours must also own its background. Sections can implement `apply_theme(dark)`.
- `ColorWheelWidget.set_color()` is deliberately quiet (no signal). Callers trigger `_on_wheel_color_changed()` themselves.
- `QTextDocument.setMarkdown()` silently truncates at an unclosed void HTML tag. Pass the text through `_close_void_html()` first.
- Paint canvases store strokes in **image** coordinates, commit each stroke on release, and keep the width per stroke. Subtractive edits are painted from a **fold** of all strokes, never stroke by stroke.
- `set_image` must be idempotent: sections call it on refresh, and reloading would wipe the selection.

## Tests

- Run `python -m pytest tests`. A bare `pytest` collects the bundled `runtime/`.
- Tests that build a `MainWindow` must **close** it in teardown, or pytest hangs at exit.
- `QT_QPA_PLATFORM=offscreen` doesn't rasterise fonts and returns fake HWNDs. Rendered-text and real-window tests must skip there.
- Scrollbar and range assertions after a single `processEvents()` are racy. Drain the queue, or wait for the async retry (IndexWatcher `_unwatch` retries on a timer).
- Verify generated Markdown by **rendering** it, and generated PPTX by opening it in PowerPoint over COM (the only check that proves there's no repair prompt).

## Media, GPU & AI

- **Never `cv2.imread`/`cv2.imwrite` a user's path.** On Windows both fail silently on non-ASCII paths (Arabic file names) and give no reason when a save is refused. Read with `cv2.imdecode(np.fromfile(...))`, write with `cv2.imencode` plus Python `open()`, and print the OSError. Photo Restore and the AI Upscaler do this since 5.1.
- **Windows Controlled folder access blocks Videl's helpers.** With Defender's ransomware protection on, the bundled `python.exe` (and any unsigned exe) cannot write into Pictures, Documents or Desktop. Writes fail as EBADF or ENOENT, with Defender event 1123 in Microsoft-Windows-Windows Defender/Operational. Users fix it under Windows Security > Ransomware protection > Allow an app; code signing and reputation are the long-term fix.
- **GPU probe exit 3221225478 = a disk error, not a CUDA problem** (2026-11-24). The probe starts torch in the bundled Python; `0xC0000006` (STATUS_IN_PAGE_ERROR) means Windows couldn't read a DLL from the drive. On the maintainer's PC, `torch_cpu.dll` sat on bad blocks of the C: SSD (CRC error at about 136 MB; System log event 7 "has a bad block"), so all three torch tools fell back to CPU with the GPU greyed out. `core/gpu_probe.py` now names crashes in plain words (`last_detect_problem()` in both probe modules), and the tools show it instead of the raw code. To repair: delete `ai_packages/torch_runtime` and reinstall. The AI tool screens use `model_manager.is_ready()` (installed and every `requires` present), so a missing torch_runtime brings back the install banner; before, `is_installed()` alone kept the tool open with no way to reinstall the runtime.

- **Spotify on Android** mirrors the desktop (`core/downloader.py`; change the two together): `videl_dl.spotify_tracks` reads the public embed page's `__NEXT_DATA__` (single tracks also read the track page for the album name), and the app downloads each song from `ytsearch1:Artist - Title` through the normal `download()`, which unwraps the search's one-entry playlist. FFmpegKit then writes an MP3 named, tagged and given cover art from Spotify (`FfmpegRunner.toTaggedMp3`, arguments as a list so quotes in titles are safe). Spotify joins several artists with non-breaking spaces; they are normalised.
- Flutter is installed at `C:/src/flutter` but not on PATH: run `C:/src/flutter/bin/flutter analyze` in `mobile/` after Dart changes.
- **Android: never download a bare format id.** `download()` looks the link up a second time, and the id picked from the first list can be gone: YouTube answers through a different player client, Facebook renumbers its DASH streams. A bare id then fails with "Requested format is not available" (reported after minimising the app mid-download, 2026-11-24). `_pick` in `downloader_page.dart` asks for `id/bv*[height<=h]/b[height<=h]/bv*/b` (with sound: `id/b[height<=h]/b`, audio: `id/ba/b`), using the `height` that `list_formats` now returns. No `+` merges there: Chaquopy has no FFmpeg, the app muxes.
- **The Android app uses the web app's look** (`core/theme/videl_theme.dart`): the site's colour tokens under the old `VidelColors` names, Bricolage Grotesque headings (`videlDisplay`), Inter body text (Geist isn't in google_fonts 6.3), pill buttons, choices and tabs, and the blue and violet glow backdrop with a fading grid. Tool colours match desktop `_TOOL_COLOR` and web `META`.
- **Android downloads X/Twitter**: the app fetches video and audio in parallel and muxes them with FFmpeg (no FFmpeg inside Chaquopy). That assumed YouTube's shape. X serves video and audio both as `.mp4`, so the two parts had the same file name and collided, and most X posts have no audio-only stream at all (every MP4 already has sound, with codecs unlabelled), so `ba` failed the whole download. `videl_dl.py` now names parts `.video`/`.audio` (a file with sound keeps the plain name) and returns `""` when an audio selector finds nothing; the Dart side then keeps the video, and the MP3 path falls back to `b`. An unknown codec (`None`) counts as present; only an explicit `'none'` means absent.
- `h264_nvenc` hard-caps at **4096×4096**; use `hevc_nvenc` above that. Pick the encoder from **output** dimensions.
- Real-ESRGAN `tile=0` above ~720p spills into shared memory: 22× slower. Use `auto_tile_size()`. ×2 costs the same GPU time as ×4 (both models are native ×4).
- `detect_hw_encoders()` returns **labels** (`nvidia`/`amd`/`intel`), not encoder names.
- Drain long-running subprocess output with a reader thread + `queue.Queue`, so Cancel responds within 100 ms.
- rembg: always pass an explicit session. The default u2net is the worst. `isnet-general-use` ≈ `birefnet-general-lite` quality at ~6× the speed; `birefnet-dis` fails on people.
- SAM in rembg uses a **fixed 684×1024** preprocessing canvas. Prompt with **interior points** (a shape's centre), never rectangle corners.
- LaMa ONNX (fixed 512×512) for object removal: crop a padded square around the hole, infer, and composite only inside the mask.
- huggingface_hub `WinError 1314` is a **symlink-probe race**, not a permissions problem. Pre-fetch with `max_workers=1`.
- DDColor needs the float-Lab pipeline end to end; mixing in uint8 L gives a cyan cast. Don't `.half()` CodeFormer, because its vendored code forces fp32.

## Documents (PDF → DOCX / MD / PPTX)

- One reader per input format and one builder per output format, with `DocumentBlock` in between. Add formats as serialisers.
- PyMuPDF `get_image_bbox()` needs an entry from `get_images(full=True)`.
- python-pptx: `slide_width` is EMU (`/12700` gives points). Shape proxies are fresh objects, so compare `shape_id`, never `is`.
- Design decks (aspect ≥ 1.4 + full-bleed background) are rendered page-for-slide with text redacted and re-laid as editable boxes, one per **line**. Use `apply_redactions(graphics=0)` and remove outlined glyphs individually, because `graphics=2` eats vector art. Cap renders at the source images' native resolution and use JPEG.
- Arabic text from a PDF comes reversed and in presentation forms: NFKC, then reverse, then set `rtl=1`. Pin overlay text to Calibri.
- **Open core (decision 2026-11-25).** The Pro tools live in the private `videl_pro/` package, which is its own repo checked out inside this one and git-ignored. Public code reaches it only behind `core.edition.HAS_PRO`; a Pro section in `_SECTIONS_META` carries `"pro": True`. Settings and Tutorial have `cls: None` by design, so never filter sections on `cls`. Test both editions: `python -m pytest tests videl_pro/tests -q`, then the same `tests` run with `videl_pro/` moved aside. Code that was public under MIT before the move stays MIT in the git history; only changes made after it are private.
- **Videl never imports `fitz`.** PyMuPDF is AGPL and must stay in the `videl-pdf` helper so it does not reach the private Pro code (decision 2026-11-25). New PDF features go into `core/pdf_toolkit.py` or `core/document.py`, get an entry in `CALLS` in `pdf_helper.py`, and are called through `core/pdf_bridge.py`. JSON turns tuples into lists, so the bridge re-tuples results.
- PyMuPDF `insert_textbox()` writes nothing when the text does not fit and only returns a negative number. The searchable-PDF text layer used it with fontsize = 0.8 x box height, which never fits, so OCR'd PDFs had no text until 5.1. The layer now uses `insert_text` on the box baseline. It is Helvetica, so Arabic and CJK words in it are not searchable yet.
- Before calling something "unremovable / baked in", **render it and look at it** at high zoom. Twice it turned out to be our own leftovers or a drop shadow.

## Web app

- A `url()` inside a CSS custom property resolves against the **stylesheet that uses it**, not the page. Icons set as `--src: url(assets/...)` from JS loaded `css/assets/...` and 404'd. Build an absolute URL with `new URL(path, document.baseURI)`.
- ffmpeg.wasm's wrapper starts its worker with `new Worker(new URL("./worker.js", import.meta.url))`, so the wrapper must be served from your own origin (`web/vendor/ffmpeg/`). The core (`ffmpeg-core.js` and `.wasm`) can come from a CDN through blob URLs. The 31 MB wasm is also over the 25 MiB per-file asset limit, so it can't be self-hosted on Cloudflare anyway.
- Hash navigation goes through `document.startViewTransition`, which applies the DOM update a moment later. A test that changes the hash and waits for `.ws` can grab the **previous** tool's page. Load each test case fresh.
- The user wants the layout to **use the window**, not a fixed centred column: fluid width (max 2400px) and `auto-fill` grids. Animations must replay every time a page is shown, not only on a full reload.
- Use the **real logo image** (`web/assets/videl-logo.png`) for the brand mark. The user rejected a hand-drawn SVG approximation of the ribbon. Progress is shown by clipping the logo (`clip-path` driven by `--p`), not by redrawing it.
- Never put `filter: drop-shadow` on an element that also has a `clip-path`: the glow is clipped at the element's box and shows as a dark rectangle. Put the filter on a wrapper.
- The web app's background follows the desktop site (gh-pages): drifting blue and violet glows plus a masked grid. The glows are radial gradients moved with `transform`, not `filter: blur`, to keep paint cost low.
- Phones: nothing may scroll sideways or be cut off. The category tabs and the step pills **wrap** below 640px (no hidden horizontal scroll), so the sliding tab highlight moves on both axes (`offsetLeft` and `offsetTop`). On touch screens (`pointer: coarse`) every tap target is at least 44px.
- **The web app's `#/tool/...` routes are invisible to search engines** (everything after `#` is ignored), so the 15 tools were one page to Google. Each tool now has a real page (`/compress-video`, `/merge-pdf`, ...) from `tools/web_tool_pages.py`: `<html data-tool data-h1>` makes `main.js` open that tool with no `#` and keep the page's own `<title>`. Cloudflare serves `/compress-video` from `compress-video.html` and redirects the `.html` form. No `SoftwareApplication` structured data on purpose: without ratings Google reports it as an error. Every tool shows at its own address (`/video-to-gif`) with its own how-to; Home, Tools, the Downloader and Report a bug are `/#/...`. Links between them are swapped in place (a click handler plus `history.pushState` in `main.js`, with `renderCopy` drawing the how-to from the generated `web/js/pages.js`), because loading each tool as a new page made every move slow: about ten ES modules are re-checked one after another per load. Old addresses such as /compress-video#/tool/gif are rewritten with `replaceState`. Each page also carries its heading and intro in the raw HTML (inside `<main>`, replaced by `main.js`), because Bing and AI search crawlers mostly don't run JavaScript; before 2026-11-18 the H1 only existed after the app rendered. Preset pages (`data-preset`, read in `workspace.js`) target searches a tool already answers, such as "video to mp3" or "webp to jpg". Moving these pages to `videl.app/tools/...` with a "Use tool" button was considered and rejected: the page that ranks should be the working tool, as on iLovePDF and Smallpdf, and two pages per tool would compete.
- **Google search shows a grey globe instead of the site icon** until its separate favicon crawler visits (days to weeks after indexing), and only if the icon is square, ideally a multiple of 48 px, and declared in the home page's `<head>`. Both sites serve `/favicon.ico` (16/32/48) and `assets/favicon-192.png`; the old 1164x1167, 1.2 MB `videl_icon.png` was neither square nor small. A `WebSite` JSON-LD block with `"name": "Videl"` sets the site name Google shows, and helps against confusion with an unrelated iOS app called "Videl - AI Video Generator".
- `cloudflare/wrangler-action` installs wrangler into the checkout. With the site's assets directory set to the branch root (`"."`), the first automatic deploy tried to upload `node_modules` (workerd is 155 MiB, over the 25 MiB asset limit). The gh-pages `.assetsignore` lists `node_modules` and `package*.json` for that reason. Its "npx canceled due to missing packages" line is harmless: the action checks for wrangler before installing it.
- A request sent the moment `wrangler deploy` returns can still reach the **previous** version: two test reports went out through Resend, and a later one through the pre-fix code, right after deploys that had succeeded. Wait about 30 seconds, and confirm with `wrangler tail --format json`, whose events carry `scriptVersion.id`.
- With `wrangler.jsonc` at the repo root, `npx wrangler deploy` run from `tools/bug_relay/` still deployed the **website**, not the relay. Always deploy the relay with `-c tools/bug_relay/wrangler.toml`.
- The relay fills `ticket-email.html` itself (wrangler bundles `.html` imports as text), so every reporter value is escaped in `ticket.js` first. Email Service binding errors carry an `err.code` such as `E_RECIPIENT_NOT_ALLOWED` (destination not verified) or `E_CONTENT_TOO_LARGE` (25 MiB per message); the relay logs it and resends as plain text. Check delivery with `wrangler tail videl-bug-relay` and the inbox. The Email Routing summary in the dashboard shows Worker sends as "dropped" even when delivered.
- Email Service attachments: `content` must be **bytes**. A string is taken as the file's literal text, so the base64 screenshot first arrived as a broken image (the "PNG" was the base64 text). The relay decodes with `Uint8Array.fromBase64`. `wrangler dev` writes each simulated attachment to `.wrangler/tmp/email/`, which is how this was caught; byte-compare it with the original.
- A Gmail **Reply** never carries the original's attachments (only Forward does), so a screenshot sent only as an attachment never reached the reporter. The relay embeds it in the email body instead (an inline attachment with `contentId`, `<img src="cid:screenshot">` inside the `SCREENSHOT` value). BMP stays a plain attachment because mail clients don't show it inline.
- **WhatsApp Desktop/Web sends a GIF file from the computer as a still image.** Not a Videl bug: the site's GIF was checked (72 frames, infinite loop, NETSCAPE2.0 block present) and plays as a GIF when sent from the phone. WhatsApp itself flattens GIFs uploaded from a computer. Workarounds: send from the phone, or attach it as a Document.
- **A public site calling 127.0.0.1 needs the visitor's permission in Chrome** (Local Network Access): the first "Open in Videl" shows a prompt, and the fetch waits for the answer. The bridge also sends `Access-Control-Allow-Private-Network: true` for older Chromium. In Playwright, call `context.grant_permissions(["local-network-access"])`, or the request just fails. A Videl too old to trust the web app's origin fails the CORS check, which the page can't tell apart from Videl not running, so one message covers both.
- **Split video (web) mirrors the desktop Auto-Chunker but checks its work.** The segment muxer writes `part%03d.ext`, so `runFFmpeg` returns every file matching a `%` output (via `ffmpeg.listDir`). Splitting by size estimates each part's length from the average bitrate, then splits again with shorter parts (up to 3 tries) if a part is still over the limit; the desktop only estimates. Sizes are decimal MB, so parts also fit limits counted in MiB. Rotate, crop, resize (the desktop's Transform) uses FFmpeg expressions (`crop` to the ratio from the centre, `scale` on the shorter side with `-2`, never enlarging), so it works without knowing the video's size in advance.
- **Custom sizes must stay even for H.264.** A typed size such as 541p is rounded down with `trunc(x/2)*2` in Compress and in Rotate, crop, resize, and a custom rotate angle (FFmpeg `rotate` with `rotw`/`roth`, black corners) is followed by an even-size `scale`; 90, 180 and 270 still use `transpose`/flips, which lose nothing.
- `h()` in `web/js/ui.js` flattens children only one level. An array inside an array renders as "[object HTMLParagraphElement]"; spread inner lists.
- `wrangler pages project create` now deploys to **Workers static assets** and writes a `wrangler.jsonc` named after the folder. Rename it to the real project (`videl-web`), or the next `wrangler deploy` creates a second site.

## Background remover (web)

- ISNet int8 (46 MB) matches the desktop fp32 model at IoU 0.995-1.0, and fp16 (88 MB) at 1.0. int8 is the default: half the download for no visible difference. The browser pipeline matched the Python reference at IoU 0.9994.
- Run it on **multi-threaded WASM, not WebGPU**. The dynamic-int8 ops aren't supported on WebGPU, which measured no faster. Threads need cross-origin isolation: single-threaded was 7.5 s per image, 4 threads 2.0 s.
- Use COEP `credentialless`, not `require-corp`. It keeps Google Fonts and the jsDelivr FFmpeg core loading without CORP headers. Safari ignores it and simply runs single-threaded.
- Cloudflare static assets are capped at 25 MiB per file, so the model ships as `isnet-q8.part0` + `part1` and is joined in the browser. R2 wasn't needed (it isn't enabled on the account yet).
- ONNX Runtime prints "Removing initializer" warnings for this model. Silence them with session option `logSeverityLevel: 3`; `env.logLevel` alone doesn't cover session creation.

## Platform & integrations

- Windows Search over ADO (`Search.CollatorDSO`) has no parameter binding (escape terms inline) and no `COUNT(*)`. It covers only indexed drives, usually just C:.
- Deleted folders still being watched sit in a "delete pending" state: `isdir()` returns True while listing them fails. IndexWatcher probes with `scandir`.
- Folder Rules deletes go through `SHFileOperationW` to the Recycle Bin. EXIF stripping writes to a temp file and swaps, so a failed save never truncates the original.
- The Workers rate-limit binding is approximate: per data centre and eventually consistent. A 20-request burst against a 5-per-minute limit got about 1 in 4 blocked after roughly 10 requests. Treat it as a damper, not a hard cap.
- Spotify: scrape the public embed page's `__NEXT_DATA__`, then search YouTube. No API key is used.
- Writing non-ASCII into locale JSON through a shell heredoc corrupts it (the console is cp1252). Use `\u` escapes, and verify by codepoint.
