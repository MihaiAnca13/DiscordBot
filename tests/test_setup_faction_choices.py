"""The setup command's faction list is too long for Discord's 25 choices."""
from commands.setup_commands import SetupCommands, faction_autocomplete
from tests.fakes import FakeInteraction


def test_setup_game_factions_use_autocomplete():
    for number in range(1, 10):
        parameter = next(p for p in SetupCommands.game.parameters if p.name == f"faction{number}")
        assert parameter.autocomplete is not None
        assert not parameter.choices


def test_faction_autocomplete_filters_and_caps_at_25(run):
    assert len(SetupCommands.factionChoices) > 25
    everything = run(faction_autocomplete(FakeInteraction(), ""))
    assert len(everything) == 25
    filtered = run(faction_autocomplete(FakeInteraction(), "vor"))
    assert [choice.value for choice in filtered] == ["vor"]
