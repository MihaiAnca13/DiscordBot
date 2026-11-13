"""One retry when the connection carrying a Discord request was already gone.

discord.py retries a reset connection only for errno 54/10054, which Linux never raises:
here the reset (errno 104) reaches the caller and the request is lost, so an interaction
is never acknowledged or a message never arrives. install() puts one retry in front of the
two request loops every call goes through: the REST client, and the webhook adapter that
answers interactions.

shortcut: the retry is blind, so a request that landed but lost its reply can repeat; that
is the trade discord.py already makes on macOS and Windows.
"""
import aiohttp
import discord.webhook.async_


def _retrying(call):
    async def request(*args, **kwargs):
        try:
            return await call(*args, **kwargs)
        except aiohttp.ClientConnectionError:
            return await call(*args, **kwargs)
    return request


def install(bot):
    """Give the bot's Discord traffic one retry; call once, before it connects."""
    bot.http.request = _retrying(bot.http.request)
    adapter = discord.webhook.async_.async_context.get()
    adapter.request = _retrying(adapter.request)
