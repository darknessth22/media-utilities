# -*- mode: python ; coding: utf-8 -*-

import os
import sys
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

# Collect data files for various packages
datas = []
datas += collect_data_files('yt_dlp')
datas += collect_data_files('pillow_heif')
datas += collect_data_files('fitz')

# Collect only PySide6 plugin data files (platforms, styles, imageformats)
pyside6_binaries = []
try:
    pyside6_datas = collect_data_files('PySide6', includes=['plugins/platforms/*', 'plugins/styles/*', 'plugins/imageformats/*', 'plugins/multimedia/*'])
    datas += pyside6_datas
except Exception as e:
    print(f"Warning: PySide6 data collection failed: {e}")

# Try to collect spotdl data files for Spotify support
try:
    datas += collect_data_files('spotdl')
except Exception:
    print("Warning: spotdl data files not found - Spotify support may not work in executable")

# Add application assets
assets_dir = os.path.join(os.path.dirname(os.path.abspath('.')), 'assets')
if os.path.isdir('assets'):
    datas.append(('assets', 'assets'))

# Add FFmpeg and FFprobe executables if they exist in the bin directory (setup by build_executable.py)
if os.path.exists('bin/ffmpeg.exe'):
    datas.append(('bin/ffmpeg.exe', '.'))
if os.path.exists('bin/ffprobe.exe'):
    datas.append(('bin/ffprobe.exe', '.'))

# Fallback for current directory if bin/ doesn't exist yet
if not os.path.exists('bin/ffmpeg.exe'):
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
    binaries=pyside6_binaries,
    datas=datas,
    hiddenimports=hiddenimports + [
        'openpyxl.cell._writer',
        'openpyxl.worksheet._writer'
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'tkinter', 'ttkbootstrap', 'darkdetect', '_tkinter',
        # PySide6 unused modules
        'PySide6.QtWebEngine', 'PySide6.QtWebEngineCore', 'PySide6.QtWebEngineWidgets',
        'PySide6.Qt3DCore', 'PySide6.Qt3DRender', 'PySide6.Qt3DInput',
        'PySide6.QtCharts', 'PySide6.QtDataVisualization',
        'PySide6.QtDesigner', 'PySide6.QtHelp',
        'PySide6.QtQuick', 'PySide6.QtQuickWidgets', 'PySide6.QtQml',
        'PySide6.QtLocation', 'PySide6.QtBluetooth', 'PySide6.QtNfc',
        'PySide6.QtSerialPort', 'PySide6.QtSensors', 'PySide6.QtVirtualKeyboard',
        # Heavy ML/AI libraries not needed at runtime
        'torch', 'tensorflow', 'tensorboard', 'keras',
        'onnxruntime', 'onnx',
        'numpy.distutils',
        'scipy', 'sklearn', 'skimage',
        'matplotlib', 'pandas',
        'IPython', 'ipykernel', 'ipywidgets', 'notebook', 'jupyter',
        'cv2', 'torchvision', 'torchaudio',
        'triton', 'cupy',
    ],
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
    upx_exclude=[
        'vcruntime140.dll', 'msvcp140.dll', 'qwindows.dll', 'qstyles.dll',
        'Qt6Core.dll', 'Qt6Gui.dll', 'Qt6Widgets.dll', 'Qt6Multimedia.dll',
        'Qt6MultimediaWidgets.dll', 'Qt6Network.dll', 'Qt6Svg.dll',
        'Qt6SvgWidgets.dll', 'shiboken6.abi3.dll', 'pyside6.abi3.dll'
    ],
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
    upx_exclude=[
        'vcruntime140.dll', 'msvcp140.dll', 'qwindows.dll', 'qstyles.dll',
        'Qt6Core.dll', 'Qt6Gui.dll', 'Qt6Widgets.dll', 'Qt6Multimedia.dll',
        'Qt6MultimediaWidgets.dll', 'Qt6Network.dll', 'Qt6Svg.dll',
        'Qt6SvgWidgets.dll', 'shiboken6.abi3.dll', 'pyside6.abi3.dll'
    ],
    name='MediaUtility',
)
