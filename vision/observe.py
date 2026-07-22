"""read_screen() — the vision observe. Turn a captured battle frame into the main
components: who's out and your HP. OCR reads the pixels; the KB resolves the noisy
name string to a real species (and, downstream, its types and base stats).

This is the OCR-first milestone: names + HP now, the full battle struct later.
"""
from __future__ import annotations

import re
from difflib import get_close_matches

from kb import KB
from vision import layout as _layout
from vision.capture import crop_norm

_HP = re.compile(r"(\d+)\s*[/il|\s.]\s*(\d+)")   # tolerate OCR misreads of '/' — as i/l/|, a
#                            dropped separator ("105 105"), or a period ("0. 130")

_MOVE_SLOTS = ("move_0", "move_1", "move_2", "move_3")


class UnknownMoveError(LookupError):
    """OCR read a move name in the menu that no KB entry matches — the KB is
    incomplete (or the move-slot region is misaligned). The message names the slot
    and the raw text so it's actionable."""


def _region_text(img, ocr, box) -> str:
    return " ".join(r.text for r in ocr.recognize(crop_norm(img, box))).strip()


def match_species(text: str, kb: KB) -> str | None:
    """Fuzzy-match an OCR'd name to a KB species (handles case + a few wrong letters)."""
    token = re.sub(r"[^A-Za-z]", "", text or "").title()
    if not token:
        return None
    hits = get_close_matches(token, list(kb.base_stats.keys()), n=1, cutoff=0.6)
    return hits[0] if hits else None


def match_move(text: str, kb: KB) -> str | None:
    """Fuzzy-match an OCR'd move label to a KB move key (case- and space-tolerant).

    Move names have spaces/hyphens (`Hyper Beam`, `Double-Edge`), so unlike species
    we keep separators and compare lowercased. Returns None if nothing is close."""
    token = re.sub(r"\s+", " ", (text or "").strip())
    if not token:
        return None
    keys_lower = {k.lower(): k for k in kb.moves}
    if token.lower() in keys_lower:
        return keys_lower[token.lower()]
    hits = get_close_matches(token.lower(), list(keys_lower), n=1, cutoff=0.6)
    return keys_lower[hits[0]] if hits else None


def read_moves(img, ocr, kb: KB, regions: dict | None = None) -> list[str]:
    """OCR the move-select menu -> KB move names, in slot order.

    Empty slots (a mon with <4 moves) are skipped. A slot with text that matches no
    KB move raises UnknownMoveError — fail loudly, because a mis-identified move makes
    every downstream decision (and keystroke) wrong."""
    R = regions or _layout.MOVES
    names: list[str] = []
    for slot in _MOVE_SLOTS:
        raw = _region_text(img, ocr, R[slot])
        if not raw.strip():
            continue
        matched = match_move(raw, kb)
        if matched is None:
            raise UnknownMoveError(
                f"Move OCR read {raw!r} in {slot}, but no move in kb/moves.json "
                f"matches it. Add the move (name, type, power, accuracy, pp) to "
                f"kb/moves.json, or fix the {slot} box in vision/layout.py."
            )
        names.append(matched)
    return names


def menu_open(img, ocr, kb: KB, regions: dict | None = None) -> bool:
    """Lenient turn detector: True if any move slot resolves to a KB move. Never
    raises (unlike read_moves) — used to decide *whether* the move menu is up."""
    R = regions or _layout.MOVES
    return any(match_move(_region_text(img, ocr, R[slot]), kb) for slot in _MOVE_SLOTS)


def read_panels(img, ocr, kb: KB, regions: dict) -> dict:
    """Read both sides' species + HP from the action-menu panels (both show HP there).

    recognize() call order per side: name, then hp — self first, then opp."""
    def side(pfx: str) -> dict:
        name = match_species(_region_text(img, ocr, regions[f"{pfx}_name"]), kb)
        hp = _HP.search(_region_text(img, ocr, regions[f"{pfx}_hp"]))
        return {
            "name": name,
            "hp": int(hp.group(1)) if hp else None,
            "max_hp": int(hp.group(2)) if hp else None,
        }
    return {"self": side("self"), "opp": side("opp")}


def action_menu_open(img, ocr, kb: KB, regions: dict | None = None) -> bool:
    """Turn detector: True when the battle action bar (BATTLE / POKéMON / RUN) shows.
    Robust to OCR slips — matches on the stable keywords in the bar region."""
    R = regions or _layout.ACTION
    text = _region_text(img, ocr, R["bar"]).upper()
    return "BATTLE" in text or "RUN" in text or "POK" in text


def switch_screen_open(img, ocr, kb: KB, regions: dict | None = None) -> bool:
    """Forced-switch detector: after a faint the bar shows only "R Check" (no BATTLE/RUN
    action bar, and no "Cancel" — the switch is mandatory). Distinguishes this from the
    move pre-commit screen, which shows BOTH "L Cancel" and "R Check"."""
    R = regions or _layout.ACTION
    text = _region_text(img, ocr, R["bar"]).upper()
    return "CHECK" in text and "CANCEL" not in text and "BATTLE" not in text and "RUN" not in text


def on_battle_screen(img, ocr, kb: KB, regions: dict) -> bool:
    """True while we're still in a battle: the action bar, a forced-switch prompt, or
    both HP panels are showing. False on a settled result/non-battle screen (used, with
    a debounce, to detect battle end). Cheap — reuses the ACTION bar + panel reads."""
    if action_menu_open(img, ocr, kb, regions) or switch_screen_open(img, ocr, kb, regions):
        return True
    panels = read_panels(img, ocr, kb, regions)
    return bool(panels["self"]["name"] and panels["opp"]["name"])


def read_party(img, ocr, kb: KB, regions: dict) -> list[dict]:
    """Read the forced-switch party diamond (revealed by holding Check) into a list of
    {name, hp, max_hp}, in DIAMOND-SLOT order (up, right, down, ...) so a slot index maps
    straight to a D-pad direction. Slots with no resolvable name are dropped (short teams).
    ⚠️ PARTY cell boxes want a live calibration pass."""
    out: list[dict] = []
    slots = sorted(k[:-5] for k in regions if k.endswith("_name"))   # slot_0, slot_1, ...
    for slot in slots:
        name = match_species(_region_text(img, ocr, regions[f"{slot}_name"]), kb)
        if not name:
            continue
        raw = _region_text(img, ocr, regions.get(f"{slot}_hp", (0, 0, 0, 0)))
        m = _HP.search(raw)
        if m:
            hp, max_hp = int(m.group(1)), int(m.group(2))
        else:
            # A fainted mon shows "0/124", but Apple Vision reads the leading 0 as the
            # letter O — catch that so a fainted Pokémon isn't mistaken for a healthy one.
            fnt = re.search(r"[O0]\s*[/il| .]\s*(\d+)", raw)
            hp = 0 if fnt else None
            max_hp = int(fnt.group(1)) if fnt else None
        out.append({"name": name, "hp": hp, "max_hp": max_hp})
    return out


def read_screen(img, ocr, kb: KB, regions: dict | None = None) -> dict:
    R = regions or _layout.BATTLE
    self_hp = _HP.search(_region_text(img, ocr, R["self_hp"]))
    return {
        "self": {
            "name": match_species(_region_text(img, ocr, R["self_name"]), kb),
            "hp": int(self_hp.group(1)) if self_hp else None,
            "max_hp": int(self_hp.group(2)) if self_hp else None,
        },
        "opp": {
            "name": match_species(_region_text(img, ocr, R["opp_name"]), kb),
        },
    }
