"""Children of Cog: Infinite Possibilities and Adaptive Transformation."""
import pytest

from Buttons.Upgrade import UpgradeButtons
from helpers.DrawHelper import DrawHelper
from tests.fakes import FakeInteraction, buttons, player_helper, reload


@pytest.fixture(autouse=True)
def _no_tile_render(monkeypatch):
    monkeypatch.setattr(DrawHelper, "board_tile_image_file", lambda self, position: None)
    monkeypatch.setattr(DrawHelper, "mergeLocationsFile", lambda self, positions: None)


def test_infinite_possibilities_is_printed_under_build_and_move():
    from tests.fakes import player_stats
    cog = player_stats("cog")
    assert DrawHelper.action_annotation(cog, "build") == "+1 UPG"
    assert DrawHelper.action_annotation(cog, "move") == "+1 UPG"
    assert DrawHelper.action_annotation(player_stats("hyd"), "build") is None


def test_infinite_possibilities_offers_one_free_upgrade(start_game, press):
    game, channel = start_game(factions=["cog", "eri"])

    press(channel, 1, "FCIDblue_startBuild")
    before = reload(game).get_player(1)["influence_discs"]
    assert "FCIDblue_infiniteUpgrade_build" in buttons(channel)
    inter = press(channel, 1, "FCIDblue_infiniteUpgrade_build")
    assert inter.message.id in channel.deleted

    menu = buttons(channel)
    free_ship = next(cid for cid in menu if cid.startswith("FCIDblue_upgradeShip_1_interceptor_free"))
    inter = press(channel, 1, free_ship)
    old_part = next(cid for cid in inter.message.edited["view"].children
                    if cid.custom_id.startswith("FCIDblue_selectOldPart_")
                    and cid.custom_id.endswith("_free_0"))
    inter = press(channel, 1, old_part.custom_id, inter.message)
    new_part = next(cid for cid in inter.message.edited["view"].children
                    if cid.custom_id.startswith("FCIDblue_chooseUpgrade_")
                    and cid.custom_id.endswith("_hul_0_free"))
    press(channel, 1, new_part.custom_id, inter.message)

    state = reload(game)
    player = state.get_player(1)
    assert player["influence_discs"] == before
    assert player["infinitePossibilitiesUsed"] is True
    assert player["interceptor_parts"] != ["ioc", "nus", "nud", "empty"]

    menu = buttons(channel)
    assert "FCIDblue_finishInfiniteUpgrade" in menu
    assert not any(cid.startswith("FCIDblue_upgradeShip_") for cid in menu)
    press(channel, 1, "FCIDblue_finishInfiniteUpgrade")
    resumed = buttons(channel)
    assert any(cid.startswith("FCIDblue_buildIn_") for cid in resumed)
    assert not any(cid.startswith("FCIDblue_infiniteUpgrade") for cid in resumed)


def test_adaptive_swaps_need_two_ships_in_one_sector():
    from tests.fakes import board_tile, player_stats
    from helpers.GamestateHelper import GamestateHelper

    player = player_stats("cog", color="blue")
    game = GamestateHelper.__new__(GamestateHelper)
    game.gamestate = {"board": {
        "101": {"player_ships": ["blue-int", "blue-int"]},
        "102": {"player_ships": ["blue-cru", "blue-cru"]},
        "103": {"player_ships": ["blue-drd"]},
        "104": {"player_ships": ["blue-cru"]},
    }}
    assert ("int", "cru", 1) in UpgradeButtons.adaptiveSwaps(game, player, "101")
    assert ("cru", "drd", 2) in UpgradeButtons.adaptiveSwaps(game, player, "102")
    assert ("cru", "int", -1) in UpgradeButtons.adaptiveSwaps(game, player, "104")
    assert ("drd", "cru", -2) in UpgradeButtons.adaptiveSwaps(game, player, "103")


