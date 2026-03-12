# -*- mode: python ; coding: utf-8 -*-

import os
import sys
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

# Collect data files for various packages
datas = []
datas += collect_data_files('yt_dlp')
datas += collect_data_files('pillow_heif')
datas += collect_data_files('fitz')

# Collect PySide6 assets (translations, plugins, etc.)
try:
    datas += collect_data_files('PySide6')
except Exception:
    pass

# Try to collect spotdl data files for Spotify support
try:
    datas += collect_data_files('spotdl')
except Exception:
    print("Warning: spotdl data files not found - Spotify support may not work in executable")

# Add application assets
assets_dir = os.path.join(os.path.dirname(os.path.abspath('.')), 'assets')
if os.path.isdir('assets'):
    datas.append(('assets', 'assets'))

# Add FFmpeg and FFprobe executables if they exist in the current directory
if os.path.exists('ffmpeg.exe'):
    datas.append(('ffmpeg.exe', '.'))
if os.path.exists('ffprobe.exe'):
    datas.append(('ffprobe.exe', '.'))

# Add spotdl executable if it exists (for Spotify support)
if os.path.exists('spotdl.exe'):
    datas.append(('spotdl.exe', '.'))
elif os.path.exists('Scripts/spotdl.exe'):
    datas.append(('Scripts/spotdl.exe', '.'))

# Hidden imports for packages that might not be detected automatically
hiddenimports = []
hiddenimports += collect_submodules('yt_dlp')
hiddenimports += collect_submodules('pillow_heif')

# PySide6 multimedia modules for video trimmer
hiddenimports += [
    'PySide6.QtMultimedia',
    'PySide6.QtMultimediaWidgets',
    'PySide6.QtSvg',
    'PySide6.QtSvgWidgets',
]

# Try to collect spotdl submodules for Spotify support
try:
    hiddenimports += collect_submodules('spotdl')
except Exception:
    print("Warning: spotdl submodules not found - adding basic spotdl imports")
    hiddenimports += ['spotdl', 'spotdl.download', 'spotdl.utils']

hiddenimports += [
    'fitz',
    'docx',
    'docx.shared',
    'docx.enum',
    'docx.enum.text',   # WD_ALIGN_PARAGRAPH used in document.py
    'openpyxl',
    'pptx',
    'pptx.util',
    'json',
    'subprocess',
    'threading',
    'io',
    'xml.etree.ElementTree',
    'tempfile',
    'contextlib',       # Used in document.py _temp_png context manager
    'urllib.request',   # May be needed for spotdl
    'docx2pdf',
]

block_cipher = None

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports + [
        'openpyxl.cell._writer',
        'openpyxl.worksheet._writer'
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tkinter', 'ttkbootstrap', 'darkdetect', '_tkinter'],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='MediaUtility',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='icon.ico' if os.path.exists('icon.ico') else None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='MediaUtility',
)
