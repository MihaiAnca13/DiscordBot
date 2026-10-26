"""Integration tests: press real buttons through ButtonListener.resolveButton."""
from tests.fakes import buttons, reload

P1, P2 = 1, 2


def test_pass_then_next_player_gets_turn(start_game, press):
    game, channel = start_game()
    blue_money = game.get_player(P1)["money"]
    red_money = game.get_player(P2)["money"]
    press(channel, P1, "FCIDblue_passForRound")
    state = reload(game).gamestate
    assert state["players"][str(P1)]["passed"]
    assert state["players"][str(P1)]["money"] == blue_money + 2
    assert state["activePlayerColor"] == ["red"]
    assert any(l and "Build" in l for l in buttons(channel).values())
    # a second press in the same process must not be blocked by the first one's lock
    press(channel, P2, "FCIDred_passForRound")
    red = reload(game).get_player(P2)
    assert red["passed"]
    assert red["money"] == red_money
