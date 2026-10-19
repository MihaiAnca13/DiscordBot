import json

from helpers.DrawHelper import DrawHelper
from tests.fakes import buttons, reload


def find_button(channel, prefix):
    return next(
        button.custom_id
        for content, kwargs in reversed(channel.sent)
        for button in getattr(kwargs.get("view"), "children", [])
        if button.custom_id.startswith(prefix)
    )


def test_turtugan_explores_with_a_reserved_sector_then_passes(start_game, press, monkeypatch):
    monkeypatch.setattr(DrawHelper, "show_select_techs", lambda self, *args, **kwargs: None)
    game, channel = start_game(factions=["tur", "eri"])
    player = game.get_player(1)
    reserve = player["deep_space_sectors"]
    sectors = json.load(open("data/sectors.json"))
    reserved = next(tile for tile in reserve if sectors[tile]["ancient"] == 0)

    press(channel, 1, "FCIDblue_startExplore")
    position = next(cid.split("_")[2] for cid in buttons(channel)
                    if cid.startswith("FCIDblue_exploreTile_3"))
    press(channel, 1, f"FCIDblue_exploreTile_{position}")
    press(channel, 1, find_button(channel, f"FCIDblue_reservedTile_{position}_{reserved}_"))
    press(channel, 1, find_button(channel, f"FCIDblue_placeTile_{position}_{reserved}_"))
    press(channel, 1, find_button(channel, f"FCIDblue_addInfluenceFinish_{position}"))
    press(channel, 1, "FCIDblue_finishAction")
    press(channel, 1, "FCIDblue_endTurn")

    press(channel, 2, "FCIDred_passForRound")
    press(channel, 1, "FCIDblue_passForRound")
    state = reload(game)
    assert state.is_everyone_passed()
    assert "runUpkeep" in buttons(channel)
    assert state.gamestate["board"][position]["sector"] == reserved
    assert state.gamestate["board"][position]["owner"] == "blue"
    assert state.get_player(1)["deep_space_sectors"] == [tile for tile in reserve if tile != reserved]
    assert state.get_player(1)["explore_action_counters"] == 1
    assert len(state.get_player(1)["owned_tiles"]) == 2
    assert state.get_player(1)["passed"] is True
    assert (state.get_player(1)["materials"], state.get_player(1)["science"],
            state.get_player(1)["money"]) == (4, 3, 3)

    press(channel, 1, "runUpkeep")
    assert reload(game).gamestate["roundNum"] == 2
