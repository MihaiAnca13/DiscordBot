from Buttons.Draft import DraftButtons
from commands.setup_commands import SetupCommands
from tests.fakes import FakeGame, reload


def test_horde_only_appears_in_the_community_draft():
    assert len(DraftButtons.getDraftButtons(FakeGame(False, False)).children) == 16
    more = DraftButtons.getDraftButtons(FakeGame(True, False), 24)
    assert [button.label for button in more.children] == ["Children of Cog", "Legion of Midas",
                                                          "The Horde", "Vorlons",
                                                          "Hegemony of the Highest Cushion"]


def test_horde_colour_and_bans():
    assert DraftButtons.getColor("hor") == "red"
    game = FakeGame(True, False)
    game.gamestate["bannedFactions"] = ["hor"]
    labels = [button.label for button in DraftButtons.getDraftButtons(game, 24).children]
    assert "The Horde" not in labels


def test_horde_faction_choice_exists():
    choices = [(choice.name, choice.value) for choice in SetupCommands.factionChoices]
    assert ("The Horde", "hor") in choices


def test_horde_setup_loads_its_data(start_game):
    game, _channel = start_game(factions=["hor", "eri"])
    state = reload(game)
    player = state.get_player(1)
    assert player["name"].startswith("The Horde")
    assert player["home_planet"] == "288"
    assert player["military_tech"] == ["neb"] and player["nano_tech"] == ["nar"]
    assert player["build_apt"] == 3  # printed 2 plus the starting Nanorobots activation
    assert player["colony_ships"] == 4
    assert (player["money_pop_cubes"], player["material_pop_cubes"], player["science_pop_cubes"]) == (11, 11, 12)
