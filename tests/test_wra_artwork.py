from pathlib import Path

import pytest
from PIL import Image

from helpers import FactionData

WRA_ARTWORK = {
    "images/resources/components/factions/wraith_board.png": (4400, 2470),
    "images/resources/components/factions/wraith_info.png": (1855, 957),
    "images/resources/components/factions/wraith_ambassador.png": (512, 512),
    "images/resources/components/layouts/factionImages/wraith_image.png": (512, 512),
    "images/resources/components/layouts/faction_titles/name_trade_wraith.png": (1186, 177),
    "images/resources/components/layouts/blueprints/classes/wraith_interceptor_class.png": (300, 115),
    "images/resources/components/layouts/blueprints/classes/wraith_cruiser_class.png": (300, 115),
    "images/resources/components/layouts/blueprints/classes/wraith_dreadnought_class.png": (315, 148),
    "images/resources/components/layouts/blueprints/classes/wraith_starbase_class.png": (300, 115),
    "images/resources/hexes/254.png": (1024, 890),
    "images/resources/hexes/numberless/254.png": (1024, 890),
    "images/resources/components/technology/military/tech_phase_module.png": (257, 257),
}


@pytest.mark.parametrize("path,size", WRA_ARTWORK.items())
def test_wra_artwork_exists_and_loads(path, size):
    assert Path(path).is_file(), path
    with Image.open(path) as image:
        assert image.size == size, path
        image.load()


@pytest.mark.parametrize("path,corner", [
    ("images/resources/components/factions/wraith_ambassador.png", (0, 0)),
    ("images/resources/components/layouts/factionImages/wraith_image.png", (0, 0)),
    ("images/resources/hexes/254.png", (0, 0)),
    ("images/resources/hexes/numberless/254.png", (0, 0)),
    ("images/resources/components/layouts/blueprints/classes/wraith_interceptor_class.png", (0, 0)),
])
def test_wra_transparent_artwork_has_a_clear_corner(path, corner):
    with Image.open(path) as image:
        assert image.mode == "RGBA"
        assert image.getpixel(corner)[3] == 0


def test_wra_artwork_key_matches_the_name_lookups():
    assert FactionData.artwork_name("The Wraith") == "wraith"
