from pathlib import Path

import pytest

from Buttons.Draft import DraftButtons
from commands.setup_commands import SetupCommands
from tests.fakes import FakeGame


@pytest.mark.parametrize("community_mode", [False, True])
def test_heralds_only_appears_in_the_community_draft(community_mode):
    standard_buttons = DraftButtons.getDraftButtons(FakeGame(False, community_mode))
    community_buttons = DraftButtons.getDraftButtons(FakeGame(True, community_mode))

    assert len(standard_buttons.children) == 16
    assert [button.label for button in community_buttons.children].count("Heralds of Ragnarok") == 1
    assert len(community_buttons.children) == 24


def test_heralds_faction_color_is_supported_setup_color():
    supported_colors = ["blue", "red", "green", "yellow", "purple", "white", "pink", "brown", "teal"]
    assert DraftButtons.getColor("her") == "yellow"
    assert DraftButtons.getColor("her") in supported_colors


@pytest.mark.parametrize("drafted, available", [
    (["dra"], {"her"}),
    (["ter5"], {"her"}),
    (["her"], {"dra", "ter5"}),
    (["her", "dra"], set()),
    (["ra"], {"dra", "ter5", "her"}),
])
def test_heralds_do_not_take_or_give_colour_blocks(drafted, available):
    game = FakeGame(True, False)
    game.gamestate["draftedFactions"] = list(enumerate(drafted))

    buttons = DraftButtons.getDraftButtons(game)
    available_keys = {button.custom_id.split("_")[1] for button in buttons.children}

    assert available_keys & {"her", "dra", "ter5"} == available


def test_heralds_still_respect_explicit_bans():
    game = FakeGame(True, False)
    game.gamestate["bannedFactions"] = ["her"]

    assert "Heralds of Ragnarok" not in [button.label for button in DraftButtons.getDraftButtons(game).children]


def test_heralds_faction_choice_exists():
    choices = [(choice.name, choice.value) for choice in SetupCommands.factionChoices]
    assert ("Heralds of Ragnarok", "her") in choices


def test_heralds_reference_images_exist():
    for name in ("heralds_board.png", "heralds_info.png"):
        assert Path(f"images/resources/components/factions/{name}").is_file(), name
