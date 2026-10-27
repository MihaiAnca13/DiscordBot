"""Scripted play through the live HTTP surface.

Prepare the game first (service stopped), then run this with the service up:

    docker compose -f compose.webui.yaml stop webui
    docker compose -f compose.webui.yaml run --rm webui python -m dev.webui.seed
    docker compose -f compose.webui.yaml up -d --wait webui
    docker compose -f compose.webui.yaml exec -T webui python -m dev.webui.playthrough round

    ... python -m dev.webui.scenarios combat ...
    ... python -m dev.webui.playthrough combat
"""
import json
import re
import sys
import time
import urllib.request

BASE = "http://127.0.0.1:8099/api/games/aeb1"


def api(path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(BASE + path, data=data,
                                     headers={"Content-Type": "application/json"} if data else {})
    with urllib.request.urlopen(request, timeout=90) as response:
        return json.load(response)


def view(seat):
    return api(f"/view?seat={seat}")


def pending(seat, room=None):
    return [message for message in view(seat)["pending"]
            if room is None or room in message["room"]]


def press(seat, message, button):
    result = api("/press", {"seat": seat, "custom_id": button["custom_id"],
                            "message_id": message["id"]})
    if result.get("error"):
        raise RuntimeError(f"{button['custom_id']}: {result['error']}")
    time.sleep(0.35)


def find(seat, label, room=None, exact=False, regex=False):
    """Find (message, button) by visible label."""
    for message in pending(seat, room):
        for button in message["buttons"]:
            text = button.get("label") or ""
            if (regex and re.search(label, text)) or (exact and text == label) \
                    or (not exact and not regex and label in text):
                return message, button
    return None, None


def click(seat, label, room=None, exact=False, regex=False):
    message, button = find(seat, label, room, exact, regex)
    if message is None:
        raise AssertionError(f"no button {label!r} for seat {seat}: "
                             f"{[(m['id'], [b['label'] for b in m['buttons']]) for m in pending(seat)]}")
    press(seat, message, button)


def wait_for(seat, label, timeout=10, room=None):
    deadline = time.time() + timeout
    while time.time() < deadline:
        message, button = find(seat, label, room)
        if message:
            return message, button
        time.sleep(0.25)
    raise AssertionError(f"timed out waiting for {label!r} for seat {seat}")


def play_round():
    """Build with blue, explore with red, then upkeep into round two."""
    before = view("1")
    assert before["game"]["round"] == 1, before["game"]["round"]

    click("1", "Build (2)")
    click("1", "201", exact=True)
    click("1", "Interceptor (3)")
    click("1", "Finished In This System")
    click("1", "Materials (2)")
    click("1", "Science (3:1)")
    click("1", "Finish Build In This System")
    click("1", "Finish Action")
    click("1", "End Turn")
    blue = view("1")["game"]["players"][0]
    blue_tile = [tile for tile in blue["owned_tiles"] if tile["position"] == "201"][0]
    assert "blue-int" in blue_tile["ships"] or len(blue_tile["ships"]) >= 2, blue_tile

    click("2", "Explore (1)")
    tile_message, tile_button = next(
        (message, button) for message in pending("2")
        for button in message["buttons"]
        if re.fullmatch(r"\d{3}", button.get("label") or ""))
    press("2", tile_message, tile_button)
    click("2", "Option #1")
    if find("2", "Get 2 Points")[0]:
        click("2", "Get 2 Points")
    if find("2", "Decline Influence Placement")[0]:
        click("2", "Decline Influence Placement")
    click("2", "Finish Action")
    click("2", "End Turn")

    # Both seats pass so the round can end; a turn ending alone does not pass.
    click("1", "Pass (1st)")
    click("2", "Pass (2nd)")
    wait_for("1", "Run Upkeep")
    click("1", "Run Upkeep")

    after = view("1")
    assert after["game"]["round"] == 2, after["game"]["round"]
    assert after["game"]["active"], after["game"]["active"]
    assert after["you"]["income"]["money"] is not None
    print("round complete: round", after["game"]["round"], "active", after["game"]["active"])


def play_movement():
    """Click-move a ship from 201 to the neutral 101 and back to 201."""
    click("1", "Move (2)")
    click("1", "201", exact=True)
    click("1", "Interceptor (Range: 1)")
    click("1", "101", exact=True)
    click("1", "Move an additional ship")
    click("1", "101", exact=True)
    click("1", "Interceptor (Range: 1)")
    click("1", "201", exact=True)
    click("1", "Finish Action")
    view_after = view("1")
    tiles = {tile["position"]: tile["ships"] for tile in view_after["game"]["players"][0]["owned_tiles"]}
    assert any("blue-int" in ships for ships in tiles.values())
    print("movement complete:", tiles)


def play_full():
    """Pass both seats and run upkeep from round 1 until the score screen appears."""
    for _ in range(40):
        after = view("1")
        if after["game"]["ended"]:
            break
        acted = False
        for seat in ("1", "2"):
            message, button = find(seat, "Pass (", exact=False)
            if message and button and "Pass Unless" not in (button.get("label") or ""):
                press(seat, message, button)
                acted = True
                break
        if acted:
            continue
        message, button = find("1", "Run Upkeep")
        if message:
            press("1", message, button)
            continue
        message, button = find("1", "Declare Winner")
        if message:
            press("1", message, button)
            time.sleep(1)
            continue
        message, button = find("1", "Ready for Upkeep")
        if message:
            press("1", message, button)
            continue
        raise AssertionError(f"stuck at round {after['game']['round']}: "
                             f"{[(m['id'], [b['label'] for b in m['buttons']]) for m in after['pending']]}")
    final = view("1")
    assert final["game"]["ended"], final["game"]
    assert final["result"], final
    print("game complete: winner", final["result"][0]["name"],
          "with", final["result"][0]["points"], "points in round", final["game"]["round"])


def play_combat():
    """Roll both sides until the battle resolves, then take reputation."""
    last = None
    for _ in range(80):
        acted = False
        for seat in ("1", "2"):
            for message in pending(seat):
                if "Combat" not in message["room"] and "Bombing" not in message["room"]:
                    continue
                button = next((b for b in message["buttons"]
                               if "rollDice" in (b.get("custom_id") or "")), None)
                if button is None:
                    continue
                press(seat, message, button)
                acted = True
                last = message["room"]
                break
            if acted:
                break
        if not acted:
            break
    for seat in ("1", "2"):
        for message in pending(seat):
            for button in message["buttons"]:
                if "drawReputation" in (button.get("custom_id") or ""):
                    press(seat, message, button)
    after = view("1")
    battles = [message for message in after["pending"] if "Combat" in message["room"]]
    rolls = [message for message in battles
             if any("rollDice" in (button.get("custom_id") or "") for button in message["buttons"])]
    assert not rolls, rolls
    assert after["game"]["round"] >= 1
    print("combat resolved in", last, "reputation:",
          [(player["name"], player["reputation"]) for player in after["game"]["players"]])


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "round"
    if mode == "round":
        play_round()
    elif mode == "movement":
        play_movement()
    elif mode == "full":
        play_full()
    elif mode == "combat":
        play_combat()
    else:
        raise SystemExit("mode must be round, movement, full or combat")
