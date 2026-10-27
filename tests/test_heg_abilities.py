"""Hegemony of the Highest Cushion: Nine Lives, Pounce and Solitary Hunter."""

from helpers.CombatHelper import Combat
from helpers.DrawHelper import DrawHelper
from tests.fakes import (FakeChannel, FakeInteraction, buttons, player_helper, player_stats,
                         reload)


def _combat_game(make_game, ships, attacker, defender, extra=None, players=None):
    tile = {"owner": 0, "sector": 101, "disctile": 0, "player_ships": list(ships),
            "attacker": attacker, "defender": defender}
    tile.update(extra or {})
    return make_game({
        "advanced_ai": 0, "wa_ai": 0, "player_count": 2,
        "activePlayerColor": ["blue"],
        "players": players or {"1": player_stats("heg", color="blue"),
                               "2": player_stats("eri", color="red")},
        "board": {"101": tile},
    }, game_id="aeb1")


def test_solitary_hunter_boosts_a_lone_ship(make_game, no_random, run):
    # a later engagement round keeps Pounce out of the picture
    game = _combat_game(make_game, ["blue-int", "red-cru"], "blue", "red", {"engagementRound": 2})
    ships = game.gamestate["board"]["101"]["player_ships"]
    assert Combat.getCombatantShipsBySpeed(game, "blue", ships, "101") == [(4, "int", 1)]
    # 5 + 1 (Solitary Hunter) makes a yellow die hit a shieldless cruiser
    no_random([5])
    run(Combat.rollDice(game, "rollDice_101_blue_4_deleteMsg", FakeInteraction()))
    assert game.gamestate["board"]["101"]["damage_tracker"]["red-cru"] == 1


def test_solitary_hunter_is_off_with_a_second_friendly_ship(make_game, no_random, run):
    game = _combat_game(make_game, ["blue-int", "blue-cru", "red-cru"], "blue", "red",
                        {"engagementRound": 2})
    ships = game.gamestate["board"]["101"]["player_ships"]
    assert Combat.getCombatantShipsBySpeed(game, "blue", ships, "101") == [(3, "int", 1), (2, "cru", 1)]
    no_random([5])
    run(Combat.rollDice(game, "rollDice_101_blue_3_deleteMsg", FakeInteraction()))
    assert "damage_tracker" not in game.gamestate["board"]["101"]


def test_pounce_hits_when_shooting_first_in_the_first_round(make_game, no_random, run):
    game = _combat_game(make_game, ["blue-int", "blue-cru", "red-cru"], "blue", "red")
    assert Combat.shooting_first(game, "101") == ["blue"]
    no_random([5])
    run(Combat.rollDice(game, "rollDice_101_blue_3_deleteMsg", FakeInteraction()))
    assert game.gamestate["board"]["101"]["damage_tracker"]["red-cru"] == 1


def test_pounce_is_off_in_the_second_engagement_round(make_game, no_random, run):
    game = _combat_game(make_game, ["blue-int", "blue-cru", "red-cru"], "blue", "red",
                        {"engagementRound": 2})
    no_random([5])
    run(Combat.rollDice(game, "rollDice_101_blue_3_deleteMsg", FakeInteraction()))
    assert "damage_tracker" not in game.gamestate["board"]["101"]


def test_pounce_needs_to_shoot_first(make_game):
    game = _combat_game(make_game, ["blue-int", "blue-cru", "red-int"], "red", "blue")
    # at equal initiative the defender fires first in this codebase
    assert Combat.shooting_first(game, "101") == ["blue"]
    assert Combat.pounce_hit(game, "101", "blue", 3) == 1
    slow = _combat_game(make_game, ["blue-int", "blue-cru", "red-cru"], "red", "blue")
    assert Combat.shooting_first(slow, "101") == ["blue"]
    assert Combat.pounce_hit(slow, "101", "red", 2) == 0  # Pounce is Hegemony only


def test_pounce_never_applies_to_the_missile_round(make_game):
    game = _combat_game(make_game, ["blue-int", "blue-cru", "red-cru"], "blue", "red")
    assert Combat.pounce_hit(game, "101", "blue", 199) == 0


