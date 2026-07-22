"""LLMPlayer logic — prompt building, reply parsing, legality, and fallback — with
a fake provider, so no network or API key is touched.

The provider is injected; these tests lock down that a well-formed reply becomes the
right Action, and that anything unparseable / illegal / erroring defers to the
HeuristicPlayer (a turn is never lost)."""
from __future__ import annotations

from agent.player import HeuristicPlayer, LLMPlayer
from battle.observe import read_battle
from kb import default_kb
from world.mock import MockBattle


def _state(cfg):
    backend = MockBattle(cfg)
    return read_battle(backend, default_kb(), level=cfg["world"].get("level", 50))


class _FakeProvider:
    """Returns a canned reply, or raises if `boom` is set."""
    def __init__(self, reply="", boom=False):
        self.reply = reply
        self.boom = boom
        self.last_prompt = None

    def complete(self, system, user):
        self.last_prompt = user
        if self.boom:
            raise RuntimeError("provider down")
        return self.reply


def _cfg():
    import yaml
    with open("config.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


def test_valid_move_reply_is_used():
    cfg = _cfg()
    state = _state(cfg)
    slot = state.available_moves[0]
    player = LLMPlayer(cfg, provider=_FakeProvider(reply=f"move {slot}"))
    action = player.decide(state, default_kb())
    assert action.kind == "move" and action.index == slot


def test_prompt_lists_legal_options():
    cfg = _cfg()
    state = _state(cfg)
    fake = _FakeProvider(reply=f"move {state.available_moves[0]}")
    LLMPlayer(cfg, provider=fake).decide(state, default_kb())
    # Every legal move slot is offered to the model.
    for i in state.available_moves:
        assert f"move {i}:" in fake.last_prompt


def test_illegal_index_falls_back_to_heuristic():
    cfg = _cfg()
    state = _state(cfg)
    kb = default_kb()
    # Slot 99 is not a legal move -> parser rejects -> heuristic decides.
    player = LLMPlayer(cfg, provider=_FakeProvider(reply="move 99"))
    assert player.decide(state, kb) == HeuristicPlayer().decide(state, kb)


def test_unparseable_reply_falls_back():
    cfg = _cfg()
    state = _state(cfg)
    kb = default_kb()
    player = LLMPlayer(cfg, provider=_FakeProvider(reply="I choose you!"))
    assert player.decide(state, kb) == HeuristicPlayer().decide(state, kb)


def test_provider_error_falls_back():
    cfg = _cfg()
    state = _state(cfg)
    kb = default_kb()
    player = LLMPlayer(cfg, provider=_FakeProvider(boom=True))
    assert player.decide(state, kb) == HeuristicPlayer().decide(state, kb)


def test_make_provider_builds_claudecli():
    from agent.providers import ClaudeCliProvider, make_provider
    p = make_provider({"provider": "claudecli",
                       "claudecli": {"command": "claude", "timeout": 5}})
    assert isinstance(p, ClaudeCliProvider)
    assert p.command == "claude" and p.timeout == 5


def test_claudecli_provider_feeds_prompt_on_stdin_and_returns_stdout():
    import subprocess
    from unittest.mock import patch

    from agent.providers import ClaudeCliProvider

    class _Res:
        stdout, stderr = "  move 2\n", ""

    captured = {}

    def _fake_run(cmd, input=None, capture_output=None, text=None, timeout=None):
        captured["cmd"], captured["input"] = cmd, input
        return _Res()

    with patch.object(subprocess, "run", _fake_run):
        out = ClaudeCliProvider(command="claude").complete("SYSTEM RULES", "STATE HERE")

    assert out == "move 2"                                  # stdout, stripped
    assert captured["cmd"][:2] == ["claude", "-p"]          # headless print mode
    assert "SYSTEM RULES" in captured["input"] and "STATE HERE" in captured["input"]
