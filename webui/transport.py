"""Two surfaces, one interaction.

The engine (Buttons/, helpers/) only ever sees something shaped like a Discord
interaction: `.channel.send(...)`, `.followup.send(...)`, `.message.delete()`,
`.message.edit(...)`, `.user`, `.guild`. The tests already exploit that with a
fake; this module is the same trick, production grade.

- `WebInteraction` answers an HTTP press and writes to the feed.
- `RecordingInteraction` wraps a real Discord interaction and write-through
  records every message it posts, so the web feed shows Discord prompts too.

Nothing here changes game rules. If a handler uses a Discord attribute neither
class knows, the press fails loudly instead of silently doing nothing.
"""
import os
from datetime import datetime, timezone
from types import SimpleNamespace

import discord

from webui.store import buttons_from_view


# --------------------------------------------------------------------------
# payload helpers
# --------------------------------------------------------------------------
def file_bytes(file):
    """The bytes behind a discord.File, without letting a re-send reuse the pointer."""
    fp = getattr(file, "fp", None)
    if fp is None:
        return b""
    try:
        fp.seek(0)
    except (AttributeError, OSError, ValueError):
        pass
    return fp.read()


def collect_files(file=None, files=None):
    """[(filename, bytes)] for whatever the handler passed as file=/files=."""
    given = []
    if file is not None:
        given.append(file)
    if files:
        given.extend(files)
    out = []
    for item in given:
        name = getattr(item, "filename", "image.webp")
        out.append((name, file_bytes(item)))
    return out


def save_media(media_dir, message_id, files):
    """Write the bytes beside the feed record and return browser-facing entries."""
    if not files:
        return []
    folder = os.path.join(media_dir, str(message_id))
    os.makedirs(folder, exist_ok=True)
    entries = []
    for name, data in files:
        safe = os.path.basename(name) or "file.bin"
        with open(os.path.join(folder, safe), "wb") as handle:
            handle.write(data)
        entries.append({"name": safe, "url": f"/api/media/{message_id}/{safe}"})
    return entries


class _ButtonRow:
    """Enough of a discord component row for the handlers that inspect children."""

    def __init__(self, buttons):
        self.children = [SimpleNamespace(label=b["label"], custom_id=b["custom_id"],
                                         disabled=b["disabled"], url=b["url"])
                         for b in buttons]


class _Flags:
    def __init__(self, ephemeral):
        self.ephemeral = ephemeral


class _NotFoundResponse:
    status = 404
    reason = "Not Found"


def not_found():
    return discord.NotFound(_NotFoundResponse(), "Unknown Message")


class _Role:
    def __init__(self, name):
        self.name = name
        self.mention = f"<@&{name}>"


class _Member:
    def __init__(self, display_name, roles=()):
        self.display_name = display_name
        self.roles = list(roles)
        self.mention = f"<@{display_name}>"


class WebUser:
    def __init__(self, seat, display_name=None):
        self.id = seat
        self.name = display_name or seat
        self.display_name = self.name
        self.mention = f"<@{seat}>"


class WebGuild:
    """Roles exist only so community-mode colour matching keeps working."""

    emojis = []
    channels = []
    categories = []
    default_role = _Role("@everyone")

    def __init__(self, game_id, members, colors):
        self._members = members
        self.roles = [_Role(color) for color in colors] + [_Role(game_id)]

    def get_member(self, user_id):
        name = self._members.get(str(user_id))
        if name is None:
            return _Member(str(user_id), roles=[])
        return _Member(name, roles=[])


# --------------------------------------------------------------------------
# the web surface
# --------------------------------------------------------------------------
class WebResponder:
    """Stands in for interaction.response / interaction.followup."""

    def __init__(self, surface, ephemeral):
        self.surface = surface
        self.ephemeral = ephemeral

    async def defer(self, *args, **kwargs):
        return None

    async def send(self, content=None, view=None, file=None, files=None, ephemeral=False):
        private = ephemeral or self.ephemeral
        return await self.surface.send(content, view=view, file=file, files=files,
                                       ephemeral_to=self.surface.seat if private else None)

    send_message = send


