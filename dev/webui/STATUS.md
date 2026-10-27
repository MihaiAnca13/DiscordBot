# Web UI progress

## Current milestone

Milestones 1–7 of `dev/webui/AGENT.md` are implemented and verified in the Docker
sandbox. The live preview is http://127.0.0.1:8099/?seat=1 (seat 2 is red). No real
Discord, production save or remote host was touched.

## Baseline and final checks

| Check | Result |
|---|---|
| `pytest tests -m 'not render' -q` | **626 passed**, 24 deselected |
| `pytest tests -m render -q` | **24 passed**, 626 deselected |
| `python -m dev.webui.smoke` | passed; desktop screenshot, Build menu, hotspots |
| `python -m dev.webui.browser_checks` | **18/18 passed** (real Chromium, HTTP, two seats) |
| `python -m dev.webui.playthrough round` | passed: build, explore, discovery, influence, passing, upkeep → round 2 |
| `python -m dev.webui.playthrough movement` | passed: click-move 201 → 101 → 201 |
| `python -m dev.webui.playthrough full` | passed: pass-only game from round 1 to final scores (round 9) |
| `python -m dev.webui.playthrough combat` | passed: two-sided combat to destruction + reputation draw |
| scoring scenario + browser | passed: round 8 upkeep → Declare Winner → final scoreboard |
| bankruptcy scenario | passed: upkeep blocks with trade/remove-control choices |

All commands ran through `compose.webui.yaml`; screenshots and result JSON are in
`dev/webui/artifacts/` (Git-ignored).

## What was built

- **Table layout** (`webui/static/index.html`, `style.css`, `app.js`): dark tabletop
  with a map panel, tech market, action dock, player panels, history and faction
  sheets. Desktop and narrow layouts were inspected in Chromium screenshots.
- **Board** (`webui/render.py`): map-only render at tile scale, cached by save
  version; every placed and unexplored ring slot has a position. Zoom, wheel zoom,
  drag pan and Fit. Build/explore/influence/move choices become hotspots; movement
  has a draggable ship token plus click/touch destination chips.
- **Player panels**: resources, activation counters, income/upkeep, tech tracks,
  blueprint slots with part art, public VP, owned systems and reputation.
- **Tech market + faction reference**: engine artwork and discounted costs; the
  faction sheet shows the engine's faction board and starting facts.
- **Research/upgrade dialogs** (`app.js` + `webui/catalog.py`): tech cards, part
  cards with stats, ship choices and Undo/back as plain choices.
- **Action/history split** (`webui/store.py`, `server.py`): pending choices are a
  separate unbounded query (`pending_messages`); history is paged and keeps used
  prompts. Stale phase prompts and old turn menus are hidden from the dock.
- **Combat rooms** (`server.py`, `transport.py`, `app.js`): every battle retains its
  room name, its orders and its own collapsible log. Presses reuse the original
  room, not the general actions room.
- **Cross-play safety**: one shared game lock and canonical feed ids; two seats
  pressing the same prompt yield one action; a stale replay awards nothing; a colour's
  roll button is retired after that colour rolls; other research menus lose owned or
  unaffordable techs.
- **Sandbox tools** (`dev/webui/`): `seed`, `scenarios` (combat, movement, upkeep,
  scoring, bankrupt, recovery), `smoke`, `shot`, `browser_checks`, `playthrough`.
  Fixed seed / rule setup comes from the existing test setup.

## Evidence for specific requirements

- 80-message limit cannot hide choices: a prompt after 60 newer records still
  appears in `pending` (`tests/test_webui_view.py`).
- Private seat isolation: ephemeral prompts appear only for their seat (transport
  test and view test); browser checks confirm red sees no private blue prompt.
- Consumed/stale buttons: repeated race produced one research action; replaying the
  used prompt left science unchanged; discovery and combat roll cases are covered.
- Two-seat observation: browser checks run two pages on the same seat and assert a
  single disc/action; seat 2 polls the shared feed for the other seat's turn.
- Upkeep and scoring: full round and round-8 scoring scenarios passed; the end screen
  shows final VP and hides all old prompts.
- Combat: two-sided interceptor battle ran through initiative rounds to destruction,
  drew reputation for both sides, and left the battle room log intact.

## Exact commands

```sh
docker compose -f compose.webui.yaml build
docker compose -f compose.webui.yaml stop webui
docker compose -f compose.webui.yaml run --rm webui python -m dev.webui.seed
docker compose -f compose.webui.yaml up -d --wait webui
docker compose -f compose.webui.yaml run --rm webui python -m pytest tests -m 'not render' -q
docker compose -f compose.webui.yaml run --rm webui python -m pytest tests -m render -q
docker compose -f compose.webui.yaml exec -T webui python -m dev.webui.smoke
docker compose -f compose.webui.yaml exec -T webui python -m dev.webui.browser_checks
```

Reset before smoke/browser checks; each scenario also wipes both development volumes.
Cold board render takes a few seconds; wait for `#board.naturalWidth > 0`.

## Known limits (not implemented)

- No login/authentication. `seat` is a query parameter/local storage. Keep the API on
  loopback or WireGuard; it is not safe on a public interface.
- No live Discord run. Mirror send/edit/delete, real thread creation and
  cross-surface consumption are recorded/tested with fakes only. The demo game has
  `mirror_to_discord = false`. Do not claim live cross-play is verified.
- Remote frontend/WireGuard/TLS/reverse-proxy setup is documented, not installed.
- Polling every 1.5 s; no push channel.
- No drag-to-move on touch pinch gestures (click destination chips are the touch
  fallback); board pan/zoom supports pointer and buttons.
- Faction ability names come from `data/factions.json`; full rule text lives on the
  faction-board image rather than extracted HTML.
- Bankruptcy prompts are displayed and tested, but resolving a bankruptcy through
  trade/removal end-to-end was not scripted.

## Next task

1. Authentication and remote-host deployment (TLS reverse proxy, WireGuard bind,
   seat tokens) before exposing the UI.
2. One live Discord session to verify the mirror and cross-surface prompt retirement.
3. Optional polish: richer faction ability text, bankruptcy resolution script,
   touch pinch zoom.

## Checkpoints

- Branch `mihai/webui`; checkpoint commits made after the verified milestones (see
  `git log`). No push, merge, live save or wave2 access.
