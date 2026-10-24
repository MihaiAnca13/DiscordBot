import json

import pytest

from helpers.ShipHelper import PlayerShip
from tests.fakes import FACTIONS, player_stats


def test_midas_faction_stats_match_printed_card():
    mid = FACTIONS["mid"]
    assert mid["name"] == "Legion of Midas"
    assert mid["artwork"] == "midas"
    assert mid["setup_color"] == "yellow"
    assert mid["community"] is True
    assert mid["abilities"] == ["midas_touch", "money_is_power", "all_that_glitters"]
    assert (mid["materials"], mid["science"], mid["money"]) == (2, 3, 4)
    assert (mid["colony_ships"], mid["base_colony_ships"]) == (3, 3)
    assert mid["home_planet"] == "277"
    assert mid["military_tech"] == [] and mid["grid_tech"] == ["ade"] and mid["nano_tech"] == []
    assert [mid[key] for key in ("explore_apt", "research_apt", "upgrade_apt",
                                 "build_apt", "move_apt", "influence_apt")] == [1, 1, 2, 2, 2, 2]
    assert mid["trade_value"] == 3
    assert mid["influence_discs"] == 12
    assert mid["reputation_track"] == ["amb", "mixed", "mixed", "mixed"]
    assert mid.get("reputation_only_slots", []) == []
    assert (mid["money_pop_cubes"], mid["material_pop_cubes"], mid["science_pop_cubes"]) == (12, 12, 12)
    assert mid["tech_track"] == [-8, -6, -4, -3, -2, -1, 0, 0]
    assert [mid[key] for key in ("cost_orbital", "cost_monolith", "cost_interceptor",
                                 "cost_cruiser", "cost_dread", "cost_starbase")] == [4, 10, 3, 5, 8, 3]
    assert mid["ship_stock"] == [7, 4, 2, 4]


def test_midas_starting_tech_is_advanced_economy():
    with open("data/techs.json", "r") as f:
        techs = json.load(f)
    assert techs["ade"]["name"] == "Advanced Economy"
    assert techs["ade"]["track"] == "grid"


def test_midas_blueprint_parts_and_cells():
    with open("data/parts.json", "r") as f:
        parts = json.load(f)
    mid = FACTIONS["mid"]
    for ship in ("interceptor", "cruiser", "dread", "starbase"):
        for part in mid[f"{ship}_parts"]:
            assert part == "empty" or part in parts
    for ship in ("interceptor", "cruiser", "dread"):
        assert len(mid["blueprint_slots"][ship]) == len(mid[f"{ship}_parts"])


@pytest.mark.parametrize("ship,expected", [
    ("interceptor", (0, 1, 1, 0, 3, 3)),
    ("cruiser", (1, 1, 1, 1, 2, 5)),
    ("dread", (2, 0, 1, 1, 1, 8)),
    ("starbase", (2, 2, 0, 1, 4, 3)),
])
def test_midas_ship_stats(ship, expected):
    model = PlayerShip(player_stats("mid"), ship)
    assert (model.hull, model.energy, model.range, model.computer, model.speed, model.cost) == expected
