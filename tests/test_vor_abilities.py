"""Vorlons: Tech Masters, Organic Tech, Few in Number, Regenerative Hull and the Centre bonus."""
import pytest
from PIL import Image

from Buttons.Research import ResearchButtons
from helpers.CombatHelper import Combat
from helpers.DrawHelper import DrawHelper
from helpers.PlayerHelper import PlayerHelper
from tests.fakes import FakeChannel, FakeInteraction, buttons, player_stats, reload

TECH = {"name": "Gauss Shield", "track": "grid", "base_cost": 5, "min_cost": 0}


class FakeGame:
    """The research code paths only need these."""

    def __init__(self, player):
        self.player = player

    def get_player_from_color(self, color):
        return "1"

    def preGameTasks(self):
        return []

    def playerResearchTech(self, player_id, tech, tech_type):
        self.player[f"{tech_type}_tech"].append(tech)

    def update_player(self, player_helper):
        pass


def test_tech_masters_charges_2_3_4_more_for_the_wrong_tray():
    player = player_stats("vor")
    for uses, cost in ((0, 6), (1, 7), (2, 8)):
        player["techMasterUses"] = uses
        assert ResearchButtons.calculate_cost(TECH, "military", player) == cost
    assert ResearchButtons.calculate_cost(TECH, "grid", player) == 4
    assert ResearchButtons.calculate_cost(TECH, "military", player_stats("hyd")) == 5


def test_tech_masters_offers_every_tray_and_records_a_wrong_one(run, monkeypatch):
    monkeypatch.setattr(DrawHelper, "show_tech_ref_image", lambda *args: None)
    player = player_stats("vor", science=20)
    interaction = FakeInteraction()
    game = FakeGame(player)

    run(ResearchButtons.getTech(game, player, PlayerHelper("1", player), interaction,
                                "getTech_gas_grid"))

    assert set(buttons(interaction.channel)) == {
        "FCIDblue_getTech_gas_military_tm",
        "FCIDblue_getTech_gas_grid_tm",
        "FCIDblue_getTech_gas_nano_tm",
    }
    assert buttons(interaction.channel)["FCIDblue_getTech_gas_military_tm"] == "Military (4)"
    assert player["grid_tech"] == []

    run(ResearchButtons.getTech(game, player, PlayerHelper("1", player), interaction,
                                "getTech_gas_military_tm"))

    assert player["military_tech"] == ["gas"]
    assert player["techMasterUses"] == 1
    assert player["science"] == 20 - 4


def test_organic_tech_gives_a_free_upgrade_after_research(start_game, press, monkeypatch):
    monkeypatch.setattr(DrawHelper, "show_tech_ref_image", lambda *args: None)
    monkeypatch.setattr(DrawHelper, "use_image",
                        lambda self, filename: Image.new("RGBA", (1024, 890)))
    monkeypatch.setattr(DrawHelper, "use_resized_image",
                        lambda self, filename, size: self.use_image(filename).resize(size))
    game, channel = start_game(factions=["vor", "eri"])
    game.gamestate["available_techs"] = ["gas"]
    game.get_player(1)["science"] = 40
    game.update()

    press(channel, 1, "FCIDblue_startResearch")
    press(channel, 1, "FCIDblue_getTech_gas_grid")
    assert buttons(channel)["FCIDblue_getTech_gas_grid_tm"] == "Grid (2)"

    press(channel, 1, "FCIDblue_getTech_gas_grid_tm")
    after = reload(game).get_player(1)
    assert after["grid_tech"] == ["gas"]
    assert after["science"] == 38
    offer = next(cid for cid in buttons(channel)
                 if cid.startswith("FCIDblue_ancientInstinctUpgrade_"))
    assert offer == "FCIDblue_ancientInstinctUpgrade_gas"

    discs = after["influence_discs"]
    press(channel, 1, offer)
    inter = press(channel, 1, "FCIDblue_upgradeShip_1_interceptor_gas")
    old_part = next(cid for cid in inter.message.edited["view"].children
                    if cid.custom_id.startswith("FCIDblue_selectOldPart_")
                    and cid.custom_id.endswith("_gas_0"))
    press(channel, 1, old_part.custom_id, inter.message)

    after = reload(game).get_player(1)
    assert after["interceptor_parts"][0] == "gas"
    assert after["influence_discs"] == discs


