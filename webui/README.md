# Web UI — day 1 prototype

One feed, two surfaces. The game engine in `Buttons/` and `helpers/` is untouched:
both Discord and the browser drive it through an interaction-shaped object, exactly
like `tests/fakes.py` already does.

```
Discord press ──► ButtonListener.on_interaction ──► runtime.record()   ─┐
Browser press ──► POST /api/games/{id}/press ────► WebInteraction      ─┤
                                                                       ├─► resolveButton (unchanged)
                                                                       │
feed (SQLite) ◄── RecordingInteraction / WebInteraction ────────────────┘
   │                                                   │
   │                                                   └─► DiscordMirror (optional, per game)
   └─► GET /api/games/{id}/view ─► one page in the browser
```

## Why it works in one process

`helpers/GameLock` is an in-process `asyncio.Lock` and the save files are written by
this process alone. The web server therefore rides the bot's event loop
(`webui/runtime.start_webui`, called from `setup_hook`). Do not run it as a separate
process that writes the same game: that is the one thing that corrupts saves. If it
has to live on another machine later, it must call this process over WireGuard and
never touch `gamestates/` itself.

## Message ids are canonical

Every prompt gets a feed id (`messages.id`). Discord's own id is stored beside it.
`gamestate["lastButtonMessage"]` therefore means the same thing whichever surface
pressed, and the "already used" and double-press guards keep working across surfaces.

## Run it

For an isolated Docker sandbox, browser checks and the OpenCode build brief, see
[dev/webui/README.md](../dev/webui/README.md).

In the bot (needs `webui_port` in `config.json`, port 0 disables it):

```json
{ "webui_port": 8099, "webui_host": "127.0.0.1" }
```

Then `python main.py` serves the page at http://127.0.0.1:8099/ while the bot runs.

Standalone, against a **copy** of the saves (no Discord, no writes to real games):

```bash
mkdir -p gamestates && cp ~/personal/DiscordBot/gamestates/aeb22*.json gamestates/
WEBUI_GAMESTATE_PATH=gamestates WEBUI_PORT=8099 .venv/bin/python -m webui.server
```

Open `http://127.0.0.1:8099/?seat=<discord id>` or pick a seat in the header.

## Endpoints

| Route | Purpose |
|---|---|
| `GET /api/games` | active games with players and round |
| `GET /api/games/{id}/view?seat=` | one seat's table state: board geometry, players, market, pending choices, first history page |
| `GET /api/games/{id}/history?seat=&before=` | paged feed, including used prompts and their canonical ids |
| `POST /api/games/{id}/press` | `{seat, custom_id, message_id}` — the Discord press |
| `POST /api/games/{id}/mirror` | web-only (`false`) vs cross-play (`true`); default true |
| `GET /api/games/{id}/board.webp` | rendered map, cached by save-file version |
| `GET /api/games/{id}/tile.webp?sector=&rot=` | one explored sector at an offered rotation, for the on-board preview |
| `GET /api/catalog` | tech, part and discovery facts/artwork for visual choices |
| `GET /api/media/{message_id}/{name}` | images the engine sent privately |
| `/art/...` | read-only game artwork under `images/resources` |

## What the table does

- **Board.** Map-only render with zoom, pan and fit. Placed sectors carry ship and
  owner art; unexplored ring slots are drawn as dark hexes. The board is the choice
  surface: ships are clickable tokens at their real snap points, unexplored slots
  and legal destinations are marked worlds, empty planet squares are ghost targets
  and the chosen explored tile previews in place. See
  [dev/webui/INTERACTIONS.md](../dev/webui/INTERACTIONS.md).
- **Player panels.** Resources, activations, income/upkeep, tech tracks, blueprint
  slots with installed parts and public victory points, for every seat. During an
  Upgrade action the seat's own blueprint ship and slot are the click targets.
- **Tech market and faction reference.** Market cards use the engine's artwork and
  the seat's discounted cost. The faction dialog shows the engine's faction board
  (rules reference) plus starting setup and ability names.
