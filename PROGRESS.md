# PROGRESS

> **👉 Read [`HANDOFF.md`](HANDOFF.md) first** — it is the authoritative current-state briefing
> (2026-07-22). The session logs below are the detailed trail; HANDOFF.md is the summary.

## ⭐⭐⭐⭐⭐ SESSION 2026-07-22 (part 2) — INTEGRATION: macOS work + Windows PR #1 reconciled (`combined_dev`)

Merged the two lines of work into one branch. **PR #1** (Windows: PrintWindow capture, Tesseract OCR,
`SendInput` input) had been merged into `master` on GitHub, but that auto-merge **regressed the macOS
path** — I diagnosed three breakages and fixed them on `combined_dev` (off `master`):

1. **`world/keyboard.py` — macOS input clobbered.** The merge took PR #1's *unverified* `_MAC_KEYCODES`
   (no `c_*` C-buttons, `select`=Right Shift) and **dropped the persistent mouse-mover thread**. Result:
   `diamond_select` raised `KeyError` on `c_up` and the "single biggest reliability fix" was gone. Restored
   the live-verified C-button keymap + the `MacKeyboard` mouse-mover (+ `_window_center`/`_mouse_loop`/
   `stop` + the pyobjc symbol pre-resolve), and removed the duplicated class docstring the merge left.
2. **`world/keyboard.py` — distinct diamond-commit map per OS.** The two RetroArch configs are genuinely
   different (confirmed), so the diamond-commit keys are now a per-driver attribute `_DIR_MAP` instead of a
   shared `_DIR_TO_C`: macOS → `_DIR_TO_C` (N64 **C-buttons** N/M/B/L), Windows → `_DIR_TO_DIA` (the
   **PgUp/Home/PgDn/End** nav cluster, live-verified in PR #1). `diamond_select` uses `self._DIR_MAP`, so
   neither OS borrows the other's key names; only the open/preview/back keys (`select`/`check`/`cancel` =
   Z/W/Q) are shared because both configs put them on the same physical keys.
3. **`vision/layout.py` — import error.** The merge left `ACTION_WIN`/`ACTION_MAC` referencing an undefined
   `_ACTION_SHARED` (and no `ACTION_MAC`), so every vision import raised `NameError`. Rebuilt the intended
   `_ACTION_SHARED` → `ACTION_MAC`/`ACTION_WIN` → platform-dispatched `ACTION` structure.

Everything else the GitHub merge produced was correct (both-OS `capture.py`, `ocr.py`, `observe.py`,
`WindowsKeyboard` class with the 40-byte `INPUT` fix + `AttachThreadInput` focus, and the new tests).
Docs unified: this PROGRESS log is a 3-way merge of both trails (macOS full-battle entry + the Windows-port
section both preserved); HANDOFF/state carry the newer macOS narrative plus a Windows-support section.

**Result: all 64 tests pass; all modules import clean on macOS.** Open item flagged for the Windows owner:
PR #1's `a`→BATTLE→diamond flow vs the macOS `z`→C-button (no BATTLE bar) flow are likely different
per-machine RetroArch input configs — confirm before trusting either key map cross-machine.

## ⭐⭐⭐⭐ SESSION 2026-07-22 — FULL BATTLE PLAYED END-TO-END + KB COMPLETE

The whole vertical slice now works and is live-verified. Highlights (all committed; branch `brendan_dev`):

- **The turn primitive is `diamond_select`** — one mechanic for BOTH moves and switches: `z` opens the
  pre-commit screen, then the **C-button** for a diamond direction commits (▲Up=`n` ▼Down=`m` ◀Left=`b`
  ▶Right=`l`). Holding `w`/Check only previews the option names. ("`L` used Ice Beam" = the user meant the
  **`l` key** = C-right, not the L shoulder.) Live-verified: a move fired and the turn resolved.
- **Reliability = continuous mouse + retry.** RetroArch throttles input/render when the cursor is idle;
  `MacKeyboard` runs a persistent mouse-mover thread, and `step()` retries until observe confirms the HP/
  name changed. This is what made the flaky input usable.
- **Harness rewritten for the diamond model** (`world/vision.py`, `world/keyboard.py`): `awaiting_input`
  infers action-bar vs forced-switch from on-screen prompts; `snapshot` peeks moves/party; `step` commits
  via `diamond_select` + retry.
