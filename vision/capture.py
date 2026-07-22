"""Screen capture for the vision path — cross-platform, three backends behind
capture_region():

  * screencapture — macOS built-in CLI, a screen rectangle (no dependency).
  * imagegrab     — Pillow ImageGrab (Windows + macOS; Pillow is already a vision dep).
  * window        — capture a specific window (e.g. RetroArch) BY IDENTITY, so it can be
    moved/resized freely and sit behind other windows (occlusion-independent). macOS grabs
    the window (title bar included) via Quartz + screencapture -l; Windows grabs its CLIENT
    area (no title bar/borders) via PrintWindow. Because the game keeps a fixed aspect ratio,
    the normalized region boxes stay valid at any window size — no region rect to set or
    re-tune. (The macOS and Windows crops differ by the title bar, so ACTION/MOVES layout is
    calibrated per OS.)

'auto' uses screencapture on macOS and ImageGrab elsewhere. Force via config
world.vision.capture. crop_norm slices a normalized box out of an already-captured
frame — capture once per turn, crop many regions.
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile

from PIL import Image, ImageGrab


def _ltrb(bbox: tuple[int, int, int, int] | None):
    """(x, y, w, h) -> (left, top, right, bottom) for ImageGrab; None stays None."""
    if bbox is None:
        return None
    x, y, w, h = bbox
    return (x, y, x + w, y + h)


def _grab_screencapture(bbox: tuple[int, int, int, int] | None) -> Image.Image:
    fd, path = tempfile.mkstemp(suffix=".png")
    os.close(fd)
    try:
        cmd = ["screencapture", "-x"]        # -x: silent
        if bbox is not None:
            cmd += ["-R", f"{bbox[0]},{bbox[1]},{bbox[2]},{bbox[3]}"]
        cmd.append(path)
        subprocess.run(cmd, check=True, capture_output=True)
        img = Image.open(path)
        img.load()
        return img
    finally:
        if os.path.exists(path):
            os.unlink(path)


def _grab_imagegrab(bbox: tuple[int, int, int, int] | None) -> Image.Image:
    ltrb = _ltrb(bbox)
    img = ImageGrab.grab() if ltrb is None else ImageGrab.grab(bbox=ltrb)
    return img.convert("RGB")


def _pick_window(infos, match: str):
    """Largest on-screen window whose owner or title contains `match` (case-insensitive).
    `infos` is CGWindowListCopyWindowInfo output. Returns the CGWindowID, or None."""
    m = match.lower()
    best, best_area = None, -1
    for w in infos:
        owner = (w.get("kCGWindowOwnerName") or "")
        name = (w.get("kCGWindowName") or "")
        if m in owner.lower() or m in name.lower():
            b = w.get("kCGWindowBounds") or {}
            area = (b.get("Width") or 0) * (b.get("Height") or 0)
            if area > best_area:
                best_area, best = area, w.get("kCGWindowNumber")
    return best


def _find_window_id(match: str):
    import Quartz
    infos = Quartz.CGWindowListCopyWindowInfo(
        Quartz.kCGWindowListOptionOnScreenOnly, Quartz.kCGNullWindowID)
    return _pick_window(infos, match)


def _grab_window(match: str) -> Image.Image:
    """Capture the window matching `match` by identity — dispatched by platform."""
    if sys.platform == "darwin":
        return _grab_window_mac(match)
    if sys.platform == "win32":
        return _grab_window_windows(match)
    raise RuntimeError(
        f"window capture is only implemented for macOS and Windows (platform={sys.platform!r}); "
        "use capture: imagegrab with an explicit region instead"
    )


def _grab_window_mac(match: str) -> Image.Image:
    """macOS: capture the window matching `match` by its CGWindowID (position/size/
    z-order independent). Needs Screen Recording permission and the window on-screen."""
    wid = _find_window_id(match)
    if wid is None:
        raise RuntimeError(
            f"No on-screen window matching {match!r} found. Is RetroArch running and "
            "visible (not minimized)? Set world.vision.window to match its title."
        )
    fd, path = tempfile.mkstemp(suffix=".png")
    os.close(fd)
    try:
        # -l <id>: that window only; -o: no drop shadow; -x: silent.
        subprocess.run(["screencapture", "-x", "-o", "-l", str(wid), path],
                       check=True, capture_output=True)
        img = Image.open(path)
        img.load()
        return img.convert("RGB")
    finally:
        if os.path.exists(path):
            os.unlink(path)


# ---- Windows: capture a window's client area by identity (stdlib ctypes) ------------
# PrintWindow(PW_CLIENTONLY | PW_RENDERFULLCONTENT) reads the window's OWN buffer, so the
# capture is occlusion-independent — RetroArch can sit behind log/editor windows and still
# be read (matches the macOS screencapture -l behavior). Works with RetroArch's Vulkan/GL
# renderer, where plain PrintWindow returns black. Window is matched by class (the emulator's
# is "RetroArch"), so an Explorer folder that happens to be named "RetroArch..." is ignored.
_user32_cache = None
_gdi32_cache = None


def _user32():
    """Cache user32 with argtypes set — Python ints must reach HWND/HDC params as pointers
    (c_void_p), not truncated 32-bit c_int, on Win64."""
    global _user32_cache
    if _user32_cache is not None:
        return _user32_cache
    import ctypes
    from ctypes import wintypes
    u = ctypes.windll.user32
    u.IsWindowVisible.argtypes = [wintypes.HWND]
    u.IsWindowVisible.restype = wintypes.BOOL
    u.GetWindowTextLengthW.argtypes = [wintypes.HWND]
    u.GetWindowTextLengthW.restype = ctypes.c_int
    u.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    u.GetWindowTextW.restype = ctypes.c_int
    u.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    u.GetClassNameW.restype = ctypes.c_int
    u.GetClientRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
    u.GetClientRect.restype = wintypes.BOOL
    u.GetDC.argtypes = [wintypes.HWND]
    u.GetDC.restype = wintypes.HDC
    u.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]
    u.PrintWindow.argtypes = [wintypes.HWND, wintypes.HDC, wintypes.UINT]
    u.PrintWindow.restype = wintypes.BOOL
    _user32_cache = u
    return u


def _gdi32():
    """Cache gdi32 with argtypes set (handles are pointers — must not truncate on Win64)."""
    global _gdi32_cache
    if _gdi32_cache is not None:
        return _gdi32_cache
    import ctypes
    from ctypes import wintypes
    g = ctypes.windll.gdi32
    g.CreateCompatibleDC.argtypes = [wintypes.HDC]
    g.CreateCompatibleDC.restype = wintypes.HDC
    g.CreateCompatibleBitmap.argtypes = [wintypes.HDC, ctypes.c_int, ctypes.c_int]
    g.CreateCompatibleBitmap.restype = wintypes.HBITMAP
    g.SelectObject.argtypes = [wintypes.HDC, wintypes.HGDIOBJ]
    g.SelectObject.restype = wintypes.HGDIOBJ
    g.GetDIBits.argtypes = [wintypes.HDC, wintypes.HBITMAP, ctypes.c_uint, ctypes.c_uint,
                            ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint]
    g.GetDIBits.restype = ctypes.c_int
    g.DeleteObject.argtypes = [wintypes.HGDIOBJ]
    g.DeleteDC.argtypes = [wintypes.HDC]
    _gdi32_cache = g
    return g


def _pick_hwnd(candidates, match: str):
    """Choose the target window. `candidates` = [(hwnd, title, cls, width, height)].
    Windows whose CLASS contains `match` win over title-only matches (the emulator's class
    is "RetroArch"; an Explorer folder titled "RetroArch..." has class "CabinetWClass").
    Among the winning pool, the largest by area. Returns the hwnd, or None."""
    m = match.lower()
    by_class = [c for c in candidates if m in (c[2] or "").lower()]
    by_title = [c for c in candidates if m in (c[1] or "").lower()]
    pool = by_class or by_title
    if not pool:
        return None
    return max(pool, key=lambda c: c[3] * c[4])[0]


def _enum_windows_windows():
    """Every visible top-level window as (hwnd, title, class, client_w, client_h)."""
    import ctypes
    from ctypes import wintypes
    u = _user32()
    out = []
    WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def _cb(hwnd, _lparam):
        if u.IsWindowVisible(hwnd):
            n = u.GetWindowTextLengthW(hwnd)
            title = ctypes.create_unicode_buffer(n + 1)
            u.GetWindowTextW(hwnd, title, n + 1)
            cls = ctypes.create_unicode_buffer(256)
            u.GetClassNameW(hwnd, cls, 256)
            rect = wintypes.RECT()
            u.GetClientRect(hwnd, ctypes.byref(rect))
            out.append((hwnd, title.value, cls.value,
                        rect.right - rect.left, rect.bottom - rect.top))
        return True

    u.EnumWindows(WNDENUMPROC(_cb), 0)
    return out


def _ensure_dpi_aware() -> None:
    """Make the process DPI-aware so GetClientRect returns native (physical) pixels — a
    scaled display would otherwise yield a smaller, blurrier capture. Best-effort, idempotent."""
    import ctypes
    for attempt in (
        lambda: ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4)),
        lambda: ctypes.windll.shcore.SetProcessDpiAwareness(2),  # PER_MONITOR_DPI_AWARE
        lambda: ctypes.windll.user32.SetProcessDPIAware(),
    ):
        try:
            attempt()
            return
        except Exception:
            continue


def _printwindow_client(hwnd) -> Image.Image:
    """Capture a window's client area into a PIL image via PrintWindow + GetDIBits."""
    import ctypes
    from ctypes import wintypes
    u, g = _user32(), _gdi32()

    class _BMIH(ctypes.Structure):
        _fields_ = [("biSize", wintypes.DWORD), ("biWidth", wintypes.LONG),
                    ("biHeight", wintypes.LONG), ("biPlanes", wintypes.WORD),
                    ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD),
                    ("biSizeImage", wintypes.DWORD), ("biXPelsPerMeter", wintypes.LONG),
                    ("biYPelsPerMeter", wintypes.LONG), ("biClrUsed", wintypes.DWORD),
                    ("biClrImportant", wintypes.DWORD)]

    rect = wintypes.RECT()
    u.GetClientRect(hwnd, ctypes.byref(rect))
    w, h = rect.right, rect.bottom
    if w <= 0 or h <= 0:
        raise RuntimeError("target window has an empty client area (minimized?).")

    hdc = u.GetDC(hwnd)
    memdc = g.CreateCompatibleDC(hdc)
    bmp = g.CreateCompatibleBitmap(hdc, w, h)
    old = g.SelectObject(memdc, bmp)
    try:
        PW_CLIENTONLY, PW_RENDERFULLCONTENT = 0x1, 0x2
        if not u.PrintWindow(hwnd, memdc, PW_CLIENTONLY | PW_RENDERFULLCONTENT):
            raise RuntimeError("PrintWindow failed (window not renderable?).")
        bmi = _BMIH()
        bmi.biSize = ctypes.sizeof(_BMIH)
        bmi.biWidth, bmi.biHeight = w, -h           # negative height = top-down rows
        bmi.biPlanes, bmi.biBitCount, bmi.biCompression = 1, 32, 0  # BI_RGB
        buf = (ctypes.c_char * (w * h * 4))()
        if not g.GetDIBits(memdc, bmp, 0, h, buf, ctypes.byref(bmi), 0):  # DIB_RGB_COLORS
            raise RuntimeError("GetDIBits failed.")
        return Image.frombuffer("RGB", (w, h), bytes(buf), "raw", "BGRX", 0, 1)
    finally:
        g.SelectObject(memdc, old)
        g.DeleteObject(bmp)
        g.DeleteDC(memdc)
        u.ReleaseDC(hwnd, hdc)


