# Adding a community faction

The process this repo follows to add a faction from `community-races/factions/<name>/` to the bot,
and the pitfalls that have actually bitten us. It is kept generic on purpose: a faction's numbers
belong in `data/factions.json`, its home in `data/sectors.json`, its rules text in the commit, and
its behaviour in its tests. The `add-faction` skill's `CHECKLIST.md` mirrors this process; if the
two disagree, this file wins and both get updated.

A faction is done when its own tests pass, the verification pass below has come back clean, every
throwaway probe has been triaged, and the sandbox playtest (step 8) has come back with no open bugs.

## The process

1. **Inventory the source folder before planning.** List it and write down what exists. Mixed
   `.jpg`/`.png`, missing assets and themed file names are normal: the rules card can be `*Back`,
   the board can have no suffix, the tile can be `*Sector` and the emblem `*Token`. Identify each
   file by what is in it (the card with the ability boxes is the info card) and record the mapping
   in the commit message. If something the implementation needs is missing, ask; never improvise
   an asset.
2. **Read the rules images yourself, verbatim.** Crop at native resolution and zoom; write down
   setup resources, colony ships, technologies, sector contents, activations, trade value,
   reputation track and every ability's exact wording. Do this for every image that carries rules
   text — some factions ship several info pages. In parallel, delegate a second transcription as a
   cross-check and tell the delegate to flag anything illegible rather than normalise it. Flag
   disputed readings instead of guessing. Give every ability a row in a timing table: trigger
   (setup, pre-game, own turn, a named action, combat start, each die, upkeep, end of game),
   limit (once, per die, per round, unlimited) and who it applies to. Fill each cell from the
   wording; a blank cell is a reading to record, not a default.
3. **Decode the board against an implemented board of the same template.** The differences are the
   rule deltas: reputation-slot frames (ambassador frame present, absent, or mixed), the bubble
   above an action circle (how many colony ships an Influence action flips), printed glyphs and
   starting technology icons. None of that is written on the card.
4. **Reconcile against the base rulebook and the existing code.** Check the rulebook for whatever
   base mechanic each ability modifies, then grep for the closest existing flow *before* writing
   anything. Route the ability through that flow; only add shared logic when the grep comes up
   empty. Write down the shared state machines each ability can reach, as plain-language risk
   guesses, and put them in the commit message with the flow each ability reuses.
5. **Implement in independent chunks.** Data entry, home tile, artwork, selection wiring, each
   ability, tests: fan the non-overlapping chunks out to parallel fast subagents, giving each one
   the transcribed rule text, the flow to reuse, and the exact constants (snap coordinates, crop
   boxes, pixel sizes) measured by you rather than by the worker. Anything touching a shared state
   machine (population, prompts, scoring, draft/colour, setup hooks, ship costs) stays with the
   lead or goes to exactly one worker. Any chunk that touches a risk guess also gets one throwaway
   probe test aimed at that edge case, clearly marked. For every non-trivial branch, one real test.
6. **Review the merged diff against `AGENTS.md`.** A new abstraction with one caller, a parallel
   path where an existing flow would do, dead buttons or state from an earlier design. Where an
   ability was routed into an existing flow, confirm that flow's validation and error handling
   still cover the merged-in case.
7. **Verify with a second, separate pass.** It checks, it does not build. In parallel:
   - rule accuracy: the transcribed rules and board readings next to the code, including every
     exclusion or narrowing an earlier review added, re-read against the exact wording;
   - regression: diff against the base branch, grep the callers of every shared file touched,
     confirm other factions are unchanged, run the *full* suite including the probes, and check
     the draft, colour allocation and setup hooks;
   - probe triage: a probe that failed found a real shared bug — fix it and keep the test without
     its throwaway marker; a probe that passed is deleted;
   - assets: every referenced artwork path exists and matches its source (pixel or hash compare,
     not just dimensions), and this doc is still generic with any new shortcoming folded in.
8. **Playtest in the sandbox.** Run the `faction-playtest` skill: agents draft the faction in the
   web UI sandbox, compare the rendered home tile, player area and blueprints with the board, fire
   each ability and read every message it posts. Tests stub the art and fake Discord, so this is
   the only check of the picture and the text. Without the skill, at least render the first-round
   save through `webui/render.py` (`render_board` / `render_panel`) and check it by eye.
