"""The standalone sandbox must use one save directory for reads and writes."""
import importlib

import config
from webui.server import build


def test_environment_override_reaches_game_engine(tmp_path, monkeypatch):
    original_path = config.gamestate_path
    monkeypatch.setenv("WEBUI_GAMESTATE_PATH", str(tmp_path))
    try:
        importlib.reload(config)
        assert config.gamestate_path == str(tmp_path)
        app = build(data_dir=str(tmp_path))
        try:
            assert app.games_path == str(tmp_path)
        finally:
            app.store.close()
    finally:
        config.gamestate_path = original_path
