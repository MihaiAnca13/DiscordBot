import random

import pytest

from Buttons.Draft import DraftButtons
from commands.setup_commands import SetupCommands
from helpers.GamestateHelper import GamestateHelper
from setup.GameInit import GameInit
from tests.fakes import FakeChannel, FakeGame, FakeInteraction, reload

SUPPORTED_COLORS = ["blue", "red", "green", "yellow", "purple", "white", "pink", "brown", "teal"]


@pytest.mark.parametrize("community_mode", [False, True])
def test_turtugan_only_appears_in_community_draft(community_mode):
    standard_buttons = DraftButtons.getDraftButtons(FakeGame(False, community_mode))
    community_buttons = DraftButtons.getDraftButtons(FakeGame(True, community_mode))

    assert len(standard_buttons.children) == 16
    assert [button.label for button in standard_buttons.children].count("Turtugan") == 0
    assert [button.label for button in community_buttons.children].count("Turtugan") == 1
    assert len(community_buttons.children) == 23


def test_turtugan_color_is_supported():
    assert DraftButtons.getColor("tur") in SUPPORTED_COLORS
    assert DraftButtons.getColor("tur") == "teal"


def test_turtugan_respects_explicit_bans():
    game = FakeGame(True, False)
    game.gamestate["bannedFactions"] = ["tur"]
    assert "Turtugan" not in [button.label for button in DraftButtons.getDraftButtons(game).children]


def test_turtugan_and_the_exiles_share_teal_without_blocking_each_other():
    game = FakeGame(True, False)
    game.gamestate["draftedFactions"] = [(1, "exl")]
    keys = {button.custom_id.split("_")[1] for button in DraftButtons.getDraftButtons(game).children}
    assert "tur" in keys

    game.gamestate["draftedFactions"] = [(1, "tur")]
    keys = {button.custom_id.split("_")[1] for button in DraftButtons.getDraftButtons(game).children}
    assert "exl" in keys


def test_turtugan_faction_choice_exists():
    choices = [(choice.name, choice.value) for choice in SetupCommands.factionChoices]
    assert ("Turtugan", "tur") in choices


def test_setup_gives_turtugan_its_home_ships_and_reserve(start_game):
    game, _channel = start_game(factions=["tur", "eri"])
    player = game.get_player(1)
    assert player["name"] == "Turtugan"
    assert player["color"] == "blue"
    assert player["home_planet"] == "253"
    assert player["military_tech"] == ["stb"]
    assert player["reputation_track"] == ["amb", "mixed", "mixed", "mixed"]
    assert (player["materials"], player["science"], player["money"]) == (4, 3, 3)
    assert player["move_apt"] == 2
    assert player["ship_stock"] == [8, 4, 2, 3]
    assert game.gamestate["board"]["201"]["player_ships"] == ["blue-sb"]
    reserve = player["deep_space_sectors"]
    assert len(reserve) == 2
    assert all(tile.isdigit() for tile in reserve)
    assert reserve[0] in game.displayPlayerStats(player)
    assert reserve[1] in game.displayPlayerStats(player)


def test_only_turtugan_gets_a_deep_space_reserve(start_game):
    game, _channel = start_game(factions=["eri", "hyd"])
    assert "deep_space_sectors" not in game.get_player(1)


def test_general_setup_posts_the_reserved_sectors(games_dir, run):
    random.seed(0)
    GameInit("T", [[1, "<@1>"], [2, "<@2>"]], "def", True, True, False, False).create_game()
    game = GamestateHelper(None, "aeb1")
    game.setup_techs_and_outer_rim(2, False, False)
    channel = FakeChannel("aeb1-actions")
    interaction = FakeInteraction(channel, role_names=["aeb1"])
    run(DraftButtons.generalSetup(interaction, game, [1, 2], ["tur", "eri"]))

    state = reload(game)
    reserve = state.get_player(1)["deep_space_sectors"]
    assert state.get_player(1)["color"] == "teal"
    assert len(reserve) == 2
    messages = [content for content, _ in channel.sent if content]
    reserve_messages = [content for content in messages if "Deep Space Explorers reserves S3 sector" in content]
    assert len(reserve_messages) == 2
    assert all(tile in " ".join(reserve_messages) for tile in reserve)
    assert state.gamestate["board"]["201"]["sector"] == "253"
