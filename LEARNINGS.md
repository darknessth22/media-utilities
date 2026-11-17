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
- **Photo Restore heal = Microsoft BOPB via `zeroscratches`.** Five heuristic OpenCV attempts hit the same ceiling. Colorize = DDColor ONNX (Natural/Vivid). Faces = CodeFormer. Upscaling is deliberately left to the Upscaler tab.
- **Markdown is write-only** (an output format plus a live viewer through Qt `setMarkdown`). MD→DOCX/PDF/PPTX was built and rejected.
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
- `core/restore.py` ships its child script as a string. A test `ast.parse`s it, because syntax errors there pass every import check.
- `markdown` (PyPI) is only installed transitively. Fine for tests (`importorskip`), never for runtime code.

## Qt / GUI

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

- **Spotify on Android** mirrors the desktop (`core/downloader.py`; change the two together): `videl_dl.spotify_tracks` reads the public embed page's `__NEXT_DATA__` (single tracks also read the track page for the album name), and the app downloads each song from `ytsearch1:Artist - Title` through the normal `download()`, which unwraps the search's one-entry playlist. FFmpegKit then writes an MP3 named, tagged and given cover art from Spotify (`FfmpegRunner.toTaggedMp3`, arguments as a list so quotes in titles are safe). Spotify joins several artists with non-breaking spaces; they are normalised.
- Flutter is installed at `C:/src/flutter` but not on PATH: run `C:/src/flutter/bin/flutter analyze` in `mobile/` after Dart changes.
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
- With `wrangler.jsonc` at the repo root, `npx wrangler deploy` run from `tools/bug_relay/` still deployed the **website**, not the relay. Always deploy the relay with `-c tools/bug_relay/wrangler.toml`.
- The relay fills `ticket-email.html` itself (wrangler bundles `.html` imports as text), so every reporter value is escaped in `ticket.js` first. Email Service binding errors carry an `err.code` such as `E_RECIPIENT_NOT_ALLOWED` (destination not verified) or `E_CONTENT_TOO_LARGE` (25 MiB per message); the relay logs it and resends as plain text. Check delivery with `wrangler tail videl-bug-relay` and the inbox. The Email Routing summary in the dashboard shows Worker sends as "dropped" even when delivered.
- A Gmail **Reply** never carries the original's attachments (only Forward does), so a screenshot sent only as an attachment never reached the reporter. The relay embeds it in the email body instead (an inline attachment with `contentId`, `<img src="cid:screenshot">` inside the `SCREENSHOT` value). BMP stays a plain attachment because mail clients don't show it inline.
- **WhatsApp Desktop/Web sends a GIF file from the computer as a still image.** Not a Videl bug: the site's GIF was checked (72 frames, infinite loop, NETSCAPE2.0 block present) and plays as a GIF when sent from the phone. WhatsApp itself flattens GIFs uploaded from a computer. Workarounds: send from the phone, or attach it as a Document.
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
