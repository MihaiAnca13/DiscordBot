from pathlib import Path

import pytest
from PIL import Image

HEG_ARTWORK = {
    "images/resources/components/factions/hegemony_board.png": ((4400, 2475), "RGB"),
    "images/resources/components/factions/hegemony_info.png": ((1855, 957), "RGB"),
    "images/resources/components/factions/hegemony_ambassador.png": ((512, 512), "RGBA"),
    "images/resources/components/layouts/factionImages/hegemony_image.png": ((512, 512), "RGBA"),
    "images/resources/components/layouts/faction_titles/name_trade_hegemony.png": ((1186, 177), "RGBA"),
    "images/resources/components/layouts/blueprints/classes/hegemony_interceptor_class.png": ((300, 115), "RGBA"),
    "images/resources/components/layouts/blueprints/classes/hegemony_cruiser_class.png": ((300, 115), "RGBA"),
    "images/resources/components/layouts/blueprints/classes/hegemony_dreadnought_class.png": ((315, 148), "RGBA"),
    "images/resources/components/layouts/blueprints/classes/hegemony_starbase_class.png": ((300, 115), "RGBA"),
}

HEG_CLASS_ARTWORK = [path for path in HEG_ARTWORK if path.endswith("_class.png")]


@pytest.mark.parametrize("path,expected", HEG_ARTWORK.items())
def test_hegemony_artwork_exists_and_matches_its_target(path, expected):
    size, mode = expected
    assert Path(path).is_file(), path
    with Image.open(path) as image:
        assert image.size == size, path
        assert image.mode == mode, path
        image.load()


def test_hegemony_ambassador_uses_the_shared_tile_mask():
    with Image.open("images/resources/components/factions/hegemony_ambassador.png") as image:
        alpha = image.convert("RGBA").getchannel("A")
        assert alpha.getpixel((0, 0)) == 0
        assert alpha.getpixel((256, 256)) == 255


@pytest.mark.parametrize("path", HEG_CLASS_ARTWORK)
def test_hegemony_class_images_have_visible_pixels(path):
    with Image.open(path) as image:
        assert image.getchannel("A").getextrema()[1] > 0, path

