"""Discord delivery must not hold up web gameplay or lose its pending work."""
import asyncio
import io
from types import SimpleNamespace
from unittest.mock import AsyncMock

import discord
import pytest

from webui.mirror import DiscordMirror
from webui.store import FeedStore
from webui.transport import Surface


def bot_for(channel):
    return SimpleNamespace(wait_until_ready=AsyncMock(),
                           get_guild=lambda guild_id: SimpleNamespace(channels=[channel], threads=[]))


def test_combat_mirroring_uses_the_thread_for_sends_edits_and_deletes(tmp_path):
    async def check():
        store = FeedStore(str(tmp_path / "feed.sqlite3"))
        message = SimpleNamespace(id=123, attachments=[], edit=AsyncMock(), delete=AsyncMock())
        actions = SimpleNamespace(name="aeb1-actions", send=AsyncMock())
        thread = SimpleNamespace(name="aeb1-Round 1, Tile 101, Combat",
                                 send=AsyncMock(return_value=message),
                                 fetch_message=AsyncMock(return_value=message))
        guild = SimpleNamespace(channels=[actions], threads=[thread])
        bot = SimpleNamespace(get_guild=lambda guild_id: guild)
        mirror = DiscordMirror(bot, 1, store, tmp_path)
        sent = await mirror.send("aeb1", thread.name, "battle", None, [])
        await mirror.edit(thread.name, sent["discord_id"], "updated", None)
        await mirror.delete(thread.name, sent["discord_id"])

        actions.send.assert_not_awaited()
        thread.send.assert_awaited_once()
        message.edit.assert_awaited_once_with(content="updated", view=None)
        message.delete.assert_awaited_once()
        store.close()
    asyncio.run(check())


def test_web_created_battle_room_creates_one_discord_thread(tmp_path):
    async def check():
        store = FeedStore(str(tmp_path / "feed.sqlite3"))
        thread = SimpleNamespace(send=AsyncMock(return_value=SimpleNamespace(id=123, attachments=[])))
        actions = SimpleNamespace(name="aeb1-actions", create_thread=AsyncMock(return_value=thread),
                                  send=AsyncMock())
        mirror = DiscordMirror(bot_for(actions), 1, store, tmp_path)
        room = "aeb1-Round 1, Tile 101, Combat"
        await mirror.send("aeb1", room, "battle", None, [])
        await mirror.send("aeb1", room, "roll", None, [])

        actions.create_thread.assert_awaited_once_with(
            name=room, auto_archive_duration=10080, type=discord.ChannelType.public_thread)
        assert thread.send.await_count == 2
        actions.send.assert_not_awaited()
        with pytest.raises(RuntimeError, match="Discord channel unavailable"):
            await mirror.send("aeb1", "missing-room", "battle", None, [])
        store.close()
    asyncio.run(check())


def test_slow_discord_does_not_block_web_and_preserves_order(tmp_path):
    async def check():
        store = FeedStore(str(tmp_path / "feed.sqlite3"))
        started, release, finished = asyncio.Event(), asyncio.Event(), asyncio.Event()
        calls = []

        async def edit(**kwargs):
            assert "view" not in kwargs
            calls.append("edit")

        async def delete():
            calls.append("delete")
            finished.set()

        real = SimpleNamespace(id=123, attachments=[], edit=edit, delete=delete)

        async def send(**kwargs):
            calls.append("send")
            assert kwargs["view"].children[0].disabled is False
            assert kwargs["view"].to_components()[0]["components"][0]["style"] == 2
            started.set()
            await release.wait()
            return real

        channel = SimpleNamespace(name="aeb1-actions", send=send,
                                  fetch_message=AsyncMock(return_value=real))
        mirror = DiscordMirror(bot_for(channel), 1, store, tmp_path)
        mirror.start()
        surface = Surface(store, "aeb1", mirror=mirror, media_dir=str(tmp_path))
        view = discord.ui.View()
        view.add_item(discord.ui.Button(label="Build", custom_id="FCIDblue_startBuild"))
        message = await asyncio.wait_for(surface.send("prompt", view=view), 0.5)
        view.children[0].disabled = True
        await asyncio.wait_for(started.wait(), 0.5)
        await asyncio.wait_for(message.edit(content="updated"), 0.5)
        await asyncio.wait_for(message.delete(), 0.5)
        assert store.get(message.id)["deleted"]
        with pytest.raises(discord.NotFound):
            await surface.channel.fetch_message(message.id)
        assert calls == ["send"]
        release.set()
        await asyncio.wait_for(finished.wait(), 0.5)
        assert calls == ["send", "edit", "delete"]
        assert store.next_mirror_job() is None
        await mirror.close()
        store.close()
    asyncio.run(check())


def test_restart_retains_files_and_skips_obsolete_and_private_prompts(tmp_path):
    async def check():
        path = str(tmp_path / "feed.sqlite3")
        store = FeedStore(path)
        delivered = asyncio.Event()
        calls = []

        async def send(**kwargs):
            calls.append(kwargs)
            assert kwargs["files"][0].fp.read() == b"image bytes"
            delivered.set()
            return SimpleNamespace(id=123, attachments=[])

        channel = SimpleNamespace(name="aeb1-actions", send=send)
        bot = bot_for(channel)
        mirror = DiscordMirror(bot, 1, store, tmp_path)
        surface = Surface(store, "aeb1", mirror=mirror, media_dir=str(tmp_path))
        message = await surface.send("image", file=discord.File(io.BytesIO(b"image bytes"), filename="board.png"))
        await surface.send("private", ephemeral_to="1")
        obsolete = await surface.send("obsolete")
        await obsolete.delete()
        store.close()
        store = FeedStore(path)
        mirror = DiscordMirror(bot, 1, store, tmp_path)
        mirror.start()
        await asyncio.wait_for(delivered.wait(), 0.5)
        assert len(calls) == 1
        assert calls[0]["nonce"] == f"webui-{message.id}"
        assert store.get(message.id)["discord_id"] == "123"
        assert store.next_mirror_job() is None
        await mirror.close()
        store.close()
    asyncio.run(check())


def test_failed_delivery_is_logged_and_remains_queued_for_restart(tmp_path, caplog):
    async def check():
        store = FeedStore(str(tmp_path / "feed.sqlite3"))
        attempted, delivered = asyncio.Event(), asyncio.Event()

        async def fail(**kwargs):
            attempted.set()
            raise RuntimeError("Discord unavailable")

        channel = SimpleNamespace(name="aeb1-actions", send=fail)
        bot = bot_for(channel)
        mirror = DiscordMirror(bot, 1, store, tmp_path)
        mirror.start()
        await Surface(store, "aeb1", mirror=mirror).send("public text without an attachment")
        await asyncio.wait_for(attempted.wait(), 0.5)
        await mirror.close()
        assert store.next_mirror_job() is not None
        assert "retrying" in caplog.text

        async def succeed(**kwargs):
            delivered.set()
            return SimpleNamespace(id=456, attachments=[])

        channel.send = succeed
        mirror = DiscordMirror(bot, 1, store, tmp_path)
        mirror.start()
        await asyncio.wait_for(delivered.wait(), 0.5)
        assert store.next_mirror_job() is None
        await mirror.close()
        store.close()
    asyncio.run(check())
