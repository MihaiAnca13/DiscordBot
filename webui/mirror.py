"""Post a web-originated prompt into the game's Discord channel, so cross-play works.

The bot is the only writer of game state, so this lives in the bot process and
runs on the bot's event loop. A game can turn it off (`mirror_to_discord`), which
is what a web-only game wants: no channel spam and no rate limits.
"""
import asyncio
import io
import json
import logging
from pathlib import Path

import discord


class DiscordMirror:
    def __init__(self, bot, guild_id, store, media_dir):
        self.bot = bot
        self.guild_id = guild_id
        self.store = store
        self.media_dir = Path(media_dir)
        self.wakeup = asyncio.Event()
        self.worker = None
        self.created_threads = {}

    def start(self):
        self.worker = asyncio.create_task(self.run())
        self.wakeup.set()

    async def close(self):
        if self.worker is not None:
            self.worker.cancel()
            try:
                await self.worker
            except asyncio.CancelledError:
                pass

    def enqueue(self, operation, game_id, message_id, room, content=None,
                view=discord.utils.MISSING, attachments=()):
        buttons = None
        if view is not discord.utils.MISSING and view is not None:
            buttons = [
                {"label": item.label, "style": int(item.style), "custom_id": item.custom_id,
                 "disabled": item.disabled, "url": item.url,
                 "emoji": str(item.emoji) if item.emoji else None}
                for item in view.children]
        self.store.enqueue_mirror(game_id, message_id, operation, {
            "room": room, "content": content, "buttons": buttons,
            "has_view": view is not discord.utils.MISSING,
            "files": [attachment["name"] for attachment in attachments]})
        self.wakeup.set()

    async def run(self):
        await self.bot.wait_until_ready()
        while True:
            await self.wakeup.wait()
            self.wakeup.clear()
            while job := self.store.next_mirror_job():
                try:
                    await self.deliver(job)
                except Exception:
                    logging.getLogger(__name__).exception("Discord mirror job %s failed; retrying", job["id"])
                    await asyncio.sleep(5)
                else:
                    self.store.finish_mirror_job(job["id"])

    async def deliver(self, job):
        row = self.store.get(job["message_id"])
        if row is None:
            return
        payload = json.loads(job["payload"])
        view = discord.utils.MISSING
        if payload["has_view"]:
            view = None
            if payload["buttons"] is not None:
                view = discord.ui.View(timeout=None)
                for button in payload["buttons"]:
                    button["style"] = discord.ButtonStyle(button["style"])
                    view.add_item(discord.ui.Button(**button))
        if job["operation"] == "send":
            if row["deleted"] or row["discord_id"]:
                return
            files = [(name, (self.media_dir / str(row["id"]) / Path(name).name).read_bytes())
                     for name in payload["files"]]
            # shortcut: nonce deduplication lasts minutes; inspect ambiguous sends after long outages.
            mirrored = await self.send(job["game_id"], payload["room"], payload["content"],
                                       view, files, nonce=f"webui-{row['id']}")
            self.store.attach_discord(row["id"], mirrored["discord_id"], payload["room"])
        elif row["discord_id"]:
            if job["operation"] == "delete":
                await self.delete(payload["room"], row["discord_id"])
            else:
                await self.edit(payload["room"], row["discord_id"], payload["content"], view)

    def _guild(self):
        return self.bot.get_guild(self.guild_id)

    def _channel(self, room):
        if room in self.created_threads:
            return self.created_threads[room]
        guild = self._guild()
        if guild is None:
            return None
        return discord.utils.get([*guild.channels, *guild.threads], name=room)

    async def send(self, game_id, room, content, view, files, nonce=None):
        channel = self._channel(room)
        if channel is None and room.startswith(f"{game_id}-Round "):
            actions = self._channel(f"{game_id}-actions")
            if actions is not None:
                channel = await actions.create_thread(name=room, auto_archive_duration=10080,
                                                      type=discord.ChannelType.public_thread)
                self.created_threads[room] = channel
        if channel is None:
            raise RuntimeError(f"Discord channel unavailable: {room}")
        payload = [discord.File(io.BytesIO(data), filename=name) for name, data in (files or [])]
        kwargs = {"content": content, "nonce": nonce}
        if view is not None:
            kwargs["view"] = view
        if payload:
            kwargs["files"] = payload
        message = await channel.send(**kwargs)
        return {"discord_id": message.id,
                "attachments": [{"name": a.filename, "url": a.url} for a in message.attachments]}

    async def edit(self, room, discord_id, content, view):
        channel = self._channel(room)
        if channel is None:
            raise RuntimeError(f"Discord channel unavailable: {room}")
        try:
            message = await channel.fetch_message(int(discord_id))
            kwargs = {} if view is discord.utils.MISSING else {"view": view}
            await message.edit(content=content, **kwargs)
        except discord.NotFound:
            logging.getLogger(__name__).info("Discord message %s already removed", discord_id)

    async def delete(self, room, discord_id):
        channel = self._channel(room)
        if channel is None:
            raise RuntimeError(f"Discord channel unavailable: {room}")
        try:
            message = await channel.fetch_message(int(discord_id))
            await message.delete()
        except discord.NotFound:
            logging.getLogger(__name__).info("Discord message %s already removed", discord_id)