def test_nine_lives_holds_the_hit_until_the_defender_answers(make_game, no_random, run):
    game = _combat_game(make_game, ["red-int", "blue-cru"], "red", "blue")
    channel = FakeChannel("aeb1-actions")
    no_random([6])
    run(Combat.rollDice(game, "rollDice_101_red_3_deleteMsg", FakeInteraction(channel)))
    assert "damage_tracker" not in game.gamestate["board"]["101"]
    assert any(cid.startswith("FCIDblue_nineLives_101_reroll_") for cid in buttons(channel))
    assert any(cid.startswith("FCIDblue_nineLives_101_pass_") for cid in buttons(channel))


def test_nine_lives_works_with_the_last_colony_ship(make_game, no_random, run, press):
    game = _combat_game(make_game, ["red-int", "blue-cru"], "red", "blue")
    game.get_player(1)["colony_ships"] = 1
    game.update()
    channel = FakeChannel("aeb1-actions")
    no_random([6, 1])
    run(Combat.rollDice(game, "rollDice_101_red_3_deleteMsg", FakeInteraction(channel)))
    reroll = next(cid for cid in buttons(channel) if cid.startswith("FCIDblue_nineLives_101_reroll_"))
    press(channel, 1, reroll)
    state = reload(game)
    assert state.gamestate["players"]["1"]["colony_ships"] == 0
    assert "damage_tracker" not in state.gamestate["board"]["101"]


def test_pride_pays_only_on_the_hegemonys_own_centre(make_game):
    def points(owner, alliances=None):
        player = player_stats("heg", color="blue")
        owner_player = player_stats("hyd", color=owner)
        if alliances:
            player["alliances"] = {alliances: False}
            owner_player["alliances"] = {alliances: False}
        game = make_game({
            "players": {"1": player, "2": owner_player},
            "board": {"000": {"sector": "001", "owner": owner, "vp": 0, "artifact": 0}},
        })
        return DrawHelper(game.gamestate).get_public_points(game.get_player(1), True)

    assert points("blue") == 2
    assert points("red") == 0
    assert points("red", alliances="al") == 2  # the faceup Alliance Tile only


def test_nine_lives_declined_lets_the_hit_land(make_game, no_random, run, press):
    game = _combat_game(make_game, ["red-int", "blue-cru"], "red", "blue")
    channel = FakeChannel("aeb1-actions")
    no_random([6])
    run(Combat.rollDice(game, "rollDice_101_red_3_deleteMsg", FakeInteraction(channel)))
    passed = next(cid for cid in buttons(channel) if cid.startswith("FCIDblue_nineLives_101_pass_"))
    press(channel, 1, passed)
    state = reload(game)
    assert state.gamestate["players"]["1"]["colony_ships"] == 3
    assert state.gamestate["board"]["101"]["damage_tracker"]["blue-cru"] == 1


def test_nine_lives_only_answers_the_attacker(make_game):
    game = _combat_game(make_game, ["blue-int", "red-cru"], "blue", "red")
    assert Combat.nine_lives_target(game, "101", "blue", ["red-cru"]) is None
    defender = _combat_game(make_game, ["red-int", "blue-cru"], "red", "blue")
    assert Combat.nine_lives_target(defender, "101", "red", ["blue-cru"]) == "blue"


def test_nine_lives_prompt_answers_once(make_game, no_random, run):
    game = _combat_game(make_game, ["red-int", "blue-cru"], "red", "blue")
    channel = FakeChannel("aeb1-actions")
    no_random([3])
    run(Combat.offerNineLives(game, FakeInteraction(channel), "101", "blue", {
        "roller": "red", "computer": 0, "speed": 3, "dieNum": 6, "hits": [1],
        "dieColor": "yellow", "counter": 1, "ignore": False, "damageBonus": 0, "split": False,
        "shielded": False, "shipType": None}))
    run(Combat.resolveNineLives(game, player_helper(game, "blue"),
                                FakeInteraction(channel), "nineLives_101_pass_1"))
    second = FakeInteraction(channel)
    run(Combat.resolveNineLives(game, player_helper(game, "blue"), second, "nineLives_101_pass_1"))
    assert any("already resolved" in str(content) for content, _ in second.followup.sent)


