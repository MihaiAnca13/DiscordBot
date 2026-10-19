"""Heralds of Ragnarok through setup and a first round, using the real engine and save files."""
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
        for _content, kwargs in reversed(channel.sent)
        for button in getattr(kwargs.get("view"), "children", [])
        if button.custom_id.startswith(prefix)
    )


def _stub_render(monkeypatch):
    def load_thumbnail(self, filename):
        assert Path(filename).is_file(), filename
        return Image.new("RGBA", (1024, 890))

    monkeypatch.setattr(DrawHelper, "use_image", load_thumbnail)
    monkeypatch.setattr(DrawHelper, "use_resized_image",
                        lambda self, filename, size: self.use_image(filename).resize(size))


def test_heralds_through_the_real_draft(games_dir, run, monkeypatch):
    _stub_render(monkeypatch)
    random.seed(0)
    GameInit("Heralds draft", [[1, "<@1>"], [2, "<@2>"], [3, "<@3>"]],
             "def", True, True, False, False, community_factions=True).create_game()
    game = GamestateHelper(None, "aeb1")
    game.setup_techs_and_outer_rim(3, False, False)
    channel = FakeChannel("aeb1-actions")
    interaction = FakeInteraction(channel, role_names=["aeb1"])
    run(DraftButtons.generalSetup(interaction, game, [1, 2, 3], ["her", "ra", "tm"]))

    state = reload(game).gamestate
    assert state["players"]["1"]["name"] == "Heralds of Ragnarok"
    assert state["players"]["1"]["color"] == "yellow"
    assert state["board"]["201"]["sector"] == "299"
    assert state["board"]["201"]["player_ships"] == ["yellow-cru"]
    assert state["players"]["1"]["materials"] == 2
    assert state["players"]["1"]["science"] == 3
    assert state["players"]["1"]["money"] == 3
    assert state["players"]["2"]["name"] == "Remnants of Ra"
    assert state["board"]["205"]["sector"] == "255"
    assert state["players"]["3"]["name"] == "Techno-Mages"
    assert state["board"]["209"]["sector"] == "244"


def test_heralds_setup_and_first_round(games_dir, start_game, run, press, monkeypatch):
    """The first-round flows render art internally, so it is stubbed out (the stub checks the
    file exists)."""
    _stub_render(monkeypatch)
    game, channel = start_game(factions=["her", "eri"])

    state = reload(game).gamestate
    assert state["players"]["1"]["name"] == "Heralds of Ragnarok"
    assert state["board"]["201"]["sector"] == "299"
    assert state["players"]["1"]["military_tech"] == ["neb"]
    assert state["players"]["1"]["reputation_track"] == ["amb", "mixed", "mixed", "rep", "rep"]
    assert state["players"]["1"]["ship_stock"] == [8, 3, 2, 4]
    assert state["board"]["201"]["player_ships"] == ["blue-cru"]

    game = reload(game)
    game.gamestate["discTiles"] = ["mog", "sci", "mat", "cru"]
    game.gamestate["tile_deck_100"] = ["102", "103"]
    game.update()

    press(channel, 1, "FCIDblue_startExplore")
    explore = next(cid for cid in buttons(channel) if cid.startswith("FCIDblue_exploreTile_1"))
    position = explore.split("_")[2]
    press(channel, 1, explore)
    press(channel, 1, find_button(channel, f"FCIDblue_placeTile_{position}_"))
    press(channel, 1, find_button(channel, f"FCIDblue_addInfluenceFinish_{position}"))
    press(channel, 1, "FCIDblue_finishAction")
    press(channel, 1, "FCIDblue_endTurn")

    state = reload(game)
    assert state.gamestate["board"][position]["sector"] in {"102", "103"}
    assert state.gamestate["board"][position]["owner"] == "blue"
    assert state.get_player(1)["explore_action_counters"] == 1
    assert len(state.get_player(1)["owned_tiles"]) == 2
    assert state.gamestate["activePlayerColor"] == ["red"]

    # Red passes first, so Blue gets no passing money; Heralds keep their printed 2/3/3.
    press(channel, 2, "FCIDred_passForRound")
    press(channel, 1, "FCIDblue_passForRound")
    final = reload(game)
    assert final.is_everyone_passed()
    assert "runUpkeep" in buttons(channel)
    assert final.get_player(1)["materials"] == 2
    assert final.get_player(1)["science"] == 3
    assert final.get_player(1)["money"] == 3
