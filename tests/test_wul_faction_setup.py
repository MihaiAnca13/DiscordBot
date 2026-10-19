from Buttons.Draft import DraftButtons
from commands.setup_commands import SetupCommands
from tests.fakes import FakeGame, buttons, reload


def test_wulfen_only_appears_in_community_draft():
    standard_buttons = DraftButtons.getDraftButtons(FakeGame(False, False))
    community_buttons = DraftButtons.getDraftButtons(FakeGame(True, False))

    assert len(standard_buttons.children) == 16
    assert "The Wulfen" not in [button.label for button in standard_buttons.children]
    assert [button.label for button in community_buttons.children].count("The Wulfen") == 1
    assert len(community_buttons.children) == 24


def test_wulfen_uses_brown_and_respects_bans():
    assert DraftButtons.getColor("wul") == "brown"

    game = FakeGame(True, False)
    game.gamestate["bannedFactions"] = ["wul"]
    assert "The Wulfen" not in [button.label for button in DraftButtons.getDraftButtons(game).children]


def test_wulfen_and_rho_indi_do_not_colour_block_each_other():
    game = FakeGame(True, False)
    game.gamestate["draftedFactions"] = [(1, "rho")]
    labels = [button.label for button in DraftButtons.getDraftButtons(game).children]
    assert "The Wulfen" in labels


def test_wulfen_faction_choice_exists():
    choices = [(choice.name, choice.value) for choice in SetupCommands.factionChoices]
    assert ("The Wulfen", "wul") in choices


def test_setup_loads_the_wulfen_blueprints(start_game, press):
    game, channel = start_game(factions=["wul", "eri"])

    press(channel, 1, "FCIDblue_startUpgrade")
    labels = list(buttons(channel).values())
    assert "Interceptor" not in labels
    state = reload(game)
    player = state.get_player(1)
    assert state.gamestate["board"]["201"]["player_ships"] == ["blue-cru"]
    assert player["dread_parts"] == ["elc", "nus", "nud", "empty", "hul", "hul", "ioc", "ioc"]
    assert player["starbase_parts"] == ["empty", "hul", "hul", "ioc", "ioc"]


def test_general_setup_gives_two_brown_factions_different_colours(games_dir, run, monkeypatch):
    import asyncio
    from helpers.GamestateHelper import GamestateHelper
    from setup.GameInit import GameInit
    from tests.fakes import FakeChannel, FakeInteraction

    async def noop(*args, **kwargs):
        return None

    monkeypatch.setattr(GamestateHelper, "showUpdate", noop)
    GameInit("Two brown factions", [[1, "<@1>"], [2, "<@2>"]], "def", True, True, False, False,
             community_factions=True).create_game()
    game = GamestateHelper(None, "aeb1")
    game.setup_techs_and_outer_rim(2, False, False)
    channel = FakeChannel("aeb1-actions")
    interaction = FakeInteraction(channel, role_names=["aeb1"])

    run(DraftButtons.generalSetup(interaction, game, [1, 2], ["wul", "rho"]))

    state = reload(game).gamestate
    assert state["players"]["1"]["color"] == "brown"
    assert state["players"]["2"]["color"] != "brown"
