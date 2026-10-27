# Web UI build brief

Work only in `/home/mihai/personal/DiscordBot-webui`, branch `mihai/webui`.
Read the root AGENTS.md, webui/README.md and this directory's README.md first.

Build a polished, playable Eclipse web interface. Use the images in references/
as layout and interaction references: board and tech market on the left, readable
player panels on the right, focused research/upgrade dialogs, separate combat
views, and faction reference panels. Reuse this project's artwork and rules.
Inspect the reference images with your image tool before making visual choices.
If your model/tools cannot inspect images, record that limit explicitly; use DOM
and browser checks, save screenshots for human review, and never claim visual review.

## Requirements

- The existing Python engine remains authoritative. Do not duplicate game rules
  in JavaScript or invent legal choices that the engine has not offered.
- Make this a game interface, not a reskinned chat log. Show current actionable
  prompts prominently; move completed actions into a separate History view.
  Keep each battle's history within its combat room. Preserve underlying feed
  records and canonical IDs; hiding history must not delete cross-play state.
  Consumed buttons must disappear on both surfaces and stale requests must not
  award resources or points again, even after an intervening action or refresh.
  The current 80-message view limit must not make older unresolved prompts
  inaccessible: fetch pending choices independently of paginated history.
- Discord/browser cross-play is essential. Actions, edits, deletions, used prompts
  and private messages must remain consistent across both surfaces. Preserve
  canonical message IDs and the shared game lock. Extend existing automated
  recording/transport tests when changing these paths.
- The eventual frontend runs on another host, connecting to the bot API over
  WireGuard. Keep API access centralized and use relative URLs compatible with a
  reverse proxy. Only the bot process writes saves. Document deployment needs;
  don't configure the user's hosts or tunnel.
- Focus effort on browser appearance and gameplay. Real Discord tests are a
  later milestone, not a reason to stop browser work. Do not claim live cross-play
  is verified by fakes.
- Never read or modify sibling worktrees, live saves, credentials, the wave2 bot,
  host services or OpenCode configuration. Never launch main.py or connect to
  Discord. Use only the Docker sandbox for app execution and tests.
- Do not publish, push or merge. Do not enable an unauthenticated public endpoint.
- Complete one milestone before moving to the next. Keep a local Git checkpoint
  commit after each verified milestone, containing only this task's changes.
  Preserve the existing setup and bug fixes. Never reset or discard other work.

## Order of work

1. Run the baseline checks and inspect the current UI in Chromium.
2. Board layout, zoom/pan, player panels, tech market and faction reference.
3. Complete research and upgrade flows with visual choices and clear feedback.
4. Build, explore, influence, population, movement and passing. Add drag movement
   only after the equivalent click flow works; keep a click/touch alternative.
5. Combat rooms: separate each battle's state/history and available actions while
   preserving the room identity needed by Discord cross-play.
6. Refresh/recovery, private prompts, stale buttons and multiple browser seats.
   Verify a complete two-player round, including upkeep, and scripted combat;
   test that two browser sessions observe the same action without duplicate effects.
7. Document authentication, notification and remote-host integration work still
   needed. Never present deferred work as implemented.

## Repeat until each milestone is complete

Choose a small complete flow -> implement -> rebuild Docker -> reset demo -> run
rule/transport tests -> drive the real browser -> inspect screenshots -> fix
failures -> update STATUS.md with evidence and the next step. Keep working through
the milestones without asking for routine approval. Do not stop after a plan.

Add resettable scenarios and browser tests for each new flow. Check actual saved
state, not just a button disappearing. Include invalid/stale choices and private
seat isolation where relevant. Keep rule regression tests and browser tests
independent enough to catch a wrong implementation.

Run all existing tests before declaring completion. Capture desktop and narrow
viewport screenshots, inspect them, and resolve console/server errors. Update
browser selectors when redesigning the UI, preserving their behavioral checks.
Do not weaken assertions to make failures pass.

Use STATUS.md as a durable handoff after interruptions. Record exact commands,
passed/failed checks, unresolved limitations and the next task. If an external
dependency blocks one feature, record it and continue independent work. If the
same failure repeats without progress, report it instead of looping indefinitely.
