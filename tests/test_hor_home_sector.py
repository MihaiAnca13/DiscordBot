import json
from pathlib import Path

from PIL import Image

from helpers.DrawHelper import DrawHelper
from tests.fakes import reload


def horde_home():
    with open("data/sectors.json") as f:
        return json.load(f)["288"]


def test_horde_home_sector_data():
    sector = horde_home()
    assert sector["name"] == "Kassus Gar Rift"
    assert sector["type"] == "home"
    assert sector["ring"] == 2
    assert sector["vp"] == 3
    assert sector["artifact"] == 1
    assert sector["wormholes"] == [0, 1, 3, 4]
    assert sector["money_pop"] == [1] and sector["moneyadv_pop"] == [0]
    assert sector["material_pop"] == [1] and sector["materialadv_pop"] == [0]
    assert sector["science_pop"] == []
    for key, coords in sector.items():
        if key.endswith("_snap") and coords:
            assert len(coords) == 2, f"{key} {coords} is not a point"
            assert 0 <= coords[0] <= 1024 and 0 <= coords[1] <= 890, f"{key} {coords} is off the tile"


def test_horde_home_tile_art():
    path = "images/resources/hexes/288.png"
    assert Path(path).is_file(), path
    with Image.open(path) as tile:
        assert tile.size == (1024, 890)
        assert tile.mode == "RGBA"
        rgba = tile.convert("RGBA")
        assert rgba.getpixel((0, 0))[3] == 0
        for point in ((604, 169), (741, 171), (329, 449), (333, 609)):
            assert rgba.getpixel(point)[3] > 0
        tile.load()


def test_horde_home_is_set_up_on_the_board(start_game):
    game, _channel = start_game(factions=["hor", "eri"])
    state = reload(game)
    tile = state.gamestate["board"]["201"]
    assert tile["sector"] == "288"
    assert tile["money_pop"] == [1] and tile["material_pop"] == [1]
    assert tile["player_ships"] == ["blue-int"]
    player = state.get_player(1)
    assert (player["money_pop_cubes"], player["material_pop_cubes"], player["science_pop_cubes"]) == (11, 11, 12)


def test_horde_home_tile_renders(start_game):
    game, _channel = start_game(factions=["hor", "eri"])
    image = DrawHelper(reload(game).gamestate).board_tile_image("201")
    assert image.size[0] > 0 and image.size[1] > 0
