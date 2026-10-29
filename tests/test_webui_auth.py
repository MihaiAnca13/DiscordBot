import asyncio
import time
from types import SimpleNamespace

from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

import config
from webui.auth import install_auth
from webui.store import FeedStore


def test_login_boundary(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "data", {
        "webui_require_login": True, "discord_client_id": "123",
        "discord_client_secret": "secret", "webui_origin": "https://example.com"})

    async def check():
        app = web.Application()
        install_auth(app, SimpleNamespace(store=FeedStore(str(tmp_path / "feed.sqlite3"))))
        app.router.add_get("/", lambda request: web.Response(text="private"))
        app.router.add_get("/api/games", lambda request: web.json_response({}))
        async with TestClient(TestServer(app)) as client:
            response = await client.get("/")
            assert "Sign in with Discord" in await response.text()
            assert (await client.get("/api/games")).status == 401
            response = await client.get("/auth/login", allow_redirects=False)
            assert response.status == 302
            assert "scope=identify" in response.headers["Location"]
            assert response.cookies["oauth_state"]["secure"]
            assert (await client.get("/auth/callback?state=forged&code=x")).status == 400
    asyncio.run(check())


def test_authenticated_seat_and_origin(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "data", {
        "webui_require_login": True, "discord_client_id": "123",
        "discord_client_secret": "secret", "webui_origin": "https://example.com"})

    async def check():
        app = web.Application()
        store = FeedStore(str(tmp_path / "feed.sqlite3"))
        surface = SimpleNamespace(store=store, game=lambda game_id: SimpleNamespace(gamestate={"players": {"42": {}}}))
        install_auth(app, surface)
        store.save_session("test-session", "42", time.time() + 60)

        async def echo(request):
            return web.json_response({"seat": request.query["seat"],
                                      "body": request.authenticated_body})
        app.router.add_post("/api/games/{game_id}/press", echo)
        app.router.add_get("/api/games/{game_id}/{panel}.webp",
                           lambda request: web.json_response({"seat": request.query.get("seat")}))
        async with TestClient(TestServer(app)) as client:
            headers = {"Cookie": "session=test-session", "Origin": "https://example.com"}
            response = await client.get("/api/games/aeb1/player.webp?seat=99", headers=headers)
            assert await response.json() == {"seat": "99"}
            response = await client.get("/api/games/aeb1/blueprint-int.webp?seat=99", headers=headers)
            assert await response.json() == {"seat": "99"}
            response = await client.post("/api/games/aeb1/press?seat=99", json={"seat": "99"}, headers=headers)
            assert await response.json() == {"seat": "42", "body": {"seat": "42"}}
            response = await client.post("/api/games/aeb1/press?seat=99", headers=headers)
            assert response.status == 200
            assert await response.json() == {"seat": "42", "body": {"seat": "42"}}
            response = await client.post("/api/games/aeb1/press", data="invalid", headers=headers)
            assert response.status == 400
            headers["Origin"] = "https://attacker.example"
            response = await client.post("/api/games/aeb1/press", json={}, headers=headers)
            assert response.status == 403
    asyncio.run(check())


def test_sessions_survive_restart_and_expire(tmp_path):
    path = str(tmp_path / "feed.sqlite3")
    store = FeedStore(path)
    store.save_session("secret-token", "42", time.time() + 60)
    store.close()
    store = FeedStore(path)
    assert store.session_user("secret-token") == "42"
    expiry = store.conn.execute("SELECT expires_at FROM sessions").fetchone()[0]
    assert expiry > time.time() + 604790
    assert store.session_user("forged") is None
    assert store.conn.execute("SELECT token_hash FROM sessions").fetchone()[0] != "secret-token"
    store.save_session("expired-token", "42", time.time() - 1)
    assert store.session_user("expired-token") is None
    store.delete_session("secret-token")
    assert store.session_user("secret-token") is None
    store.close()
