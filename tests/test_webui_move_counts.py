import json
from types import SimpleNamespace

import pytest

from Buttons.Move import MoveButtons
from webui.server import build
from webui.store import FeedStore
from webui.transport import Surface


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
