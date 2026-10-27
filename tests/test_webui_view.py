"""The read side of the web ui: one seat's choices, independent of history."""
import pytest

from Buttons.Turn import TurnButtons
from webui.server import build
from webui.store import FeedStore
from webui.transport import Surface


@pytest.fixture
def store(tmp_path):
    feed = FeedStore(str(tmp_path / "feed.sqlite3"))
    yield feed
    feed.close()


@pytest.fixture
def app(store, tmp_path):
    return build(store=store, data_dir=str(tmp_path))


def turn_menu(run, store, game, seat, color):
    surface = Surface(store, game.game_id, seat=seat)
    return run(surface.channel.send("your turn", view=TurnButtons.getStartTurnButtons(
        game, game.getPlayerObjectFromColor(color), color)))


def test_pending_choices_do_not_fall_off_the_history_page(start_game, store, app, run):
    game, _channel = start_game()
    menu = turn_menu(run, store, game, "1", "blue")
    for index in range(60):
        store.record("aeb1", "aeb1-actions", content=f"log {index}")

    view = app.snapshot("aeb1", "1")

    assert any(message["id"] == menu.id for message in view["pending"])
    assert menu.id not in [message["id"] for message in view["history"]]
    assert view["history_more"] is True


def test_another_seats_public_prompt_is_not_one_of_your_choices(start_game, store, app, run):
    game, _channel = start_game()
    turn_menu(run, store, game, "1", "blue")

    blue = app.snapshot("aeb1", "1")
    red = app.snapshot("aeb1", "2")

    assert any(button["label"].startswith("Explore") for message in blue["pending"]
               for button in message["buttons"])
    assert not any(button["custom_id"].startswith("FCIDblue") for message in red["pending"]
                   for button in message["buttons"])


def test_history_keeps_used_prompts_and_pages_backwards(start_game, store, app, run):
    game, _channel = start_game()
    menu = turn_menu(run, store, game, "1", "blue")
    store.remove(menu.id)
    for index in range(50):
        store.record("aeb1", "aeb1-actions", content=f"log {index}")

    first = app.snapshot("aeb1", "1")["history"]
    older, has_more = store.history_page("aeb1", "1", before=first[-1]["id"], limit=40)

    assert menu.id not in [message["id"] for message in first]
    assert has_more is False
    assert len(older) >= 10
    assert any(message["id"] == menu.id for message in older)


def test_a_game_over_hides_the_stale_turn_menu(start_game, store, app, run):
    game, _channel = start_game()
    turn_menu(run, store, game, "1", "blue")
    game.gamestate["gameEnded"] = True
    game.update()

    view = app.snapshot("aeb1", "1")

    assert view["pending"] == []
    assert view["game"]["ended"] is True
    assert view["result"][0]["points"] is not None


def test_private_prompts_are_only_in_their_seats_choices(start_game, store, app, run):
    game, _channel = start_game()
    turn_menu(run, store, game, "1", "blue")
    store.record("aeb1", "aeb1-actions", content="blue only", ephemeral_to="1", buttons=[
        {"label": "Pass Unless Someone Attacks You", "custom_id": "permanentlyPass",
         "style": 3, "disabled": False, "url": None}])

    blue = app.snapshot("aeb1", "1")
    red = app.snapshot("aeb1", "2")

    assert any(message["content"] == "blue only" for message in blue["pending"])
    assert not any(message["content"] == "blue only" for message in red["pending"])
    # A standing reaction offer does not replace the reaction turn's actions.
    assert any(button["custom_id"].endswith("_startBuild")
               for message in blue["pending"] for button in message["buttons"])


def test_a_new_phase_hides_the_previous_turn_menu(start_game, store, app, run):
    game, _channel = start_game()
    turn_menu(run, store, game, "1", "blue")
    store.record("aeb1", "aeb1-actions", content="all players have passed", buttons=[
        {"label": "Run Upkeep", "custom_id": "runUpkeep",
         "style": 1, "disabled": False, "url": None}])

    view = app.snapshot("aeb1", "1")

    assert [message["content"] for message in view["pending"]] == ["all players have passed"]


def test_combat_overview_stops_offering_a_rolled_colour(store, app):
    blue = store.record("aeb1", "aeb1-Round 1, Tile 102, Combat", content="Combat",
                        buttons=[
                            {"label": "(Defender) Roll Initative 3 Ships",
                             "custom_id": "FCIDblue_rollDice_102_blue_3_defender",
                             "style": 3, "disabled": False, "url": None},
                            {"label": "(Attacker) Roll Initative 3 Ships",
                             "custom_id": "FCIDred_rollDice_102_red_3_attacker",
                             "style": 4, "disabled": False, "url": None},
                            {"label": "Refresh Image", "custom_id": "refreshImage_102",
                             "style": 1, "disabled": False, "url": None},
                        ])

    app._retire_combat_rolls("aeb1", "aeb1-Round 1, Tile 102, Combat", "blue")

    buttons = store.get(blue)["buttons"]
    assert [button["custom_id"] for button in buttons] == [
        "FCIDred_rollDice_102_red_3_attacker", "refreshImage_102"]


def test_board_metadata_marks_unexplored_slots(start_game, store, app, run):
    _game, _channel = start_game()

    meta = app.snapshot("aeb1", "1")["board_meta"]

    assert meta["width"] > 0 and meta["height"] > 0
    assert any(tile["empty"] for tile in meta["tiles"])
    assert any(tile["position"] == "000" and not tile["empty"] for tile in meta["tiles"])
    by_position = {tile["position"]: tile for tile in meta["tiles"]}
    assert by_position["000"]["label"] == "Galactic Center"


def test_other_research_menu_drops_owned_and_unaffordable_techs(start_game, store, app):
    game, _channel = start_game()
    player = game.get_player(1)
    player["science"] = 2
    player["military_tech"].append("stb")
    game.update()
    menu = store.record("aeb1", "aeb1-actions", content="second tech", buttons=[
        {"label": "Star Base (4)", "custom_id": "FCIDblue_getTech_stb_military",
         "style": 4, "disabled": False, "url": None},
        {"label": "Plasma Cannon (6)", "custom_id": "FCIDblue_getTech_plc_military",
         "style": 4, "disabled": False, "url": None},
        {"label": "Nano Robots (2)", "custom_id": "FCIDblue_getTech_nar_nano",
         "style": 1, "disabled": False, "url": None},
        {"label": "Decline 2nd Tech", "custom_id": "FCIDblue_deleteMsg",
         "style": 4, "disabled": False, "url": None},
    ])

    app._prune_research_options(game, "aeb1-actions", "blue", "aeb1")

    assert [button["custom_id"] for button in store.get(menu)["buttons"]] == [
        "FCIDblue_getTech_nar_nano", "FCIDblue_deleteMsg"]
