"""HTTP API used by the desktop UI (and later the Android companion / remote access)."""
from __future__ import annotations

import csv
import io
import json
import mimetypes
import shutil
import sqlite3
import time
from pathlib import Path
from typing import Any

from fastapi import Body, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from . import __version__
from .catalog import identify
from .config import DEFAULT_SETTINGS, WEB_DIR
from .db import jdumps, jloads
from .feeds import CATEGORIES, FEEDS, effective_feeds
from .logs import ring

SORTS = {
    "newest": "first_seen DESC",
    "cheapest": "price IS NULL, price ASC",
    "expensive": "price IS NULL, price DESC",
    "deal": "deal_score IS NULL, deal_score DESC",
    "personal": "personal_score IS NULL, personal_score DESC",
    "profit": "profit_est IS NULL, profit_est DESC",
    "roi": "roi_est IS NULL, roi_est DESC",
    "drop": "(COALESCE(initial_price,price) - price) / NULLIF(initial_price,0) DESC",
    "updated": "last_seen DESC",
}
SORT_TIEBREAK = ", id DESC"   # without a tie-breaker equal values come back in random order and pages overlap

EXPORTABLE = {
    "listings": "SELECT id, ss_id, url, title, description, price, initial_price, min_price, category_key, product_key, "
                "product_name, brand, condition, flags, status, first_seen, last_seen, removed_at, deal_score, "
                "personal_score, confidence, classification, saved, user_state FROM listings",
    "price_history": "SELECT * FROM price_history",
    "listing_events": "SELECT * FROM listing_events",
    "market": "SELECT * FROM market_stats",
    "market_history": "SELECT * FROM market_history",
    "market_corrections": "SELECT * FROM market_corrections",
    "feedback": "SELECT * FROM feedback",
    "notifications": "SELECT * FROM notifications",
    "watchlist": "SELECT * FROM watchlist",
    "roi_plans": "SELECT * FROM roi_plans",
    "tasks": "SELECT * FROM tasks",
    "scan_runs": "SELECT * FROM scan_runs",
}


_SETTINGS = None  # set by create_api so list rows can estimate a flip with the user's own assumptions


def _flip(r: dict, det: dict) -> dict | None:
    from .flip import compute_flip
    return compute_flip(r.get("price"), r.get("condition"), det, (_SETTINGS.get("flip", {}) if _SETTINGS else {}) or {})


def _row_listing(r: dict, full: bool = False) -> dict:
    r = dict(r)
    r["flags"] = jloads(r.get("flags"), [])
    r["attrs"] = jloads(r.get("attrs"), {})
    r["photos"] = jloads(r.get("photos"), [])
    det = jloads(r.pop("score_details", None), {})
    if full:
        r["score_details"] = det
    else:
        r["headline"] = (det.get("deal") or {}).get("headline")
        v = det.get("valuation") or {}
        r["value_low"], r["value_typical"], r["value_high"] = v.get("low"), v.get("typical"), v.get("high")
        r["reason"] = det.get("classification_reason")
        r["flip"] = _flip(r, det)
        r.pop("description", None)
    return r


mimetypes.add_type("application/manifest+json", ".webmanifest")
mimetypes.add_type("text/javascript", ".js")

LOCAL_HOSTS = ("127.0.0.1", "::1", "localhost", "testclient")
PROXY_HEADERS = ("x-forwarded-for", "x-forwarded-host", "forwarded", "cf-connecting-ip", "tailscale-user-login")


def request_origin(request: Request) -> str:
    """'local' (this PC), 'tailscale' (Tailscale Serve, a signed-in member of your tailnet) or 'remote' (anything else).
    A proxy on this PC (Tailscale Serve, Cloudflare Tunnel) connects from 127.0.0.1, so forwarding headers decide."""
    client = request.client.host if request.client else "127.0.0.1"
    if client not in LOCAL_HOSTS:
        return "remote"
    h = request.headers
    if h.get("tailscale-user-login") and not h.get("cf-connecting-ip"):
        return "tailscale"
    if any(h.get(k) for k in PROXY_HEADERS):
        return "remote"
    return "local"


