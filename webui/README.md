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
| `GET /api/games/{id}/view?seat=` | one seat's whole UI state: board, players, feed |
| `POST /api/games/{id}/press` | `{seat, custom_id, message_id}` — the Discord press |
| `POST /api/games/{id}/turn-menu?seat=` | recovery: re-post the start-of-turn buttons |
| `POST /api/games/{id}/mirror` | web-only (`false`) vs cross-play (`true`); default true |
| `GET /api/games/{id}/board.webp` | rendered board, cached by save-file version |
| `GET /api/media/{message_id}/{name}` | images the engine sent privately |

## Verified today

- Real game copy served, board rendered and cached (2.8 s cold, 10 ms cached).
- Turn menu → build → tile → ship chain pressed entirely over HTTP, gamestate saved.
- Private prompts (ephemeral) visible only to their seat; public prompts to everyone.
- In-place prompt edits (`Total cost so far of 3`) keep the same message id.
- Used prompts disappear; pressing one again answers "these buttons were already used".
- Another seat's `FCID<colour>_` buttons are refused.
- 612 existing tests still pass; 14 new ones cover store, press and recording.

## Not done (deliberately)

- **Login.** `seat` is a query parameter or local storage. Moving into OBG replaces
  this with the Django session + `Profile.discord_id`; a seat token is the fallback.
- **Discord mirror is written but never sent live** (no bot token here). The recording
  side is tested with fakes; `DiscordMirror.send/edit/delete` needs one real session.
  It only mirrors public prompts and only when `mirror_to_discord` is on.
- **Threads are flattened.** Combat prompts become feed messages instead of Discord
  threads; a web-only game never creates threads. Cross-play combat needs rooms.
- **Drag to move.** It is a chain of existing presses (pick ship → engine returns legal
  destinations → pick one), so it is a UI feature, not an engine change.
- **Notifications.** Turn pings are still Discord role mentions; OBG's email/DM
  machinery is the web-only answer.
- **Feed history** is capped at 80 messages in the view; older prompts stay in SQLite.
- **Every poll reads the save file** (small, cached by mtime+size); a busy instance
  would want the snapshot pushed instead of polled.

## Next, in order

1. The Vue port when it moves into OBG (`<GAME>/vue<GAME>/src`, API client already
   isolated in `static/app.js`).
2. Discord login + `discord_id` seats.
3. Rooms for combat, then web-only games with the mirror flag off.
4. WireGuard between the OBG host and the bot host, bot API bound to the tunnel address.
