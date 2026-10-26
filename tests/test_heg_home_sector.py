import json
from pathlib import Path

from PIL import Image

from helpers.DrawHelper import DrawHelper
from tests.fakes import reload


def hegemony_home():
    with open("data/sectors.json") as f:
        return json.load(f)["276"]


def test_hegemony_home_sector_data():
    sector = hegemony_home()
    assert sector["name"] == "The Cattery"
    assert sector["type"] == "home"
    assert sector["ring"] == 2
    assert sector["vp"] == 3
    assert sector["artifact"] == 1
    assert sector["wormholes"] == [0, 1, 3, 4]
    assert sector["material_pop"] == [1]
    assert sector["science_pop"] == [1]
    assert sector["scienceadv_pop"] == [0]
    assert sector["money_pop"] == [1]
    for key, coords in sector.items():
        if key.endswith("_snap") and coords:
            assert len(coords) == 2, f"{key} {coords} is not a point"
            assert 0 <= coords[0] <= 1024 and 0 <= coords[1] <= 890, f"{key} {coords} is off the tile"


def test_hegemony_home_tile_art():
    path = "images/resources/hexes/276.png"
    assert Path(path).is_file(), path
    with Image.open(path) as tile:
        assert tile.size == (1024, 890)
        assert tile.mode == "RGBA"
        rgba = tile.convert("RGBA")
        assert rgba.getpixel((0, 0))[3] == 0
        for point in ((894, 431), (93, 423), (206, 423), (292, 83)):
            assert rgba.getpixel(point)[3] > 0
        tile.load()


def test_hegemony_home_numberless_art():
    path = "images/resources/hexes/numberless/276.png"
    assert Path(path).is_file(), path
    with Image.open(path) as tile:
        assert tile.size == (1024, 890)
        assert tile.mode == "RGBA"
        tile.load()


def test_hegemony_home_is_set_up_on_the_board(start_game):
    game, _channel = start_game(factions=["heg", "eri"])
    state = reload(game)
    tile = state.gamestate["board"]["201"]
    assert tile["sector"] == "276"
    assert tile["material_pop"] == [1] and tile["science_pop"] == [1]
    assert tile["scienceadv_pop"] == [0] and tile["money_pop"] == [1]
    assert tile["player_ships"] == ["blue-int"]
    player = state.get_player(1)
    assert (player["money_pop_cubes"], player["material_pop_cubes"], player["science_pop_cubes"]) == (11, 11, 11)


def test_hegemony_home_tile_renders(start_game):
    game, _channel = start_game(factions=["heg", "eri"])
    image = DrawHelper(reload(game).gamestate).board_tile_image("201")
    assert image.size[0] > 0 and image.size[1] > 0
