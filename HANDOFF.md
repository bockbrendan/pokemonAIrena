# HANDOFF — pokemonAIrena (read this first)

_Last updated: 2026-07-22. Authoritative current-state briefing. Supersedes older notes in
`PROGRESS.md` / `state.md` where they conflict._

## Goal

An LLM/heuristic agent plays a **real Pokémon Stadium (Gen 1)** battle on RetroArch (macOS) by
**reading the screen (OCR) and driving the keyboard** — no RAM map. The harness owns the turn loop;
the agent proposes a move, a guardrail gate vets it, `send_input()` actuates it.

## Status at a glance

| Layer | State |
|---|---|
| Battle core (types, damage, guardrails), mock backend, **61 tests** | ✅ Done & passing |
| **Knowledge base** — 151 species base stats + **all 165 Gen 1 moves** | ✅ **Complete** (was 18 moves) |
| **Observe** (window capture → OCR → both panels + turn detection) | ✅ Solid & window-size-independent |
| Emulator config (windowed, no-pause, no crash-on-load) | ✅ Fixed & locked |
| **Input / move commit / switch** (`z` → C-button "diamond") | ✅ SOLVED & live-verified |
| **Diamond cell calibration** (`MOVES` / `PARTY` boxes) | ✅ **Calibrated live** (reads real moves/party) |
| **Faint / switch flow** | ✅ Live-verified (auto-switched to a type-correct mon) |
| **Battle-end + winner detection** (`is_over` / `result`) | ✅ **Done & live-verified** on a real result screen |
| **A full 3-Pokémon battle, end to end** | ✅ **Played to conclusion** by an auto-player |
| `python app.py` driven by the *agent* (heuristic/LLM), start to win/loss | 🔧 the one remaining live pass |

**Bottom line:** every mechanic is built, tested, and live-verified. An auto-player drove a **complete
battle** — Squirtle → (fainted) → Sandshrew → (fainted) → Clefairy, KO'd Oddish, lost to Psyduck's crit —
through faints, switches, and a detected loss screen. The KB is complete so the agent can classify any
moveset. **What remains is running `python app.py` so the *agent* (not the hardcoded auto-player) drives a
battle end to end, then tuning timings** (`turn_wait` / `act_retries` / peek cadence).

---

## The input model (macOS RetroArch, live-verified this session)

**Delivery:** synthetic keys via `CGEventPostToPid(<RetroArch pid>, ev)` — a *global* `CGEventPost`
does NOT reach RetroArch. Implemented in `world/keyboard.py` (`MacKeyboard`).

**Three reliability rules (all required, learned the hard way):**
1. **Long holds (~0.3s).** RetroArch polls core input per frame; a 50ms tap is missed. `press()`
   default hold is 0.3s.
2. **Mouse nudge after every key.** RetroArch throttles/doesn't render input unless the mouse moves.
   After each keydown/keyup, jiggle the cursor: `CGWarpMouseCursorPosition` + a `CGEventMouseMoved`
   to the window center. **This is what turned flaky input reliable.** (User's tip. Likely related to
   App Nap / run-loop throttling — App Nap is now disabled via `defaults`, but the nudge is still the
   proven fix; verify whether a *fresh* RetroArch launch removes the need for it.)
3. **Retry until the effect is observed.** Even with 1+2, some presses don't register. Retry the
   press and re-check the screen/HP until it changes. `z` often needs a few retries.

**The RetroPad→N64 mapping is NON-STANDARD** — do NOT trust `retroarch.cfg`'s `input_player1_*` names.
From RetroArch's *Port 1 Controls* menu (Settings→Input→Port 1 Controls), the live mapping is:
- key **x** → N64 **C1**, key **a** → **C2/B**, key **s** → **C4** (the face keys are **C-buttons**,
  which is why `x` (cfg calls it "N64 A") is a no-op at the action menu)
- key **q** → **L Shoulder**, key **w** → **R Shoulder (Check)**, key **enter** → **Start**
- N64 **A** (BATTLE) appears bound to *nothing useful on the keyboard* — no single key opened BATTLE.

## The turn primitive — "diamond select" (SOLVED, live-verified 2026-07-22)

