from Buttons.Draft import DraftButtons
from commands.setup_commands import SetupCommands
from tests.fakes import FakeGame, buttons, reload


def test_cog_only_appears_in_the_community_draft():
    assert len(DraftButtons.getDraftButtons(FakeGame(False, False)).children) == 16
    community = DraftButtons.getDraftButtons(FakeGame(True, False))
    assert len(community.children) == 25
    more = DraftButtons.getDraftButtons(FakeGame(True, False), 24)
    assert [button.label for button in more.children] == ["Children of Cog", "Legion of Midas",
                                                          "The Horde", "Vorlons"]


def test_cog_colour_and_bans():
    assert DraftButtons.getColor("cog") == "green"
    game = FakeGame(True, False)
    game.gamestate["bannedFactions"] = ["cog"]
    labels = [button.label for button in DraftButtons.getDraftButtons(game, 24).children]
    assert "Children of Cog" not in labels


def test_cog_faction_choice_exists():
    choices = [(choice.name, choice.value) for choice in SetupCommands.factionChoices]
    assert ("Children of Cog", "cog") in choices


def test_cog_setup_loads_its_data(start_game):
    game, channel = start_game(factions=["cog", "eri"])
    player = reload(game).get_player(1)
    assert player["name"].startswith("Children of Cog")
    assert player["home_planet"] == "256"
    assert player["nano_tech"] == ["nar"]
    assert player["build_apt"] == 3  # printed 2 plus the starting Nanorobots activation
    assert player["interceptor_parts"] == ["ioc", "nus", "nud", "empty"]
    assert reload(game).gamestate["board"]["201"]["player_ships"] == ["blue-int"]
    assert (player["money_pop_cubes"], player["material_pop_cubes"], player["science_pop_cubes"]) == (12, 11, 11)
