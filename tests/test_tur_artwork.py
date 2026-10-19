from pathlib import Path

import pytest
from PIL import Image

from helpers import FactionData

TUR_ARTWORK = {
    "images/resources/components/factions/turtugan_board.png": ((4405, 2476), "RGB"),
    "images/resources/components/factions/turtugan_info.png": ((1855, 957), "RGB"),
    "images/resources/components/factions/turtugan_ambassador.png": ((512, 512), "RGBA"),
    "images/resources/components/layouts/factionImages/turtugan_image.png": ((512, 512), "RGBA"),
    "images/resources/components/layouts/faction_titles/name_trade_turtugan.png": ((1186, 177), "RGBA"),
    "images/resources/components/layouts/blueprints/classes/turtugan_interceptor_class.png": ((300, 115), "RGBA"),
    "images/resources/components/layouts/blueprints/classes/turtugan_cruiser_class.png": ((300, 115), "RGBA"),
    "images/resources/components/layouts/blueprints/classes/turtugan_dreadnought_class.png": ((315, 148), "RGBA"),
    "images/resources/components/layouts/blueprints/classes/turtugan_starbase_class.png": ((300, 115), "RGBA"),
}


@pytest.mark.parametrize("path,expected", TUR_ARTWORK.items())
def test_turtugan_artwork_exists_and_matches_its_target(path, expected):
    size, mode = expected
    assert Path(path).is_file(), path
    with Image.open(path) as image:
        assert image.size == size, path
        assert image.mode == mode, path
        image.load()


def test_turtugan_image_has_transparent_corners():
    with Image.open("images/resources/components/layouts/factionImages/turtugan_image.png") as image:
        assert image.convert("RGBA").getpixel((0, 0))[3] == 0
    with Image.open("images/resources/components/factions/turtugan_ambassador.png") as image:
        assert image.convert("RGBA").getpixel((0, 0))[3] == 0


def test_turtugan_artwork_key_matches_the_name_lookups():
    assert FactionData.artwork_name("Turtugan") == "turtugan"
