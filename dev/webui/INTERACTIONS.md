# Direct interaction audit

Reference screenshots (`references/`) show a tabletop: the map, the tech market and
the player boards are the interface. They cannot show behaviour, so the interactions
below are inferred from the game's objects (tiles, ships, discs, planet squares,
blueprints, tech cards, discovery tiles) and from what the Python engine already
offers as legal buttons.

Every direct interaction presses an existing engine button. The frontend never
computes a legal move, target, rotation or price; it only decides which visible
object carries that button.

## Gaps found

| Flow | Current interaction | Natural object | Gap |
|---|---|---|---|
| Movement | Dock buttons: "201" → "Interceptor" → "101"; drag token is a `⇢ interceptor` label at the origin, not the ship | The ship on its tile, then the destination tile | Ships are not selectable; the fake token does not look like the unit; multi-ship selection is a text queue |
| Exploration | Dock buttons for ring slots, then "Option #1/#2/#3"; orientations only in a combined attachment image, not on the target slot | The unexplored ring slot; the drawn tile itself | No on-board tile preview, no rotation, no direct placement |
| Research | Tech market cards are clickable (good), but the same cards are duplicated in the dock; no affordability feedback on the market | Tech card in the market | Duplicate choice surface; unaffordable techs look identical |
| Upgrade | Dock "Interceptor/Cruiser/…" then part buttons grouped in the dock; blueprint art in the player panel is inert | The ship blueprint and its part slots, then the replacement part | Blueprint cannot be clicked; no highlight of the slot being replaced |
| Build | Dock tile button, then unit buttons, then resource-spend buttons | Owned system; then the ship/unit slots in that system | Buildable systems are only listed as text; units are text prices; no cost/affordability cue |
| Influence | Dock tile buttons for add/remove; a tile hotspot exists only when that tile offers exactly one choice | Empty world (place disc), own disc (remove) | Discs cannot be clicked; legal worlds are not marked as "place disc" |
| Population | Dock "Money (tile 201)" text buttons | Empty planet square / orbital slot on the map | Empty planet squares are invisible and not clickable |
| Discoveries | Generic buttons; card art only in the message attachment for the draw | The discovery card and its diamond on the tile | Atlantians' two draws were one button list over one attachment |
| Combat | Roll / assign-hit buttons in the battle room; separated rooms are good | Contested system, enemy ships, retreat destinations | Hits cannot be assigned by clicking the enemy ship; retreat is a text list |
| Turn / pass / upkeep | Dock buttons | None (action choice, not an object) | Acceptable as-is; improve labels/counters only |
| Diplomacy, minor species, trade, bankruptcy | Dock buttons | None / player panel | Acceptable; may reuse player panel later |

## Interaction model

- A button naming a board position becomes a marked object on the board: a whole
  tile, a ship token on its actual snap point, an empty planet square, or the
  discovery diamond. Nebula A/B/C target the wedge label the engine paints, so
  sibling subsectors never share a hotspot.
- A button naming a ship (origin, type, hit target, retreat) attaches to that ship's
  token; clicking the token presses it. Drag uses the same token.
- Tile rotations (`placeTile_*`) become a preview of the real tile image at the
  target slot, cycling only the rotations the engine offered, with keyboard
  left/right, click-to-rotate and an explicit Place/Discard action.
- Blueprint ship/slot buttons attach to the blueprint in the player panel.
- Tech and part buttons attach to the existing tech-market and part cards.
- Buttons with no board object (roll dice, quantity, pass, trade, end turn) stay in
  the dock, styled by their role, never removed.
- Spatial choices also keep a keyboard/screen-reader fallback list in the prompt
  (collapsed by default) and the board objects are real `<button>`s.
- Every press still goes through `/press` with the canonical message id and the
  engine's custom id, so Discord cross-play, stale-button protection and the shared
  lock are unchanged.

## Ordered checklist

1. Foundation: per-tile piece geometry (ships, planet squares, discovery diamond)
   in the view payload; object layer in the overlay; one parser from custom id to
   spatial target; tile-preview and discovery-card art endpoints; tests.
2. Movement: click ship → origin; click ship type → destination options; drag the
   real ship token onto a highlighted destination; stack/quantity control; tests.
3. Exploration: click ring slot; on-board rotated preview; rotate/place/discard;
   keyboard; tests and screenshots.
4. Influence: click a world to place or remove a disc; ghost disc marker; feedback.
5. Population: click empty planet/orbital square; resource-type pick where the
   engine asks.
6. Build: click a system; unit cards with art/cost/affordability; explicit finish.
7. Upgrade: click blueprint ship, click slot, choose part; undo/back preserved.
8. Research: single surface (market); affordable/owned/too-expensive states.
9. Discoveries: card art with Use / Keep.
10. Combat: click enemy ship to assign a hit; roll prominence; battle room unchanged.
11. Full regression: pytest, browser checks, playthrough round/movement/full/combat,
    invalid/stale choices, refresh, second browser, narrow viewport; STATUS.md.

## Status

Items 1–10 are implemented. The engine still decides legality: the frontend only
moves the engine's own button onto the object it names.

Verified with `python -m dev.webui.direct_checks <flow>` inside the container:

| Flow | Object the player uses | Saved outcome asserted |
|---|---|---|
| movement | ship token, then destination world | ship in 101; refresh and second seat agree; a replayed move changes nothing |
| movement-drag | drag the real ship token onto the world | ship in 101 |
| movement-stack | ship token + stack stepper | two interceptors moved |
| explore | ring slot + rotated tile preview + arrow keys | the engine's sector is on the board in the chosen rotation |
| build | system marker + unit picture cards | the second interceptor is in the save |
| upgrade | blueprint ship + slot + part card | the installed part changed |
| influence | world click adds, own disc click removes | owner blue → 0 |
| population | empty planet ghost | money cube saved on the tile |
| population-neutral | grey planet + cube type choice | neutral planet holds the chosen cube |
| research | tech-market card | science spent, tech owned |
| discovery | discovery card art | `disc_tiles_for_points` incremented |
| atlantian-discovery | two drawn cards, then Use/Keep | the chosen ability's science gain is saved |
| nebula | subsector B ship, then the A/C wedge label | the ship is in exactly 207c; A and C targets do not overlap |
| retreat | controlled neighbour in a mid-retreat prompt | the retreating ship left the battle for 201; a replay moves nothing |
| bankrupt | bankruptcy prompt's trade, then Run Upkeep | money covers the shortfall, upkeep runs into round 2 |
| combat | enemy ship token in the hit prompt | the hit target was accepted by the engine |

Choices with no visible object (roll dice, trade, pass, end turn, quantity) stay in
the dock; they are not forced into the board.

Not scripted here: the Ghosts' immediate `Retreat Now` variant and resolving
bankruptcy by removing a sector. Both use the same destination/removal objects.
