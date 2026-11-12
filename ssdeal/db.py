"""SQLite storage. One service process owns the database (WAL mode)."""
from __future__ import annotations

import json
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any, Iterable

SCHEMA_VERSION = 1

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);

CREATE TABLE IF NOT EXISTS listings (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    ss_id           TEXT UNIQUE NOT NULL,      -- canonical ad path /msg/lv/.../xxxx.html
    ss_num          TEXT,                      -- numeric row id from list pages (tr_123)
    url             TEXT NOT NULL,
    feed_key        TEXT,
    category_path   TEXT,                      -- ss.lv category path from the url
    category_key    TEXT,                      -- our category (gpu, camera, lens ...)
    title           TEXT,
    description     TEXT,
    price           REAL,
    price_text      TEXT,
    location        TEXT,
    attrs           TEXT DEFAULT '{}',         -- JSON: parsed attributes
    image_url       TEXT,
    photos          TEXT DEFAULT '[]',
    product_key     TEXT,
    product_name    TEXT,
    brand           TEXT,
    condition       TEXT,                      -- new | used | broken | parts | untested | unknown
    flags           TEXT DEFAULT '[]',         -- JSON list: bundle, collection, buying, service ...
    is_buying       INTEGER DEFAULT 0,
    fingerprint     TEXT,
    repost_of       INTEGER,
    status          TEXT DEFAULT 'active',     -- active | removed
    first_seen      REAL NOT NULL,
    last_seen       REAL NOT NULL,
    posted_at       REAL,
    removed_at      REAL,
    detail_fetched  REAL,
    deal_score      REAL,
    personal_score  REAL,
    confidence      REAL,
    classification  TEXT,                      -- GOOD_DEAL | INTERESTING | IGNORE
    score_details   TEXT DEFAULT '{}',
    scored_at       REAL,
    saved           INTEGER DEFAULT 0,
    user_state      TEXT,                      -- interested | ignored | bought | too_expensive
    initial_price   REAL,
    min_price       REAL
);
CREATE INDEX IF NOT EXISTS ix_listings_status ON listings(status);
CREATE INDEX IF NOT EXISTS ix_listings_product ON listings(product_key);
CREATE INDEX IF NOT EXISTS ix_listings_cat ON listings(category_key);
CREATE INDEX IF NOT EXISTS ix_listings_first ON listings(first_seen);
CREATE INDEX IF NOT EXISTS ix_listings_deal ON listings(deal_score);
CREATE INDEX IF NOT EXISTS ix_listings_fp ON listings(fingerprint);

CREATE TABLE IF NOT EXISTS price_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    listing_id INTEGER NOT NULL,
    price REAL,
    observed_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_ph_listing ON price_history(listing_id);

CREATE TABLE IF NOT EXISTS listing_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    listing_id INTEGER NOT NULL,
    type TEXT NOT NULL,       -- created, price_change, removed, reappeared, detail, repost
    data TEXT DEFAULT '{}',
    at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_le_listing ON listing_events(listing_id);
CREATE INDEX IF NOT EXISTS ix_le_at ON listing_events(at);

CREATE TABLE IF NOT EXISTS market_stats (
    product_key TEXT NOT NULL,
    bucket TEXT NOT NULL,                     -- working | broken | all
    product_name TEXT,
    category_key TEXT,
    low REAL, typical REAL, high REAL,
    median REAL, mean REAL,
    n INTEGER, n_active INTEGER, n_sales INTEGER DEFAULT 0, n_corrections INTEGER DEFAULT 0,
    confidence REAL,
    basis TEXT,                               -- asking_prices | asking+sales | manual
    demand REAL,                              -- 0..1 how fast comparable ads disappear
    avg_days_listed REAL,
    bundle_premium REAL,
    updated_at REAL,
    PRIMARY KEY (product_key, bucket)
);

CREATE TABLE IF NOT EXISTS market_history (
    product_key TEXT NOT NULL,
    day TEXT NOT NULL,
    typical REAL, median REAL, low REAL, high REAL, n INTEGER,
    PRIMARY KEY (product_key, day)
);

CREATE TABLE IF NOT EXISTS market_corrections (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    product_key TEXT NOT NULL,
    value REAL NOT NULL,
    kind TEXT NOT NULL,          -- reference | sale | override
    note TEXT,
    listing_id INTEGER,
    created_at REAL NOT NULL,
    active INTEGER DEFAULT 1
);