class WebMessage:
    def __init__(self, surface, message_id):
        self.surface = surface
        self.id = message_id

    def _row(self):
        return self.surface.store.get(self.id)

    @property
    def flags(self):
        row = self._row()
        return _Flags(bool(row and row["ephemeral_to"]))

    @property
    def components(self):
        row = self._row()
        return [_ButtonRow(row["buttons"])] if row and row["buttons"] else []

    @property
    def jump_url(self):
        return f"/game/{self.surface.game_id}/message/{self.id}"

    @property
    def attachments(self):
        row = self._row()
        return [SimpleNamespace(url=a["url"], filename=a["name"]) for a in (row["attachments"] if row else [])]

    async def delete(self):
        row = self._row()
        if row is None or row["deleted"]:
            raise not_found()
        await self.surface.mirror_delete(row)
        self.surface.store.remove(self.id)

    async def edit(self, content=None, view=None, **kwargs):
        buttons = buttons_from_view(view) if view is not None else None
        self.surface.store.update(self.id, content=content, buttons=buttons)
        await self.surface.mirror_edit(self.id, content, view)

    async def create_thread(self, name):
        return await self.surface.thread(name)


class WebChannel:
    def __init__(self, surface, name=None):
        self.surface = surface
        self.name = name or f"{surface.game_id}-actions"
        self.id = self.name
        self.threads = []
        self.category = SimpleNamespace(name="web")

    async def edit(self, **kwargs):
        return None

    async def send(self, content=None, view=None, file=None, files=None, ephemeral_to=None,
                   **kwargs):
        return await self.surface.send(content, view=view, file=file, files=files,
                                       ephemeral_to=ephemeral_to, room=self.name)

    async def fetch_message(self, message_id):
        """Only the feed is authoritative: a deleted prompt is gone for every surface."""
        row = self.surface.store.get(int(message_id))
        if row is None or row["deleted"]:
            raise not_found()
        return WebMessage(self.surface, int(message_id))


class Surface:
    """Shared writing path for both surfaces: feed first, then the Discord mirror."""

    def __init__(self, store, game_id, seat=None, mirror=None, media_dir=None, channel_name=None):
        self.store = store
        self.game_id = game_id
        self.seat = None if seat is None else str(seat)
        self.mirror = mirror
        self.media_dir = media_dir
        self.ephemeral_to = None
        self.channel = WebChannel(self, name=channel_name or f"{game_id}-actions")

    def _mirrors(self):
        return self.mirror is not None and self.store.mirrors(self.game_id)

    async def send(self, content, view=None, file=None, files=None, ephemeral_to=None, room=None):
        room = room or self.channel.name
        payload = collect_files(file, files)
        message_id = self.store.record(
            self.game_id, room, content=content,
            buttons=buttons_from_view(view) if view is not None else [],
            ephemeral_to=None if ephemeral_to is None else str(ephemeral_to),
            author_id=self.seat)
        attachments = save_media(self.media_dir, message_id, payload) if self.media_dir else []
        if attachments:
            self.store.update(message_id, attachments=attachments)
        if payload and self._mirrors() and ephemeral_to is None:
            mirrored = await self.mirror.send(self.game_id, room, content, view, payload)
            if mirrored:
                self.store.attach_discord(message_id, mirrored["discord_id"], room)
                if mirrored.get("attachments"):
                    self.store.update(message_id, attachments=mirrored["attachments"])
        return WebMessage(self, message_id)

    async def mirror_delete(self, row):
        if row["discord_id"] and self._mirrors():
            await self.mirror.delete(row["room"], row["discord_id"])

    async def mirror_edit(self, message_id, content, view):
        row = self.store.get(message_id)
        if row and row["discord_id"] and self._mirrors():
            await self.mirror.edit(row["room"], row["discord_id"], content, view)

    async def thread(self, name):
        """Threads are feed rooms on the web; Discord threads are not mirrored in day 1."""
        channel = WebChannel(self, name=name)
        self.channel.threads.append(channel)
        return channel


class WebInteraction:
    """A press that arrived over HTTP, shaped exactly like the Discord object handlers expect."""

    def __init__(self, store, game_id, seat, custom_id=None, message_id=None, members=None,
                 display_name=None, mirror=None, media_dir=None):
        self.store = store
        self.game_id = game_id
        self.surface = Surface(store, game_id, seat=seat, mirror=mirror, media_dir=media_dir)
        self.channel = self.surface.channel
        self.message = WebMessage(self.surface, int(message_id)) if message_id is not None else None
        self.user = WebUser(str(seat), display_name)
        colors = list((members or {}).get("colors", []))
        self.guild = WebGuild(game_id, (members or {}).get("names", {}), colors)
        self.response = WebResponder(self.surface, ephemeral=False)
        self.followup = WebResponder(self.surface, ephemeral=True)
        self.data = {"custom_id": custom_id}
        self.created_at = datetime.now(timezone.utc)
        self.type = discord.InteractionType.component


