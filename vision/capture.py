"""Screen capture for the vision path — cross-platform, two backends behind
capture_region():

  * screencapture — macOS built-in CLI (no dependency).
  * imagegrab     — Pillow ImageGrab (Windows + macOS; Pillow is already a vision dep).

'auto' uses screencapture on macOS and ImageGrab elsewhere (Windows). Force either via
config world.vision.capture. crop_norm slices a normalized box out of an already-
captured frame — capture once per turn, crop many regions.
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


def capture_region(bbox: tuple[int, int, int, int] | None = None,
                   backend: str = "auto") -> Image.Image:
    """Capture a screen rectangle (x, y, w, h) in points, or the whole display.

    backend: 'auto' (screencapture on macOS, ImageGrab elsewhere) | 'screencapture' | 'imagegrab'.
    """
    if backend == "auto":
        backend = "screencapture" if sys.platform == "darwin" else "imagegrab"
    if backend == "screencapture":
        return _grab_screencapture(bbox)
    if backend == "imagegrab":
        return _grab_imagegrab(bbox)
    raise ValueError(
        f"unknown capture backend {backend!r} (expected 'auto', 'screencapture', or 'imagegrab')"
    )


def crop_norm(img: Image.Image, box: tuple[float, float, float, float]) -> Image.Image:
    """Crop a normalized (x, y, w, h) box (top-left origin) out of img."""
    w, h = img.size
    x0, y0, bw, bh = box
    return img.crop((int(x0 * w), int(y0 * h), int((x0 + bw) * w), int((y0 + bh) * h)))
