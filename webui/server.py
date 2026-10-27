"""The HTTP surface of a game: list games, read the feed, press a button.

One process, one event loop with the bot, so `game_lock` still serialises presses
across both surfaces. See webui/README.md for the shape and the leftovers.
"""
import asyncio
import json
import logging
import os
import re
import traceback

from aiohttp import web

import config
from Buttons.Research import ResearchButtons
from Buttons.Turn import TurnButtons
from helpers.DrawHelper import DrawHelper
from helpers.GamestateHelper import GamestateHelper
from helpers.GameIds import list_active_game_ids
from helpers.GameLock import game_lock
from helpers.ImageCache import ImageCacheHelper
from helpers.PlayerHelper import PlayerHelper
from helpers.ShipHelper import PlayerShip
from listeners.ButtonListener import ButtonListener
from webui import catalog
from webui.render import board_meta, render_board
from webui.store import FeedStore
from webui.transport import Surface, WebInteraction

LOG = logging.getLogger(__name__)
ROOT = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(ROOT, "static")
ART_DIR = os.path.join(os.path.dirname(ROOT), "images", "resources")

SHIPS = ("interceptor", "cruiser", "dreadnought", "starbase")


async def prepare_images(app):
    # Match bot startup: no request may see a partially populated image cache.
    await asyncio.to_thread(ImageCacheHelper, "images/resources")


def _clean_name(text):
    """Drop Discord emoji glyphs from a username: the browser has no custom emoji set."""
    return re.sub(r"<a?:[^:>]+:\d+>", "", text or "").strip() or text


def _unmention(text, players):
    """`<@123>` reads badly in a browser; swap in the name the seat already has."""
    if not text:
        return text
    for player_id, stats in players.items():
        name = _clean_name(stats.get("username") or stats.get("color") or player_id)
        text = text.replace(f"<@{player_id}>", name).replace(f"<@!{player_id}>", name)
    text = re.sub(r"<@&\w+>\s*", "", text)
    return re.sub(r"[ \t]+$", "", text, flags=re.MULTILINE)


def _message(row, players, seat=None, color=None):
    """One feed record, shaped for both the action dock and the history view."""
    deleted = bool(row["deleted"])
    buttons = [] if deleted else row["buttons"]
    # A public prompt can belong to another seat (their turn menu). Keep only the
    # buttons this seat may press; a prompt with nothing of its own is not a choice.
    pressable = []
    dummy = []
    own = False
    other = False
    public_action = False
    dummy_action = False
    public_nav = {"showGame", "showReputation", "undoLastTurn", "refreshImage", "removeUnits"}
    for button in buttons:
        custom_id = button.get("custom_id") or ""
        if custom_id.startswith("FCID"):
            seat_color = custom_id.split("_")[0].replace("FCID", "")
            action = custom_id.split("_", 1)[1] if "_" in custom_id else custom_id
            if seat_color == "dummy":
                dummy.append(button)
                dummy_action = dummy_action or action not in public_nav
            elif color and seat_color == color:
                own = True
                pressable.append(button)
            else:
                other = True
        else:
            pressable.append(button)
            public_action = public_action or custom_id not in public_nav
    for_you = own or (not other and (public_action or dummy_action))
    if for_you:
        pressable.extend(dummy)
    buttons = pressable
    return {
        "id": row["id"],
        "room": row["room"],
        "content": _unmention(row["content"], players),
        "buttons": buttons,
        "attachments": row["attachments"],
        "private": bool(row["ephemeral_to"]),
        "deleted": deleted,
        "created": row["created_at"],
        "actionable": bool(buttons and for_you),
        "for_you": bool(for_you),
    }


def _blueprint(player, ship):
    parts = player.get(f"{ship}_parts")
    if not parts:
        return None
    stats = {}
    try:
        ship_object = PlayerShip(player, ship)
        stats = {"range": ship_object.getRange(), "speed": ship_object.speed,
                 "energy": ship_object.energy, "computer": ship_object.computer,
                 "shield": ship_object.shield, "hull": ship_object.hull,
                 "cost": ship_object.cost, "jump": ship_object.getJumpDrive()}
    except Exception as exc:  # a part combination that is mid-change in the save
        LOG.debug("cannot compute %s blueprint for %s: %s", ship, player.get("color"), exc)
    return {
        "ship": ship,
        "image": catalog.art_url(f"components/layouts/blueprints/blueprint_{ship}.png"),
        "stats": stats,
        "slots": [{"index": index, "part": catalog.part(part_id)}
                  for index, part_id in enumerate(parts)],
    }


