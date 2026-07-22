# pokemonAIrena — Handoff State

_A cold-start briefing: what this is, how it fits together, what works, and what's next._

> **⚠️ For the LIVE current state (2026-07-22), read [`HANDOFF.md`](HANDOFF.md).** This file
> describes the original RAM-map design; the project has since pivoted to a **vision + keyboard**
> approach on RetroArch, and that path now works end to end: observe (window-size-independent), the
> `z`→C-button "diamond" move/switch primitive, continuous-mouse + retry reliability, faint/switch
> handling, and win/loss detection — **an auto-player drove a complete 3-Pokémon battle to a detected
> loss.** The KB is complete (165 Gen 1 moves + 151 species). The one remaining step is running
> `python app.py` so the *agent* drives a battle end to end, then tuning timings. See HANDOFF.md for
> the input model, emulator config, and next steps.

## What it is

An LLM agent plays **Pokémon Stadium (Gen 1)** battles on an N64 emulator. The
harness owns the turn loop — it reads the game's RAM to see the board, detects when
it's the agent's turn, vets the chosen move against a guardrail gate, and drives the
controller — with no human hands. The agent only ever *proposes*; the harness
observes, vets, and acts.

Full design rationale: `../pokemon-battle-harness-plan.md`. Project rules: `CLAUDE.md`.

## Quick start

```bash
python app.py            # play the default battle, one line per turn
python app.py --quiet    # just the final result
pytest                   # 57 tests: KB, damage, gate, full battle, RA transport, vision/OCR, LLM player, VisionBackend
```

The vision path needs the optional `vision` extra (macOS): `pip install pillow
pyobjc-framework-Vision pyobjc-framework-Quartz`. Without it, its two tests are skipped.

No emulator or ROM needed — the default backend (`world.backend: mock` in
`config.yaml`) is a deterministic in-memory Gen 1 engine. Everything is verifiable
today.

## Architecture (one turn)

`read_battle()` decodes the backend snapshot (dex IDs + raw numbers) → the
**knowledge base** turns it into meaning (types, base stats, effectiveness) → the
**player** proposes an `Action` → the **guardrail gate** vets it (illegal / 0× /
bad-switch), may substitute, and logs why → `send_input()` (the single door out)
actuates it → the backend resolves the turn. Loop until one side has no Pokémon.

```
world/       Backend protocol + factory; mock (default), project64, retroarch; keyboard (act)
kb/          type_chart · base_stats · moves  (Gen 1 / Stadium ruleset)
battle/      state types · read_battle (observe) · send_input (act) · damage math
vision/      capture · ocr (Apple Vision) · layout · observe  — "read the screen" path
guardrails/  the gate -> Verdict{action, violations}
agent/       HeuristicPlayer (baseline) + LLMPlayer (stub -> heuristic fallback)
harness/     the turn loop (loop.py)
app.py       entry point
scripts/     probe_retroarch.py (live NCI probe) · ocr_probe.py (OCR region calibration)
tests/       KB, damage, guardrails, full battle, retroarch transport, vision observe + OCR
```

## Status

| Area | State |
|---|---|
| Knowledge base | ✅ type chart (Stadium-corrected), all 151 base stats, 18 moves |
| Damage/stat math | ✅ Gen 1 formula, single Special stat, category-by-type, deterministic |
| Observe / act | ✅ `read_battle` + `send_input` over the Backend protocol |
| Guardrail gate | ✅ legality + quality, logs every block |
| Players | ✅ HeuristicPlayer · ✅ LLMPlayer (Claude API or local llama.cpp; heuristic fallback) |
| mock backend | ✅ deterministic 3v3, resolves to a winner |
| vision backend | ◑ `VisionBackend` plays the REAL game (OCR state + keyboard act); logic tested, live run needs calibration |
| retroarch backend | ◑ UDP memory client works; RAM map + input TODO |
| project64 backend | ⬜ stub (needs JS-script bridge) |
| Vision observe (OCR) | ◑ `read_screen` → names + self HP, real Apple Vision OCR verified; layout uncalibrated |
| Vision act (keyboard) | ◑ `world/keyboard.py` → RetroArch RetroPad; keystroke maps need calibration + Accessibility perm |
| Tests | ✅ 57 passing (`pytest`) |

`python app.py` plays a full, sensible, deterministic battle (player wins the
default matchup in 8 turns, 0 gate blocks).

## Backends

| Backend | Platform | State read | Input | Status |
|---|---|---|---|---|
| `mock` | anywhere | in-memory engine | direct | working (dev/test default) |
| `retroarch` | macOS/Linux/Win | `READ_CORE_MEMORY` (UDP :55355) | RAM write / virtual gamepad | transport works; RAM map + input TODO |
| `project64` | Windows | `mem.u8` (script) | `joypad.set` | stub |

The RAM map and knowledge base are backend-independent — switching backends only
changes the observe/act plumbing, not battle logic.

## Vision path — "play it like a human"

A second observe/act approach that needs **no RAM map**: read the screen with OCR,
drive the game with keyboard events. Complements the RAM route rather than replacing it.

