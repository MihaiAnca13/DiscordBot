"""Heralds of Ragnarok species rules: Raid, Regroup, the alternate blueprints and the
starting cruiser.

Raid reuses the existing Build flow from a Move action; Regroup reuses the existing
Move flow from a Build action. Both are one extra activation of the other type, once
per action, and never a second influence disc.
"""
from PIL import Image
import pytest

from helpers.DrawHelper import DrawHelper
from helpers.ShipHelper import PlayerShip
from tests.fakes import buttons, player_stats, reload


@pytest.fixture(autouse=True)
def _no_tile_render(monkeypatch):
    """These tests cover action bookkeeping, not rendering; real art loads the image cache."""
    monkeypatch.setattr(DrawHelper, "board_tile_image_file", lambda self, position: None)
    monkeypatch.setattr(DrawHelper, "mergeLocationsFile", lambda self, positions: None)
    monkeypatch.setattr(DrawHelper, "use_image", lambda self, filename: Image.new("RGBA", (1024, 890)))
    monkeypatch.setattr(DrawHelper, "use_resized_image",
                        lambda self, filename, size: self.use_image(filename).resize(size))


def setup_game(start_game):
    game, channel = start_game(factions=["her", "eri"])
    # Two free ring-1 sectors, both valid destinations from the home sector.
    for tile, orientation in (("301", 0), ("302", 60)):
        game.add_tile(tile, orientation, "202")
    game.get_player(1)["materials"] = 8
    game.update()
    return game, channel


def edited_menu(interaction):
    return {child.custom_id: child.label for child in interaction.message.edited["view"].children}


def press_edited(press, channel, interaction, prefix):
    custom_id = next(cid for cid in edited_menu(interaction) if cid.startswith(prefix))
    return press(channel, 1, custom_id, interaction.message)


def move_cruiser(press, channel, origin="201", destination="301", move_count="1", suffix=""):
    press(channel, 1, next(cid for cid in buttons(channel)
                           if cid.startswith(f"FCIDblue_moveFrom_{origin}_{move_count}") and suffix in cid))
    press(channel, 1, next(cid for cid in buttons(channel)
                           if "moveThisShip" in cid and "cruiser" in cid and suffix in cid))
    return press(channel, 1, next(cid for cid in buttons(channel)
                                  if f"moveTo_{origin}_cruiser_{destination}_{move_count}" in cid
                                  and suffix in cid))


def finish_raid_build(press, channel, move_count=1):
    press(channel, 1, f"FCIDblue_herRaidBuild_{move_count}")
    press(channel, 1, f"FCIDblue_buildIn_201_herRaid_{move_count}")
    inter = press(channel, 1, next(cid for cid in buttons(channel)
                                   if cid.startswith("FCIDblue_buildShip_") and "Interceptor" in cid))
    inter = press_edited(press, channel, inter, "FCIDblue_finishBuild_")
    spend = buttons(channel)
    inter = press(channel, 1, next(cid for cid in spend if cid.startswith("FCIDblue_spendMaterial_")))
    inter = press_edited(press, channel, inter, "FCIDblue_finishSpendForBuild_")
    return inter


def finish_standard_build(press, channel, ship="Interceptor"):
    press(channel, 1, "FCIDblue_buildIn_201")
    inter = press(channel, 1, next(cid for cid in buttons(channel)
                                   if cid.startswith("FCIDblue_buildShip_") and ship in cid))
    inter = press_edited(press, channel, inter, "FCIDblue_finishBuild_")
    spend = buttons(channel)
    inter = press(channel, 1, next(cid for cid in spend if cid.startswith("FCIDblue_spendMaterial_")))
    return press_edited(press, channel, inter, "FCIDblue_finishSpendForBuild_")


# --- Raid --------------------------------------------------------------------

