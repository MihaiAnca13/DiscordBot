"""The full game render: the map must keep clear of the round order strip under it."""
from PIL import Image
import pytest

from helpers.DrawHelper import DrawHelper


@pytest.mark.parametrize("faction", ["wul", "eri"])
def test_muon_sources_render_outside_dreadnought_slots(start_game, monkeypatch, faction):
    monkeypatch.setattr(DrawHelper, "use_image",
                        lambda self, filename: Image.new("RGBA", (1024, 890), "white"))
    muon_color = (255, 0, 255, 255)

    def part_image(self, filename, size):
        color = muon_color if filename.endswith("/muon_source.png") else "white"
        return Image.new("RGBA", size, color)

    monkeypatch.setattr(DrawHelper, "use_resized_image", part_image)
    game, _channel = start_game(factions=[faction, "eri"])
    player = game.get_player(1)
    player["dread_parts"].extend(["mus", "mus"])

    image = DrawHelper(game.gamestate).player_area(player)

    x, y = 4760, 180
    size = 64
    assert image.getpixel((x + size // 2, y + size // 2)) == muon_color
    assert image.getpixel((x + size // 2, y + size + 4 + size // 2)) == muon_color


def test_show_game_leaves_a_gap_between_the_map_and_the_round_order(start_game, monkeypatch):
    # Solid stubs so pixel geometry is meaningful without paying the real art cache load.
    def solid(self, filename):
        return Image.new("RGBA", (1024, 890), (255, 255, 255, 255))

    monkeypatch.setattr(DrawHelper, "use_image", solid)
    monkeypatch.setattr(DrawHelper, "use_resized_image",
                        lambda self, filename, size: self.use_image(filename).resize(size))
    game, _channel = start_game()

    image = Image.open(DrawHelper(game.gamestate).show_game().fp).convert("L")
    pixels = image.load()
    width, height = image.size

    def has_content(row, x_from, x_to):
        return any(pixels[x, row] > 40 for x in range(x_from, x_to, 10))

    # The tech tray sits on the left; the two player map is centred right of it.
    strip_top = next(row for row in range(height) if has_content(row, 0, 900))
    map_bottom = max(row for row in range(strip_top) if has_content(row, 900, width))

    assert strip_top - map_bottom >= 30


def test_the_info_strip_has_room_for_the_turn_order(start_game, monkeypatch):
    # The turn order is pasted under the minor species block inside the strip; the strip has to
    # be tall enough or its "Next Round" row is clipped by the canvas and the player areas below.
    monkeypatch.setattr(DrawHelper, "use_image",
                        lambda self, filename: Image.new("RGBA", (1024, 890), (255, 255, 255, 255)))
    game, _channel = start_game()
    game.gamestate["minor_species"] = ["Point Per Ambassador"]
    drawing = DrawHelper(game.gamestate)

    strip = drawing.display_remaining_tiles()
    turn_order = drawing.display_turn_order()

    assert strip.height >= 250 + turn_order.height
