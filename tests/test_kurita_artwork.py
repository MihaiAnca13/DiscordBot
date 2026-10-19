from pathlib import Path

import pytest
from PIL import Image

from helpers import FactionData
from helpers.DrawHelper import DrawHelper

KURITA_ARTWORK = {
    "images/resources/components/factions/kurita_board.png": ((4401, 2457), "RGB"),
    "images/resources/components/factions/kurita_info.png": ((1855, 957), "RGB"),
    "images/resources/components/factions/kurita_ambassador.png": ((512, 512), "RGBA"),
    "images/resources/components/layouts/factionImages/kurita_image.png": ((512, 512), "RGBA"),
    "images/resources/components/layouts/faction_titles/name_trade_kurita.png": ((1186, 177), "RGBA"),
    "images/resources/components/layouts/blueprints/classes/kurita_interceptor_class.png": ((300, 115), "RGBA"),
    "images/resources/components/layouts/blueprints/classes/kurita_cruiser_class.png": ((300, 115), "RGBA"),
    "images/resources/components/layouts/blueprints/classes/kurita_dreadnought_class.png": ((315, 148), "RGBA"),
    "images/resources/components/layouts/blueprints/classes/kurita_starbase_class.png": ((300, 115), "RGBA"),
    "images/resources/hexes/251.png": ((1024, 890), "RGBA"),
    "images/resources/hexes/numberless/251.png": ((1024, 890), "RGBA"),
}


@pytest.mark.parametrize("path,size_and_mode", KURITA_ARTWORK.items())
def test_kurita_artwork_exists_and_loads(path, size_and_mode):
    size, mode = size_and_mode
    assert Path(path).is_file(), path
    with Image.open(path) as image:
        assert image.size == size, path
        assert image.mode == mode, path
        image.load()


def test_kurita_artwork_key_matches_the_name_lookups():
    assert FactionData.artwork_name("Kurita Prefecture") == "kurita"


def test_kurita_portrait_uses_its_dedicated_image(monkeypatch):
    loaded = []

    def record(self, filename):
        loaded.append(filename)
        return Image.new("RGBA", (512, 512))

    monkeypatch.setattr(DrawHelper, "use_image", record)

    DrawHelper({}).faction_portrait("kurita")

    assert loaded == ["images/resources/components/layouts/factionImages/kurita_image.png"]
