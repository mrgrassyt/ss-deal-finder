"""SQLite storage: one table of content items (any type from schema.py) and a small key/value table for settings."""
from __future__ import annotations

import json
import secrets
import sqlite3
import threading
import time
from pathlib import Path

from .schema import TYPES, slugify

META = ("id", "type", "slug", "published", "created", "updated")


class DB:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.con = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
        self.con.row_factory = sqlite3.Row
        self.lock = threading.Lock()
        self.con.executescript("""
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS items (id INTEGER PRIMARY KEY, type TEXT NOT NULL, slug TEXT NOT NULL, published INTEGER NOT NULL DEFAULT 1,
                created REAL NOT NULL, updated REAL NOT NULL, data TEXT NOT NULL, UNIQUE(type, slug));
            CREATE INDEX IF NOT EXISTS items_type ON items(type, created);
            CREATE TABLE IF NOT EXISTS kv (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        """)

    # ---- settings -------------------------------------------------------------------------------------------------
    def kv(self, key: str, default=None):
        with self.lock:
            row = self.con.execute("SELECT value FROM kv WHERE key=?", (key,)).fetchone()
        return json.loads(row["value"]) if row else default

    def set_kv(self, key: str, value) -> None:
        with self.lock:
            self.con.execute("INSERT INTO kv (key, value) VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, json.dumps(value)))

    # ---- items ----------------------------------------------------------------------------------------------------
    @staticmethod
    def _item(row) -> dict:
        return {**json.loads(row["data"]), **{k: row[k] for k in META}, "published": bool(row["published"])}

    def all(self, type_: str, public: bool = False) -> list[dict]:
        """Newest first. public=True leaves out drafts."""
        with self.lock:
            rows = self.con.execute(f"SELECT * FROM items WHERE type=? {'AND published=1' if public else ''} ORDER BY created DESC, id DESC", (type_,)).fetchall()
        return [self._item(r) for r in rows]

    def one(self, type_: str, slug: str, public: bool = False) -> dict | None:
        with self.lock:
            row = self.con.execute("SELECT * FROM items WHERE type=? AND slug=?", (type_, slug)).fetchone()
        return self._item(row) if row and (row["published"] or not public) else None

    def by_id(self, id_: int) -> dict | None:
        with self.lock:
            row = self.con.execute("SELECT * FROM items WHERE id=?", (id_,)).fetchone()
        return self._item(row) if row else None

    def _free_slug(self, type_: str, want: str, id_: int | None) -> str:
        base = slugify(want) or secrets.token_hex(4)
        slug, n = base, 1
        while True:
            row = self.con.execute("SELECT id FROM items WHERE type=? AND slug=?", (type_, slug)).fetchone()
            if not row or row["id"] == id_:
                return slug
            n += 1
            slug = f"{base}-{n}"

    def save(self, type_: str, data: dict, id_: int | None = None, published: bool = True, slug: str = "", created: float | None = None) -> dict:
        now = time.time()
        with self.lock:
            if id_:
                old = self.con.execute("SELECT slug FROM items WHERE id=? AND type=?", (id_, type_)).fetchone()
                if not old:
                    raise KeyError(id_)
                slug = self._free_slug(type_, slug, id_) if slug else old["slug"]
                self.con.execute("UPDATE items SET slug=?, published=?, updated=?, data=? WHERE id=?", (slug, int(published), now, json.dumps(data), id_))
            else:
                slug = self._free_slug(type_, slug or str(data.get(TYPES[type_]["title"]) or ""), None)
                id_ = self.con.execute("INSERT INTO items (type, slug, published, created, updated, data) VALUES (?,?,?,?,?,?)",
                                       (type_, slug, int(published), created or now, now, json.dumps(data))).lastrowid
        return self.by_id(id_)

    def delete(self, id_: int) -> None:
        with self.lock:
            self.con.execute("DELETE FROM items WHERE id=?", (id_,))

    def count(self, type_: str) -> int:
        with self.lock:
            return self.con.execute("SELECT COUNT(*) FROM items WHERE type=?", (type_,)).fetchone()[0]

    def media_in_use(self) -> str:
        """All item and settings JSON in one string: enough to check whether an uploaded file is still referenced."""
        with self.lock:
            rows = self.con.execute("SELECT data FROM items UNION ALL SELECT value FROM kv").fetchall()
        return "\n".join(r[0] for r in rows)
