import pytest

from Buttons.Draft import DraftButtons
from commands.setup_commands import SetupCommands
from tests.fakes import FakeGame


@pytest.mark.parametrize("community_mode", [False, True])
def test_kurita_only_appears_in_community_draft(community_mode):
    standard_buttons = DraftButtons.getDraftButtons(FakeGame(False, community_mode))
    community_buttons = DraftButtons.getDraftButtons(FakeGame(True, community_mode))

    assert len(standard_buttons.children) == 16
    assert [button.label for button in standard_buttons.children].count("Kurita Prefecture") == 0
    assert [button.label for button in community_buttons.children].count("Kurita Prefecture") == 1
    assert len(community_buttons.children) == 20


def test_kurita_faction_color_is_supported_setup_color():
    supported_colors = ["blue", "red", "green", "yellow", "purple", "white", "pink", "brown", "teal"]
    assert DraftButtons.getColor("kur") == "red"
    assert DraftButtons.getColor("kur") in supported_colors


@pytest.mark.parametrize("drafted, available", [
    (["eri"], {"kur", "atl", "ra", "tm"}),   # red is shared with a standard faction, never a block
    (["ter3"], {"kur", "atl", "ra", "tm"}),
    (["atl"], {"kur", "ra", "tm", "eri", "ter3"}),
    (["kur"], {"atl", "ra", "tm", "eri", "ter3"}),
    (["kur", "eri"], {"atl", "ra", "tm"}),
])
def test_kurita_does_not_share_colour_blocks(drafted, available):
    game = FakeGame(True, False)
    game.gamestate["draftedFactions"] = list(enumerate(drafted))

    buttons = DraftButtons.getDraftButtons(game)
    available_keys = {button.custom_id.split("_")[1] for button in buttons.children}

    assert available_keys & {"kur", "atl", "ra", "tm", "eri", "ter3"} == available


def test_kurita_still_respects_explicit_bans():
    game = FakeGame(True, False)
    game.gamestate["bannedFactions"] = ["kur"]

    assert "Kurita Prefecture" not in [button.label for button in DraftButtons.getDraftButtons(game).children]


def test_kurita_faction_choice_exists():
    choices = [(choice.name, choice.value) for choice in SetupCommands.factionChoices]
    assert ("Kurita Prefecture", "kur") in choices