def create_api(svc) -> FastAPI:
    app = FastAPI(title="SS Deal Finder", version=__version__)
    db, settings = svc.db, svc.settings
    global _SETTINGS
    _SETTINGS = settings

    server_mode = bool(getattr(svc, "server_mode", False))
    sessions = None
    if server_mode:
        from .server import COOKIE, Sessions
        sessions = Sessions(svc.home)

    @app.middleware("http")
    async def auth(request: Request, call_next):
        # This PC needs nothing. Remote use needs the access token, except through Tailscale Serve: Tailscale has already
        # signed the person in (it adds Tailscale-User-Login, and only for members of your own tailnet; Funnel never does).
        # Server mode (always-on cloud box): everything from outside the machine needs the login cookie or the API token.
        path = request.url.path
        if path.startswith("/api"):
            where = request_origin(request)
            token = settings.secret("api_token")
            given = request.headers.get("x-api-token") or request.query_params.get("token")
            token_ok = bool(token) and given == token
            if server_mode:
                if where != "local" and path not in ("/api/login", "/api/auth") and not token_ok \
                        and not sessions.valid(request.cookies.get(COOKIE)):
                    return JSONResponse({"detail": "Please log in", "login": True}, status_code=401)
            elif where == "remote" or (where == "tailscale" and not settings.get("api.trust_tailscale", True)):
                if not token_ok:
                    return JSONResponse({"detail": "API token required for remote access"}, status_code=401)
        resp = await call_next(request)
        if request.url.path in ("/sw.js", "/manifest.webmanifest", "/", "/index.html"):
            resp.headers["Cache-Control"] = "no-cache"          # app updates show up at once, also in the installed app
        return resp

    def bad(msg: str, code: int = 400):
        raise HTTPException(status_code=code, detail=msg)

    # ------------------------------------------------------------ server-mode login
    def _client_ip(request: Request) -> str:
        fwd = request.headers.get("x-forwarded-for", "")
        return (fwd.split(",")[0].strip() if fwd else (request.client.host if request.client else "?")) or "?"

    @app.get("/api/auth")
    def auth_state(request: Request):
        if not server_mode:
            return {"server": False, "authed": True}
        from .server import COOKIE
        return {"server": True, "authed": request_origin(request) == "local" or sessions.valid(request.cookies.get(COOKIE))}

    @app.post("/api/login")
    def login(request: Request, body: dict = Body(default={})):
        if not server_mode:
            bad("Login is only used in server mode", 400)
        from .server import COOKIE, SESSION_DAYS
        ip = _client_ip(request)
        wait = sessions.locked_for(ip)
        if wait:
            bad(f"Too many wrong passwords. Try again in {wait // 60 + 1} min.", 429)
        if not sessions.attempt(ip, str(body.get("password", ""))):
            bad("Wrong password", 401)
        resp = JSONResponse({"ok": True})
        https = request.headers.get("x-forwarded-proto", request.url.scheme) == "https"
        resp.set_cookie(COOKIE, sessions.make(), max_age=SESSION_DAYS * 86400, httponly=True, secure=https, samesite="lax", path="/")
        return resp

    @app.post("/api/server/import")
    async def server_import(request: Request):
        """Replace this server's data with a pack from the PC (Settings -> Server mode). Applied at the next start."""
        if not server_mode:
            bad("Only available in server mode", 400)
        from .server import check_pack
        data = await request.body()
        if len(data) > 300 * 1024 * 1024:
            bad("That file is too big (limit 300 MB)", 413)
        why = check_pack(data)
        if why:
            bad(why, 400)
        (svc.home / "import.zip").write_bytes(data)
        (svc.home / "import.force").write_text("1")
        svc.request_shutdown()          # the platform / Docker starts it again, and the import runs first
        return {"ok": True, "restarting": True}

    @app.post("/api/logout")
    def logout():
        from .server import COOKIE
        resp = JSONResponse({"ok": True})
        resp.delete_cookie(COOKIE, path="/")
        return resp

    # ------------------------------------------------------------ status / dashboard
    @app.get("/api/status")
    def status():
        return svc.status()

    @app.get("/api/dashboard")
    def dashboard():
        now = time.time()
        day0 = time.mktime(time.localtime(now)[:3] + (0, 0, 0, 0, 0, -1))
        q = db.scalar
        best = db.query("""SELECT * FROM listings WHERE status='active' AND classification='GOOD_DEAL'
                           ORDER BY deal_score DESC LIMIT 8""")
        interesting = db.query("""SELECT * FROM listings WHERE status='active' AND classification='INTERESTING'
                                  ORDER BY first_seen DESC LIMIT 8""")
        drops = db.query("""SELECT l.*, e.at AS drop_at, json_extract(e.data,'$.from') AS from_price FROM listing_events e
                            JOIN listings l ON l.id=e.listing_id WHERE e.type='price_change'
                            AND json_extract(e.data,'$.to') < json_extract(e.data,'$.from')
                            ORDER BY e.at DESC LIMIT 8""")
        cats = db.query("""SELECT category_key, COUNT(*) AS n,
                           SUM(classification='GOOD_DEAL') AS good, SUM(classification='INTERESTING') AS interesting
                           FROM listings WHERE status='active' GROUP BY category_key ORDER BY good DESC, interesting DESC""")
        plans = db.query("SELECT * FROM roi_plans ORDER BY updated_at DESC")
        est_profit = sum(_plan_calc(p)["profit"] for p in plans if p["status"] in ("planned", "bought"))
        actual = [p for p in plans if p["status"] == "sold" and p["actual_sale"]]
        actual_profit = sum(_plan_calc(p)["actual_profit"] or 0 for p in actual)
        per_day = db.query("""SELECT strftime('%Y-%m-%d', first_seen, 'unixepoch', 'localtime') AS day, COUNT(*) AS n,
                              SUM(classification='GOOD_DEAL') AS good, SUM(classification='INTERESTING') AS interesting
                              FROM listings WHERE first_seen > ? AND first_seen >= ? GROUP BY day ORDER BY day""",
                           (now - 14 * 86400, float(settings.get("scan.warmup_done_at", 0) or 0)))
        movers = db.query("""SELECT product_key, product_name, typical, n, confidence, demand FROM market_stats
                             WHERE bucket='working' AND product_key NOT LIKE 'category:%' ORDER BY n DESC LIMIT 10""")
        return {
            "totals": {
                "active": q("SELECT COUNT(*) FROM listings WHERE status='active'", default=0),
                "all": q("SELECT COUNT(*) FROM listings", default=0),
                "new_today": q("""SELECT COUNT(*) FROM listings WHERE first_seen >= ? AND first_seen >= ?
                               AND (posted_at IS NULL OR posted_at >= ?)""", (day0, float(settings.get("scan.warmup_done_at", 0) or 0), day0 - 6 * 3600), 0),
                "good_active": q("SELECT COUNT(*) FROM listings WHERE status='active' AND classification='GOOD_DEAL'", default=0),
                "interesting_active": q("SELECT COUNT(*) FROM listings WHERE status='active' AND classification='INTERESTING'", default=0),
                "saved": q("SELECT COUNT(*) FROM listings WHERE saved=1", default=0),
                "products_tracked": q("SELECT COUNT(DISTINCT product_key) FROM market_stats WHERE product_key NOT LIKE 'category:%'", default=0),
                "price_drops_24h": q("SELECT COUNT(*) FROM listing_events WHERE type='price_change' AND at > ?", (now - 86400,), 0),
                "active_plans": sum(1 for p in plans if p["status"] in ("planned", "bought")),
                "estimated_profit": round(est_profit, 2),
                "actual_profit": round(actual_profit, 2),
            },
            "best": [_row_listing(r) for r in best],
            "interesting": [_row_listing(r) for r in interesting],
            "drops": [_row_listing(r) for r in drops],
            "categories": cats[:12],
            "saved": [_row_listing(r) for r in db.query("SELECT * FROM listings WHERE saved=1 ORDER BY last_seen DESC LIMIT 6")],
            "purchases": [dict(p, **_plan_calc(p)) for p in plans if p["status"] in ("bought", "sold")][:6],
            "per_day": per_day,
            "market": movers,
            "errors": db.query("SELECT * FROM app_errors ORDER BY id DESC LIMIT 6"),
            "status": svc.status(),
        }

    # ------------------------------------------------------------ listings
    @app.get("/api/listings")
    def listings(q: str = "", category: str = "", min_price: float | None = None, max_price: float | None = None,
                 condition: str = "", min_deal: float | None = None, min_personal: float | None = None,
                 classification: str = "", status: str = "active", saved: bool = False, sort: str = "newest",
                 page: int = 1, page_size: int = 50, product_key: str = "", flag: str = ""):
        where, params = [], []
        if status in ("active", "removed"):
            where.append("status=?")
            params.append(status)
        if q:
            for word in q.split():
                where.append("(title LIKE ? OR product_name LIKE ? OR description LIKE ?)")
                params += [f"%{word}%"] * 3
        if category:
            cats = category.split(",")
            where.append(f"category_key IN ({','.join('?' * len(cats))})")
            params += cats
        if min_price is not None:
            where.append("price >= ?")
            params.append(min_price)
        if max_price is not None:
            where.append("price <= ?")
            params.append(max_price)
        if condition:
            conds = condition.split(",")
            where.append(f"condition IN ({','.join('?' * len(conds))})")
            params += conds
        if min_deal is not None:
            where.append("deal_score >= ?")
            params.append(min_deal)
        if min_personal is not None:
            where.append("personal_score >= ?")
            params.append(min_personal)
        if classification:
            cl = classification.split(",")
            where.append(f"classification IN ({','.join('?' * len(cl))})")
            params += cl
        if saved:
            where.append("saved=1")
        if product_key:
            where.append("product_key=?")
            params.append(product_key)
        if flag:
            where.append("flags LIKE ?")
            params.append(f'%"{flag}"%')
        if sort == "drop":
            where.append("initial_price > price")
        if flag not in ("service", "buying"):       # services and "wanted" ads are not items for sale: never listed
            where.append("""COALESCE(is_buying,0)=0 AND COALESCE(flags,'') NOT LIKE '%"service"%' AND COALESCE(flags,'') NOT LIKE '%"buying"%'""")
        w = ("WHERE " + " AND ".join(where)) if where else ""
        page_size = max(1, min(page_size, 500))
        total = db.scalar(f"SELECT COUNT(*) FROM listings {w}", params, 0)
        rows = db.query(f"SELECT * FROM listings {w} ORDER BY {SORTS.get(sort, SORTS['newest'])}{SORT_TIEBREAK} LIMIT ? OFFSET ?",
                        params + [page_size, (max(page, 1) - 1) * page_size])
        return {"total": total, "page": page, "page_size": page_size, "items": [_row_listing(r) for r in rows]}

    @app.get("/api/listings/{lid}")
    def listing(lid: int):
        r = db.one("SELECT * FROM listings WHERE id=?", (lid,))
        if not r:
            bad("not found", 404)
        out = _row_listing(r, full=True)
        out["price_history"] = db.query("SELECT price, observed_at FROM price_history WHERE listing_id=? ORDER BY observed_at", (lid,))
        out["events"] = [dict(e, data=jloads(e["data"], {})) for e in
                         db.query("SELECT * FROM listing_events WHERE listing_id=? ORDER BY at DESC LIMIT 100", (lid,))]
        out["notifications"] = db.query("SELECT * FROM notifications WHERE listing_id=? ORDER BY id DESC", (lid,))
        out["feedback"] = db.query("SELECT id, kind, value, text, source, effect, created_at, active FROM feedback WHERE listing_id=? ORDER BY id DESC", (lid,))
        out["tasks"] = db.query("SELECT * FROM tasks WHERE listing_id=? ORDER BY due_at", (lid,))
        out["plans"] = db.query("SELECT * FROM roi_plans WHERE listing_id=?", (lid,))
        if r["product_key"]:
            out["market"] = db.query("SELECT * FROM market_stats WHERE product_key=?", (r["product_key"],))
            out["market_history"] = svc.engine.market.history(r["product_key"], 120)
            out["similar"] = [_row_listing(x) for x in db.query(
                "SELECT * FROM listings WHERE product_key=? AND id<>? ORDER BY last_seen DESC LIMIT 12", (r["product_key"], lid))]
        if r["repost_of"]:
            out["repost"] = db.one("SELECT id, title, price, status, first_seen FROM listings WHERE id=?", (r["repost_of"],))
        return out

    @app.post("/api/listings/{lid}/action")
    def listing_action(lid: int, body: dict = Body(...)):
        try:
            return svc.actions.apply(lid, body.get("kind", ""), body.get("value"), body.get("text"),
                                     source="ui", at=body.get("at"))
        except KeyError as e:
            bad(str(e), 404)
        except ValueError as e:
            bad(str(e))

    @app.post("/api/listings/{lid}/reply")
    def listing_reply(lid: int, body: dict = Body(...)):
        """Natural-language feedback typed in the desktop app (same parser as Discord)."""
        from .discord_bot import apply_parsed
        from .intents import parse_reply

        parsed = parse_reply(body.get("text", ""))
        msgs, clar = apply_parsed(svc.actions, lid, parsed, source="ui")
        return {"messages": msgs, "clarify": clar}

    @app.post("/api/listings/{lid}/refresh")
    async def listing_refresh(lid: int):
        r = db.one("SELECT * FROM listings WHERE id=?", (lid,))
        if not r:
            bad("not found", 404)
        res = await svc.scanner.check_listing(r)
        row = db.one("SELECT * FROM listings WHERE id=?", (lid,))
        svc.engine.apply_scores(lid, svc.engine.evaluate(row))
        return res

    @app.post("/api/listings/{lid}/correct")
    def listing_correct(lid: int, body: dict = Body(...)):
        """Fix identification (product / category / condition) when the parser got it wrong."""
        r = db.one("SELECT * FROM listings WHERE id=?", (lid,))
        if not r:
            bad("not found", 404)
        vals = {k: body[k] for k in ("product_key", "product_name", "category_key", "condition", "brand") if body.get(k)}
        if "category_key" in vals and vals["category_key"] not in CATEGORIES:
            bad("unknown category")
        if "condition" in vals and vals["condition"] not in ("new", "used", "broken", "parts", "untested"):
            bad("unknown condition")
        db.update("listings", lid, vals)
        db.insert("listing_events", {"listing_id": lid, "type": "corrected", "data": jdumps(vals), "at": time.time()})
        row = db.one("SELECT * FROM listings WHERE id=?", (lid,))
        svc.engine.apply_scores(lid, svc.engine.evaluate(row))
        return {"ok": True}

    # ------------------------------------------------------------ market
    @app.get("/api/market")
    def market(q: str = "", category: str = "", sort: str = "n", limit: int = 300):
        where, params = ["bucket='working'", "product_key NOT LIKE 'category:%'"], []
        if q:
            where.append("(product_key LIKE ? OR product_name LIKE ?)")
            params += [f"%{q}%", f"%{q}%"]
        if category:
            where.append("category_key=?")
            params.append(category)
        order = {"n": "n DESC", "name": "product_name", "price": "typical DESC", "confidence": "confidence DESC",
                 "updated": "updated_at DESC"}.get(sort, "n DESC")
        rows = db.query(f"SELECT * FROM market_stats WHERE {' AND '.join(where)} ORDER BY {order} LIMIT ?", params + [limit])
        cats = db.query("SELECT * FROM market_stats WHERE product_key LIKE 'category:%' ORDER BY n DESC")
        return {"items": rows, "categories": cats}

    # ------------------------------------------------------------ item prices (editable, export / import)
    def _price_rows(q: str = "", category: str = "", mine: bool = False, limit: int = 100000) -> list[dict]:
        where, params = ["m.bucket='working'", "m.product_key NOT LIKE 'category:%'"], []
        if q:
            where.append("(m.product_key LIKE ? OR m.product_name LIKE ?)")
            params += [f"%{q}%", f"%{q}%"]
        if category:
            where.append("m.category_key=?")
            params.append(category)
        rows = db.query(f"""SELECT m.product_key, m.product_name, m.category_key, m.low, m.typical, m.high, m.n, m.n_active,
                                   m.confidence, m.basis, m.own_typical,
                                   (SELECT value FROM market_corrections c WHERE c.product_key=m.product_key AND c.kind='override' AND c.active=1
                                    ORDER BY c.id DESC LIMIT 1) AS your_price
                            FROM market_stats m WHERE {' AND '.join(where)} ORDER BY m.n DESC, m.product_name LIMIT ?""", params + [limit])
        if mine:
            rows = [r for r in rows if r["your_price"] is not None]
        for r in rows:
            r["app_price"] = r["own_typical"] if r["own_typical"] is not None else (None if r["your_price"] is not None else r["typical"])
        return rows

    def _set_override(key: str, value: float | None) -> None:
        if value is None:
            db.execute("UPDATE market_corrections SET active=0 WHERE product_key=? AND kind='override'", (key,))
        else:
            svc.engine.market.add_correction(key, value, "override", "set in Settings > Item prices")

    @app.get("/api/prices")
    def prices(q: str = "", category: str = "", mine: bool = False, limit: int = 300):
        rows = _price_rows(q, category, mine)
        return {"total": len(rows), "items": rows[:limit]}

    @app.post("/api/prices/set")
    def prices_set(body: dict = Body(...)):
        key = (body.get("product_key") or "").strip()
        if not key or key.startswith("category:"):
            bad("missing product")
        v = body.get("price")
        try:
            v = None if v in (None, "") else float(v)
        except (TypeError, ValueError):
            bad("the price must be a number")
        if v is not None and not (0 < v < 1_000_000):
            bad("the price must be between 0 and 1,000,000")
        _set_override(key, v)
        svc.engine.market.recalc_all()
        svc.schedule_rescore()
        return {"ok": True}

    @app.get("/api/prices/export")
    def prices_export(format: str = "json", mine: bool = False):
        rows = _price_rows(mine=mine)
        stamp = time.strftime("%Y%m%d")
        if format == "csv":
            out = io.StringIO()
            w = csv.writer(out)
            w.writerow(["product_key", "product_name", "category", "app_price", "your_price", "based_on_ads"])
            for r in rows:
                w.writerow([r["product_key"], r["product_name"], r["category_key"], r["app_price"] if r["app_price"] is not None else "",
                            r["your_price"] if r["your_price"] is not None else "", r["n"]])
            return {"filename": f"ssdeal-prices-{stamp}.csv", "content": out.getvalue()}
        data = {"version": 1, "exported": stamp, "currency": "EUR",
                "items": [{"product_key": r["product_key"], "product_name": r["product_name"], "category": r["category_key"],
                           "app_price": r["app_price"], "your_price": r["your_price"], "based_on_ads": r["n"]} for r in rows]}
        return {"filename": f"ssdeal-prices-{stamp}.json", "content": json.dumps(data, ensure_ascii=False, indent=1)}

    @app.post("/api/prices/import")
    def prices_import(body: dict = Body(...)):
        """JSON ({items:[{product_key, your_price}]} or a plain list) or CSV (header with product_key and your_price / price).
        A blank price leaves that product alone. Nothing is changed unless the whole file parses."""
        text = (body.get("text") or "").strip()
        if not text:
            bad("the file is empty")
        entries: list[tuple[str, Any]] = []
        try:
            if text[:1] in "[{":
                data = json.loads(text)
                items = data.get("items", []) if isinstance(data, dict) else data
                for it in items:
                    entries.append((str(it.get("product_key") or "").strip(), it.get("your_price", it.get("price"))))
            else:
                rd = csv.DictReader(io.StringIO(text), delimiter=";" if text.split("\n", 1)[0].count(";") > text.split("\n", 1)[0].count(",") else ",")
                names = [(n or "").strip().lower() for n in (rd.fieldnames or [])]
                if "product_key" not in names or not ({"your_price", "price"} & set(names)):
                    bad("the CSV needs the columns product_key and your_price")
                for row in rd:
                    row = {(k or "").strip().lower(): v for k, v in row.items()}
                    entries.append(((row.get("product_key") or "").strip(), row.get("your_price", row.get("price"))))
        except HTTPException:
            raise
        except Exception as e:  # noqa: BLE001
            bad(f"could not read the file: {e}")
        todo, skipped = [], []
        for key, raw in entries:
            if not key or key.startswith("category:"):
                skipped.append({"product_key": key, "why": "no product key"})
                continue
            if raw in (None, ""):
                continue
            try:
                v = float(str(raw).replace("€", "").replace(",", ".").strip())
                if not (0 < v < 1_000_000):
                    raise ValueError
            except ValueError:
                skipped.append({"product_key": key, "why": f"bad price {raw!r}"})
                continue
            todo.append((key, v))
        for key, v in todo:
            _set_override(key, v)
        if todo:
            svc.engine.market.recalc_all()
            svc.schedule_rescore()
        return {"applied": len(todo), "skipped": skipped[:50], "skipped_count": len(skipped)}

    @app.get("/api/market/lookup")
    def market_lookup(text: str, category: str = "other"):
        m = identify(text, "", category)
        if not m:
            return {"match": None}
        v = svc.engine.market.value_for(m.key, "used")
        return {"match": m.to_dict(), "value": {k: v[k] for k in ("typical", "low", "high", "confidence", "n")} if v and v.get("typical") else None}

    @app.get("/api/market/product")
    def market_product(key: str):
        stats = db.query("SELECT * FROM market_stats WHERE product_key=?", (key,))
        return {"key": key, "stats": stats, "history": svc.engine.market.history(key),
                "corrections": db.query("SELECT * FROM market_corrections WHERE product_key=? ORDER BY id DESC", (key,)),
                "listings": [_row_listing(x) for x in db.query(
                    "SELECT * FROM listings WHERE product_key=? ORDER BY last_seen DESC LIMIT 100", (key,))]}

    @app.post("/api/market/correction")
    def market_correction(body: dict = Body(...)):
        try:
            cid = svc.engine.market.add_correction(body["product_key"], float(body["value"]), body.get("kind", "reference"),
                                                   body.get("note", ""))
        except (KeyError, ValueError, TypeError) as e:
            bad(f"invalid correction: {e}")
        svc.engine.market.recalc_all()
        svc.schedule_rescore()
        return {"ok": True, "id": cid}

    @app.delete("/api/market/correction/{cid}")
    def market_correction_delete(cid: int):
        db.execute("UPDATE market_corrections SET active=0 WHERE id=?", (cid,))
        svc.engine.market.recalc_all()
        svc.schedule_rescore()
        return {"ok": True}

    # ------------------------------------------------------------ watchlist
    @app.get("/api/watchlist")
    def watchlist():
        rows = db.query("SELECT * FROM watchlist ORDER BY active DESC, id DESC")
        for w in rows:
            w["matches"] = db.scalar("SELECT COUNT(*) FROM watch_matches WHERE watch_id=?", (w["id"],), 0)
            w["active_matches"] = db.scalar("""SELECT COUNT(*) FROM watch_matches m JOIN listings l ON l.id=m.listing_id
                                               WHERE m.watch_id=? AND l.status='active'""", (w["id"],), 0)
            w["best_price"] = db.scalar("""SELECT MIN(l.price) FROM watch_matches m JOIN listings l ON l.id=m.listing_id
                                           WHERE m.watch_id=? AND l.status='active'""", (w["id"],))
        return rows

    def _watch_vals(body: dict) -> dict:
        name = (body.get("name") or body.get("query") or "").strip()
        if not name:
            bad("name or search text is required")
        vals = {"name": name, "query": (body.get("query") or "").strip(), "exclude": (body.get("exclude") or "").strip(),
                "product_key": body.get("product_key") or None, "category_key": body.get("category_key") or None,
                "max_price": float(body["max_price"]) if body.get("max_price") not in (None, "") else None,
                "min_deal": float(body["min_deal"]) if body.get("min_deal") not in (None, "") else None,
                "condition": body.get("condition") or "any", "notify": int(bool(body.get("notify", True))),
                "notify_drops": int(bool(body.get("notify_drops", True))), "active": int(bool(body.get("active", True)))}
        if not vals["query"] and not vals["product_key"] and not vals["category_key"]:
            bad("give search words, a product or a category")
        return vals

    @app.post("/api/watchlist")
    def watch_create(body: dict = Body(...)):
        wid = db.insert("watchlist", {**_watch_vals(body), "created_at": time.time()})
        svc.engine.invalidate_watchlist()
        svc.schedule_rescore()
        return {"id": wid}

    @app.put("/api/watchlist/{wid}")
    def watch_update(wid: int, body: dict = Body(...)):
        db.update("watchlist", wid, _watch_vals(body))
        svc.engine.invalidate_watchlist()
        svc.schedule_rescore()
        return {"ok": True}

    @app.delete("/api/watchlist/{wid}")
    def watch_delete(wid: int):
        db.execute("DELETE FROM watchlist WHERE id=?", (wid,))
        db.execute("DELETE FROM watch_matches WHERE watch_id=?", (wid,))
        svc.engine.invalidate_watchlist()
        return {"ok": True}

    # ------------------------------------------------------------ my items (wants)
    def _want_vals(b: dict) -> dict:
        name = (b.get("name") or "").strip()
        if not name:
            bad("give the item a name, e.g. “Sony A7 III” or “iPhone 13 mini”")
        mp = b.get("max_price")
        try:
            mp = float(mp) if mp not in (None, "") else None
        except (TypeError, ValueError):
            bad("max price must be a number")
        return {"name": name[:120], "keywords": (b.get("keywords") or "").strip()[:200] or None,
                "category_key": b.get("category_key") or None, "max_price": mp, "active": 1 if b.get("active", True) else 0}

    @app.get("/api/wants")
    def wants_list():
        return db.query("SELECT * FROM wants ORDER BY active DESC, id DESC")

    @app.post("/api/wants")
    def wants_create(body: dict = Body(...)):
        wid = db.insert("wants", {**_want_vals(body), "created_at": time.time()})
        svc.engine.wants.invalidate()
        svc.schedule_rescore()
        return {"id": wid}

    @app.put("/api/wants/{wid}")
    def wants_update(wid: int, body: dict = Body(...)):
        db.update("wants", wid, _want_vals(body))
        svc.engine.wants.invalidate()
        svc.schedule_rescore()
        return {"ok": True}

    @app.delete("/api/wants/{wid}")
    def wants_delete(wid: int):
        db.execute("DELETE FROM wants WHERE id=?", (wid,))
        svc.engine.wants.invalidate()
        svc.schedule_rescore()
        return {"ok": True}

    @app.get("/api/watchlist/{wid}/matches")
    def watch_matches(wid: int):
        return [dict(_row_listing(r), matched_at=r["matched_at"], match_price=r["mprice"]) for r in db.query(
            """SELECT l.*, m.matched_at, m.price AS mprice FROM watch_matches m JOIN listings l ON l.id=m.listing_id
               WHERE m.watch_id=? ORDER BY m.matched_at DESC LIMIT 200""", (wid,))]

    # ------------------------------------------------------------ ROI planner
    @app.get("/api/roi")
    def roi_list():
        return [dict(p, **_plan_calc(p)) for p in db.query("SELECT * FROM roi_plans ORDER BY updated_at DESC")]

    @app.get("/api/roi/import/{lid}")
    def roi_import(lid: int):
        r = db.one("SELECT * FROM listings WHERE id=?", (lid,))
        if not r:
            bad("not found", 404)
        det = jloads(r["score_details"], {})
        v = det.get("valuation") or {}
        rep = (det.get("deal") or {}).get("repair") or {}
        cal = _calibration(db)
        factor = cal.get(r["category_key"], {}).get("ratio") or cal.get("_all", {}).get("ratio") or 1.0
        st = db.one("SELECT avg_days_listed FROM market_stats WHERE product_key=? AND bucket='working'", (r["product_key"],)) if r["product_key"] else None
        typical = (rep.get("working_value") or v.get("typical") or 0) * factor
        return {"listing_id": lid, "title": r["product_name"] or r["title"][:80], "product_key": r["product_key"],
                "purchase_price": r["price"] or 0, "resale_price": round(typical, 2),
                "resale_low": round((v.get("low") or typical * 0.85) * factor, 2),
                "resale_high": round((v.get("high") or typical * 1.1) * factor, 2),
                "repair_cost": rep.get("repair_cost_est") or 0,
                "expected_days": int(st["avg_days_listed"]) if st and st["avg_days_listed"] else None,
                "calibration_factor": round(factor, 3),
                "note": "Resale estimate = market estimate × your historical accuracy factor" if factor != 1.0 else
                        "Resale estimate is asking-price based; adjust if you know better"}

    ROI_FIELDS = ("listing_id", "title", "product_key", "purchase_price", "resale_price", "resale_low", "resale_high",
                  "repair_cost", "transport_cost", "accessories_cost", "platform_fees", "other_costs", "expected_days",
                  "status", "actual_purchase", "actual_repair", "actual_other", "actual_sale", "notes")

    def _roi_vals(body: dict) -> dict:
        vals = {}
        for k in ROI_FIELDS:
            if k in body:
                v = body[k]
                if k in ("title", "status", "notes", "product_key"):
                    vals[k] = v
                elif v in ("", None):
                    vals[k] = None
                else:
                    try:
                        vals[k] = float(v) if k not in ("listing_id", "expected_days") else int(float(v))
                    except (TypeError, ValueError):
                        bad(f"{k} must be a number")
                    if k not in ("listing_id",) and vals[k] is not None and vals[k] < 0:
                        bad(f"{k} cannot be negative")
        if "status" in vals and vals["status"] not in ("planned", "bought", "sold", "skipped"):
            bad("invalid status")
        return vals

    @app.post("/api/roi")
    def roi_create(body: dict = Body(...)):
        vals = _roi_vals(body)
        if not vals.get("title"):
            bad("title is required")
        now = time.time()
        pid = db.insert("roi_plans", {**vals, "created_at": now, "updated_at": now})
        return {"id": pid}

    @app.put("/api/roi/{pid}")
    def roi_update(pid: int, body: dict = Body(...)):
        old = db.one("SELECT * FROM roi_plans WHERE id=?", (pid,))
        if not old:
            bad("not found", 404)
        vals = _roi_vals(body)
        now = time.time()
        if vals.get("status") == "bought" and not old["bought_at"]:
            vals["bought_at"] = now
        if vals.get("status") == "sold" and not old["sold_at"]:
            vals["sold_at"] = now
        db.update("roi_plans", pid, {**vals, "updated_at": now})
        new = db.one("SELECT * FROM roi_plans WHERE id=?", (pid,))
        if new["status"] == "sold" and new["actual_sale"] and new["product_key"] and not (
                old["status"] == "sold" and old["actual_sale"] == new["actual_sale"]):
            svc.engine.market.add_correction(new["product_key"], new["actual_sale"], "sale",
                                             note=f"ROI plan {pid} sold", listing_id=new["listing_id"])
            svc.engine.market.recalc_all()
        return {"ok": True}

    @app.delete("/api/roi/{pid}")
    def roi_delete(pid: int):
        db.execute("DELETE FROM roi_plans WHERE id=?", (pid,))
        return {"ok": True}

    @app.get("/api/roi/accuracy")
    def roi_accuracy():
        return _calibration(db)

    # ------------------------------------------------------------ tasks / calendar
    @app.get("/api/tasks")
    def tasks(include_done: bool = False):
        w = "" if include_done else "WHERE done=0"
        rows = db.query(f"""SELECT t.*, l.title AS listing_title, l.product_name, l.price AS listing_price, l.url AS listing_url
                            FROM tasks t LEFT JOIN listings l ON l.id=t.listing_id {w.replace('done', 't.done')}
                            ORDER BY t.done, t.due_at IS NULL, t.due_at""")
        return rows

    TASK_KINDS = ("task", "reminder", "purchase", "resale", "check", "follow_up")

    def _task_vals(body: dict) -> dict:
        vals = {}
        for k in ("title", "notes", "kind", "due_at", "remind_at", "listing_id", "plan_id", "done"):
            if k in body:
                vals[k] = body[k] if body[k] != "" else None
        if "title" in vals and not (vals["title"] or "").strip():
            bad("title is required")
        if vals.get("kind") and vals["kind"] not in TASK_KINDS:
            bad("invalid kind")
        if "remind_at" in vals:
            vals["reminded"] = 0
        return vals

    @app.post("/api/tasks")
    def task_create(body: dict = Body(...)):
        vals = _task_vals(body)
        if not vals.get("title"):
            bad("title is required")
        return {"id": db.insert("tasks", {**vals, "created_at": time.time()})}

    @app.put("/api/tasks/{tid}")
    def task_update(tid: int, body: dict = Body(...)):
        db.update("tasks", tid, _task_vals(body))
        return {"ok": True}

    @app.delete("/api/tasks/{tid}")
    def task_delete(tid: int):
        db.execute("DELETE FROM tasks WHERE id=?", (tid,))
        return {"ok": True}

    @app.get("/api/calendar")
    def calendar(month: str):
        try:
            y, m = map(int, month.split("-"))
            start = time.mktime((y, m, 1, 0, 0, 0, 0, 0, -1))
            end = time.mktime((y + (m == 12), m % 12 + 1, 1, 0, 0, 0, 0, 0, -1))
        except ValueError:
            bad("month must be YYYY-MM")
        deals = db.query("""SELECT n.created_at AS at, n.level, l.id AS listing_id, l.title, l.product_name, n.price, l.deal_score
                            FROM notifications n JOIN listings l ON l.id=n.listing_id
                            WHERE n.created_at>=? AND n.created_at<? AND n.level='GOOD_DEAL' AND l.deal_score>=?
                            ORDER BY n.created_at""", (start, end, float(settings.get("notify.calendar_min_score", 85))))
        tasks_ = db.query("SELECT * FROM tasks WHERE due_at>=? AND due_at<?", (start, end))
        plans = db.query("""SELECT id, title, status, bought_at, sold_at, created_at FROM roi_plans
                            WHERE (bought_at>=? AND bought_at<?) OR (sold_at>=? AND sold_at<?)""", (start, end, start, end))
        return {"deals": deals, "tasks": tasks_, "plans": plans}

    # ------------------------------------------------------------ learning
    @app.get("/api/learning")
    def learning():
        summary = svc.engine.prefs.summary()
        fb = db.query("""SELECT f.*, l.title, l.product_name FROM feedback f LEFT JOIN listings l ON l.id=f.listing_id
                         ORDER BY f.id DESC LIMIT 300""")
        for f in fb:
            f["snapshot"] = jloads(f["snapshot"], {})
        by_level = db.query("""SELECT json_extract(snapshot,'$.classification') AS level, AVG(value) AS avg_rating, COUNT(*) AS n
                               FROM feedback WHERE kind='rating' AND active=1 GROUP BY level""")
        by_band = db.query("""SELECT CAST(json_extract(snapshot,'$.deal_score')/10 AS INT)*10 AS band, AVG(value) AS avg_rating, COUNT(*) AS n
                              FROM feedback WHERE kind='rating' AND active=1 GROUP BY band ORDER BY band""")
        ignored = db.query("""SELECT json_extract(snapshot,'$.features.cat') AS category, COUNT(*) AS n FROM feedback
                              WHERE kind IN ('ignored','not_for_me') AND active=1 GROUP BY category ORDER BY n DESC LIMIT 10""")
        liked = db.query("""SELECT json_extract(snapshot,'$.features.cat') AS category, AVG(value) AS avg_rating, COUNT(*) AS n
                            FROM feedback WHERE kind='rating' AND active=1 GROUP BY category HAVING n>0 ORDER BY avg_rating DESC LIMIT 10""")
        budget = db.query("""SELECT json_extract(snapshot,'$.features.cat') AS category,
                             AVG(COALESCE(value, json_extract(snapshot,'$.price'))) AS typical_price, COUNT(*) AS n FROM feedback
                             WHERE kind IN ('bought','would_pay','interested','saved') AND active=1 GROUP BY category""")
        return {"summary": summary, "feedback": fb, "rating_by_level": by_level, "rating_by_deal_band": by_band,
                "ignored_categories": ignored, "liked_categories": liked, "budget": budget,
                "explicit": settings.get("preferences"), "calibration": _calibration(db)}

    @app.post("/api/learning/undo/{fid}")
    def learning_undo(fid: int):
        return svc.actions.undo(fid)

    @app.post("/api/learning/redo/{fid}")
    def learning_redo(fid: int):
        r = svc.actions.redo(fid)
        svc.schedule_rescore()
        return r

    @app.post("/api/learning/reset")
    def learning_reset():
        return svc.actions.reset_learning()

    # ------------------------------------------------------------ notifications / events
    NOTIF_SORTS = {
        "newest": "n.id DESC", "oldest": "n.id ASC",
        "cheapest": "n.price IS NULL, n.price ASC, n.id DESC", "expensive": "n.price IS NULL, n.price DESC, n.id DESC",
        "profit": "l.profit_est IS NULL, l.profit_est DESC, n.id DESC", "roi": "l.roi_est IS NULL, l.roi_est DESC, n.id DESC",
        "personal": "l.personal_score IS NULL, l.personal_score DESC, n.id DESC", "unread": "n.read ASC, n.id DESC",
        "level": "n.high_roi DESC, CASE n.level WHEN 'GOOD_DEAL' THEN 0 ELSE 1 END, n.id DESC",
    }

    @app.get("/api/notifications")
    def notifications(limit: int = 100, sort: str = "newest"):
        order = NOTIF_SORTS.get(sort, NOTIF_SORTS["newest"])
        rows = db.query(f"""SELECT n.*, l.title, l.product_name, l.url, l.image_url, l.deal_score, l.personal_score, l.status, l.condition,
                                   l.score_details, l.profit_est, l.roi_est
                            FROM notifications n JOIN listings l ON l.id=n.listing_id ORDER BY {order} LIMIT ?""", (limit,))
        for r in rows:
            r["channels"] = jloads(r["channels"], [])
            r["push_errors"] = jloads(r.get("push_errors"), None)
            r["flip"] = _flip(r, jloads(r.pop("score_details", None), {}))
        return rows

    def _unread() -> int:
        return int(db.scalar("SELECT COUNT(*) FROM notifications WHERE read=0", default=0))

    @app.post("/api/notifications/read")
    def notifications_read(body: dict = Body(default={})):
        """Mark read: one notification ({"id"}), all of one listing ({"listing_id"}), or everything ({})."""
        if body.get("id"):
            db.execute("UPDATE notifications SET read=1 WHERE id=?", (int(body["id"]),))
        elif body.get("listing_id"):
            db.execute("UPDATE notifications SET read=1 WHERE listing_id=?", (int(body["listing_id"]),))
        else:
            db.execute("UPDATE notifications SET read=1 WHERE read=0")
        return {"ok": True, "unread": _unread()}

    @app.post("/api/notifications/test")
    async def notifications_test(body: dict = Body(...)):
        return await svc.notifier.test(str(body.get("channel") or ""))

    @app.post("/api/notifications/telegram/chats")
    async def telegram_chats(body: dict = Body(default={})):
        from .notify import telegram_find_chats
        token = (body.get("token") or "").strip() or settings.secret("telegram_token")
        if not token:
            bad("save the bot token first")
        try:
            return {"chats": await telegram_find_chats(token)}
        except Exception as e:  # noqa: BLE001
            bad(f"Telegram: {e}")

    @app.get("/api/events")
    def events(after: int = -1):
        """In-app feed by sequence number (the device clock does not matter). after=-1: just tell me where we are."""
        n = svc.notifier
        items = [] if after < 0 else [e for e in n.ui_events if e["seq"] > after]
        return {"seq": n.seq, "items": items, "popups": bool(settings.get("notify.in_app_popups", False))}

    # ------------------------------------------------------------ settings
    @app.get("/api/settings")
    def get_settings():
        return {"settings": settings.all(), "secrets": settings.secret_status(), "defaults": DEFAULT_SETTINGS,
                "categories": CATEGORIES, "feeds": effective_feeds(settings)}

    @app.put("/api/settings")
    def put_settings(patch: dict = Body(...)):
        try:
            for section in ("feeds",):
                if section in patch:
                    cur = settings.get(section, {}) or {}
                    cur.update(patch.pop(section))
                    settings.replace_section(section, cur)
            for section, key in (("preferences", "categories"), ("preferences", "brands"), ("preferences", "budgets"),
                                 ("filters", "categories")):
                if section in patch and key in patch[section]:
                    full = settings.get(section)
                    full[key] = patch[section].pop(key)
                    settings.replace_section(section, full)
            if patch:
                settings.update(patch)
        except ValueError as e:
            bad(str(e))
        svc.on_settings_changed()
        return {"ok": True, "settings": settings.all()}

    @app.post("/api/settings/secret")
    def put_secret(body: dict = Body(...)):
        try:
            settings.set_secret(body.get("key", ""), (body.get("value") or "").strip())
        except ValueError as e:
            bad(str(e))
        return {"ok": True, "secrets": settings.secret_status()}

    @app.post("/api/settings/reset")
    def reset_settings(body: dict = Body(default={})):
        section = body.get("section")
        if section and section not in DEFAULT_SETTINGS:
            bad("unknown section")
        warm = settings.get("scan.warmup_complete")
        settings.reset(section)
        if warm and (not section or section == "scan"):
            settings.set("scan.warmup_complete", True)
        svc.on_settings_changed()
        return {"ok": True}

    @app.get("/api/meta")
    def meta():
        return {"categories": CATEGORIES, "feeds": FEEDS, "version": __version__, "demo": svc.demo}

    # ------------------------------------------------------------ scanner control
    @app.post("/api/scanner/{action}")
    async def scanner_action(action: str, body: dict = Body(default={})):
        if action == "pause":
            svc.scanner.paused = True
        elif action == "resume":
            svc.scanner.paused = False
        elif action == "reset-cooldown":
            svc.fetcher.reset_cooldown()
        elif action == "run":
            svc.request_run(body.get("job", "new"), body.get("feed"))
        elif action == "recalc":
            svc.engine.market.recalc_all()
            svc.schedule_rescore()
        elif action == "backfill":
            svc.request_run("backfill", None)
        elif action == "redetect-rss":
            db.execute("DELETE FROM meta WHERE key LIKE 'rss:%'")
        else:
            bad("unknown action")
        return {"ok": True, "status": svc.status()}

    @app.post("/api/diagnose")
    async def diagnose(body: dict = Body(default={})):
        """Fetch one list page and one ad page and report what the parsers extracted."""
        from .feeds import FEEDS as _F
        from .parsers import looks_like_rss, parse_detail_page, parse_list_page

        feed = _F.get(body.get("feed") or "pc_parts")
        if not feed:
            bad("unknown feed")
        out: dict = {"feed": feed["key"], "url": svc.fetcher.absolute(feed["path"])}
        res = await svc.fetcher.get(feed["path"])
        out.update(status=res.status, error=res.error, robots=svc.fetcher.state.robots_status, bytes=len(res.text))
        if not res.ok:
            return out
        lp = parse_list_page(res.text, svc.fetcher.base_url)
        out["rows"] = len(lp.rows)
        out["warnings"] = lp.warnings
        out["has_next_page"] = lp.has_next
        out["with_price"] = sum(1 for r in lp.rows if r.price is not None)
        out["samples"] = [{"title": r.title[:90], "price": r.price, "price_text": r.price_text, "kind": r.price_kind,
                           "path": r.ss_id, "image": bool(r.image_url)} for r in lp.rows[:5]]
        rss = await svc.fetcher.get(feed["path"] + "rss/")
        out["rss_available"] = bool(rss.ok and looks_like_rss(rss.text))
        if lp.rows:
            ad = await svc.fetcher.get(lp.rows[0].url)
            det = parse_detail_page(ad.text, svc.fetcher.base_url, ad.status, ad.final_url)
            out["ad"] = {"status": ad.status, "removed": det.removed, "price": det.price, "attrs": det.attrs,
                         "description_chars": len(det.description), "photos": len(det.photos),
                         "posted_at": det.posted_at, "warnings": det.warnings}
        return out

    # ------------------------------------------------------------ logs / errors
    @app.get("/api/logs")
    def logs(n: int = 200, level: str = ""):
        return ring.tail(n, level or None)

    @app.get("/api/errors")
    def errors():
        return db.query("SELECT * FROM app_errors ORDER BY id DESC LIMIT 200")

    @app.get("/api/runs")
    def runs(limit: int = 100):
        return db.query("SELECT * FROM scan_runs ORDER BY id DESC LIMIT ?", (limit,))

    # ------------------------------------------------------------ export / backup
    @app.get("/api/export/{name}")
    def export(name: str):
        dataset, _, fmt = name.partition(".")
        if dataset not in EXPORTABLE or fmt not in ("csv", "json", "jsonl"):
            bad("unknown dataset or format")
        rows = db.query(EXPORTABLE[dataset])
        fname = f"ssdeal-{dataset}-{time.strftime('%Y%m%d-%H%M')}.{fmt}"
        headers = {"Content-Disposition": f'attachment; filename="{fname}"'}
        if fmt == "json":
            return Response(json.dumps(rows, ensure_ascii=False, indent=1, default=str), media_type="application/json", headers=headers)
        if fmt == "jsonl":
            return Response("\n".join(json.dumps(r, ensure_ascii=False, default=str) for r in rows) + "\n",
                            media_type="application/x-ndjson", headers=headers)
        buf = io.StringIO()
        if rows:
            w = csv.DictWriter(buf, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)
        return Response("﻿" + buf.getvalue(), media_type="text/csv; charset=utf-8", headers=headers)

    @app.get("/api/backups")
    def backups():
        d = svc.home / "backups"
        return [{"name": p.name, "size": p.stat().st_size, "created": p.stat().st_mtime}
                for p in sorted(d.glob("*.db"), key=lambda p: p.stat().st_mtime, reverse=True)]

    @app.post("/api/backups")
    def backup_create():
        return {"name": svc.backup().name}

    @app.post("/api/backups/restore")
    def backup_restore(body: dict = Body(...)):
        name = Path(body.get("name", "")).name
        src = svc.home / "backups" / name
        if not src.exists() or src.suffix != ".db":
            bad("backup not found", 404)
        svc.backup(prefix="pre-restore")
        source = sqlite3.connect(str(src))
        try:
            with db._lock:
                source.backup(db.conn)
        finally:
            source.close()
        svc.engine.market.invalidate()
        svc.engine.prefs.invalidate()
        svc.engine.invalidate_watchlist()
        return {"ok": True, "message": f"Restored {name}. A safety backup of the previous state was made first."}

    @app.get("/api/backups/download/{name}")
    def backup_download(name: str):
        p = svc.home / "backups" / Path(name).name
        if not p.exists():
            bad("not found", 404)
        return FileResponse(p, filename=p.name)

    # ------------------------------------------------------------ system
    @app.get("/api/system/autostart")
    def autostart_get():
        from . import autostart
        return autostart.status()

    @app.post("/api/system/autostart")
    def autostart_set(body: dict = Body(...)):
        from . import autostart
        try:
            r = autostart.set_enabled(bool(body.get("enabled")))
        except OSError as e:
            bad(str(e))
        settings.set("startup.autostart", bool(body.get("enabled")))
        return r

    # ------------------------------------------------------------ remote access (Tailscale)
    @app.get("/api/system/remote")
    def remote_status(request: Request):
        from . import remote
        st = remote.status(int(settings.get("api.port", 8765)))
        st["you_are"] = request_origin(request)
        st["you"] = request.headers.get("tailscale-user-login") or ""
        return st

    @app.post("/api/system/remote/serve")
    def remote_serve(request: Request, body: dict = Body(default={})):
        from . import remote
        if request_origin(request) != "local":
            bad("Set this up on the PC itself", 403)
        return remote.serve(int(settings.get("api.port", 8765)), on=bool(body.get("on", True)))

    @app.post("/api/system/shutdown")
    def shutdown(request: Request):
        if request_origin(request) != "local":
            bad("Quit is only allowed from the computer running the service", 403)
        svc.request_shutdown()
        return {"ok": True}

    @app.post("/api/system/recheck")
    async def recheck():
        import asyncio
        return await asyncio.to_thread(svc.recheck_everything)

    @app.post("/api/system/restart")
    def restart():
        """Start a fresh copy of the service (it waits for this one to release the port), then stop this one."""
        import os
        if server_mode or os.environ.get("SSDEAL_MANAGED"):      # Docker / the hub's supervisor starts it again
            svc.request_shutdown()
            return {"ok": True}
        import os
        import subprocess
        import sys
        from pathlib import Path
        exe = Path(sys.executable)
        pyw = exe.with_name("pythonw.exe")
        interp = str(pyw if (sys.platform == "win32" and pyw.exists()) else exe)
        script = str(Path(__file__).resolve().parent.parent / "run_service.pyw")
        env = dict(os.environ, SSDEAL_WAIT_PORT="1")
        kw: dict = {"cwd": str(Path(script).parent), "stdin": subprocess.DEVNULL, "stdout": subprocess.DEVNULL,
                    "stderr": subprocess.DEVNULL, "env": env}
        if sys.platform == "win32":
            kw["creationflags"] = 0x00000008 | 0x08000000 | 0x00000200
        else:
            kw["start_new_session"] = True
        subprocess.Popen([interp, script] + (["--demo"] if svc.demo else []), **kw)
        svc.request_shutdown()
        return {"ok": True}

    # ------------------------------------------------------------ static UI
    if WEB_DIR.exists():
        app.mount("/", StaticFiles(directory=str(WEB_DIR), html=True), name="web")

    return app


