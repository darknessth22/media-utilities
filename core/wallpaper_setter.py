"""Programmatic per-monitor wallpaper assignment on Windows.

Uses the `IDesktopWallpaper` COM interface via raw ctypes (no extra deps).
On non-Windows platforms public functions degrade gracefully (`is_supported`
returns False; setters raise NotImplementedError).

Public API:
- ``is_supported()`` — True on Windows
- ``list_monitors()`` — enumerate connected monitors with device-path IDs + geometry
- ``apply_assignments(pairs)`` — set each (monitor_id, file_path) pair as that monitor's wallpaper
- ``apply_per_monitor(paths)`` — index-based fallback; sets paths[i] on the i-th enumerated monitor

Reference: https://learn.microsoft.com/en-us/windows/win32/api/shobjidl_core/nn-shobjidl_core-idesktopwallpaper
"""
from __future__ import annotations

import os
import sys
from typing import Optional


def is_supported() -> bool:
    return sys.platform == "win32"


# ── Internal: bound interface ────────────────────────────────────────────────

class _IFace:
    """Holds the live COM pointer + bound vtable methods. Caller must call .release()."""

    def __init__(self) -> None:
        import ctypes
        from ctypes import POINTER, c_uint, c_ulong, c_void_p, c_wchar_p, c_long
        from ctypes import HRESULT

        self._ctypes = ctypes
        self._ole32 = ctypes.OleDLL("ole32")

        class GUID(ctypes.Structure):
            _fields_ = [
                ("Data1", ctypes.c_uint32),
                ("Data2", ctypes.c_uint16),
                ("Data3", ctypes.c_uint16),
                ("Data4", ctypes.c_ubyte * 8),
            ]

        class RECT(ctypes.Structure):
            _fields_ = [
                ("left", c_long), ("top", c_long),
                ("right", c_long), ("bottom", c_long),
            ]

        self.RECT = RECT

        def _guid(s: str) -> GUID:
            g = GUID()
            self._ole32.IIDFromString(ctypes.c_wchar_p(s), ctypes.byref(g))
            return g

        CLSID_DesktopWallpaper = _guid("{C2CF3110-460E-4FC1-B9D0-8A1C0C9CC4BD}")
        IID_IDesktopWallpaper  = _guid("{B92B56A9-8B55-4E14-9A89-0199BBB6F93B}")

        CLSCTX_LOCAL_SERVER = 0x4
        COINIT_APARTMENTTHREADED = 0x2

        try:
            self._ole32.CoInitializeEx(None, COINIT_APARTMENTTHREADED)
        except OSError:
            pass  # already initialised, fine

        p_iface = c_void_p()
        hr = self._ole32.CoCreateInstance(
            ctypes.byref(CLSID_DesktopWallpaper), None,
            CLSCTX_LOCAL_SERVER,
            ctypes.byref(IID_IDesktopWallpaper),
            ctypes.byref(p_iface),
        )
        if hr != 0 or not p_iface.value:
            raise OSError(
                f"CoCreateInstance(IDesktopWallpaper) failed (HRESULT 0x{hr & 0xFFFFFFFF:08X})."
            )
        self.p_iface = p_iface

        # vtable layout (IUnknown 0..2, interface 3..):
        #   3 SetWallpaper(LPCWSTR monitorID, LPCWSTR wallpaper)
        #   5 GetMonitorDevicePathAt(UINT idx, LPWSTR *monitorID)
        #   6 GetMonitorDevicePathCount(UINT *count)
        #   7 GetMonitorRECT(LPCWSTR monitorID, RECT *displayRect)
        #  10 SetPosition(DESKTOP_WALLPAPER_POSITION)
        vtbl = ctypes.cast(p_iface, POINTER(POINTER(c_void_p))).contents
        self.SetWallpaper = ctypes.WINFUNCTYPE(HRESULT, c_void_p, c_wchar_p, c_wchar_p)(vtbl[3])
        self.GetMonitorDevicePathAt = ctypes.WINFUNCTYPE(HRESULT, c_void_p, c_uint, POINTER(c_wchar_p))(vtbl[5])
        self.GetMonitorDevicePathCount = ctypes.WINFUNCTYPE(HRESULT, c_void_p, POINTER(c_uint))(vtbl[6])
        self.GetMonitorRECT = ctypes.WINFUNCTYPE(HRESULT, c_void_p, c_wchar_p, POINTER(RECT))(vtbl[7])
        self.SetPosition = ctypes.WINFUNCTYPE(HRESULT, c_void_p, c_uint)(vtbl[10])
        self._Release = ctypes.WINFUNCTYPE(c_ulong, c_void_p)(vtbl[2])

    def co_task_mem_free(self, ptr) -> None:
        self._ole32.CoTaskMemFree(ptr)

    def release(self) -> None:
        if self.p_iface and self.p_iface.value:
            self._Release(self.p_iface)
            self.p_iface.value = 0


