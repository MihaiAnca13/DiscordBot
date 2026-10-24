"""Legion of Midas: Midas Touch and All That Glitters."""
from Buttons.Turn import TurnButtons
from Buttons.Upgrade import UpgradeButtons
from helpers import FactionData
from helpers.DrawHelper import DrawHelper
from tests.fakes import FakeInteraction, buttons, player_helper, reload


def test_midas_touch_costs_one_and_adds_an_activation(start_game, run):
    game, channel = start_game(factions=["mid", "eri"])
    state = reload(game)
    player = state.get_player(1)
    player["money"] = 10
    state.update()

    run(TurnButtons.midasTouch(player, state, FakeInteraction(channel)))
    labels = list(buttons(channel).values())
    assert "Build (+1 activation, 1 money)" in labels

    interaction = FakeInteraction(channel)
    run(TurnButtons.midasAction(player, state, interaction, "midasAction_build"))
    after = reload(game).get_player(1)
    assert after["money"] == 9
    assert after["midasBoost"] == "build"
    assert FactionData.action_apt(after, "build") == 3


def test_midas_touch_surcharge_with_seven_or_fewer_disks(start_game, run):
    game, channel = start_game(factions=["mid", "eri"])
    state = reload(game)
    player = state.get_player(1)
    player["influence_discs"] = 7
    player["money"] = 10
    state.update()

    run(TurnButtons.midasTouch(player, state, FakeInteraction(channel)))
    labels = list(buttons(channel).values())
    assert "Build (+1 activation, 2 money)" in labels
    assert "Research (+1 activation, 4 money)" in labels


def test_all_that_glitters_gives_one_money_for_passing_first(start_game, press):
    game, channel = start_game(factions=["mid", "eri"])
    state = reload(game)
    player = state.get_player(1)
    player["money"] = 0
    state.update()

    press(channel, 1, "FCIDblue_passForRound")

    after = reload(game).get_player(1)
    assert after["money"] == 1
    assert after["firstPlayer"] is True


def test_free_ship_part_editor_keeps_the_done_flow(start_game, run):
    game, channel = start_game(factions=["mid", "eri"])
    player = game.get_player(1)

    run(UpgradeButtons.chooseUpgrade(game, player, FakeInteraction(channel),
                                     "chooseUpgrade_1_interceptor_ioc_hul_0_free",
                                     player_helper(game, "blue")))

    menu = buttons(channel)
    assert "FCIDblue_deleteMsg" in menu
    assert any(cid.startswith("FCIDblue_upgradeShip_1_") and cid.endswith("_free") for cid in menu)
