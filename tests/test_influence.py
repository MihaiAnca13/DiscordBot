import pytest

from tests.fakes import buttons, reload


@pytest.mark.parametrize("faction, initial_ships, refreshed", [
    ("ra", 1, 2), ("tm", 1, 2), ("vor", 0, 1), ("hyd", 1, 3),
])
def test_influence_refreshes_the_factions_colony_ship_allowance(
        start_game, press, faction, initial_ships, refreshed):
    game, channel = start_game(factions=[faction, "eri"])
    game.get_player(1)["colony_ships"] = initial_ships
    game.update()

    press(channel, 1, "FCIDblue_startInfluence")
    allowance = refreshed - initial_ships
    assert f"Refresh {allowance} Colony Ship{'s' if allowance > 1 else ''}" in buttons(channel).values()
    press(channel, 1, "FCIDblue_refreshPopShips")

    assert reload(game).get_player(1)["colony_ships"] == refreshed
