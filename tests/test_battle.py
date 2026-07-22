"""End to end: a full battle must resolve to a winner, deterministically."""
import yaml

from agent.player import HeuristicPlayer, make_player
from harness.loop import battle
from kb import default_kb
from world.mock import MockBattle


def _cfg():
    with open("config.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


def test_default_battle_resolves():
    cfg = _cfg()
    cfg["agent"]["player"] = "heuristic"   # deterministic + offline: never drive a live LLM/CLI in tests
    kb = default_kb()
    result = battle(MockBattle(cfg), make_player(cfg), kb, cfg)
    assert result["winner"] in {"player", "opponent"}          # someone won
    assert result["turns"] < cfg["run"]["max_turns"]           # didn't hang
    assert result["player_remaining"] == 0 or result["opponent_remaining"] == 0


def test_battle_is_deterministic():
    cfg = _cfg()
    kb = default_kb()
    r1 = battle(MockBattle(cfg), HeuristicPlayer(), kb, cfg)
    r2 = battle(MockBattle(cfg), HeuristicPlayer(), kb, cfg)
    assert r1 == r2                                            # same result every run


def test_heuristic_never_proposes_a_blocked_move_illegally():
    # The heuristic should pick legal, non-zero-effect moves — so in a normal battle
    # the gate should rarely fire. (It may still flag switches.) Assert it resolves
    # without the gate having to substitute an illegal move.
    cfg = _cfg()
    kb = default_kb()
    result = battle(MockBattle(cfg), HeuristicPlayer(), kb, cfg)
    assert not any("illegal-move" in b for b in result["blocks"])
