"""Render a game's board once per state, then serve the cached file.

Rendering is the slow part (seconds), so the URL carries a version taken from the
save file's mtime and size: the browser keeps the image until the state changes.
"""
import os

from helpers.DrawHelper import DrawHelper
from helpers.GamestateHelper import GamestateHelper


def state_version(games_path, game_id):
    stat = os.stat(os.path.join(games_path, f"{game_id}.json"))
    return f"{stat.st_mtime_ns}-{stat.st_size}"


def render_board(games_path, game_id, cache_dir, keep=3):
    """Return (path, key). Blocking: call it in a thread."""
    key = state_version(games_path, game_id)
    folder = os.path.join(cache_dir, game_id)
    os.makedirs(folder, exist_ok=True)
    target = os.path.join(folder, f"{key}.webp")
    if os.path.exists(target):
        return target, key
    rendered = DrawHelper(GamestateHelper(None, game_id).gamestate).show_game()
    data = rendered.fp.read()
    temporary = f"{target}.tmp"
    with open(temporary, "wb") as handle:
        handle.write(data)
    os.replace(temporary, target)
    cached = sorted(os.path.join(folder, name) for name in os.listdir(folder))
    for stale in cached[:-keep]:
        os.unlink(stale)
    return target, key
