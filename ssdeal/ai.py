"""AI second opinion (Google Gemini) on what an ad is actually selling.

The normal rules decide first. Before an alert goes out (and in the background for listings the rules found
interesting), Gemini reads the ad and answers a few narrow questions: is this the device itself or a part/accessory
for it, what exactly is it (model, generation, specs), what condition, and does the rules' guess name the right item.
It never invents prices; prices still come from real listings.

Where the key lives:
  * on a multi-user server: the admin's key, set once under Manage users. One check per ad is shared by every account
    (the hub caches it), so friends do not add cost;
  * on the desktop app, or for a user with their own key: Settings -> AI check.
"""
from __future__ import annotations

import hashlib
import json
import os
import time

import httpx

from .feeds import CATEGORIES
from .logs import get_logger

log = get_logger("ai")
DEFAULT_MODEL = "gemini-3.5-flash-lite"
API = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
KINDS = ("device", "part", "accessory", "bundle", "service", "wanted")
CONDITIONS = ("new", "used", "broken", "parts", "unknown")

SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "kind": {"type": "STRING", "enum": list(KINDS)},
        "item": {"type": "STRING"},
        "category": {"type": "STRING"},
        "condition": {"type": "STRING", "enum": list(CONDITIONS)},
        "guess_ok": {"type": "BOOLEAN"},
        "problem": {"type": "STRING"},
        "confidence": {"type": "NUMBER"},
    },
    "required": ["kind", "item", "category", "condition", "guess_ok", "problem", "confidence"],
}


def text_hash(title: str, description: str) -> str:
    return hashlib.sha1(f"{(title or '').strip()}\n{(description or '').strip()[:1500]}".encode()).hexdigest()[:20]


def item_from_listing(row: dict) -> dict:
    return {"title": row.get("title") or "", "description": (row.get("description") or "")[:1500], "price": row.get("price"),
            "ss_path": row.get("ss_path") or "", "guess": {"product": row.get("product_name") or row.get("product_key") or "unknown",
                                                          "category": row.get("category_key") or "other",
                                                          "kind": "part/accessory" if any(f in (row.get("flags") or "") for f in ("part", "accessory")) else "device",
                                                          "condition": row.get("condition") or "unknown"},
            "hash": text_hash(row.get("title") or "", row.get("description") or "")}


def prompt(item: dict) -> str:
    g = item.get("guess") or {}
    return f"""You check second-hand ads from SS.lv (Latvia). The text may be Latvian, Russian or English.
Decide what is ACTUALLY for sale. Do not estimate any price.

Rules:
- A part or accessory FOR a device (an SSD for a PS5, a case or battery for an iPhone, a cooler or cable for an RTX 3070,
  a controller or stand for a console) is "part" or "accessory", not "device".
- A device sold together with extras (console + 2 controllers + games) is "bundle" (or "device").
- Someone looking to buy ("pērku", "куплю", "wanted") is "wanted"; repairs, rentals, other services are "service".
- Look-alike names: GDDR5/GDDR6 is graphics-card memory, not DDR5/DDR6 RAM; "for PS5" does not make an SSD a PS5;
  MacBook Air 2013 and 2020 are different products; check generation, year, capacity and model numbers.
- "pārdodu rezerves daļās", "uz daļām", "на запчасти" = the whole device, broken or for parts: kind "device", condition "parts".

Our rule-based guess: product = {g.get('product')}; category = {g.get('category')}; kind = {g.get('kind')}; condition = {g.get('condition')}.

Ad:
Title: {item.get('title')}
Price: {item.get('price')} EUR
SS.lv section: {item.get('ss_path')}
Description: {item.get('description') or '(none)'}

Answer in JSON:
kind: device | part | accessory | bundle | service | wanted
item: the exact item for sale, short, in English, with the key specs (e.g. "WD Black SN850X 2TB NVMe SSD (for PS5)")
category: one of {', '.join(sorted(CATEGORIES))}
condition: new | used | broken | parts | unknown
guess_ok: true if our product guess names the item that is for sale (same model, generation and main specs), else false
problem: if guess_ok is false or kind is not device/bundle, ONE short sentence why; otherwise ""
confidence: 0 to 1, how sure you are"""