def test_nine_lives_declined_lethal_hit_closes_the_combat(make_game, no_random, run, press):
    game = _combat_game(make_game, ["red-int", "blue-int"], "red", "blue")
    channel = FakeChannel("aeb1-actions")
    no_random([6])
    run(Combat.rollDice(game, "rollDice_101_red_3_deleteMsg", FakeInteraction(channel)))
    passed = next(cid for cid in buttons(channel) if cid.startswith("FCIDblue_nineLives_101_pass_"))
    press(channel, 1, passed)
    state = reload(game)
    assert "blue-int" not in state.gamestate["board"]["101"]["player_ships"]
    assert state.gamestate["board"]["101"]["nineLivesPending"] == []


def test_nine_lives_also_stops_an_ai_attack(make_game, no_random, run):
    game = _combat_game(make_game, ["ai-anc", "blue-cru"], "ai", "blue")
    channel = FakeChannel("aeb1-actions")
    no_random([6, 6])
    run(Combat.rollDiceAI(game, "rollDice_101_ai_2_deleteMsg", FakeInteraction(channel)))
    assert any(cid.startswith("FCIDblue_nineLives_101_") for cid in buttons(channel))


def test_nine_lives_keeps_each_die_until_it_is_answered(make_game, no_random, run, press):
    game = _combat_game(make_game, ["red-int", "red-int", "blue-cru"], "red", "blue")
    channel = FakeChannel("aeb1-actions")
    no_random([6, 6])

    def prompts():
        return {child.custom_id for _content, kwargs in channel.sent
                for child in getattr(kwargs.get("view"), "children", [])
                if getattr(child, "custom_id", "").startswith("FCIDblue_nineLives_101_pass_")}

    run(Combat.rollDice(game, "rollDice_101_red_3_deleteMsg", FakeInteraction(channel)))
    pending = prompts()
    assert len(pending) == 2
    first = sorted(pending)[0]
    press(channel, 1, first)
    assert len(reload(game).gamestate["board"]["101"]["nineLivesPending"]) == 1
    assert len(prompts() - {first}) == 1
    press(channel, 1, (prompts() - {first}).pop())
    assert reload(game).gamestate["board"]["101"]["nineLivesPending"] == []


def _all_combat_ids(channel):
    return {child.custom_id for _content, kwargs in channel.sent
            for child in getattr(kwargs.get("view"), "children", [])}


def test_lyra_reroll_and_nine_lives_can_be_pending_together(make_game, no_random, run, press):
    blue = player_stats("lyr", color="blue", colony_ships=3,
                        cruiser_parts=["ioc", "nus", "nud", "hul", "hul"])
    red = player_stats("heg", color="red", colony_ships=3,
                       cruiser_parts=["ioc", "nus", "nud", "hul", "hul"])
    game = make_game({
        "advanced_ai": 0, "wa_ai": 0, "player_count": 2,
        "players": {"1": blue, "2": red},
        "board": {"101": {"owner": 0, "sector": 101, "disctile": 0,
                          "player_ships": ["blue-cru", "blue-cru", "red-cru"],
                          "attacker": "blue", "defender": "red"}},
    }, game_id="aeb1")
    channel = FakeChannel("aeb1-actions")

    # One blue die hits (Nine Lives prompt) and the next misses (Lyra reroll prompt).
    no_random([6, 2])
    run(Combat.rollDice(game, "rollDice_101_blue_2_deleteMsg", FakeInteraction(channel)))
    ids = _all_combat_ids(channel)
    assert any(cid.startswith("FCIDred_nineLives_101_") for cid in ids)
    lyra_reroll = next(cid for cid in ids if cid.startswith("FCIDblue_rerollDie_101_blue_"))
    assert reload(game).gamestate["board"]["101"]["nineLivesPending"]

    # Lyra pays its own colony ship; the pending Nine Lives choice is untouched.
    no_random([6])
    press(channel, 1, lyra_reroll)
    after = reload(game)
    assert after.get_player(1)["colony_ships"] == 2
    assert after.get_player(2)["colony_ships"] == 3
    assert after.gamestate["board"]["101"]["nineLivesPending"]

    # Hegemony's forced reroll spends the defender's colony ship, not Lyra's.
    nine_lives_reroll = next(cid for cid in _all_combat_ids(channel)
                             if cid.startswith("FCIDred_nineLives_101_reroll_"))
    no_random([6])
    press(channel, 2, nine_lives_reroll)
    after = reload(game)
    assert after.get_player(1)["colony_ships"] == 2
    assert after.get_player(2)["colony_ships"] == 2
    assert after.gamestate["board"]["101"]["nineLivesPending"] == []


