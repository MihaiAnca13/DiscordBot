"""Reset only the Docker sandbox, using the same setup as the rule tests."""
import asyncio
from pathlib import Path
import shutil

import config
from Buttons.Turn import TurnButtons
from helpers.GamestateHelper import GamestateHelper
from setup.GameInit import GameInit
from tests.fakes import FakeInteraction
from webui.store import FeedStore
from webui.transport import Surface


async def reset():
    """Wipe both development data directories and build the demo game.

    Returns (game, store). Callers must close the store when finished.
    """
    games = Path(config.gamestate_path)
    assert games == Path("/sandbox/games"), "Reset is restricted to the Docker sandbox"
    feed_dir = Path("/app/webui/data")
    for directory in (games, feed_dir):
        directory.mkdir(parents=True, exist_ok=True)
        for path in directory.iterdir():
            if path.is_dir():
                shutil.rmtree(path)
            else:
                path.unlink()
    # The container has a disposable config; no real token or save folder is available.
    config.game_number = 1
    GameInit("Web UI demo", [[1, "Blue"], [2, "Red"]], "def", True, True, False, False).create_game()
    game = GamestateHelper(None, "aeb1")
    game.setup_techs_and_outer_rim(2, False, False)
    game.add_tile("000", 0, "001")
    for seat, faction, color, position in [(1, "hyd", "blue", "201"), (2, "eri", "red", "203")]:
        game.player_setup(seat, faction, color, FakeInteraction())
        game.add_tile(position, 0, game.get_player(seat)["home_planet"], color)
    game.setup_finished()
    await game.updateNamesAndOutRimTiles(FakeInteraction())
    game.gamestate["roundNum"] = 1
    game.initilizeKey("activePlayerColor")
    game.addToKey("activePlayerColor", "blue")
    store = FeedStore(str(feed_dir / "webui.sqlite3"))
    store.set_mirror("aeb1", False)
    surface = Surface(store, "aeb1", seat="1")
    await surface.channel.send("Blue, choose an action", view=TurnButtons.getStartTurnButtons(
        game, game.get_player(1), "blue"))
    assert GamestateHelper(None, "aeb1").gamestate["activePlayerColor"] == ["blue"]
    assert store.open_messages("aeb1", "1")
    return game, store


async def main():
    _game, store = await reset()
    store.close()
    print("Reset aeb1: blue seat 1, red seat 2")


if __name__ == "__main__":
    asyncio.run(main())
