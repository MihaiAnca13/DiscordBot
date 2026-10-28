# Isolated Web UI development

Run commands from `/home/mihai/personal/DiscordBot-webui`.
The container contains a dummy config and no Discord token. Only named development
volumes hold saves/feed; the only host bind mount is the screenshot directory.
Source is copied into the image: rebuild after edits. Docker's socket is never
mounted into the container. Do not add live saves or configuration as mounts.

## Build, reset and start

```sh
docker compose -f compose.webui.yaml build
docker compose -f compose.webui.yaml stop webui
docker compose -f compose.webui.yaml run --rm webui python -m dev.webui.seed
docker compose -f compose.webui.yaml up -d --wait webui
```

Open http://127.0.0.1:8099/?seat=1 (blue); seat 2 is red.
Reset only while the service is stopped, so SQLite and saves have a single writer.
The seed deliberately deletes only the two development data directories.

## Checks

```sh
docker compose -f compose.webui.yaml run --rm webui python -m pytest tests -m 'not render' -q
docker compose -f compose.webui.yaml run --rm webui python -m pytest tests -m render -q
docker compose -f compose.webui.yaml exec webui python -m dev.webui.smoke
docker compose -f compose.webui.yaml exec webui python -m dev.webui.browser_checks
docker compose -f compose.webui.yaml logs --tail=60 webui
```

Reset before repeating the smoke test: it changes the demo game. Screenshots and the
result JSON appear under `dev/webui/artifacts/` (ignored by Git). The browser checks
run inside the app container, using real HTTP and Chromium, and cover layout,
zoom/pan, faction/history dialogs, two-seat races, stale replay, refresh and a narrow
viewport.

## Scripted play and fabricated saves

All of these run with the service **stopped** when they reset the sandbox:

```sh
docker compose -f compose.webui.yaml stop webui
docker compose -f compose.webui.yaml run --rm webui python -m dev.webui.seed
docker compose -f compose.webui.yaml up -d --wait webui
docker compose -f compose.webui.yaml exec -T webui python -m dev.webui.playthrough round
```

Scenarios reach later phases quickly; each wipes the two development volumes first:

```sh
docker compose -f compose.webui.yaml stop webui
docker compose -f compose.webui.yaml run --rm webui python -m dev.webui.scenarios combat
docker compose -f compose.webui.yaml up -d --wait webui
docker compose -f compose.webui.yaml exec -T webui python -m dev.webui.playthrough combat
```

`combat`, `movement`, `movement-stack`, `influence`, `population`,
`population-neutral`, `discovery`, `atlantian-discovery`, `nebula`, `retreat`,
`upkeep`, `scoring`, `bankrupt` and `recovery` are available.
`python -m dev.webui.playthrough round|movement|full|combat` drives the prepared game
through the live HTTP surface; `full` plays a pass-only game from round 1 to the final
score screen. `python -m dev.webui.shot <url> <name>` saves desktop and narrow
screenshots plus a JSON error report; `python -m dev.webui.smoke` is the minimal
build-menu check.

## Direct interaction checks

Each flow clicks the visible object (ship, ring slot, planet square, blueprint, tech
card, discovery card) and then asserts the engine's saved state changed. Prepare a
flow's scenario first; the checks never fabricate an action, they press the buttons
the engine offered.

```sh
docker compose -f compose.webui.yaml stop webui
docker compose -f compose.webui.yaml run --rm webui python -m dev.webui.scenarios movement
docker compose -f compose.webui.yaml up -d --wait webui
docker compose -f compose.webui.yaml exec -T webui python -m dev.webui.direct_checks movement
```

Flows: `movement`, `movement-drag`, `movement-stack`, `explore`, `build`, `upgrade`,
`influence`, `population`, `population-neutral`, `discovery`, `atlantian-discovery`,
`nebula`, `retreat`, `bankrupt`, `research`, `combat`.
Use `seed` for the setup-less flows. `combat` drives both seats and needs a hit
prompt; the check reports `skipped` when the rolled dice never offered a choice.

## Inspecting references

`references/` holds the layout references used for the table, research dialog,
upgrade dialog and faction panel. They were inspected before the visual work; the
screenshots in `artifacts/` are the evidence of the browser result.

## OpenCode + DeepSeek

Configure your chosen DeepSeek model in OpenCode as usual. From this worktree run
`opencode`, select it with `/models`, and send:

> Read dev/webui/AGENT.md and execute its milestones. Keep working through the
> implement/test/browser-inspect/fix loop. Maintain dev/webui/STATUS.md so another
> session can resume. Start by checking the baseline and inspecting the references.

For a noninteractive run, use your configured provider/model identifier:

```sh
opencode run --model 'PROVIDER/MODEL' --title 'Eclipse web UI' 'Read dev/webui/AGENT.md and execute its milestones. Maintain dev/webui/STATUS.md with verification evidence and continue until complete or blocked.'
```

Run inside tmux if it must survive terminal disconnection. The computer must stay
awake. Model limits or an agent ending its turn can stop work; resume the same
session with `opencode run --continue 'Read dev/webui/STATUS.md and continue the next incomplete milestone from dev/webui/AGENT.md.'`.
There is no unlimited automatic restart loop. Review the first milestone before
leaving a long run unattended. Docker isolates the app, not the host agent: the
agent's host permissions still matter. Leave normal OpenCode permissions enabled.

## Stop

`docker compose -f compose.webui.yaml down` stops development; volumes persist.
No command here stops or changes the separate wave2 bot.

### Live code changes

The dev container mounts source folders from this checkout. Python edits restart
the server automatically within a second; refresh the browser for HTML, CSS, or
JavaScript changes. Game saves and feed data persist across restarts. Dependency
or Dockerfile changes still require `docker compose -f compose.webui.yaml up -d --build`.
