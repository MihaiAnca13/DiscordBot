"""The read side of the web ui: one seat's choices, independent of history."""
import json
from types import SimpleNamespace

import pytest

from Buttons.Turn import TurnButtons
from webui.render import rotate_tile_point
from webui.server import build
from webui.store import FeedStore
from webui.transport import Surface, WebInteraction


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


def test_used_restart_menu_still_retires_abandoned_research(start_game, store, app, run):
    game, channel = start_game()
    old_choices = []
    for custom_id in ("FCIDblue_getTech_stb_military", "FCIDblue_payAtRatio_money"):
        old_choices.append(store.record(game.game_id, channel.name, buttons=[
            {"label": "Old choice", "custom_id": custom_id, "style": 1,
             "disabled": False, "url": None}]))
    menu = turn_menu(run, store, game, "1", "blue")
    store.remove(menu.id)
    current = store.record(game.game_id, channel.name, buttons=[
        {"label": "Choose tech", "custom_id": "FCIDblue_getTech_nar_nano",
         "style": 1, "disabled": False, "url": None}])

    pending_ids = [message["id"] for message in app.snapshot(game.game_id, "1")["pending"]]

    assert current in pending_ids
    assert not set(old_choices).intersection(pending_ids)


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


def test_a_bankruptcy_prompt_keeps_the_run_upkeep_button(start_game, store, app, run):
    game, _channel = start_game()
    turn_menu(run, store, game, "1", "blue")
    store.record("aeb1", "aeb1-actions", content="all players have passed", buttons=[
        {"label": "Run Upkeep", "custom_id": "runUpkeep",
         "style": 1, "disabled": False, "url": None}])
    store.record("aeb1", "aeb1-actions",
                 content="It appears that Blue would be bankrupt (negative money).", buttons=[
                     {"label": "Done Resolving", "custom_id": "FCIDblue_deleteMsg",
                      "style": 4, "disabled": False, "url": None}])

    view = app.snapshot("aeb1", "1")

    labels = [button["label"] for message in view["pending"] for button in message["buttons"]]
    assert "Run Upkeep" in labels, labels
    assert any("bankrupt" in (message["content"] or "").lower()
               for message in view["pending"])


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


def test_board_pieces_sit_on_the_drawn_ship_and_planet_snaps(start_game, store, app):
    game, _channel = start_game()

    pieces = app.snapshot("aeb1", "1")["pieces"]
    tile = game.gamestate["board"]["201"]

    ship = next(piece for piece in pieces
                if piece["kind"] == "ship" and piece["position"] == "201")
    assert ship["name"] == "blue-int" and ship["class"] == "int"
    assert abs(ship["x"] - tile["int_snap"][0] * 345 / 1024) < 0.2
    assert abs(ship["y"] - tile["int_snap"][1] * 300 / 890) < 0.2

    planet = next(piece for piece in pieces
                  if piece["kind"] == "planet" and piece["position"] == "201"
                  and piece["square"] == "money")
    assert planet["pop"] == tile["money_pop"][0]
    assert abs(planet["x"] - tile["money1_snap"][0] * 345 / 1024) < 0.2


def boxes_overlap(left, right):
    return not (left["x"] + left["width"] <= right["x"]
                or right["x"] + right["width"] <= left["x"]
                or left["y"] + left["height"] <= right["y"]
                or right["y"] + right["height"] <= left["y"])


def test_nebula_subsector_targets_sit_on_distinct_wedges(start_game, store, app):
    game, _channel = start_game()
    game.add_tile("207", 120, "295")
    game.update()

    meta = app.snapshot("aeb1", "1")["board_meta"]
    by_position = {tile["position"]: tile for tile in meta["tiles"]}
    subsectors = {tile["position"]: tile for tile in meta["subsectors"]}

    assert by_position["207"]["label"] == "207-A"
    assert subsectors["207b"]["label"] == "207-B"
    assert subsectors["207c"]["label"] == "207-C"
    targets = [by_position["207"], subsectors["207b"], subsectors["207c"]]
    for tile in targets:
        assert tile["hit"]["x"] >= tile["x"], tile["hit"]
        assert tile["hit"]["y"] >= tile["y"], tile["hit"]
        assert tile["hit"]["x"] + tile["hit"]["width"] <= tile["x"] + 345, tile["hit"]
        assert tile["hit"]["y"] + tile["hit"]["height"] <= tile["y"] + 300, tile["hit"]
    for index, left in enumerate(targets):
        for right in targets[index + 1:]:
            assert not boxes_overlap(left["hit"], right["hit"]), (left["hit"], right["hit"])


