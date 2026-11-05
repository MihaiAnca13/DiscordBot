"""Stage a live sandbox game for a playtest: place a sector, add ships, edit a player.

Run it between presses, never during one: it writes the save outside the server's game lock.

    docker compose -f compose.webui.yaml exec -T webui python -m dev.webui.stage aeb2 tile 102 104 blue
    docker compose -f compose.webui.yaml exec -T webui python -m dev.webui.stage aeb2 units 102 blue-cru red-int red-int
    docker compose -f compose.webui.yaml exec -T webui python -m dev.webui.stage aeb2 player 2 '{"colony_ships": 3}'

Ships of two sides in one sector fight when the round's actions end, through the normal flow.
"""
import json
import sys

import config
from helpers.GamestateHelper import GamestateHelper
from helpers.PlayerHelper import PlayerHelper


def stage(game_id, op, *args):
    assert config.gamestate_path == "/sandbox/games", "Staging is restricted to the Docker sandbox"
    game = GamestateHelper(None, game_id)
    if op == "tile":
        position, sector, *owner = args
        game.add_tile(position, 0, sector, *owner)
    elif op == "units":
        position, *units = args
        for unit in units:
            color, ship = unit.split("-")
            assert f"{PlayerHelper.blueprint_key(ship)}_parts" in game.getPlayerObjectFromColor(color), \
                f"{color} has no {ship} blueprint"
        owner = game.gamestate["board"][position].get("owner")
        for color in dict.fromkeys(unit.split("-")[0] for unit in units):
            game.add_units([unit for unit in units if unit.startswith(color + "-")], position)
            if color != owner:
                game.noteUnitEntry(color, position)
    elif op == "player":
        seat, changes = args
        game.gamestate["players"][seat].update(json.loads(changes))
    else:
        raise SystemExit("op must be tile, units or player")
    game.update()


if __name__ == "__main__":
    stage(*sys.argv[1:])
