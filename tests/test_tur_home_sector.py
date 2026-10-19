import json
from pathlib import Path

from PIL import Image

from helpers.DrawHelper import DrawHelper


def tur_home_sector():
    with open("data/sectors.json", "r") as f:
        return json.load(f)["253"]


def test_turtugan_home_sector_data():
    sector = tur_home_sector()
    assert sector["name"] == "Turtuga"
    assert sector["type"] == "home"
    assert sector["ring"] == 2
    assert sector["vp"] == 3
    assert sector["artifact"] == 1
    assert sector["wormholes"] == [0, 1, 3, 4]
    assert sector["money_pop"] == [1]
    assert sector["material_pop"] == [1]
    assert sector["materialadv_pop"] == [0]
    assert sector["science_pop"] == []
    assert sector["scienceadv_pop"] == [0]
    assert sector["neutral_pop"] == []
    for key, coords in sector.items():
        if key.endswith("_snap") and coords:
            assert len(coords) == 2, f"{key} {coords} is not a point"
            assert 0 <= coords[0] <= 1024 and 0 <= coords[1] <= 890, f"{key} {coords} is off the tile"


def test_turtugan_home_tiles_exist_and_are_masked():
    for path in ("images/resources/hexes/253.png",
                 "images/resources/hexes/numberless/253.png"):
        assert Path(path).is_file(), path
        with Image.open(path) as tile:
            assert tile.size == (1024, 890)
            assert tile.mode == "RGBA"
            assert tile.getpixel((0, 0))[3] == 0
            tile.load()


def test_setup_places_turtuga_and_the_starting_harvester(start_game):
    game, _channel = start_game(factions=["tur", "eri"])
    state = game.gamestate
    assert state["board"]["201"]["sector"] == "253"
    assert state["board"]["201"]["player_ships"] == ["blue-sb"]
    assert state["board"]["201"]["scienceadv_pop"] == [0]
    assert state["board"]["201"]["materialadv_pop"] == [0]
    assert state["board"]["201"]["money_pop"] == [1]
    assert state["board"]["201"]["material_pop"] == [1]
    assert "blue-int" not in state["board"]["201"]["player_ships"]


def test_render_home_tile(start_game):
    game, _channel = start_game(factions=["tur", "eri"])
    image = DrawHelper(game.gamestate).board_tile_image("201")
    assert image.size == (1024, 890)