# --------------------------------------------------------------------------
# the Discord surface: same feed, real messages
# --------------------------------------------------------------------------
class RecordingMessage:
    def __init__(self, real, surface, message_id):
        self._real = real
        self.surface = surface
        self.id = message_id

    def __getattr__(self, name):
        return getattr(self._real, name)

    async def delete(self):
        # The real Discord message is already the mirror, so no fan-out here.
        self.surface.store.remove(self.id)
        await self._real.delete()

    async def edit(self, content=None, view=None, **kwargs):
        buttons = buttons_from_view(view) if view is not None else None
        self.surface.store.update(self.id, content=content, buttons=buttons)
        await self._real.edit(content=content, view=view, **kwargs)


class RecordingChannel:
    def __init__(self, real, surface):
        self._real = real
        self.surface = surface

    def __getattr__(self, name):
        return getattr(self._real, name)

    async def send(self, content=None, view=None, file=None, files=None, **kwargs):
        real = await self._real.send(content=content, view=view, file=file, files=files, **kwargs)
        attachments = [{"name": a.filename, "url": a.url} for a in getattr(real, "attachments", [])]
        message_id = self.surface.store.record(
            self.surface.game_id, getattr(self._real, "name", "discord"), content=content,
            buttons=buttons_from_view(view) if view is not None else [],
            attachments=attachments,
            ephemeral_to=self.surface.ephemeral_to,
            author_id=self.surface.seat,
            discord_id=real.id)
        return RecordingMessage(real, self.surface, message_id)

    async def fetch_message(self, message_id):
        """Canonical id in, canonical id out; deletion is the feed's answer, not Discord's."""
        row = self.surface.store.get(int(message_id))
        if row is None or row["deleted"]:
            raise not_found()
        return RecordingMessage(SimpleNamespace(id=message_id), self.surface, int(message_id))


class RecordingResponder:
    def __init__(self, real, surface, ephemeral):
        self._real = real
        self.surface = surface
        self.ephemeral = ephemeral

    def __getattr__(self, name):
        return getattr(self._real, name)

    async def defer(self, *args, **kwargs):
        return await self._real.defer(*args, **kwargs)

    async def send(self, content=None, view=None, file=None, files=None, ephemeral=False, **kwargs):
        real = await self._real.send(content=content, view=view, file=file, files=files,
                                     ephemeral=ephemeral, **kwargs)
        attachments = [{"name": a.filename, "url": a.url} for a in getattr(real, "attachments", [])]
        self.surface.ephemeral_to = self.surface.seat if (ephemeral or self.ephemeral) else None
        self.surface.store.record(
            self.surface.game_id, "private", content=content,
            buttons=buttons_from_view(view) if view is not None else [],
            attachments=attachments,
            ephemeral_to=self.surface.ephemeral_to,
            author_id=self.surface.seat)
        return real

    send_message = send


class RecordingInteraction:
    """A real Discord interaction that write-through records what the handlers post."""

    def __init__(self, interaction, store, game_id, mirror=None):
        self._interaction = interaction
        self.surface = Surface(store, game_id, seat=str(getattr(interaction.user, "id", "")),
                               mirror=mirror)
        self.channel = RecordingChannel(interaction.channel, self.surface)
        self.surface.channel = self.channel
        self.followup = RecordingResponder(interaction.followup, self.surface, ephemeral=True)
        self.response = RecordingResponder(interaction.response, self.surface, ephemeral=False)
        self.message = self._wrap_message(interaction.message)

    def _wrap_message(self, real):
        row = self.surface.store.by_discord_id(self.surface.game_id, real.id)
        room = getattr(getattr(real, "channel", None), "name", "discord")
        message_id = row["id"] if row else self.surface.store.record(
            self.surface.game_id, room, buttons=[], discord_id=real.id)
        return RecordingMessage(real, self.surface, message_id)

    def __getattr__(self, name):
        return getattr(self._interaction, name)
