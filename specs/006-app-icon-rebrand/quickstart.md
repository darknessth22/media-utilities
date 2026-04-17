# Quickstart: Custom App Icon & Rebrand to Medix

**Feature Branch**: `006-app-icon-rebrand`
**Date**: 2026-03-27

## How to Set Your Custom Icon

### Step 1: Prepare Your Icon Files

You need two versions of your icon:

| File | Format | Sizes | Purpose |
|------|--------|-------|---------|
| `icon.ico` | Windows ICO | 256, 128, 64, 32, 16 px | Executable file icon & installer |
| `app-icon.png` | PNG | 256x256 px (recommended) | Runtime window/taskbar/tray icon |

**Tip**: Use a tool like [RealFaviconGenerator](https://realfavicongenerator.net/) or GIMP to create multi-size ICO files from a PNG source.

### Step 2: Place the Icon Files

1. Copy your `.ico` file to the **project root** as `icon.ico`
2. Copy your `.png` file to `assets/icons/app-icon.png`

```text
media-utilities/
├── icon.ico                  ← Your Windows ICO file
└── assets/
    └── icons/
        └── app-icon.png      ← Your PNG icon for runtime
```

### Step 3: Run the Application

```bash
python main.py
```

Verify your icon appears in:
- Window title bar (top-left corner)
- Windows taskbar
- System tray (bottom-right notification area)

### Step 4: Build the Executable (optional)

If distributing as a standalone `.exe`:

```bash
python build_executable.py
```

The built executable at `dist/Medix/Medix.exe` will embed your `icon.ico` as its file icon.

## Troubleshooting

| Issue | Solution |
|-------|----------|
| Default Python icon still showing | Ensure `app-icon.png` exists in `assets/icons/` and restart the app |
| Taskbar shows old icon | Windows caches taskbar icons. Right-click taskbar → restart Explorer, or log out and back in |
| Executable has no icon | Ensure `icon.ico` is in the project root before running `build_executable.py` |
| Icon looks blurry | Use a multi-size ICO (256+128+64+32+16) and a 256x256+ PNG |

## Optional: Replace the In-App Logo

The title bar and sidebar display a separate logo loaded from `assets/icons/dashboard.svg`. To customize it:

1. Create your logo as SVG
2. Replace `assets/icons/dashboard.svg` with your file
3. The app renders it at 24px (title bar) and 40px (sidebar) with blue tinting (#3B82F6)
