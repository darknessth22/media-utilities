# Videl Development Workflow

How a change goes from idea to a release users get prompted to install. This describes what the repo and CI actually do today.

```
plan -> build -> definition of done -> test -> commit -> release -> CI -> users updated
```

Related documents: [ARCHITECTURE.md](ARCHITECTURE.md) covers how Videl works, and [LEARNINGS.md](LEARNINGS.md) covers gotchas and decisions.


## 1. Plan

- **Bug fix or small tweak**: go straight to building.
- **New tool or large feature**: use Spec Kit: `/speckit.specify`, `/speckit.clarify`, `/speckit.plan`, `/speckit.tasks`, then implement. The output lives in `specs/<NNN-feature>/`.
- When working from `specs/<feature>/tasks.md`, tick each task as it's finished, not at the end of a phase.


## 2. Build

**Branching**
- Work on `master` directly, or on `feature/<name>` / `fix/<name>` and merge into `master`.
- The old branches `phase1/security-stability` and `001-linux-build` are fully merged and stale.

**Layering**
- `core/<tool>.py` holds business logic with no Qt imports.
- `gui/tabs/<tool>_section.py` holds the Qt section for that tool.
- Long work runs on the background `Worker` (`gui/worker.py`). Never block the GUI thread.
- Heavy AI libraries are on-demand components in `manifests/`, never app requirements.
- Anything imported at startup goes in both `requirements.txt` and `requirements-build.txt`.
- A new build dependency also gets an exact `==` line in `constraints-build.txt`, using the version you tested with. Release builds install with `-c constraints-build.txt`, so an unpinned package floats to the newest version on every build.
- Upgrading a library is a deliberate change: bump its line in `constraints-build.txt` (PySide6 also pins its Addons, Essentials and shiboken6 packages to the same version), build, test, release. Expect that release's Windows delta update to be large.

**Adding a tool tab**
1. `gui/app.py`: import the class and add one `_SECTIONS_META` entry, including `cls`. The window builds everything else from it.
2. Navigate by id only: `_section_index("<id>")`.
3. `gui/pages/home_page.py`: add the id to `_TOOL_ORDER`, plus a colour in `_TOOL_COLOR` and a category in `_TOOL_CATEGORY`.
4. Add `assets/icons/<name>.svg`, using `currentColor`.


## 3. Definition of done

A change is done when every item that applies is true:

