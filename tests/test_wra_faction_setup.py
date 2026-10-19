import random

import pytest

from Buttons.Draft import DraftButtons
from commands.setup_commands import SetupCommands
from helpers.GamestateHelper import GamestateHelper
from setup.GameInit import GameInit
from tests.fakes import FakeChannel, FakeGame, FakeInteraction, reload


@pytest.mark.parametrize("community_mode", [False, True])
def test_wra_only_appears_in_community_draft(community_mode):
    standard_buttons = DraftButtons.getDraftButtons(FakeGame(False, community_mode))
    community_buttons = DraftButtons.getDraftButtons(FakeGame(True, community_mode))

    assert len(standard_buttons.children) == 16
    assert [button.label for button in standard_buttons.children].count("The Wraith") == 0
    assert [button.label for button in community_buttons.children].count("The Wraith") == 1
    assert len(community_buttons.children) == 20


def test_wra_faction_color_is_supported_setup_color():
    supported_colors = ["blue", "red", "green", "yellow", "purple", "white", "pink", "brown", "teal"]
    assert DraftButtons.getColor("wra") == "white"
    assert DraftButtons.getColor("wra") in supported_colors


@pytest.mark.parametrize("drafted, expected", [
    (["mec"], {"wra", "hyd"}),   # both are white; community factions never colour-block
    (["wra"], {"mec", "hyd"}),   # and a drafted community faction does not block the standard white
])
def test_the_wraith_does_not_colour_block_mechanema(drafted, expected):
    game = FakeGame(True, False)
    game.gamestate["draftedFactions"] = list(enumerate(drafted))

    available = {button.custom_id.split("_")[1] for button in DraftButtons.getDraftButtons(game).children}

    assert available & {"wra", "mec", "hyd"} == expected


def test_wra_still_respects_explicit_bans():
    game = FakeGame(True, False)
    game.gamestate["bannedFactions"] = ["wra"]

    assert "The Wraith" not in [button.label for button in DraftButtons.getDraftButtons(game).children]


def test_wra_faction_choice_exists():
    choices = [(choice.name, choice.value) for choice in SetupCommands.factionChoices]
    assert ("The Wraith", "wra") in choices


@pytest.mark.parametrize("factions, colors", [
    (["wra", "mec"], {"The Wraith": "white", "Mechanema": "blue"}),
    (["mec", "wra"], {"Mechanema": "white", "The Wraith": "blue"}),
])
def test_multi_faction_setup_assigns_the_faction_colour_it_actually_got(games_dir, run, factions, colors):
    random.seed(0)
    GameInit("Wraith setup", [[1, "<@1>"], [2, "<@2>"]],
             "def", True, True, False, False).create_game()
    game = GamestateHelper(None, "aeb1")
    game.setup_techs_and_outer_rim(2, False, False)
    game.add_tile("000", 0, "001")
    channel = FakeChannel("aeb1-actions")
    interaction = FakeInteraction(channel, role_names=["aeb1"])

    run(DraftButtons.generalSetup(interaction, game, [1, 2], factions))

    state = reload(game).gamestate
    wraith = next(player for player in state["players"].values() if player["name"] == "The Wraith")
    other = next(player for player in state["players"].values() if player["name"] == "Mechanema")
    assert wraith["color"] == colors["The Wraith"]
    assert other["color"] == colors["Mechanema"]
    wraith_home = next(pos for pos, tile in state["board"].items() if tile.get("sector") == "254")
    assert state["board"][wraith_home]["owner"] == wraith["color"]
    assert wraith["military_tech"] == ["phm"]
    assert wraith["reputation_track"] == ["mixed", "rep", "rep", "rep"]
    assert (wraith["money"], wraith["science"], wraith["materials"]) == (2, 4, 4)
    assert wraith["wraithSouls"] == 0
