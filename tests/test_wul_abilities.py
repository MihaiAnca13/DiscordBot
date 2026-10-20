"""The Wulfen species rules: no Interceptors, Spine Cannons and Wolf Pack."""
import pytest
from PIL import Image

from Buttons.Build import BuildButtons
from Buttons.Move import MoveButtons
from Buttons.Upgrade import UpgradeButtons
from helpers.CombatHelper import Combat
from helpers.DrawHelper import DrawHelper
from helpers.PlayerHelper import PlayerHelper
from tests.fakes import FakeChannel, FakeInteraction, buttons, player_helper, player_stats, reload


@pytest.fixture(autouse=True)
def _no_tile_render(monkeypatch):
    monkeypatch.setattr(DrawHelper, "board_tile_image_file", lambda self, position: None)
    monkeypatch.setattr(DrawHelper, "mergeLocationsFile", lambda self, positions: None)


def _combat_game(make_game, blue_parts, red_parts=None, blue_tech=None, red_tech=None):
    blue = player_stats("wul", color="blue", cruiser_parts=blue_parts,
                        military_tech=blue_tech or [])
    red = player_stats("hyd", color="red", name="Hydran Progress",
                       cruiser_parts=red_parts or ["ioc", "nus", "nud", "hul", "hul"],
                       military_tech=red_tech or [])
    return make_game({
        "advanced_ai": 0, "wa_ai": 0, "player_count": 2,
        "players": {"1": blue, "2": red},
        "board": {"101": {"owner": 0, "sector": 101, "disctile": 0,
                          "player_ships": ["blue-cru", "red-cru"],
                          "attacker": "red", "defender": "blue"}},
    }, game_id="aeb1")


def test_augment_slot_contributes_no_die(make_game, no_random, run):
    game = _combat_game(make_game, ["nus", "hul", "nud", "ioc", "ioc"])
    inter = FakeInteraction()
    no_random([6])
    run(Combat.rollDice(game, "rollDice_101_blue_2_deleteMsg", inter))

    # one Ion Cannon die, not two: the augment Ion Cannon is only energy
    assert game.gamestate["board"]["101"]["damage_tracker"]["red-cru"] == 1


def test_spine_hit_mode_turns_a_five_into_a_hit(make_game, no_random, run):
    game = _combat_game(make_game, ["nus", "hul", "nud", "ioc", "ioc"])
    inter = FakeInteraction()
    no_random([5])
    run(Combat.rollDice(game, "rollDice_101_blue_2_deleteMsg_spinehit", inter))
    assert game.gamestate["board"]["101"]["damage_tracker"]["red-cru"] == 1

    game = _combat_game(make_game, ["nus", "hul", "nud", "ioc", "ioc"])
    inter = FakeInteraction()
    no_random([5])
    run(Combat.rollDice(game, "rollDice_101_blue_2_deleteMsg", inter))
    assert "damage_tracker" not in game.gamestate["board"]["101"]


def test_spine_roll_modes_are_offered_when_the_cruiser_fires(make_game, run):
    game = _combat_game(make_game, ["nus", "hul", "nud", "ioc", "ioc"])
    game.gamestate["players"]["2"]["cruiser_parts"] = ["nus", "hul", "hul"]  # unarmed, so only blue rolls
    channel = FakeChannel("aeb1-actions")
    run(Combat.promptNextSpeed(game, "101", channel, False))
    assert any(cid.endswith("_spinehit") for cid in buttons(channel))


def test_spine_damage_mode_adds_the_augment_weapons_damage(make_game, no_random, run):
    game = _combat_game(make_game, ["nus", "hul", "nud", "ioc", "ioc"])
    inter = FakeInteraction()
    no_random([6])
    run(Combat.rollDice(game, "rollDice_101_blue_2_deleteMsg_spinedmg", inter))
    assert reload(game).gamestate["board"]["101"]["damage_tracker"]["red-cru"] == 2


def test_a_plasma_augment_adds_two(make_game, no_random, run):
    parts = ["empty", "hul", "hul", "ioc", "plc"]
    blue = player_stats("wul", color="blue", starbase_parts=parts)
    red = player_stats("hyd", color="red", name="Hydran Progress",
                       cruiser_parts=["ioc", "nus", "nud", "hul", "hul", "hul", "hul"])
    game = make_game({
        "advanced_ai": 0, "wa_ai": 0, "player_count": 2,
        "players": {"1": blue, "2": red},
        "board": {"101": {"owner": 0, "sector": 101, "disctile": 0,
                          "player_ships": ["blue-sb", "red-cru"],
                          "attacker": "red", "defender": "blue"}},
    })
    inter = FakeInteraction()
    no_random([6])
    run(Combat.rollDice(game, "rollDice_101_blue_3_deleteMsg_spinedmg", inter))
    # Ion Cannon 1 + Plasma augment 2
    assert game.gamestate["board"]["101"]["damage_tracker"]["red-cru"] == 3