Moves and switches are the SAME mechanic:
- **To READ options:** `z` (keycode 6) opens the pre-commit screen, then **HOLD `w`/Check** (kc13) to
  reveal the **diamond**: 4 move cells (▲Surf ◀Withdraw ▶Ice Beam ▼Strength) or, on a forced switch,
  the party (▲/▶/▼ = your Pokémon). *Holding `w` is for viewing only.*
- **To COMMIT:** `z` → the **C-button** for the direction. The four moves/party slots ARE the C-buttons:
  **▲Up=`n`(kc45) · ▼Down=`m`(kc46) · ◀Left=`b`(kc11) · ▶Right=`l`(kc37)**. (This is why "`L` used Ice
  Beam" — the user meant the **`l` key** = C-right = the ▶Ice Beam cell, not the L shoulder.)
- **Continuous mouse movement is mandatory** the whole time (see below). Retry until observe confirms.

Proven end-to-end: `z`→`l` fired Ice Beam (Magnemite took damage); Squirtle then fainted to Magnemite's
super-effective Electric; `z`→`m` sent out Sandshrew ("Go! SANDSHREW!"). `enter` (Start) reaches a
different "look at field" screen — ignore it; use the `z` path.

**Forced switch (faint):** same primitive. On a faint the bar shows only "R Check" (no BATTLE/Cancel).
HOLD `w` reveals the party as a diamond (▲/▶/▼ = your Pokémon; fainted ones show ✖/"FAINTED"), then
`z`→C-button picks one. `read_party` reads them in slot order and excludes fainted mons (their `0` HP
OCRs as the letter `O` — handled).

**Battle end + winner** (`vision/observe.py::battle_result`, live-verified): the result screen stacks
**`1P`** (player, top) over **`COM`** (opponent, bottom), each with a big **WIN**/**LOSE** word. The
WIN/LOSE nearest the `1P` row is the player's outcome → `"self"` (won) / `"opponent"` (lost). `is_over()`
checks this first, with a "left the battle screens for N polls" debounce as fallback.

---

## Emulator setup (macOS, App Store / sandboxed RetroArch 1.22.2)

- Config lives under the container, NOT `~/Library/Application Support`:
  `~/Library/Containers/com.libretro.dist.RetroArch/Data/Library/Application Support/RetroArch/config/retroarch.cfg`
- Core: **Mupen64Plus-Next** (`/Applications/RetroArch.app/Contents/Frameworks/mupen64plus.next.libretro.framework`).
- ROM: `Pokemon Stadium (USA) (Rev 2)/Pokemon Stadium (USA) (Rev 2).z64`.
- **Config changes made this session (locked so they persist):**
  - `video_fullscreen = "false"` (was reverting to true → windowed now)
  - `pause_nonactive = "false"` (don't pause when unfocused)
  - `input_joypad_driver = "hid"` (was `"mfi"` — the mfi driver **SIGSEGV'd in `input_joypad_analog_axis`
    on content load; that was the "History games won't load / crashes" bug)**
  - `config_save_on_exit = "false"` ← **this locks the above** so RetroArch stops overwriting them on exit.
    Trade-off: in-app setting changes no longer persist unless you edit the cfg. A `.bak-*` of the
    original cfg sits beside it.
  - App Nap disabled: `defaults write com.libretro.dist.RetroArch NSAppSleepDisabled -bool YES`
    (applies on next RetroArch launch).
- **Relaunch-into-a-battle recipe** (the sandboxed app ignores `--args` and a direct-binary exec fails):
  `open -a RetroArch` → goes to menu (No Core) → menu-nav to **History** tab → select the Pokémon
  Stadium entry (loads core+ROM) → **Run** → once the game renders, **F4** loads the save state back
  into the exact battle. ⚠️ Activating "Run" via synthetic input was unreliable — may need the user.
- **Save/restore a battle:** **F2** (kc120) saves state slot 0, **F4** (kc118) loads it. Both work
  reliably via PostToPid (function keys are reliable). State file:
  `.../Data/Documents/RetroArch/states/Mupen64Plus-Next/Pokemon Stadium (USA) (Rev 2).state`.
  **Make a save state at the action menu at the start of every live session** so experiments can reset.
- Menu navigation (if stuck in RetroArch's menu): arrows = kc123/124/125/126 move, `x`(kc7) = Back,
  **F1** (kc122) toggles the menu. Menu-OK/confirm-a-leaf ("Run") could NOT be reliably triggered.

---

## Code — the harness now implements the diamond model

- **`world/keyboard.py`** — `CGEventPostToPid` delivery; `press()` hold 0.3s; **added the C-button keys
  `n/m/b/l` + direction map (`_DIR_TO_C`); a persistent MOUSE-MOVER thread** (started in `MacKeyboard.__init__`,
  runs for the driver's life — the reliability fix); **`diamond_select(direction)`** (Z → C-button) and
  **`hold(button, dur)`** (Check). (One gotcha handled: pyobjc lazy imports aren't thread-safe — the Quartz
  symbols the mouse thread uses are force-resolved on the main thread first.)
- **`world/vision.py`** — rewritten for the diamond model: `awaiting_input` = action-bar OR forced-switch
  (inferred from prompts); `snapshot` reads panels, then peeks moves (`z`→hold `w`→OCR→cancel) or the party
  on a forced switch; `step` commits via `diamond_select(slot→direction)` with **retry-until-observed**
  (`_changed` checks HP/name moved). `_SLOT_DIR = (up,right,down,left)`.
- **`vision/observe.py`** — `switch_screen_open` (faint detector), `read_party` (fainted-aware),
  `on_battle_screen`, and **`battle_result`** (the WIN/LOSE result-screen reader); `_HP` tolerates
  `/`, whitespace, or `.` as the separator.
- **`vision/layout.py`** — `ACTION`, `MOVES` (move diamond), and `PARTY` boxes **all calibrated live**
  against real viewport frames.
- **`vision/capture.py`** — `_crop_to_viewport()` (title bar + letterbox removal) → window-size-independent.
- **`kb/moves.json`** — completed to **all 165 Gen 1 moves** (type/power/accuracy/pp; category derived
  from type; Gen-1 quirks encoded). `kb/base_stats.json` already had all 151 species.
- **`tests/test_vision_backend.py`** — diamond model + battle-end/`battle_result` tests.

Tests: **61 pass**; backend/player construct and all modules import clean.

## Scratch artifacts (in `/tmp`)

- `/tmp/pk_drive.py` — persistent-mouse harness (the reliable input pattern). `/tmp/pk_conclude.py` — the
  auto-player that drove a full battle to its end. Helpers: `/tmp/pk_exp.py`.
- Frames: `/tmp/pk_movediamond2.png` (Clefairy move diamond), `/tmp/pk_checkheld.png` (party check),
  `/tmp/pk_RESULT.png` (the 1P=LOSE / COM=WIN result screen).

---

## Immediate next steps (in order)

1. **Run `python app.py` agent-driven, end to end.** The mechanics are proven by the auto-player; the
   remaining step is letting the *agent* (`config.yaml` → `agent.player: heuristic` for no-API, or `llm`)
   drive: observe → decide → `diamond_select` → confirm → loop through faints/switches → detected win/loss.
   Watch the forced-switch path and `_changed` confirmation; tune `turn_wait` / `act_retries` / peek cadence.
2. **Reliability polish:** the input is reliable-*ish* with the persistent mouse-mover + retry, but expect
   occasional missed presses — the retry-until-observed loop absorbs them; widen retries/waits if needed.
3. Solve reliable **relaunch-into-battle** (menu "Run" activation) so a core crash can auto-recover unattended
   (currently needs the user to click Run; then `F4` loads the save state).
4. Pre-battle menu navigation (choosing mode/cup/team) is still unbuilt — a fresh battle is set up manually.

**Live-session preamble every time:** launch RetroArch → History → Run the ROM → get to a battle action
menu → **F2** (save state) so experiments can reset. Keep the RetroArch window a normal size (the viewport
crop handles sizing).

## What's solid and needs no rework

- Battle core / KB (165 moves + 151 species) / guardrails / mock backend / 61 tests.
- Observe: `capture_region(...,'window')` → viewport crop → `action_menu_open` + `read_panels` reads both
  Pokémon (name+HP) at any window size. Verified across multiple viewport sizes.
- The full act path: `diamond_select` (moves + switches), continuous mouse, retry-until-observed, faint
  handling, and battle-end/winner detection — all live-verified in a complete battle.
