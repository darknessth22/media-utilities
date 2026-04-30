# Videl — Claude Guidelines

## File reading discipline

**Read only files relevant to the current question or feature.**
Do not read the entire codebase. If you need to know where a method or class lives,
query the codebase graph (see below) before opening any file.

Key entry points when you do need to read:
- `gui/app.py` — MainWindow, TitleBar, shortcuts, navigation
- `gui/tabs/<name>_section.py` — individual tool tabs
- `core/<module>.py` — business logic for each tool
- `locales/en.json` + `locales/ar.json` — all UI strings

## Arabic translation rule

**Every UI-visible string added or changed must have a matching Arabic entry.**

Whenever you add or modify:
- Text in any `gui/` file (labels, tooltips, placeholders, section headers)
- Tutorial content in `gui/tabs/tutorial_section.py`
- Locale keys in `locales/en.json`

…you must also update `locales/ar.json` with the Arabic translation in the same PR/change.

The tutorial section stores data in two parallel Python lists:
`_TUTORIAL_DATA_EN` and `_TUTORIAL_DATA_AR` — both must stay in sync.

## New features and the How to Use tutorial

**Whenever you add a new user-facing feature or tool tab**, update the How to Use tutorial in `gui/tabs/tutorial_section.py` in the same change.

- Add steps or a subsection that explain what the feature does and how to use it (English in `_TUTORIAL_DATA_EN`).
- Add the matching Arabic copy in `_TUTORIAL_DATA_AR` so the two lists stay aligned entry-for-entry.

Skipping the tutorial leaves users without in-app guidance for the new capability; treat tutorial + Arabic as part of the feature definition of done.

## README update rule

**Whenever you add a new feature, tool tab, or significant capability**, update `README.md` in the same change.

- Add the new tool/feature to the features list or tools table.
- If it introduces new dependencies, update the installation/requirements section.
- Keep the README accurate — it is the first thing users and contributors read.

Treat README as part of the feature definition of done, same as the tutorial.

## Codebase graph

A knowledge graph of the codebase is available via `/graphify`.
Query it to find which file a class or method lives in, what calls what,
and how modules are connected — **before** opening files to explore.

Use the graph to answer questions like:
- "Where is `_navigate_to` defined?"
- "What calls `trigger_primary_action`?"
- "Which tabs import `Worker`?"

This avoids reading files that are not relevant to the task.

Whenever you change something in the codebase, refresh the graph:

```bash
graphify update ./src
```

## Project structure (quick reference)

```
gui/
  app.py                    MainWindow + TitleBar + SettingsSection
  tabs/<name>_section.py    One file per tool tab (16 tabs)
  theme.py                  ThemeManager
  worker.py                 Background thread Worker
core/
  <tool>.py                 Business logic (no Qt imports)
  i18n.py                   I18n singleton — tr() for translations
  settings.py               SettingsManager + UserSettings dataclass
locales/
  en.json                   English strings
  ar.json                   Arabic strings  ← always update together with en.json
assets/icons/               SVG icons (tinted at runtime)
.github/workflows/ci.yml      CI — pytest on Windows (push to `main` only)
.github/workflows/build.yml   Release build — PyInstaller + Inno Setup + artifacts (push to `main` only)
media_util_gui.spec           PyInstaller spec (datas, hiddenimports, binaries)
```

## Build

```bat
python build_executable.py   # PyInstaller + Inno Setup → Output/Videl_Setup.exe
```

**PyInstaller spec:** On any major update (new dependencies, runtime data files, non-Python assets loaded at startup, binaries, or modules PyInstaller fails to detect), update `media_util_gui.spec` in the same change: extend `datas` for bundled folders/files, `hiddenimports` for dynamic imports, and `binaries` only when needed. Frozen builds do not see the repo filesystem the same way as `python main.py`; anything the app opens by path must use `resource_path` (or equivalent) and be listed in `datas` where appropriate.

GitHub Actions (**push to `main` only**, e.g. after merging a PR): **CI** runs `pytest`, then **Build Videl** produces the Windows installer and uploads artifacts. Neither workflow runs on pull-request events alone.
