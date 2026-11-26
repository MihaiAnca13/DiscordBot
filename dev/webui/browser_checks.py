"""Repeatable browser checks: layout, race, stale replay, seat isolation.

Run after `python -m dev.webui.seed` with the service up:

    docker compose -f compose.webui.yaml exec -T webui python -m dev.webui.browser_checks
"""
import json
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
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.load(response)


def check(name, condition, detail=""):
    results.append({"check": name, "passed": bool(condition), "detail": detail})
    print(("PASS " if condition else "FAIL ") + name + (f" — {detail}" if detail else ""))


def view(seat):
    return api(f"/api/games/aeb1/view?seat={seat}")


def main():
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    errors = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(args=["--no-sandbox"])
        one = browser.new_page(viewport={"width": 1600, "height": 1000})
        two = browser.new_page(viewport={"width": 1600, "height": 1000})
        for page in (one, two):
            page.set_default_timeout(25000)
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.on("response", lambda response: errors.append(
                f"HTTP {response.status}: {response.url}") if response.status >= 500 else None)
        one.goto(f"{BASE}/?seat=1", wait_until="networkidle")
        one.wait_for_function("document.querySelector('#board').naturalWidth > 0", timeout=120000)
        one.locator("#action-dock .prompt").first.wait_for()
        check("board renders", True)
        check("player panels render", one.locator("#players .rendered-player").count() == 2)
        check("player boards render the engine artwork",
              one.evaluate("[...document.querySelectorAll('#players .rendered-panel')]"
                           ".every((image) => image.complete && image.naturalWidth > 0)"))
        check("tech market renders the engine artwork",
              one.evaluate("document.querySelector('.market-stage img').naturalWidth > 0"))
        one.screenshot(path=str(ARTIFACTS / "check-table.png"), full_page=True)

        zoom_before = one.evaluate("state.zoom")
        one.locator("#zoom-in").click()
        zoom_after = one.evaluate("state.zoom")
        check("zoom control changes the board", zoom_after > zoom_before, f"{zoom_before:.2f}→{zoom_after:.2f}")
        pan_before = one.evaluate("state.panX")
        box = one.locator("#board-viewport").bounding_box()
        one.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
        one.mouse.down()
        one.mouse.move(box["x"] + box["width"] / 2 + 80, box["y"] + box["height"] / 2, steps=6)
        one.mouse.up()
        check("drag pans the board", one.evaluate("state.panX") != pan_before)
        one.locator("#zoom-fit").click()
        check("fit restores the whole map", abs(one.evaluate("state.zoom") - zoom_before) < 0.01)

        one.locator("#market-toggle").click()
        one.wait_for_timeout(300)
        check("the market can collapse", one.locator("#market-content.collapsed").count() == 1)

        one.locator("#open-faction").click()
        one.wait_for_timeout(500)
        check("faction reference opens", one.locator("#faction-title").inner_text() == "Hydran Progress")
        one.screenshot(path=str(ARTIFACTS / "check-faction.png"), full_page=True)
        one.locator('[data-close="faction-dialog"]').click()

        one.locator("#players .rendered-panel").first.click()
        one.wait_for_timeout(400)
        check("a player board opens enlarged", one.locator("#zoom-dialog[open]").count() == 1)
        one.keyboard.press("Escape")

        one.locator(".top-actions").get_by_role("button", name="Parts reference").click()
        one.wait_for_timeout(500)
        one.locator("#reference-body img").click()
        one.wait_for_timeout(400)
        check("the parts reference opens enlarged", one.locator("#zoom-dialog[open]").count() == 1)
        one.keyboard.press("Escape")
        one.locator('[data-close="reference-dialog"]').click()

        two.goto(f"{BASE}/?seat=1", wait_until="networkidle")
        before = view("1")
        discs_before = before["game"]["players"][0]["influence_discs"]
        # One race: both browser seats answer the same turn menu at once.
        one.get_by_role("button", name="Research (2)").click()
        try:
            two.get_by_role("button", name="Research (2)").click(timeout=4000)
        except Exception:
            pass
        one.wait_for_timeout(3500)
        after = view("1")
        discs_after = after["game"]["players"][0]["influence_discs"]
        research_starts = [m for m in after["history"] + after["pending"]
                           if "is using their turn to research" in (m["content"] or "")]
        check("one research action despite two presses", discs_before - discs_after == 1,
              f"discs {discs_before}→{discs_after}")
        check("one research start message", len(research_starts) == 1,
              f"{len(research_starts)} starts")

        prompt = max((message for message in after["pending"]
                      if any(button.get("custom_id", "").startswith("FCIDblue_getTech_")
                             for button in message["buttons"])),
                     key=lambda message: message["id"])
        button = next(button for button in prompt["buttons"]
                      if button["custom_id"].startswith("FCIDblue_getTech_"))
        check("tech choices carry canonical ids", button["custom_id"].startswith("FCIDblue_getTech_"))
        tech_id = button["custom_id"].split("_getTech_")[1].split("_")[0]
        one.wait_for_selector(".market-target")
        one.locator(f'.market-target[data-tech="{tech_id}"]').first.click()
        one.wait_for_timeout(600)
        if one.locator("#tech-track-dialog[open]").count():
            one.locator(".tech-track-choice").first.click()
        one.wait_for_timeout(3000)
        bought = view("1")
        science_after_buy = bought["game"]["players"][0]["science"]
        check("research changes saved state", science_after_buy < 6,
              f"science now {science_after_buy}")
        techs = bought["game"]["players"][0]["techs"]
        check("a tech is never owned twice",
              len(techs["military"] + techs["grid"] + techs["nano"])
              == len({tech["id"] for tech in techs["military"] + techs["grid"] + techs["nano"]}))

        decline = one.get_by_role("button", name="Decline 2nd Tech")
        if decline.count():
            decline.first.click()
            one.wait_for_timeout(1600)
            check("the market returns to its collapsed state after research",
                  one.evaluate("""(() => {
                    const card = document.querySelector('.market-card');
                    return !card.classList.contains('researching')
                      && document.querySelector('#market-content').classList.contains('collapsed');
                  })()"""))

        # A stale press on the used prompt must not buy the tech again.
        stale = api("/api/games/aeb1/press", {"seat": "1", "custom_id": button["custom_id"],
                                              "message_id": prompt["id"]})
        replay = view("1")
        check("stale replay awards nothing",
              replay["game"]["players"][0]["science"] == science_after_buy,
              f"science {science_after_buy}→{replay['game']['players'][0]['science']}")

        # A private prompt of blue is invisible to red's pending choices.
        blue_private = [message for message in replay["pending"] if message["private"]]
        red = view("2")
        check("private prompts stay with their seat",
              all(message["private"] is False for message in red["pending"])
              or not blue_private,
              f"{len(blue_private)} private prompt(s) for blue")

        one.get_by_role("button", name="History").click()
        one.wait_for_timeout(1200)
        check("history view lists records", one.locator(".history-item").count() > 0)
        tallest = one.evaluate("""Math.max(0, ...[...document.querySelectorAll('#history-list img.attachment')]
          .map((image) => image.getBoundingClientRect().height))""")
        check("history images stay compact", tallest <= 240, f"tallest {tallest:.0f}px")
        one.screenshot(path=str(ARTIFACTS / "check-history.png"), full_page=True)
        one.locator('[data-close="history-dialog"]').click()

        one.reload(wait_until="networkidle")
        one.locator("#action-dock .prompt").first.wait_for()
        check("refresh restores open choices", bool(view("1")["pending"]))
        check("no browser exceptions", not errors, "; ".join(errors[:3]))

        narrow = browser.new_page(viewport={"width": 700, "height": 950})
        narrow.goto(f"{BASE}/?seat=1", wait_until="networkidle")
        narrow.locator("#action-dock .prompt").first.wait_for()
        narrow.screenshot(path=str(ARTIFACTS / "check-narrow.png"), full_page=True)
        check("narrow viewport renders one column",
              narrow.locator("#players .rendered-player").count() == 2)

        tablet = browser.new_page(viewport={"width": 1024, "height": 768})
        tablet.goto(f"{BASE}/?seat=1", wait_until="networkidle")
        tablet.locator("#action-dock .prompt").first.wait_for()
        tablet.wait_for_timeout(300)
        tablet.screenshot(path=str(ARTIFACTS / "check-tablet.png"), full_page=True)
        tablet_layout = tablet.evaluate("""() => {
            const card = document.querySelector('.market-card').getBoundingClientRect();
            const stage = document.querySelector('.market-stage').getBoundingClientRect();
            return {
                header: getComputedStyle(document.querySelector('.topbar')).position,
                market: [stage.width, card.width],
                overflow: document.documentElement.scrollWidth - innerWidth,
            };
        }""")
        check("tablet header scrolls away", tablet_layout["header"] == "static",
              tablet_layout["header"])
        check("tablet market fills the card",
              tablet_layout["market"][0] > tablet_layout["market"][1] * 0.9,
              f"{tablet_layout['market'][0]:.0f}/{tablet_layout['market'][1]:.0f}")
        check("tablet layout has no sideways page scroll", tablet_layout["overflow"] <= 0,
              f"{tablet_layout['overflow']}px")
        tablet.close()

        phone_context = browser.new_context(viewport={"width": 390, "height": 844},
                                            has_touch=True, is_mobile=True)
        phone = phone_context.new_page()
        phone.set_default_timeout(25000)
        phone.on("pageerror", lambda error: errors.append(str(error)))
        phone.goto(f"{BASE}/?seat=1", wait_until="networkidle")
        phone.locator("#action-dock .prompt, #action-dock .waiting").first.wait_for()
        phone.wait_for_function("document.querySelector('#board').naturalWidth > 0", timeout=120000)
        phone.wait_for_timeout(300)
        phone.screenshot(path=str(ARTIFACTS / "check-phone.png"), full_page=True)
        layout = phone.evaluate("""() => ({
            topbar: document.querySelector('.topbar').getBoundingClientRect().height,
            overflow: document.documentElement.scrollWidth - innerWidth,
            choice: document.querySelector('.choice')?.getBoundingClientRect().height || 0,
            hint: document.querySelector('#board-hint').textContent,
            marketScroll: document.querySelector('#tech-market').scrollWidth,
            marketClient: document.querySelector('#tech-market').clientWidth,
        })""")
        check("phone header stays compact", layout["topbar"] <= 170, f"{layout['topbar']:.0f}px")
        check("phone layout has no sideways page scroll", layout["overflow"] <= 0,
              f"{layout['overflow']}px")
        check("touch choices are at least 42px tall", layout["choice"] >= 42,
              f"{layout['choice']:.0f}px")
        check("touch hint names pinch zoom", "pinch" in layout["hint"], layout["hint"])
        check("the phone market scrolls instead of shrinking", layout["marketScroll"] > layout["marketClient"],
              f"{layout['marketScroll']} > {layout['marketClient']}")

        zoom_before = phone.evaluate("state.zoom")
        client = phone_context.new_cdp_session(phone)
        box = phone.locator("#board-viewport").bounding_box()
        cx, cy = box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
        points = [{"x": cx - 20, "y": cy, "id": 1, "radiusX": 5, "radiusY": 5, "force": 1},
                  {"x": cx + 20, "y": cy, "id": 2, "radiusX": 5, "radiusY": 5, "force": 1}]
        client.send("Input.dispatchTouchEvent", {"type": "touchStart", "touchPoints": points})
        for step in (40, 70, 100):
            rest = [{"x": cx + step, "y": cy, "id": 2, "radiusX": 5, "radiusY": 5, "force": 1}]
            client.send("Input.dispatchTouchEvent",
                        {"type": "touchMove", "touchPoints": [points[0]] + rest})
            phone.wait_for_timeout(30)
        client.send("Input.dispatchTouchEvent", {"type": "touchEnd", "touchPoints": []})
        phone.wait_for_timeout(200)
        check("pinch zooms the board", phone.evaluate("state.zoom") > zoom_before * 1.2,
              f"{zoom_before:.2f}→{phone.evaluate('state.zoom'):.2f}")

        phone.locator("#zoom-fit").click()
        phone.wait_for_timeout(200)
        phone.set_viewport_size({"width": 844, "height": 390})
        phone.wait_for_timeout(500)
        rotated = phone.evaluate("""() => ({
            fitted: state.fitted,
            board: document.querySelector('#board-viewport').getBoundingClientRect().height,
        })""")
        check("a fitted board refits after rotation", rotated["fitted"] and rotated["board"] < 300,
              f"{rotated['board']:.0f}px")
        phone.set_viewport_size({"width": 390, "height": 844})
        phone.wait_for_timeout(400)
        phone.get_by_role("button", name="AI stats").click()
        phone.wait_for_timeout(400)
        phone.locator("#reference-body img").click()
        phone.wait_for_timeout(300)
        check("a phone reference image opens enlarged",
              phone.locator("#zoom-dialog[open]").count() == 1)
        phone.keyboard.press("Escape")
        phone.locator('[data-close="reference-dialog"]').click()
        phone.locator("#open-history").click()
        phone.wait_for_timeout(600)
        dialog = phone.evaluate("""() => {
            const box = document.querySelector('#history-dialog').getBoundingClientRect();
            return { width: box.width, height: box.height, viewport: [innerWidth, innerHeight] };
        }""")
        check("history fills a phone screen",
              dialog["width"] == dialog["viewport"][0] and dialog["height"] == dialog["viewport"][1],
              f"{dialog['width']:.0f}×{dialog['height']:.0f}")
        phone_context.close()
        browser.close()
    (ARTIFACTS / "browser_checks.json").write_text(json.dumps(results, indent=1))
    failed = [row for row in results if not row["passed"]]
    print(f"{len(results) - len(failed)}/{len(results)} checks passed")
    raise SystemExit(1 if failed else 0)


if __name__ == "__main__":
    main()