- `vision/capture.py` — `capture_region()` (macOS `screencapture`) + `crop_norm()`.
- `vision/ocr.py` — `VisionOCR`, Apple Vision on-device OCR; normalized top-left boxes.
- `vision/observe.py` — `read_screen()` → self/opp name + self HP; the KB fuzzy-matches the
  noisy OCR name to a real species (tolerates OCR slips like I↔l, 4↔A).
- `vision/layout.py` — `BATTLE` region boxes, **uncalibrated starting guesses**.
- `world/keyboard.py` — `press()/tap_sequence()` via Quartz CGEvent → RetroArch's default
  keyboard→RetroPad binds (X=A, Z=B, arrows=D-pad, Enter=Start). Needs Accessibility perm.
- `scripts/ocr_probe.py` — calibration tool: dump full-frame OCR + boxes, or show what each
  layout region reads, to line up `vision/layout.py` against a real Stadium frame.

Verified: `tests/test_ocr.py` runs **real** Apple Vision OCR on a rendered frame (recovers
name + HP); `tests/test_vision_observe.py` locks down the parsing + KB matching with a stub
OCR. Both green with the `vision` extra installed.

## Gen 1 / Stadium rules encoded (do not mix in later gens)

- Single **Special** stat (no Sp.Atk/Sp.Def split); move **category is fixed by type**
  (special: fire/water/grass/electric/ice/psychic/dragon).
- **Ghost → Psychic is 2×** (RBY cartridge bug made it 0×; Stadium fixed it).
- Bug↔Poison mutually super-effective; Gen 1 immunities (Normal/Fighting→Ghost 0,
  Ground→Flying 0, Electric→Ground 0).
- Damage uses maxed DV/stat-exp at L50 with the classic RBY equation; deterministic
  max roll (no crit/accuracy/status rolls yet).

## Next steps (build order)

Two live-emulator routes to a working bridge — **RAM** or **vision**. Both feed the same
harness loop; pick one to drive to a full live battle. The rest are backend-independent.

**RAM route (retroarch/project64):**
1. **RAM map (step 2)** — fill `world/retroarch.py::_ADDR` with the Stadium
   battle-struct addresses (self/opp species, HP, PP, status, stat stages,
   menu_state). Start from DataCrystal / TCRF; verify against a known HP using
   `scripts/probe_retroarch.py`. Implement `snapshot()` to match `MockBattle`'s shape.
2. **Turn detection + input (step 3)** — `awaiting_input()` off the menu-state byte;
   `send_action()` via WRITE_CORE_MEMORY to the controller-poll address or a virtual gamepad.

**Vision route (no RAM map):**
1. **Calibrate `vision/layout.py`** against a real Stadium frame (`python scripts/ocr_probe.py
   --region x,y,w,h --regions`). Needs the emulator running.
2. **Extend `read_screen()`** past names + self-HP to the full struct: opp HP, the 4 moves +
   PP, status, and a menu-state read for turn detection.
3. **`VisionBackend` in `world/`** — stitch capture→observe (state) + keyboard (act) into the
   `Backend` protocol so `harness/loop.py` runs against live RetroArch with no RAM map.

**Backend-independent:**
- **LLMPlayer (step 5)** — prompt from BattleState, pick among available_moves/switches,
  fall back to HeuristicPlayer on any error.
- **Arena + dashboard (step 6)** — win rate over N battles; reasoning/decision-log UI.

## Notes / open items

- `kb/base_stats.json` now covers all 151 Gen 1 species (verified vs Bulbapedia).
- Mock simplifications: no status/crit/accuracy rolls; faint auto-switch picks first alive.
- User-added and kept as-is: `tests/test_retroarch_transport.py`, `scripts/probe_retroarch.py`.
- **Git repo** on `master`, remote `origin` = github.com/bockbrendan/pokemonAIrena.
- **Stadium battle UI (mapped live, this session):** no "BATTLE/POKéMON/RUN" bar in this mode —
  move-selection is a **D-pad DIAMOND** (▲/◀/▶/▼ = 4 moves, e.g. Up=Surf/Left=Withdraw/Right=Ice
  Beam/Down=Strength). B from the diamond = "L Cancel/R Check" camera-look mode (L returns to the
  diamond). `world/keyboard.py` needs **L=q, R=w** added. `_MOVE_KEYS`→direction-based, `MOVES`
  recalibrate to diamond cells. Full detail + open items in `PROGRESS.md` HANDOFF.
- **Live emulator (macOS):** sandboxed/App-Store RetroArch — config, cores, saves, states under
  `~/Library/Containers/com.libretro.dist.RetroArch/Data/...`. N64 core = Mupen64Plus-Next
  (`/Applications/RetroArch.app/Contents/Frameworks/mupen64plus.next.libretro.framework`);
  ROM = `Pokemon Stadium (USA) (Rev 2)/<...>.z64`, with a `.srm` battery save + content-history
  entry, so it relaunches via CLI (`RetroArch -L <core> "<rom>"`). No save states → Stadium's
  pre-battle menus must be navigated each boot to reach the action menu. Details in `PROGRESS.md`.
- Fixed during build: a fainted mon's just-switched-in replacement was wrongly acting
  mid-turn (actors now bind the attacker object at queue time).
