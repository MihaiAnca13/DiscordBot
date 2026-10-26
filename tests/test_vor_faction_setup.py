from Buttons.Draft import DraftButtons
from commands.setup_commands import SetupCommands
from tests.fakes import FakeGame, reload


def test_vorlons_only_appears_in_the_community_draft():
    assert len(DraftButtons.getDraftButtons(FakeGame(False, False)).children) == 16
    more = DraftButtons.getDraftButtons(FakeGame(True, False), 24)
    assert [button.label for button in more.children] == ["Children of Cog", "Legion of Midas",
                                                          "The Horde", "Vorlons",
                                                          "Hegemony of the Highest Cushion"]


def test_vorlons_colour_and_bans():
    assert DraftButtons.getColor("vor") == "purple"
    game = FakeGame(True, False)
    game.gamestate["bannedFactions"] = ["vor"]
    labels = [button.label for button in DraftButtons.getDraftButtons(game, 24).children]
    assert "Vorlons" not in labels


def test_vorlons_faction_choice_exists():
    choices = [(choice.name, choice.value) for choice in SetupCommands.factionChoices]
    assert ("Vorlons", "vor") in choices


def test_vorlons_setup_loads_its_data(start_game):
    game, _channel = start_game(factions=["vor", "eri"])
    state = reload(game)
    player = state.get_player(1)
    assert player["name"].startswith("Vorlons")
    assert player["home_planet"] == "235"
    assert player["nano_tech"] == ["reh"]
    assert player["interceptor_parts"] == ["ioc", "nus", "reh", "nud"]
    assert (player["money_pop_cubes"], player["material_pop_cubes"], player["science_pop_cubes"]) == (12, 11, 11)
