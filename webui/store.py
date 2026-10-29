"""The prompt feed: one record of everything a game showed its players.

Both surfaces write here. Discord records the messages it posts, the web renders
records and presses the buttons on them. The brightness of that idea is that the
engine only ever talks to a duck-typed interaction, so nothing in Buttons/ or
helpers/ knows which surface it is serving.

A record id is the canonical message id. Discord's own id is kept beside it so a
press arriving from either side compares the same `lastButtonMessage`.
"""
import hashlib
import json
import os
import sqlite3
import time

SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    token_hash TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    expires_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS mirror_jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    game_id TEXT NOT NULL,
    message_id INTEGER NOT NULL,
    operation TEXT NOT NULL,
    payload TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS games (
    game_id TEXT PRIMARY KEY,
    mirror_to_discord INTEGER NOT NULL DEFAULT 1,
    created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    game_id TEXT NOT NULL,
    room TEXT NOT NULL,
    author_id TEXT,
    content TEXT,
    buttons TEXT,
    attachments TEXT,
    ephemeral_to TEXT,
    discord_id TEXT,
    deleted INTEGER NOT NULL DEFAULT 0,
    rev INTEGER NOT NULL,
    created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS messages_by_game ON messages (game_id, rev);
CREATE UNIQUE INDEX IF NOT EXISTS messages_by_discord ON messages (game_id, discord_id)
    WHERE discord_id IS NOT NULL;
"""


def buttons_from_view(view):
    """A view is inert data: keep only what a browser can render and press."""
    buttons = []
    for child in getattr(view, "children", []):
        buttons.append({
            "label": getattr(child, "label", None),
            "custom_id": getattr(child, "custom_id", None),
            "style": int(getattr(child, "style", 2)),
            "disabled": bool(getattr(child, "disabled", False)),
            "url": getattr(child, "url", None),
        })
    return buttons


class FeedStore:
    def __init__(self, path):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        columns = {row["name"] for row in self.conn.execute("PRAGMA table_info(messages)")}
        if "combat" not in columns:
            self.conn.execute("ALTER TABLE messages ADD COLUMN combat TEXT")
        self.conn.commit()

    def close(self):
        self.conn.close()

    def save_session(self, token, user_id, expires_at):
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        with self.conn:
            self.conn.execute("DELETE FROM sessions WHERE expires_at <= ?", (time.time(),))
            self.conn.execute("INSERT INTO sessions VALUES (?, ?, ?)",
                              (token_hash, user_id, expires_at))

    def session_user(self, token):
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        row = self.conn.execute(
            "SELECT user_id FROM sessions WHERE token_hash = ? AND expires_at > ?",
            (token_hash, time.time())).fetchone()
        if row is None:
            return None
        with self.conn:
            self.conn.execute("UPDATE sessions SET expires_at = ? WHERE token_hash = ?",
                              (time.time() + 604800, token_hash))
        return row["user_id"]

    def delete_session(self, token):
        with self.conn:
            self.conn.execute("DELETE FROM sessions WHERE token_hash = ?",
                              (hashlib.sha256(token.encode()).hexdigest(),))

    # -- games ------------------------------------------------------------
    def ensure_game(self, game_id, mirror_to_discord=1):
        self.conn.execute(
            "INSERT OR IGNORE INTO games (game_id, mirror_to_discord, created_at) VALUES (?, ?, ?)",
            (game_id, int(mirror_to_discord), time.time()))
        self.conn.commit()

    def game(self, game_id):
        row = self.conn.execute("SELECT * FROM games WHERE game_id = ?", (game_id,)).fetchone()
        if row is None:
            self.ensure_game(game_id)
            return self.game(game_id)
        return dict(row)

    def set_mirror(self, game_id, mirror_to_discord):
        self.ensure_game(game_id)
        self.conn.execute("UPDATE games SET mirror_to_discord = ? WHERE game_id = ?",
                          (int(bool(mirror_to_discord)), game_id))
        self.conn.commit()

    def mirrors(self, game_id):
        return bool(self.game(game_id)["mirror_to_discord"])

    def enqueue_mirror(self, game_id, message_id, operation, payload):
        with self.conn:
            self.conn.execute(
                "INSERT INTO mirror_jobs (game_id, message_id, operation, payload) VALUES (?, ?, ?, ?)",
                (game_id, message_id, operation, json.dumps(payload)))

    def next_mirror_job(self):
        row = self.conn.execute("SELECT * FROM mirror_jobs ORDER BY id LIMIT 1").fetchone()
        return dict(row) if row else None

    def finish_mirror_job(self, job_id):
        with self.conn:
            self.conn.execute("DELETE FROM mirror_jobs WHERE id = ?", (job_id,))

    # -- messages ---------------------------------------------------------
    def _next_rev(self):
        return self.conn.execute("SELECT COALESCE(MAX(rev), 0) + 1 FROM messages").fetchone()[0]

    def record(self, game_id, room, content=None, buttons=None, attachments=None,
               ephemeral_to=None, author_id=None, discord_id=None, combat=None):
        rev = self._next_rev()
        cur = self.conn.execute(
            "INSERT INTO messages (game_id, room, author_id, content, buttons, attachments,"
            " ephemeral_to, discord_id, rev, created_at, combat) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (game_id, room, author_id, content,
             json.dumps(buttons or []), json.dumps(attachments or []),
             ephemeral_to, None if discord_id is None else str(discord_id),
             rev, time.time(), json.dumps(combat or {})))
        self.conn.commit()
        return cur.lastrowid

    def update(self, message_id, content=None, buttons=None, attachments=None):
        row = self.get(message_id)
        if row is None:
            return
        self.conn.execute(
            "UPDATE messages SET content = ?, buttons = ?, attachments = ?, rev = ? WHERE id = ?",
            (row["content"] if content is None else content,
             json.dumps(row["buttons"] if buttons is None else buttons),
             json.dumps(row["attachments"] if attachments is None else attachments),
             self._next_rev(), message_id))
        self.conn.commit()

    def remove(self, message_id):
        self.conn.execute("UPDATE messages SET deleted = 1, rev = ? WHERE id = ?",
                          (self._next_rev(), message_id))
        self.conn.commit()

    def clear_buttons(self, message_id):
        """Keep the record and its canonical id, but retire its choices."""
        row = self.get(message_id)
        if row is None or row["deleted"] or not row["buttons"]:
            return
        self.update(message_id, buttons=[])

    def set_buttons(self, message_id, buttons):
        row = self.get(message_id)
        if row is None or row["deleted"]:
            return
        self.update(message_id, buttons=buttons)

    def prompts_in_room(self, game_id, room):
        rows = self.conn.execute(
            "SELECT * FROM messages WHERE game_id = ? AND room = ? AND deleted = 0"
            " AND buttons != '[]' ORDER BY id ASC", (game_id, room)).fetchall()
        return [self._as_message(row) for row in rows]

    def attach_discord(self, message_id, discord_id, room):
        self.conn.execute("UPDATE messages SET discord_id = ? WHERE id = ?", (str(discord_id), message_id))
        self.conn.commit()

    def get(self, message_id):
        row = self.conn.execute("SELECT * FROM messages WHERE id = ?", (message_id,)).fetchone()
        return self._as_message(row) if row else None

    def by_discord_id(self, game_id, discord_id):
        row = self.conn.execute(
            "SELECT * FROM messages WHERE game_id = ? AND discord_id = ?",
            (game_id, str(discord_id))).fetchone()
        return self._as_message(row) if row else None

    @staticmethod
    def _as_message(row):
        message = dict(row)
        message["buttons"] = json.loads(message["buttons"] or "[]")
        message["attachments"] = json.loads(message["attachments"] or "[]")
        message["combat"] = json.loads(message.get("combat") or "{}")
        message["deleted"] = bool(message["deleted"])
        return message

    def rev(self, game_id):
        """Latest feed change for a game, so a snapshot cache knows when to drop."""
        return self.conn.execute(
            "SELECT COALESCE(MAX(rev), 0) FROM messages WHERE game_id = ?", (game_id,)).fetchone()[0]

    def open_messages(self, game_id, seat, limit=25):
        """Prompts this seat may still answer, newest first."""
        rows = self.conn.execute(
            "SELECT * FROM messages WHERE game_id = ? AND deleted = 0"
            " AND (ephemeral_to IS NULL OR ephemeral_to = ?)"
            " ORDER BY id DESC LIMIT ?", (game_id, seat, limit)).fetchall()
        return [self._as_message(row) for row in rows]

    def pending_messages(self, game_id, seat, include_deleted=False):
        """Every prompt this seat can still answer, independent of the history page.

        The history is paged and capped; an unresolved choice must never fall off it.
        """
        rows = self.conn.execute(
            "SELECT * FROM messages WHERE game_id = ? AND (deleted = 0 OR ?)"
            " AND buttons != '[]'"
            " AND (ephemeral_to IS NULL OR ephemeral_to = ?)"
            " ORDER BY id ASC", (game_id, include_deleted, seat)).fetchall()
        return [self._as_message(row) for row in rows]

    def combat_history(self, game_id, seat):
        rows = self.conn.execute(
            "SELECT * FROM messages WHERE game_id = ?"
            " AND (room LIKE '%combat%' OR room LIKE '%battle%' OR room LIKE '%bombing%')"
            " AND (ephemeral_to IS NULL OR ephemeral_to = ?) ORDER BY id ASC",
            (game_id, seat)).fetchall()
        return [self._as_message(row) for row in rows]

    def visible_history(self, game_id, seat, limit=60):
        rows = self.conn.execute(
            "SELECT * FROM messages WHERE game_id = ?"
            " AND (ephemeral_to IS NULL OR ephemeral_to = ?)"
            " ORDER BY id DESC LIMIT ?", (game_id, seat, limit)).fetchall()
        return [self._as_message(row) for row in rows]

    def history_page(self, game_id, seat, before=None, limit=40):
        """One page of the full feed, newest first, including used prompts."""
        if before is None:
            rows = self.conn.execute(
                "SELECT * FROM messages WHERE game_id = ?"
                " AND (ephemeral_to IS NULL OR ephemeral_to = ?)"
                " ORDER BY id DESC LIMIT ?", (game_id, seat, limit)).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT * FROM messages WHERE game_id = ? AND id < ?"
                " AND (ephemeral_to IS NULL OR ephemeral_to = ?)"
                " ORDER BY id DESC LIMIT ?", (game_id, before, seat, limit)).fetchall()
        messages = [self._as_message(row) for row in rows]
        has_more = False
        if messages:
            has_more = self.conn.execute(
                "SELECT 1 FROM messages WHERE game_id = ? AND id < ?"
                " AND (ephemeral_to IS NULL OR ephemeral_to = ?) LIMIT 1",
                (game_id, messages[-1]["id"], seat)).fetchone() is not None
        return messages, has_more

