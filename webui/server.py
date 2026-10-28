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
from discord.ui import View
from Buttons.Draft import DraftButtons
from setup.GameInit import GameInit

import config
from Buttons.Research import ResearchButtons
from Buttons.Move import MoveButtons
from Buttons.Turn import TurnButtons
from helpers.DrawHelper import DrawHelper
from helpers.CombatHelper import Combat
from helpers.GamestateHelper import GamestateHelper
from helpers.GameIds import list_active_game_ids, list_game_ids
from helpers.GameLock import game_lock
from helpers.ImageCache import ImageCacheHelper
from helpers.PlayerHelper import PlayerHelper
from helpers.ShipHelper import PlayerShip
from listeners.ButtonListener import ButtonListener
from webui import catalog
from webui.render import (SOURCE_H, SOURCE_W, TILE_H, TILE_W, board_meta, render_board,
                          render_tile_preview, render_panel, rotate_tile_point)
from webui.store import FeedStore, buttons_from_view
from webui.transport import Surface, WebInteraction, combat_context

LOG = logging.getLogger(__name__)
ROOT = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(ROOT, "static")
ART_DIR = os.path.join(os.path.dirname(ROOT), "images", "resources")

SHIPS = ("interceptor", "cruiser", "dreadnought", "starbase")
PIECE_SHIPS = ("int", "cru", "drd", "sb", "orb", "mon", "anc", "gcds", "grd")
PLANET_SQUARES = ("money", "science", "material", "neutral", "moneyadv",
                  "scienceadv", "materialadv", "neutraladv", "orbital")


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
        "combat": row.get("combat") or {},
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
        "name": _clean_name(stats.get("username") or stats.get("player_name") or stats.get("name") or pid),
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
    """A prompt that stays beside newer prompts instead of being replaced by them.

    The private reaction-pass offer sits beside the turn menu, and a bankruptcy
    prompt needs the older Run Upkeep button to stay reachable so the resolved
    upkeep can be started again.
    """
    content = (message["content"] or "").lower()
    return any((button.get("custom_id") or "") == "permanentlyPass"
               for button in message["buttons"]) \
        or "would be bankrupt" in content


def _snap_point(point, rotation=0):
    """Save snapshots use the engine's 1024x890 tile; the board paints 345x300.

    Nebula art is rotated after its ships are drawn, so those points rotate too.
    """
    if not point or len(point) < 2:
        return None
    x, y = point[0], point[1]
    if rotation:
        x, y = rotate_tile_point(x, y, rotation)
    return {"x": round(x * TILE_W / SOURCE_W, 1), "y": round(y * TILE_H / SOURCE_H, 1)}


def _tile_pieces(tile, drawn_on, position, rotation=0):
    """The clickable objects the engine's own tile image already shows.

    A ship token sits on the snap point the engine draws it at, so the browser can
    put a hit target (or a drag handle) exactly on the visible unit. Empty planet
    squares have no art of their own, so the browser draws them as ghosts.
    """
    ships = {}
    for unit in tile.get("player_ships", []):
        if "-" not in unit:
            continue
        color, kind = unit.split("-", 1)
        kind = kind.replace("adv", "")
        if kind not in PIECE_SHIPS:
            continue
        anchor = _snap_point(tile.get(f"{'ai' if kind in ('anc', 'gcds', 'grd') else kind}_snap"),
                             rotation)
        if anchor is None:
            continue
        entry = ships.setdefault(unit, {"kind": "ship", "name": unit, "color": color,
                                        "class": kind, "count": 0,
                                        "position": position, "tile": drawn_on, **anchor})
        entry["count"] += 1
    planets = []
    for kind in PLANET_SQUARES:
        populations = tile.get(f"{kind}_pop")
        if not populations:
            continue
        for index, value in enumerate(populations):
            key = "orb" if kind == "orbital" else f"{kind}{index + 1}"
            anchor = _snap_point(tile.get(f"{key}_snap"), rotation)
            if anchor is None:
                continue
            planets.append({"kind": "planet", "square": kind, "index": index,
                            "pop": int(value or 0), "position": position,
                            "tile": drawn_on, **anchor})
    pieces = list(ships.values()) + planets
    return pieces