# ── Public ───────────────────────────────────────────────────────────────────

def list_monitors() -> list[dict]:
    """Enumerate connected monitors. Returns [{id, x, y, width, height}, ...] in IDesktopWallpaper order."""
    if not is_supported():
        return []
    import ctypes
    from ctypes import c_uint, c_wchar_p
    iface = _IFace()
    out: list[dict] = []
    try:
        count = c_uint(0)
        if iface.GetMonitorDevicePathCount(iface.p_iface, ctypes.byref(count)) != 0:
            return out
        for i in range(count.value):
            mid = c_wchar_p()
            hr = iface.GetMonitorDevicePathAt(iface.p_iface, i, ctypes.byref(mid))
            if hr != 0 or not mid.value:
                continue
            device_path = mid.value
            try:
                rect = iface.RECT()
                if iface.GetMonitorRECT(iface.p_iface, mid, ctypes.byref(rect)) == 0:
                    out.append({
                        "id": device_path,
                        "x": int(rect.left),
                        "y": int(rect.top),
                        "width": int(rect.right - rect.left),
                        "height": int(rect.bottom - rect.top),
                    })
                else:
                    # Detached monitor — keep the id so user can still target it manually if it comes back.
                    out.append({
                        "id": device_path,
                        "x": 0, "y": 0, "width": 0, "height": 0,
                    })
            finally:
                iface.co_task_mem_free(mid)
    finally:
        iface.release()
    return out


def apply_assignments(pairs: list[tuple[Optional[str], str]]) -> int:
    """Set wallpapers for specific monitors.

    Each tuple is (monitor_id, file_path). monitor_id is a Windows device path
    returned by `list_monitors`. When monitor_id is None, the next unused
    enumerated monitor (by index, skipping ones already assigned in this call)
    is targeted — useful for manually-added rows that weren't bound at detect time.

    Returns the count of monitors successfully set.
    """
    if not is_supported():
        raise NotImplementedError("Per-monitor wallpaper setting is Windows-only.")
    import ctypes
    from ctypes import c_uint, c_wchar_p
    DWPOS_FILL = 4

    iface = _IFace()
    n_applied = 0
    try:
        # Render at native pixel ratio — image was already sized to the screen.
        iface.SetPosition(iface.p_iface, DWPOS_FILL)

        # Build the enumerated list once so None-id assignments can claim leftovers.
        count = c_uint(0)
        iface.GetMonitorDevicePathCount(iface.p_iface, ctypes.byref(count))
        enumerated: list[str] = []
        for i in range(count.value):
            mid = c_wchar_p()
            if iface.GetMonitorDevicePathAt(iface.p_iface, i, ctypes.byref(mid)) == 0 and mid.value:
                enumerated.append(mid.value)
                iface.co_task_mem_free(mid)
        used: set[str] = set()

        for monitor_id, file_path in pairs:
            if not file_path or not os.path.isfile(file_path):
                continue
            target_id = monitor_id
            if not target_id:
                # Pick first unused enumerated monitor.
                for cand in enumerated:
                    if cand not in used:
                        target_id = cand
                        break
            if not target_id:
                continue
            hr = iface.SetWallpaper(
                iface.p_iface,
                ctypes.c_wchar_p(target_id),
                ctypes.c_wchar_p(os.path.abspath(file_path)),
            )
            if hr == 0:
                n_applied += 1
                used.add(target_id)
    finally:
        iface.release()
    return n_applied


