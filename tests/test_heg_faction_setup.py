from Buttons.Draft import DraftButtons
from commands.setup_commands import SetupCommands
from tests.fakes import FakeGame, reload


def test_hegemony_only_appears_in_the_community_draft():
    assert len(DraftButtons.getDraftButtons(FakeGame(False, False)).children) == 16
    community = DraftButtons.getDraftButtons(FakeGame(True, False))
    assert len(community.children) == 25
    more = DraftButtons.getDraftButtons(FakeGame(True, False), 24)
    assert [button.label for button in more.children] == ["Children of Cog", "Legion of Midas",
                                                          "The Horde", "Vorlons",
                                                          "Hegemony of the Highest Cushion"]


def test_hegemony_colour_and_bans():
    assert DraftButtons.getColor("heg") == "orange"
    game = FakeGame(True, False)
    game.gamestate["bannedFactions"] = ["heg"]
    labels = [button.label for button in DraftButtons.getDraftButtons(game, 24).children]
    assert "Hegemony of the Highest Cushion" not in labels


def test_hegemony_faction_choice_exists():
    choices = [(choice.name, choice.value) for choice in SetupCommands.factionChoices]
    assert ("Hegemony of the Highest Cushion", "heg") in choices


def test_hegemony_setup_loads_its_data(start_game):
    game, _channel = start_game(factions=["heg", "eri"])
    state = reload(game)
    player = state.get_player(1)
    assert player["name"].startswith("Hegemony of the Highest Cushion")
    assert player["home_planet"] == "276"
    assert player["nano_tech"] == ["fud"]
    assert player["interceptor_parts"] == ["ioc", "nus", "nud", "empty"]
    assert (player["money_pop_cubes"], player["material_pop_cubes"], player["science_pop_cubes"]) == (11, 11, 11)
