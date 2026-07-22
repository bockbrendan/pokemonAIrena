"""OCR over the emulator screen — the vision path to battle state.

Two interchangeable engines behind one `recognize(img) -> list[OCRResult]` shape
(normalized, top-left-origin boxes):
  * VisionOCR   — Apple Vision framework (macOS only; on-device, strong on stylized
    game fonts, no external binary).
  * TesseractOCR — Tesseract via pytesseract (cross-platform: Windows/Linux/macOS).

`default_ocr(engine)` picks one: 'auto' uses Apple Vision on macOS and falls back to
Tesseract elsewhere; force with 'vision' or 'tesseract'. This is the observe layer
for the "read the screen like a human" approach — no RAM map required. It gives you
what's printed (names, HP numbers); the KB supplies the rest from the recognized name.
"""
from __future__ import annotations

import io
from dataclasses import dataclass

from PIL import Image, ImageOps


@dataclass(frozen=True)
class OCRResult:
    text: str
    confidence: float
    bbox: tuple[float, float, float, float]   # (x, y, w, h), normalized, top-left origin


class VisionOCR:
    """Apple Vision VNRecognizeTextRequest. Language correction off (game text)."""

    def __init__(self) -> None:
        import Quartz
        import Vision
        from Foundation import NSData
        self._Quartz = Quartz
        self._Vision = Vision
        self._NSData = NSData

    def _cgimage(self, img: Image.Image):
        buf = io.BytesIO()
        img.convert("RGB").save(buf, "PNG")
        raw = buf.getvalue()
        data = self._NSData.dataWithBytes_length_(raw, len(raw))
        src = self._Quartz.CGImageSourceCreateWithData(data, None)
        return self._Quartz.CGImageSourceCreateImageAtIndex(src, 0, None)

    def recognize(self, img: Image.Image, mode: str = "line") -> list[OCRResult]:
        V = self._Vision
        cg = self._cgimage(img)   # mode is a Tesseract hint; Vision reads game fonts natively
        req = V.VNRecognizeTextRequest.alloc().init()
        req.setRecognitionLevel_(V.VNRequestTextRecognitionLevelAccurate)
        req.setUsesLanguageCorrection_(False)
        handler = V.VNImageRequestHandler.alloc().initWithCGImage_options_(cg, {})
        ok, _err = handler.performRequests_error_([req], None)
        if not ok:
            return []
        out: list[OCRResult] = []
        for obs in (req.results() or []):
            cand = obs.topCandidates_(1)
            if not cand:
                continue
            top = cand[0]
            r = obs.boundingBox()   # normalized, bottom-left origin
            x, y, w, h = r.origin.x, r.origin.y, r.size.width, r.size.height
            out.append(OCRResult(
                text=str(top.string()),
                confidence=float(top.confidence()),
                bbox=(x, 1.0 - y - h, w, h),   # flip to top-left origin
            ))
        return out


def _normalize_tesseract(data: dict, size: tuple[int, int]) -> list[OCRResult]:
    """pytesseract image_to_data (DICT) -> OCRResults with normalized top-left boxes.

    Tesseract confidence is 0-100 (or -1 for a non-text box); pixel coords are already
    top-left origin, so we just scale by the image size."""
    w, h = size
    out: list[OCRResult] = []
    for i in range(len(data["text"])):
        text = (data["text"][i] or "").strip()
        conf = float(data["conf"][i])
        if not text or conf < 0:          # conf == -1 marks a box with no text
            continue
        x, y, bw, bh = data["left"][i], data["top"][i], data["width"][i], data["height"][i]
        out.append(OCRResult(
            text=text,
            confidence=conf / 100.0,
            bbox=(x / w, y / h, bw / w, bh / h),
        ))
    return out


def _otsu_threshold(gray: Image.Image) -> int:
    """Otsu's method: the 0-255 split that maximizes between-class variance. Pure PIL
    (histogram), no numpy — adapts the binarization cut to each crop's own contrast."""
    hist = gray.histogram()[:256]
    total = sum(hist)
    sum_total = sum(i * hist[i] for i in range(256))
    sum_b = weight_b = best_var = threshold = 0
    for t in range(256):
        weight_b += hist[t]
        if weight_b == 0:
            continue
        weight_f = total - weight_b
        if weight_f == 0:
            break
        sum_b += t * hist[t]
        mean_b = sum_b / weight_b
        mean_f = (sum_total - sum_b) / weight_f
        var = weight_b * weight_f * (mean_b - mean_f) ** 2
        if var > best_var:
            best_var, threshold = var, t
    return threshold


