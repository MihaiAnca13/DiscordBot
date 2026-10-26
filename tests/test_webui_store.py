"""The feed store: what a seat may see, and what a delete means."""
import pytest

from webui.store import FeedStore


@pytest.fixture
def store(tmp_path):
    feed = FeedStore(str(tmp_path / "feed.sqlite3"))
    yield feed
    feed.close()


def test_open_messages_are_scoped_to_a_seat(store):
    store.record("aeb1", "aeb1-actions", content="public")
    store.record("aeb1", "private", content="for blue", ephemeral_to="1")

    assert [m["content"] for m in store.open_messages("aeb1", "1")] == ["for blue", "public"]
    assert [m["content"] for m in store.open_messages("aeb1", "2")] == ["public"]


def test_deleted_prompt_leaves_every_feed(store):
    message = store.record("aeb1", "aeb1-actions", content="prompt")
    assert store.open_messages("aeb1", "1")

    store.remove(message)
    assert store.open_messages("aeb1", "1") == []
    assert store.get(message)["deleted"]


def test_edit_bumps_the_message_in_place(store):
    message = store.record("aeb1", "aeb1-actions", content="cost 0")
    store.update(message, content="cost 4")

    row = store.get(message)
    assert row["id"] == message and row["content"] == "cost 4"


def test_discord_id_maps_to_one_record(store):
    message = store.record("aeb1", "aeb1-actions", content="prompt", discord_id=987654321)
    assert store.by_discord_id("aeb1", 987654321)["id"] == message
    assert store.by_discord_id("aeb1", 1234) is None


def test_mirror_switch_defaults_on_and_off_for_web_only(store):
    assert store.mirrors("aeb1") is True
    store.set_mirror("aeb1", False)
    assert store.mirrors("aeb1") is False
