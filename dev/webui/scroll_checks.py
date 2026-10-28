"""Read-only Chromium checks for page scrolling versus galaxy-map zoom.

Run with the Docker sandbox up:
    docker compose -f compose.webui.yaml exec -T webui python -m dev.webui.scroll_checks
"""
from playwright.sync_api import sync_playwright


def main():
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(args=["--no-sandbox"])
        page = browser.new_page(viewport={"width": 1600, "height": 700})
        page.goto("http://127.0.0.1:8099/?seat=1", wait_until="networkidle")
        page.wait_for_function("document.querySelector('#board').naturalWidth > 0")
        page.wait_for_timeout(300)

        result = page.evaluate("""() => {
          const before = state.zoom;
          document.body.dispatchEvent(new WheelEvent('wheel', {
            deltaY: 120, bubbles: true, cancelable: true,
          }));
          const continued = new WheelEvent('wheel', {
            deltaY: 120, bubbles: true, cancelable: true,
          });
          el.viewport.dispatchEvent(continued);
          return { prevented: continued.defaultPrevented, unchanged: state.zoom === before };
        }""")
        assert not result["prevented"] and result["unchanged"], result
        print("PASS page scroll entering the map stays a page scroll")

        page.wait_for_timeout(300)
        result = page.evaluate("""() => {
          const before = state.zoom;
          const started = new WheelEvent('wheel', {
            deltaY: -120, bubbles: true, cancelable: true,
          });
          el.viewport.dispatchEvent(started);
          return { prevented: started.defaultPrevented, zoomed: state.zoom > before };
        }""")
        assert result["prevented"] and result["zoomed"], result
        print("PASS a new scroll starting over the map zooms")

        page.wait_for_timeout(300)
        page.mouse.move(5, 350)
        before = page.evaluate("({scroll: window.scrollY, zoom: state.zoom})")
        page.mouse.wheel(0, 180)
        page.wait_for_function("window.scrollY > " + str(before["scroll"]))
        assert page.evaluate("state.zoom") == before["zoom"]
        print("PASS actual wheel input outside the map scrolls the page")

        page.locator("#board-viewport").scroll_into_view_if_needed()
        box = page.locator("#board-viewport").bounding_box()
        page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
        page.wait_for_timeout(300)
        before = page.evaluate("({scroll: window.scrollY, zoom: state.zoom})")
        page.mouse.wheel(0, -120)
        page.wait_for_function("state.zoom > " + str(before["zoom"]))
        assert page.evaluate("window.scrollY") == before["scroll"]
        print("PASS actual wheel input starting on the map zooms without scrolling")
        browser.close()


if __name__ == "__main__":
    main()
