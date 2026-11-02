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


def test_one_discord_message_is_one_row(store):
    first = store.record("aeb1", "aeb1-actions", content="prompt", discord_id=42)
    again = store.record("aeb1", "aeb1-actions", content="prompt", discord_id=42)

    assert again == first
    assert store.get(first)["content"] == "prompt"


def test_a_press_row_is_filled_by_the_send_that_posted_it(store):
    # a press on a just-posted message wrote an empty row first; the send's record fills it
    shell = store.record("aeb1", "aeb1-actions", buttons=[], discord_id=42)
    posted = store.record("aeb1", "aeb1-actions", content="select a tile", discord_id=42,
                          buttons=[{"label": "Go", "custom_id": "go"}])

    assert posted == shell
    row = store.get(shell)
    assert row["content"] == "select a tile"
    assert row["buttons"] == [{"label": "Go", "custom_id": "go"}]


def test_a_full_row_is_not_overwritten_by_a_later_press(store):
    posted = store.record("aeb1", "aeb1-actions", content="select a tile", discord_id=42)
    store.record("aeb1", "aeb1-actions", buttons=[], discord_id=42)

    assert store.get(posted)["content"] == "select a tile"