def test_raid_build_before_the_move_spends_one_disc_and_returns_to_move(start_game, press):
    game, channel = setup_game(start_game)
    press(channel, 1, "FCIDblue_startMove")
    assert "FCIDblue_herRaidBuild_1" in buttons(channel)

    press(channel, 1, "FCIDblue_herRaidBuild_1")
    chooser = buttons(channel)
    assert "FCIDblue_buildIn_201_herRaid_1" in chooser
    assert not [cid for cid in chooser if "herRegroupMove" in cid]

    press(channel, 1, "FCIDblue_buildIn_201_herRaid_1")
    assert any("up to 1 units" in content for content, _kwargs in channel.sent)

    finish_raid_build(press, channel)
    state = reload(game)
    player = state.get_player(1)
    assert player["materials"] == 4
    assert player["influence_discs"] == 11
    assert player["move_action_counters"] == 1
    assert player["build_action_counters"] == 0
    assert player["herCrossUsed"] is True
    assert player["herRaidCharged"] is True
    assert "blue-int" in state.gamestate["board"]["201"]["player_ships"]
    # Back on the Move chooser with the first move still available, and no second Raid build.
    menu = buttons(channel)
    assert "FCIDblue_moveFrom_201_1" in menu
    assert not [cid for cid in menu if "herRaidBuild" in cid]

    move_cruiser(press, channel)
    state = reload(game)
    player = state.get_player(1)
    assert player["influence_discs"] == 11
    assert player["move_action_counters"] == 1
    assert not player.get("herRaidCharged")
    assert "Moved a cruiser" in player["detailsOflastAction"]
    assert "Built" in player["detailsOflastAction"]


def test_raid_build_after_the_move_does_not_spend_a_second_disc(start_game, press):
    game, channel = setup_game(start_game)
    press(channel, 1, "FCIDblue_startMove")
    move_cruiser(press, channel)
    assert "FCIDblue_herRaidBuild_2" in buttons(channel)

    press(channel, 1, "FCIDblue_herRaidBuild_2")
    press(channel, 1, "FCIDblue_buildIn_201_herRaid_2")
    inter = press(channel, 1, next(cid for cid in buttons(channel)
                                   if cid.startswith("FCIDblue_buildShip_") and "Interceptor" in cid))
    inter = press_edited(press, channel, inter, "FCIDblue_finishBuild_")
    spend = buttons(channel)
    inter = press(channel, 1, next(cid for cid in spend if cid.startswith("FCIDblue_spendMaterial_")))
    press_edited(press, channel, inter, "FCIDblue_finishSpendForBuild_")

    state = reload(game)
    player = state.get_player(1)
    assert player["influence_discs"] == 11
    assert player["move_action_counters"] == 1
    assert player["build_action_counters"] == 0
    assert player["herCrossUsed"] is True
    assert "blue-int" in state.gamestate["board"]["201"]["player_ships"]
    # The second move is still available and Raid is used up.
    menu = buttons(channel)
    assert "FCIDblue_moveFrom_301_2" in menu
    assert not [cid for cid in menu if "herRaidBuild" in cid]


def test_raid_nested_build_allows_only_one_unit(start_game, press):
    game, channel = setup_game(start_game)
    press(channel, 1, "FCIDblue_startMove")
    press(channel, 1, "FCIDblue_herRaidBuild_1")
    press(channel, 1, "FCIDblue_buildIn_201_herRaid_1")
    first = press(channel, 1, next(cid for cid in buttons(channel)
                                   if cid.startswith("FCIDblue_buildShip_") and "Interceptor" in cid))
    menu = edited_menu(first)
    second = press_edited(press, channel, first, "FCIDblue_buildShip_")
    assert "cannot build any more units" in second.message.edited["content"]
    assert "FCIDblue_finishBuild_blue-int_4_201_herRaid_1" in menu


def test_raid_double_press_builds_only_one_unit(start_game, press):
    game, channel = setup_game(start_game)
    press(channel, 1, "FCIDblue_startMove")
    press(channel, 1, "FCIDblue_herRaidBuild_1")
    press(channel, 1, "FCIDblue_buildIn_201_herRaid_1")
    inter = press(channel, 1, next(cid for cid in buttons(channel)
                                   if cid.startswith("FCIDblue_buildShip_") and "Interceptor" in cid))
    inter = press_edited(press, channel, inter, "FCIDblue_finishBuild_")
    spend = buttons(channel)
    inter = press(channel, 1, next(cid for cid in spend if cid.startswith("FCIDblue_spendMaterial_")))
    finish = next(cid for cid in edited_menu(inter) if cid.startswith("FCIDblue_finishSpendForBuild_"))
    message = inter.message
    press(channel, 1, finish, message)
    press(channel, 1, finish, message)

    state = reload(game)
    assert state.gamestate["board"]["201"]["player_ships"].count("blue-int") == 1
    assert state.get_player(1)["ship_stock"][0] == 7


# --- Regroup -----------------------------------------------------------------

