# Contributing to Videl

Thanks for your interest in improving Videl. This guide covers how to set up the project, the conventions to follow, and how to submit changes.

## Getting started

1. Fork the repo and clone your fork.
2. Create a virtual environment and install dependencies:
   ```bash
   python -m venv .venv
   .venv\Scripts\activate
   pip install -r requirements.txt
   ```
3. Run the app:
   ```bash
   python main.py
   ```
4. See [SETUP.md](SETUP.md) for FFmpeg, PyTorch, and platform-specific notes.

## Branching

- `main` — release branch. Pushes here trigger CI + the Windows installer build.
- Feature branches — `feature/<short-name>`, `fix/<short-name>`, or `phase<N>/<topic>`.
- Open PRs against `main`. Pull requests do **not** trigger the build workflow; only merges to `main` do.

## Code conventions

- **GUI vs core separation.** `core/` holds business logic and must not import Qt. `gui/` wires Qt widgets to core modules.
- **Tabs.** One file per tool tab in `gui/tabs/<name>_section.py`. When adding a new tab, follow the checklist in [CLAUDE.md](CLAUDE.md) under *Adding a new section / tool tab* — every step is required or the app breaks.
- **i18n.** Every UI-visible string lives in `locales/en.json` and `locales/ar.json`. Both files must be updated in the same change. Use `tr()` from `core/i18n.py`; never hardcode user-facing text.
- **Tutorial.** New user-facing features must add steps to `gui/tabs/tutorial_section.py` (`_TUTORIAL_DATA_EN` and `_TUTORIAL_DATA_AR`, kept entry-for-entry aligned).
- **README.** New features/tools must be reflected in `README.md` in the same change.
- **Frozen builds.** Anything loaded by path at runtime must use `resource_path` and be listed in `media_util_gui.spec` (`datas` / `hiddenimports` / `binaries`).

## Tests

Run the suite locally before opening a PR:

```bash
pytest
```

CI runs `pytest` on Windows for every push to `main`. Add tests under `tests/` for new core logic. GUI smoke tests are welcome but not required.

## Commits

- Conventional Commits style: `feat(scope): …`, `fix(scope): …`, `refactor(scope): …`, `docs(scope): …`.
- Keep the subject ≤ 72 chars. Use the body for the *why*.
- Do **not** add `Co-Authored-By` trailers for AI assistants.
- For release-bound merges to `main`, also bump `APP_VERSION` in `main.py` and tag (`vX.Y.Z`) — see [CLAUDE.md](CLAUDE.md) *Deployment Protocol*.

## Pull requests

A good PR:

- Targets `main` (or the active phase branch if directed).
- Has a clear title and a description that explains motivation, approach, and any tradeoffs.
- Includes screenshots or a short clip for any UI change.
- Updates `README.md`, the tutorial, and `locales/ar.json` when applicable.
- Passes `pytest` and runs cleanly via `python main.py`.

## Reporting bugs

Open a GitHub issue with:

- OS + version, Python version, Videl version (`APP_VERSION` in `main.py`).
- Repro steps, expected vs actual behaviour.
- Logs from the in-app Bug Reporter tab, or the console output when running `python main.py`.

## Security

Do not file public issues for security problems. Email the maintainer directly with details and a repro.

## License

By contributing you agree your contributions are licensed under the same license as the project.
