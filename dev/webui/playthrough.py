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
import os
import re
import sys
import time
import urllib.error
import urllib.request

WEBUI = os.environ.get("WEBUI", "http://127.0.0.1:8099")
GAME = os.environ.get("GAME", "aeb1")
BASE = f"{WEBUI}/api/games/{GAME}"


def fetch(url, body=None):
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(url, data=data,
                                     headers={"Content-Type": "application/json"} if data else {})
    try:
        with urllib.request.urlopen(request, timeout=90) as response:
            return json.load(response)
    except urllib.error.HTTPError as error:
        raise SystemExit(f"{error.code}: {error.read().decode()}")


def api(path, body=None):
    return fetch(BASE + path, body)


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


# -- one press at a time, for an agent playing the game ----------------------
# GAME=aeb2 python3 -m dev.webui.playthrough show 1
# GAME=aeb2 python3 -m dev.webui.playthrough press 1 "Explore (1)"   (a label or a custom_id)
# GAME=aeb2 python3 -m dev.webui.playthrough img player 1             (board, player, blueprint-cru, /api/media/...)
# GAME=aeb2 python3 -m dev.webui.playthrough state                     (every player's resources and tiles)

def print_message(message):
    # A public prompt can be another seat's turn menu; the API only lists buttons the seat may press.
    foreign = "" if message.get("for_you", True) else "  (not this seat's: no buttons for it)"
    print(f"\n#{message['id']} [{message['room']}]{' private' if message['private'] else ''}{foreign}")
    if message["content"]:
        print(message["content"])
    for button in message["buttons"]:
        print(f"  [{button.get('label')}]  {button['custom_id']}")
        for count in button.get("counts", []):
            print(f"    [{count.get('label')}]  {count['custom_id']}")
    for attachment in message["attachments"]:
        print(f"  file: {attachment['url']}")


def show(seat):
    snapshot = view(seat)
    game = snapshot["game"]
    drafting = f", drafting seat {game['drafting_seat']}" if game["setup"] else ""
    print(f"{GAME} round {game['round']}, active {game['active']}{drafting}")
    for message in snapshot["pending"]:
        print_message(message)


def choose(seat, text):
    """Press the one button whose custom_id or label is text (else contains it), print what followed."""
    options = [(message, choice) for message in pending(seat) for button in message["buttons"]
               for choice in [button, *button.get("counts", [])]]
    matches = ([(m, b) for m, b in options if text in (b["custom_id"], b.get("label"))]
               or [(m, b) for m, b in options if text in (b.get("label") or "")])
    if len(matches) != 1:
        raise SystemExit(f"{len(matches)} buttons match {text!r}: "
                         f"{[(b.get('label'), b['custom_id']) for _m, b in matches or options]}")
    last = max((m["id"] for m in api(f"/history?seat={seat}")["messages"]), default=0)
    message, button = matches[0]
    result = api("/press", {"seat": seat, "custom_id": button["custom_id"], "message_id": message["id"]})
    if result.get("error"):
        print(f"ERROR: {result['error']}")
    time.sleep(0.35)
    print("--- posted since the press ---")
    for posted in reversed(api(f"/history?seat={seat}")["messages"]):
        if posted["id"] > last:
            print_message(posted)
    print("\n--- pending now ---")
    show(seat)


def state():
    for player in view("1")["game"]["players"]:
        print({key: player[key] for key in (
            "id", "color", "faction_name", "money", "science", "materials", "colony_ships",
            "influence_discs", "points", "actions", "reputation", "ship_stock", "passed")},
              "tiles:", [tile["position"] for tile in player["owned_tiles"]])


def image(panel, seat=""):
    url = WEBUI + panel if panel.startswith("/") else f"{BASE}/{panel}.webp" + (f"?seat={seat}" if seat else "")
    folder = os.environ.get("OUT", "dev/webui/artifacts/playtest")
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, f"{GAME}-{panel.strip('/').replace('/', '-')}{'-' + seat if seat else ''}"
                        + ("" if panel.startswith("/") else ".webp"))
    urllib.request.urlretrieve(url, path)
    print(os.path.abspath(path))


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "round"
    if mode == "new":
        print(fetch(f"{WEBUI}/api/games", {"name": "Playtest", "players": int(sys.argv[2]),
                                           "community_factions": True})["id"])
    elif mode == "show":
        show(sys.argv[2])
    elif mode == "press":
        choose(sys.argv[2], sys.argv[3])
    elif mode == "img":
        image(*sys.argv[2:])
    elif mode == "state":
        state()
    elif mode == "round":
        play_round()
    elif mode == "movement":
        play_movement()
    elif mode == "full":
        play_full()
    elif mode == "combat":
        play_combat()
    else:
        raise SystemExit("mode must be new, show, press, img, state, round, movement, full or combat")
