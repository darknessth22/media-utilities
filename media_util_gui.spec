# -*- mode: python ; coding: utf-8 -*-

import os
import sys
from PyInstaller.utils.hooks import collect_data_files, collect_submodules, collect_all, collect_dynamic_libs

IS_WIN = sys.platform == "win32"
IS_LINUX = sys.platform.startswith("linux")

datas = []
datas += collect_data_files('yt_dlp')

# Collect pip fully — datas, binaries, and submodules — so pip._vendor's
# custom path finder works inside the frozen exe.
_pip_datas, _pip_binaries, _pip_hidden = collect_all('pip')
datas += _pip_datas
datas += collect_data_files('pillow_heif')
datas += collect_data_files('fitz')

# rembg and demucs are NOT bundled — installed on-demand by the user via in-app button.

pyside6_binaries = []
try:
    pyside6_datas = collect_data_files('PySide6', includes=[
        'plugins/platforms/*', 'plugins/styles/*',
        'plugins/imageformats/*', 'plugins/multimedia/*',
        'plugins/mediaservice/*', 'plugins/audio/*',
    ])
    datas += pyside6_datas
    # Native DLLs: Qt6Multimedia.dll, Qt6MultimediaWidgets.dll, FFmpeg backend
    # DLLs (avcodec/avformat/avutil/swresample/swscale), and the multimedia
    # plugin .dlls. collect_data_files does NOT grab these — without them the
    # frozen exe cannot import QtMultimedia even though Python bindings are
    # bundled. Must use collect_dynamic_libs.
    pyside6_binaries = collect_dynamic_libs('PySide6')
    pyside6_binaries += collect_dynamic_libs('shiboken6')
except Exception as e:
    print(f"Warning: PySide6 binary collection failed: {e}")

try:
    datas += collect_data_files('playwright')
except Exception:
    print("Warning: playwright data files not found")

if os.path.isdir('assets'):
    datas.append(('assets', 'assets'))

if os.path.isdir('locales'):
    datas.append(('locales', 'locales'))

# Browser extension — shipped alongside the installed app so users can
# load it unpacked into their browser (Chrome/Edge: Load unpacked).
if os.path.isdir('browser_extension'):
    datas.append(('browser_extension', 'browser_extension'))

# Bundled embeddable Python runtime + AI manifests — Windows-only (embeddable
# Python is win-amd64). Linux installs AI packages into the user-site instead.
if IS_WIN and os.path.isdir('runtime'):
    datas.append(('runtime', 'runtime'))
if os.path.isdir('manifests'):
    datas.append(('manifests', 'manifests'))

if IS_WIN:
    if os.path.exists('bin/ffmpeg.exe'):
        datas.append(('bin/ffmpeg.exe', '.'))
    if os.path.exists('bin/ffprobe.exe'):
        datas.append(('bin/ffprobe.exe', '.'))

    if not os.path.exists('bin/ffmpeg.exe'):
        if os.path.exists('ffmpeg.exe'):
            datas.append(('ffmpeg.exe', '.'))
        if os.path.exists('ffprobe.exe'):
            datas.append(('ffprobe.exe', '.'))

    if os.path.exists('spotdl.exe'):
        datas.append(('spotdl.exe', '.'))
    elif os.path.exists('Scripts/spotdl.exe'):
        datas.append(('Scripts/spotdl.exe', '.'))
elif IS_LINUX:
    # Linux static ffmpeg/ffprobe staged into bin/ by build_appimage.sh.
    if os.path.exists('bin/ffmpeg'):
        datas.append(('bin/ffmpeg', '.'))
    if os.path.exists('bin/ffprobe'):
        datas.append(('bin/ffprobe', '.'))

hiddenimports = []

# Force-include all GUI tab modules. Static imports in gui/app.py should be
# detected automatically, but CI builds have intermittently dropped
# gui.tabs.bug_reporter — pinning the whole package avoids the gamble.
hiddenimports += collect_submodules('gui')

# yt-dlp: lazy-loads extractors internally — no submodule collection needed
hiddenimports += ['yt_dlp']

# pip: runs in-process to install AI packages — full collect via collect_all above
hiddenimports += _pip_hidden

hiddenimports += collect_submodules('pillow_heif')

# playwright: imported directly by interceptor
hiddenimports += collect_submodules('playwright')

# PySide6 multimedia modules for video trimmer
hiddenimports += [
    'PySide6.QtMultimedia',
    'PySide6.QtMultimediaWidgets',
    'PySide6.QtSvg',
    'PySide6.QtSvgWidgets',
]

hiddenimports += [
    'fitz',
    'pypdf',
    'docx',
    'docx.shared',
    'docx.enum',
    'docx.enum.text',
    'openpyxl',
    'pptx',
    'pptx.util',
    'json',
    'subprocess',
    'threading',
    'io',
    'xml.etree.ElementTree',
    'tempfile',
    'contextlib',
    'urllib.request',
    'docx2pdf',
    'win32com',
    'win32com.client',
    'win32com.server',
    'win32api',
    'win32con',
    'pywintypes',
    'winreg',
]

