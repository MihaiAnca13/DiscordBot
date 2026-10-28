"""Render a game's board once per state, then serve the cached file.

Rendering is the slow part (seconds), so the URL carries a version taken from the
save file's mtime and size: the browser keeps the image until the state changes.
"""
import json
import math
import os

from PIL import Image

from helpers.DrawHelper import DrawHelper, load_properties
from helpers.GamestateHelper import GamestateHelper


def state_version(games_path, game_id):
    stat = os.stat(os.path.join(games_path, f"{game_id}.json"))
    return f"{stat.st_mtime_ns}-{stat.st_size}"


TILE_W, TILE_H = 345, 300
SOURCE_W, SOURCE_H = 1024, 890
NEBULA_LABELS = {"": (865, 445), "b": (335, 139), "c": (335, 751)}
NEBULA_HIT = 90


def rotate_tile_point(x, y, orientation):
    """Where the engine paints a 1024-pixel tile point after rotating the art."""
    angle = math.radians(orientation)
    dx, dy = x - SOURCE_W / 2, y - SOURCE_H / 2
    return (SOURCE_W / 2 + dx * math.cos(angle) + dy * math.sin(angle),
            SOURCE_H / 2 - dx * math.sin(angle) + dy * math.cos(angle))


def nebula_anchor(parent, orientation, suffix):
    """The painted label anchor of one Nebula subsector, in board pixels."""
    x, y = rotate_tile_point(*NEBULA_LABELS[suffix], orientation)
    return round(x * TILE_W / SOURCE_W, 1), round(y * TILE_H / SOURCE_H, 1)


def _nebula_hit(point, left=0, top=0):
    x, y = point
    return {"x": round(left + x - NEBULA_HIT / 2, 1),
            "y": round(top + y - NEBULA_HIT / 2, 1),
            "width": NEBULA_HIT, "height": NEBULA_HIT}


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
    cached = sorted(os.path.join(folder, name) for name in os.listdir(folder)
                    if name.endswith(".map.webp"))
    for stale in cached[:-keep]:
        os.unlink(stale)
    return target, key


def board_meta(games_path, game_id):
    """JSON-friendly geometry: image size plus each clickable tile or subsector.

    Nebula sectors paint three subsectors inside one hex, so their targets sit on
    the wedge labels the engine draws. Separate wedges never overlap: a shared
    whole-tile hotspot would let the wrong subsector take the click.
    """
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
        state = gamestate["board"][tile["position"]]
        tile["label"] = labels.get(tile["position"], tile["position"])
        tile["owner"] = state.get("owner")
        tile["orientation"] = state.get("orientation", 0)
        if state.get("type") == "nebula":
            tile["label"] = f"{tile['position']}-A"
            tile["hit"] = _nebula_hit(nebula_anchor(tile["position"], tile["orientation"], ""),
                                      tile["x"], tile["y"])
        else:
            tile["hit"] = {"x": tile["x"] + 36, "y": tile["y"] + 28,
                           "width": 273, "height": 244}
    subsectors = []
    for position, state in gamestate["board"].items():
        parent = state.get("nebula_parent")
        if parent is None:
            continue
        parent_tile = next(tile for tile in geometry["tiles"] if tile["position"] == parent)
        suffix = position[len(parent):]
        subsectors.append({
            "position": position, "parent": parent,
            "label": f"{parent}-{suffix.upper()}",
            "x": parent_tile["x"], "y": parent_tile["y"],
            "owner": state.get("owner"),
            "orientation": state.get("orientation", 0),
            "hit": _nebula_hit(nebula_anchor(parent, parent_tile["orientation"], suffix),
                               parent_tile["x"], parent_tile["y"]),
        })
    geometry["subsectors"] = subsectors
    return geometry


def render_panel(games_path, game_id, panel, seat, cache_dir):
    """Use the same market and player-board images as the Discord bot."""
    key = state_version(games_path, game_id)
    folder = os.path.join(cache_dir, game_id, "panels")
    os.makedirs(folder, exist_ok=True)
    is_blueprint = panel.startswith("blueprint-")
    name = f"{panel}-{seat}" if panel == "player" or is_blueprint else panel
    if panel == "turn-order":
        name = "turn-order-compact"
    target = os.path.join(folder, f"{key}.{name}.webp")
    layout_path = f"{target}.json"
    if not os.path.exists(target) or ((panel == "market" or is_blueprint) and not os.path.exists(layout_path)):
        game = GamestateHelper(None, game_id)
        drawing = DrawHelper(game.gamestate)
        if panel == "market":
            regions = []
            image = drawing.display_techs("Available Techs", game.gamestate["available_techs"], regions)
            with open(layout_path, "w") as handle:
                json.dump({"width": image.width, "height": image.height, "regions": regions}, handle)
        elif panel == "turn-order":
            order = drawing.display_turn_order()
            count = max(1, len(game.gamestate["players"]))
            height = 270 if game.gamestate.get("pass_order") else 175
            image = order.crop((0, 85, max(95 * count, 130 + 65 * len(game.gamestate.get("pass_order", []))), height))
        elif panel in ("ai", "species", "parts"):
            reference = drawing.display_remaining_tiles()
            bounds = {"ai": (0, 270, 630, 560), "species": (640, 0, 1300, 200),
                      "parts": (1300, 0, 1900, 450)}
            image = reference.crop(bounds[panel])
        else:
            player = game.gamestate["players"].get(seat)
            if player is None or not player.get("color"):
                return None
            regions = [] if is_blueprint else None
            image = drawing.player_area(player, regions)
            if is_blueprint:
                ship = panel.removeprefix("blueprint-")
                regions = [region for region in regions if region["ship"] == ship]
                if not regions:
                    return None
                left = min(region["x"] for region in regions) - 8
                top = min(region["y"] for region in regions) - 8
                right = max(region["x"] + region["width"] for region in regions) + 8
                bottom = max(region["y"] + region["height"] for region in regions) + 8
                image = image.crop((left, top, right, bottom))
                slots = [{**region, "x": region["x"] - left, "y": region["y"] - top}
                         for region in regions if region["kind"] == "slot"]
                with open(layout_path, "w") as handle:
                    json.dump({"width": image.width, "height": image.height, "regions": slots}, handle)
        temporary = f"{target}.tmp"
        image.save(temporary, format="WEBP", quality=92, method=1)
        os.replace(temporary, target)
        cached = sorted(os.path.join(folder, entry) for entry in os.listdir(folder)
                        if entry.endswith(f".{name}.webp"))
        for stale in cached[:-3]:
            os.unlink(stale)
            if os.path.exists(f"{stale}.json"):
                os.unlink(f"{stale}.json")
    return target
