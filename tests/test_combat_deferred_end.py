"""A deferred multi-target hit must still end the pairing when it kills the last ship.

Carapace missiles and rift dice defer combat-end checks until their target button is
pressed. If that hit removes the last ship of a side, the deferred path must call
`checkCombatEnd`; otherwise the pairing never advances.
"""
from helpers.CombatHelper import Combat
from tests.fakes import FakeInteraction, POS, player_stats


def test_deferred_multi_target_hit_that_ends_the_side_calls_check_combat_end(make_game, monkeypatch, run):
    blue = player_stats("hyd", color="blue", name="Hydran Progress")
    red = player_stats("hyd", color="red", name="Hydran Progress")
    game = make_game({
        "advanced_ai": 0,
        "wa_ai": 0,
        "player_count": 2,
        "players": {"1": blue, "2": red},
        "board": {POS: {"owner": 0, "sector": 101, "disctile": 0,
                        "player_ships": ["red-int"],
                        "attacker": "blue", "defender": "red",
                        "combatants": ["blue", "red"]}},
    })

    checked = []
    prompted = []

    async def check(game, interaction, pos, old_length):
        checked.append((pos, old_length))

    async def prompt(*args, **kwargs):
        prompted.append(True)

    monkeypatch.setattr(Combat, "checkCombatEnd", staticmethod(check))
    monkeypatch.setattr(Combat, "promptNextSpeed", staticmethod(prompt))

    run(Combat.assignHitTo(game, f"assignHitTo_{POS}_blue_red-int_6_5_defer",
                           FakeInteraction(), True))

    assert "red-int" not in game.gamestate["board"][POS]["player_ships"]
    assert checked == [(POS, 1)]
    assert not prompted
