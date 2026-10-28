# Web UI guidelines

These guidelines come from refining the development web UI alongside the Discord bot.

## Reuse the bot

Reuse the bot’s game rules, action handlers, drawing code, reference text and icons.
The web UI should arrange that content and add interaction around it.
Do not recreate player boards, technology trays or faction references as custom menus
when the existing presentation already works.

## Put controls on their targets

Place controls near the object they affect:

- Rotation buttons on the explored tile.
- Influence targets sized to the sector’s center circle.
- Population targets on the corresponding planet, labelled with its resource type.
- Research targets directly on the rendered technologies.

Get overlay coordinates from the renderer rather than maintaining a separate layout.
Keep legality and costs in the shared game handlers.

## Preserve the artwork

Use transparent targets, outlines and glows. Hover must not obscure the image.
Avoid duplicate labels, decorative symbols and floating menus when a small control suffices.
Use a compact popup for a secondary choice such as a technology track, with clear names,
track colors and the bot’s discounted science costs.

## Make state transitions complete

- Restarting a turn must retire choices from the abandoned actions.
- Research must expand and open the market, then return it when choices finish.
- In the dev build, follow the active seat after actions and page refresh, while preserving
  manual seat selection during background updates.
- Keep the selected player’s board first.
- Preserve collapsed board states across updates.

Showing an old prompt as actionable is a behavior bug, not merely a display issue.

## Keep layout compact

Use existing rendered boards at a useful size. Remove unnecessary wrapper padding and gaps.
Offer individual and collective collapse controls for player boards.
Keep important status information visible and aligned; use a readable capsule for the S3 count.
Use short collapse animations and respect reduced-motion preferences.

Enable zoom where it materially helps, such as parts reference and the compact tech market.
Disable it where it adds little or conflicts with selecting an action.
Keep popups sized to their contents and avoid unnecessarily obscuring the page.

## Watch shared styles and rendering behavior

Check how generic button, hover and dialog styles affect specialized controls.
A global hover fill must not cover an image target; a small picker must not inherit a large
reference dialog’s dimensions.

Coordinate image and overlay loading. Reserve image dimensions while loading and prevent
concurrent requests from writing the same temporary cache file.

## Work from the reported behavior

Clarify the specific interaction before changing it. For example, reversed rotation direction
does not imply that skipping illegal orientations is wrong.

Use separate disposable games for checks; do not advance the user’s game to verify a handler.
For visual refinements, make a small change and let the user check first. Use browser checks
or focused tests when a reported problem calls for investigation, rather than after every edit.

These are observed patterns, not a complete audit of the UI or its action flows.
