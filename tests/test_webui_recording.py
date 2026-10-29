"""Discord prompts land in the same feed, with one canonical message id."""
from types import SimpleNamespace

import discord
import pytest
from discord.ui import Button, View

from Buttons.Draft import DraftButtons
from commands.setup_commands import CommunitySheetButtonView, CommunitySheetSelectView
from listeners.ButtonListener import ButtonListener
from webui import runtime
from webui.server import build

from tests.fakes import FakeChannel, FakeInteraction
from webui.store import FeedStore
from webui.transport import RecordingInteraction


@pytest.fixture
def store(tmp_path):
    feed = FeedStore(str(tmp_path / "feed.sqlite3"))
    yield feed
    feed.close()


def view():
    result = View()
    result.add_item(Button(label="Build", style=1, custom_id="FCIDblue_startBuild"))
    return result


def test_the_same_discord_message_keeps_one_canonical_id(store, run):
    channel = FakeChannel("aeb1-actions")
    message = run(channel.send("prompt", view=view()))

    first = RecordingInteraction(FakeInteraction(channel, custom_id="x", message=message), store, "aeb1")
    second = RecordingInteraction(FakeInteraction(channel, custom_id="x", message=message), store, "aeb1")

    assert first.message.id == second.message.id


def test_deleting_through_the_feed_deletes_the_discord_message(store, run):
    channel = FakeChannel("aeb1-actions")
    wrapped = RecordingInteraction(FakeInteraction(channel, custom_id="x"), store, "aeb1")
    sent = run(wrapped.channel.send("prompt", view=view()))

    run(sent.delete())

    assert store.get(sent.id)["deleted"]
    assert channel.messages[0].id in channel.deleted


def test_editing_discord_content_preserves_buttons_until_explicitly_removed(store, run):
    channel = FakeChannel("aeb1-actions")
    wrapped = RecordingInteraction(FakeInteraction(channel, custom_id="x"), store, "aeb1")
    sent = run(wrapped.channel.send("prompt", view=view()))
    run(sent.edit(content="updated"))
    assert store.get(sent.id)["buttons"]
    run(sent.edit(view=None))
    assert store.get(sent.id)["buttons"] == []


def test_ephemeral_discord_replies_are_private_to_the_presser(store, run):
    channel = FakeChannel("aeb1-actions")
    wrapped = RecordingInteraction(FakeInteraction(channel, custom_id="x", user_id=42), store, "aeb1")

    run(wrapped.followup.send("only you", ephemeral=True))

    assert store.open_messages("aeb1", "42")[0]["content"] == "only you"
    seen_by_other = [m["content"] for m in store.open_messages("aeb1", "43")]
    assert "only you" not in seen_by_other


def test_runtime_wraps_game_channels_only(tmp_path, monkeypatch):
    from webui import runtime

    store = FeedStore(str(tmp_path / "feed.sqlite3"))
    monkeypatch.setattr(runtime, "store", store)
    monkeypatch.setattr(runtime, "mirror", None)

    game_press = FakeInteraction(FakeChannel("aeb1-actions"), custom_id="x")
    assert isinstance(runtime.record(game_press), RecordingInteraction)

    elsewhere = FakeInteraction(FakeChannel("general"), custom_id="x")
    assert runtime.record(elsewhere) is elsewhere
    store.close()


@pytest.mark.parametrize("target", ["channel", "followup", "response"])
@pytest.mark.parametrize("attachment", [None, "file", "files"])
def test_discord_sends_omit_unused_optional_arguments(store, run, target, attachment):
    calls = []

    async def strict_send(content=None, **kwargs):
        assert "view" not in kwargs
        assert not ("file" in kwargs and "files" in kwargs)
        assert all(value is not None for value in kwargs.values())
        calls.append(kwargs)
        return SimpleNamespace(id=123, attachments=[])

    interaction = FakeInteraction(FakeChannel("aeb1-actions"), custom_id="x")
    real = SimpleNamespace(send_message=strict_send) if target == "response" else SimpleNamespace(send=strict_send, name="aeb1-actions")
    setattr(interaction, target, real)
    wrapped = RecordingInteraction(interaction, store, "aeb1")
    options = {attachment: object()} if attachment else {}
    sender = getattr(wrapped, target)
    run(sender.send_message("test", **options) if target == "response" else sender.send("test", **options))
    assert len(calls) == 1
    for key, value in options.items():
        assert calls[0][key] is value


def test_setup_draft_channel_records_choices_and_deletes_real_message(store, run, start_game, monkeypatch, tmp_path):
    game, channel = start_game()
    game.gamestate.update(setup_finished=False, draftingPlayers=[1, 2], draftedFactions=[], bannedFactions=[], draftMessages=[])
    game.update()
    monkeypatch.setattr(runtime, "store", store)
    recorded = runtime.record_channel(channel, game.game_id)
    run(DraftButtons.sendDraftOptions(game, recorded, "Choose a faction"))
    surface = build(store=store, data_dir=str(tmp_path))
    mine = surface.snapshot(game.game_id, "1")["pending"]
    assert any(button["custom_id"].startswith("draftFaction_")
               for message in mine for button in message["buttons"])
    assert surface.snapshot(game.game_id, "2")["pending"] == []
    run(DraftButtons.clearDraftOptions(game, recorded))
    assert channel.deleted
    assert surface.snapshot(game.game_id, "1")["pending"] == []


@pytest.mark.parametrize("kind", ["button", "select"])
def test_community_sheet_controls_are_handled_only_by_their_own_callbacks(run, monkeypatch, kind):
    async def check():
        manager = SimpleNamespace(sheets={"cog": ("Children of Cog", "cog.png")})
        view = CommunitySheetButtonView(manager) if kind == "button" else CommunitySheetSelectView(manager)
        interaction = FakeInteraction(custom_id=view.children[0].custom_id)
        interaction.type = discord.InteractionType.component
        monkeypatch.setattr(runtime, "record", lambda request: pytest.fail("Global handler must ignore sheet controls"))
        await ButtonListener(None).on_interaction(interaction)
    run(check())
