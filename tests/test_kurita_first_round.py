"""Kurita Prefecture through the real draft/setup flow (community mode)."""
import random
from pathlib import Path

from PIL import Image

from Buttons.Draft import DraftButtons
from helpers.DrawHelper import DrawHelper
from helpers.GamestateHelper import GamestateHelper
from setup.GameInit import GameInit
from tests.fakes import FakeChannel, FakeInteraction, buttons, reload


def test_kurita_setup_assigns_its_data_and_has_no_setup_hook(games_dir, run, press, monkeypatch):
    random.seed(0)

    def load_thumbnail(self, filename):
        assert Path(filename).is_file(), filename
        return Image.new("RGBA", (1024, 890))

    monkeypatch.setattr(DrawHelper, "use_image", load_thumbnail)
    monkeypatch.setattr(DrawHelper, "use_resized_image",
                        lambda self, filename, size: self.use_image(filename).resize(size))
    GameInit("Kurita first round", [[1, "<@1>"], [2, "<@2>"]],
             "def", True, True, False, False, community_factions=True).create_game()
    game = GamestateHelper(None, "aeb1")
    game.setup_techs_and_outer_rim(2, False, False)
    game.gamestate["discTiles"] = ["mog", "sci", "mat", "cru"]
    game.gamestate["tile_deck_100"] = ["102", "103"]
    game.update()
    channel = FakeChannel("aeb1-actions")
    interaction = FakeInteraction(channel, role_names=["aeb1"])
    run(DraftButtons.generalSetup(interaction, game, [1, 2], ["kur", "hyd"]))

    state = reload(game).gamestate
    kurita = state["players"]["1"]
    assert kurita["name"] == "Kurita Prefecture"
    assert kurita["color"] == "red"
    assert kurita["military_tech"] == ["phs"]
    assert kurita["reputation_track"] == ["mixed", "mixed", "rep", "rep"]
    assert (kurita["materials"], kurita["science"], kurita["money"]) == (4, 3, 2)
    assert kurita["colony_ships"] == 3
    assert state["board"]["201"]["sector"] == "251"
    assert state["board"]["201"]["player_ships"] == ["red-int"]
    assert state["board"]["207"]["sector"] == "224"
    assert state["players"]["2"]["color"] == "blue"
    assert state["activePlayerColor"] == ["red"]

    run(game.updateNamesAndOutRimTiles(FakeInteraction()))

    offered = [button.custom_id for _content, kwargs in channel.sent
               for button in getattr(kwargs.get("view"), "children", [])]
    assert not [custom_id for custom_id in offered
                if any(hook in custom_id for hook in ("ancientsCube", "selectDiscTile", "setupTech"))]

    press(channel, 1, "FCIDred_passForRound")
    assert reload(game).gamestate["activePlayerColor"] == ["blue"]
    press(channel, 2, "FCIDblue_passForRound")
    final_game = reload(game)
    assert final_game.is_everyone_passed()
    assert "runUpkeep" in buttons(channel)
    # Kurita passed first: starting 2 money plus the +2 pass bonus.
    assert final_game.get_player(1)["money"] == 4
