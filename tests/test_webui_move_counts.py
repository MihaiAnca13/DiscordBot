import json
from types import SimpleNamespace

import pytest

from Buttons.Move import MoveButtons
from Buttons.Turn import TurnButtons
from webui.server import build
from webui.store import FeedStore
from webui.transport import Surface


@pytest.mark.parametrize("queued", [False, True])
def test_two_cruisers_exhaust_move_action(start_game, tmp_path, run, queued):
    game, channel = start_game()
    player = game.get_player(1)
    player["move_apt"] = 2
    game.gamestate["board"]["201"]["player_ships"] = ["blue-cru"] * 3
    game.gamestate["board"]["201"]["wormholes"] = list(range(6))
    game.gamestate["board"]["000"]["wormholes"] = list(range(6))
    game.gamestate["board"]["201"]["adjacent"] = ["000"]
    game.gamestate["board"]["000"]["adjacent"] = ["201"]
    game.update()
    store = FeedStore(str(tmp_path / "feed.sqlite3"))
    try:
        app = build(store=store, data_dir=str(tmp_path))
        surface = Surface(store, game.game_id, seat="1")
        run(surface.channel.send("Your turn", view=TurnButtons.getStartTurnButtons(
            game, player, "blue")))

        def click(custom_id):
            pending = app.snapshot(game.game_id, "1")["pending"]
            message = next(message for message in pending if any(
                button["custom_id"] == custom_id for button in message["buttons"]))

            async def body():
                return {"seat": "1", "message_id": message["id"], "custom_id": custom_id}

            request = SimpleNamespace(match_info={"game_id": game.game_id}, json=body)
            response = json.loads(run(app.api_press(request)).text)
            assert response["error"] is None
            if custom_id in ("FCIDblue_moveFrom_201_2", "FCIDblue_moveThisShip_201_cruiser_2_all"):
                assert any(button["custom_id"] == "FCIDblue_finishAction"
                           for message in response["pending"] for button in message["buttons"])
            return response

        click("FCIDblue_startMove")
        click("FCIDblue_moveFrom_201_1")
        click("FCIDblue_moveThisShip_201_cruiser_1_all")
        if queued:
            click("FCIDblue_moveQueueAdd_201_cruiser_1_1_all")
        click(f"FCIDblue_moveQueueDone_201_cruiser_1_{2 if queued else 1}_all")
        click(f"FCIDblue_moveTo_201_cruiser_000_1_q{1 if queued else 0}_all")
        if queued:
            response = click("FCIDblue_moveQueueContinue_201_cruiser_000_2_1_all")
        else:
            click("FCIDblue_moveFrom_201_2")
            click("FCIDblue_moveThisShip_201_cruiser_2_all")
            response = click("FCIDblue_moveTo_201_cruiser_000_2_q0_all")
        ids = [button["custom_id"] for message in response["pending"] for button in message["buttons"]]
        assert "FCIDblue_finishAction" in ids
        assert not any("move" in custom_id.lower() for custom_id in ids)
        assert app.game(game.game_id).gamestate["board"]["000"]["player_ships"].count("blue-cru") == 2
    finally:
        store.close()


@pytest.mark.parametrize("selected", [1, 2, 9])
def test_move_counts_use_bot_limits(start_game, tmp_path, run, selected):
    game, channel = start_game()
    game.add_tile("301", 0, "202")
    player = game.get_player(1)
    player["move_apt"] = 3
    game.gamestate["board"]["201"]["player_ships"] = ["blue-int", "blue-int"]
    game.update()
    store = FeedStore(str(tmp_path / "feed.sqlite3"))
    try:
        app = build(store=store, data_dir=str(tmp_path))
        surface = Surface(store, game.game_id, seat="1")
        menu = run(surface.channel.send("Choose ships", view=MoveButtons.buildMoveQueueView(
            player, "201", "interceptor", "1", 1, 2, "_all")))
        pending = app.snapshot(game.game_id, "1")["pending"]
        choices = next(button["counts"] for message in pending for button in message["buttons"]
                       if "counts" in button)
        assert [button["label"] for button in choices] == ["Done (1)", "Done (2)"]

        async def body():
            return {"seat": "1", "message_id": menu.id,
                    "custom_id": f"FCIDblue_moveQueueDone_201_interceptor_1_{selected}_all"}

        request = SimpleNamespace(match_info={"game_id": game.game_id}, json=body)
        response = json.loads(run(app.api_press(request)).text)

        if selected == 9:
            assert response["error"] == "That choice is no longer active."
        else:
            assert response["error"] is None
            assert any(f"_q{selected - 1}_all" in button["custom_id"]
                       for message in response["pending"] for button in message["buttons"])
        assert app.game(game.game_id).gamestate["board"]["201"]["player_ships"] == ["blue-int", "blue-int"]
    finally:
        store.close()