def test_only_the_cannon_slots_die_gets_the_damage_bonus(make_game, no_random, run):
    # a normal Ion Cannon in a grid slot plus the spine cannon: the augment only boosts the latter
    parts = ["elc", "nus", "nud", "ioc", "hyg", "hul", "ioc", "ioc"]
    blue = player_stats("wul", color="blue", dread_parts=parts)
    red = player_stats("hyd", color="red", name="Hydran Progress",
                       cruiser_parts=["ioc", "nus", "nud", "hul", "hul", "hul", "hul"])
    game = make_game({
        "advanced_ai": 0, "wa_ai": 0, "player_count": 2,
        "players": {"1": blue, "2": red},
        "board": {"101": {"owner": 0, "sector": 101, "disctile": 0,
                          "player_ships": ["blue-drd", "red-cru"],
                          "attacker": "red", "defender": "blue"}},
    })
    inter = FakeInteraction()
    no_random([6, 6])
    run(Combat.rollDice(game, "rollDice_101_blue_1_deleteMsg_spinedmg", inter))
    # normal die 1 + cannon die 1 + augment 1
    assert game.gamestate["board"]["101"]["damage_tracker"]["red-cru"] == 3


def test_spine_hit_survives_the_multi_target_prompt(make_game, no_random, run):
    game = _combat_game(make_game, ["nus", "hul", "nud", "ioc", "ioc"],
                        red_parts=["ioc", "nus", "nud", "hul", "hul"])
    game.gamestate["board"]["101"]["player_ships"].append("red-int")
    game.update()
    inter = FakeInteraction()
    no_random([5])
    run(Combat.rollDice(game, "rollDice_101_blue_2_deleteMsg_spinehit", inter))
    target = next(c for c in buttons(inter.channel) if c.startswith("FCIDblue_assignHitTo_"))
    run(Combat.assignHitTo(game, target.replace("FCIDblue_", ""), inter, True))
    assert "red-int" not in game.gamestate["board"]["101"]["player_ships"]


def test_upgrade_menu_filters_spine_slots_to_guns(start_game, press):
    game, channel = start_game(factions=["wul", "eri"])
    game.get_player(1)["military_tech"].append("plc")
    game.update()
    press(channel, 1, "FCIDblue_startUpgrade")
    inter = press(channel, 1, next(c for c in buttons(channel)
                                    if "_upgradeShip_" in c and c.endswith("_cruiser_dummy")))
    menu = {c.custom_id: c.label for c in inter.message.edited["view"].children}
    inter = press(channel, 1, next(c for c in menu if "_selectOldPart_" in c and c.endswith("_3")))
    offered = {c.custom_id.split("_")[5] for c in inter.message.edited["view"].children
               if c.custom_id.startswith("FCIDblue_chooseUpgrade_")}
    assert "ioc" in offered and "plc" in offered
    assert not offered & {"empty", "hul", "anm", "iom", "rican", "ricon"}


def test_spine_replacement_refuses_a_non_gun_without_spending_a_disc(start_game, run):
    game, channel = start_game(factions=["wul", "eri"])
    player = game.get_player(1)
    discs = player["influence_discs"]
    before = list(player["starbase_parts"])
    helper = player_helper(game, "blue")

    interaction = FakeInteraction(channel)
    run(UpgradeButtons.chooseUpgrade(game, player, interaction,
                                     "chooseUpgrade_1_starbase_ioc_hul_3_free", helper))

    assert reload(game).get_player(1)["starbase_parts"] == before
    assert reload(game).get_player(1)["influence_discs"] == discs
    assert "not valid" in interaction.followup.sent[-1][0]


