"""Post a web-originated prompt into the game's Discord channel, so cross-play works.

The bot is the only writer of game state, so this lives in the bot process and
runs on the bot's event loop. A game can turn it off (`mirror_to_discord`), which
is what a web-only game wants: no channel spam and no rate limits.
"""
import io
import logging

import discord


class DiscordMirror:
    def __init__(self, bot, guild_id):
        self.bot = bot
        self.guild_id = guild_id

    def _guild(self):
        return self.bot.get_guild(self.guild_id)

    def _channel(self, game_id, room):
        guild = self._guild()
        if guild is None:
            return None
        channel = discord.utils.get(guild.channels, name=room)
        if channel is None:
            channel = discord.utils.get(guild.channels, name=f"{game_id}-actions")
        return channel

    async def send(self, game_id, room, content, view, files):
        channel = self._channel(game_id, room)
        if channel is None:
            return None
        payload = [discord.File(io.BytesIO(data), filename=name) for name, data in (files or [])]
        kwargs = {"content": content}
        if view is not None:
            kwargs["view"] = view
        if payload:
            kwargs["files"] = payload
        try:
            message = await channel.send(**kwargs)
        except discord.HTTPException as error:
            logging.getLogger(__name__).warning("mirror send failed: %s", error)
            return None
        return {"discord_id": message.id,
                "attachments": [{"name": a.filename, "url": a.url} for a in message.attachments]}

    async def edit(self, room, discord_id, content, view):
        channel = self._channel(None, room)
        if channel is None:
            return
        try:
            message = await channel.fetch_message(int(discord_id))
            kwargs = {} if view is discord.utils.MISSING else {"view": view}
            await message.edit(content=content, **kwargs)
        except discord.HTTPException as error:
            logging.getLogger(__name__).warning("mirror edit failed: %s", error)

    async def delete(self, room, discord_id):
        channel = self._channel(None, room)
        if channel is None:
            return
        try:
            message = await channel.fetch_message(int(discord_id))
            await message.delete()
        except discord.HTTPException:
            pass
