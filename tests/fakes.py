"""Reusable test doubles and builders shared by the test suite.

Discord is never available in tests, so interaction, channel, guild and message
objects are stubbed here. Anything that is a plain helper rather than a pytest
fixture belongs in this module; fixtures live in conftest.py.
"""
import copy
import json
from datetime import datetime, timezone

from helpers.GamestateHelper import GamestateHelper
from helpers.PlayerHelper import PlayerHelper

FACTIONS = json.load(open("data/factions.json"))
POS = "101"  # the sector board_tile() builds by default


class FakeMessage:
    _next_id = 1

    def __init__(self):
        self.id = FakeMessage._next_id
        FakeMessage._next_id += 1
        self.components = []

    async def delete(self):
        pass

    async def edit(self, **kwargs):
        self.edited = kwargs


class FakeChannel:
    def __init__(self, name="aeb1-actions"):
        self.name = name
        self.threads = []
        self.sent = []

    async def send(self, content=None, **kwargs):
        self.sent.append((content, kwargs))
        return FakeMessage()


class FakeUser:
    name = "tester"
    mention = "<@tester>"
    id = 195677939050872832
    display_name = "tester"


class FakeRole:
    def __init__(self, name):
        self.name = name
        self.mention = f"<@&{name}>"


class FakeGuild:
    emojis = []
    channels = []

    def __init__(self, role_names=()):
        self.roles = [FakeRole(n) for n in role_names]

    def get_member(self, _id):
        return None


class FakeResponder:
    """Stands in for interaction.response / interaction.followup; records sends."""

    def __init__(self):
        self.sent = []

    async def defer(self, **kwargs):
        pass

    async def send(self, content=None, **kwargs):
        self.sent.append((content, kwargs))

    send_message = send


class FakeInteraction:
    def __init__(self, channel=None, custom_id=None, user_id=None, role_names=(), message=None):
        self.channel = channel or FakeChannel()
        self.user = FakeUser()
        if user_id is not None:
            self.user.id = user_id
        self.guild = FakeGuild(role_names)
        self.message = message or FakeMessage()
        self.data = {"custom_id": custom_id}
        self.created_at = datetime.now(timezone.utc)
        self.response = FakeResponder()
        self.followup = FakeResponder()


class FakeGame:
    """Stand-in for the draft/setup code paths: only the gamestate keys they read."""

    def __init__(self, community_factions, community_mode):
        self.gamestate = {
            "community_factions": community_factions,
            "communityMode": community_mode,
            "bannedFactions": [],
            "draftedFactions": [],
        }

    getShortFactionNameFromFull = GamestateHelper.getShortFactionNameFromFull


def player_stats(faction, **overrides):
    """A faction's stats with the colour/identity fields the bot fills in at setup."""
    stats = copy.deepcopy(FACTIONS[faction])
    color = overrides.pop("color", "blue")
    stats.update({
        "player_name": color,
        "username": color,
        "color": color,
        "military_tech": [],
        "grid_tech": [],
        "nano_tech": [],
        "ancient_parts": [],
    })
    stats.update(overrides)
    return stats


def players(*colors):
    """A gamestate players dict with one Hydran Progress per colour."""
    return {str(i): player_stats("hyd", color=color) for i, color in enumerate(colors, 1)}


def board_tile(ships=(), owner=0, sector=int(POS), **extra):
    """A board dict holding one sector, keyed the way the gamestate keys it."""
    tile = {"owner": owner, "sector": sector, "disctile": 0, "player_ships": list(ships)}
    tile.update(extra)
    return {str(sector): tile}


def player_helper(game, color):
    """A PlayerHelper for the player with this colour."""
    return PlayerHelper(game.get_player_from_color(color), game.getPlayerObjectFromColor(color))


def offered_buttons(interaction):
    """Every button offered across the messages the fake channel received."""
    return [child for _content, kwargs in interaction.channel.sent
            for child in getattr(kwargs.get("view"), "children", [])]


def offered_labels(interaction):
    """Button labels offered across every message the fake channel received."""
    return [getattr(button, "label", None) for button in offered_buttons(interaction)]


def offered_ids(interaction):
    """Button custom_ids offered across every message the fake channel received."""
    return [getattr(button, "custom_id", None) for button in offered_buttons(interaction)]


def buttons(channel):
    """custom_id -> label for every button in the most recent message that has any."""
    for _content, kwargs in reversed(channel.sent):
        children = getattr(kwargs.get("view"), "children", [])
        if children:
            return {c.custom_id: c.label for c in children}
    return {}


def reload(game):
    """Re-read a game from disk: what the next button press will see."""
    return type(game)(None, game.game_id)