def test_a_valid_spine_replacement_can_be_undone(start_game, press):
    game, channel = start_game(factions=["wul", "eri"])
    game.get_player(1)["military_tech"].append("plc")
    game.update()
    before = list(game.get_player(1)["starbase_parts"])

    press(channel, 1, "FCIDblue_startUpgrade")
    inter = press(channel, 1, next(c for c in buttons(channel)
                                    if "_upgradeShip_" in c and c.endswith("_starbase_dummy")))
    menu = {c.custom_id: c.label for c in inter.message.edited["view"].children}
    inter = press(channel, 1, next(c for c in menu if "_selectOldPart_" in c and c.endswith("_3")))
    menu = {c.custom_id: c.label for c in inter.message.edited["view"].children}
    press(channel, 1, next(c for c in menu
                           if c.startswith("FCIDblue_chooseUpgrade_") and c.split("_")[5] == "plc"))
    assert reload(game).get_player(1)["starbase_parts"][3] == "plc"

    press(channel, 1, next(c for c in buttons(channel) if "_undoUpgrade_" in c))
    assert reload(game).get_player(1)["starbase_parts"] == before


def test_no_interceptors_in_the_build_upgrade_or_move_menus(start_game, press):
    game, channel = start_game(factions=["wul", "eri"])

    press(channel, 1, "FCIDblue_startBuild")
    press(channel, 1, "FCIDblue_buildIn_201")
    labels = list(buttons(channel).values())
    assert "Interceptor" not in labels
    assert "Cruiser (4)" in labels

    press(channel, 1, "FCIDblue_startUpgrade")
    labels = list(buttons(channel).values())
    assert "Interceptor" not in labels
    assert {"Cruiser", "Dread", "Starbase"} <= set(labels)

    press(channel, 1, "FCIDblue_startMove")
    press(channel, 1, "FCIDblue_moveFrom_201_1")
    labels = list(buttons(channel).values())
    assert "Interceptor" not in labels
    assert any(label.startswith("Cruiser") for label in labels)


def test_player_area_draws_three_wulfen_blueprints(start_game, monkeypatch):
    game, _channel = start_game(factions=["wul", "eri"])
    player = game.get_player(1)
    loaded = []

    def stub(self, filename):
        loaded.append(filename)
        return Image.new("RGBA", (1024, 890), (255, 255, 255, 255))

    monkeypatch.setattr(DrawHelper, "use_image", stub)
    monkeypatch.setattr(DrawHelper, "use_resized_image",
                        lambda self, filename, size: self.use_image(filename).resize(size))
    image = DrawHelper(game.gamestate).player_area(player)

    assert image.size == (5000, 800)
    joined = " ".join(loaded)
    assert "blueprint_interceptor.png" not in joined
    for ship in ("cruiser", "dreadnought", "starbase"):
        assert f"wulfen_{ship}_blueprint.png" in joined
        assert f"blueprint_{ship}.png" not in joined


def _wolf_game(make_game):
    blue = player_stats("wul", color="blue",
                        cruiser_parts=["nus", "hul", "nud", "ioc", "ioc"],
                        dread_parts=["elc", "nus", "nud", "empty", "hul", "hul", "ioc", "ioc"])
    red = player_stats("hyd", color="red", name="Hydran Progress",
                       cruiser_parts=["ioc", "nus", "nud", "hul", "hul", "hul", "hul"])
    return make_game({
        "advanced_ai": 0, "wa_ai": 0, "player_count": 2,
        "players": {"1": blue, "2": red},
        "board": {"101": {"owner": 0, "sector": 101, "disctile": 0,
                          "player_ships": ["blue-cru", "red-cru"],
                          "attacker": "red", "defender": "blue"}},
    }, game_id="aeb1")


def test_wolf_pack_converts_a_miss_from_the_same_pool(make_game, no_random, run, press):
    game = _wolf_game(make_game)
    game.gamestate["board"]["101"]["player_ships"].append("blue-cru")
    game.update()
    inter = FakeInteraction()
    no_random([6, 1])
    run(Combat.rollDice(game, "rollDice_101_blue_2_deleteMsg", inter))

    prompt = buttons(inter.channel)
    convert = next(c for c in prompt if c.startswith("FCIDblue_wolfPackConvert_"))
    press(inter.channel, 1, convert, inter.channel.message_with(convert))

    assert reload(game).gamestate["board"]["101"]["damage_tracker"]["red-cru"] == 2


