"""THROWAWAY render probe: writes the Heralds player area and home tile for visual review."""
from helpers.DrawHelper import DrawHelper
from tests.fakes import reload


def test_render_heralds_player_area(start_game, tmp_path):
    game, _channel = start_game(factions=["her", "eri"])
    state = reload(game)
    drawing = DrawHelper(state.gamestate)
    drawing.player_area(state.get_player(1)).save(tmp_path / "player_area.png")
    drawing.board_tile_image("201").save(tmp_path / "home_tile.png")
    assert (tmp_path / "player_area.png").is_file()
    assert (tmp_path / "home_tile.png").is_file()
