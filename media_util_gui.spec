# -*- mode: python ; coding: utf-8 -*-

import os
import sys
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

# Collect data files for various packages
datas = []
datas += collect_data_files('yt_dlp')
datas += collect_data_files('pillow_heif')
datas += collect_data_files('fitz')

# Try to collect spotdl data files for Spotify support
try:
    datas += collect_data_files('spotdl')
except:
    print("Warning: spotdl data files not found - Spotify support may not work in executable")

# Add FFmpeg executable if it exists in the current directory
if os.path.exists('ffmpeg.exe'):
    datas.append(('ffmpeg.exe', '.'))

# Add spotdl executable if it exists (for Spotify support)
if os.path.exists('spotdl.exe'):
    datas.append(('spotdl.exe', '.'))
elif os.path.exists('Scripts/spotdl.exe'):
    datas.append(('Scripts/spotdl.exe', '.'))

# Hidden imports for packages that might not be detected automatically
hiddenimports = []
hiddenimports += collect_submodules('yt_dlp')
hiddenimports += collect_submodules('pillow_heif')

# Try to collect spotdl submodules for Spotify support
try:
    hiddenimports += collect_submodules('spotdl')
except:
    print("Warning: spotdl submodules not found - adding basic spotdl imports")
    hiddenimports += ['spotdl', 'spotdl.download', 'spotdl.utils']

hiddenimports += [
    'PIL._tkinter_finder',
    'tkinter',
    'tkinter.ttk',
    'tkinter.filedialog',
    'tkinter.messagebox',
    'fitz',
    'docx',
    'docx.shared',  # Added for enhanced document conversion
    'openpyxl',
    'pptx',
    'pptx.util',    # Added for enhanced document conversion
    'json',
    'subprocess',
    'threading',
    'io',
    'xml.etree.ElementTree',  # Added for document image extraction
    'tempfile',     # Added for temporary file handling
    'urllib.request'  # May be needed for spotdl
]

block_cipher = None

a = Analysis(
    ['media_util_gui.py'],
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
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='MediaUtility',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,  # Set to False for GUI application
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='icon.ico' if os.path.exists('icon.ico') else None,
)