def test_regroup_move_before_building_spends_one_disc_and_returns_to_build(start_game, press):
    game, channel = setup_game(start_game)
    press(channel, 1, "FCIDblue_startBuild")
    assert "FCIDblue_herRegroupMove_before" in buttons(channel)

    press(channel, 1, "FCIDblue_herRegroupMove_before")
    menu = buttons(channel)
    assert "FCIDblue_moveFrom_201_1_herRegroup_before" in menu
    assert not [cid for cid in menu if "herRaidBuild" in cid]
    assert "FCIDblue_herBackToBuild" in menu

    move_cruiser(press, channel, suffix="_herRegroup_before")
    state = reload(game)
    player = state.get_player(1)
    assert player["influence_discs"] == 11
    assert player["build_action_counters"] == 1
    assert player["move_action_counters"] == 0
    assert player["herCrossUsed"] is True
    assert "blue-cru" in state.gamestate["board"]["301"]["player_ships"]
    # Back at the Build tile chooser, and the Regroup move is used up.
    menu = buttons(channel)
    assert "FCIDblue_buildIn_201" in menu
    assert not [cid for cid in menu if "herRegroupMove" in cid]

    finish_standard_build(press, channel)
    state = reload(game)
    player = state.get_player(1)
    assert player["influence_discs"] == 11
    assert player["build_action_counters"] == 1
    assert player["move_action_counters"] == 0
    assert "blue-int" in state.gamestate["board"]["201"]["player_ships"]


def test_regroup_move_after_building_ends_the_build_phase(start_game, press):
    game, channel = setup_game(start_game)
    press(channel, 1, "FCIDblue_startBuild")
    finish_standard_build(press, channel)
    menu = buttons(channel)
    assert "FCIDblue_herRegroupMove_after" in menu
    assert "FCIDblue_finishAction" in menu

    press(channel, 1, "FCIDblue_herRegroupMove_after")
    move_cruiser(press, channel, suffix="_herRegroup_after")
    state = reload(game)
    player = state.get_player(1)
    assert player["influence_discs"] == 11
    assert player["build_action_counters"] == 1
    assert player["move_action_counters"] == 0
    assert player["herCrossUsed"] is True
    # The move ended the build phase; only the normal end-of-action screen remains.
    menu = buttons(channel)
    assert "FCIDblue_endTurn" in menu
    assert not [cid for cid in menu if "buildIn" in cid]
    assert not [cid for cid in menu if "herRegroupMove" in cid]


def test_regroup_move_is_exactly_one_activation(start_game, press):
    game, channel = setup_game(start_game)
    press(channel, 1, "FCIDblue_startBuild")
    press(channel, 1, "FCIDblue_herRegroupMove_before")
    # No "Move an additional ship" inside the nested move.
    assert not [cid for cid in buttons(channel) if "startMove" in cid or "additional" in str(cid)]
    move_cruiser(press, channel, suffix="_herRegroup_before")
    state = reload(game)
    assert state.gamestate["board"]["301"]["player_ships"].count("blue-cru") == 1
    assert "blue-cru" not in state.gamestate["board"]["201"]["player_ships"]


def test_back_to_build_does_not_use_the_regroup_activation(start_game, press):
    game, channel = setup_game(start_game)
    press(channel, 1, "FCIDblue_startBuild")
    press(channel, 1, "FCIDblue_herRegroupMove_before")
    press(channel, 1, "FCIDblue_herBackToBuild")
    state = reload(game)
    player = state.get_player(1)
    assert player["influence_discs"] == 11
    assert player["build_action_counters"] == 1
    assert player["move_action_counters"] == 0
    assert player.get("herCrossUsed") is not True
    assert "FCIDblue_herRegroupMove_before" in buttons(channel)


# --- Reactions ---------------------------------------------------------------

def test_reactions_do_not_offer_the_other_activation(start_game, press):
    game, channel = setup_game(start_game)
    game.get_player(1)["passed"] = True
    game.update()

    press(channel, 1, "FCIDblue_startMove")
    assert not [cid for cid in buttons(channel) if "herRaidBuild" in cid]
    press(channel, 1, "FCIDblue_startBuild")
    assert "FCIDblue_herRegroupMove_before" not in buttons(channel)


# --- Influence and action summary ---------------------------------------------

def test_raid_uses_one_disc_and_upkeep_returns_it(start_game, press):
    game, channel = setup_game(start_game)
    press(channel, 1, "FCIDblue_startMove")
    finish_raid_build(press, channel)
    move_cruiser(press, channel)

    state = reload(game)
    player = state.get_player(1)
    assert player["influence_discs"] == 11
    assert player["lastAction"] == "move"
    assert "Built" in player["detailsOflastAction"]
    assert "Moved a cruiser" in player["detailsOflastAction"]

    from helpers.PlayerHelper import PlayerHelper
    helper = PlayerHelper(state.get_player_from_color("blue"), player)
    helper.upkeep()
    state.update_player(helper)
    player = reload(state).get_player(1)
    assert player["influence_discs"] == 12
    assert player["move_action_counters"] == 0
    assert player["build_action_counters"] == 0