def clean(d: dict) -> dict | None:
    try:
        out = {"kind": d["kind"] if d.get("kind") in KINDS else "device",
               "item": str(d.get("item") or "")[:140],
               "category": d.get("category") if d.get("category") in CATEGORIES else "other",
               "condition": d["condition"] if d.get("condition") in CONDITIONS else "unknown",
               "guess_ok": bool(d.get("guess_ok", True)),
               "problem": str(d.get("problem") or "")[:240],
               "confidence": max(0.0, min(1.0, float(d.get("confidence") or 0)))}
        return out
    except (TypeError, ValueError, KeyError):
        return None


class AIError(Exception):
    pass


async def ask_gemini(key: str, item: dict, model: str = DEFAULT_MODEL, transport: httpx.AsyncBaseTransport | None = None) -> dict:
    """One Gemini call. Raises AIError with a plain reason on any failure (bad key, quota, unexpected answer)."""
    body = {"contents": [{"role": "user", "parts": [{"text": prompt(item)}]}],
            "generationConfig": {"temperature": 0, "responseMimeType": "application/json", "responseSchema": SCHEMA}}
    url = os.environ.get("SSDEAL_GEMINI_URL") or API.format(model=model)
    try:
        async with httpx.AsyncClient(timeout=40, transport=transport) as c:
            r = await c.post(url, json=body, headers={"x-goog-api-key": key})
    except httpx.HTTPError as e:
        raise AIError(f"could not reach Gemini: {e}") from e
    if r.status_code == 429:
        raise AIError("Gemini quota used up for now (free tier limit) — try again later")
    if r.status_code in (400, 401, 403):
        try:
            msg = r.json().get("error", {}).get("message", "")
        except ValueError:
            msg = ""
        raise AIError(f"Gemini refused the request ({r.status_code}): {msg[:160] or 'check the API key and model name'}")
    if r.status_code != 200:
        raise AIError(f"Gemini error HTTP {r.status_code}")
    try:
        text = r.json()["candidates"][0]["content"]["parts"][0]["text"]
        out = clean(json.loads(text))
    except (ValueError, KeyError, IndexError, TypeError) as e:
        raise AIError(f"unexpected answer from Gemini: {e}") from e
    if not out:
        raise AIError("unexpected answer from Gemini")
    return out


