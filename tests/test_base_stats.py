"""Structural completeness of the base-stats KB: all 151 Gen 1 species present, dex
1-151 exactly once, valid Gen-1 types, and every species usable by the harness
(name<->dex round-trip, stat computation). The specific base-stat *values* are
verified against a canonical RBY source separately; this locks the shape."""
from __future__ import annotations

from battle.damage import battle_stats
from kb import KB

GEN1_TYPES = {"normal", "fire", "water", "electric", "grass", "ice", "fighting",
              "poison", "ground", "flying", "psychic", "bug", "rock", "ghost", "dragon"}


def test_all_151_present_with_unique_dex():
    kb = KB()
    assert len(kb.base_stats) == 151
    dexes = sorted(v["dex"] for v in kb.base_stats.values())
    assert dexes == list(range(1, 152))


def test_types_are_gen1_only():
    kb = KB()
    for name, v in kb.base_stats.items():
        assert 1 <= len(v["types"]) <= 2, name
        assert all(t in GEN1_TYPES for t in v["types"]), (name, v["types"])


def test_every_species_has_five_positive_stats():
    kb = KB()
    for name, v in kb.base_stats.items():
        base = v["base"]
        assert set(base) == {"hp", "atk", "def", "spc", "spe"}, name
        assert all(isinstance(base[k], int) and base[k] > 0 for k in base), name


def test_name_dex_round_trip_and_stat_math():
    kb = KB()
    for name, v in kb.base_stats.items():
        assert kb.name_for(v["dex"]) == name          # dex -> name round-trips
        stats = battle_stats(v["base"], level=50)      # stat math works for all
        assert stats["hp"] > 0 and stats["spe"] > 0