def _prep_tesseract(img: Image.Image, mode: str, scale: int) -> Image.Image:
    """Isolate Stadium's light text for Tesseract. The RED channel is bright for white
    text yet dark for BOTH the blue (self) and green (opp) HP panels, so it separates
    text from panel colour far better than luminance. Upscale with NEAREST (keeps the
    pixel-font edges crisp) + autocontrast. Single-word reads (species names) add an
    Otsu binarization, which sharpens the letters; line reads (HP, moves, the action
    bar) skip it, because a hard threshold swallows the thin '/' between HP numbers."""
    red = img.convert("RGB").split()[0]
    big = red.resize((red.width * scale, red.height * scale), Image.NEAREST)
    big = ImageOps.autocontrast(big)
    if mode == "word":
        cut = _otsu_threshold(big)
        big = big.point(lambda p: 255 if p > cut else 0)
    return big


class TesseractOCR:
    """Tesseract via pytesseract — cross-platform (Windows / Linux / macOS), preprocessed
    for Stadium's stylized on-screen text (see `_prep_tesseract`).

    Needs the Tesseract binary on PATH plus `pip install pytesseract pillow`. recognize()
    takes a `mode`: 'line' (--psm 7, a text line — move names, the action bar), 'word'
    (--psm 8 + Otsu, a single species name), or 'number' (--psm 7 + a digit/'/' whitelist,
    HP counters — stops '124' being read as letters like 'IZ4')."""

    _PSM = {"line": 7, "word": 8, "number": 7}

    # 5x upscale — at 4x the blurry blue-panel "2" in a self-HP "124" was dropped ("14");
    # 5x reads it reliably. (Over-reads still clamp to the KB max in VisionBackend.)
    def __init__(self, scale: int = 5) -> None:
        import pytesseract
        self._pt = pytesseract
        self._scale = scale

    def recognize(self, img: Image.Image, mode: str = "line") -> list[OCRResult]:
        prepped = _prep_tesseract(img, mode, self._scale)
        config = f"--psm {self._PSM.get(mode, 7)}"
        if mode == "number":
            config += " -c tessedit_char_whitelist=0123456789/"
        data = self._pt.image_to_data(
            prepped, config=config, output_type=self._pt.Output.DICT)
        return _normalize_tesseract(data, prepped.size)


_VISION_HELP = (
    "Apple Vision OCR unavailable (macOS only). Install the bridge:\n"
    "  pip install pyobjc-framework-Vision pyobjc-framework-Quartz"
)
_TESSERACT_HELP = (
    "Tesseract OCR unavailable. Install the binary and the Python binding:\n"
    "  Windows: winget install UB-Mannheim.TesseractOCR   (or `choco install tesseract`)\n"
    "  macOS:   brew install tesseract\n"
    "  Linux:   apt-get install tesseract-ocr\n"
    "  then:    pip install pytesseract"
)


def default_ocr(engine: str = "auto"):
    """Pick an OCR engine. 'auto' = Apple Vision on macOS, Tesseract elsewhere; force
    with 'vision' or 'tesseract'. Raises with install guidance if the choice is unmet."""
    if engine not in ("auto", "vision", "tesseract"):
        raise ValueError(f"unknown OCR engine {engine!r} (expected 'auto', 'vision', or 'tesseract')")

    tried = []
    if engine in ("auto", "vision"):
        try:
            return VisionOCR()
        except Exception as exc:  # pragma: no cover - environment dependent
            if engine == "vision":
                raise RuntimeError(f"{_VISION_HELP}\n(import failed: {exc})") from exc
            tried.append(f"vision: {exc}")
    if engine in ("auto", "tesseract"):
        try:
            return TesseractOCR()
        except Exception as exc:  # pragma: no cover - environment dependent
            if engine == "tesseract":
                raise RuntimeError(f"{_TESSERACT_HELP}\n(import failed: {exc})") from exc
            tried.append(f"tesseract: {exc}")
    raise RuntimeError(
        "No OCR engine available.\n  " + "\n  ".join(tried)
        + f"\n\n{_VISION_HELP}\n\n{_TESSERACT_HELP}"
    )
