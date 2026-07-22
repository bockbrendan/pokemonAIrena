"""vision — a Backend that plays REAL Pokemon Stadium on RetroArch, no RAM map.

**Turn model (live-verified 2026-07-22).** A Stadium turn is a "diamond": at a
decision point the game shows an action bar and lets you pick a move — or, when your
Pokemon faints, forces a party switch. Moves and switches are the SAME primitive:

    press "select" (Z) -> a pre-commit screen -> press the C-button for a diamond
    direction (up/down/left/right) to commit that cell.

To READ the options (move names, or party names) you HOLD "check" (R/W) to reveal the
diamond, capture, and OCR the four cells. The KB then classifies each name as a move
or a Pokemon — so the backend infers *what* is on offer from the screen rather than
hard-coding every game state. Directions map to fixed slots: 0=up 1=right 2=down 3=left.

**Reliability (all required, learned the hard way):** input goes out via
`world/keyboard.py` (CGEventPostToPid), with LONG holds, a PERSISTENT mouse-mover
(RetroArch throttles input/rendering when the cursor is idle), and RETRY-until-observed
(some presses are dropped). `MacKeyboard` owns the mouse-mover; this backend owns the
retries (it re-checks the screen after acting and re-tries until it changes).

Observe uses `vision/` (window capture auto-cropped to the game viewport + OCR); act
goes out through `world/keyboard.py`. `read_battle()` sees the same snapshot shape as
the mock. ⚠️ The diamond cell boxes in `vision/layout.py::MOVES`/`PARTY` still want a
live calibration pass against a real move/party diamond frame.
"""
from __future__ import annotations

import time

from battle.damage import battle_stats
from battle.state import Action
from kb import default_kb
from vision import layout as _layout
from vision.capture import capture_region
from vision.observe import (action_menu_open, battle_result, on_battle_screen,
                            read_moves, read_panels, read_party, switch_screen_open)

# Diamond slot -> D-pad direction (the C-button the actuator presses). Fixed order so a
# slot index the agent chose maps to one deterministic direction.
_SLOT_DIR = ("up", "right", "down", "left")