# --- Blueprints ---------------------------------------------------------------

def test_blueprint_menus_offer_every_printed_slot(start_game, press):
    game, channel = setup_game(start_game)
    press(channel, 1, "FCIDblue_startUpgrade")
    inter = press(channel, 1, next(cid for cid in buttons(channel)
                                   if cid.startswith("FCIDblue_upgradeShip_") and "interceptor" in cid))
    assert len(inter.message.edited["view"].children) == 5 + 1  # five parts plus "Choose Different Ship"

    inter = press_edited(press, channel, inter, "FCIDblue_chooseDifferentShip_")
    inter = press(channel, 1, next(cid for cid in buttons(channel)
                                   if cid.startswith("FCIDblue_upgradeShip_") and "cruiser" in cid))
    assert len(inter.message.edited["view"].children) == 6 + 1


def test_the_extra_interceptor_hull_is_a_replaceable_slot(start_game, press):
    game, channel = setup_game(start_game)
    press(channel, 1, "FCIDblue_startUpgrade")
    inter = press(channel, 1, next(cid for cid in buttons(channel)
                                   if cid.startswith("FCIDblue_upgradeShip_") and "interceptor" in cid))
    inter = press(channel, 1, next(cid for cid in edited_menu(inter)
                                   if cid.startswith("FCIDblue_selectOldPart_2_interceptor_hul_")))
    part_buttons = edited_menu(inter)
    choice = next(cid for cid in part_buttons if "_interceptor_hul_elc_3_" in cid)
    press(channel, 1, choice, inter.message)

    player = reload(game).get_player(1)
    assert player["interceptor_parts"] == ["ioc", "nus", "nud", "elc", "empty"]
    model = PlayerShip(player, "interceptor")
    assert model.hull == 0 and model.computer == 1 and model.check_valid_ship()


def test_cruiser_has_no_hull_slot_and_costs_four(start_game):
    game, _channel = setup_game(start_game)
    player = game.get_player(1)
    model = PlayerShip(player, "cruiser")
    assert model.hull == 0
    assert model.cost == 4
    assert len(player["cruiser_parts"]) == 6
    assert "hul" not in player["cruiser_parts"]


def test_only_three_more_cruisers_are_buildable_after_the_starting_one(start_game, press):
    game, channel = setup_game(start_game)
    player = game.get_player(1)
    assert player["ship_stock"][1] == 3
    assert game.gamestate["board"]["201"]["player_ships"] == ["blue-cru"]
    player["materials"] = 100
    game.update()

    press(channel, 1, "FCIDblue_startBuild")
    # Two cruisers in the first build activation batch.
    press(channel, 1, "FCIDblue_buildIn_201")
    inter = press(channel, 1, next(cid for cid in buttons(channel)
                                   if cid.startswith("FCIDblue_buildShip_") and "Cruiser" in cid))
    second = next(cid for cid in edited_menu(inter)
                  if cid.startswith("FCIDblue_buildShip_") and "Cruiser" in cid)
    inter = press(channel, 1, second, inter.message)
    inter = press_edited(press, channel, inter, "FCIDblue_finishBuild_")
    spend = buttons(channel)
    inter = press(channel, 1, next(cid for cid in spend if cid.startswith("FCIDblue_spendMaterial_")))
    press_edited(press, channel, inter, "FCIDblue_finishSpendForBuild_")

    # A third cruiser through Build Somewhere Else.
    press(channel, 1, "startBuild2_deleteMsg")
    press(channel, 1, "FCIDblue_buildIn_201")
    inter = press(channel, 1, next(cid for cid in buttons(channel)
                                   if cid.startswith("FCIDblue_buildShip_") and "Cruiser" in cid))
    inter = press_edited(press, channel, inter, "FCIDblue_finishBuild_")
    spend = buttons(channel)
    inter = press(channel, 1, next(cid for cid in spend if cid.startswith("FCIDblue_spendMaterial_")))
    press_edited(press, channel, inter, "FCIDblue_finishSpendForBuild_")

    state = reload(game)
    assert state.get_player(1)["ship_stock"][1] == 0
    press(channel, 1, "startBuild2_deleteMsg")
    press(channel, 1, "FCIDblue_buildIn_201")
    assert not [cid for cid in buttons(channel) if "Cruiser" in cid]