- **Choices.** Pending prompts are fetched separately from history, so the 80-record
  history cap can never hide an unresolved choice. Research is chosen on the tech
  market; upgrades on the blueprints; build units, replacement parts, discovery
  cards and movement quantities are picture cards. Spatial choices carry a
  collapsed "choose from a list" fallback for keyboard and screen-reader use.
  Finish/navigation buttons sit below the real choices.
- **Combat rooms.** Every battle keeps its own room name, orders and a collapsible
  battle log. An old combat overview stops offering a colour's roll once that
  colour has rolled.
- **History.** Used prompts, private replies and resolved actions stay readable in
  a paged dialog; hiding history never deletes the feed records.
- **Discord delivery.** Web actions write their save and feed immediately; public
  sends, edits and deletes go through a persistent SQLite queue in order. Discord
  delays do not hold the game lock. Unsent deleted prompts are skipped; stale
  deleted prompts are rejected even while their Discord messages remain visible.
  Failures are logged and retried, and pending work survives bot restarts.
  Private replies remain browser-only. Artwork rendering still runs before the
  web action completes. Discord nonce deduplication covers short retries; an
  ambiguous send after a long outage may need manual inspection.
- **Cross-play guards.** A press binds its canonical feed id, the room it came from
  and the shared game lock. Two browser seats pressing the same menu produce one
  action; a stale replay awards nothing. A second research menu drops techs already
  owned or no longer affordable.

## Verified in the Docker sandbox

- 625 non-rendering tests and 24 rendering tests pass; the web-ui view/store tests
  cover pending-vs-history, seat filtering, private prompts and combat roll cleanup.
- `dev.webui.browser_checks`: 18 real-Chromium checks (layout, zoom/pan, faction,
  history, two-seat race, stale replay, refresh, narrow viewport).
- `dev.webui.playthrough round`: build, explore, discovery, influence, passing and
  upkeep through live HTTP, ending in round 2.
- `dev.webui.playthrough combat`: two-sided combat to destruction, reputation draw
  and battle-room logs.
- Screenshots in `dev/webui/artifacts/` were inspected for desktop and narrow views.

## Not done (deliberately)

- **Login.** For a public deployment set `webui_require_login: true`,
  `discord_client_id`, `discord_client_secret` and `webui_origin` (the HTTPS origin)
  in the private `config.json`. Register `<webui_origin>/auth/callback` in the
  Discord application's OAuth2 redirects. Login requests only `identify`; the API
  binds seats to that Discord ID and limits games/media to their players.
  Sessions expire after one week of inactivity and persist across restarts in SQLite. POST `/auth/logout`
  clears the session. Keep the backend on loopback behind Caddy. Login-disabled
  mode is for isolated development only.
- **Discord mirror is written but never sent live** (no bot token here). The recording
  side is tested with fakes; `DiscordMirror.send/edit/delete` needs one real session.
  It only mirrors public prompts and only when `mirror_to_discord` is on. Feed-side
  roll cleanup is not verified against a live Discord message.
- **Notifications.** Turn pings are still Discord role mentions; OBG's email/DM
  machinery is the web-only answer.
- **Remote host.** The page only uses relative API/media URLs, so a reverse proxy can
  serve it beside the bot API. Still required: TLS, an auth layer, a proxy route for
  `/api`, `/static` and `/art`, and a WireGuard binding between the frontend host and
  the bot host. The bot process stays the only writer of `gamestates/`.
- **Polling.** Each browser polls the seat view every 1.5 s; the server caches by save
  version and feed revision. A busy instance should push snapshots instead.
- **Combat starter.** The demo sandbox has no starting combat; use
  `python -m dev.webui.scenarios combat` while the service is stopped.

## Next, in order

1. The Vue port when it moves into OBG (`<GAME>/vue<GAME>/src`, API client already
   isolated in `static/app.js`).
2. Discord login + `discord_id` seats, then a reverse proxy with TLS and WireGuard.
3. One live Discord session to verify mirror send/edit/delete and cross-surface
   prompt consumption, including combat rooms.
4. Push snapshots instead of polling for larger games.
