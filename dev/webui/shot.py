"""Screenshot the live page in Chromium and report browser errors.

    python -m dev.webui.shot [url] [name]
"""
import json
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright


def main():
    url = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8099/?seat=1"
    name = sys.argv[2] if len(sys.argv) > 2 else "table"
    artifacts = Path("dev/webui/artifacts")
    artifacts.mkdir(parents=True, exist_ok=True)
    errors = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(args=["--no-sandbox"])
        for label, viewport in (("desktop", {"width": 1600, "height": 1000}),
                                ("narrow", {"width": 720, "height": 980})):
            page = browser.new_page(viewport=viewport)
            page.set_default_timeout(20000)
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.on("console", lambda message: errors.append(f"console {message.type}: {message.text}")
                    if message.type == "error" else None)
            page.on("response", lambda response: errors.append(f"HTTP {response.status}: {response.url}")
                    if response.status >= 500 else None)
            page.goto(url, wait_until="networkidle")
            page.locator("#action-dock .prompt, #action-dock .waiting").first.wait_for()
            page.wait_for_function("document.querySelector('#board').naturalWidth > 0", timeout=120000)
            page.wait_for_timeout(400)
            page.screenshot(path=str(artifacts / f"{name}-{label}.png"), full_page=True)
            print(label, page.locator("#players .player").count(), "players",
                  page.locator("#action-dock .prompt").count(), "prompts",
                  page.locator(".hotspot").count(), "hotspots")
            page.close()
        browser.close()
    (artifacts / f"{name}.json").write_text(json.dumps({"errors": errors}, indent=1))
    print("errors:", errors or "none")


if __name__ == "__main__":
    main()
