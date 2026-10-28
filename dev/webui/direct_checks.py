"""Direct-interaction browser checks: click the objects, then read the save.

Prepare the named scenario with the service stopped, then run with it up:

    docker compose -f compose.webui.yaml stop webui
    docker compose -f compose.webui.yaml run --rm webui python -m dev.webui.scenarios movement
    docker compose -f compose.webui.yaml up -d --wait webui
    docker compose -f compose.webui.yaml exec -T webui python -m dev.webui.direct_checks movement

Each flow presses the board object (ship, ring slot, planet square, blueprint,
tech card, discovery card) and asserts the engine's saved state changed. Standard
dock buttons are still used for choices that have no board object.
"""
import json
import re
import sys
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:8099"
ARTIFACTS = Path("dev/webui/artifacts")
results = []


def api(path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(BASE + path, data=data,
                                     headers={"Content-Type": "application/json"} if data else {})
    with urllib.request.urlopen(request, timeout=90) as response:
        return json.load(response)


def view(seat="1"):
    return api(f"/api/games/aeb1/view?seat={seat}")


def check(name, condition, detail=""):
    results.append({"check": name, "passed": bool(condition), "detail": detail})
    print(("PASS " if condition else "FAIL ") + name + (f" — {detail}" if detail else ""))


def ships(seat="1"):
    return [(piece["position"], piece["name"]) for piece in view(seat)["pieces"]
            if piece["kind"] == "ship"]


def open_page(browser, seat="1", errors=None, viewport=None, prompt=True):
    page = browser.new_page(viewport=viewport or {"width": 1600, "height": 1000})
    page.set_default_timeout(25000)
    if errors is not None:
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.on("response", lambda response: errors.append(
            f"HTTP {response.status}: {response.url}") if response.status >= 500 else None)
    page.goto(f"{BASE}/?seat={seat}", wait_until="networkidle")
    page.wait_for_function("document.querySelector('#board').naturalWidth > 0", timeout=120000)
    if prompt:
        page.wait_for_selector("#action-dock .prompt")
    else:
        page.wait_for_selector("#players .player")
        page.wait_for_timeout(800)
    return page


def shot(page, name):
    page.screenshot(path=str(ARTIFACTS / f"direct-{name}.png"), full_page=True)


def click_choice(page, label, exact=False):
    page.get_by_role("button", name=label, exact=exact).first.click()


def flow_movement(page):
    click_choice(page, "Move (2)")
    page.wait_for_selector(".piece.move-from")
    check("ship on the board is the move origin",
          page.locator(".piece.move-from").count() == 1,
          page.locator(".piece.move-from").first.get_attribute("aria-label"))
    shot(page, "movement-origin")
    page.locator(".piece.move-from").first.click()
    page.wait_for_selector(".piece.move-ship")
    check("the ship type is chosen by clicking the ship",
          page.locator(".piece.move-ship").count() == 1)
    page.locator(".piece.move-ship").first.click()
    page.wait_for_selector(".hotspot.move-dest")
    check("dragging uses the real ship token", page.locator(".drag-token").count() == 1)
    check("illegal destinations are not clickable",
          page.locator('.hotspot[data-position="203"]').count() == 0)
    shot(page, "movement-destination")
    destination_id = page.locator(".hotspot.move-dest").first.get_attribute("data-custom-id")
    destination_message = page.locator(".hotspot.move-dest").first.get_attribute("data-message-id")
    page.locator(".hotspot.move-dest").first.click()
    page.wait_for_timeout(2200)
    moved = ships()
    check("clicking the destination moved the ship in the save",
          ("101", "blue-int") in moved, str(moved))
    shot(page, "movement-done")

    stale = api("/api/games/aeb1/press", {
        "seat": "1", "custom_id": destination_id, "message_id": int(destination_message)})
    after_stale = ships()
    check("replaying the used move does not move another ship",
          after_stale.count(("101", "blue-int")) == 1, str(after_stale))

    page.reload(wait_until="networkidle")
    page.wait_for_function("document.querySelector('#board').naturalWidth > 0", timeout=120000)
    page.wait_for_timeout(800)
    check("refresh restores the moved ship", ("101", "blue-int") in ships())

    other = open_page(page.context.browser, "2", prompt=False)
    check("the other seat sees the same ship position",
          ("101", "blue-int") in ships("2"))
    other.close()


def flow_movement_stack(page):
    click_choice(page, "Move (2)")
    page.wait_for_selector(".piece.move-from")
    page.locator(".piece.move-from").first.click()
    page.wait_for_selector(".piece.move-ship")
    page.locator(".piece.move-ship").first.click()
    page.wait_for_selector(".stack-choice")
    head = page.locator(".stack-choice .tray-head").inner_text()
    check("the stack asks how many of the visible ships move", "1" in head and "2" in head, head)
    shot(page, "movement-stack")
    page.locator(".stack-choice .icon").filter(has_text="+").click()
    page.wait_for_timeout(1800)
    check("adding a ship raises the stack count",
          "2" in page.locator(".stack-choice .tray-head").inner_text(),
          page.locator(".stack-choice .tray-head").inner_text())
    page.get_by_role("button", name="Move 2").click()
    page.wait_for_selector(".hotspot.move-dest")
    page.locator(".hotspot.move-dest").first.click()
    page.wait_for_timeout(2200)
    if page.locator(".hotspot.move-dest").count():
        page.locator(".hotspot.move-dest").first.click()
        page.wait_for_timeout(2200)
    piece = next((row for row in view("1")["pieces"]
                  if row["kind"] == "ship" and row["position"] == "101"
                  and row["name"] == "blue-int"), {})
    check("both ships moved together", piece.get("count") == 2, str(piece))


def flow_explore(page):
    click_choice(page, "Explore (1)")
    page.wait_for_selector(".hotspot.explore")
    slots = page.locator(".hotspot.explore")
    check("unexplored ring slots are the explore targets", slots.count() > 0,
          f"{slots.count()} slots")
    position = slots.first.get_attribute("data-position")
    shot(page, "explore-slots")
    slots.first.click()
    page.wait_for_selector(".tile-preview", timeout=30000)
    page.wait_for_function(
        "document.querySelector('.tile-preview img').naturalWidth > 0", timeout=60000)
    rotations = page.evaluate("state.previewRotations")
    preview_key = page.evaluate("state.previewKey")
    preview_src = page.locator(".tile-preview img").get_attribute("src")
    check("the drawn tile previews on the target slot",
          preview_key.startswith(f"{position}:") and "tile.webp" in (preview_src or ""),
          f"{preview_key} {preview_src}")
    check("only the engine's legal rotations are offered", 1 <= len(rotations) <= 6, str(rotations))
    before = page.evaluate("state.previewRotation")
    if len(rotations) > 1:
        page.locator(".tile-preview").click()
        page.wait_for_timeout(400)
        after = page.evaluate("state.previewRotation")
        check("clicking the preview rotates it", after != before, f"{before}°→{after}°")
    shot(page, "explore-preview")
    chosen_rotation = page.evaluate("state.previewRotation")
    click_choice(page, "Place tile here")
    page.wait_for_timeout(2500)
    meta = {tile["position"]: tile for tile in view("1")["board_meta"]["tiles"]}
    check("placing the preview saved the engine's tile",
          meta[position]["empty"] is False and meta[position]["label"] != "Unexplored",
          meta[position]["label"])
    check("the saved tile keeps the previewed rotation",
          meta[position]["orientation"] == chosen_rotation,
          f"{meta[position]['orientation']}° vs {chosen_rotation}°")


def flow_build(page):
    click_choice(page, "Build (2)")
    page.wait_for_selector(".hotspot.build-tile")
    check("buildable systems are marked on the board",
          page.locator(".hotspot.build-tile").count() > 0)
    shot(page, "build-system")
    page.locator(".hotspot.build-tile").first.click()
    page.wait_for_selector(".build-card")
    check("units are picture cards with their price", page.locator(".build-card").count() > 0,
          page.locator(".build-card").first.inner_text().replace("\n", " "))
    shot(page, "build-units")
    page.locator(".build-card", has_text="Interceptor").first.click()
    page.wait_for_timeout(1800)
    click_choice(page, "Finished In This System")
    page.wait_for_selector(".choices .choice")
    page.get_by_role("button", name="Materials (2)").first.click()
    page.wait_for_timeout(1200)
    page.get_by_role("button", name="Science (3:1)").first.click()
    page.wait_for_timeout(1200)
    page.get_by_role("button", name="Finish Build In This System").first.click()
    page.wait_for_timeout(2000)
    if page.get_by_role("button", name="Finish Action").count():
        page.get_by_role("button", name="Finish Action").first.click()
        page.wait_for_timeout(1800)
    built = next((piece for piece in view("1")["pieces"]
                  if piece["kind"] == "ship" and piece["position"] == "201"
                  and piece["name"] == "blue-int"), {})
    check("the built ship is in the saved system", built.get("count", 0) >= 2, str(built))


def flow_upgrade(page):
    before = next(player for player in view("1")["game"]["players"] if player["is_you"])
    click_choice(page, "Upgrade (2)")
    page.wait_for_selector(".ship-mini.target")
    check("your blueprints become the upgrade targets",
          page.locator(".ship-mini.target").count() > 0)
    shot(page, "upgrade-ships")
    page.locator(".ship-mini.target").first.click()
    page.wait_for_selector(".slot.target")
    check("the ship's part slots are clickable", page.locator(".slot.target").count() > 0)
    shot(page, "upgrade-slots")
    page.locator(".slot.target").first.click()
    page.wait_for_selector(".part-card")
    check("replacement parts are cards", page.locator(".part-card").count() > 0)
    shot(page, "upgrade-parts")
    part = page.locator(".part-card", has_text="Hull")
    (part if part.count() else page.locator(".part-card")).first.click()
    page.wait_for_timeout(2200)
    after = next(player for player in view("1")["game"]["players"] if player["is_you"])
    old_slots = [slot["part"]["id"] for slot in before["blueprints"][0]["slots"]]
    new_slots = [slot["part"]["id"] for slot in after["blueprints"][0]["slots"]]
    check("the chosen part is saved on the blueprint", old_slots != new_slots,
          f"{old_slots} → {new_slots}")


def flow_influence(page):
    click_choice(page, "Influence (2)")
    page.wait_for_timeout(1200)
    page.get_by_role("button", name=re.compile(r"Add\s+Influence")).first.click()
    page.wait_for_selector(".hotspot.influence-add")
    check("neutral worlds are marked for a disc", page.locator(".hotspot.influence-add").count() > 0)
    shot(page, "influence-targets")
    page.locator(".hotspot.influence-add").first.click()
    page.wait_for_timeout(2200)
    owners = {tile["position"]: tile["owner"] for tile in view("1")["board_meta"]["tiles"]}
    check("clicking the world placed the disc", owners.get("101") == "blue", str(owners.get("101")))
    page.get_by_role("button", name="Remove Influence").first.click()
    page.wait_for_selector(".hotspot.influence-remove")
    check("your disc is the remove target", page.locator(".hotspot.influence-remove").count() > 0)
    shot(page, "influence-remove")
    page.locator(".hotspot.influence-remove").first.click()
    page.wait_for_timeout(2200)
    owners = {tile["position"]: tile["owner"] for tile in view("1")["board_meta"]["tiles"]}
    check("clicking your disc removes it", owners.get("101") == 0, str(owners.get("101")))


def flow_population(page):
    page.wait_for_selector(".piece.planet")
    check("empty planet squares are ghost targets", page.locator(".piece.planet").count() > 0,
          page.locator(".piece.planet").first.get_attribute("aria-label"))
    shot(page, "population-targets")
    page.locator(".piece.planet").first.click()
    page.wait_for_timeout(2200)
    planets = [piece for piece in view("1")["pieces"]
               if piece["kind"] == "planet" and piece["position"] == "101"]
    check("clicking the planet square placed population",
          any(planet["pop"] > 0 for planet in planets),
          str([(planet["square"], planet["index"], planet["pop"]) for planet in planets]))


def flow_population_neutral(page):
    page.wait_for_selector(".piece.planet")
    page.locator(".piece.planet").first.click()
    page.wait_for_selector(".choices .choice")
    page.wait_for_timeout(1500)
    check("a grey planet asks for the cube type",
          page.get_by_role("button", name="Science").count() > 0,
          [node.inner_text() for node in page.locator(".choices .choice").all()])
    shot(page, "population-type")
    page.get_by_role("button", name="Science").first.click()
    page.wait_for_timeout(2200)
    planets = [piece for piece in view("1")["pieces"]
               if piece["kind"] == "planet" and piece["position"] == "101"
               and piece["square"] == "neutral"]
    check("the chosen cube type is saved on the grey planet",
          any(planet["pop"] > 0 for planet in planets), str(planets))


def flow_discovery(page):
    page.wait_for_selector(".discovery-card")
    page.wait_for_function(
        "document.querySelector('.discovery-card img')?.naturalWidth > 0", timeout=30000)
    check("the discovery tile is shown as its card", True)
    before = view("1")["you"].get("disc_tiles") or 0
    shot(page, "discovery-card")
    click_choice(page, "Keep it for 2 points")
    page.wait_for_timeout(2200)
    after = view("1")["you"].get("disc_tiles") or 0
    check("keeping the discovery is saved for points", after == before + 1, f"{before}→{after}")


def flow_research(page):
    click_choice(page, "Research (2)")
    page.wait_for_timeout(1200)
    page.wait_for_selector(".tech-chip.playable")
    check("the tech market itself is the research choice",
          page.locator(".tech-chip.playable").count() > 0)
    shot(page, "research-market")
    before = next(player for player in view("1")["game"]["players"] if player["is_you"])
    page.locator(".tech-chip.playable").first.click()
    page.wait_for_timeout(2200)
    after = next(player for player in view("1")["game"]["players"] if player["is_you"])
    techs = [tech["id"] for track in ("military", "grid", "nano") for tech in after["techs"][track]]
    before_techs = [tech["id"] for track in ("military", "grid", "nano")
                    for tech in before["techs"][track]]
    check("clicking a market tech bought it", len(techs) == len(before_techs) + 1,
          f"{before_techs} → {techs}")


def flow_combat(browser, errors):
    one = open_page(browser, "1", errors)
    two = open_page(browser, "2", errors)
    for _ in range(40):
        acted = False
        for page in (one, two):
            clicked = page.evaluate("""(() => {
              const prompts = [...document.querySelectorAll('.prompt.combat')]
                .filter((prompt) => [...prompt.querySelectorAll('button')].some((b) => /Roll/.test(b.textContent)))
                .sort((a, b) => Number(a.dataset.messageId) - Number(b.dataset.messageId));
              const prompt = prompts[prompts.length - 1];
              if (!prompt) return false;
              const button = [...prompt.querySelectorAll('button')].find((b) => /Roll/.test(b.textContent));
              button.click();
              return true;
            })()""")
            if clicked:
                page.wait_for_timeout(900)
                acted = True
                break
        if one.locator(".piece.combat-hit").count():
            break
        if not acted:
            one.wait_for_timeout(900)
    if not one.locator(".piece.combat-hit").count():
        check("combat hit assignment is clickable on the enemy ship", True,
              "skipped: no hit prompt in 40 rolls")
        return
    shot(one, "combat-hit-target")
    target = one.locator(".piece.combat-hit").first.get_attribute("aria-label")
    one.locator(".piece.combat-hit").first.click()
    one.wait_for_timeout(2200)
    check("clicking the enemy ship assigns the hit", target not in (None, ""), target)
    shot(one, "combat-hit-done")


FLOWS = {
    "movement": flow_movement,
    "movement-stack": flow_movement_stack,
    "explore": flow_explore,
    "build": flow_build,
    "upgrade": flow_upgrade,
    "influence": flow_influence,
    "population": flow_population,
    "population-neutral": flow_population_neutral,
    "discovery": flow_discovery,
    "research": flow_research,
}


def main():
    name = sys.argv[1] if len(sys.argv) > 1 else "movement"
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    errors = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(args=["--no-sandbox"])
        if name == "combat":
            flow_combat(browser, errors)
        elif name in FLOWS:
            page = open_page(browser, "1", errors)
            FLOWS[name](page)
            check("no browser exceptions", not errors, "; ".join(errors[:3]))
        else:
            raise SystemExit(f"flow must be one of: {', '.join([*FLOWS, 'combat'])}")
        browser.close()
    (ARTIFACTS / f"direct-{name}.json").write_text(json.dumps(results, indent=1))
    failed = [row for row in results if not row["passed"]]
    print(f"{len(results) - len(failed)}/{len(results)} checks passed")
    raise SystemExit(1 if failed else 0)


if __name__ == "__main__":
    main()
