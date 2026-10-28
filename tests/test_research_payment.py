import pytest

from Buttons.Research import ResearchButtons
from Buttons.Turn import TurnButtons
from helpers.PlayerHelper import PlayerHelper
from tests.fakes import FakeInteraction
from webui import catalog


@pytest.mark.parametrize("action", ["finishAction", "endTurn", "passForRound"])
def test_unpaid_research_blocks_turn_completion(start_game, run, action):
    game, channel = start_game()
    player = game.get_player(1)
    player["research_payment_due"] = 2
    helper = PlayerHelper("1", player)
    game.update_player(helper)
    interaction = FakeInteraction(channel=channel)
    arguments = [player, game, interaction]
    if action != "endTurn":
        arguments.append(helper)

    run(getattr(TurnButtons, action)(*arguments))
    run(getattr(TurnButtons, action)(*arguments))

    assert game.gamestate["activePlayerColor"] == ["blue"]
    assert player["research_payment_due"] == 2
    assert any("remaining 2 science" in (content or "")
               for content, options in interaction.followup.sent)


@pytest.mark.parametrize("resource", ["money", "materials"])
def test_research_trade_pays_down_balance(start_game, run, resource):
    game, channel = start_game()
    player = game.get_player(1)
    player.update(research_payment_due=2, money=10, materials=10)
    helper = PlayerHelper("1", player)
    interaction = FakeInteraction(channel=channel)
    before = player[resource]

    run(ResearchButtons.payAtRatio(game, player, helper, interaction, f"payAtRatio_{resource}"))

    assert player["research_payment_due"] == 1
    assert player[resource] == before - player["trade_value"]
    run(ResearchButtons.payAtRatio(game, player, helper, interaction, f"payAtRatio_{resource}"))
    assert player["research_payment_due"] == 0


def test_research_records_unpaid_cost(start_game, run):
    game, channel = start_game()
    player = game.get_player(1)
    player.update(science=1, money=30, materials=30)
    game.gamestate["available_techs"] = ["rican"]
    helper = PlayerHelper("1", player)
    cost = ResearchButtons.calculate_cost(catalog.TECHS["rican"], "grid", player)
    interaction = FakeInteraction(channel=channel)

    run(ResearchButtons.handle_specific_tech_selection(
        interaction, game, player, helper, catalog.TECHS["rican"], "grid", "rican"))

    assert player["science"] == 0
    assert player["research_payment_due"] == cost - 1
    assert "rican" in player["grid_tech"]
    assert run(ResearchButtons.has_unpaid_research(player, interaction))