9. **Report.** What was added, which flow each ability reuses, what the checks found, the readings
   taken where the card was silent, and only the questions that pass the gate in
   [Questions for the human](#questions-for-the-human).

Work from the latest base branch and commit as you go. Before the final report, merge the base
branch again and re-check the wiring against anything that moved: draft rules, setup sends and
shared helpers have all shifted under a faction before.

## Where things live in this repo

| Piece | Location |
|---|---|
| Faction data and shared facts | `data/factions.json`, read through `helpers/FactionData.py` |
| Home sector data | `data/sectors.json` |
| Home tile art | `images/resources/hexes/<id>.png`, plus `hexes/numberless/<id>.png` when the printed number must go |
| Shared artwork | `images/resources/components/factions/`, `layouts/factionImages/`, `layouts/faction_titles/`, `layouts/blueprints/classes/` |
| Setup command and faction list | `commands/setup_commands.py` (`factionChoices`, autocomplete) |
| Reference-thread text | `helpers/FactionReference.py` (hand-written per faction: rules as text plus the board file name; the board is the only image posted) |
| Draft, colours, pagination | `Buttons/Draft.py` |
| Pre-game setup actions | `Buttons/PreGame.py` (`tasksForPlayer`) |
| Population paths | `Buttons/Population.py`, `helpers/GamestateHelper.remove_pop`, `helpers/PlayerHelper.upkeep` |
| Prompt resolution | `listeners/ButtonListener.py` (`ANSWER_BUTTONS`) |
| Drawing | `helpers/DrawHelper.py` (`player_area`, `faction_portrait`, `draw_blueprint_slots`, `draw_tech_track`, `board_tile_image`) |
| Display sizes | `helpers/ImageCache.py` (`get_image_size`) |
| Tests | `tests/`, including the per-batch first-round tests |

Selection is data-driven: `"community": true` and a `"setup_color"` make an entry visible only with
`community_factions` enabled, respect drafted-away factions and bans, and neither cause nor receive
colour blocks. `SetupCommands.factionChoices` is a separate hardcoded list and a test keeps it in
sync with the data. The draft's 25-button paging and the setup command's autocomplete already exist;
don't re-add them, don't regress them.

Colours: new ones are unsupported. Use an existing setup colour; a community faction may share one
with a standard faction and setup hands the second one a free colour.

## Faction facts in the data

Shared facts and reusable capabilities belong in `data/factions.json` and are read through
`helpers/FactionData.py`. Reuse an existing field when it fits; don't invent a shape for a
hypothetical faction. The fields in use:

| Field | Read by | Meaning |
|---|---|---|
| `artwork` | `FactionData.artwork_name` | image/emoji/blueprint key (the data key and artwork key may differ) |
| `name_aliases` | `FactionData.BY_NAME` | optional old names that resolve to the same facts and artwork |
| `setup_color` | `DraftButtons.getColor` | colour the draft hands the faction |
| `community` | `DraftButtons.getDraftButtons` | draft only with `community_factions` on |
| `starting_ships` | `GamestateHelper.setup_finished` | ships on the home sector at setup (default `["int"]`) |
| `influence_colony_ships` | `Buttons/Influence.py`, `DrawHelper.player_area` | colony ships one Influence action flips (default 2) |
| `reputation_track` | setup, `GamestateHelper` relation code | one `mixed`/`rep`/`amb` entry per printed slot |
| `reputation_only_slots` | `PlayerHelper.is_reputation_only_slot` | reputation-track indices with no ambassador slot; must name exactly the `rep` entries of `reputation_track` |
| `<ship>_parts` | setup, `DrawHelper.player_area` | one entry per printed slot in the standard slot order (see Drawing), `empty` where nothing is printed |
| `blueprint_slots` | `DrawHelper.draw_blueprint_slots` | per ship, one `[column, half-row]` cell per parts entry when the printed slot shape is not the standard one |
| `portrait_image` | `DrawHelper.faction_portrait` | use `factionImages/<art>_image.png` instead of the standard board crop |
| `abilities` | `FactionData.has(player, "...")` | named abilities the implementation is guarded by |
| `vp_per_*` | `DrawHelper.get_public_points` | end-of-game points per owned tile, artifact tile, shrine, orbital population, Ancient ship, centre |
| `tech_track`, `tech_track_max`, `tech_track_vp` | `FactionData.tech_track`, `tech_track_max`, `tech_track_vp` | printed research discount by tiles already on the track, track length when it is not seven, end-game VP by tile count |
| `midas_touch_costs` | `TurnButtons.midasTouch` | money costs per action for the paid extra activation |
| `call_to_arms_materials` | `GamestateHelper.destroy_ship` | materials per ship type destroyed while the sector is not yours |
| `tech_masters_extra` | `ResearchButtons.calculate_cost` | the first wrong-tray extra and the step added to each later use |
| `discovery_part_vp`, `discovery_part_ship_cost`, `money_trade_ratio`, `reputation_draw_money` | scoring, `PlayerHelper.get_ship_cost`, trade and reputation flows | the named number where an ability is a count |

An ability whose behaviour is an existing flow (a research discount, a discovery choice, a
reputation draw) keeps its implementation where that flow lives; the code only asks whether the
player has it. Grep for `FactionData.has` before inventing an id. Numbers a faction accumulates
during play live on the player instead, as fields setup copies in for that faction only.

Population cube counts are not printed: every track starts at 12 per resource minus one cube for
each cube setup places on the home sector, including an Advanced square that a starting technology
unlocks. Verify against the other factions rather than copying a number.

`starting_ships` does not decrement `ship_stock`: set the stock to the physical count minus what
setup places.

## Gotchas, grouped by area

### Reading the rules

- **Filed names do not say what the file is.** Identify by content, record the mapping.
- **The card can overrule the board's blueprint.** A card that says "Standard Ships" wins over a
  printed slot that would leave a ship without a weapon. Copy the standard parts array and flag the
  print in the report.
- **A printed tech track's first cell can be blank.** A blank first cell is the starting-tech space
  and reads as a 0 discount. Identify glyphs on a board whose values are known — a board font can
  draw several digits alike. Don't copy a neighbouring faction's array because the row looks the
  same. Arrays are indexed by tiles already on the track, so a track read left to right is entered
  right to left; verify the first-tech discount against the board.
- **A printed quantity with no verb may be a replacement.** A bare number next to an action can
  replace the standard value rather than add to it. Compare the same spot on an implemented board.
- **Slot types are art, not text.** Reputation-only, ambassador-only and mixed slots differ only in
  the frame: a plain gold shield, a notched frame with a hex fill, and a shield inside that frame.
  A thin outline hugging the shield is not the notched frame. Compare against a board whose data is
  known, not against a description.
- **Two readings can both be wrong.** Settle a disputed number with a sharpened high-zoom crop or
  by template-matching the glyph against a board whose value is known.
- **Do not narrow an ability beyond its text.** Check every exclusion against the exact wording and
  flag it rather than deciding it.
- **Silence on timing is a decision.** Where card and board are both silent (timing, "any type"),
  write the reading down and flag it in the report.
- **Do not add limits the text lacks.** "Once", "only when defending", "only your own dice" are
  narrowings like any other: an ability that answers a die answers every die it can see, rerolls
  included, unless the wording says otherwise.
- **A card's resource word is usually a base-game quantity.** Before inventing a counter that is
  spent and refilled, check whether the word (Power, energy, souls) matches an existing stat such
  as blueprint energy, colony ships or influence. A permanent bonus read as a spendable pool
  changes every fight, and the costs it pays may come from spare blueprint energy first.
- **"The X action" is not every way to do X.** Pulsar builds and moves, free activations granted by
  another ability, `/move` and similar commands enter the same flow. Decide from the wording which
  of them trigger the ability and check each entry path (flags such as `pulsar_build`).
- **The setup line on the card is an ability.** "Start with", "place", "choose" before round one
  needs a pre-game task; a recurring choice (each upkeep) needs its own hook, not a pre-game one.

### Home tile and sector data

- **The source may not be a hexagon on black.** Some factions ship a full-bleed scene: reconstruct
  the hexagon from the straight clips printed across the art and keep the canvas inscribed so the
  tips survive. The cache resizes every tile to 1024×890, which is the target; shipped files vary
  by a few pixels.
- **Printed ring marks are not automatically population squares.** They can be artifact-key markers
  while the real squares sit elsewhere; the card's Starting System icons give the square types.
  Setup fills every non-advanced home *resource* square with a cube (plus any Advanced square a
  starting technology unlocks) whether or not the art prints one, and the population tracks drop by
  the same count. A neutral square is a neutral planet and stays empty.
- **Plain or advanced is printed per square.** Read each square's frame on the tile art; the
  card's icon count does not say which square is advanced. A square that a starting technology
  does not unlock starts empty.
- **Snaps are centres.** Each `<type><n>_snap` is the centre of its printed square, not a corner
  or a ring mark, and every ship snap (`int`, `cru`, `drd`, `sb`, `orb`, `mon`) lies inside the
  hexagon. Check by rendering the tile with every square filled and every ship type placed.
- **A nameplate can sit over a population square.** Then the tile needs a numberless variant plus a
  per-tile `number_snap`, or the banner covers a square or a second printed number shows.
- **The tile number box.** Without a numberless variant, `images/resources/masks/banner.png` is
  pasted over the printed nameplate. Home art with no nameplate there shows the box as a cutout.
- **A home sector number can already be taken.** Use the printed number only if it is free, else
  pick a free sector and say which number the bot uses in the reference text. Never renumber a
  faction already in play.
- **Held sectors need two counts.** A reserve held off the board must be excluded from the
  outer-rim cleanup *and* included in the explore-position enumeration, or the last held tile
  becomes unplaceable when its deck empties.

### Artwork

- **Derived artwork is not shipped.** Expect to compose the title and class images from the board,
  and verify them where the game draws them.
- **Class images are committed large and shown small.** They are 300×115 (dreadnought 315×148),
  transparent, with a white silhouette, a two-line class name and initiative chevrons; the cache
  shrinks them to 90×33 in the player area. Compose from the board's own stencil lettering and
  reuse the white glyphs; the chevrons are the base initiative, not the total printed next to the
  initiative arrow. Check the name at paste size and outline light headers darkly.
- **A custom blueprint panel is not the shared template.** Only `blueprint_<ship>` files are
  resized to the paste area.
- **Every ship part needs its own upgrade icon.** `player_area` loads `upgrades/<part name>.png`; a
  tech-card image is not it.
- **An ambassador source can be two-up.** A two-up sheet on an opaque field renders as two tiny
  cards on a grey square. Crop one tile and apply the same alpha shape as the existing single-tile
  art.
- **A new faction has no emoji token.** Its token falls back to a placeholder until one is
  uploaded. Cosmetic; note it, don't spend the task on it.

### Drawing the player area

- **Rules the board prints must reach the player area.** `DrawHelper.player_area` draws some board
  numbers from data and some from hardcoded faction lists; an ability that changes the latter needs
  the drawing updated too. A number that lives in both rule and drawing belongs in `factions.json`.
  A counter the faction accumulates (a dial, a die on the board) needs drawing as well.
- **A non-standard tech track pastes the board's own tray.** `draw_tech_track` crops the tray from
  the 4400px `<art>_board.png` at fixed coordinates and skips the starting technologies the board
  already prints. A board that is not the standard template needs its crop measured. Check that
  the picture and the research menu's discounts agree.
- **Parts arrays follow the standard slot order.** `DrawHelper.player_area` places entry *n* of
  `<ship>_parts` on the standard template's slot *n*: top row left to right, bottom row left to
  right, then the extra corner slot. Count the printed slots including empty ones and write
  `empty` where nothing is printed. A special part printed in a standard slot (a hull-like part,
  say) goes in that slot of the standard array.
- **`blueprint_slots` is the last resort.** Overlay the standard template on the printed blueprint
  first; a reordered parts array fixes most mismatches. Use `blueprint_slots` only for a shape the
  template cannot show, never as name branches or coordinate overrides.
- **The reputation track is two fields.** `reputation_track` and `reputation_only_slots` must agree
  slot by slot, and both must match the frames on the board.

### Setup and the draft

- **A card action can happen before the first turn.** Declare the capability in data, add the task
  to `PreGameButtons.tasksForPlayer`, and route it to the flow that already does that thing.
  Advance the task only after a successful action and return the next task name when a follow-up
  choice is needed. The game waits for it, so the prompt must be completable on its own and must
  not offer a turn-only button — there is no turn to go back to yet.
- **Reusing a turn flow for a setup hook.** Turn actions carry turn-only parts (the "using their
  turn" message, trading for the cost, Finish/Restart). Gate them with a flag rather than copying
  the flow.
- **A new mode of a shared flow needs that flow's Undo.** A once-only guard otherwise refuses the
  retry after a misclick.
- **A starting technology's passive still applies.** Setup copies starting techs into the track
  without `playerResearchTech`, so an action-count bonus must be applied in `player_setup` too.
- **Press the colour setup actually assigned.** `generalSetup` hands out colours in `getColor`
  order with a `pop(0)` fallback, so the faction's colour depends on who else is in the game; a
  test copied from another faction can press the wrong colour and silently no-op.

### Abilities and shared state machines

Check each machine the faction touches by hand and with a test: population placement and removal
(`findEmptyPopulation` / `findFullPopulation` / `remove_pop` / upkeep graveYard / elimination /
population-gone), prompt resolution (`ANSWER_BUTTONS`), scoring, the draft and colour allocation,
setup hooks (several factions can be drafted into one game), the Influence action's colony-ship
refresh, and ship cost/upgrade paths.

- **Extra population locations.** A cube on the influence disc or another non-planet location needs
  a tile field, drawing at that location, the normal track bookkeeping, and the return path so
  losing the sector, combat hits, elimination, the upkeep graveYard and the population-gone check
  all handle it. List it in `findFullPopulation` and check `remove_pop` and `upkeep`.
- **A displayed action count must be enforced.** Activation numbers are not labels: cap the
  placements, removals or units, including later presses.
- **A built-in part slot must be excluded from upgrades.** Otherwise the player gets the module and
  a free replacement.
- **Income from a placed piece must be counted before bankruptcy.** Apply it before the check, or a
  player is wrongly forced to trade or remove control.
- **A destroy hook only sees combat removals.** Ships removed by another effect (a black hole, a
  board cleanup, the editor) don't pass through `destroy_ship`. Decide from the wording whether
  they count and route them explicitly, or record the narrower reading.
- **Check the body of a shared flag, not its name.** A flag may do more than its name suggests; a
  faction whose wording removes more needs its own guard in the shared function.
- **Check the shape of a lookup table a new branch adds.** A value that should be a list of ids but
  is a string is iterated character by character and silently passes an `any()`/`all()`.
- **Changing a shared button id breaks live games.** Posted buttons keep their old `custom_id`, so
  a parser expecting an extra field must still accept the old shape.

### Combat

- **"At the start of each combat" is `Combat.startCombat`,** which reruns for every new pairing on a
  multi-player tile — not `startCombatThreads`, which runs once per tile. Temporary state the
  ability installs must come off at the next `startCombat` and in `declareAWinner`.
- **An engagement-round counter must coexist with the first-shot phase.** With a first-shot faction
  in the game the phase switch also ends a pass; increment only when the phase is over (or absent)
  or the ability fires in the wrong round.
- **"Make the attacker reroll" is a deferred defender prompt.** Store the die's parameters with a
  token on the tile, keep the hit unassigned while pending, let the defender answer, and close the
  pairing from the resolver when the last pending entry is answered. A reroll re-derives hit and
  damage from the stored computer/speed.
- **A deferred hit still has to close the pairing.** A target button whose resolution is deferred
  must still run the end-of-combat check when it removes the last ship of a side.
- **Initiative changes need every speed path.** Apply them in the speed enumeration, the manual
  button validity check, the reroll path and the end-of-combat checks.
- **A free activation's filter belongs in the next button id.** Put a class restriction into the
  emitted `moveFrom` id and test the id the UI emits.
- **A no-combat bombing prompt still needs the weapon/power choice.** Offer it rather than claiming
  a combat-start declaration covers the case. A sector cleared that way still owes the influence
  and population prompts that every other way of clearing a sector offers.
- **Per-die modifiers apply before a split.** `Combat.die_damage` is the one place that turns a face
  into hits; a reduction applied after an Antimatter split hits every fragment instead of the die.
- **Reroll prompts chain.** One faction's reroll is a new die for another faction's die ability.
  Keep the full die context (computer, speed, damage bonus, split, shield, ship) in the pending
  entry so either side can answer the rerolled die.
- **The AI assigns hits on its own path.** A defensive ability must hold when the AI is the
  attacker (`Combat.ai_target`, the salvo allocation), not only when a player picks the target.

### Prompts, menus and buttons

- **New answer-style prompts.** A prompt that resolves once must be added to `ANSWER_BUTTONS` and
  its handler must refuse a second resolution on its own.
- **A free activation inside another action must resume it.** Return to the Build or Move menu (or
  finish the action) and allow exactly one upgrade.
- **A sub-flow that spends one activation must not hide the rest.** After the swap, offer the
  remaining normal activations; a view with only "again" or "finish" traps them. Returning from it
  must keep the activation count (no reset that lets the player exceed it) and must not add a
  second Finish button.
- **A new guard in a shared function breaks odd callers.** Commands and free activations call the
  same function with unusual arguments (a move count of 8, a build with no action). Grep every
  caller, slash commands included, before tightening a check.
- **A recurring choice with one legal answer resolves itself.** Prompting every upkeep for a forced
  choice stalls the round; apply it and say what was done.

### Messages

Tests fake Discord, so nothing checks the words. The playtest reads them.

- **Announce every declared choice and every bonus with its parts.** When a player picks a mode or
  an option, or an ability changes a roll, the public message names it; a total says what it is
  made of (blueprint +1, ability +2) and why an ability that might apply did not. Another player
  must be able to audit the roll from the channel alone.
- **Dice are dice emoji, components are emoji.** A die face goes through `Combat.die_face`; parts,
  resources and tokens through `Emoji.getEmojiByName`. A bare number where a die is meant, or a ❓,
  is a bug. The sandbox web UI names dice and tokens as `:dice_red_6:` text so the check is
  possible without Discord.
- **A prompt states the budget it spends.** "Colony Ships available: 2", "Power left: 1".
- **The reference text is code.** `helpers/FactionReference.py` is hand-written per faction; compare
  its setup, starting-sector line and ability text with the transcription. A loop that prints
  several factions' lines can repeat one faction's planets under another's name.

### Live games and saves

- **A data fix does not reach running games.** Setup copies faction data into the player, so a later
  fix to `factions.json` changes new games only. Migrate on load (as `PlayerHelper.sync_blueprint_slots`
  pads blueprints) or say the fix needs a new game. A new field needs a default that keeps old
  saves behaving as before.
- **Buttons must survive a restart.** A `View` with Python callbacks dies with the process; post plain
  `custom_id`s that `ButtonListener` answers.
- **A per-faction branch must not cost every faction.** A save or render added to a shared path for
  one faction's reset runs for everyone; keep it inside the faction's condition.

## Questions for the human

Most questions an agent raises are answered by reading more carefully. Before a question reaches
the human it must pass all four checks; otherwise the agent settles it and lists the reading under
"Readings taken" in the report.

1. **Re-read.** The exact card text, a zoomed crop of the board region, the home tile, and the
   reference text. Quote what was read.
2. **Rulebook.** `rulebook.md` does not define the term, timing or limit.
3. **Precedent.** No implemented faction with the same wording or icon settles it (grep
   `data/factions.json` and `helpers/FactionReference.py`).
4. **It matters.** Both readings fit the verbatim text and lead to different play.
5. **Not already the natural reading.** If the code does the plain reading and an implemented
   faction does the same (off-board bonuses work like Planta's; an ability that restates a printed
   number restates it; "X is worth -4" replaces the base value), it is a reading taken.

A board value read differently from the data is not a bug yet. Readers misread frames, slot
counts and the tech track; the shared default is usually right. Re-crop the region beside an
implemented board of the same template, count the cells, and call it a bug only when the
comparison shows a real printed difference from the default. Timing that the code implements on
purpose through an existing phase (pre-upkeep for "end of turn") is a reading, not a bug.

Ask in one shape: the quote, reading A, reading B, what the code does now, the recommended
default. At most three per faction, ranked by how often the difference comes up in play; the rest
take the recommended default and are listed as readings taken.
