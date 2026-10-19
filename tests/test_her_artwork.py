from pathlib import Path

import pytest
from PIL import Image

from helpers import FactionData

HERALDS_ARTWORK = {
    "images/resources/components/factions/heralds_board.png": ((4547, 2539), "RGB"),
    "images/resources/components/factions/heralds_info.png": ((1855, 957), "RGB"),
    "images/resources/components/factions/heralds_ambassador.png": ((512, 512), "RGBA"),
    "images/resources/components/layouts/factionImages/heralds_image.png": ((512, 512), "RGBA"),
    "images/resources/components/layouts/faction_titles/name_trade_heralds.png": ((1186, 177), "RGB"),
    "images/resources/components/layouts/blueprints/classes/heralds_interceptor_class.png": ((300, 115), "RGBA"),
    "images/resources/components/layouts/blueprints/classes/heralds_cruiser_class.png": ((300, 115), "RGBA"),
    "images/resources/components/layouts/blueprints/classes/heralds_dreadnought_class.png": ((315, 148), "RGBA"),
    "images/resources/components/layouts/blueprints/classes/heralds_starbase_class.png": ((300, 115), "RGBA"),
    "images/resources/hexes/299.png": ((1024, 890), "RGBA"),
}


@pytest.mark.parametrize("path,size,mode", [(p, s, m) for p, (s, m) in HERALDS_ARTWORK.items()])
def test_heralds_artwork_exists_and_loads(path, size, mode):
    assert Path(path).is_file(), path
    with Image.open(path) as image:
        assert image.size == size, path
        assert image.mode == mode, path
        image.load()


def test_heralds_board_and_icon_are_the_source_assets():
    source = Path("community-races/factions/Heralds Of Ragnarok")
    if not source.is_dir():
        pytest.skip("community-races source folder is not present in this checkout")
    with Image.open(source / "heralds_board.png") as original, \
            Image.open("images/resources/components/factions/heralds_board.png") as copied:
        assert original.convert("RGB").tobytes() == copied.convert("RGB").tobytes()
    with Image.open(source / "heralds_icon.png") as original, \
            Image.open("images/resources/components/layouts/factionImages/heralds_image.png") as copied:
        assert original.convert("RGBA").tobytes() == copied.convert("RGBA").tobytes()


def test_heralds_ambassador_has_a_transparent_background():
    with Image.open("images/resources/components/factions/heralds_ambassador.png") as image:
        assert image.getpixel((0, 0))[3] == 0
        assert image.getpixel((511, 511))[3] == 0


def test_heralds_artwork_key_matches_the_name_lookups():
    assert FactionData.artwork_name("Heralds of Ragnarok") == "heralds"
