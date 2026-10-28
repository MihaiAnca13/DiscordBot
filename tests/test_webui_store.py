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
