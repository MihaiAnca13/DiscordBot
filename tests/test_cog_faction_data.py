import json

import pytest

from helpers.PlayerHelper import PlayerHelper
from helpers.ShipHelper import PlayerShip
from tests.fakes import FACTIONS, player_stats


def test_cog_faction_stats_match_printed_board():
    cog = FACTIONS["cog"]
    assert cog["name"] == "Children of Cog"
    assert cog["artwork"] == "cog"
    assert cog["setup_color"] == "green"
    assert cog["community"] is True
    assert cog["abilities"] == ["infinite_possibilities", "adaptive_transformation"]
    assert (cog["materials"], cog["science"], cog["money"]) == (3, 2, 3)
    assert (cog["colony_ships"], cog["base_colony_ships"]) == (3, 3)
    assert cog["home_planet"] == "256"
    assert cog["military_tech"] == [] and cog["grid_tech"] == [] and cog["nano_tech"] == ["nar"]
    assert [cog[key] for key in ("explore_apt", "research_apt", "upgrade_apt",
                                 "build_apt", "move_apt", "influence_apt")] == [1, 1, 3, 2, 2, 2]
    assert cog["trade_value"] == 3
    assert cog["influence_discs"] == 12
    assert cog["reputation_track"] == ["amb", "mixed", "mixed", "mixed", "mixed"]
    assert cog.get("reputation_only_slots", []) == []
    assert (cog["money_pop_cubes"], cog["material_pop_cubes"], cog["science_pop_cubes"]) == (12, 11, 11)
    assert cog["population_track"] == [28, 24, 21, 18, 15, 12, 10, 8, 6, 4, 3, 2, 0]
    assert cog["tech_track"] == [-3, -3, -2, -2, -2, -1, 0, 0]
    assert cog["tech_track_vp"] == [0, 0, 0, 1, 2, 2, 2, 3]
    assert [cog[key] for key in ("cost_orbital", "cost_monolith", "cost_interceptor",
                                 "cost_cruiser", "cost_dread", "cost_starbase")] == [4, 10, 3, 5, 8, 3]
    assert cog["ship_stock"] == [7, 4, 2, 4]


def test_cog_starting_tech_is_nanorobots():
    with open("data/techs.json", "r") as f:
        techs = json.load(f)
    assert techs["nar"]["name"] == "Nano Robots"
    assert techs["nar"]["track"] == "nano"


def test_cog_blueprint_parts_exist_and_have_a_cell_each():
    with open("data/parts.json", "r") as f:
        parts = json.load(f)
    cog = FACTIONS["cog"]
    for ship in ("interceptor", "cruiser", "dread", "starbase"):
        for part in cog[f"{ship}_parts"]:
            assert part == "empty" or part in parts, f"unknown {ship} part {part!r}"
    for ship in ("interceptor", "cruiser", "dread"):
        assert len(cog["blueprint_slots"][ship]) == len(cog[f"{ship}_parts"])


@pytest.mark.parametrize("ship,expected", [
    # hull, energy, range, computer, initiative, cost
    ("interceptor", (0, 1, 1, 0, 3, 3)),
    ("cruiser", (1, 1, 1, 1, 2, 5)),
    ("dread", (2, 0, 1, 1, 1, 8)),
    ("starbase", (2, 2, 0, 1, 4, 3)),
])
def test_cog_ship_stats(ship, expected):
    model = PlayerShip(player_stats("cog"), ship)
    assert (model.hull, model.energy, model.range, model.computer, model.speed, model.cost) == expected


def test_cog_abilities_are_declared_once():
    cog = player_stats("cog")
    assert PlayerHelper(cog["player_name"], cog)
    assert "infinite_possibilities" in cog["abilities"]
    assert "adaptive_transformation" in cog["abilities"]
