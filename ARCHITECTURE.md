# Videl Architecture

Videl is an offline desktop media workstation built on PySide6. Media work goes through bundled FFmpeg. AI tools run on optional components (PyTorch / ONNX) that are installed only when a tool first needs them. Windows is the main target; Linux ships as an AppImage. A browser extension and an Android app sit alongside the desktop app.

```
main.py  ->  MainWindow (gui/app.py)
               |-- sidebar, home grid, Ctrl+K palette  ->  26 tool sections
               |-- settings, history, how-to-use, bug reporter
               |-- background services (tray, hotkeys, bridge, watchers, updater)

gui/tabs/<tool>_section.py  --Worker (QThread)-->  core/<tool>.py
                                                     |-- FFmpeg / FFprobe (bundled)
                                                     |-- Pillow, yt-dlp (in-process)
                                                     |-- videl-pdf helper (PyMuPDF, via core/pdf_bridge.py)
                                                     |-- child process on bundled Python + AI packages
```

Related documents: [WORKFLOW.md](WORKFLOW.md) covers how changes ship, and [LEARNINGS.md](LEARNINGS.md) covers gotchas and decisions.


## 1. Layers

- **`main.py`**: the entry point. The boot order matters (section 2).
- **`gui/`**: Qt widgets only. One file per tool in `gui/tabs/<tool>_section.py`, shared widgets in `gui/widgets/`, pages in `gui/pages/`.
- **`core/`**: business logic with no Qt imports. Plain functions that take paths and settings and return results. The exceptions are Qt-bound services: `tray`, `index_watcher` and `rule_runner`.
- **`utils/`**: plumbing. FFmpeg location, user-data paths, logging, AI package installs, yt-dlp and Deno provisioning, the process registry, temp-file cleanup.
- **`videl_pro/`** (private, not in this repo): the Pro tools, open core style. Transcript, Vocal Isolator, AI Upscaler, AI Video Upscaler, Photo Restore, Jump-Cutter and Folder Rules live here, each as `<tool>.py` plus `<tool>_section.py`, with their tests in `videl_pro/tests/`. It is its own git repo (`videl-pro`), checked out into this folder and git-ignored. `core/edition.py` sets `HAS_PRO` when it is present; `gui/app.py` marks those sections `"pro": True` and drops them when it is not, so the public repo builds a free-only Videl. Release builds check it out with the `VIDEL_PRO_TOKEN` secret. Public code must never import `videl_pro` except behind `HAS_PRO`.
- **`locales/`**: `en.json` and `ar.json` hold every visible string, looked up with `tr("key")`.
- **`manifests/`**: pinned pip lists for each on-demand AI component (`<component>.txt` and `<component>.cuda.txt`).
- **`tools/bug_relay/`**: the Cloudflare Worker that receives bug reports (section 6).

Known exception: Compress, Merge and GIF build their FFmpeg commands inside the GUI section instead of a `core/` module.


## 2. Startup sequence

`main.py` runs these steps in order:

1. Replace the null stdout/stderr of the windowed PyInstaller build, and point `faulthandler` at a log file.
2. Load `.env` from next to the executable.
3. `model_manager.reconcile_on_launch()` repairs interrupted AI installs, then puts `ai_packages/` on `sys.path`.
4. Activate the user-updated yt-dlp and the Deno runtime (the YouTube JS challenge solver). This must happen before anything imports `yt_dlp`.
5. Take the single-instance mutex `Local\VidelAppMutex` (dev runs use a separate name).
6. Load settings, set the language and RTL direction, apply the theme. On a first run only (`settings.seen_version` empty) show the splash screen.
7. "Get Started", or straight away after the first run, creates `MainWindow`. It records `seen_version` and, after an update, shows that version's notes once. The notes for every release live in `assets/changelog.json` (`core/changelog.py`), listed in Settings, What's new (`gui/widgets/whats_new_card.py`), also reachable from the title-bar menu. Then it starts these in the background: the FFmpeg dependency check, the update check, and Deno provisioning plus a stale-yt-dlp refresh.


## 3. Main window