def apply_slideshow(
    folder: str,
    interval_minutes: int = 30,
    shuffle: bool = False,
) -> bool:
    """Configure Windows to cycle wallpapers from `folder` every `interval_minutes`.

    Uses ``IDesktopWallpaper.SetSlideshow`` + ``SetSlideshowOptions``. This is a
    SYSTEM-WIDE slideshow (Windows cycles across all monitors); the COM API
    does not support per-monitor folders. For "per-monitor slideshow" we still
    rely on the single SetSlideshow call — the user picks one anchor folder.
    """
    if not is_supported():
        raise NotImplementedError("Slideshow setting is Windows-only.")
    if not folder or not os.path.isdir(folder):
        raise ValueError(f"Slideshow folder does not exist: {folder!r}")

    import ctypes
    from ctypes import POINTER, c_int, c_uint, c_void_p, c_wchar_p
    from ctypes import HRESULT

    iface = _IFace()
    try:
        ole32 = iface._ole32

        class GUID(ctypes.Structure):
            _fields_ = [
                ("Data1", ctypes.c_uint32),
                ("Data2", ctypes.c_uint16),
                ("Data3", ctypes.c_uint16),
                ("Data4", ctypes.c_ubyte * 8),
            ]

        def _guid(s: str) -> GUID:
            g = GUID()
            ole32.IIDFromString(ctypes.c_wchar_p(s), ctypes.byref(g))
            return g

        IID_IShellItem      = _guid("{43826D1E-E718-42EE-BC55-A1E261C37BFE}")
        IID_IShellItemArray = _guid("{B63EA76D-1F85-456F-A19C-48159EFA858B}")

        shell32 = ctypes.OleDLL("shell32")
        shell32.SHCreateItemFromParsingName.restype = HRESULT
        shell32.SHCreateItemFromParsingName.argtypes = [
            c_wchar_p, c_void_p, POINTER(GUID), POINTER(c_void_p),
        ]
        shell32.SHCreateShellItemArrayFromShellItem.restype = HRESULT
        shell32.SHCreateShellItemArrayFromShellItem.argtypes = [
            c_void_p, POINTER(GUID), POINTER(c_void_p),
        ]

        p_item = c_void_p()
        hr = shell32.SHCreateItemFromParsingName(
            ctypes.c_wchar_p(os.path.abspath(folder)), None,
            ctypes.byref(IID_IShellItem), ctypes.byref(p_item),
        )
        if hr != 0 or not p_item.value:
            raise OSError(f"SHCreateItemFromParsingName failed (HRESULT 0x{hr & 0xFFFFFFFF:08X}).")

        # Each IUnknown has a Release at vtable index 2.
        item_vt = ctypes.cast(p_item, POINTER(POINTER(c_void_p))).contents
        item_release = ctypes.WINFUNCTYPE(ctypes.c_ulong, c_void_p)(item_vt[2])

        p_arr = c_void_p()
        try:
            hr = shell32.SHCreateShellItemArrayFromShellItem(
                p_item, ctypes.byref(IID_IShellItemArray), ctypes.byref(p_arr),
            )
            if hr != 0 or not p_arr.value:
                raise OSError(f"SHCreateShellItemArrayFromShellItem failed (HRESULT 0x{hr & 0xFFFFFFFF:08X}).")

            arr_vt = ctypes.cast(p_arr, POINTER(POINTER(c_void_p))).contents
            arr_release = ctypes.WINFUNCTYPE(ctypes.c_ulong, c_void_p)(arr_vt[2])

            # IDesktopWallpaper vtable extras:
            #  12 SetSlideshow(IShellItemArray*)
            #  13 GetSlideshow(IShellItemArray**)
            #  14 SetSlideshowOptions(DESKTOP_SLIDESHOW_OPTIONS, UINT tickMs)
            #  17 Enable(BOOL)
            vtbl = ctypes.cast(iface.p_iface, POINTER(POINTER(c_void_p))).contents
            SetSlideshow        = ctypes.WINFUNCTYPE(HRESULT, c_void_p, c_void_p)(vtbl[12])
            SetSlideshowOptions = ctypes.WINFUNCTYPE(HRESULT, c_void_p, c_uint, c_uint)(vtbl[14])
            Enable              = ctypes.WINFUNCTYPE(HRESULT, c_void_p, c_int)(vtbl[17])

            Enable(iface.p_iface, 1)
            hr = SetSlideshow(iface.p_iface, p_arr)
            if hr != 0:
                raise OSError(f"SetSlideshow failed (HRESULT 0x{hr & 0xFFFFFFFF:08X}).")
            DSO_SHUFFLEIMAGES = 0x01
            options = DSO_SHUFFLEIMAGES if shuffle else 0
            tick_ms = max(60_000, int(interval_minutes) * 60 * 1000)
            SetSlideshowOptions(iface.p_iface, options, tick_ms)
            arr_release(p_arr)
        finally:
            item_release(p_item)
    finally:
        iface.release()
    return True


def apply_per_monitor(paths_in_screen_order: list[str]) -> int:
    """Index-based fallback. paths[i] → enumerated monitor i. Kept for compatibility.

    Prefer `apply_assignments` when you have monitor IDs — that variant is
    immune to row reordering / deletion in the caller's UI.
    """
    return apply_assignments([(None, p) for p in paths_in_screen_order])