def test_few_in_number_refreshes_one_colony_ship(start_game, press):
    game, channel = start_game(factions=["vor", "eri"])
    state = reload(game)
    state.get_player(1)["colony_ships"] = 0
    state.update()

    press(channel, 1, "FCIDblue_startInfluence")
    assert "Refresh 1 Colony Ship" in buttons(channel).values()

    press(channel, 1, "FCIDblue_refreshPopShips")
    assert reload(game).get_player(1)["colony_ships"] == 1


def _damaged_vorlons_cruiser(make_game, ships, positions):
    return make_game({
        "advanced_ai": 0, "wa_ai": 0, "player_count": 2,
        "players": {"1": player_stats("vor", color="blue"),
                    "2": player_stats("hyd", color="red")},
        "board": {"101": {"owner": 0, "sector": 101, "disctile": 0,
                          "player_ships": ships,
                          "attacker": positions[0], "defender": positions[1],
                          "damage_tracker": {"blue-cru": 1}}},
    })


def test_regenerative_hull_repairs_a_damaged_ship(make_game, run):
    game = _damaged_vorlons_cruiser(make_game, ["blue-cru", "red-cru"], ("red", "blue"))
    run(Combat.checkForMorphShield(game, "101", FakeChannel(),
                                   ["blue-cru", "red-cru"], ["blue", "red"]))
    assert reload(game).gamestate["board"]["101"]["damage_tracker"]["blue-cru"] == 0


def test_regenerative_hull_repairs_against_guardians(make_game, run):
    game = _damaged_vorlons_cruiser(make_game, ["blue-cru", "ai-grd"], ("ai", "blue"))
    run(Combat.checkForMorphShield(game, "101", FakeChannel(),
                                   ["blue-cru", "ai-grd"], ["blue", "ai"]))
    assert reload(game).gamestate["board"]["101"]["damage_tracker"]["blue-cru"] == 0


def test_regenerative_hull_does_not_repair_against_ancients(make_game, run):
    game = _damaged_vorlons_cruiser(make_game, ["blue-cru", "ai-anc"], ("ai", "blue"))
    run(Combat.checkForMorphShield(game, "101", FakeChannel(),
                                   ["blue-cru", "ai-anc"], ["blue", "ai"]))
    assert reload(game).gamestate["board"]["101"]["damage_tracker"]["blue-cru"] == 1


def test_regenerative_hull_does_not_repair_a_ship_that_lost_the_part(make_game, run):
    game = _damaged_vorlons_cruiser(make_game, ["blue-cru", "red-cru"], ("red", "blue"))
    state = reload(game)
    state.get_player(1)["cruiser_parts"] = ["ioc", "nus", "nud", "hul", "hul", "elc"]
    state.update()
    run(Combat.checkForMorphShield(state, "101", FakeChannel(),
                                   ["blue-cru", "red-cru"], ["blue", "red"]))
    assert reload(state).gamestate["board"]["101"]["damage_tracker"]["blue-cru"] == 1


def test_centre_gives_vorlons_two_points_and_others_none(make_game):
    def points(faction, owner, alliances=None):
        player = player_stats(faction, color="blue")
        owner_player = player_stats("hyd", color=owner)
        if alliances:
            player["alliances"] = {alliances: False}
            owner_player["alliances"] = {alliances: False}
        game = make_game({
            "players": {"1": player, "2": owner_player},
            "board": {"000": {"sector": "001", "owner": owner, "vp": 0, "artifact": 0}},
        })
        return DrawHelper(game.gamestate).get_public_points(game.get_player(1), True)

    assert points("vor", "blue") == 2
    assert points("vor", "red") == 0
    assert points("hyd", "blue") == 0
    assert points("vor", "red", alliances="al") == 4  # the Centre plus the faceup Alliance Tile
