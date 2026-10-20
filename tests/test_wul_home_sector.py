import json
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw

from helpers.DrawHelper import DrawHelper
from tests.fakes import reload


def lupis():
    with open("data/sectors.json") as f:
        return json.load(f)["252"]


def test_lupis_sector_data():
    sector = lupis()
    assert sector["name"] == "Lupis"
    assert sector["type"] == "home"
    assert sector["ring"] == 2
    assert sector["vp"] == 3
    assert sector["artifact"] == 1
    assert sector["wormholes"] == [0, 1, 3, 4]
    assert sector["money_pop"] == [1]
    assert sector["material_pop"] == [1]
    assert sector["materialadv_pop"] == [0]
    assert sector["science_pop"] == [] and sector["neutral_pop"] == []
    for key, coords in sector.items():
        if key.endswith("_snap") and coords:
            assert len(coords) == 2, f"{key} {coords} is not a point"
            assert 0 <= coords[0] <= 1024 and 0 <= coords[1] <= 890, f"{key} {coords} is off the tile"


def test_home_tile_and_numberless_art():
    for path in ("images/resources/hexes/252.png", "images/resources/hexes/numberless/252.png"):
        assert Path(path).is_file(), path
        with Image.open(path) as tile:
            assert tile.size == (1024, 890), path
            assert tile.mode == "RGBA"
            rgba = tile.convert("RGBA")
            assert rgba.getpixel((0, 0))[3] == 0
            # the three population square centres are inside the hex
            assert rgba.getpixel((299, 79))[3] > 0
            assert rgba.getpixel((299, 191))[3] > 0
            assert rgba.getpixel((889, 399))[3] > 0


def test_setup_places_lupis_and_the_starting_cruiser(start_game):
    game, _channel = start_game(factions=["wul", "eri"])
    state = reload(game)

    tile = state.gamestate["board"]["201"]
    assert tile["sector"] == "252"
    assert tile["money_pop"] == [1]
    assert tile["material_pop"] == [1]
    assert tile["materialadv_pop"] == [0]
    assert tile["player_ships"] == ["blue-cru"]

    player = state.get_player(1)
    assert player["home_planet"] == "252"
    assert player["grid_tech"] == ["fus"]
    assert "interceptor_parts" not in player
    assert player["cruiser_parts"] == ["nus", "hul", "nud", "ioc", "ioc"]


def test_board_tile_image_uses_the_number_snap(start_game, monkeypatch):
    game, _channel = start_game(factions=["wul", "eri"])
    drawing = DrawHelper(game.gamestate)
    image = drawing.board_tile_image("201")
    assert image.size == (1024, 890)
    original_text = ImageDraw.ImageDraw.text

    def omit_map_number(self, xy, text, *args, **kwargs):
        if text != "201":
            return original_text(self, xy, text, *args, **kwargs)

    monkeypatch.setattr(ImageDraw.ImageDraw, "text", omit_map_number)
    without_number = drawing.board_tile_image("201")
    difference = ImageChops.difference(image.convert("RGB"), without_number.convert("RGB"))
    bounds = difference.getbbox()
    assert bounds is not None
    left, top, right, bottom = bounds
    assert 650 <= left < right <= 850
    assert 310 <= top < bottom <= 430
