"""The pre-game phase: the factions that have something to do before the game starts
do it now, and the first turn waits for them.
"""
import random
from pathlib import Path

from PIL import Image

from Buttons.Draft import DraftButtons
from helpers.DrawHelper import DrawHelper
from helpers.GamestateHelper import GamestateHelper
from setup.GameInit import GameInit
from tests.fakes import FakeChannel, FakeInteraction, buttons, reload


def find_button(channel, prefix):
    return next(
        button.custom_id
        for content, kwargs in reversed(channel.sent)
        for button in getattr(kwargs.get("view"), "children", [])
        if button.custom_id.startswith(prefix)
    )


def start_pre_game(games_dir, run, monkeypatch):
    """A four player game with the four factions that act before the game starts."""
    random.seed(0)

    def load_thumbnail(self, filename):
        assert Path(filename).is_file(), filename
        return Image.new("RGBA", (1024, 890))

    monkeypatch.setattr(DrawHelper, "use_image", load_thumbnail)
    monkeypatch.setattr(DrawHelper, "use_resized_image",
                        lambda self, filename, size: self.use_image(filename).resize(size))
    monkeypatch.setattr(DrawHelper, "show_disc_tile", lambda self, name: None)
    GameInit("Pre game phase", [[1, "<@1>"], [2, "<@2>"], [3, "<@3>"], [4, "<@4>"]],
             "def", True, True, False, False, community_factions=True).create_game()
    game = GamestateHelper(None, "aeb1")
    game.setup_techs_and_outer_rim(4, False, False)
    game.gamestate["discTiles"] = ["mog", "sci", "mat", "cru", "mog", "sci"]
    game.gamestate["tile_deck_100"] = ["102", "103", "106", "108"]
    game.update()
    channel = FakeChannel("aeb1-actions")
    interaction = FakeInteraction(channel, role_names=["aeb1"])
    run(DraftButtons.generalSetup(interaction, game, [1, 2, 3, 4], ["exl", "atl", "ra", "tm"]))
    return game, channel


def test_the_first_turn_waits_for_every_pre_game_action(games_dir, run, press, monkeypatch):
    game, channel = start_pre_game(games_dir, run, monkeypatch)

    state = reload(game).gamestate
    assert state["pre_game"]["tasks"] == [["1", "orbital_pop"], ["2", "discovery_tile"],
                                          ["3", "artifact_cube"], ["4", "setup_tech"]]
    # nobody has taken a turn yet
    assert "activePlayerColor" not in state

    # The Exiles put a population cube on the Orbital in their starting sector.
    press(channel, 1, find_button(channel, "FCIDteal_preGameOrbital_"))
    state = reload(game).gamestate
    assert state["board"]["201"]["orbital_pop"] == [1]
    assert state["players"]["1"]["colony_ships"] == 3
    assert state["pre_game"]["tasks"] == [["2", "discovery_tile"], ["3", "artifact_cube"],
                                          ["4", "setup_tech"]]
    assert "activePlayerColor" not in state

    # Remnants of Ra put a cube on the disc of their artifact sector.
    press(channel, 3, find_button(channel, "FCIDyellow_ancientsCube_"))
    assert reload(game).gamestate["board"]["207"]["disc_pop"] == [1]
    assert "activePlayerColor" not in reload(game).gamestate

    # The Atlantians resolve one of the two discovery tiles they drew.
    press(channel, 2, find_button(channel, "FCIDblue_selectDiscTile_"))
    press(channel, 2, find_button(channel, "FCIDblue_keepDiscForPoints"))
    assert reload(game).get_player(2)["disc_tiles_for_points"] == 1
    assert "activePlayerColor" not in reload(game).gamestate

    # The Techno-Mages may pass on their technology, which lets the game start.
    press(channel, 4, find_button(channel, "FCIDpurple_declineSetupTech"))
    state = reload(game).gamestate
    assert state["pre_game"]["tasks"] == []
    assert state["activePlayerColor"] == ["teal"]


def test_the_techno_mages_may_buy_their_technology_before_the_game_starts(games_dir, run, press, monkeypatch):
    game, channel = start_pre_game(games_dir, run, monkeypatch)

    press(channel, 4, "FCIDpurple_setupTech")
    press(channel, 4, next(cid for cid in buttons(channel) if cid.startswith("FCIDpurple_getTech_")))
    # the technology is bought, but the game still waits for the other factions
    assert reload(game).get_player(4)["military_tech"]
    assert len(reload(game).gamestate["pre_game"]["tasks"]) == 3

    press(channel, 1, find_button(channel, "FCIDteal_preGameOrbital_"))
    press(channel, 3, find_button(channel, "FCIDyellow_ancientsCube_"))
    press(channel, 2, find_button(channel, "FCIDblue_selectDiscTile_"))
    press(channel, 2, find_button(channel, "FCIDblue_keepDiscForPoints"))
    assert reload(game).gamestate["activePlayerColor"] == ["teal"]


def test_a_turn_cannot_be_restarted_before_the_game_starts(games_dir, run, press, monkeypatch):
    """The turn menus offer a restart, but there is no turn to go back to yet."""
    game, channel = start_pre_game(games_dir, run, monkeypatch)

    press(channel, 1, find_button(channel, "FCIDteal_preGameOrbital_"))
    press(channel, 1, "FCIDteal_restartTurn")

    state = reload(game).gamestate
    # the pre-game action is not rolled back and no turn has started
    assert state["board"]["201"]["orbital_pop"] == [1]
    assert len(state["pre_game"]["tasks"]) == 3
    assert "activePlayerColor" not in state


def test_a_game_without_pre_game_actions_starts_right_away(games_dir, run, press, monkeypatch):
    random.seed(0)
    GameInit("No pre game actions", [[1, "<@1>"], [2, "<@2>"]],
             "def", True, True, False, False).create_game()
    game = GamestateHelper(None, "aeb1")
    game.setup_techs_and_outer_rim(2, False, False)
    game.update()
    channel = FakeChannel("aeb1-actions")
    interaction = FakeInteraction(channel, role_names=["aeb1"])
    run(DraftButtons.generalSetup(interaction, game, [1, 2], ["hyd", "eri"]))

    state = reload(game).gamestate
    assert state["pre_game"]["tasks"] == []
    assert state["activePlayerColor"] == ["blue"]