def _board_pieces(game):
    """Everything clickable that the board image already draws, in tile pixels."""
    pieces = []
    for position, tile in game.gamestate["board"].items():
        if "nebula_parent" in tile:
            continue  # painted inside the parent's image
        rotation = tile.get("orientation", 0) if tile.get("type") == "nebula" else 0
        pieces.extend(_tile_pieces(tile, position, position, rotation))
        for sibling in tile.get("nebula_internal", []):
            sub = game.gamestate["board"].get(sibling)
            if sub:
                pieces.extend(_tile_pieces(sub, position, sibling, rotation))
    return pieces


def _is_past_combat(room, round_number):
    match = re.search(r"-Round (\d+), Tile .+, (?:Combat|Bombing)$", room or "")
    return bool(match and round_number is not None and int(match[1]) < round_number)


def _current_prompts(pending, turn_menus=()):
    if not pending:
        return pending
    superseding = [message for message in pending
                   if _is_phase_prompt(message) or not _is_standing(message)]
    newest = max((message["id"] for message in superseding), default=0)
    turn_starts = {}
    for message in [*pending, *turn_menus]:
        if _is_turn_menu(message):
            turn_starts[message["room"]] = max(turn_starts.get(message["room"], 0), message["id"])
    return [message for message in pending
            if _is_standing(message) or not (
                message["id"] < turn_starts.get(message["room"], 0)
                or ((_is_turn_menu(message) or _is_phase_prompt(message)) and message["id"] < newest))]


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
        names = {pid: (stats.get("username") or stats.get("player_name") or stats.get("color") or pid)
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

        rows = self.store.pending_messages(game_id, seat_requested, include_deleted=True)
        # Used turn menus still mark the boundary of an abandoned action.
        turn_menus = [_message({**row, "deleted": False}, players, seat_requested, you_color)
                      for row in rows if _is_turn_menu(row)]
        turn_menus = [message for message in turn_menus if message["actionable"]]
        pending = [_message(row, players, seat_requested, you_color)
                   for row in rows if not row["deleted"]]
        pending = [message for message in pending
                   if message["actionable"] and seat_requested
                   and not _is_past_combat(message["room"], game.gamestate.get("roundNum"))]
        drafting = game.gamestate.get("draftingPlayers", [])
        if drafting and seat_requested != str(drafting[0]):
            pending = [message for message in pending if not any(
                (button.get("custom_id") or "").startswith("draftFaction_")
                for button in message["buttons"])]
        pending = _current_prompts(pending, turn_menus)
        for message in pending:
            for button in list(message["buttons"]):
                match = re.fullmatch(r"FCID([^_]+)_startMove_(\d+)", button.get("custom_id") or "")
                if not match or int(match[2]) < 2 or button.get("disabled"):
                    continue
                color, move_count = match.groups()
                player = game.getPlayerObjectFromColor(color)
                view, tiles = MoveButtons.buildMoveOriginView(game, player, move_count, "all", "")
                message["buttons"].extend(buttons_from_view(view))
        for message in pending:
            for button in message["buttons"]:
                match = re.fullmatch(r"FCID([^_]+)_moveQueueDone_(.+)", button.get("custom_id") or "")
                if not match:
                    continue
                color, command = match.groups()
                parts = command.split("_")
                origin, ship, move_count = parts[:3]
                nested, phase, ship_filter, suffix = MoveButtons.getMoveQueueContext(
                    f"moveQueueDone_{command}", 5)
                player = game.getPlayerObjectFromColor(color)
                maximum = min(MoveButtons.getMovableShipsOfType(game, player, origin, ship),
                              MoveButtons.getRemainingMoveActivations(player, int(move_count), nested))
                button["counts"] = []
                for count in range(1, maximum + 1):
                    choices = MoveButtons.buildMoveQueueView(player, origin, ship, move_count, count, maximum, suffix)
                    button["counts"].extend(choice for choice in buttons_from_view(choices)
                                            if "_moveQueueDone_" in choice["custom_id"])
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

        battles = {}
        for row in self.store.combat_history(game_id, seat_requested):
            room = row["room"]
            if _is_past_combat(room, game.gamestate.get("roundNum")):
                continue
            position = re.search(r"Tile (\d+[a-z]?)", room)
            tile = game.gamestate["board"].get(position[1], {}) if position else {}
            if room not in battles:
                battles[room] = {"room": room, "messages": [], "sides": [
                    {"role": side, "colors": Combat.sideOf(tile.get(side))}
                    for side in ("defender", "attacker")]}
            if not row.get("combat"):
                row["combat"] = combat_context(game_id, room, row["content"], row["buttons"], game=game)
            battles[room]["messages"].append(_message(row, players, seat_requested, you_color))

        player_rows = [player_state(game, seat, pid, stats) for pid, stats in players.items()]
        you_row = next((row for row in player_rows if row["is_you"]), None)
        payload = {
            "game": {
                "id": game_id,
                "name": game.gamestate.get("game_name", game_id),
                "round": game.gamestate.get("roundNum"),
                "round_max": 8,
                "s3_remaining": len(game.gamestate.get("tile_deck_300", [])) + len(game.gamestate.get("tile_discard_deck_300", [])),
                "minor_species": game.gamestate.get("minor_species", []),
                "setup": not bool(game.gamestate.get("setup_finished")),
                "drafting_seat": str((game.gamestate.get("draftingPlayers") or [""])[0]),
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
                "disc_tiles": you_row["disc_tiles"],
                "faction": you_row["faction"],
                "passed": you_row["passed"],
                "is_your_turn": you_row["color"] in active,
            },
            "mirror_to_discord": self.store.mirrors(game_id),
            "version": version,
            "board": f"/api/games/{game_id}/board.webp?v={version}",
            "board_meta": self._board(game_id, version),
            "pieces": _board_pieces(game),
            "tech_market": self._tech_market(game, you),
            "result": sorted(
                [{"id": row["id"], "name": row["name"], "color": row["color"],
                  "faction_name": row["faction_name"], "points": row["points"]}
                 for row in player_rows],
                key=lambda row: (row["points"] is None, -(row["points"] or 0))),
            "pending": pending,
            "battles": list(battles.values()),
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
    async def api_create_game(self, request):
        if self.games_path != "/sandbox/games":
            return web.json_response({"error": "Game creation is restricted to the dev sandbox"}, status=403)
        body = await request.json()
        name = body.get("name", "")
        count = body.get("players")
        ai = body.get("ai", "def")
        options = ("rift_cannon", "turn_order_variant", "galactic_event_tiles", "hyperlanes",
                   "community_parts", "community_rep_mod", "ban_factions", "alliances", "community_factions")
        if (not isinstance(name, str) or not name.strip() or len(name) > 100
                or type(count) is not int or not 1 <= count <= 9
                or ai not in ("def", "adv", "wa", "random")
                or any(type(body.get(key, False)) is not bool for key in options)):
            return web.json_response({"error": "Invalid game settings"}, status=400)
        if body.get("hyperlanes") and count not in (4, 5):
            return web.json_response({"error": "Hyperlanes require 4 or 5 players"}, status=400)
        if body.get("alliances") and count < 4:
            return web.json_response({"error": "Alliances require at least 4 players"}, status=400)
        players = [[seat, f"Player {seat}"] for seat in range(1, count + 1)]
        async with game_lock("dev-create"):
            while os.path.exists(os.path.join(self.games_path, f"aeb{config.game_number}.json")):
                config.game_number += 1
            init = GameInit(name.strip(), players, ai, body.get("rift_cannon", True),
                            body.get("turn_order_variant", True), body.get("community_parts", False),
                            body.get("community_rep_mod", False), body.get("community_factions", False))
            init.create_game()
            game_id = init.gamestate["game_id"]
            game = self.game(game_id)
            game.setAlliances(body.get("alliances", False))
            game.setup_techs_and_outer_rim(count, body.get("galactic_event_tiles", False), body.get("hyperlanes", False))
            self.store.set_mirror(game_id, False)
            interaction = WebInteraction(self.store, game_id, "1", media_dir=self.media_dir)
            await DraftButtons.startDraft(game, players, interaction, interaction.channel, body.get("ban_factions", False))
        return web.json_response({"id": game_id}, status=201)

    async def api_games(self, request):
        games = []
        active_ids = set(list_active_game_ids())
        for game_id in list_game_ids():
            try:
                game = self.game(game_id)
            except (OSError, ValueError):
                continue
            if game_id not in active_ids and game.gamestate.get("setup_finished"):
                continue
            names, _colors = self._parts(game_id, game)
            games.append({
                "id": game_id,
                "name": game.gamestate.get("game_name", game_id),
                "round": game.gamestate.get("roundNum"),
                "active": game.gamestate.get("activePlayerColor", []),
                "players": [_clean_name(names[pid]) for pid in game.gamestate["players"]],
            })
        return web.json_response({"games": games, "can_create": self.games_path == "/sandbox/games"})

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
                pending = self.snapshot(game_id, seat)["pending"]
                allowed = [button for message in pending if message["id"] == int(message_id)
                           for button in message["buttons"] if not button.get("disabled")]
                allowed += [choice for button in allowed for choice in button.get("counts", [])]
                track_choices = []
                for button in allowed:
                    match = re.fullmatch(r"FCID([^_]+)_getTech_([^_]+)_any(_setup)?",
                                         button.get("custom_id") or "")
                    if not match:
                        continue
                    color, tech, setup = match.groups()
                    player = game.getPlayerObjectFromColor(color)
                    view = await ResearchButtons.handle_wild_tech_selection(
                        View(), catalog.TECHS[tech], tech, player, bool(setup))
                    tracks = buttons_from_view(view)
                    if custom_id == button["custom_id"]:
                        return web.json_response({**self.snapshot(game_id, seat),
                                                  "tech_tracks": tracks, "error": None})
                    track_choices.extend(tracks)
                if not any(button.get("custom_id") == custom_id
                           for button in [*allowed, *track_choices]):
                    return web.json_response({**self.snapshot(game_id, seat),
                                              "error": "That choice is no longer active."})
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
        response.headers["Content-Type"] = "image/webp"
        response.headers["X-Board-Key"] = key
        return response

    async def api_market_layout(self, request):
        game_id = request.match_info["game_id"]
        try:
            async with game_lock(game_id):
                path = await asyncio.to_thread(render_panel, self.games_path, game_id,
                                               "market", "", self.render_dir)
        except FileNotFoundError:
            return web.json_response({"error": "unknown game"}, status=404)
        return web.FileResponse(f"{path}.json", headers={"Cache-Control": "no-cache"})

    async def api_panel(self, request):
        game_id = request.match_info["game_id"]
        panel = request.match_info["panel"]
        seat = request.query.get("seat", "")
        blueprint_panels = tuple(f"blueprint-{ship}" for ship in (*SHIPS, "orbital"))
        if (panel not in ("market", "player", "turn-order", "ai", "species", "parts", *blueprint_panels)
                or ((panel == "player" or panel in blueprint_panels) and not seat.isdigit())):
            return web.json_response({"error": "unknown panel"}, status=400)
        try:
            async with game_lock(game_id):
                path = await asyncio.to_thread(render_panel, self.games_path, game_id, panel, seat, self.render_dir)
        except FileNotFoundError:
            return web.json_response({"error": "unknown game"}, status=404)
        if path is None:
            return web.json_response({"error": "player has not drafted a faction"}, status=404)
        if panel in blueprint_panels and request.query.get("layout") == "1":
            return web.FileResponse(f"{path}.json", headers={"Cache-Control": "no-cache"})
        response = web.FileResponse(path)
        response.headers["Cache-Control"] = "no-cache"
        return response

    async def api_tile(self, request):
        """A single explored tile at one rotation, painted by the engine's own art."""
        game_id = request.match_info["game_id"]
        sector = request.query.get("sector") or ""
        try:
            rotation = int(request.query.get("rot") or 0)
        except ValueError:
            return web.json_response({"error": "rot must be a number"}, status=400)
        if not re.fullmatch(r"[a-z0-9]+", sector) or rotation % 60:
            return web.json_response({"error": "sector and a 60° rotation are required"}, status=400)
        try:
            path = await asyncio.to_thread(
                render_tile_preview, sector, rotation, self.render_dir)
        except FileNotFoundError:
            return web.json_response({"error": "unknown game"}, status=404)
        if path is None:
            return web.json_response({"error": "unknown sector"}, status=404)
        response = web.FileResponse(path)
        response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        response.headers["Content-Type"] = "image/webp"
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
        app.router.add_post("/api/games", self.api_create_game)
        app.router.add_get("/api/games/{game_id}/view", self.api_view)
        app.router.add_get("/api/games/{game_id}/history", self.api_history)
        app.router.add_get("/api/catalog", self.api_catalog)
        app.router.add_post("/api/games/{game_id}/press", self.api_press)
        app.router.add_post("/api/games/{game_id}/turn-menu", self.api_turn_menu)
        app.router.add_post("/api/games/{game_id}/mirror", self.api_mirror)
        app.router.add_get("/api/games/{game_id}/board.webp", self.api_board)
        app.router.add_get("/api/games/{game_id}/tile.webp", self.api_tile)
        app.router.add_get("/api/games/{game_id}/{panel}.webp", self.api_panel)
        app.router.add_get("/api/games/{game_id}/market-layout", self.api_market_layout)
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
