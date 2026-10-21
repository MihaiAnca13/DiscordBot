from pathlib import Path

import pytest
from PIL import Image

from helpers import FactionData

WULFEN_ARTWORK = {
    "images/resources/components/factions/wulfen_board.png": ((4400, 2475), "RGB"),
    "images/resources/components/factions/wulfen_info.png": ((1855, 957), "RGB"),
    "images/resources/components/factions/wulfen_ambassador.png": ((512, 512), "RGBA"),
    "images/resources/components/layouts/factionImages/wulfen_image.png": ((512, 512), "RGBA"),
    "images/resources/components/layouts/faction_titles/name_trade_wulfen.png": ((1186, 177), "RGBA"),
    "images/resources/components/layouts/blueprints/classes/wulfen_cruiser_class.png": ((300, 115), "RGBA"),
    "images/resources/components/layouts/blueprints/classes/wulfen_dreadnought_class.png": ((315, 148), "RGBA"),
    "images/resources/components/layouts/blueprints/classes/wulfen_starbase_class.png": ((300, 115), "RGBA"),
}


@pytest.mark.parametrize("path,size_mode", WULFEN_ARTWORK.items())
def test_wulfen_artwork_exists_and_loads(path, size_mode):
    size, mode = size_mode
    assert Path(path).is_file(), path
    with Image.open(path) as image:
        assert image.size == size, path
        assert image.mode == mode, path
        image.load()


def test_wulfen_artwork_key_matches_the_name_lookups():
    assert FactionData.artwork_name("The Wulfen") == "wulfen"


def test_wulfen_has_no_interceptor_art():
    assert not Path("images/resources/components/layouts/blueprints/classes/"
                    "wulfen_interceptor_class.png").exists()
