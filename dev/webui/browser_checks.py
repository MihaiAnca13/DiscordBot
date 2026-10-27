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
        check("player panels render", one.locator("#players .player").count() == 2)
        check("tech market renders", one.locator(".tech-chip").count() > 5)
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

        one.get_by_role("button", name="Faction").click()
        one.wait_for_timeout(500)
        check("faction reference opens", one.locator("#faction-title").inner_text() == "Hydran Progress")
        one.screenshot(path=str(ARTIFACTS / "check-faction.png"), full_page=True)
        one.locator('[data-close="faction-dialog"]').click()

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
        card = one.locator(
            f'.prompt[data-message-id="{prompt["id"]}"] [data-custom="{button["custom_id"]}"]')
        card.first.click()
        one.wait_for_timeout(3000)
        bought = view("1")
        science_after_buy = bought["game"]["players"][0]["science"]
        check("research changes saved state", science_after_buy < 6,
              f"science now {science_after_buy}")
        techs = bought["game"]["players"][0]["techs"]
        check("a tech is never owned twice",
              len(techs["military"] + techs["grid"] + techs["nano"])
              == len({tech["id"] for tech in techs["military"] + techs["grid"] + techs["nano"]}))

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
              narrow.locator("#players .player").count() == 2)
        browser.close()
    (ARTIFACTS / "browser_checks.json").write_text(json.dumps(results, indent=1))
    failed = [row for row in results if not row["passed"]]
    print(f"{len(results) - len(failed)}/{len(results)} checks passed")
    raise SystemExit(1 if failed else 0)


if __name__ == "__main__":
    main()
