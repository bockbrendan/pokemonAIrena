"""Move-menu OCR: fuzzy move matching, reading the 4 slots into KB move names, the
KB-miss error, and the lenient turn detector. Stub OCR, no screen, no engine."""
from __future__ import annotations

import pytest
from PIL import Image

from kb import default_kb
from vision.observe import UnknownMoveError, match_move, menu_open, read_moves


class _SlotOCR:
    """Returns one canned string per recognize() call, in slot order (move_0..3)."""
    def __init__(self, slots):
        self._slots = list(slots)
        self._i = 0

    def recognize(self, _img, _mode="line"):
        from vision.ocr import OCRResult
        t = self._slots[self._i] if self._i < len(self._slots) else ""
        self._i += 1
        return [OCRResult(t, 0.9, (0.0, 0.0, 1.0, 1.0))]


_IMG = Image.new("RGB", (16, 16))


def test_match_move_exact_and_case():
    kb = default_kb()
    assert match_move("Surf", kb) == "Surf"
    assert match_move("HYPER BEAM", kb) == "Hyper Beam"      # case-insensitive, keeps space


def test_match_move_tolerates_ocr_slips():
    kb = default_kb()
    assert match_move("Blizzurd", kb) == "Blizzard"          # a wrong letter
    assert match_move("", kb) is None
    assert match_move("Xyzzy", kb) is None                   # nothing close


def test_read_moves_resolves_all_four():
    kb = default_kb()
    ocr = _SlotOCR(["SURF", "BLIZZARD", "THUNDERBOLT", "PSYCHIC"])
    assert read_moves(_IMG, ocr, kb) == ["Surf", "Blizzard", "Thunderbolt", "Psychic"]


def test_read_moves_skips_empty_slots():
    kb = default_kb()
    ocr = _SlotOCR(["Body Slam", "Earthquake", "", ""])       # a 2-move mon
    assert read_moves(_IMG, ocr, kb) == ["Body Slam", "Earthquake"]


def test_unknown_move_raises_with_actionable_message():
    kb = default_kb()
    ocr = _SlotOCR(["Surf", "Toxic", "", ""])                # Toxic isn't in the KB subset
    with pytest.raises(UnknownMoveError) as exc:
        read_moves(_IMG, ocr, kb)
    msg = str(exc.value)
    assert "Toxic" in msg and "kb/moves.json" in msg and "move_1" in msg


def test_menu_open_detects_and_rejects():
    kb = default_kb()
    assert menu_open(_IMG, _SlotOCR(["Surf", "", "", ""]), kb) is True
    assert menu_open(_IMG, _SlotOCR(["", "", "", ""]), kb) is False
    # Non-menu screen with junk text must NOT be mistaken for the menu, and must not raise.
    assert menu_open(_IMG, _SlotOCR(["12/166", "STARMIE", "", ""]), kb) is False
