from tests.fakes import buttons, reload


def find_button(channel, prefix):
    return next(
        button.custom_id
        for content, kwargs in reversed(channel.sent)
        for button in getattr(kwargs.get("view"), "children", [])
        if button.custom_id.startswith(prefix)
    )


def test_wulfen_explores_and_passes_a_first_round(start_game, press):
    game, channel = start_game(factions=["wul", "eri"])
    game.gamestate["tile_deck_100"] = ["102"]
    game.update()

    press(channel, 1, "FCIDblue_startExplore")
    explore = find_button(channel, "FCIDblue_exploreTile_1")
    position = explore.split("_")[2]
    press(channel, 1, explore)
    press(channel, 1, find_button(channel, f"FCIDblue_placeTile_{position}_"))
    press(channel, 1, find_button(channel, f"FCIDblue_addInfluenceFinish_{position}"))
    assert reload(game).gamestate["board"][position]["owner"] == "blue"
    press(channel, 1, "FCIDblue_finishAction")
    press(channel, 1, "FCIDblue_endTurn")

    press(channel, 2, "FCIDred_endTurn")
    press(channel, 1, "FCIDblue_passForRound")
    press(channel, 2, "FCIDred_passForRound")

    final_game = reload(game)
    assert final_game.is_everyone_passed()
    assert "runUpkeep" in buttons(channel)

    player = final_game.get_player(1)
    assert player["name"] == "The Wulfen"
    assert player["home_planet"] == "252"
    assert player["grid_tech"] == ["fus"]
    assert "interceptor_parts" not in player
    assert player["explore_action_counters"] == 1
    assert len(player["owned_tiles"]) == 2
    assert player["passed"]
    # 2/3/3 from the card, plus the 2 money for passing first.
    assert (player["materials"], player["science"], player["money"]) == (2, 3, 5)
    assert final_game.gamestate["board"]["201"]["player_ships"] == ["blue-cru"]
