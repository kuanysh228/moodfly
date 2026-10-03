import json
import secrets
import sqlite3
import threading
import time

from .paths import DATA

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY, nick TEXT UNIQUE NOT NULL COLLATE NOCASE, token TEXT UNIQUE NOT NULL, created REAL
);
CREATE TABLE IF NOT EXISTS pets (
    id INTEGER PRIMARY KEY, owner_id INTEGER UNIQUE NOT NULL REFERENCES users(id), name TEXT NOT NULL,
    genome TEXT NOT NULL, checkup TEXT NOT NULL, points TEXT NOT NULL DEFAULT '{}',
    level INTEGER NOT NULL DEFAULT 1, xp INTEGER NOT NULL DEFAULT 0, unspent INTEGER NOT NULL DEFAULT 0,
    wins INTEGER NOT NULL DEFAULT 0, losses INTEGER NOT NULL DEFAULT 0, draws INTEGER NOT NULL DEFAULT 0,
    memory BLOB, flags TEXT NOT NULL DEFAULT '{}', created REAL
);
CREATE TABLE IF NOT EXISTS battles (
    id INTEGER PRIMARY KEY, a_pet INTEGER, b_pet INTEGER, winner INTEGER, summary TEXT, created REAL
);
"""

PET_JSON = ("genome", "checkup", "points", "flags")


class DB:
    def __init__(self, path=DATA / "moodfly.db"):
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        self.lock = threading.Lock()

    def _one(self, sql: str, args=()) -> dict | None:
        with self.lock:
            row = self.conn.execute(sql, args).fetchone()
        return dict(row) if row else None

    def _exec(self, sql: str, args=()) -> int:
        with self.lock:
            cur = self.conn.execute(sql, args)
            self.conn.commit()
            return cur.lastrowid

    def register(self, nick: str) -> dict | None:
        token = secrets.token_urlsafe(24)
        try:
            uid = self._exec("INSERT INTO users (nick, token, created) VALUES (?, ?, ?)", (nick, token, time.time()))
        except sqlite3.IntegrityError:
            return None
        return {"id": uid, "nick": nick, "token": token}

    def user_by_token(self, token: str) -> dict | None:
        return self._one("SELECT * FROM users WHERE token = ?", (token,))

    @staticmethod
    def _pet(row: dict | None) -> dict | None:
        if row:
            for k in PET_JSON:
                row[k] = json.loads(row[k])
        return row

    def create_pet(self, owner_id: int, name: str, genome: dict, checkup: dict) -> dict:
        pid = self._exec(
            "INSERT INTO pets (owner_id, name, genome, checkup, created) VALUES (?, ?, ?, ?, ?)",
            (owner_id, name, json.dumps(genome), json.dumps(checkup), time.time()),
        )
        return self.pet(pid)

    def pet(self, pid: int) -> dict | None:
        return self._pet(self._one("SELECT p.*, u.nick AS owner FROM pets p JOIN users u ON u.id = p.owner_id WHERE p.id = ?", (pid,)))

    def pet_of(self, owner_id: int) -> dict | None:
        return self._pet(self._one("SELECT p.*, u.nick AS owner FROM pets p JOIN users u ON u.id = p.owner_id WHERE owner_id = ?", (owner_id,)))

    def pets(self) -> list[dict]:
        with self.lock:
            rows = self.conn.execute(
                "SELECT p.*, u.nick AS owner FROM pets p JOIN users u ON u.id = p.owner_id ORDER BY p.level DESC, p.wins DESC"
            ).fetchall()
        return [self._pet(dict(r)) for r in rows]

    def update_pet(self, pid: int, **fields) -> None:
        if not fields:
            return
        cols, vals = [], []
        for k, v in fields.items():
            cols.append(f"{k} = ?")
            vals.append(json.dumps(v) if k in PET_JSON else v)
        self._exec(f"UPDATE pets SET {', '.join(cols)} WHERE id = ?", (*vals, pid))

    def save_battle(self, a: int, b: int, winner: int | None, summary: dict) -> int:
        return self._exec(
            "INSERT INTO battles (a_pet, b_pet, winner, summary, created) VALUES (?, ?, ?, ?, ?)",
            (a, b, winner, json.dumps(summary, ensure_ascii=False), time.time()),
        )