class AIReviewer:
    """Per-account checker. Uses the account's own key if it has one, otherwise the server's shared one (hub)."""

    def __init__(self, db, settings, transport: httpx.AsyncBaseTransport | None = None):
        self.db, self.settings, self.transport = db, settings, transport
        self.broker = os.environ.get("SSDEAL_FETCH_BROKER", "").rstrip("/")
        self.token = os.environ.get("SSDEAL_BROKER_TOKEN", "")
        self.pause_until = 0.0
        self.last_error = ""

    def cfg(self) -> dict:
        return self.settings.get("ai", {}) or {}

    def own_key(self) -> str:
        return self.settings.secret("gemini_api_key") or ""

    def available(self) -> bool:
        return bool(self.cfg().get("enabled", True)) and bool(self.own_key() or (self.broker and self.token)) \
            and time.time() >= self.pause_until

    def used_today(self) -> int:
        day0 = time.mktime(time.localtime()[:3] + (0, 0, 0, 0, 0, -1))
        return int(self.db.scalar("SELECT COUNT(*) FROM ai_reviews WHERE at>=? AND source!='cache'", (day0,)) or 0)

    def stored(self, listing: dict) -> dict | None:
        if not listing.get("id"):
            return None
        row = self.db.one("SELECT text_hash, result FROM ai_reviews WHERE listing_id=?", (listing["id"],))
        if not row or row["text_hash"] != text_hash(listing.get("title") or "", listing.get("description") or ""):
            return None
        try:
            return json.loads(row["result"])
        except ValueError:
            return None

    def server_has_key(self) -> bool:
        if not (self.broker and self.token):
            return False
        try:
            return bool(httpx.get(self.broker + "/ai_status", headers={"X-Broker-Token": self.token}, timeout=3).json().get("key_set"))
        except (httpx.HTTPError, ValueError):
            return False

    def status(self) -> dict:
        shared = False if self.own_key() else self.server_has_key()
        return {"available": self.available(), "own_key": bool(self.own_key()), "shared": shared, "on_server": bool(self.broker),
                "used_today": self.used_today(), "daily_limit": int(self.cfg().get("daily_limit", 300)),
                "model": self.cfg().get("model") or DEFAULT_MODEL, "last_error": self.last_error}

    async def check(self, row: dict) -> dict | None:
        """Review one listing (cached per ad text). Returns the review or None (off, limit reached, error)."""
        if not self.available():
            return None
        item = item_from_listing(dict(row))
        have = self.stored(dict(row))
        if have:
            return have
        if self.used_today() >= int(self.cfg().get("daily_limit", 300)):
            return None
        source = "own"
        try:
            if self.own_key():
                res = await ask_gemini(self.own_key(), item, self.cfg().get("model") or DEFAULT_MODEL, self.transport)
            else:
                source = "server"
                async with httpx.AsyncClient(timeout=60, transport=self.transport) as c:
                    r = await c.post(self.broker + "/ai", json={"item": item}, headers={"X-Broker-Token": self.token})
                d = r.json()
                if r.status_code != 200:
                    raise AIError(d.get("detail", f"HTTP {r.status_code}"))
                res, source = clean(d["review"]), ("cache" if d.get("cached") else "server")
                if not res:
                    raise AIError("bad answer from the server")
        except (AIError, httpx.HTTPError, ValueError, KeyError) as e:
            self.last_error = str(e)
            self.pause_until = time.time() + 600                 # back off 10 minutes, the rules keep working meanwhile
            log.event("ai.error", str(e), _level=30)
            return None
        self.last_error = ""
        self.db.execute("INSERT OR REPLACE INTO ai_reviews (listing_id, text_hash, result, at, source) VALUES (?,?,?,?,?)",
                        (row["id"], item["hash"], json.dumps(res), time.time(), source))
        return res


def apply_review(ai: dict, level: str, why: str, listing: dict, min_conf: float = 0.6) -> tuple[str, str, list[str]]:
    """How an AI review changes the label. Returns (level, why, flags)."""
    flags: list[str] = []
    if ai["confidence"] < min_conf:
        return level, why, ["ai_unsure"]
    rule_part = any(f in (listing.get("flags") or "") for f in ("part", "accessory"))
    if ai["kind"] in ("part", "accessory") and not rule_part:
        flags.append("ai_part")
        if level != "IGNORE":
            return "IGNORE", f"AI check: {ai['item'] or 'this'} is a {ai['kind']}, not the device itself" + \
                (f" — {ai['problem']}" if ai["problem"] else ""), flags
    elif ai["kind"] in ("wanted", "service"):
        flags.append("ai_" + ai["kind"])
        if level != "IGNORE":
            return "IGNORE", f"AI check: this is a {'buyer looking for an item' if ai['kind'] == 'wanted' else 'service'}", flags
    elif not ai["guess_ok"]:
        flags.append("ai_mismatch")
        if level != "IGNORE":
            return "IGNORE", f"AI check: wrong product match — {ai['problem'] or ai['item']}", flags
    elif ai["condition"] in ("broken", "parts") and listing.get("condition") not in ("broken", "parts", "untested"):
        flags.append("ai_condition")
        if level == "GOOD_DEAL":
            return "INTERESTING", f"AI check: looks {ai['condition']} — {ai['problem'] or 'check the description'}", flags
    else:
        flags.append("ai_ok")
        return level, f"{why} · AI check OK: {ai['item']}" if ai["item"] else why, flags
    return level, why, flags
