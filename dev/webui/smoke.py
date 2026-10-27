"""Exercise the real browser and HTTP handlers against the reset demo game."""
import json
import re
from pathlib import Path

from playwright.sync_api import sync_playwright


def main():
    artifacts = Path("dev/webui/artifacts")
    artifacts.mkdir(parents=True, exist_ok=True)
    errors = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(args=["--no-sandbox"])
        page = browser.new_page(viewport={"width": 1600, "height": 1000})
        page.set_default_timeout(20000)
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.on("response", lambda response: errors.append(f"HTTP {response.status}: {response.url}")
                if response.status >= 500 else None)
        page.goto("http://127.0.0.1:8099/?seat=1", wait_until="networkidle")
        page.locator("#action-dock .prompt").first.wait_for()
        page.wait_for_function("document.querySelector('#board').naturalWidth > 0", timeout=120000)
        page.screenshot(path=str(artifacts / "table.png"), full_page=True)
        page.get_by_role("button", name=re.compile(r"^Build \(")).click()
        page.get_by_text("choose which tile", exact=False).wait_for()
        page.wait_for_function("document.querySelector('#board-note').textContent === ''", timeout=120000)
        page.wait_for_timeout(400)
        page.screenshot(path=str(artifacts / "build.png"), full_page=True)
        view = page.request.get("http://127.0.0.1:8099/api/games/aeb1/view?seat=1").json()
        assert any("choose which tile" in (message["content"] or "")
                   for message in view["pending"]), view["pending"]
        assert page.locator(".hotspot, .tile-chip").count() > 0
        assert not errors, errors
        (artifacts / "smoke.json").write_text(json.dumps({"passed": True, "browser_errors": errors}))
        browser.close()
    print("Browser smoke passed; screenshots in dev/webui/artifacts")


if __name__ == "__main__":
    main()