class VisionBackend:
    """Observe Stadium via OCR (window capture), act via the diamond primitive. Reads
    whoever is on screen through the KB — no config roster required."""

    def __init__(self, cfg: dict, ocr=None, keyboard=None):
        self.cfg = cfg
        self.kb = default_kb()
        self.level = cfg["world"].get("level", 50)
        v = cfg["world"].get("vision", {})
        self.region = tuple(v["region"]) if v.get("region") else None
        self._ocr = ocr
        self._kb_input = keyboard
        self.reset()

    def reset(self) -> None:
        self._self = None   # {dex, name, max_hp, hp, moves:[{name,pp,slot}]}
        self._opp = None
        self._party: list[dict] = []
        self._awaiting: str | None = None      # "move" | "switch"
        self.pending: Action | None = None
        self._done = False
        self._winner: str | None = None        # "self" | "opponent" | None (unknown)
        self._off_screen = 0                   # consecutive non-battle frames (end debounce)

    # ---- dependencies (lazy on real runs) ----------------------------------
    def _ocr_engine(self):
        if self._ocr is None:
            from vision.ocr import default_ocr
            self._ocr = default_ocr(self.cfg["world"].get("vision", {}).get("ocr", "auto"))
        return self._ocr

    def _keyboard(self):
        if self._kb_input is None:
            from world.keyboard import make_keyboard
            kb = make_keyboard(self.cfg["world"].get("vision", {}).get("keyboard", "auto"))
            kb.activate()
            self._kb_input = kb
        return self._kb_input

    def _frame(self):
        v = self.cfg["world"].get("vision", {})
        return capture_region(self.region, v.get("capture", "auto"), v.get("window", "RetroArch"))

    # ---- observe -----------------------------------------------------------
    def awaiting_input(self) -> bool:
        """A decision is needed when either the action bar (move turn) or the forced-
        switch screen (a Pokemon fainted) is up — inferred from on-screen prompts."""
        if self._done:
            return False
        frame, ocr = self._frame(), self._ocr_engine()
        return (action_menu_open(frame, ocr, self.kb, _layout.ACTION)
                or switch_screen_open(frame, ocr, self.kb, _layout.ACTION))

    def _mon(self, o: dict, attr: str) -> None:
        """Build/refresh a cached active from an OCR'd {name, hp, max_hp} via the KB."""
        cur = getattr(self, attr)
        name = o.get("name")
        if name:
            sp = self.kb.species(name)
            max_hp = battle_stats(sp["base"], self.level)["hp"]
            same = cur is not None and cur["name"] == name
            hp = o["hp"] if o.get("hp") is not None else (cur["hp"] if same else max_hp)
            setattr(self, attr, {
                "dex": sp["dex"], "name": name, "max_hp": max_hp,
                "hp": max(0, min(max_hp, hp)),
                "moves": cur["moves"] if same else [],
            })
        elif cur is not None and o.get("hp") is not None:
            cur["hp"] = max(0, min(cur["max_hp"], o["hp"]))

    def _move_entry(self, name: str, slot: int) -> dict:
        m = self.kb.move(name)
        return {"name": name, "pp": m["pp"], "slot": slot}

    def _peek_moves(self) -> list[str]:
        """Reveal the move diamond (Z to open, HOLD Check) and OCR its cells; then Cancel
        back to the action bar so `step` starts clean. Names in slot order (skips empties)."""
        kbd, v = self._keyboard(), self.cfg["world"].get("vision", {})
        kbd.press("select")                                   # Z: action bar -> pre-commit
        time.sleep(v.get("menu_wait", 0.6))
        kbd._down("check")                                    # hold R/W to show the names
        time.sleep(v.get("menu_wait", 0.6))
        names = read_moves(self._frame(), self._ocr_engine(), self.kb, _layout.MOVES)
        kbd._up("check")
        kbd.press("cancel")                                   # L: back to the action bar
        time.sleep(v.get("menu_wait", 0.6))
        return names

    def _peek_party(self) -> list[dict]:
        """On the forced-switch screen, HOLD Check to reveal the party diamond and OCR it.
        Returns [{name, hp, max_hp}] for the bench (fainted mon excluded by the caller)."""
        kbd, v = self._keyboard(), self.cfg["world"].get("vision", {})
        kbd._down("check")
        time.sleep(v.get("menu_wait", 0.6))
        party = read_party(self._frame(), self._ocr_engine(), self.kb, _layout.PARTY)
        kbd._up("check")
        return party

    def snapshot(self) -> dict:
        frame, ocr = self._frame(), self._ocr_engine()
        # Which decision is this? A move turn (action bar) or a forced switch (faint)?
        forced_switch = (switch_screen_open(frame, ocr, self.kb, _layout.ACTION)
                         and not action_menu_open(frame, ocr, self.kb, _layout.ACTION))
        panels = read_panels(frame, ocr, self.kb, _layout.ACTION)
        self._mon(panels["self"], "_self")
        self._mon(panels["opp"], "_opp")
        if self._self is None or self._opp is None:
            raise RuntimeError(
                "Could not read both Pokémon from the panels — calibrate "
                "self_name/opp_name in vision/layout.py (ACTION)."
            )

        if forced_switch:
            self._awaiting = "switch"
            self._party = self._peek_party()
            if self._party and not any((p.get("hp") or 0) > 0 for p in self._party):
                self._done, self._winner = True, "opponent"     # nothing left to send out
        else:
            self._awaiting = "move"
            if not self._self["moves"]:                        # cache: only re-read when unknown
                names = self._peek_moves()
                self._self["moves"] = [self._move_entry(n, i) for i, n in enumerate(names)]
        return self._build_snapshot()

    def _party_view(self, p: dict) -> dict:
        sp = self.kb.species(p["name"])
        max_hp = battle_stats(sp["base"], self.level)["hp"]
        hp = p.get("hp")
        hp = 0 if hp is None else max(0, min(max_hp, hp))   # unreadable HP -> treat as fainted
        return {"dex": sp["dex"], "hp": hp, "max_hp": max_hp, "status": None}

    def _build_snapshot(self) -> dict:
        me, opp = self._self, self._opp
        return {
            "awaiting": self._awaiting if (me["moves"] or self._awaiting == "switch") else None,
            "self": {
                "dex": me["dex"], "hp": me["hp"], "max_hp": me["max_hp"], "status": None,
                "stages": {},
                "moves": [{"name": mv["name"], "pp": mv["pp"]} for mv in me["moves"]],
            },
            "self_party": [self._party_view(p) for p in self._party],
            "opp": {"dex": opp["dex"], "hp": opp["hp"], "max_hp": opp["max_hp"], "status": None},
        }

    # ---- act ---------------------------------------------------------------
    def send_action(self, action: Action) -> None:
        self.pending = action

    def _direction_for(self, action: Action) -> str:
        """Diamond direction for the chosen move slot / party index. Moves keep their slot;
        a switch's party index maps 1:1 to the same fixed slot order."""
        idx = action.index
        if action.kind == "move" and idx < len(self._self["moves"]):
            idx = self._self["moves"][idx]["slot"]
        return _SLOT_DIR[idx % 4]

    def step(self) -> None:
        """Commit the queued move/switch via the diamond primitive, retrying until the
        screen changes (input is flaky). With nothing queued, poll-sleep."""
        v = self.cfg["world"].get("vision", {})
        action, self.pending = self.pending, None
        if action is None:
            time.sleep(v.get("poll", 0.3))
            return
        direction = self._direction_for(action)
        kbd, ocr = self._keyboard(), self._ocr_engine()
        before = read_panels(self._frame(), ocr, self.kb, _layout.ACTION)
        for _ in range(v.get("act_retries", 5)):
            kbd.diamond_select(direction)
            time.sleep(v.get("turn_wait", 4.0))
            after = read_panels(self._frame(), ocr, self.kb, _layout.ACTION)
            if self._changed(before, after):                  # committed -> turn resolved
                break
        self._self["moves"] = [] if action.kind == "switch" else self._self["moves"]

    @staticmethod
    def _changed(before: dict, after: dict) -> bool:
        """The action took effect if HP moved or a Pokémon was swapped in/out."""
        for side in ("self", "opp"):
            b, a = before[side], after[side]
            if a.get("name") and b.get("name") and a["name"] != b["name"]:
                return True
            if a.get("hp") is not None and b.get("hp") is not None and a["hp"] != b["hp"]:
                return True
        return False

    # ---- close out ---------------------------------------------------------
    def is_over(self) -> bool:
        """Battle end. Once set, stays set. Otherwise DEBOUNCE on leaving the battle
        screens: when the game is no longer showing the action bar / a forced switch /
        both HP panels for `end_polls` consecutive checks, the battle has ended (result
        screen). ⚠️ Winner is only known for sure in the forced-switch-with-no-party case;
        the result-SCREEN itself (win vs loss text) still needs a live calibration pass —
        `max_turns` remains the backstop."""
        if self._done:
            return True
        v = self.cfg["world"].get("vision", {})
        frame, ocr = self._frame(), self._ocr_engine()
        winner = battle_result(frame, ocr)                 # the WIN/LOSE result screen
        if winner is not None:
            self._done, self._winner = True, winner
            return True
        if on_battle_screen(frame, ocr, self.kb, _layout.ACTION):
            self._off_screen = 0
        else:                                              # debounce fallback
            self._off_screen += 1
            if self._off_screen >= v.get("end_polls", 5):
                self._done = True
        return self._done

    def result(self) -> dict:
        return {"winner": self._winner, "player_remaining": None,
                "opponent_remaining": None}
