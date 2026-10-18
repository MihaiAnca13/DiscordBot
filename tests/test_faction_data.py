from pathlib import Path

from Buttons.Research import ResearchButtons
from helpers import FactionData
from helpers.CombatHelper import Combat
from tests.fakes import POS, player_stats


def test_every_faction_row_carries_its_artwork_and_colour():
    """factions.json drives the emoji, board and setup colour lookups."""
    for key, faction in FactionData.FACTIONS.items():
        artwork = faction["artwork"]
        assert faction["setup_color"], key
        assert Path(f"images/resources/components/factions/{artwork}_board.png").exists(), key
        assert Path(f"images/resources/components/layouts/factionImages/{artwork}_image.png").exists(), key


def test_abilities_come_from_the_faction_data():
    assert FactionData.has(player_stats("tm"), "techno_magic")
    assert not FactionData.has(player_stats("hyd"), "techno_magic")
    # A faction that is not in the file at all falls back to its own fields.
    assert not FactionData.has({"name": "Homebrew", "color": "blue"}, "techno_magic")


def test_rho_trades_money_on_the_factions_own_ratio():
    player = player_stats("rho", science=0, money=6, materials=0)
    assert ResearchButtons.getPlayerTotalAvailableScience(player, None) == 4
    assert ResearchButtons.getPlayerTotalAvailableScience(player_stats("hyd", science=0, money=6,
                                                                      materials=0), None) == 2


def test_starting_ships_come_from_the_faction_data(start_game):
    game, _channel = start_game(factions=["exl", "rho"])

    assert game.gamestate["board"]["201"]["player_ships"] == ["blue-orb", "blue-int"]
    assert game.gamestate["board"]["203"]["player_ships"] == ["red-int", "red-int"]


def _tile_game(make_game, faction, owner="blue", **tile):
    stats = player_stats(faction, color=owner)
    board_tile = {"owner": owner, "sector": 101, "disctile": 0, "player_ships": [],
                  "orbital_pop": [0]}
    board_tile.update(tile)
    return make_game({"players": {"1": stats}, "board": {POS: board_tile}})


def test_an_orbital_counts_as_a_ship_only_for_a_faction_that_says_so(make_game):
    assert Combat.exile_orbital_exists(
        _tile_game(make_game, "exl", player_ships=["blue-orb"], orbital_pop=[1]), POS)
    assert not Combat.exile_orbital_exists(
        _tile_game(make_game, "hyd", player_ships=["blue-orb"], orbital_pop=[1]), POS)


def test_only_the_draco_data_gives_a_pass_against_the_ancients(make_game):
    draco = _tile_game(make_game, "dra", player_ships=["blue-int", "ai-anc"])
    assert Combat.isDracoAgainstAncients(draco, POS)
    assert not Combat.isDracoAgainstAncients(
        _tile_game(make_game, "hyd", player_ships=["blue-int", "ai-anc"]), POS)
