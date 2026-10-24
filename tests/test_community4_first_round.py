"""Children of Cog, Legion of Midas, The Horde and Vorlons through setup and one round."""
import random
from pathlib import Path

from PIL import Image

from Buttons.Draft import DraftButtons
from helpers.DrawHelper import DrawHelper
from helpers.GamestateHelper import GamestateHelper
from setup.GameInit import GameInit
from tests.fakes import FakeChannel, FakeInteraction, buttons, reload

FACTIONS = ["cog", "mid", "hor", "vor"]
NAMES = {"cog": "Children of Cog", "mid": "Legion of Midas", "hor": "The Horde", "vor": "Vorlons"}
HOMES = {"cog": "256", "mid": "277", "hor": "288", "vor": "235"}
ART = {"cog": "cog", "mid": "midas", "hor": "horde", "vor": "vorlons"}


def find_button(channel, prefix):
    return next(
        button.custom_id
        for content, kwargs in reversed(channel.sent)
        for button in getattr(kwargs.get("view"), "children", [])
        if button.custom_id.startswith(prefix)
    )


def test_community4_factions_setup_and_first_round(games_dir, run, press, monkeypatch):
    random.seed(0)
    loaded_images = []

    def load_thumbnail(self, filename):
        assert Path(filename).is_file(), filename
        loaded_images.append(filename)
        return Image.new("RGBA", (1024, 890))

    monkeypatch.setattr(DrawHelper, "use_image", load_thumbnail)
    monkeypatch.setattr(DrawHelper, "use_resized_image",
                        lambda self, filename, size: self.use_image(filename).resize(size))
    monkeypatch.setattr(DrawHelper, "show_disc_tile", lambda self, name: None)

    GameInit("Wave 4 first round", [[i, f"<@{i}>"] for i in range(1, 5)],
             "def", True, True, False, False, community_factions=True).create_game()
    game = GamestateHelper(None, "aeb1")
    game.setup_techs_and_outer_rim(4, False, False)
    game.gamestate["discTiles"] = ["mog", "sci", "mat", "cru"]
    game.gamestate["tile_deck_100"] = ["101", "102", "103", "104"]
    game.update()
    channel = FakeChannel("aeb1-actions")
    interaction = FakeInteraction(channel, role_names=["aeb1"])
    run(DraftButtons.generalSetup(interaction, game, [1, 2, 3, 4], FACTIONS))

    state = reload(game).gamestate
    colors = {pid: state["players"][str(pid)]["color"] for pid in range(1, 5)}
    for pid, key in enumerate(FACTIONS, 1):
        player = state["players"][str(pid)]
        assert player["name"].startswith(NAMES[key])
        assert player["home_planet"] == HOMES[key]
    assert state["pre_game"]["tasks"] == []
    assert state["activePlayerColor"] == [colors[1]]

    midas = FACTIONS.index("mid") + 1
    midas_color = colors[midas]
    midas_tile = next(tile for tile in state["board"].values() if tile.get("owner") == midas_color)
    assert midas_tile["moneyadv_pop"] == [1]
    assert state["players"][str(midas)]["money_pop_cubes"] == 11

    explored = []
    for pid, key in enumerate(FACTIONS, 1):
        state = reload(game).gamestate
        color = colors[pid]
        assert state["activePlayerColor"] == [color]
        press(channel, pid, f"FCID{color}_startExplore")
        explore = next(cid for cid in buttons(channel)
                       if cid.startswith(f"FCID{color}_exploreTile_"))
        position = explore.split("_")[2]
        press(channel, pid, explore)
        reserved = [cid for cid in buttons(channel)
                    if cid.startswith(f"FCID{color}_reservedTile_{position}_")
                    and "_random_" not in cid]
        if reserved:
            press(channel, pid, reserved[0])
        press(channel, pid, find_button(channel, f"FCID{color}_placeTile_{position}_"))
        influence = [cid for cid in buttons(channel)
                     if cid.startswith(f"FCID{color}_addInfluenceFinish_{position}")]
        if influence:
            press(channel, pid, influence[0])
        press(channel, pid, f"FCID{color}_finishAction")
        press(channel, pid, f"FCID{color}_endTurn")
        state = reload(game).gamestate
        assert state["board"][position].get("sector") is not None
        assert state["board"][position]["owner"] in (color, 0)
        explored.append(position)

    assert len(set(explored)) == 4
    for pid in range(1, 5):
        player = reload(game).get_player(pid)
        assert player["explore_action_counters"] == 1
        assert len(player["owned_tiles"]) >= 1
    assert reload(game).gamestate["activePlayerColor"] == [colors[1]]

    for pid in range(1, 5):
        press(channel, pid, f"FCID{colors[pid]}_passForRound")
    press(channel, 1, "runUpkeep")
    final = reload(game)
    assert final.gamestate["roundNum"] == 2

    for player in final.gamestate["players"].values():
        assert DrawHelper(final.gamestate).player_area(player).size == (5000, 800)
    DrawHelper(final.gamestate).display_turn_order()
    for key in FACTIONS:
        art = ART[key]
        assert f"images/resources/components/layouts/factionImages/{art}_image.png" in loaded_images
        assert f"images/resources/components/layouts/faction_titles/name_trade_{art}.png" in loaded_images
        for ship in ("interceptor", "cruiser", "dreadnought", "starbase"):
            assert (f"images/resources/components/layouts/blueprints/classes/"
                    f"{art}_{ship}_class.png") in loaded_images
        with Image.open(f"images/resources/components/factions/{art}_ambassador.png") as ambassador:
            assert ambassador.size == (512, 512)
            assert ambassador.convert("RGBA").getpixel((0, 0))[3] == 0