def test_wolf_pack_saves_a_reroll_for_a_later_ship(make_game, no_random, run, press):
    game = _wolf_game(make_game)
    game.gamestate["board"]["101"]["player_ships"].append("blue-cru")
    game.update()
    inter = FakeInteraction()
    no_random([6, 1])
    run(Combat.rollDice(game, "rollDice_101_blue_2_deleteMsg", inter))

    save = next(c for c in buttons(inter.channel) if c.startswith("FCIDblue_wolfPackSave_"))
    press(inter.channel, 1, save, inter.channel.message_with(save))
    game = reload(game)
    assert game.gamestate["board"]["101"]["wolfPackRerolls"]["blue"] == 1

    # the dread fires later in the round and may use the banked reroll on its miss
    game.gamestate["board"]["101"]["player_ships"].append("blue-drd")
    game.update()
    inter2 = FakeInteraction(inter.channel)
    no_random([1])
    run(Combat.rollDice(game, "rollDice_101_blue_1_deleteMsg", inter2))
    reroll = next(c for c in buttons(inter.channel) if c.startswith("FCIDblue_wolfPackReroll_"))
    no_random([6])
    press(inter.channel, 1, reroll, inter.channel.message_with(reroll))
    assert reload(game).gamestate["board"]["101"].get("wolfPackRerolls", {}).get("blue", 0) == 0


def test_wolf_pack_is_not_offered_to_other_factions(make_game, no_random, run):
    blue = player_stats("hyd", color="blue")
    red = player_stats("eri", color="red")
    game = make_game({
        "advanced_ai": 0, "wa_ai": 0, "player_count": 2,
        "players": {"1": blue, "2": red},
        "board": {"101": {"owner": 0, "sector": 101, "disctile": 0,
                          "player_ships": ["blue-cru", "red-cru"],
                          "attacker": "red", "defender": "blue"}},
    })
    inter = FakeInteraction()
    no_random([6])
    run(Combat.rollDice(game, "rollDice_101_blue_2_deleteMsg", inter))

    assert "wolfPack" not in game.gamestate["board"]["101"]
    assert not [c for c in buttons(inter.channel) if "wolfPack" in c]


def test_wolf_pack_six_with_no_miss_offers_only_a_saved_reroll(make_game, no_random, run):
    game = _wolf_game(make_game)
    inter = FakeInteraction()
    no_random([6])
    run(Combat.rollDice(game, "rollDice_101_blue_2_deleteMsg", inter))

    prompt = buttons(inter.channel)
    assert any(c.startswith("FCIDblue_wolfPackSave_") for c in prompt)
    assert any(c.startswith("FCIDblue_wolfPackDone_") for c in prompt)
    assert not [c for c in prompt if c.startswith("FCIDblue_wolfPackConvert_")]


def test_two_sixes_can_each_be_saved(make_game, no_random, run, press):
    game = _wolf_game(make_game)
    game.gamestate["board"]["101"]["player_ships"].append("blue-cru")
    game.update()
    inter = FakeInteraction()
    no_random([6, 6])
    run(Combat.rollDice(game, "rollDice_101_blue_2_deleteMsg", inter))

    for _ in range(2):
        save = next(c for c in buttons(inter.channel) if c.startswith("FCIDblue_wolfPackSave_"))
        press(inter.channel, 1, save, inter.channel.message_with(save))

    assert reload(game).gamestate["board"]["101"]["wolfPackRerolls"]["blue"] == 2


def test_wolf_pack_bank_is_cleared_when_a_new_pairing_starts(make_game, run, monkeypatch):
    game = _wolf_game(make_game)
    game.gamestate["board"]["101"]["wolfPackRerolls"] = {"blue": 1}
    game.update()
    monkeypatch.setattr(DrawHelper, "player_area", lambda self, player: Image.new("RGBA", (1, 1)))
    monkeypatch.setattr(DrawHelper, "show_player_ship_area", lambda self, image: None)

    run(Combat.startCombat(game, FakeInteraction().channel, "101"))

    assert "wolfPackRerolls" not in reload(game).gamestate["board"]["101"]


def test_wolf_pack_keeps_a_six_from_a_killing_attack(make_game, no_random, run, monkeypatch):
    game = _wolf_game(make_game)
    game.get_player(2)["cruiser_parts"] = ["ioc", "nus", "nud"]
    ended = []

    async def winner(game, interaction, pos):
        ended.append(pos)

    monkeypatch.setattr(Combat, "declareAWinner", winner)
    no_random([6])
    inter = FakeInteraction()
    run(Combat.rollDice(game, "rollDice_101_blue_2_deleteMsg", inter))
    assert "red-cru" not in game.gamestate["board"]["101"]["player_ships"]
    assert not ended
    assert "FCIDblue_wolfPackSave_101" in buttons(inter.channel)
    run(Combat.wolfPackChoice(game, "wolfPackSave_101", FakeInteraction(inter.channel)))
    assert ended == ["101"]
