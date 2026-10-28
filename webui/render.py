"""Render a game's board once per state, then serve the cached file.

Rendering is the slow part (seconds), so the URL carries a version taken from the
save file's mtime and size: the browser keeps the image until the state changes.
"""
import json
import os

from PIL import Image

from helpers.DrawHelper import DrawHelper, load_properties
from helpers.GamestateHelper import GamestateHelper


def state_version(games_path, game_id):
    stat = os.stat(os.path.join(games_path, f"{game_id}.json"))
    return f"{stat.st_mtime_ns}-{stat.st_size}"


def _board_bounds(gamestate):
    """Top-left corner of the map crop, and every board position's place in it.

    Empty ring slots are kept: the engine offers them as explore targets, and a
    hotspot needs the same coordinates as the painted tiles. They are marked so
    the browser can draw them as unexplored space.
    """
    configs = load_properties("data/tileImageCoordinates.properties")
    min_x, min_y = float("inf"), float("inf")
    max_x, max_y = float("-inf"), float("-inf")
    tiles = []
    for position, tile in gamestate["board"].items():
        if "nebula_parent" in tile:
            continue
        entry = configs.get(position)
        if not entry:
            continue
        x, y = (int(part) for part in entry[0].split(","))
        tiles.append((position, x, y, "back" in str(tile.get("sector", ""))))
        min_x, min_y = min(min_x, x), min(min_y, y)
        max_x, max_y = max(max_x, x), max(max_y, y)
    if gamestate.get("5playerhyperlane"):
        # show_map leaves the hyperlane image out; show_game pastes it at this fixed spot.
        min_x, min_y = min(min_x, 1820), min(min_y, 2850)
        max_x, max_y = max(max_x, 1820 + 1125), max(max_y, 2850 + 900)
    if not tiles:
        return {"width": 0, "height": 0, "tiles": []}
    return {"width": int(max_x - min_x + 345), "height": int(max_y - min_y + 300),
            "tiles": [{"position": position, "x": x - min_x, "y": y - min_y,
                       "empty": empty}
                      for position, x, y, empty in tiles]}


def board_geometry(game_id):
    game = GamestateHelper(None, game_id)
    return _board_bounds(game.gamestate)


def _map_image(gamestate):
    """The map alone, cut to the tiles that are on the board (show_map, without I/O)."""
    drawing = DrawHelper(gamestate)
    configs = load_properties("data/tileImageCoordinates.properties")
    min_x, min_y = float("inf"), float("inf")
    max_x, max_y = float("-inf"), float("-inf")
    context = Image.new("RGBA", (4160, 5100), (0, 0, 0, 255))
    for position, tile in gamestate["board"].items():
        if position not in configs:
            continue
        x, y = (int(part) for part in configs.get(position)[0].split(","))
        if "nebula_parent" not in tile and "back" not in str(tile.get("sector", "")):
            tile_image = drawing.board_tile_image(position).resize((345, 300))
            context.paste(tile_image, (x, y), mask=tile_image)
            max_x, max_y = max(max_x, x + tile_image.width), max(max_y, y + tile_image.height)
        else:
            max_x, max_y = max(max_x, x + 345), max(max_y, y + 300)
        min_x, min_y = min(min_x, x), min(min_y, y)
    if min_x == float("inf"):
        return context
    if gamestate.get("5playerhyperlane"):
        hyper = drawing.use_resized_image("images/resources/hexes/5playerhyperlane.png", (1125, 900))
        context.paste(hyper, (1820, 2850), mask=hyper)
        min_x, min_y = min(min_x, 1820), min(min_y, 2850)
        max_x, max_y = max(max_x, 1820 + hyper.width), max(max_y, 2850 + hyper.height)
    return context.crop((int(min_x), int(min_y), int(max_x), int(max_y)))


def _tile_properties(sector):
    with open(os.path.join("data", "sectors.json")) as data:
        return json.load(data).get(sector)


def render_tile_preview(sector, rotation, cache_dir):
    """The engine's tile art at one offered rotation, for the on-board preview."""
    rotation = int(rotation) % 360
    properties = _tile_properties(sector)
    if properties is None:
        return None
    folder = os.path.join(cache_dir, "tiles")
    os.makedirs(folder, exist_ok=True)
    target = os.path.join(folder, f"{sector}-{rotation}.webp")
    if os.path.exists(target):
        return target
    image = DrawHelper({}).base_tile_image_with_rotation(
        sector, rotation, properties.get("wormholes", []))
    if properties.get("type") == "nebula":
        image = image.rotate(rotation)
    tile = image.resize((345, 300))
    temporary = f"{target}.tmp"
    tile.save(temporary, format="WEBP", quality=92, method=1)
    os.replace(temporary, target)
    return target


def render_board(games_path, game_id, cache_dir, keep=3):
    """Return (path, key). Blocking: call it in a thread."""
    key = state_version(games_path, game_id)
    folder = os.path.join(cache_dir, game_id)
    os.makedirs(folder, exist_ok=True)
    target = os.path.join(folder, f"{key}.map.webp")
    if os.path.exists(target):
        return target, key
    rendered = _map_image(GamestateHelper(None, game_id).gamestate)
    temporary = f"{target}.tmp"
    rendered.save(temporary, format="WEBP", quality=88, method=1)
    os.replace(temporary, target)
    cached = sorted(os.path.join(folder, name) for name in os.listdir(folder))
    for stale in cached[:-keep]:
        os.unlink(stale)
    return target, key


def board_meta(games_path, game_id):
    """JSON-friendly geometry: image size plus each tile's top-left offset."""
    geometry = board_geometry(game_id)
    with open(os.path.join(games_path, f"{game_id}.json")) as save:
        gamestate = json.load(save)
    labels = {}
    for position, tile in gamestate["board"].items():
        label = tile.get("name") or tile.get("sector") or position
        if "back" in str(tile.get("sector", "")):
            label = "Unexplored"
        labels[position] = label
    for tile in geometry["tiles"]:
        tile["label"] = labels.get(tile["position"], tile["position"])
        tile["owner"] = gamestate["board"][tile["position"]].get("owner")
        tile["orientation"] = gamestate["board"][tile["position"]].get("orientation", 0)
    return geometry
