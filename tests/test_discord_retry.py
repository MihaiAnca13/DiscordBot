"""A Discord call must survive the socket Discord closed between requests."""
from types import SimpleNamespace

import aiohttp
import discord.webhook.async_
import pytest

from helpers import DiscordRetry


class Call:
    """A request that drops its connection `drops` times, then answers."""

    def __init__(self, drops):
        self.drops = drops
        self.calls = 0

    async def __call__(self, *args, **kwargs):
        self.calls += 1
        if self.calls <= self.drops:
            raise aiohttp.ClientOSError(104, "Connection reset by peer")
        return "answer"


def test_a_dropped_connection_is_retried_once(run):
    call = Call(drops=1)
    assert run(DiscordRetry._retrying(call)()) == "answer"
    assert call.calls == 2


def test_a_second_drop_is_raised(run):
    with pytest.raises(aiohttp.ClientOSError):
        run(DiscordRetry._retrying(Call(drops=2))())


def test_install_wraps_rest_and_interaction_traffic(monkeypatch, run):
    rest, interactions = Call(drops=1), Call(drops=1)
    bot = SimpleNamespace(http=SimpleNamespace(request=rest))
    adapter = SimpleNamespace(request=interactions)
    monkeypatch.setattr(discord.webhook.async_, "async_context",
                        SimpleNamespace(get=lambda: adapter))

    DiscordRetry.install(bot)

    assert run(bot.http.request()) == "answer"
    assert run(adapter.request()) == "answer"
    assert rest.calls == 2 and interactions.calls == 2
