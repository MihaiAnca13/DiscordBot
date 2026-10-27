"""Legion of Midas: Midas Touch and All That Glitters."""
from Buttons.Turn import TurnButtons
from helpers import FactionData
from helpers.GamestateHelper import GamestateHelper
from tests.fakes import FakeInteraction, buttons, reload


def _snapshots(monkeypatch):
    calls = []
    monkeypatch.setattr(GamestateHelper, "updateSaveFile", lambda self: calls.append(1))
    return calls


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


def test_midas_paid_action_writes_a_turn_start_save(start_game, monkeypatch, run):
    game, channel = start_game(factions=["mid", "eri"])
    state = reload(game)
    player = state.get_player(1)
    player["money"] = 10
    state.update()
    snapshots = _snapshots(monkeypatch)

    run(TurnButtons.midasAction(player, state, FakeInteraction(channel), "midasAction_build"))

    assert len(snapshots) == 1
    assert reload(game).get_player(1)["midasBoost"] == "build"


def test_midas_touch_can_be_cancelled_without_paying(start_game, run, press):
    game, channel = start_game(factions=["mid", "eri"])
    state = reload(game)
    player = state.get_player(1)
    player["money"] = 10
    state.update()

    run(TurnButtons.midasTouch(player, state, FakeInteraction(channel)))
    assert "FCIDblue_midasCancel" in buttons(channel)
    press(channel, 1, "FCIDblue_midasCancel")

    assert reload(game).get_player(1)["money"] == 10
    assert any(cid.startswith("FCIDblue_startBuild") for cid in buttons(channel))


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