- **Diamond cells calibrated live** (`vision/layout.py` MOVES/PARTY) — reads real move names and party.
- **Faint/switch flow** live-verified — auto-switched to a type-correct Pokémon (Sandshrew, Ground, immune
  to Magnemite's Electric).
- **Battle-end + winner detection** (`vision/observe.py::battle_result`) — reads the real 1P=LOSE / COM=WIN
  result screen; `is_over()`/`result()` report the winner.
- **A complete 3-Pokémon battle was played to its conclusion** by an auto-player: Squirtle → (fainted) →
  Sandshrew → (fainted) → Clefairy; KO'd Oddish; lost to Psyduck's crit — through faints, switches, and a
  detected loss.
- **KB completed:** `kb/moves.json` 18 → **165 Gen 1 moves** (base stats already covered all 151 species),
  so the agent can classify any moveset the vision backend reads.
- Emulator fixes locked in: windowed, no pause-on-unfocus, `mfi→hid` joypad driver (fixed the load-crash),
  `config_save_on_exit=false`, App Nap disabled.
- **61 tests pass.**

**The one remaining step:** run `python app.py` so the *agent* (heuristic/LLM), not the hardcoded auto-
player, drives a battle end to end; then tune timings. See HANDOFF.md → Immediate next steps.

## ⭐⭐⭐ SESSION 2026-07-21 (part 4) — MOVE SCREEN CRACKED (the whole-session blocker)

**The move-select IS a D-pad DIAMOND** (the old "part 1" note was right; the "action bar → move list"
model was wrong). Live-confirmed flow to reach + read moves:

1. **Action menu** (`A BATTLE  B POKéMON  S RUN`).
2. Press **`z`** (RetroPad B, keycode 6) → the **cancel/check** screen (`L Cancel  R Check`).
   ⚠️ `z` is **FLAKY via synthetic CGEventPostToPid** — it took ~4 retries to register (user confirmed
   "if z doesn't work try again"). Retry the press (held ~0.9s) with ~2.8s waits until the screen changes.
3. **HOLD `w`** (RetroPad R = Check, keycode 13) → the **move DIAMOND** renders: each move on a D-pad
   direction with name + type + PP. This battle (Squirtle): **▲Up=SURF(Water 15/15) · ◀Left=WITHDRAW
   (Water 40/40) · ▶Right=ICE BEAM(Ice 10/10) · ▼Down=STRENGTH(Normal 15/15)**. Frame saved:
   `/tmp/pk_whold_view.png`.
4. **COMMIT — VERIFIED ONCE:** from the cancel/check screen, pressing **`L` (key q, kc12)** fired a
   move — Magnemite **105→78 HP**, Squirtle took the counter, returned to the action menu. A full turn
   executed. (So `L` is NOT just "Cancel" here — it commits a move. Move→button mapping still needs
   mapping for all 4; only `L`=one move confirmed.)
5. **RELIABILITY TRICK (user tip, confirmed helps):** RetroArch needs a **mouse move after a keypress**
   to render/process it. `nudge()` = `CGWarpMouseCursorPosition` + `CGEventMouseMoved` to the window
   center, jiggled, after every keydown/keyup. Without it, keys often don't take effect.
6. **⚠️ STILL FLAKY — automation NOT yet reliable.** The full turn worked **once manually** (105→78),
   but a retry-until-HP-drops loop (`/tmp/pk_play_loop.py`, move=`L`, 6 attempts/turn + nudges) landed
   **zero** moves over many attempts. So the mechanism is proven but the timing/flakiness isn't solved
   for unattended looping. Next: tune nudge timing + hold durations + the exact z→cancel→L cadence so
   `L` fires consistently; verify the z-retry actually reaches CANCEL each attempt (log state per step);
   then map all 4 move buttons; then loop. Recipe scripts: `/tmp/pk_play_loop.py`, helpers in `/tmp/pk_exp.py`.

**Input reality (critical for any automation):**
- Synthetic input via `CGEventPostToPid` DOES drive the core, but is **flaky and laggy** — needs
  RETRIES (esp. `z`), long HOLDS (`w` must be held to keep the diamond up), and patient waits (3-5s;
  the game lags). Tapping + short waits reads as "no-op" when the action actually worked a beat later.
- The RetroPad→N64 map is non-standard: keys **x/a/s = N64 C-buttons** (from the Port-1-Controls menu),
  which is why `x`(cfg "N64 A") is a no-op at the action menu. Do NOT trust retroarch.cfg's
  `input_player1_*` names for what a key does in-game.
- `enter` = Start → also reaches a cancel/check-like "look at field" screen (a DIFFERENT one than `z`'s;
  holding `w` there shows NO diamond). Use the **`z` path**, not `enter`.

**STILL OPEN:** verify the direction-press commits a move and executes the turn (HP change / animation);
calibrate `vision/layout.py::MOVES` to the diamond cells + build `read_moves` for the diamond; detect
turn completion; then loop. Observe (both panels, size-independent) + save-state reset (F2/F4) are solid.

## ⭐⭐ SESSION 2026-07-21 (part 3) — dynamic window sizing (observe is now size-independent)

- **`vision/capture.py::_crop_to_viewport`** now auto-crops every window capture down to the
  game's 4:3 render area — drops the macOS title bar (the "tallest contiguous band of non-black
  rows" is the game; the title bar is a smaller band, so it's excluded) and trims black letterbox
  margins. So normalized layout boxes are the SAME at any window size — no per-size re-tuning.
  Falls back to the full frame if detection is degenerate (dark frame).
- **`vision/layout.py::ACTION`** recalibrated to VIEWPORT coordinates (was full-window). Calibrated
  on a 1476x1120 viewport; verified identical reads on a 1426x1081 viewport (different window size).
- **`vision/observe.py::_HP`** regex now accepts whitespace as a separator — Apple Vision sometimes
  splits "105/105" into two tokens ("105","105") or "105/ 105"; the old `[/il|]`-only pattern missed
  those. Fixed → 5/5 reliable reads (self Squirtle 124/124, opp Magnemite 105/105).
- Verified across two window sizes + 5 consecutive live frames; 57 tests still pass.
- **App Nap:** set `NSAppSleepDisabled=YES` for `com.libretro.dist.RetroArch` — the residual
  "pauses when unfocused" was macOS App Nap (OS-level), not `pause_nonactive`. Takes effect on next
  RA launch. (Doesn't affect the harness, which foregrounds RA per turn.)
- **Load-crash fixed:** RA crash reports showed SIGSEGV in `input_joypad_analog_axis` (the `mfi`
  joypad driver). Switched `input_joypad_driver` mfi→hid in retroarch.cfg. This is why History
  games "wouldn't load" (booted then instant-crashed on the first input poll).

## ⭐⭐ SESSION 2026-07-21 (part 2) — pause fix + emulator ops

- **`pause_nonactive` fix (user asked: game pauses when clicking away).** retroarch.cfg already
  had `pause_nonactive = "false"`, but the *running* instance had loaded `true` and kept pausing
  (verified: unfocused frame-diff = 0.000 = frozen). Config is only read at startup, and
  `config_save_on_exit = "true"` would re-write the running value on a clean exit — so the fix is:
  **save state → `kill -9` RetroArch (skips the config re-write) → relaunch (loads `false`)**.
  Done: RA now runs with `pause_nonactive=false`. To VERIFY once a game runs: unfocus + frame-diff
  should be > 0.
- **Save state works & the battle is preserved:** F2 (kc120) via PostToPid saved slot 0 to
  `~/Library/Containers/com.libretro.dist.RetroArch/Data/Documents/RetroArch/states/Mupen64Plus-Next/Pokemon Stadium (USA) (Rev 2).state`.
  F4 (kc118) loads it. **Do this at the start of every live session.**
- **Relaunch-into-battle recipe (the `--args`/direct-binary launch does NOT work for this sandboxed
  App Store build):** `open -a RetroArch` (goes to menu, No Core) → menu-nav to **History** tab →
  select the Pokémon Stadium entry (loads core+ROM) → **Run** → once the game renders, **F4** to
  load the save state back into the exact battle.
- **Menu navigation via PostToPid (verified):** d-pad `left/right/up/down` (kc123/124/126/125) and
  `back`=`x`(kc7) all work at ~0.18s hold. **UNRESOLVED: the menu OK/confirm-a-leaf key.** Enter(36)
  opens an entry's context submenu but does NOT activate "Run"; z(6), x(7=back), d(2) also don't;
  a mouse click at a guessed coord missed. The menu-confirm key is still unknown — likely tied to
  the same in-game keycode remap (in-game the effective confirm was `d`/kc2, back was `q`/kc12).
  Next session: resolve the menu-OK key (try mouse click with correct window-offset coords, or map
  it empirically) so History→Run can be automated.

## ⭐⭐ SESSION 2026-07-21 — live findings (supersede conflicting notes below)

Worked the live emulator directly (RetroArch running, Squirtle vs Oddish at the action menu).
Verified facts this session — trust these over the older HANDOFF where they conflict:

1. **This battle mode DOES have the action bar** `A BATTLE · B POKéMON · S RUN`. The
   uncommitted "no bar exists, it's a move diamond" note (below) is WRONG for this battle —
   the bar is on screen. Observe model (action-menu anchor) is correct.
2. **Observe works.** Recalibrated the opponent panel in `vision/layout.py::ACTION`
   (`opp_name`→(0.72,0.648,0.22,0.048), `opp_hp`→(0.72,0.720,0.24,0.042)) for the live
   window (1460×1656). Both sides now read: **self Squirtle 124/124, opp Oddish 125/125**,
   `action_menu_open: True`. ⚠️ These boxes are per-window-size; letterbox auto-crop is still
   the durable fix (see capture caveat below).
3. **ACT PATH — root cause found. Three layers; two FIXED IN CODE, one still open.**
   - **Delivery (FIXED in `world/keyboard.py`):** global `CGEventPost` (what the driver used)
     does **NOT** reach RetroArch — my own event tap sees the synthetic key, but RA never reacts.
     `pause_nonactive = "true"` means RA only takes input when frontmost, and even frontmost the
     global post is dropped. **`CGEventPostToPid(<RA pid>, ev)` DOES reach it.** `MacKeyboard`
     now resolves the RA pid (pgrep -x RetroArch, re-resolves if RA restarts) and posts to it.
   - **Timing (FIXED in code) — this is almost certainly the ORIGINAL "input does nothing" bug.**
     RetroArch reads *core* input by **polling a key-state array each frame**, so a 50ms synthetic
     press is missed between polls. Verified live: kc12 (`q`=L=Cancel) did NOTHING at 0.07s hold
     but reliably backed out of the Cancel/Check screen at **0.35s hold**. `_Keyboard.press()`
     default `hold` raised 0.05 → **0.3s**. (Hotkeys like F1 are edge-triggered and fire on any
     hold; only core buttons need the long hold — which is why F1 "worked" but buttons didn't.)
   - **Keycode map — STILL OPEN (contradictory, lost the battle before confirming).** With
     PostToPid + long hold: kc12 (`q`=L) works as Cancel (matches cfg). BUT kc7 (`x`, cfg N64 A)
     was a **no-op even at 0.35s**, while kc2 (`d`, unbound in cfg) *advanced* action-menu →
     "L Cancel · R Check". kc0/kc1 nothing. So `x`→A is NOT holding up; the effective A bind is
     unconfirmed (maybe a per-core .rmp remap, or kc2 result was a stale frame). **`_MAC_KEYCODES`
     `a`/`b` are NOT yet verified — re-test each with the 0.3s hold on a fresh battle before trusting.**
4. **Move-select flow.** Pressing the button that advances (kc2 this session) from the action
   menu reaches the **"L Cancel · R Check"** screen (battlefield view, no move names) — matches
   the older "Cancel/Check" note. The 4 move names are still not located/OCR'd. Need the correct
   keycodes first (step 3), then map the move screen for `layout.py::MOVES` + `_MOVE_KEYS`.
5. RetroArch input facts (sandboxed cfg, `.../Containers/com.libretro.dist.RetroArch/.../config/retroarch.cfg`):
   `input_driver=cocoa`, `input_menu_toggle=f1`, `input_enable_hotkey=nul` (hotkeys always on),
   `pause_nonactive=true`, `menu_swap_ok_cancel_buttons=true`, `input_exit_emulator=escape`
   (⚠️ don't send Escape — quits RA), player1 a=x b=z l=q r=w, arrows=dpad, start=enter, select=rshift.
   Process tree note: this ran under **VS Code** (TCC perms attach to VS Code; Screen Recording
   granted, Accessibility granted — `CGEventTapCreate` returns non-nil).
6. Scratch frames this session in /tmp: `pk_frame_window.png` (action menu), `pk_probe.png`
   (RA main menu overlay), `pk_cancelcheck.png` (L Cancel/R Check screen). Helper:
   `/tmp/pk_keys.py <btn...>` posts keycodes to the RA pid.

**⚠️ Emulator state at end of session:** the live battle was LOST — during the keycode sweep the
Mupen64Plus core went to a black screen and RetroArch **restarted** (pid 6550→9928), now sitting at
its **Load Content** menu with **no ROM loaded** (N64 core instability, cf. the black-screen notes).
No save state exists, so getting back to a battle needs manual Stadium menu navigation (unbuilt).
LESSON: **make a RetroArch save state at the action menu FIRST** (F2=kc120 save / F4=kc118 load,
both work via PostToPid since function keys are reliable) so keycode probing can reset instantly
instead of losing the battle.

**Immediate next steps:** (a) load the ROM + navigate Stadium to a battle action menu, then
**save-state immediately**; (b) with the driver's new PostToPid + 0.3s hold, re-verify each
`_MAC_KEYCODES` entry (esp. `a`/`b`) against the game, load-stating between probes; (c) drive
action-menu→BATTLE, capture the TRUE move-select screen, calibrate `MOVES`/`_MOVE_KEYS`;
(d) one real turn via `python app.py`. Code already done this session: PostToPid delivery + long
hold in `world/keyboard.py`; opp-panel calibration in `vision/layout.py`. Tests still 57/57.

---

## ⭐ HANDOFF — current live state (read this first)

> See also [`HANDOFF.md`](HANDOFF.md) — the authoritative cross-platform briefing, including
> upstream's macOS **move-select breakthrough** (`z → cancel/check → hold w → move DIAMOND`) and the
> non-standard RetroPad→N64 mapping. This PROGRESS file holds the **Windows** detail below.

**Goal right now:** get the vision backend to play ONE real turn against Pokémon Stadium
on RetroArch. Active work is now on **Windows**, in the fork **pokemonAIrena_kahn**
(origin github.com/GenghisKahn/pokemonAIrena) — see the **Windows port** section directly
below. Everything below the emulator is done and tested (56 pass on Windows; the 3 skips are
the macOS-only Apple Vision OCR tests). The macOS notes further down are retained for that OS.

> Env: use the shared venv at `../.venv` (Python 3.14 — has yaml/pytest/pytesseract). The
> repo dir has no venv of its own. Run tests with `../.venv/Scripts/python.exe -m pytest -q`.

### Windows port (fork: pokemonAIrena_kahn) — OBSERVE live-verified + size-independent; move flow known, not yet driven

RetroArch on Windows: window class `RetroArch`, title `RetroArch Mupen64Plus-Next 2.8-Vulkan`,
**Vulkan** renderer, client area ~1241x925.

**✅ Live-verified end-to-end (production pipeline, not just tests):** at the action menu,
`read_panels` returns SELF **Squirtle 124/124**, OPP **Meowth 120/120**; `action_menu_open` →
True. Both species resolve via the KB (→ types/stats). Self current-HP now reads reliably
(124/124 over a 15-frame run) after the 5x-upscale fix + the KB-max clamp (see self-HP note
below); a rare transient misread self-heals on the next turn's observe. `config.yaml` is
already `backend: vision`, `capture: window`, `window: RetroArch`.

**What was built for Windows (our portion of the backend):**
- **Window capture** — `vision/capture.py::_grab_window_windows`: `PrintWindow`
  (`PW_CLIENTONLY | PW_RENDERFULLCONTENT`) grabs the window's OWN buffer, so it is
  **occlusion-independent** (RetroArch can sit behind log/editor windows) and works with the
  **Vulkan** renderer (plain PrintWindow / ImageGrab-of-screen-rect both fail — the latter
  grabs whatever is on top). Stdlib ctypes, no new dep. `_pick_hwnd` matches by window
  **class** first (title-substring fallback) so an Explorer folder named "RetroArch…" can't
  be captured by mistake.
- **OCR preprocessing** — `vision/ocr.py::_prep_tesseract` + a `mode` arg on `recognize`:
  the **RED channel** isolates white text on BOTH the blue (self) and green (opp) panels
  better than luminance; NEAREST 5x upscale (keeps pixel-font edges) + autocontrast. Modes:
  `word` (species names: psm 8 + Otsu), `number` (HP: psm 7 + digit/'/' whitelist — stops
  "124"→"IZ4"), `line` (moves/bar: psm 7). `observe.py` threads the mode per region.
  Apple Vision ignores the hint, so the macOS path is unchanged.
- **self-HP read** — the current-HP number was flaky at 4x (the blurry blue-panel "2" in
  "124" dropped → "14"). Fixed by 5x upscale (`TesseractOCR` default) reading the digit
  reliably; `VisionBackend` already clamps to the KB-derived max, so any over-read (e.g.
  1244) collapses back to the real max. OCR's own max-HP number is unused — the KB owns it.
- **Viewport crop (adopted from upstream)** — `vision/capture.py::_crop_to_viewport` runs on the
  Windows PrintWindow output too, trimming title bar + letterbox/pillarbox to the 4:3 game render.
  **Verified size- and aspect-independent:** the crop holds a ~1.319 viewport and reads correctly
  across window sizes AND non-4:3 window shapes (assumes RetroArch renders 4:3, black letterbox).
- **Layout** — `vision/layout.py`: `ACTION` boxes are viewport-relative. `bar`/`self_*` are shared
  across OSes; only `opp_*` is split (`ACTION_WIN` vs `ACTION_MAC`), because the PrintWindow vs
  `screencapture -l` crops trim the right/bottom edges differently. Selected by `sys.platform`.
- **Ported from the upstream repull (c26cf89):** `world/keyboard.py` wholesale (adds `r`/`l`
  buttons, 0.3s hold — verified identical to upstream) and `observe.py`'s broadened `_HP` regex.
- **Act path** — `world/keyboard.py::WindowsKeyboard` (SendInput scancodes) exists; **not yet
  exercised against the live game** (no keystrokes sent yet). Windows input needs neither the
  mouse-nudge nor the App-Nap workaround the macOS path requires (see HANDOFF.md).
- Tests: `tests/test_capture.py` gained class-preference + platform-dispatch cases; OCR stubs
  updated for the `mode` arg. 56 pass.

**🚧 NEXT — the move-select flow (no longer a mystery).** Upstream mapped it on macOS (see
[`HANDOFF.md`](HANDOFF.md)): action menu → `z` (B) → Cancel/Check screen → **hold `w`** (R/Check)
→ a move **DIAMOND** (▲/◀/▶/▼ = the 4 moves). The **commit key is still unknown** (upstream's open
blocker). Windows work: drive this via `WindowsKeyboard` (`z`=B, `w`=R already mapped), read the
diamond (recalibrate `vision/layout.py::MOVES` to the 4 cells; `world/vision.py::_MOVE_KEYS` →
directions), and find the commit key. Also unbuilt: pre-battle menu nav, battle-end detection
(`is_over` always False → bounded by `run.max_turns`), switching (`available_switches` empty).

**Committed** to the fork's `master`: `23b2863` (Windows PrintWindow capture + Tesseract
preprocessing) and `cb59c80` (docs). The upstream-repull merge (viewport crop, `_HP`, keyboard,
opp per-platform split, HANDOFF.md, size/aspect verification) is a follow-up commit. Not pushed yet.

--- macOS handoff (older; superseded by HANDOFF.md) ---

**Turn model (rewritten):** the harness anchors each turn on the **action menu**
("A BATTLE  B POKéMON  S RUN"), reads BOTH Pokémon off the panels, presses A to open the
moves, reads them (KB-resolved), the agent picks, keystrokes navigate the open move menu.
It reads **whoever is on screen** via the KB (all 151 now loaded) — no config teams needed.
Player = **BLUE/top-left**, opponent = **RED/bottom-right** (this battle: self=Clefairy,
opp=Oddish). Set in `vision/layout.py::ACTION`.

**✅ Live-verified (window 1194x1228, macOS):**
- Window capture by identity works (`capture: window`, `world/capture.py::_grab_window`).
- Action-menu turn detection: `action_menu_open` → True.
- Panels read correctly: SELF Clefairy 150/150, OPP Oddish 125/125 (HP boxes widened so a
  leading digit can't clip — fixed an earlier 125→25 misread). Verified via `read_panels`.
- OCR cross-checked by a blind Haiku agent: same text.

**🔧 IN PROGRESS — real Stadium battle UI mapped live (this session, Squirtle vs Oddish).**
The prior "action menu (BATTLE/POKéMON/RUN) → move list" model is **WRONG for this battle mode**.
Ground truth from live frames:
- **No "A BATTLE  B POKéMON  S RUN" bar exists in this mode.** The move-selection screen IS a
  **move DIAMOND**: the 4 moves are laid out on the **D-pad**, one per direction (NOT a vertical
  list). This battle: **▲ Up=SURF · ◀ Left=WITHDRAW · ▶ Right=ICE BEAM · ▼ Down=STRENGTH** (each
  cell shows name + type + PP). So slot→direction, and `read_moves` must read the four diamond
  positions; `_MOVE_KEYS[i]` must map to the SAME position order `read_moves` returns.
  ⚠️ Discrepancy: the previous handoff claimed `action_menu_open→True` on a BATTLE/POKéMON/RUN bar
  — never seen this session. Possibly a different mode/cup, or a prior misread. Reconcile before
  trusting `ACTION`/`action_menu_open`.
- Pressing **B** from the diamond enters a **"L Cancel / R Check" camera-look mode** (NOT a menu
  level): B just cycles the camera between the Pokémon, and **A does nothing** there. **L (Cancel)
  returns to the diamond**; R (Check) inspects stats. The "Cancel/Check screen" the last session hit
  and called a step toward the moves was actually this look mode — a dead end, not progress.
- **Keyboard driver gap (fix underway):** `world/keyboard.py` maps only A/B/dpad/start/select — this
  UI needs **L and R**. Confirmed RetroArch binds (defaults) in the sandboxed config: A=x, B=z, **L=q,
  R=w**, Y=a, X=s, arrows=dpad, Start=enter, Select=rshift. Adding L/R (mac keycodes q=12, w=13).
- **Code changes this implies:** (1) `_MOVE_KEYS` → direction-based (each move = one D-pad press;
  VERIFY whether the direction alone commits the move or needs a trailing confirm). (2) `snapshot()`'s
  single `press("a")` model is wrong — remap to: turn-start diamond is already/one-press away, pick =
  direction. (3) `vision/layout.py::MOVES` recalibrate to the diamond cells; re-examine `ACTION` (turn
  detector should key off the diamond or the two HP panels, not a BATTLE bar).
- **Capture caveat:** window capture includes the macOS title bar, and the game **letterboxes/zooms**
  (viewport size varies with window size — seen 1920×1496, 1388×1640 letterboxed, then full-window).
  Region boxes must be calibrated to the live viewport; auto-cropping the black bars would make this
  robust. Frames saved this session in the scratchpad: `frame_check.png` (diamond), `f_afterB.png`
  (Cancel/Check look mode).
- **STILL OPEN:** exact move-commit keystroke; `MOVES`/`ACTION` calibration to the live viewport; one
  verified live turn via `python app.py`.
- Also unbuilt: pre-battle menu navigation (choosing battle/team), between-battle transitions,
  battle-end detection (`is_over` returns `_done`, currently always False → bounded by
  `run.max_turns`), and switching (v1 only attacks; `available_switches` empty).

**How to test live:** RetroArch rendering a battle (Angrylion or ParaLLEl RDP fixed the
black screen), at the action menu, window at a normal size. Screen Recording + Accessibility
permissions granted (capture worked, so they are). `config.yaml` already `backend: vision`,
`capture: window`. Calibration probe: `python scripts/ocr_probe.py` (whole display) — for
window/battle use the live snippet pattern from the session, or add `--region`.

**Live emulator — relaunch recipe (mapped this session, macOS):** this RetroArch is the
**sandboxed / App Store build** — its config, cores, saves, and states live under
`~/Library/Containers/com.libretro.dist.RetroArch/Data/...`, NOT `~/Library/Application
Support/RetroArch`. N64 core = **Mupen64Plus-Next**
(`/Applications/RetroArch.app/Contents/Frameworks/mupen64plus.next.libretro.framework`).
ROM = `Pokemon Stadium (USA) (Rev 2)/Pokemon Stadium (USA) (Rev 2).z64` (32 MB, USA Rev 2,
from Vimm's Lair). A battery save (`.srm`) and RetroArch's content-history both already point
at this ROM+core, so it relaunches straight into the game:

    /Applications/RetroArch.app/Contents/MacOS/RetroArch \
      -L "/Applications/RetroArch.app/Contents/Frameworks/mupen64plus.next.libretro.framework" \
      "/Volumes/drive_4tb/Personal Projects/pokemonAIrena/Pokemon Stadium (USA) (Rev 2)/Pokemon Stadium (USA) (Rev 2).z64"

There are **no save states** (`.../states/Mupen64Plus-Next` is empty) — no mid-battle resume,
so Stadium's pre-battle menus (mode → cup → team → opponent → lead) must be navigated each boot
to reach the action menu. Idle, RetroArch sits at Main Menu with **no core loaded** (verified
this session; window capture works, 1920x1496 Retina frame).

**Capture caveat (calibration risk):** window capture returns the FULL macOS window, title bar
included. `ACTION` regions in `vision/layout.py` were calibrated at a 1194x1228 window; this
session the window was 1920x1496 — a **different aspect ratio**, so the normalized ACTION boxes
are NOT guaranteed to line up. Re-verify ACTION (and calibrate MOVES) at the actual working
window size before trusting a live read, or size the window to the calibration aspect.

## Done
- Scaffolded the harness (Pokémon-native layout, not mirroring flightgear).
- CLAUDE.md ported from flightgear_harness: behavioral rules verbatim; Project /
  What-Not-to-Touch / Success-Criteria rewritten for Pokémon Stadium (Gen 1).
- `kb/` — Gen 1 type chart (Stadium-corrected: Ghost→Psychic 2×), starter base-stats
  (17 species), move data. The load-bearing "meaning" layer.
- `battle/` — state types, `read_battle` (observe), `send_input` (act), Gen 1 stat +
  damage math.
- `guardrails/rules.py` — the gate: legality + quality (0× block, bad-switch warn),
  returns `Verdict{action, violations}`.
- `agent/player.py` — HeuristicPlayer (best-expected-damage, switches when stuck);
  LLMPlayer stub with heuristic fallback.
- `world/` — `Backend` protocol + factory; **mock** engine (deterministic 3v3, the
  default); project64 stub; retroarch stub with a **working UDP memory client**.
- `harness/loop.py` — the turn loop; `app.py` entry point.
- Tests: 18 pass (`pytest` or the manual runner). Default battle resolves to a
  winner deterministically. `python app.py` plays a full, sensible battle.
- Fixed an engine bug: a mon that fainted mid-turn had its just-switched-in
  replacement wrongly act with the fainted mon's move (actors now bind the
  attacker object at queue time).

## User-added (kept as-is)
- `tests/test_retroarch_transport.py` — validates the NCI client vs a fake UDP server.
- `scripts/probe_retroarch.py` — live probe for a running RetroArch + memory map.

## Vision path — "play it like a human" (alternative to RAM reading)
A second observe/act approach that needs no RAM map: read the screen, drive the keyboard.
- `vision/capture.py` — `capture_region()` (macOS `screencapture`) + `crop_norm()`.
- `vision/ocr.py` — `VisionOCR`, Apple Vision on-device OCR; normalized top-left boxes.
- `vision/layout.py` — `BATTLE` region boxes (**uncalibrated starting guesses**).
- `vision/observe.py` — `read_screen()` → self/opp name + self HP; KB fuzzy-matches the
  noisy OCR name to a real species (tolerates I↔l, 4↔A).
- `world/keyboard.py` — `press()/tap_sequence()` via Quartz CGEvent → RetroArch's default
  keyboard→RetroPad binds (X=A, Z=B, arrows=D-pad, Enter=Start). Needs Accessibility perm.
- `scripts/ocr_probe.py` — calibration tool: dump full-frame OCR + boxes, or show what each
  layout region reads, to line up `vision/layout.py` against a real Stadium frame.
- Deps live behind the `vision` extra (pillow + pyobjc Vision/Quartz). **Installed in this
  env; all 24 tests pass** including the two real-Apple-Vision OCR tests (`test_ocr.py`).

### VisionBackend (step 3) — DONE (unverified live)
- `world/vision.py::VisionBackend` — plays the REAL game with no RAM map. Key design: the
  static roster (species/movepools/PP/base stats) comes from `config.battle` (you don't OCR
  your own team); OCR tracks only the dynamic state (active mon by name→roster match, your
  HP, menu). Emits the same snapshot shape as mock, so `read_battle`/the loop are unchanged.
  Act via `world/keyboard.py` keystrokes; `_MOVE_KEYS`/`_switch_keys` are CALIBRATE points.
- `world/base.py` factory: `backend: vision`. `config.yaml world.vision{region, turn_wait}`.
- `tests/test_vision_backend.py` — 5 tests (fake OCR + fake keyboard, no emulator): roster
  from config, OCR→active+HP sync, snapshot feeds read_battle, move→keystroke map, bad-read
  keeps state. 34 tests pass.

### Vision path — move OCR + cross-platform (DONE)
- **Move-menu OCR** — `vision/observe.py`: `match_move` (fuzzy, space/case-tolerant),
  `read_moves` (4 slots → KB move names, skips empties), `menu_open` (lenient turn
  detector). VisionBackend now reads YOUR moves off the menu and resolves them via the
  KB — config moves are just a seed. `UnknownMoveError` fails loudly (names slot + raw
  text) when OCR reads a move not in `kb/moves.json`.
- **Cross-platform OCR** — `vision/ocr.py`: `TesseractOCR` (pytesseract, Win/Linux/mac)
  alongside `VisionOCR` (mac). `default_ocr(engine)`; `config world.vision.ocr` =
  auto|vision|tesseract. Deps split: `vision` extra now cross-platform, `vision-macos`
  holds pyobjc (platform-markered).
- **Cross-platform keyboard** — `world/keyboard.py`: `MacKeyboard` (Quartz) +
  `WindowsKeyboard` (SendInput scancodes, stdlib ctypes). `make_keyboard(driver)`;
  `config world.vision.keyboard` = auto|mac|windows.
- **Cross-platform capture** — `vision/capture.py`: `_grab_screencapture` (macOS CLI)
  + `_grab_imagegrab` (Pillow ImageGrab, Windows+macOS, no new dep). `capture_region(
  bbox, backend)`; `config world.vision.capture` = auto|screencapture|imagegrab. The
  whole vision loop (capture→OCR→keyboard) now runs on Windows and macOS.
- `requirements.txt` added (mirrors pyproject extras). 51 tests pass.
- NOTE: still unverified against a live emulator; regions + keystroke maps need calibration.

### Vision path — remaining (needs the emulator on the user's machine)
1. **Calibrate `vision/layout.py`** against a real Stadium frame (`ocr_probe.py --region
   ... --regions`) — the region boxes are still guesses.
2. **Calibrate keystroke maps** — verify `_MOVE_KEYS` (2×2 move grid) and `_switch_keys`
   against the actual Stadium menu flow + RetroArch binds; grant Accessibility permission.
3. **Refine turn detection** — `awaiting_input()` currently infers "in battle" from the
   active-name region; add a dedicated move-menu region once layout is calibrated.
4. **Opp HP / status** — OCR of the opponent's HP bar is unreliable; opp HP is tracked
   best-effort (starts full). The agent still gets the type matchup, the main signal.

## LLMPlayer (step 5) — DONE
- `agent/providers.py` — pluggable providers behind `complete(system, user) -> str`:
  `ClaudeProvider` (Anthropic SDK, default `claude-haiku-4-5`, SDK default credential
  resolution) and `LlamaCppProvider` (local `llama-server`, OpenAI-compatible
  `/v1/chat/completions`, stdlib urllib, no dep, no cost).
- `agent/player.py::LLMPlayer` — builds a compact BattleState prompt (legal moves with
  type/eff/est-dmg + legal switches), parses `move N` / `switch N`, validates against
  legal options, and falls back to HeuristicPlayer on any unparseable/illegal/error reply.
- `config.yaml` agent: `provider` (claude|llamacpp), `model`, `max_tokens`, `llamacpp{host,port}`.
- `tests/test_llm_player.py` — 5 tests (fake provider): valid pick used, prompt lists
  options, illegal/unparseable/provider-error all fall back to heuristic. 29 tests pass.
- CAVEAT: the Anthropic **API is metered per token** — a Claude Pro/Max *subscription*
  covers claude.ai + Claude Code, not raw Messages API calls. The zero-arg client uses
  whatever auth is configured (ANTHROPIC_API_KEY or an `ant auth login` OAuth profile).

## Next (build order)
- **Step 2 — RAM map.** Fill `world/retroarch.py::_ADDR` with the Stadium battle-struct
  addresses (self/opp species, HP, PP, status, stat stages, menu_state). Start from
  DataCrystal / TCRF; verify with `scripts/probe_retroarch.py` against a known HP.
  Then implement `snapshot()` to return the same shape as `MockBattle.snapshot()`.
- **Step 3 — turn detection + input.** `awaiting_input()` off the menu-state byte;
  `send_action()` via WRITE_CORE_MEMORY to the controller-poll address or a virtual gamepad.
- **Step 5 — LLMPlayer.** Prompt from BattleState, choose among available_moves/switches,
  fall back to HeuristicPlayer on any error.
- **Step 6 — arena + dashboard.** Win rate over N battles; reasoning/decision log UI.

## Notes / open questions
- base_stats.json now covers all 151 Gen 1 species (verified vs Bulbapedia).
- Mock simplifications: no status/crit/accuracy rolls yet (deterministic max roll);
  voluntary switching supported, faint auto-switch picks first alive.
- Git repo on `master`, remote `origin` = github.com/bockbrendan/pokemonAIrena. 57 tests pass.
