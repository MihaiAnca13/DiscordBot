"""Discord prompts land in the same feed, with one canonical message id."""
import pytest
from discord.ui import Button, View

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


def test_a_discord_prompt_is_recorded(store, run):
    channel = FakeChannel("aeb1-actions")
    wrapped = RecordingInteraction(FakeInteraction(channel, custom_id="showGame"), store, "aeb1")

    run(wrapped.channel.send("blue, choose a tile", view=view()))

    recorded = store.visible_history("aeb1", "1")[0]
    assert recorded["content"] == "blue, choose a tile"
    assert recorded["discord_id"] == str(channel.messages[0].id)
    assert recorded["buttons"][0]["custom_id"] == "FCIDblue_startBuild"


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


def test_game_id_is_read_from_the_channel_name():
    from webui import runtime

    assert runtime.game_id_of(FakeChannel("aeb17-actions")) == "aeb17"
    assert runtime.game_id_of(FakeChannel("aeb22-Round 8, Tile 203, Combat")) == "aeb22"
    assert runtime.game_id_of(FakeChannel("bot-log")) is None


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