def test_adaptive_transformation_applies_and_undoes(start_game, run):
    game, channel = start_game(factions=["cog", "eri"])
    state = reload(game)
    state.gamestate["board"]["201"]["player_ships"] = ["blue-int", "blue-int"]
    state.update()
    player = state.get_player(1)
    player["materials"] = 0
    state.update_player(player_helper(state, "blue"))
    before = reload(state).get_player(1)["influence_discs"]

    interaction = FakeInteraction(channel)
    run(UpgradeButtons.adaptiveSwap(state, player, interaction,
                                    "adaptiveSwap_int_cru_201_3_dummy", player_helper(state, "blue")))

    after = reload(state)
    assert after.gamestate["board"]["201"]["player_ships"] == ["blue-cru"]
    assert after.get_player(1)["materials"] == 1
    assert after.get_player(1)["influence_discs"] == before - 1
    assert after.get_player(1)["adaptiveUndo"]["removed"] == ["blue-int", "blue-int"]
    assert any(cid.startswith("FCIDblue_upgradeShip_") for cid in buttons(channel))

    run(UpgradeButtons.undoAdaptive(state, after.get_player(1), FakeInteraction(channel),
                                    player_helper(state, "blue")))
    restored = reload(state)
    assert restored.gamestate["board"]["201"]["player_ships"] == ["blue-int", "blue-int"]
    assert restored.get_player(1)["materials"] == 0
    assert any(cid.startswith("FCIDblue_upgradeShip_3_") for cid in buttons(channel))


def test_adaptive_undo_refuses_after_the_ship_moved(start_game, run):
    game, channel = start_game(factions=["cog", "eri"])
    state = reload(game)
    state.gamestate["board"]["201"]["player_ships"] = ["blue-int", "blue-int"]
    state.update()
    player = state.get_player(1)
    player["materials"] = 0
    state.update_player(player_helper(state, "blue"))

    run(UpgradeButtons.adaptiveSwap(state, player, FakeInteraction(channel),
                                    "adaptiveSwap_int_cru_201_3_dummy", player_helper(state, "blue")))
    state = reload(state)
    state.gamestate["board"]["201"]["player_ships"].remove("blue-cru")
    state.gamestate["board"]["202"].setdefault("player_ships", []).append("blue-cru")
    state.update()

    interaction = FakeInteraction(channel)
    run(UpgradeButtons.undoAdaptive(state, state.get_player(1), interaction,
                                    player_helper(state, "blue")))
    assert "moved" in interaction.followup.sent[-1][0]
    assert "blue-int" not in state.gamestate["board"]["201"]["player_ships"]


def test_cog_ship_part_editor_still_works(start_game, run):
    game, channel = start_game(factions=["cog", "eri"])
    player = game.get_player(1)

    run(UpgradeButtons.chooseUpgrade(game, player, FakeInteraction(channel),
                                     "chooseUpgrade_1_interceptor_ioc_hul_0_free",
                                     player_helper(game, "blue")))

    menu = buttons(channel)
    assert "FCIDblue_deleteMsg" in menu
    assert any(cid.startswith("FCIDblue_upgradeShip_1_") and cid.endswith("_free") for cid in menu)


def test_adaptive_back_returns_to_the_normal_upgrade_menu(start_game, press):
    game, channel = start_game(factions=["cog", "eri"])
    state = reload(game)
    state.gamestate["board"]["201"]["player_ships"] = ["blue-int", "blue-int"]
    state.update()

    press(channel, 1, "FCIDblue_startUpgrade")
    press(channel, 1, "FCIDblue_adaptiveStart_3_dummy")
    sector = next(cid for cid in buttons(channel) if cid.startswith("FCIDblue_adaptiveSector_"))
    press(channel, 1, sector)
    back = next(cid for cid in buttons(channel) if cid.startswith("FCIDblue_backToUpgrade_"))
    press(channel, 1, back)

    assert any(cid.startswith("FCIDblue_upgradeShip_") for cid in buttons(channel))
