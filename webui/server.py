"""The HTTP surface of a game: list games, read the feed, press a button.

One process, one event loop with the bot, so `game_lock` still serialises presses
across both surfaces. See webui/README.md for the shape and the leftovers.
"""
import asyncio
import json
import logging
import os
import traceback

from aiohttp import web

import config
from Buttons.Turn import TurnButtons
from helpers.GamestateHelper import GamestateHelper
from helpers.GameIds import list_active_game_ids
from helpers.GameLock import game_lock
from listeners.ButtonListener import ButtonListener
from webui.render import render_board
from webui.store import FeedStore
from webui.transport import Surface, WebInteraction

LOG = logging.getLogger(__name__)
ROOT = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(ROOT, "static")


def _unmention(text, players):
    """`<@123>` reads badly in a browser; swap in the name the seat already has."""
    if not text:
        return text
    for player_id, stats in players.items():
        name = stats.get("username") or stats.get("color") or player_id
        text = text.replace(f"<@{player_id}>", name).replace(f"<@!{player_id}>", name)
    return text


class WebApp:
    def __init__(self, store, games_path, mirror=None, data_dir=None, guild_name=None):
        self.store = store
        self.games_path = games_path
        self.mirror = mirror
        data_dir = data_dir or os.path.join(ROOT, "data")
        self.media_dir = os.path.join(data_dir, "media")
        self.render_dir = os.path.join(data_dir, "renders")
        self.guild_name = guild_name
        self._snapshots = {}

    # -- state -----------------------------------------------------------
    def game(self, game_id):
        return GamestateHelper(None, game_id)

    def _version(self, game_id):
        path = os.path.join(self.games_path, f"{game_id}.json")
        stat = os.stat(path)
        return f"{stat.st_mtime_ns}-{stat.st_size}"

    def _parts(self, game_id, game):
        players = game.gamestate["players"]
        names = {pid: (stats.get("username") or stats.get("color") or pid)
                 for pid, stats in players.items()}
        colors = [stats.get("color") for stats in players.values() if stats.get("color")]
        return names, colors

    def _seat_player(self, game, seat):
        stats = game.gamestate["players"].get(str(seat))
        if stats is None:
            return None, None
        return str(seat), stats

    # -- payloads --------------------------------------------------------
    def snapshot(self, game_id, seat):
        version = self._version(game_id)
        feed_rev = self.store.rev(game_id)
        seat_requested = str(seat or "")
        cache_key = (game_id, seat_requested)
        stamp = (version, feed_rev)
        cached = self._snapshots.get(cache_key)
        if cached and cached[0] == stamp:
            return cached[1]

        game = self.game(game_id)
        players = game.gamestate["players"]
        names, colors = self._parts(game_id, game)
        seat, you = self._seat_player(game, seat_requested)
        active = game.gamestate.get("activePlayerColor", [])
        messages = []
        for row in self.store.visible_history(game_id, seat_requested, limit=80):
            # A press on a prompt posted before the feed existed leaves a stub record:
            # keep its id canonical, but show nothing.
            if row["deleted"] or not (row["content"] or row["buttons"] or row["attachments"]):
                continue
            messages.append({
                "id": row["id"],
                "room": row["room"],
                "content": _unmention(row["content"], players),
                "buttons": row["buttons"],
                "attachments": row["attachments"],
                "private": bool(row["ephemeral_to"]),
            })
        messages.reverse()

        payload = {
            "game": {
                "id": game_id,
                "round": game.gamestate.get("roundNum"),
                "active": active,
                "ended": bool(game.gamestate.get("gameEnded")),
                "players": [{
                    "id": pid,
                    "name": names[pid],
                    "color": stats.get("color"),
                    "passed": bool(stats.get("passed")),
                    "eliminated": bool(stats.get("eliminated")),
                    "money": stats.get("money"),
                    "science": stats.get("science"),
                    "materials": stats.get("materials"),
                    "influence_discs": stats.get("influence_discs"),
                    "is_you": pid == seat,
                } for pid, stats in players.items()],
            },
            "seat": seat_requested,
            "you": you and {
                "id": seat,
                "name": names.get(seat),
                "color": you.get("color"),
                "money": you.get("money"),
                "science": you.get("science"),
                "materials": you.get("materials"),
                "influence_discs": you.get("influence_discs"),
                "build_apt": you.get("build_apt"),
                "move_apt": you.get("move_apt"),
                "research_apt": you.get("research_apt"),
                "explore_apt": you.get("explore_apt"),
                "upgrade_apt": you.get("upgrade_apt"),
                "passed": bool(you.get("passed")),
                "is_your_turn": you.get("color") in active,
            },
            "mirror_to_discord": self.store.mirrors(game_id),
            "version": version,
            "board": f"/api/games/{game_id}/board.webp?v={version}",
            "messages": messages,
        }
        self._snapshots[cache_key] = (stamp, payload)
        return payload

    # -- handlers --------------------------------------------------------
    async def api_games(self, request):
        games = []
        for game_id in list_active_game_ids():
            try:
                game = self.game(game_id)
            except (OSError, ValueError):
                continue
            names, _colors = self._parts(game_id, game)
            games.append({
                "id": game_id,
                "round": game.gamestate.get("roundNum"),
                "active": game.gamestate.get("activePlayerColor", []),
                "players": [names[pid] for pid in game.gamestate["players"]],
            })
        return web.json_response({"games": games})

    async def api_view(self, request):
        game_id = request.match_info["game_id"]
        seat = request.query.get("seat") or ""
        try:
            payload = self.snapshot(game_id, seat)
        except FileNotFoundError:
            return web.json_response({"error": "unknown game", "game": game_id}, status=404)
        return web.json_response(payload)

    async def api_press(self, request):
        game_id = request.match_info["game_id"]
        try:
            body = await request.json()
        except json.JSONDecodeError:
            return web.json_response({"error": "invalid json"}, status=400)
        seat = str(body.get("seat") or "")
        custom_id = str(body.get("custom_id") or "")
        message_id = body.get("message_id")
        if not seat or not custom_id or message_id is None:
            return web.json_response({"error": "seat, custom_id and message_id are required"}, status=400)
        try:
            int(message_id)
        except (TypeError, ValueError):
            return web.json_response({"error": "message_id must be a number"}, status=400)

        error = None
        async with game_lock(game_id):
            try:
                game = self.game(game_id)
                names, colors = self._parts(game_id, game)
                interaction = WebInteraction(
                    self.store, game_id, seat, custom_id=custom_id, message_id=int(message_id),
                    members={"names": names, "colors": colors}, display_name=names.get(seat),
                    mirror=self.mirror, media_dir=self.media_dir)
                await ButtonListener(None).resolveButton(interaction)
            except Exception as exc:  # the Discord cog reports these to #bot-log; we answer the browser
                LOG.error("press failed: %s\n%s", exc, traceback.format_exc())
                error = f"{type(exc).__name__}: {exc}"

        payload = self.snapshot(game_id, seat)
        payload["error"] = error
        return web.json_response(payload)

    async def api_turn_menu(self, request):
        """Recovery: post the start-of-turn buttons when a player has no prompt open."""
        game_id = request.match_info["game_id"]
        seat = str(request.query.get("seat") or "")
        game = self.game(game_id)
        session, player = self._seat_player(game, seat)
        if player is None:
            return web.json_response({"error": "not a player in this game"}, status=403)
        view = TurnButtons.getStartTurnButtons(game, player, player["color"])
        names, colors = self._parts(game_id, game)
        surface = Surface(self.store, game_id, seat=seat, mirror=self.mirror,
                          media_dir=self.media_dir)
        await surface.channel.send(f"{names.get(seat, player['color'])}, use buttons to do your turn",
                                   view=view)
        return web.json_response(self.snapshot(game_id, seat))

    async def api_mirror(self, request):
        game_id = request.match_info["game_id"]
        body = await request.json()
        self.store.set_mirror(game_id, bool(body.get("mirror_to_discord")))
        return web.json_response(self.snapshot(game_id, str(body.get("seat") or "")))

    async def api_board(self, request):
        game_id = request.match_info["game_id"]
        try:
            path, key = await asyncio.to_thread(render_board, self.games_path, game_id, self.render_dir)
        except FileNotFoundError:
            return web.json_response({"error": "unknown game"}, status=404)
        response = web.FileResponse(path)
        response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        response.headers["X-Board-Key"] = key
        return response

    async def api_media(self, request):
        try:
            message_id = int(request.match_info["message_id"])
        except ValueError:
            return web.json_response({"error": "bad media id"}, status=400)
        name = os.path.basename(request.match_info["name"])
        path = os.path.join(self.media_dir, str(message_id), name)
        if not os.path.isfile(path):
            return web.json_response({"error": "no such media"}, status=404)
        return web.FileResponse(path)

    async def index(self, request):
        return web.FileResponse(os.path.join(STATIC_DIR, "index.html"))

    # -- wiring ----------------------------------------------------------
    def create_app(self):
        app = web.Application()
        app.router.add_get("/", self.index)
        app.router.add_get("/api/games", self.api_games)
        app.router.add_get("/api/games/{game_id}/view", self.api_view)
        app.router.add_post("/api/games/{game_id}/press", self.api_press)
        app.router.add_post("/api/games/{game_id}/turn-menu", self.api_turn_menu)
        app.router.add_post("/api/games/{game_id}/mirror", self.api_mirror)
        app.router.add_get("/api/games/{game_id}/board.webp", self.api_board)
        app.router.add_get("/api/media/{message_id}/{name}", self.api_media)
        app.router.add_static("/static", STATIC_DIR)
        return app


def build(store=None, games_path=None, mirror=None, data_dir=None):
    games_path = games_path or config.gamestate_path
    if store is None:
        store = FeedStore(os.path.join(data_dir or os.path.join(ROOT, "data"), "webui.sqlite3"))
    return WebApp(store, games_path, mirror=mirror, data_dir=data_dir)


async def start(port, store=None, games_path=None, mirror=None, host="127.0.0.1"):
    """Start the server on the current event loop (the bot's). Returns the runner."""
    app = build(store=store, games_path=games_path, mirror=mirror).create_app()
    runner = web.AppRunner(app)
    await runner.setup()
    await web.TCPSite(runner, host, port).start()
    LOG.info("web ui listening on http://%s:%s", host, port)
    return runner


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    # Dev: point at a copy of the save folder so real games are never written.
    games_path = os.environ.get("WEBUI_GAMESTATE_PATH", config.gamestate_path)
    port = int(os.environ.get("WEBUI_PORT", "8099"))
    app = build(games_path=games_path).create_app()
    web.run_app(app, host=os.environ.get("WEBUI_HOST", "127.0.0.1"), port=port)