CREATE TABLE IF NOT EXISTS feedback (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    listing_id INTEGER,
    kind TEXT NOT NULL,          -- rating, interested, saved, ignored, too_expensive, bought,
                                 -- would_pay, not_for_me, good_deal, brand_dislike, ...
    value REAL,
    text TEXT,
    source TEXT DEFAULT 'ui',    -- ui | discord | system
    snapshot TEXT DEFAULT '{}',  -- listing features at feedback time
    effect TEXT DEFAULT '',      -- human readable summary of the learning effect
    created_at REAL NOT NULL,
    active INTEGER DEFAULT 1,
    superseded_by INTEGER
);
CREATE INDEX IF NOT EXISTS ix_fb_listing ON feedback(listing_id);

CREATE TABLE IF NOT EXISTS notifications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    listing_id INTEGER NOT NULL,
    level TEXT NOT NULL,
    reason TEXT,
    price REAL,
    channels TEXT DEFAULT '[]',
    discord_message_id TEXT,
    rating INTEGER,
    read INTEGER DEFAULT 0,
    created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_notif_listing ON notifications(listing_id);
CREATE INDEX IF NOT EXISTS ix_notif_msg ON notifications(discord_message_id);

CREATE TABLE IF NOT EXISTS wants (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    keywords TEXT,
    category_key TEXT,
    max_price REAL,
    active INTEGER DEFAULT 1,
    created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS watchlist (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    query TEXT,                  -- words that must all appear (supports "a|b" alternatives)
    exclude TEXT,
    product_key TEXT,
    category_key TEXT,
    max_price REAL,
    min_deal REAL,
    condition TEXT,              -- any | new | used | working
    notify INTEGER DEFAULT 1,
    notify_drops INTEGER DEFAULT 1,
    active INTEGER DEFAULT 1,
    created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS watch_matches (
    watch_id INTEGER NOT NULL,
    listing_id INTEGER NOT NULL,
    matched_at REAL NOT NULL,
    price REAL,
    PRIMARY KEY (watch_id, listing_id)
);

CREATE TABLE IF NOT EXISTS roi_plans (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    listing_id INTEGER,
    title TEXT NOT NULL,
    product_key TEXT,
    purchase_price REAL DEFAULT 0,
    resale_price REAL DEFAULT 0,
    resale_low REAL, resale_high REAL,
    repair_cost REAL DEFAULT 0,
    transport_cost REAL DEFAULT 0,
    accessories_cost REAL DEFAULT 0,
    platform_fees REAL DEFAULT 0,
    other_costs REAL DEFAULT 0,
    expected_days INTEGER,
    status TEXT DEFAULT 'planned',  -- planned | bought | sold | skipped
    actual_purchase REAL, actual_repair REAL, actual_other REAL, actual_sale REAL,
    bought_at REAL, sold_at REAL,
    notes TEXT,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    notes TEXT,
    kind TEXT DEFAULT 'task',    -- task | reminder | purchase | resale | check | follow_up
    due_at REAL,
    remind_at REAL,
    listing_id INTEGER,
    plan_id INTEGER,
    done INTEGER DEFAULT 0,
    reminded INTEGER DEFAULT 0,
    created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_tasks_due ON tasks(due_at);

CREATE TABLE IF NOT EXISTS scan_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job TEXT NOT NULL,
    feed_key TEXT,
    started_at REAL NOT NULL,
    finished_at REAL,
    ok INTEGER,
    pages INTEGER DEFAULT 0,
    requests INTEGER DEFAULT 0,
    new_count INTEGER DEFAULT 0,
    updated_count INTEGER DEFAULT 0,
    removed_count INTEGER DEFAULT 0,
    error TEXT
);
CREATE INDEX IF NOT EXISTS ix_runs_started ON scan_runs(started_at);

CREATE TABLE IF NOT EXISTS app_errors (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    at REAL NOT NULL,
    source TEXT,
    message TEXT
);

CREATE TABLE IF NOT EXISTS pending_clarifications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    listing_id INTEGER,
    channel_message_id TEXT,
    text TEXT,
    options TEXT,
    created_at REAL NOT NULL,
    resolved INTEGER DEFAULT 0
);
"""


class Database:
    def __init__(self, path: Path | str):
        self.path = str(path)
        self._lock = threading.RLock()
        self.conn = sqlite3.connect(self.path, check_same_thread=False, timeout=30)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA synchronous=NORMAL")
        self.conn.execute("PRAGMA foreign_keys=OFF")
        self.conn.executescript(SCHEMA)
        have = {r[1] for r in self.conn.execute("PRAGMA table_info(listings)")}
        for col in ("profit_est", "roi_est"):          # added in 1.2: stored so the listing tab can sort by them
            if col not in have:
                self.conn.execute(f"ALTER TABLE listings ADD COLUMN {col} REAL")
        have_n = {r[1] for r in self.conn.execute("PRAGMA table_info(notifications)")}
        for col, typ in (("push_pending", "INTEGER DEFAULT 0"), ("pushed_at", "REAL"), ("push_errors", "TEXT"), ("high_roi", "INTEGER DEFAULT 0")):
            if col not in have_n:                                                       # added in 1.4: reliable push delivery
                self.conn.execute(f"ALTER TABLE notifications ADD COLUMN {col} {typ}")
        if "own_typical" not in {r[1] for r in self.conn.execute("PRAGMA table_info(market_stats)")}:
            self.conn.execute("ALTER TABLE market_stats ADD COLUMN own_typical REAL")   # the app's own estimate, kept next to a user override
        self.conn.execute(
            "INSERT OR IGNORE INTO meta(key, value) VALUES('schema_version', ?)", (str(SCHEMA_VERSION),)
        )
        self.conn.commit()

    # ---- basic helpers
    def execute(self, sql: str, params: Iterable[Any] = ()) -> sqlite3.Cursor:
        with self._lock:
            cur = self.conn.execute(sql, tuple(params))
            self.conn.commit()
            return cur

    def executemany(self, sql: str, rows: Iterable[Iterable[Any]]) -> None:
        with self._lock:
            self.conn.executemany(sql, rows)
            self.conn.commit()

    def query(self, sql: str, params: Iterable[Any] = ()) -> list[dict]:
        with self._lock:
            return [dict(r) for r in self.conn.execute(sql, tuple(params)).fetchall()]

    def one(self, sql: str, params: Iterable[Any] = ()) -> dict | None:
        with self._lock:
            r = self.conn.execute(sql, tuple(params)).fetchone()
            return dict(r) if r else None

    def scalar(self, sql: str, params: Iterable[Any] = (), default: Any = None) -> Any:
        with self._lock:
            r = self.conn.execute(sql, tuple(params)).fetchone()
            return r[0] if r and r[0] is not None else default

    def insert(self, table: str, row: dict) -> int:
        cols = ",".join(row.keys())
        qs = ",".join("?" for _ in row)
        with self._lock:
            cur = self.conn.execute(f"INSERT INTO {table} ({cols}) VALUES ({qs})", tuple(row.values()))
            self.conn.commit()
            return int(cur.lastrowid)

    def update(self, table: str, row_id: int, values: dict, key: str = "id") -> None:
        if not values:
            return
        sets = ",".join(f"{k}=?" for k in values)
        with self._lock:
            self.conn.execute(f"UPDATE {table} SET {sets} WHERE {key}=?", (*values.values(), row_id))
            self.conn.commit()

    def transaction(self):
        return _Tx(self)

    def get_meta(self, key: str, default: str | None = None) -> str | None:
        r = self.one("SELECT value FROM meta WHERE key=?", (key,))
        return r["value"] if r else default

    def set_meta(self, key: str, value: str) -> None:
        self.execute("INSERT INTO meta(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                     (key, value))

    def log_error(self, source: str, message: str) -> None:
        self.execute("INSERT INTO app_errors(at, source, message) VALUES(?,?,?)",
                     (time.time(), source, message[:2000]))

    def backup_to(self, dest: Path) -> None:
        with self._lock:
            target = sqlite3.connect(str(dest))
            try:
                self.conn.backup(target)
            finally:
                target.close()

    def close(self) -> None:
        with self._lock:
            self.conn.close()


class _Tx:
    def __init__(self, db: Database):
        self.db = db

    def __enter__(self):
        self.db._lock.acquire()
        self.db.conn.execute("BEGIN")
        return self.db.conn

    def __exit__(self, exc_type, exc, tb):
        try:
            if exc_type:
                self.db.conn.rollback()
            else:
                self.db.conn.commit()
        finally:
            self.db._lock.release()
        return False


def jloads(s: str | None, default: Any = None) -> Any:
    if not s:
        return default
    try:
        return json.loads(s)
    except (TypeError, json.JSONDecodeError):
        return default


def jdumps(v: Any) -> str:
    return json.dumps(v, ensure_ascii=False, separators=(",", ":"))