- [ ] Every new or changed UI string is in both `locales/en.json` and `locales/ar.json`.
- [ ] A user-facing feature has steps in `gui/tabs/tutorial_section.py`, in both `_TUTORIAL_DATA_EN` and `_TUTORIAL_DATA_AR`.
- [ ] `README.md` is updated if the feature list or requirements changed.
- [ ] New runtime files, dynamic imports or binaries are in `media_util_gui.spec`, and files opened by path use `resource_path`.
- [ ] New core logic has a test in `tests/unit/`.
- [ ] Anything non-obvious you learned is a bullet in `LEARNINGS.md`; structural changes are reflected in `ARCHITECTURE.md`.
- [ ] If the apps or the sites now contact a new service, or bug reports carry or keep new data, `privacy.html` on gh-pages (https://videl.app/privacy) says so, with a new "Last updated" date. It lists every connection Videl makes; a stale line there is a broken promise.
- [ ] You ran it for real with `python main.py`.


## 4. Test

```bash
python -m pytest tests -q
```

- Run it on `tests/`. A bare `pytest` also collects the bundled `runtime/python/` and errors out.
- Expected skips: the live-browser tests (they need `LIVE_TEST=1`), the offscreen window tests, and the global-hotkey test while Videl is running.
- Mobile code: `cd mobile && dart analyze`.


## 5. Commit

- Conventional Commits (`feat:`, `fix:`, `refactor:`, `docs:`, `chore:`), with the subject at most 72 characters.
- The body explains why, and records root causes and measurements. The commit log is the project's history.
- No `Co-Authored-By` trailers.
- Commit only when the maintainer asks. Pushing is a separate, explicit decision.


## 6. Release

**Choosing the version.** Edit `VERSION` in `core/version.py`, following semver and classifying conservatively:

- **Patch** (`X.Y.Z+1`): bug fixes, including things that should have worked all along. The default when unsure.
- **Minor** (`X.Y+1.0`): a genuinely new user-facing feature or tool tab.
- **Major** (`X+1.0.0`): a breaking change, a rewrite, or a deliberate reset.

A new version must sort higher than every existing tag, or the in-app updater won't offer it.

**Commands**

```bash
# 1. bump core/version.py and commit it on its own
git add core/version.py
git commit -m "chore: bump version to X.Y.Z"

# 2. tag: this is what triggers the release build
git tag vX.Y.Z

# 3. push the branch and the tag
git push origin master
git push origin vX.Y.Z
```

**Mobile-only release**: bump `version:` in `mobile/pubspec.yaml` and tag `android-vX.Y.Z`. That builds Android only.


## 7. CI (GitHub Actions)

- **`ci.yml`**: runs on any push, on pull requests into `master`, and manually. Runs `pytest` on Windows.
- **`build.yml`**: runs on `v*` tags and manually.
  - **Windows job**: PyInstaller and Inno Setup produce `Videl_Setup.exe`, plus the delta-update manifest and blobs, a size check comparing a clean venv against an AI-polluted one, an Ed25519 signature, and the GitHub Release.
  - **Linux job**: runs in parallel with no dependency on the Windows job. Builds a signed AppImage into the same release.
- **`android.yml`**: runs on `v*` and `android-*` tags and manually. Builds the Flutter APK from `mobile/`.
- **Secrets**: `VIDEL_PRIV_KEY_PEM` (signing). The public key is in `core/_signing.py`. No mail-service key is used in builds any more.


## 8. Bug relay (Cloudflare Worker)

The relay is deployed separately from app releases. The code is in `tools/bug_relay/`. Cloudflare credentials are in `C:\Users\dark\.cloudflare\videl.env`, outside the repo.

```bash
# from the repo root; always name the config (see LEARNINGS.md, Web app)
set -a; . ~/.cloudflare/videl.env; set +a                      # loads CLOUDFLARE_API_TOKEN
node tools/bug_relay/worker.test.mjs                           # report parsing check
npx wrangler deploy -c tools/bug_relay/wrangler.toml           # after editing worker.js or ticket-email.html
```

The web app's "Report a bug" page (`web/js/report.js`) posts to the same relay from the browser. The relay only answers browsers from the origins in `WEB_ORIGINS` in `worker.js`. **If the web app gets another address, add it there and redeploy the relay**, or web reports fail.

Changing the relay doesn't need an app release, as long as the request format (`subject`, `body`, `reporter_email`, `screenshot`) stays the same.

Mail goes out through Cloudflare Email Service: the `send_email` binding in `tools/bug_relay/wrangler.toml` can only deliver to `videl.support@gmail.com`, which is a verified Email Routing destination address (free, no quota). `videl.app` has Email Routing enabled, which is what lets the relay send from `bugs@videl.app`. If the support inbox ever changes, add and verify the new address (`npx wrangler email routing addresses create <address>`, then click the link it sends) and update both `destination_address` and `SUPPORT` in `worker.js`.

The email layout is `tools/bug_relay/ticket-email.html`, bundled into the Worker: edit it and redeploy the relay. Its placeholders are `{{{BUG_TYPE}}}`, `{{{TITLE}}}`, `{{{REPORTER_EMAIL}}}`, `{{{RECEIVED_AT}}}`, `{{{SENT_FROM}}}`, `{{{SCREENSHOT}}}` and `{{{DESCRIPTION}}}`, filled by `ticket.js`. "Sent from" comes from the request's User-Agent (`Videl/<version> (<OS>)` from the desktop app, `Videl-Android/<version>` from Android) or from the web app's "Sent from the Videl web app. Browser: ..." line, so keep those formats when editing the apps.

To see exactly what would be sent without emailing anyone, run `npx wrangler dev -c tools/bug_relay/wrangler.toml`, post a report to it, and open the files it writes under `tools/bug_relay/.wrangler/tmp/email/` (text, HTML and each attachment). If the designed send fails, the relay falls back to a plain-text email, so reports are never lost.

**Reporter confirmations** (`confirm-email.html`, filled by `confirmationEmail` in `ticket.js`) go through Resend, because Cloudflare's free plan only mails verified addresses. videl.app is verified in the Resend account, and the relay needs the `RESEND_API_KEY` secret (a sending-only key limited to videl.app); without it confirmations are skipped and reports still work. Keep the confirmation's wording fixed: it must never include anything the reporter typed, or the public form becomes a way to send strangers arbitrary text from videl.app. Test locally with `npx wrangler dev -c tools/bug_relay/wrangler.toml --var RESEND_API_KEY:fake`: the log should show "Confirmation not sent (401)" once per address.


## 9. Web app

```bash
npx wrangler deploy          # from the repo root; uses wrangler.jsonc (assets: web/)
```

Live at https://app.videl.app. The domain `videl.app` is registered on Cloudflare (same account as the Workers).

**Search pages.** Each tool also has its own address for search engines, such as `/compress-video` and `/merge-pdf`, because Google ignores everything after `#`. They are copies of `web/index.html` written by `python tools/web_tool_pages.py` (which also writes `web/sitemap.xml`, `web/robots.txt` and the footer tool links). **Run it after any change to `web/index.html`** (a `?v=` bump included) and before deploying, or the tool pages keep the old version. The titles, descriptions, how-to steps and questions live in that script; keep them true to what each tool does.

Test locally with `python -m http.server 8765` inside `web/`, then open http://127.0.0.1:8765. Library versions are pinned in `web/vendor/`; the FFmpeg core version is the `CORE` constant in `web/js/engines.js`.


## 10. How users get the update

- The app compares its `VERSION` with the latest release.
- **Windows**: downloads only the changed files (the delta updater) and verifies the Ed25519 signature before installing.
- **Linux**: replaces the AppImage in place after verifying its signature.
- **Download site**: https://videl.app, served from the `gh-pages` branch (checked out at `../media-utilities-pages`). It links to `/releases/latest/download/<asset>`. Pushing the branch deploys it to the Worker `videl-site` through `.github/workflows/deploy-site.yml` on that branch, using the repository secret `CLOUDFLARE_API_TOKEN`. That token ("videl-autodepoly" in Cloudflare) has only Workers Scripts Edit and Account Settings Read on the account, plus Workers Routes Edit and Zone Read on videl.app. If the secret is ever missing the run only warns, and `npx wrangler deploy` inside that folder does it by hand. The workflow can also be started from the Actions tab ("Deploy videl.app"). GitHub Pages still serves the same files at the old github.io address, and a script in `index.html` sends those visitors to videl.app, because older app versions open that address. `www.videl.app` redirects to `videl.app` (a Cloudflare redirect rule). The web app does the same for its old `workers.dev` address (script in `web/index.html`, keeping the `#/route`). Both sites serve their own `404.html` for unknown addresses (`not_found_handling: "404-page"` in each wrangler config), carry link-preview tags with a 1200x630 card (`assets/og-card.jpg`; regenerate it if the app's look changes), and link the privacy page (`privacy.html`, served at `/privacy`). Both sites link to each other with the same names ("Web app", "Desktop app", "Report a bug") and open them in the same tab.
