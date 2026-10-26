from Buttons.Draft import DraftButtons
from commands.setup_commands import SetupCommands
from tests.fakes import FakeGame, reload


def test_midas_only_appears_in_the_community_draft():
    assert len(DraftButtons.getDraftButtons(FakeGame(False, False)).children) == 16
    more = DraftButtons.getDraftButtons(FakeGame(True, False), 24)
    assert [button.label for button in more.children] == ["Children of Cog", "Legion of Midas",
                                                          "The Horde", "Vorlons",
                                                          "Hegemony of the Highest Cushion"]


def test_midas_colour_and_bans():
    assert DraftButtons.getColor("mid") == "yellow"
    game = FakeGame(True, False)
    game.gamestate["bannedFactions"] = ["mid"]
    labels = [button.label for button in DraftButtons.getDraftButtons(game, 24).children]
    assert "Legion of Midas" not in labels


def test_midas_faction_choice_exists():
    choices = [(choice.name, choice.value) for choice in SetupCommands.factionChoices]
    assert ("Legion of Midas", "mid") in choices


def test_midas_setup_loads_its_data_and_money_is_power(start_game):
    game, _channel = start_game(factions=["mid", "eri"])
    state = reload(game)
    player = state.get_player(1)
    assert player["name"].startswith("Legion of Midas")
    assert player["home_planet"] == "277"
    assert player["grid_tech"] == ["ade"]
    tile = state.gamestate["board"]["201"]
    assert tile["moneyadv_pop"] == [1]
    assert (player["money_pop_cubes"], player["material_pop_cubes"], player["science_pop_cubes"]) == (11, 12, 12)
