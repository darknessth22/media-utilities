# -*- mode: python ; coding: utf-8 -*-

import os
import sys
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

# Collect data files for various packages
datas = []
datas += collect_data_files('yt_dlp')
datas += collect_data_files('pillow_heif')
datas += collect_data_files('fitz')

# Add FFmpeg executable if it exists in the current directory
if os.path.exists('ffmpeg.exe'):
    datas.append(('ffmpeg.exe', '.'))

# Hidden imports for packages that might not be detected automatically
hiddenimports = []
hiddenimports += collect_submodules('yt_dlp')
hiddenimports += collect_submodules('pillow_heif')
hiddenimports += [
    'PIL._tkinter_finder',
    'tkinter',
    'tkinter.ttk',
    'tkinter.filedialog',
    'tkinter.messagebox',
    'fitz',
    'docx',
    'openpyxl',
    'pptx',
    'json',
    'subprocess',
    'threading',
    'io'
]

block_cipher = None

a = Analysis(
    ['media_util_gui.py'],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=[
    'openpyxl.cell._writer',
    'openpyxl.worksheet._writer'],
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
