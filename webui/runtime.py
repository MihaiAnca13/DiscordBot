"""Process-wide wiring between the bot and the web ui.

The web server must run on the bot's event loop: `helpers/GameLock` is an
in-process asyncio lock, and the save files are written by this process alone.
"""
import logging
import os
import re

import config
from webui.mirror import DiscordMirror
from webui.store import FeedStore

LOG = logging.getLogger(__name__)
ROOT = os.path.dirname(os.path.abspath(__file__))

store = None
mirror = None
_runners = []

GAME_CHANNEL = re.compile(r"^(aeb\d+)")


def game_id_of(channel):
    """Games are keyed by channel name: `aeb17-actions`, `aeb17-Round 3, Tile 201, Combat`."""
    name = getattr(channel, "name", "") or ""
    match = GAME_CHANNEL.match(name)
    return match.group(1) if match else None


def record(interaction):
    """Wrap a Discord interaction so the handlers' messages land in the feed."""
    if store is None:
        return interaction
    game_id = game_id_of(getattr(interaction, "channel", None))
    if game_id is None:
        return interaction
    store.ensure_game(game_id)
    from webui.transport import RecordingInteraction
    return RecordingInteraction(interaction, store, game_id, mirror=mirror)


def record_channel(channel, game_id):
    """Record setup prompts created before the first Discord button interaction."""
    if store is None:
        return channel
    from webui.transport import RecordingChannel, Surface
    return RecordingChannel(channel, Surface(store, game_id))


async def start_webui(bot):
    global store, mirror
    port = getattr(config, "webui_port", 0)
    if not port:
        return
    from webui.server import start
    store = FeedStore(os.path.join(ROOT, "data", "webui.sqlite3"))
    mirror = DiscordMirror(bot, getattr(config, "guild_id", 0), store, os.path.join(ROOT, "data", "media"))
    mirror.start()
    runner = await start(port, store=store, mirror=mirror,
                         host=getattr(config, "webui_host", "127.0.0.1"), bot=bot)
    _runners.append(runner)
    LOG.info("web ui started on port %s", port)


async def stop_webui():
    for runner in _runners:
        await runner.cleanup()
    _runners.clear()
    if mirror is not None:
        await mirror.close()