def _grab_window_windows(match: str) -> Image.Image:
    """Windows: capture the client area of the window whose class (preferred) or title
    contains `match`, via PrintWindow — occlusion-independent, so RetroArch need not be
    foreground."""
    _ensure_dpi_aware()
    hwnd = _pick_hwnd(_enum_windows_windows(), match)
    if hwnd is None:
        raise RuntimeError(
            f"No visible window matching {match!r} found. Is RetroArch running and not "
            "minimized? Set world.vision.window to match its window class or title."
        )
    return _printwindow_client(hwnd)


def capture_region(bbox: tuple[int, int, int, int] | None = None,
                   backend: str = "auto", window: str = "RetroArch") -> Image.Image:
    """Capture a screen rectangle, the whole display, or a specific window.

    backend:
      'auto'          — screencapture on macOS, ImageGrab elsewhere (uses bbox)
      'screencapture' — macOS rectangle capture (uses bbox)
      'imagegrab'     — Pillow ImageGrab (uses bbox)
      'window'        — capture the window whose title/owner contains `window`
                        (ignores bbox; move/resize-independent). macOS grabs the whole
                        window; Windows grabs its client area.
    """
    if backend == "auto":
        backend = "screencapture" if sys.platform == "darwin" else "imagegrab"
    if backend == "screencapture":
        return _grab_screencapture(bbox)
    if backend == "imagegrab":
        return _grab_imagegrab(bbox)
    if backend == "window":
        return _grab_window(window)
    raise ValueError(
        f"unknown capture backend {backend!r} "
        "(expected 'auto', 'screencapture', 'imagegrab', or 'window')"
    )


def crop_norm(img: Image.Image, box: tuple[float, float, float, float]) -> Image.Image:
    """Crop a normalized (x, y, w, h) box (top-left origin) out of img."""
    w, h = img.size
    x0, y0, bw, bh = box
    return img.crop((int(x0 * w), int(y0 * h), int((x0 + bw) * w), int((y0 + bh) * h)))
