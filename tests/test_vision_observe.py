"""Vision observe logic — name matching + HP parsing — with a stub OCR (fast).

The real Vision engine is exercised in test_ocr.py; here we lock down the parsing
and KB fuzzy-matching that turn noisy OCR strings into a clean observation.
"""
from __future__ import annotations

from PIL import Image

from kb import default_kb
from vision.observe import match_species, read_screen


def test_match_species_exact_and_case():
    kb = default_kb()
    assert match_species("STARMIE", kb) == "Starmie"
    assert match_species("snorlax", kb) == "Snorlax"


def test_match_species_tolerates_ocr_errors():
    kb = default_kb()
    assert match_species("STARMlE", kb) == "Starmie"   # OCR reads I as l
    assert match_species("ALAKAZ4M", kb) == "Alakazam"  # 4 for A


def test_match_species_rejects_noise():
    kb = default_kb()
    assert match_species("", kb) is None
    assert match_species("####", kb) is None


class _FakeOCR:
    """Returns canned text per recognize() call, in the order read_screen asks."""
    def __init__(self, texts):
        self._texts = list(texts)
        self._i = 0

    def recognize(self, _img, _mode="line"):
        from vision.ocr import OCRResult
        t = self._texts[self._i]
        self._i += 1
        return [OCRResult(t, 0.9, (0.0, 0.0, 1.0, 1.0))]


def test_read_screen_extracts_names_and_hp():
    kb = default_kb()
    # read_screen queries regions in this order: self_hp, self_name, opp_name.
    ocr = _FakeOCR(["46 / 166", "STARMIE", "SNORLAX"])
    obs = read_screen(img=Image.new("RGB", (100, 100)), ocr=ocr, kb=kb)
    assert obs["self"] == {"name": "Starmie", "hp": 46, "max_hp": 166}
    assert obs["opp"]["name"] == "Snorlax"
