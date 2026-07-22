"""VisionBackend logic for the action-menu turn model — action-menu detection,
reading BOTH actives off the panels (via the KB, so any of the 151 works — not just
config teams), pressing A to open moves, reading them, and the move keystrokes. Fake
OCR + fake keyboard, no emulator/screen/engine."""
from __future__ import annotations

import yaml
from PIL import Image

from battle.observe import read_battle
from battle.state import Action
from kb import default_kb
from world.vision import VisionBackend


def _cfg():
    with open("config.yaml", encoding="utf-8") as f:
        c = yaml.safe_load(f)
    c["world"]["vision"].update({"menu_wait": 0, "turn_wait": 0, "poll": 0})  # no sleeps
    return c


class _SeqOCR:
    """Canned text per recognize() call, in call order (repeats the last when spent)."""
    def __init__(self, texts):
        self._texts, self._i = list(texts), 0

    def recognize(self, _img, _mode="line"):
        from vision.ocr import OCRResult
        t = self._texts[min(self._i, len(self._texts) - 1)]
        self._i += 1
        return [OCRResult(t, 0.9, (0.0, 0.0, 1.0, 1.0))]


class _FakeKeyboard:
    def __init__(self):
        self.presses = []

    def press(self, button, hold=0.0):
        self.presses.append([button])

    def tap_sequence(self, buttons, gap=0.0):
        self.presses.append(list(buttons))


# A full snapshot OCRs in this order: read_panels -> self_name, self_hp, opp_name,
# opp_hp; then read_moves -> move_0..move_3.
_SNAP = ["ODDISH", "125 / 125", "CLEFAIRY", "150 / 150",
         "Razor Leaf", "Mega Drain", "Sludge", "Body Slam"]


def _backend(texts, kb=None):
    b = VisionBackend(_cfg(), ocr=_SeqOCR(texts), keyboard=kb or _FakeKeyboard())
    b._frame = lambda: Image.new("RGB", (16, 16))
    return b


def test_action_menu_detected():
    b = _backend(["A BATTLE B POKEMON S RUN"])
    assert b.awaiting_input() is True
    b2 = _backend([""])
    assert b2.awaiting_input() is False


def test_snapshot_reads_both_actives_from_the_screen():
    # Clefairy/Oddish aren't in config's teams — resolved purely via the KB (all 151).
    b = _backend(_SNAP)
    state = read_battle(b, default_kb(), level=50)
    assert state.self_active.name == "Oddish" and state.self_active.hp == 125
    assert state.opp_active.name == "Clefairy" and state.opp_active.hp == 150


def test_snapshot_reads_moves_from_menu():
    b = _backend(_SNAP)
    state = read_battle(b, default_kb(), level=50)
    assert [state.self_active.moves[i].name for i in state.available_moves] == \
        ["Razor Leaf", "Mega Drain", "Sludge", "Body Slam"]


def test_snapshot_presses_a_to_open_moves():
    kb = _FakeKeyboard()
    b = _backend(_SNAP, kb=kb)
    b.snapshot()
    assert ["a"] in kb.presses          # BATTLE pressed to open the move list


def test_move_action_navigates_open_menu():
    kb = _FakeKeyboard()
    b = _backend(_SNAP, kb=kb)
    b.send_action(Action("move", 2))     # 3rd move
    b.step()
    assert kb.presses[-1] == ["down", "down", "a"]