def _plan_calc(p: dict) -> dict:
    g = lambda k: float(p.get(k) or 0)  # noqa: E731
    costs = g("repair_cost") + g("transport_cost") + g("accessories_cost") + g("other_costs")
    invest = g("purchase_price") + costs
    fees_pct = g("platform_fees")
    # platform_fees: values <= 30 are treated as % of the sale price, larger as a fixed €
    fee = lambda sale: sale * fees_pct / 100 if fees_pct <= 30 else fees_pct  # noqa: E731
    resale = g("resale_price")
    low = float(p.get("resale_low") or resale * 0.85)
    high = float(p.get("resale_high") or resale * 1.1)
    profit = resale - fee(resale) - invest
    roi = profit / invest * 100 if invest else 0.0
    if fees_pct <= 30:
        breakeven = invest / (1 - fees_pct / 100) if fees_pct < 100 else None
    else:
        breakeven = invest + fees_pct
    worst = low * 0.9 - fee(low * 0.9) - invest - g("repair_cost") * 0.5
    actual_profit = None
    if p.get("actual_sale"):
        a_inv = float(p.get("actual_purchase") or p.get("purchase_price") or 0) + float(
            p.get("actual_repair") if p.get("actual_repair") is not None else p.get("repair_cost") or 0) + float(
            p.get("actual_other") if p.get("actual_other") is not None else (g("transport_cost") + g("accessories_cost") + g("other_costs")))
        actual_profit = float(p["actual_sale"]) - fee(float(p["actual_sale"])) - a_inv
    return {"investment": round(invest, 2), "profit": round(profit, 2), "roi": round(roi, 1),
            "breakeven": round(breakeven, 2) if breakeven else None,
            "best_profit": round(high - fee(high) - invest, 2), "realistic_profit": round(profit, 2),
            "worst_profit": round(worst, 2), "actual_profit": round(actual_profit, 2) if actual_profit is not None else None,
            "prediction_error": round(actual_profit - profit, 2) if actual_profit is not None else None}


def _calibration(db) -> dict:
    """How actual sale prices compared with predicted resale prices (per category)."""
    rows = db.query("""SELECT p.resale_price, p.actual_sale, l.category_key FROM roi_plans p
                       LEFT JOIN listings l ON l.id=p.listing_id WHERE p.status='sold' AND p.actual_sale>0 AND p.resale_price>0""")
    out: dict[str, Any] = {}
    groups: dict[str, list[float]] = {}
    for r in rows:
        ratio = r["actual_sale"] / r["resale_price"]
        groups.setdefault(r["category_key"] or "other", []).append(ratio)
        groups.setdefault("_all", []).append(ratio)
    for k, v in groups.items():
        v.sort()
        med = v[len(v) // 2]
        # shrink towards 1.0 until there is enough evidence
        shrink = len(v) / (len(v) + 3)
        out[k] = {"ratio": round(1 + (med - 1) * shrink, 3), "raw_median": round(med, 3), "n": len(v)}
    return out
