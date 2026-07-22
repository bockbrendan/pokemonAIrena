# PROGRESS

## ⭐ HANDOFF — current live state (read this first)

**Goal right now:** get the vision backend to play ONE real turn against Pokémon Stadium
on RetroArch. Active work is now on **Windows**, in the fork **pokemonAIrena_kahn**
(origin github.com/GenghisKahn/pokemonAIrena) — see the **Windows port** section directly
below. Everything below the emulator is done and tested (56 pass on Windows; the 3 skips are
the macOS-only Apple Vision OCR tests). The macOS notes further down are retained for that OS.

> Env: use the shared venv at `../.venv` (Python 3.14 — has yaml/pytest/pytesseract). The
> repo dir has no venv of its own. Run tests with `../.venv/Scripts/python.exe -m pytest -q`.

### Windows port (fork: pokemonAIrena_kahn) — OBSERVE live-verified, move-select still blocked

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
- **Layout** — `vision/layout.py`: `ACTION_WIN` calibrated to the live 1241x925 client frame,
  `ACTION_MAC` preserved; `ACTION` is selected by `sys.platform`. (Windows capture is
  client-area only — no title bar — so its boxes differ from macOS by design.)
- **Act path** — `world/keyboard.py::WindowsKeyboard` (SendInput scancodes) already existed;
  **not yet exercised against the live game** (no keystrokes sent this session).
- Tests: `tests/test_capture.py` gained class-preference + platform-dispatch cases; OCR stubs
  updated for the `mode` arg. 56 pass.

**🚧 BLOCKED (same as macOS):** the move-select flow. Pressing A likely hits an intermediate
Cancel/Check screen before the 4 moves. Still need: drive `WindowsKeyboard` on the live game
to map action-menu → moves, then calibrate `vision/layout.py::MOVES` + `world/vision.py::
_MOVE_KEYS` (the single `press("a")` in `snapshot()` may need to be two). Also unbuilt:
pre-battle menu nav, battle-end detection (`is_over` always False → bounded by
`run.max_turns`), switching (`available_switches` empty).

**Committed** to the fork's `master` as `23b2863` ("Windows vision: PrintWindow capture +
Tesseract preprocessing, live-calibrated"). Not pushed to origin yet.

--- macOS handoff (retained) ---

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

**🚧 BLOCKED — the move-select flow (the one thing left for a first live turn):**
- Pressing A (BATTLE) does NOT go straight to the 4 moves. It first shows a **Cancel/Check
  screen** (your Pokémon zoomed, no move names). The move list is one more step away.
- NEED from the user: (1) a screenshot of the actual **4-move-names screen**, and (2) the
  exact button sequence action-menu → move (likely **A twice**, then navigate).
- Then calibrate `vision/layout.py::MOVES` region boxes + fix `world/vision.py::_MOVE_KEYS`
  (and the single `press("a")` in `snapshot()` may need to become two presses).
- Also unbuilt: pre-battle menu navigation (choosing battle/team), between-battle
  transitions, battle-end detection (`is_over` returns `_done`, currently always False →
  bounded by `run.max_turns`), and switching (v1 only attacks; `available_switches` empty).

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