# Stdlib modules used by on-demand AI components (rembg / onnxruntime / demucs /
# torch) loaded from %LOCALAPPDATA%\Videl\ai_packages. Nothing in the frozen app
# imports these directly, so PyInstaller would otherwise drop them.
hiddenimports += [
    'timeit',
    'pdb',
    'cProfile',
    'pstats',
    'pkg_resources',
    'pkgutil',
    'unittest',
    'unittest.mock',
    'multiprocessing',
    'multiprocessing.pool',
    'multiprocessing.shared_memory',
    'concurrent.futures',
    'concurrent.futures.process',
    'concurrent.futures.thread',
    'lzma',
    'bz2',
    'tarfile',
    'zipfile',
    'gzip',
    'csv',
    'sqlite3',
    'email',
    'email.mime',
    'email.mime.text',
    'http.client',
    'http.cookiejar',
    'urllib.error',
    'urllib.parse',
    'urllib.response',
    'xml.etree',
    'xml.etree.ElementTree',
    'importlib.metadata',
    'importlib.resources',
    'logging.config',
    'logging.handlers',
    'difflib',
    'doctest',
    'dis',
    'platform',
    'getpass',
    'shlex',
    'pprint',
]

block_cipher = None

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=pyside6_binaries + _pip_binaries,
    datas=datas,
    hiddenimports=hiddenimports + [
        'openpyxl.cell._writer',
        'openpyxl.worksheet._writer',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=['runtime_hook_pip.py'],
    excludes=[
        'tkinter', 'ttkbootstrap', 'darkdetect', '_tkinter',
        # spotdl — runs as spotdl.exe subprocess, never imported
        'spotdl',
        # Unused PySide6 modules
        'PySide6.QtWebEngine', 'PySide6.QtWebEngineCore', 'PySide6.QtWebEngineWidgets',
        'PySide6.Qt3DCore', 'PySide6.Qt3DRender', 'PySide6.Qt3DInput',
        'PySide6.QtCharts', 'PySide6.QtDataVisualization',
        'PySide6.QtDesigner', 'PySide6.QtHelp',
        'PySide6.QtQuick', 'PySide6.QtQuickWidgets', 'PySide6.QtQml',
        'PySide6.QtLocation', 'PySide6.QtBluetooth', 'PySide6.QtNfc',
        'PySide6.QtSerialPort', 'PySide6.QtSensors', 'PySide6.QtVirtualKeyboard',
        # NB: PySide6.QtNetwork must NOT be excluded — QtMultimedia depends on it
        # for stream loading; excluding it breaks video preview in the frozen build.
        'PySide6.QtOpenGL', 'PySide6.QtOpenGLWidgets',
        'PySide6.QtPrintSupport', 'PySide6.QtTest', 'PySide6.QtXml',
        'PySide6.QtStateMachine', 'PySide6.QtConcurrent',
        'PySide6.QtPositioning', 'PySide6.QtRemoteObjects',
        'PySide6.QtScxml', 'PySide6.QtWebSockets', 'PySide6.QtWebChannel',
        # Heavy ML frameworks
        'tensorflow', 'tensorboard', 'keras',
        'numpy.distutils',
        'matplotlib', 'pandas',
        'IPython', 'ipykernel', 'ipywidgets', 'notebook', 'jupyter',
        'cv2', 'torchvision', 'torchaudio',
        'triton', 'cupy',
        # AI runtime deps — installed on-demand into %LOCALAPPDATA%\Videl\ai_packages.
        'torch', 'rembg', 'demucs', 'numba', 'onnxruntime', 'scipy', 'sklearn',
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
    name='Videl',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[
        'vcruntime140.dll', 'msvcp140.dll',
        # UPX-packed Qt DLLs silently break plugin loading (multimedia
        # backend, image formats). Keep all Qt6* + the FFmpeg backend
        # DLLs uncompressed.
        'Qt6Core.dll', 'Qt6Gui.dll', 'Qt6Widgets.dll', 'Qt6Svg.dll',
        'Qt6Multimedia.dll', 'Qt6MultimediaWidgets.dll',
        'Qt6Network.dll', 'Qt6OpenGL.dll', 'Qt6Qml.dll',
        'avcodec-*.dll', 'avformat-*.dll', 'avutil-*.dll',
        'swresample-*.dll', 'swscale-*.dll',
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
        'vcruntime140.dll', 'msvcp140.dll',
        'Qt6Core.dll', 'Qt6Gui.dll', 'Qt6Widgets.dll', 'Qt6Svg.dll',
        'Qt6Multimedia.dll', 'Qt6MultimediaWidgets.dll',
        'Qt6Network.dll', 'Qt6OpenGL.dll', 'Qt6Qml.dll',
        'avcodec-*.dll', 'avformat-*.dll', 'avutil-*.dll',
        'swresample-*.dll', 'swscale-*.dll',
    ],
    name='Videl',
)