def test_nebula_pieces_follow_the_rotated_art(start_game, store, app):
    game, _channel = start_game()
    game.add_tile("207", 120, "295")
    board = game.gamestate["board"]
    board["207b"]["player_ships"] = ["blue-int"]
    game.update()

    pieces = app.snapshot("aeb1", "1")["pieces"]
    piece = next(piece for piece in pieces
                 if piece["kind"] == "ship" and piece["position"] == "207b")
    expected = rotate_tile_point(*board["207b"]["int_snap"], 120)
    assert abs(piece["x"] - expected[0] * 345 / 1024) < 0.2
    assert abs(piece["y"] - expected[1] * 300 / 890) < 0.2


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


def test_wild_track_preview_preserves_research_menu(start_game, store, app, run):
    game, channel = start_game()
    player = game.get_player(1)
    player["science"] = 20
    game.gamestate["available_techs"] = ["rican", "nar"]
    game.update()
    menu = store.record(game.game_id, channel.name, buttons=[
        {"label": label, "custom_id": custom_id, "style": 1,
         "disabled": False, "url": None}
        for label, custom_id in [("Rift Cannon (9)", "FCIDblue_getTech_rican_any"),
                                 ("Nano Robots (2)", "FCIDblue_getTech_nar_nano")]])
    original_menu = store.get(menu)
    original_state = json.dumps(game.gamestate, sort_keys=True)
    original_rev = store.rev(game.game_id)
    selected_id = "FCIDblue_getTech_rican_any"

    async def body():
        return {"seat": "1", "message_id": menu, "custom_id": selected_id}

    request = SimpleNamespace(match_info={"game_id": game.game_id}, json=body)
    preview = json.loads(run(app.api_press(request)).text)

    assert preview["error"] is None
    assert {button["custom_id"] for button in preview["tech_tracks"]} == {
        f"FCIDblue_getTech_rican_{track}" for track in ("military", "grid", "nano")}
    assert store.get(menu) == original_menu
    assert store.rev(game.game_id) == original_rev
    assert json.dumps(app.game(game.game_id).gamestate, sort_keys=True) == original_state

    selected_id = "FCIDblue_getTech_rican_grid"
    purchased = json.loads(run(app.api_press(request)).text)

    assert purchased["error"] is None
    assert "rican" in app.game(game.game_id).get_player(1)["grid_tech"]
    assert store.get(menu)["deleted"]


def test_combat_chat_keeps_resolved_allied_events_beyond_recent_history(start_game, store, app, run):
    game, channel = start_game(player_count=3)
    game.add_tile("101", 0, "307")
    game.gamestate["board"]["101"].update(defender=["blue", "red"], attacker=["green"])
    game.update()
    room = "aeb1-Round 1, Tile 101, Combat"
    ids = []
    for seat, color in [("1", "blue"), ("2", "red"), ("3", "green")]:
        interaction = WebInteraction(store, "aeb1", seat, channel_name=room,
                                     custom_id=f"FCID{color}_rollDice_101_{color}_3_deleteMsg")
        message = run(interaction.channel.send(f"{color} rolled dice"))
        ids.append(message.id)
        run(message.delete())
    for number in range(60):
        store.record("aeb1", channel.name, content=f"Unrelated message {number}")
    store.record("aeb1", room, content="Private opponent message", ephemeral_to="3")

    view = app.snapshot("aeb1", "1")
    battle = view["battles"][0]

    assert [message["id"] for message in battle["messages"]] == ids
    assert [message["combat"]["side"] for message in battle["messages"]] == [
        "defender", "defender", "attacker"]
    assert all(message["deleted"] for message in battle["messages"])
    assert not set(ids).intersection(message["id"] for message in view["history"])