def player_state(game, seat, pid, stats):
    board = game.gamestate["board"]
    color = stats.get("color")
    player_helper = PlayerHelper(pid, stats)
    techs = {}
    for track in ("military", "grid", "nano"):
        techs[track] = [catalog.tech(tech_id) for tech_id in stats.get(f"{track}_tech", [])]
    faction = catalog.by_name(stats.get("name"))
    try:
        points = DrawHelper(game.gamestate).get_public_points(stats, False)
    except Exception:
        points = None
    try:
        income = {"money": player_helper.money_income(),
                  "science": player_helper.science_income(),
                  "materials": player_helper.materials_income()}
        upkeep = player_helper.upkeepCosts()
    except Exception:
        income, upkeep = {}, None
    owned = []
    for position in stats.get("owned_tiles", []):
        tile = board.get(position, {})
        owned.append({"position": position, "name": tile.get("name") or tile.get("sector") or position,
                      "ring": tile.get("ring"), "ships": tile.get("player_ships", [])})
    return {
        "id": pid,
        "name": _clean_name(stats.get("username") or stats.get("name") or pid),
        "faction_name": stats.get("name"),
        "color": color,
        "artwork": (faction or {}).get("artwork") or color,
        "portrait": catalog.art_url(f"components/layouts/factionImages/{stats.get('artwork', color)}_image.png"),
        "faction": faction,
        "eliminated": bool(stats.get("eliminated")),
        "passed": bool(stats.get("passed")),
        "perma_passed": bool(stats.get("perma_passed")),
        "is_you": pid == seat,
        "money": stats.get("money"), "science": stats.get("science"),
        "materials": stats.get("materials"),
        "influence_discs": stats.get("influence_discs"),
        "colony_ships": stats.get("colony_ships"),
        "trade_value": stats.get("trade_value"),
        "points": points,
        "actions": {action: stats.get(f"{action}_apt") for action in
                    ("explore", "research", "build", "upgrade", "move", "influence")},
        "counters": {action: stats.get(f"{action}_action_counters") for action in
                     ("explore", "research", "build", "upgrade", "move", "influence")},
        "income": income,
        "upkeep": upkeep,
        "techs": techs,
        "reputation": stats.get("reputation_track", []),
        "blueprints": [blueprint for blueprint in
                       (_blueprint(stats, ship) for ship in SHIPS) if blueprint],
        "ship_stock": stats.get("ship_stock", []),
        "owned_tiles": owned,
        "home_planet": stats.get("home_planet"),
        "disc_tiles": stats.get("disc_tiles_for_points"),
        "last_action": stats.get("lastAction"),
        "last_action_detail": stats.get("detailsOfLastAction"),
    }


def _button_color(button):
    custom_id = button.get("custom_id") or ""
    if not custom_id.startswith("FCID"):
        return None
    color = custom_id.split("_")[0].replace("FCID", "")
    return None if color == "dummy" else color


def _is_turn_menu(message):
    return any((button.get("custom_id") or "").endswith("_startExplore")
               for button in message["buttons"])


def _is_phase_prompt(message):
    """All-passed / ready-for-upkeep prompts stop being current once a newer
    prompt exists (usually the next round's turn menu or a bankruptcy check)."""
    content = (message["content"] or "").lower()
    if "all players have passed" in content:
        return True
    return any((button.get("custom_id") or "") in ("runUpkeep", "readyForUpkeep")
               or (button.get("custom_id") or "").endswith(("_runUpkeep", "_readyForUpkeep"))
               for button in message["buttons"])


def _is_standing(message):
    """A private reaction-pass offer sits beside the turn menu, not instead of it."""
    return any((button.get("custom_id") or "") == "permanentlyPass"
               for button in message["buttons"])


