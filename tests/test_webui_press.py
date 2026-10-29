"""A press that arrives over HTTP is the same press Discord sends.

These cases exercise `ButtonListener.resolveButton` through `WebInteraction`, so
they cover the seam: gamestate changes, prompts land in the feed, and private
prompts stay private.
"""
import pytest

from Buttons.Turn import TurnButtons
from Buttons.DiscoveryTile import DiscoveryTileButtons
from helpers.GamestateHelper import GamestateHelper
from listeners.ButtonListener import ButtonListener
from webui.store import FeedStore
from webui.transport import Surface, WebInteraction


@pytest.fixture
def store(tmp_path):
    feed = FeedStore(str(tmp_path / "feed.sqlite3"))
    yield feed
    feed.close()


def members(game):
    players = game.gamestate["players"]
    return {"names": {pid: stats.get("color") for pid, stats in players.items()},
            "colors": [stats.get("color") for stats in players.values()]}


def press(run, store, game, seat, custom_id, message_id):
    interaction = WebInteraction(store, game.game_id, seat, custom_id=custom_id,
                                 message_id=message_id, members=members(game))
    run(ButtonListener(None).resolveButton(interaction))


def turn_menu(run, store, game, seat, color):
    surface = Surface(store, game.game_id, seat=seat)
    return run(surface.channel.send("your turn", view=TurnButtons.getStartTurnButtons(
        game, game.getPlayerObjectFromColor(color), color)))


def test_pressing_a_web_prompt_changes_the_game(start_game, store, run):
    game, _channel = start_game()
    menu = turn_menu(run, store, game, "1", "blue")

    press(run, store, game, "1", "FCIDblue_passForRound", menu.id)

    state = GamestateHelper(None, "aeb1").gamestate
    assert state["players"]["1"]["passed"]
    assert state["activePlayerColor"] == ["red"]

    # the new turn's prompt is in the feed for the next player
    prompts = store.open_messages("aeb1", "2")
    assert any(b["label"] and "Build" in b["label"] for m in prompts for b in m["buttons"])
    assert store.get(menu.id)["deleted"]


def test_a_private_prompt_is_only_offered_to_its_seat(start_game, store, run):
    game, _channel = start_game()
    menu = turn_menu(run, store, game, "1", "blue")
    press(run, store, game, "1", "FCIDblue_passForRound", menu.id)

    blue = [m for m in store.open_messages("aeb1", "1") if m["ephemeral_to"] == "1"]
    red = [m for m in store.open_messages("aeb1", "2") if m["ephemeral_to"] == "2"]
    assert any("Pass Unless Someone Attacks You" in [b["label"] for b in m["buttons"]] for m in blue)
    assert not any(m["ephemeral_to"] == "1" for m in red)


def test_a_used_prompt_cannot_be_pressed_twice(start_game, store, run):
    game, _channel = start_game()
    menu = turn_menu(run, store, game, "1", "blue")
    press(run, store, game, "1", "FCIDblue_passForRound", menu.id)

    # a different button on the same, already used prompt: the feed says it is gone
    press(run, store, game, "1", "FCIDblue_startBuild", menu.id)
    notices = [m["content"] for m in store.visible_history("aeb1", "1")]
    assert any("already used" in (text or "") for text in notices)
    state = GamestateHelper(None, "aeb1").gamestate
    assert state["players"]["1"]["build_apt"] == game.gamestate["players"]["1"]["build_apt"]


def test_another_seats_buttons_are_refused(start_game, store, run):
    game, _channel = start_game()
    menu = turn_menu(run, store, game, "1", "blue")

    press(run, store, game, "2", "FCIDblue_passForRound", menu.id)

    state = GamestateHelper(None, "aeb1").gamestate
    assert not state["players"]["1"]["passed"]
    notices = [m["content"] for m in store.visible_history("aeb1", "2")]
    assert any("not for you" in (text or "") for text in notices)


def test_discovery_points_remove_choices_and_cannot_be_claimed_again(start_game, store, run):
    game, channel = start_game()
    interaction = WebInteraction(store, game.game_id, "1", members=members(game))
    run(DiscoveryTileButtons.sendDiscoveryTileOptions(
        game, "201", interaction, game.get_player(1), "orb"))
    message = next(m for m in store.open_messages("aeb1", "1") if m["buttons"])
    press(run, store, game, "1", "FCIDblue_keepDiscForPoints", message["id"])
    assert store.get(message["id"])["buttons"] == []

    # Another action bypasses the short double-click guard, but not prompt consumption.
    menu = turn_menu(run, store, game, "1", "blue")
    press(run, store, game, "1", "FCIDblue_showReputation", menu.id)
    press(run, store, game, "1", "FCIDblue_keepDiscForPoints", message["id"])
    assert GamestateHelper(None, "aeb1").get_player(1)["disc_tiles_for_points"] == 1


@pytest.mark.parametrize("action", ["startBuild", "startExplore", "startResearch", "startUpgrade", "startMove", "startInfluence", "passForRound"])
def test_turn_actions_refuse_inactive_player(start_game, store, run, action):
    game, channel = start_game()
    game.gamestate["activePlayerColor"] = ["red"]
    game.update()
    before = GamestateHelper(None, game.game_id).gamestate
    menu = turn_menu(run, store, game, "1", "blue")
    press(run, store, game, "1", f"FCIDblue_{action}", menu.id)
    assert GamestateHelper(None, game.game_id).gamestate == before
    notices = store.visible_history(game.game_id, "1")
    assert any("not your turn" in (message["content"] or "") for message in notices)