- `_SECTIONS_META` in `gui/app.py` is the one list of sections. Each entry has an id, a widget class (`cls`), a label key, an icon, sub-tab keys and an optional primary action.
- `MainWindow._make_section()` builds every widget from that list. The content stack, `_section_widgets`, operation-section wiring (entries with an `action_key`) and retranslation all follow it, so there's nothing to keep in sync.
- Navigation always goes by id: `_section_index("history")`, never a literal index.
- The home page lists only the order of its cards (`_TOOL_ORDER`). It reads each card's icon and section index from `_SECTIONS_META`, and its labels from `tool_<id>_name` / `tool_<id>_desc`.
- A tool can be opened from the sidebar, the home grid, the Ctrl+K command palette, a keyboard shortcut, drag-and-drop, or the browser extension.
- Drag-and-drop: inside a tool, `dropEvent` gives the files to that tool (`_load_into`, through `populate_batch_files` / `populate_files` / `populate_file`). On Home or the Tools page, it shows `DropSuggestions` on Home instead: the file and a button for every tool that takes it, from `core/drop_suggest.py` (each tool's accepted extensions, most useful first; several files only offer tools in `MULTI`). A click opens that tool with the files loaded (`_open_with_tool`).
- Every tool section provides `trigger_primary_action()`, `populate_files(paths)`, `retranslate_ui()` and the signals `status_message` and `busy_changed`.


## 4. How a tool runs

```
user clicks the primary action
  -> Section.trigger_primary_action()
       reads its widgets into a settings object
       -> Worker(core.fn, *args)                  gui/worker.py, a QThread
            progress(done, total, msg)  -> progress bar
            result(obj)                 -> output shown, History entry written
            error((type, value, tb))    -> status bar and crash log
```

- FFmpeg and yt-dlp subprocesses are registered in `utils/process_registry.py`, so Cancel and app exit can kill them. `utils/tmp_janitor.py` removes intermediate files.
- `utils/ffmpeg.detect_hw_encoders()` reports NVIDIA / AMD / Intel hardware encoders. NVENC failures retry once, then fall back to libx264.
- `core/history/` stores a `HistoryItem` for every finished job, tagged with its `task_type`.
- `core/crash_log.py` captures stderr from failed subprocesses. The Developer Console (`gui/crash_log_dialog.py`) shows them.


## 5. AI components

Heavy AI libraries are not in the installer. They're installed per user, the first time a tool needs them:

```
section shows an "Install" banner
  -> utils/model_manager.start_install(id)
       -> QProcess: runtime/python/python.exe -m utils.install_runner
            1. resumable pre-download of large wheels   (utils/wheel_prefetch.py)
            2. pip install --target %LOCALAPPDATA%\Videl\ai_packages\<id>
               using the pinned manifest, with --no-deps
```

Components (size on CPU / CUDA, what each needs first, which tools use it):

- **`torch_runtime`**: 600 MB / 3 GB. The shared PyTorch every torch-based component uses.
- **`bg_eraser`**: 200 MB. Used by BG Eraser (rembg on ONNX, plus BiRefNet, SAM and LaMa models).
- **`vocal_isolator`**: 50 MB, needs `torch_runtime`. Used by Vocal Isolator (HTDemucs).
- **`upscaler`**: 180 MB, needs `torch_runtime`. Used by the Image and Video Upscalers (Real-ESRGAN).
- **`photo_restore`**: 350 MB, needs `torch_runtime` and `upscaler`. Used by Photo Restore (BOPB heal, DDColor, RestoreFormer++ faces; the RestoreFormer++ arch is vendored in `videl_pro/vendor/` and loaded by path in the child process).
- **`ocr_rapid`** (120 MB) and **`ocr_easy`** (300 MB, needs `torch_runtime`): used by PDF OCR and the Text Extractor.

How the torch-based tools run (upscaler, vocal isolator, photo restore): torch never loads into the GUI process. The core module starts a child script on the bundled Python, with `sys.path` ordered component, then dependency, then `torch_runtime`. The child reports `STAGE n/total label` on stderr, and the parent turns that into progress. Models are loaded one at a time and freed between stages, so 8 GB GPUs cope.

Not installed through pip: Transcript downloads whisper.cpp binaries and GGUF models straight into `user_data_dir()`. Model weights generally download on first use.

Settings > Storage (`core/storage.py`) lists everything that has been downloaded and removes it, together with anything that depends on it.


## 6. Background services and integrations

- **Tray** (`core/tray.py`): close-to-tray, plus a notification when a background job finishes.
- **Global hotkeys** (`core/hotkey.py`, `core/keybinds.py`): Windows `RegisterHotKey`, so shortcuts work while the window is minimised. All 20 shortcuts are declared in one registry and can be rebound in Settings.
- **Browser bridge** (`core/extension_bridge.py`): an HTTP server on 127.0.0.1:17654. `POST /url` fills in the Downloader and brings the window to the front. Browsers may call it only from the extension origins and `https://app.videl.app` (`ALLOWED_WEB_ORIGINS`), the web app's Downloader page.
- **File search** (`core/file_search.py`, `file_index.py`, `index_watcher.py`): queries the Windows Search index, plus Videl's own SQLite index of the other drives, which a folder watcher keeps up to date.
- **License and the free allowance** (Pro, official builds only):
  - `videl_pro/license.py` checks the license file fully offline: an Ed25519 JWT verified against `PUBLIC_KEYS` by `kid`, bound to `device.device_id()` (8 characters from MachineGuid or /etc/machine-id), with 3 days of grace on paid-until, 7 on check-in-by, and a clock-rollback check. Files live in the config folder: `license.jwt`, `license_state.json`, `quota.json`.
  - `videl_pro/quota.py` is the gate: each Pro tool's core function calls `quota.start_job()` once, before it starts. Without a license that allows 3 runs a day and the per-tool limits, and raises `ProRequired` otherwise; `pro_ui.handle_pro_error` turns it into a "Get Pro" prompt.
  - Free tools reach the same gate through `core.edition.pro_gate()`, a no-op in builds without `videl_pro`: a batch of more than one file in `scrub_batch`, `watermark_batch`, `image_editor.process_batch` and the image batch convert (one run, up to 10 files), and the Pro-only 16-bit TIFF (`grab_frame`) and large background models (`bg_eraser.PRO_MODELS`). Their sections pass Worker errors to `gui.worker.pro_error_handled`. Sections marked `"batch": True` show the free-runs chip.
  - `videl_pro/license_client.py` talks to the license server (`https://license.videl.app`, the private `videl-license` Worker). A background thread at startup, and again every hour while the app is open, polls a pending order and checks in at most every 6 hours, so a revoke or renewal lands within hours.
  - `videl_pro/license_card.py` is Settings, License: trial, buying by manual payment, the license key for a second device, devices with Release, and the offline device code and file import. The header chip on a Pro tool (`MainWindow.refresh_pro_chip`) shows the free runs left and opens it.
- **Folder rules** (`videl_pro/folder_rules.py`, `rule_runner.py`; Pro): if-this-then-that rules for folders. Off by default; deletes go to the Recycle Bin; actions are logged and can be undone.
- **Screen tools** (`core/window_tools.py`, `core/screen_ocr.py`, `gui/widgets/screen_zoom.py`, `gui/widgets/region_selector.py`): Always On Top, Text Extractor, Zoom & Draw, and the screen colour picker.
- **Wallpaper scheduler** (`core/wallpaper_scheduler.py`): applies saved multi-monitor wallpaper setups on a schedule.
- **Updater** (`core/updater.py`): see section 8.
- **yt-dlp updater** (`utils/ytdlp_updater.py`): updates yt-dlp without rebuilding Videl. The new version takes effect on the next launch.
- **Bug reporter** (`gui/tabs/bug_reporter.py`, the same form in the mobile app, and the web app's `#/report` page in `web/js/report.js`, also linked from any failed tool): sends a JSON report to the Cloudflare Worker in `tools/bug_relay/`. The Worker emails it to `videl.support@gmail.com` from `bugs@videl.app` through Cloudflare Email Service (a `send_email` binding locked to that one inbox), filling the designed template `tools/bug_relay/ticket-email.html` (plain text if that send fails). The screenshot can be a file or pasted from the clipboard (desktop and web; an oversized paste is saved as JPEG to stay under 5 MB). The reporter's address goes in Reply-To. Each report's size is capped, and at most 5 reports per minute per IP are accepted. Each report gets a reference like `VB-7K2Q9D`. A reporter who gave an address also gets a fixed-wording confirmation with that reference, sent through Resend (Cloudflare's free plan can't mail arbitrary addresses), at most once a day per address (KV namespace `CONFIRMATIONS`, hashed keys). The only key, `RESEND_API_KEY`, is a Worker secret; nothing secret ships inside the app.


## 7. Tool catalog

Each section id is followed by the `core/` module that does its work.

**Download**
- `download`: `downloader`. yt-dlp; Spotify through its public embed page plus a YouTube match; `interceptor` for HLS on JavaScript-rendered sites.

**Video and audio**
- `convert`: `converter`
- `trim`: `trimmer`
- `gif`, `compress`, `merge`: logic in the GUI section (see Layers)
- `spatial`: `spatial`
- `mux`: `muxer`
- `chunk`: `chunker`
- `jumpcut`: `jumpcutter`
- `subtitles`: `subtitles`
- `frame_grabber`: `frame_grabber`
- `scrub`: `scrubber`
- `watermark`: `watermarker`

**Documents**
- `document`: `document`. Converts between PDF, DOCX, PPTX and Markdown; PDF to PPTX keeps text editable.
- `pdf_toolkit`: `pdf_toolkit` and `ocr`
- **PDF work runs in a separate program, `videl-pdf`** (`pdf_helper.py`, built as a second exe by `media_util_gui.spec`). PyMuPDF is AGPL, so Videl itself never imports it: the GUI calls `core/pdf_bridge.py`, which sends one JSON request to the helper and reads one JSON reply. `core/document.py` and `core/pdf_toolkit.py` only ever run inside the helper. PDF OCR is split: the helper renders pages and builds the searchable PDF, while Videl runs the OCR engines. `tests/unit/test_pdf_bridge.py` fails if anything in the app loads `fitz`.

**Image**
- `palette`: `palette_extractor`
- `image_editor`: `image_editor` and the `wallpaper_*` modules
- `pixel_art`: `pixel_art`

**AI**
- `bg_eraser`: `bg_eraser`
- `vocal_isolator`: `vocal_isolator`
- `upscaler`: `upscaler`
- `video_upscaler`: `video_upscaler`
- `photo_restore`: `restore`
- `transcript`: `transcript` (whisper.cpp)

**Automation**
- `folder_rules`: `folder_rules` and `rule_runner`

**App pages**
- `history`, `settings` (including Storage and Shortcuts), `tutorial`, `bug_reporter`


## 8. Updates and distribution

```
git tag vX.Y.Z  ->  build.yml
                      Windows: PyInstaller -> Inno Setup -> Videl_Setup.exe
                               + file manifest and blobs (rolling files-store releases)
                               + Ed25519 signature -> GitHub Release
                      Linux:   AppImage + signature -> same release
                 ->  android.yml: Flutter APK
```

On launch, `core/updater.py` checks GitHub Releases (3 second timeout). If a newer version exists:

- **Windows**: download the signed file manifest, hash the installed files, download only the files that changed, stage them, exit, robocopy-merge them in, and relaunch. Any failure falls back to the full installer.
- **Linux**: verify the signature, replace the AppImage in place, and run the new one.

The public signing key is in `core/_signing.py`. The download website is the `gh-pages` branch.


## 9. Where things live on disk

- **Settings** (`config.json`, schema-versioned): `%APPDATA%\media-utilities` on Windows, a legacy name kept so existing installs keep working; `~/.config/Videl` on Linux.
- **Presets, wallpaper setups, rules**: `%APPDATA%\Videl` on Windows, `~/.config/Videl` on Linux.
- **AI packages, whisper binaries and models, caches**: `%LOCALAPPDATA%\Videl` on Windows, `~/.local/share/Videl` on Linux.
- **Logs**: `media-utilities/logs/` (`utils/app_logger.py`, which masks secrets).
- **Bundled Python for AI installs**: `<install>\runtime\python\`, or inside the AppImage on Linux.

All path lookups go through `utils/paths.py` and `core/paths.resource_path()`.


## 10. Cross-cutting concerns

- **Language**: `core/i18n.py` is a singleton exposing `tr()`. Arabic switches the layout to right-to-left (`ThemeManager.set_rtl`), and every section re-reads its strings in `retranslate_ui()`. Paths and numbers inside Arabic text are direction-isolated.
- **Theme**: `gui/theme.py` holds the light and dark QSS and forces the Fusion style, so the app looks the same on every OS.
- **Tutorial**: `gui/tabs/tutorial_section.py` keeps parallel English and Arabic lists with one entry per tool.


## 11. Companion projects

- **Browser extension** (`browser_extension/`, Manifest V3): adds "Download with Videl" to `<video>` elements and posts the URL to the local bridge.
- **Android app** (`mobile/`, Flutter, package `videl_mobile`): downloader with time-range trim and preview, convert, extract audio, history, self-update, bug reporter. Its version is tracked separately in `pubspec.yaml`.
- **License server** (private repo `videl-license`, kept next to this one): Cloudflare Worker + D1 at `https://license.videl.app`. Orders, the admin page behind Cloudflare Access, trials, check-ins and devices. See its README.
- **Bug relay** (`tools/bug_relay/`): Cloudflare Worker `videl-bug-relay` at `https://videl-bug-relay.mostafafares080.workers.dev/report`.
- **Website** (`gh-pages` branch, live at `https://videl.app` through the Worker `videl-site`): download links point at `/releases/latest/download/<asset>`.
- **Web app** (`web/`): a browser-only version of the basic tools, live at `https://app.videl.app` (the old `https://videl-web.mostafafares080.workers.dev` still works). Every tool also has a search page such as `/compress-video`, generated by `tools/web_tool_pages.py`, plus pages that open a tool with preset settings for common searches (`/video-to-mp3`, `/webp-to-jpg`). It's plain HTML, CSS and ES modules, with no framework and no build step.
  - Video tools run ffmpeg.wasm (single-threaded, so no COOP/COEP headers). The 31 MB core comes from jsDelivr on first use; the `@ffmpeg/ffmpeg` wrapper is kept in `web/vendor/`, because its worker must be same-origin.
  - PDF tools use pdf-lib and pdf.js. Image tools use canvas. ZIP output uses fflate.
  - Each tool is one declarative entry in `web/js/tools/*.js` (fields, accept, `run()`). A choice field can add `custom` (`min`, `max`, `unit`, `whole`, or `ratio` for shapes like 3:2), which adds a "Custom" choice with a typed value checked by `customValue` in `workspace.js`; out-of-range values disable the run button with a message. Every slider also has a box for an exact value. `web/js/workspace.js` renders the files, preview, trim timeline, settings, progress and results for every tool.
  - Each tool's colour and its "takes / gives" lines live in `META` in `web/js/tools/index.js`. The colours match the desktop `_TOOL_COLOR`, so a tool looks the same in both apps.
  - Pages: Home (`#/`: big animated logo, file drop with tool suggestions, "Most used" tools counted on the device in `localStorage` key `videl.usage`, falling back to defaults), Tools (`#/tools`: category tabs, search across every tool, press `/` to jump to it, colour-coded tiles) and each tool (`#/tool/<id>`). The layout is fluid up to 2400px, and the tool grid uses `auto-fill`, so it adds columns as the window grows. Every workspace shows a three-step guide (add files, choose settings, save the result).
  - Remove background runs ISNet (int8, 46 MB, Apache-2.0) on ONNX Runtime Web 1.20.1 with multi-threaded WebAssembly. The model is the desktop app's `isnet-general-use`, at 99.5-100% mask agreement. It is stored as two parts under 25 MiB in `web/models/`, joined in `engines.js`. Masks are cached per file, so setting changes only re-composite.
  - `web/_headers` sends COOP `same-origin` and COEP `credentialless`, which make the page cross-origin isolated so WebAssembly can use threads.
  - The Downloader page (`renderHandoff` in `web/js/main.js`) downloads nothing itself: it posts the pasted link to the desktop app's browser bridge on 127.0.0.1:17654, or on phones points to the Android app. A download server was tested and rejected (see `specs/002-downloader-server/spec.md`).