def test_pounce_round_counter_survives_kurita_first_shot_phases(make_game, run):
    game = _combat_game(make_game, ["blue-int", "red-int"], "red", "blue",
                        {"firstShotSide": ["blue"], "firstShotPhase": "opponent",
                         "engagementRound": 1},
                        players={"1": player_stats("kur", color="blue"),
                                 "2": player_stats("heg", color="red")})
    tile = game.gamestate["board"]["101"]
    tile.update({"currentSpeed": 3, "currentRoller": "red"})
    run(Combat.promptNextSpeed(game, "101", FakeChannel("aeb1-actions"), False))
    assert tile["firstShotPhase"] == "kurita"
    assert tile["engagementRound"] == 1
    tile.update({"currentSpeed": 3, "currentRoller": "blue"})
    run(Combat.promptNextSpeed(game, "101", FakeChannel("aeb1-actions"), False))
    assert tile.get("firstShotPhase") is None
    assert tile["engagementRound"] == 2


def _nine_lives_reroll(channel):
    return next(cid for cid in buttons(channel) if cid.startswith("FCIDblue_nineLives_101_reroll_"))


def test_nine_lives_reroll_keeps_built_for_war(make_game, no_random, run, press):
    game = _combat_game(make_game, ["red-cru", "blue-cru"], "red", "blue",
                        players={"1": player_stats("heg", color="blue",
                                                   cruiser_parts=["ioc", "hul", "hul", "nus", "nud"]),
                                 "2": player_stats("hor", color="red")})
    channel = FakeChannel("aeb1-actions")
    no_random([6])
    run(Combat.rollDice(game, "rollDice_101_red_1_deleteMsg", FakeInteraction(channel)))
    no_random([6])
    press(channel, 1, _nine_lives_reroll(channel))
    # a yellow die deals 1, and Built for War adds 1 on the rerolled six too
    assert reload(game).gamestate["board"]["101"]["damage_tracker"]["blue-cru"] == 2


def test_nine_lives_reroll_keeps_spine_damage(make_game, no_random, run, press):
    game = _combat_game(make_game, ["red-cru", "blue-cru"], "red", "blue",
                        players={"1": player_stats("heg", color="blue",
                                                   cruiser_parts=["ioc", "hul", "hul", "nus", "nud"]),
                                 "2": player_stats("wul", color="red",
                                                   cruiser_parts=["nus", "hul", "nud", "ioc", "ioc"])})
    channel = FakeChannel("aeb1-actions")
    no_random([6])
    run(Combat.rollDice(game, "rollDice_101_red_2_deleteMsg_spinedmg", FakeInteraction(channel)))
    no_random([6])
    press(channel, 1, _nine_lives_reroll(channel))
    assert reload(game).gamestate["board"]["101"]["damage_tracker"]["blue-cru"] == 2


def test_nine_lives_offers_once_for_a_split_die(make_game, no_random, run, press):
    game = _combat_game(make_game, ["red-cru", "blue-cru"], "red", "blue",
                        players={"1": player_stats("heg", color="blue"),
                                 "2": player_stats("hor", color="red",
                                                   cruiser_parts=["anc", "nus", "nus", "nud", "hul"],
                                                   military_tech=["ans"])})
    channel = FakeChannel("aeb1-actions")
    no_random([6])
    run(Combat.rollDice(game, "rollDice_101_red_1_deleteMsg", FakeInteraction(channel)))
    # one physical die, so one reroll question; its five one-damage hits wait for the answer
    assert len([cid for cid in buttons(channel) if "nineLives_101_" in cid]) == 2
    press(channel, 1, next(cid for cid in buttons(channel)
                           if cid.startswith("FCIDblue_nineLives_101_pass_")))
    assert "blue-cru" not in reload(game).gamestate["board"]["101"]["player_ships"]
