"""An OBG-created game goes through the same channel/draft setup as the slash command."""
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

import config
from setup.GameLaunch import launch_game
from tests.fakes import FakeChannel, FakeRole
from webui.server import WebApp


class LaunchChannel(FakeChannel):
    @property
    def jump_url(self):
        return f"https://discord.test/{self.name}"

    async def create_thread(self, name, **kwargs):
        thread = FakeChannel(name)
        thread.jump_url = f"https://discord.test/{name}"
        self.threads.append(thread)
        return thread


class LaunchMember:
    def __init__(self, member_id, name):
        self.id = member_id
        self.display_name = name
        self.mention = f"<@{member_id}>"
        self.roles = []

    async def add_roles(self, role):
        self.roles.append(role)


class LaunchGuild:
    def __init__(self, members):
        self.members = {member_id: LaunchMember(member_id, name) for member_id, name in members.items()}
        self.default_role = FakeRole("@everyone")
        self.roles = [FakeRole("Observers")]
        self.categories = []
        self.channels = []

    async def create_category(self, name, overwrites=None):
        category = SimpleNamespace(name=name)
        self.categories.append(category)
        return category

    async def create_role(self, name, mentionable=False):
        role = FakeRole(name)
        self.roles.append(role)
        return role

    async def create_text_channel(self, name, category=None, overwrites=None):
        channel = LaunchChannel(name)
        self.channels.append(channel)
        return channel

    def get_member(self, member_id):
        return self.members.get(member_id)


def test_launch_game_creates_channels_and_records_players(games_dir, run):
    guild = LaunchGuild({11: "alice", 22: "bob"})
    players = [[11, "<@11>"], [22, "<@22>"]]

    result = run(launch_game(guild, "OBG game", players, 2,
                             display_names={"11": "alice", "22": "bob"},
                             members=guild.members))

    assert result["id"] == "aeb1"
    assert [channel.name for channel in guild.channels] == ["aeb1-OBG game", "aeb1-actions"]
    assert result["tabletalk_url"].endswith("/aeb1-OBG game")
    with open(games_dir / "aeb1.json") as handle:
        state = json.load(handle)
    assert state["players"]["11"]["username"] == "alice"
    assert state["players"]["22"]["username"] == "bob"
    actions = guild.channels[1]
    assert any("draft factions" in str(message[0]) for message in actions.sent)
    assert any(thread.name == "Faction Reference" for thread in actions.threads)


def _request(body, token=""):
    class Request:
        headers = {"X-OBG-Token": token} if token else {}

        async def json(self):
            return body

    return Request()


VALID_BODY = {
    "name": "OBG game",
    "players": [{"discord_id": "11", "name": "alice"}, {"discord_id": "22", "name": "bob"}],
    "player_count": 2,
}


def test_obg_endpoint_requires_the_shared_secret(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "obg_shared_secret", "secret")
    app = WebApp(None, str(tmp_path), bot=None)

    response = asyncio_run(app.api_obg_create_game(_request(VALID_BODY)))
    assert response.status == 401


def test_obg_endpoint_rejects_bad_settings(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "obg_shared_secret", "secret")
    app = WebApp(None, str(tmp_path), bot=None)
    body = dict(VALID_BODY)
    body["player_count"] = 3

    response = asyncio_run(app.api_obg_create_game(_request(body, "secret")))
    assert response.status == 400


def test_obg_endpoint_needs_a_guild(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "obg_shared_secret", "secret")
    app = WebApp(None, str(tmp_path), bot=None)

    response = asyncio_run(app.api_obg_create_game(_request(VALID_BODY, "secret")))
    assert response.status == 503


class MemberGuild:
    async def fetch_member(self, member_id):
        return SimpleNamespace(id=member_id)


class BotWithGuild:
    def __init__(self, guild):
        self.guild = guild

    def get_guild(self, guild_id):
        return self.guild


def test_obg_endpoint_calls_launch_with_the_guild_members(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "obg_shared_secret", "secret")
    monkeypatch.setattr(config, "guild_id", 1)
    guild = MemberGuild()
    app = WebApp(None, str(tmp_path), bot=BotWithGuild(guild))

    with patch("webui.server.launch_game", new=AsyncMock(return_value={
        "id": "aeb3", "tabletalk_url": "t", "actions_url": "a",
        "community_sheets": {}, "faction_thread": None, "drawing": None,
    })) as launch:
        response = asyncio_run(app.api_obg_create_game(_request(VALID_BODY, "secret")))

    assert response.status == 201
    args = launch.call_args
    assert args.args[0] is guild
    assert args.args[1] == "OBG game"
    assert args.args[2] == [[11, "<@11>"], [22, "<@22>"]]
    assert args.kwargs["members"]["11"].id == 11


def asyncio_run(coroutine):
    import asyncio
    return asyncio.run(coroutine)
