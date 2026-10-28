# Web UI progress

## Current milestone

Milestones 1–7 of `dev/webui/AGENT.md` are implemented and verified in the Docker
sandbox, and the direct-interaction pass (audit in `INTERACTIONS.md`) is implemented
and checked flow by flow. The live preview is http://127.0.0.1:8099/?seat=1 (seat 2 is
red). No real Discord, production save or remote host was touched.

## Direct interaction pass

The UI now puts each engine choice on the object it names instead of on a Discord
button. The engine still owns legality and every click goes through `/press` with the
same canonical message id.

- Movement: click the ship on the map, click the ship type, click/drag a highlighted
  destination; multi-ship moves use the engine's queue with a count control.
- Exploration: click an unexplored ring slot; the real sector previews in place and
  cycles only the engine's legal rotations (click, dock arrows or ←/→), then Place.
- Influence: empty worlds and your own disc are the add/remove targets.
- Population: empty planet squares are ghost targets; grey planets then ask for the
  cube type as a resource choice.
- Build: the system is marked on the map; units are picture cards with cost and a
  running materials total (trading still allowed at the spend step).
- Upgrade: your blueprint ship and each part slot are the targets; replacement parts
  remain cards.
- Research: the tech market is the only research surface; offered cards are
  highlighted, others dimmed. The dock keeps a collapsed accessible list.
- Discoveries: the drawn tile is shown as its card with Use / Keep.
- Combat: an enemy ship in the hit prompt is clickable; the battle room and log are
  unchanged, and roll/trade/pass buttons stay in the dock because they have no board
  object.
- Every spatial prompt keeps a collapsed "choose from a list" fallback and the board
  objects are real buttons, so clicking is also the keyboard/touch alternative to
  dragging.

## Baseline and final checks

| Check | Result |
|---|---|
| `pytest tests -m 'not render' -q` | **627 passed**, 25 deselected |
| `pytest tests -m render -q` | **25 passed**, 627 deselected |
| `python -m dev.webui.smoke` | passed; desktop screenshot, Build menu, hotspots |
| `python -m dev.webui.browser_checks` | **18/18 passed** (real Chromium, HTTP, two seats) |
| `python -m dev.webui.direct_checks <flow>` | **11/11 flows passed**: movement, movement-stack, explore, build, upgrade, influence, population, population-neutral, discovery, research, combat |
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
  version; every placed and unexplored ring slot has a position and orientation.
  Zoom, wheel zoom, drag pan and Fit. `view.pieces` exposes ship, planet-square and
  discovery anchors in tile pixels; the overlay draws click targets on them.
  Build/explore/influence/move/population choices become objects; movement drags the
  real ship token and click destinations remain the touch/keyboard alternative.
  Explored tiles preview through `/api/games/{id}/tile.webp`, painted by the engine's
  own art at the offered rotations.
- **Player panels**: resources, activation counters, income/upkeep, tech tracks,
  blueprint slots with part art, public VP, owned systems and reputation. During an
  Upgrade action your blueprint ship and its slots become the click targets.
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
- **Sandbox tools** (`dev/webui/`): `seed`, `scenarios` (combat, movement,
  movement-stack, influence, population, population-neutral, discovery, upkeep,
  scoring, bankrupt, recovery), `smoke`, `shot`, `browser_checks`, `direct_checks`,
  `playthrough`. Fixed seed / rule setup comes from the existing test setup.

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
docker compose -f compose.webui.yaml stop webui
docker compose -f compose.webui.yaml run --rm webui python -m dev.webui.scenarios movement
docker compose -f compose.webui.yaml up -d --wait webui
docker compose -f compose.webui.yaml exec -T webui python -m dev.webui.direct_checks movement
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
- Touch has no pinch zoom and no drag-to-move gesture; clicking the ship, world or
  destination is the touch/keyboard path, and the board pans with one finger.
- Faction ability names come from `data/factions.json`; full rule text lives on the
  faction-board image rather than extracted HTML.
- Bankruptcy prompts are displayed and tested, but resolving a bankruptcy through
  trade/removal end-to-end was not scripted.
- Combat auto-assigns a hit when the engine finds only one legal target; the enemy
  ship click is verified only when the engine actually posts a choice. Rolls, trade
  and pass have no board object and stay as dock buttons.
- Space-scoped choices on the far side of a nebula subsector are placed at the
  parent's painted position; the engine still resolves the subsector id.

## Next task

1. Authentication and remote-host deployment (TLS reverse proxy, WireGuard bind,
   seat tokens) before exposing the UI.
2. One live Discord session to verify the mirror and cross-surface prompt retirement.
3. Optional polish: richer faction ability text, bankruptcy resolution script,
   touch pinch zoom, a scripted retreat/two-choice discovery case.

## Checkpoints

- Branch `mihai/webui`; no push, merge, live save or wave2 access.
- `7b98232` interactive table, board, choices, battle rooms and sandbox tools.
- `fe4f5bf` table/deployment documentation.
- `41daf51` current-phase prompt filtering, history room filter, per-seat faction panel.
- `07c3113` + `54c0a94` + `a0f5199` population labels, smoother board rendering and a
  repeatable sandbox shuffle.
- Direct-interaction pass: board pieces, ship/planet targets, tile preview, build and
  discovery cards, blueprint slots, market research; audit in `INTERACTIONS.md`,
  checks in `direct_checks.py`.
- The preview after the last check sits on the explored tile/influence prompt. Reset
  before baseline checks: `seed` → `up` → `smoke`/`browser_checks`.

## Evidence images

`dev/webui/artifacts/` (Git-ignored) holds the reviewed screenshots:
`final-table.png`, `final-narrow.png`, `final-explore-preview.png`,
`final-upgrade-slots.png`, `direct-movement-*.png`, `direct-build-*.png`,
`direct-influence-*.png`, `direct-population-*.png`, `direct-discovery-card.png`,
`direct-combat-hit-*.png`. All were opened and inspected.
