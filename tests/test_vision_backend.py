"""VisionBackend logic for the diamond turn model — decision detection (action bar vs
forced switch), reading BOTH actives off the panels (via the KB, so any of the 151 works),
peeking the move diamond, and committing via the diamond_select primitive. Fake OCR + fake
keyboard, no emulator/screen/engine."""
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
    c["world"]["vision"].update({"menu_wait": 0, "turn_wait": 0, "poll": 0,
                                 "act_retries": 1, "end_polls": 2})
    return c


class _SeqOCR:
    """Canned text per recognize() call, in call order (repeats the last when spent)."""
    def __init__(self, texts):
        self._texts, self._i = list(texts), 0

    def recognize(self, _img):
        from vision.ocr import OCRResult
        t = self._texts[min(self._i, len(self._texts) - 1)]
        self._i += 1
        return [OCRResult(t, 0.9, (0.0, 0.0, 1.0, 1.0))]


class _FakeKeyboard:
    def __init__(self):
        self.presses = []
        self.selects = []           # diamond_select() directions

    def press(self, button, hold=0.0): self.presses.append(button)
    def hold(self, button, dur=0.0): self.presses.append(("hold", button))
    def _down(self, button): self.presses.append(("down", button))
    def _up(self, button): self.presses.append(("up", button))
    def diamond_select(self, direction, settle=0.0): self.selects.append(direction)
    def tap_sequence(self, buttons, gap=0.0): self.presses.append(list(buttons))


# snapshot() OCRs in this order: the action bar (switch_screen_open short-circuits on a
# move turn), then panels (self_name, self_hp, opp_name, opp_hp), then the move diamond
# (move_0..3).
_BAR = "A BATTLE B POKEMON S RUN"
_SNAP = [_BAR, "ODDISH", "125 / 125", "CLEFAIRY", "150 / 150",
         "Razor Leaf", "Mega Drain", "Sludge", "Body Slam"]


def _backend(texts, kb=None):
    b = VisionBackend(_cfg(), ocr=_SeqOCR(texts), keyboard=kb or _FakeKeyboard())
    b._frame = lambda: Image.new("RGB", (16, 16))
    return b


def test_action_menu_detected():
    assert _backend([_BAR]).awaiting_input() is True
    assert _backend([""]).awaiting_input() is False


def test_forced_switch_detected():
    # Bar shows only "R Check" (no BATTLE / Cancel) after a faint -> a decision is needed.
    assert _backend(["R CHECK"]).awaiting_input() is True


def test_snapshot_reads_both_actives_from_the_screen():
    # Clefairy/Oddish aren't in config's teams — resolved purely via the KB (all 151).
    state = read_battle(_backend(_SNAP), default_kb(), level=50)
    assert state.self_active.name == "Oddish" and state.self_active.hp == 125
    assert state.opp_active.name == "Clefairy" and state.opp_active.hp == 150


def test_snapshot_reads_moves_from_diamond():
    state = read_battle(_backend(_SNAP), default_kb(), level=50)
    assert [state.self_active.moves[i].name for i in state.available_moves] == \
        ["Razor Leaf", "Mega Drain", "Sludge", "Body Slam"]


def test_snapshot_peeks_moves_with_select_then_check():
    kb = _FakeKeyboard()
    _backend(_SNAP, kb=kb).snapshot()
    assert "select" in kb.presses                 # Z opens the pre-commit screen
    assert ("down", "check") in kb.presses        # Check held to reveal the diamond


def test_move_action_commits_via_diamond_select():
    kb = _FakeKeyboard()
    b = _backend(_SNAP, kb=kb)
    b.snapshot()                                  # populate actives + moves
    b.send_action(Action("move", 2))              # slot 2 -> down (index 2 in up,right,down,left)
    b.step()
    assert kb.selects[-1] == "down"


def test_still_on_battle_screen_is_not_over():
    assert _backend([_BAR]).is_over() is False


def test_battle_ends_after_leaving_the_battle_screens():
    # A settled non-battle screen (no bar, no panels) for end_polls checks -> battle over.
    b = _backend([""])                            # empty/result screen
    for _ in range(b.cfg["world"]["vision"]["end_polls"]):
        b.is_over()
    assert b.is_over() is True