def _current_prompts(pending):
    if not pending:
        return pending
    superseding = [message for message in pending
                   if _is_phase_prompt(message) or not _is_standing(message)]
    newest = max((message["id"] for message in superseding), default=0)
    return [message for message in pending
            if not ((_is_turn_menu(message) or _is_phase_prompt(message))
                    and not _is_standing(message) and message["id"] < newest)]


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
        self._geometry = {}

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

    def _board(self, game_id, version):
        cached = self._geometry.get(game_id)
        if cached and cached[0] == version:
            return cached[1]
        meta = board_meta(self.games_path, game_id)
        self._geometry[game_id] = (version, meta)
        return meta

    def _tech_market(self, game, seat_stats):
        market = []
        for tech_id in game.gamestate.get("available_techs", []):
            entry = catalog.tech(tech_id)
            if seat_stats is not None:
                try:
                    details = catalog.TECHS.get(tech_id, {})
                    entry["your_cost"] = ResearchButtons.calculate_cost(
                        details, details.get("track", "any"), seat_stats)
                except Exception:
                    entry["your_cost"] = entry["cost"]
            market.append(entry)
        return market

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
        you_color = (you or {}).get("color")

        pending = [_message(row, players, seat_requested, you_color)
                   for row in self.store.pending_messages(game_id, seat_requested)]
        pending = [message for message in pending
                   if message["actionable"] and seat_requested]
        pending = _current_prompts(pending)
        history, history_more = self.store.history_page(game_id, seat_requested, limit=40)
        history = [_message(row, players, seat_requested, you_color) for row in history]
        # Compatibility: the flat recent feed the day-1 page and its checks read.
        messages = [_message(row, players, seat_requested, you_color) for row in
                    self.store.visible_history(game_id, seat_requested, limit=80)
                    if not row["deleted"] and (row["content"] or row["buttons"] or row["attachments"])]
        messages.reverse()

        ended = bool(game.gamestate.get("gameEnded"))
        if ended:
            pending = []

        player_rows = [player_state(game, seat, pid, stats) for pid, stats in players.items()]
        you_row = next((row for row in player_rows if row["is_you"]), None)
        payload = {
            "game": {
                "id": game_id,
                "round": game.gamestate.get("roundNum"),
                "round_max": 8,
                "active": active,
                "ended": bool(game.gamestate.get("gameEnded")),
                "players": [{
                    "id": row["id"], "name": row["name"], "color": row["color"],
                    "faction_name": row["faction_name"], "artwork": row["artwork"],
                    "portrait": row["portrait"], "passed": row["passed"],
                    "eliminated": row["eliminated"], "money": row["money"],
                    "science": row["science"], "materials": row["materials"],
                    "influence_discs": row["influence_discs"], "points": row["points"],
                    "actions": row["actions"], "techs": row["techs"],
                    "blueprints": row["blueprints"], "income": row["income"],
                    "upkeep": row["upkeep"], "trade_value": row["trade_value"],
                    "colony_ships": row["colony_ships"], "reputation": row["reputation"],
                    "ship_stock": row["ship_stock"], "owned_tiles": row["owned_tiles"],
                    "faction": row["faction"], "is_you": row["is_you"],
                    "disc_tiles": row["disc_tiles"],
                    "last_action": row["last_action"],
                    "last_action_detail": row["last_action_detail"],
                } for row in player_rows],
            },
            "seat": seat_requested,
            "you": you_row and {
                "id": you_row["id"],
                "name": you_row["name"],
                "color": you_row["color"],
                "faction_name": you_row["faction_name"],
                "money": you_row["money"],
                "science": you_row["science"],
                "materials": you_row["materials"],
                "influence_discs": you_row["influence_discs"],
                "actions": you_row["actions"],
                "income": you_row["income"],
                "upkeep": you_row["upkeep"],
                "points": you_row["points"],
                "trade_value": you_row["trade_value"],
                "colony_ships": you_row["colony_ships"],
                "faction": you_row["faction"],
                "passed": you_row["passed"],
                "is_your_turn": you_row["color"] in active,
            },
            "mirror_to_discord": self.store.mirrors(game_id),
            "version": version,
            "board": f"/api/games/{game_id}/board.webp?v={version}",
            "board_meta": self._board(game_id, version),
            "tech_market": self._tech_market(game, you),
            "result": sorted(
                [{"id": row["id"], "name": row["name"], "color": row["color"],
                  "faction_name": row["faction_name"], "points": row["points"]}
                 for row in player_rows],
                key=lambda row: (row["points"] is None, -(row["points"] or 0))),
            "pending": pending,
            "history": history,
            "history_more": history_more,
            "messages": messages,
        }
        self._snapshots[cache_key] = (stamp, payload)
        return payload

    def _retire_combat_rolls(self, game_id, room, color):
        """A combat overview keeps offering rolls after that player rolled.

        The engine answers a roll with a newer prompt; the old roll button must
        not be able to roll the same ships again. Only that colour's roll buttons
        are retired, so the other side's shortcut stays usable.
        """
        if not color or ("combat" not in (room or "").lower()
                         and "bombing" not in (room or "").lower()):
            return
        for row in self.store.prompts_in_room(game_id, room):
            kept = []
            changed = False
            for button in row["buttons"]:
                label = (button.get("label") or "").lower()
                is_roll = ("rolldice" in (button.get("custom_id") or "").lower()
                           or "initat" in label)
                if is_roll and _button_color(button) == color:
                    changed = True
                    continue
                kept.append(button)
            if changed:
                self.store.set_buttons(row["id"], kept)

    def _prune_research_options(self, game, room, color, game_id):
        """Other research menus were priced before this purchase.

        The engine posts two menus for a 2-research action; after one purchase the
        other still lists the old affordable set. Remove techs already owned and
        techs this seat can no longer pay for, so a stale menu cannot add a tech
        and then demand payment it cannot make.
        """
        if not room or not color:
            return
        players = game.gamestate["players"]
        pid = game.get_player_from_color(color)
        if pid not in players:
            return
        player = players[pid]
        available = ResearchButtons.getPlayerTotalAvailableScience(player, game)
        owned = PlayerHelper(pid, player).getTechs()
        for row in self.store.prompts_in_room(game_id, room):
            buttons = row["buttons"]
            if not any("getTech_" in (button.get("custom_id") or "") for button in buttons):
                continue
            kept = []
            changed = False
            for button in buttons:
                custom_id = button.get("custom_id") or ""
                if "_getTech_" not in custom_id:
                    kept.append(button)
                    continue
                parts = custom_id.split("_getTech_")[1].split("_")
                tech, tech_type = parts[0], parts[1].replace("_setup", "")
                details = catalog.TECHS.get(tech)
                if details is None:
                    kept.append(button)
                    continue
                cost = ResearchButtons.calculate_cost(details, tech_type, player)
                if tech in owned or cost > available:
                    changed = True
                    continue
                kept.append(button)
            if changed:
                self.store.set_buttons(row["id"], kept)

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
                "players": [_clean_name(names[pid]) for pid in game.gamestate["players"]],
            })
        return web.json_response({"games": games})

    async def api_view(self, request):
        game_id = request.match_info["game_id"]
        seat = request.query.get("seat") or ""
        try:
            payload = await asyncio.to_thread(self.snapshot, game_id, seat)
        except FileNotFoundError:
            return web.json_response({"error": "unknown game", "game": game_id}, status=404)
        return web.json_response(payload)

    async def api_history(self, request):
        game_id = request.match_info["game_id"]
        seat = str(request.query.get("seat") or "")
        before = request.query.get("before")
        try:
            before = int(before) if before not in (None, "") else None
        except ValueError:
            return web.json_response({"error": "before must be a number"}, status=400)
        try:
            game = self.game(game_id)
        except FileNotFoundError:
            return web.json_response({"error": "unknown game"}, status=404)
        players = game.gamestate["players"]
        color = (players.get(str(seat)) or {}).get("color")
        rows, has_more = self.store.history_page(game_id, seat, before=before, limit=40)
        return web.json_response({"messages": [_message(row, players, seat, color) for row in rows],
                                  "has_more": has_more})

    async def api_catalog(self, request):
        return web.json_response(await asyncio.to_thread(catalog.snapshot))

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
                row = self.store.get(int(message_id))
                room = row["room"] if row else None
                interaction = WebInteraction(
                    self.store, game_id, seat, custom_id=custom_id, message_id=int(message_id),
                    members={"names": names, "colors": colors}, display_name=names.get(seat),
                    mirror=self.mirror, media_dir=self.media_dir, channel_name=room)
                await ButtonListener(None).resolveButton(interaction)
                pressed_color = _button_color({"custom_id": custom_id})
                self._retire_combat_rolls(game_id, room, pressed_color)
                self._prune_research_options(game, room, pressed_color, game_id)
            except Exception as exc:  # the Discord cog reports these to #bot-log; we answer the browser
                LOG.error("press failed: %s\n%s", exc, traceback.format_exc())
                error = f"{type(exc).__name__}: {exc}"

        payload = await asyncio.to_thread(self.snapshot, game_id, seat)
        payload["error"] = error
        return web.json_response(payload)

    async def api_turn_menu(self, request):
        """Recovery: post the start-of-turn buttons when a player has no prompt open."""
        game_id = request.match_info["game_id"]
        seat = str(request.query.get("seat") or "")
        async with game_lock(game_id):
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
        return web.json_response(await asyncio.to_thread(self.snapshot, game_id, seat))

    async def api_mirror(self, request):
        game_id = request.match_info["game_id"]
        body = await request.json()
        self.store.set_mirror(game_id, bool(body.get("mirror_to_discord")))
        return web.json_response(await asyncio.to_thread(
            self.snapshot, game_id, str(body.get("seat") or "")))

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
        app.on_startup.append(prepare_images)
        app.router.add_get("/", self.index)
        app.router.add_get("/api/games", self.api_games)
        app.router.add_get("/api/games/{game_id}/view", self.api_view)
        app.router.add_get("/api/games/{game_id}/history", self.api_history)
        app.router.add_get("/api/catalog", self.api_catalog)
        app.router.add_post("/api/games/{game_id}/press", self.api_press)
        app.router.add_post("/api/games/{game_id}/turn-menu", self.api_turn_menu)
        app.router.add_post("/api/games/{game_id}/mirror", self.api_mirror)
        app.router.add_get("/api/games/{game_id}/board.webp", self.api_board)
        app.router.add_get("/api/media/{message_id}/{name}", self.api_media)
        app.router.add_static("/static", STATIC_DIR)
        app.router.add_static("/art", ART_DIR)
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
