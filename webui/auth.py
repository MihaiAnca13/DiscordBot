"""Discord identity and server-side sessions for the public web UI."""
import json
from pathlib import Path
import re
import secrets
import time
from urllib.parse import urlencode

from aiohttp import ClientSession, ClientError, ClientTimeout, web

import config


def install_auth(app, surface):
    settings = config.data
    if not settings.get("webui_require_login", False):
        return
    client_id = settings.get("discord_client_id")
    secret = settings.get("discord_client_secret")
    origin = settings.get("webui_origin", "").rstrip("/")
    if not client_id or not secret or not origin.startswith("https://"):
        raise ValueError("Discord login requires client ID, secret and HTTPS webui_origin")
    callback = origin + "/auth/callback"
    states = {}

    def prune(entries):
        for key, value in list(entries.items()):
            if value[1] <= time.monotonic():
                del entries[key]

    async def login(request):
        prune(states)
        state = secrets.token_urlsafe(32)
        states[state] = (True, time.monotonic() + 600)
        response = web.HTTPFound("https://discord.com/oauth2/authorize?" + urlencode({
            "client_id": client_id, "redirect_uri": callback,
            "response_type": "code", "scope": "identify", "state": state}))
        response.set_cookie("oauth_state", state, secure=True, httponly=True,
                            samesite="Lax", max_age=600, path="/auth")
        return response

    async def finish(request):
        prune(states)
        state = request.query.get("state", "")
        if not state or not secrets.compare_digest(state, request.cookies.get("oauth_state", "")) or states.pop(state, None) is None:
            raise web.HTTPBadRequest(text="Invalid or expired login. Please try again.")
        try:
            async with ClientSession(timeout=ClientTimeout(total=20)) as client:
                async with client.post("https://discord.com/api/oauth2/token", data={
                    "client_id": client_id, "client_secret": secret,
                    "grant_type": "authorization_code", "code": request.query.get("code", ""),
                    "redirect_uri": callback}) as result:
                    if result.status != 200:
                        raise web.HTTPBadGateway(text="Discord login failed. Please try again.")
                    token = await result.json()
                async with client.get("https://discord.com/api/users/@me", headers={
                    "Authorization": "Bearer " + token["access_token"]}) as result:
                    if result.status != 200:
                        raise web.HTTPBadGateway(text="Discord identity lookup failed.")
                    identity = await result.json()
        except (ClientError, TimeoutError):
            raise web.HTTPBadGateway(text="Discord is unavailable. Please try again.")
        session = secrets.token_urlsafe(32)
        surface.store.save_session(session, str(identity["id"]), time.time() + 604800)
        response = web.HTTPFound("/")
        response.set_cookie("session", session, secure=True, httponly=True,
                            samesite="Lax", max_age=604800)
        response.del_cookie("oauth_state", path="/auth")
        return response

    async def logout(request):
        surface.store.delete_session(request.cookies.get("session", ""))
        response = web.HTTPFound("/")
        response.del_cookie("session")
        return response

    @web.middleware
    async def authenticate(request, handler):
        if request.path.startswith("/auth/"):
            return await handler(request)
        user_id = surface.store.session_user(request.cookies.get("session", ""))
        if user_id is None:
            if request.path == "/":
                return web.FileResponse(Path(__file__).parent / "static" / "login.html", headers={"Cache-Control": "no-store"})
            raise web.HTTPUnauthorized(text="Sign in with Discord", headers={"Cache-Control": "no-store"})
        if request.method not in ("GET", "HEAD") and request.headers.get("Origin") != origin:
            raise web.HTTPForbidden(text="Invalid request origin")
        game_id = request.match_info.get("game_id")
        if game_id:
            if not re.fullmatch(r"[a-zA-Z0-9-]+", game_id):
                raise web.HTTPNotFound()
            try:
                game = surface.game(game_id)
            except FileNotFoundError:
                raise web.HTTPNotFound()
            if user_id not in game.gamestate["players"]:
                raise web.HTTPForbidden(text="You are not a player in this game")
        if request.path.startswith("/api/media/"):
            try:
                message_id = int(request.match_info["message_id"])
            except ValueError:
                raise web.HTTPNotFound()
            row = surface.store.get(message_id)
            if not row or (row.get("ephemeral_to") and str(row["ephemeral_to"]) != user_id):
                raise web.HTTPForbidden()
            if user_id not in surface.game(row["game_id"]).gamestate["players"]:
                raise web.HTTPForbidden()
        query = request.rel_url.query.copy()
        if not (request.method in ("GET", "HEAD") and request.match_info.get("panel")):
            query["seat"] = user_id
        request = request.clone(rel_url=request.rel_url.with_query(query))
        if request.method == "POST":
            try:
                body = await request.json() if request.can_read_body else {}
            except (ValueError, UnicodeDecodeError):
                raise web.HTTPBadRequest(text="Invalid JSON")
            if not isinstance(body, dict):
                raise web.HTTPBadRequest(text="Expected a JSON object")
            body["seat"] = user_id
            request.authenticated_body = body
        response = await handler(request)
        if request.path == "/api/games":
            payload = json.loads(response.text)
            payload["games"] = [game for game in payload["games"]
                                if user_id in surface.game(game["id"]).gamestate["players"]]
            payload["can_create"] = False
            response = web.json_response(payload)
        if request.path.endswith("/view"):
            payload = json.loads(response.text)
            payload["authenticated"] = True
            response = web.json_response(payload)
        response.set_cookie("session", request.cookies["session"], secure=True,
                            httponly=True, samesite="Lax", max_age=604800)
        response.headers["Cache-Control"] = "no-store"
        return response

    app.middlewares.append(authenticate)
    app.router.add_get("/auth/login", login)
    app.router.add_get("/auth/callback", finish)
    app.router.add_post("/auth/logout", logout)
