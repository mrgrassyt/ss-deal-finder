"""Objective market-price database built from observed SS.lv asking prices.

Important properties
* Values are ASKING-PRICE based unless confirmed sales exist (basis field says so).
* Personal feedback (ratings, likes, brand dislikes) never touches this module.
  Only explicit market corrections and confirmed sale prices do, and each of
  them counts as a limited number of observations - one bad input cannot
  overwrite the evidence.
* Removed listings stay in the evidence set (with recency weighting).
"""
from __future__ import annotations

import math
import statistics
import time
from collections import defaultdict

from .db import Database, jloads
from .logs import get_logger

log = get_logger("market")

HALF_LIFE_DAYS = 45.0
WINDOW_DAYS = 240
EXCLUDE_FLAGS = {"buying", "service", "exchange", "collection"}
BROKEN_CONDS = {"broken", "parts"}


def wquantile(values: list[float], weights: list[float], q: float) -> float:
    """Weighted quantile with linear interpolation between weighted midpoints."""
    pairs = sorted(zip(values, weights))
    total = sum(w for _, w in pairs)
    if total <= 0:
        return statistics.median(values)
    pos, acc = [], 0.0
    for v, w in pairs:
        pos.append((acc + w / 2) / total)
        acc += w
    if q <= pos[0]:
        return pairs[0][0]
    for i in range(1, len(pairs)):
        if q <= pos[i]:
            span = pos[i] - pos[i - 1]
            f = (q - pos[i - 1]) / span if span else 0
            return pairs[i - 1][0] + f * (pairs[i][0] - pairs[i - 1][0])
    return pairs[-1][0]


def robust_filter(obs: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """Drop outliers on log scale using median absolute deviation."""
    if len(obs) < 4:
        return obs
    logs = [math.log(max(p, 1.0)) for p, _ in obs]
    med = statistics.median(logs)
    mad = statistics.median(abs(x - med) for x in logs) or 0.1
    keep = []
    for (p, w), lx in zip(obs, logs):
        z = abs(lx - med) / (1.4826 * mad)
        if z <= 3.0 and 0.15 * math.exp(med) <= p <= 4 * math.exp(med):
            keep.append((p, w))
    return keep if len(keep) >= 3 else obs


class Market:
    def __init__(self, db: Database, settings):
        self.db = db
        self.settings = settings
        self._cache: dict[tuple[str, str], dict] = {}
        self._cache_at = 0.0

    # ---------------------------------------------------------------- read
    def stats(self, product_key: str | None, bucket: str = "working") -> dict | None:
        if not product_key:
            return None
        if time.time() - self._cache_at > 60:
            self._load_cache()
        return self._cache.get((product_key, bucket))

    def _load_cache(self) -> None:
        self._cache = {(r["product_key"], r["bucket"]): r for r in self.db.query("SELECT * FROM market_stats")}
        self._cache_at = time.time()

    def invalidate(self) -> None:
        self._cache_at = 0.0

    def value_for(self, product_key: str | None, condition: str) -> dict | None:
        """Best available value estimate for a product in a given condition."""
        if not product_key:
            return None
        min_obs = int(self.settings.get("learning.min_observations", 3))
        want = {"new": "new", "used": "used", "broken": "broken", "parts": "broken"}.get(condition, "working")
        st = self.stats(product_key, want)
        factor, note = 1.0, ""
        if not st or (st["n"] < min_obs and st["basis"] != "manual"):
            st = self.stats(product_key, "working")
            if st and condition in BROKEN_CONDS:
                factor, note = 0.0, "no broken-unit comparables"
            elif st and condition == "untested":
                factor, note = 0.65, "untested: valued at 65% of working price"
            elif st and condition == "new":
                factor, note = 1.12, "new: +12% over mixed-condition median"
        elif condition == "untested":
            factor, note = 0.65, "untested: valued at 65% of working price"
        if not st or (st["n"] < min_obs and st["basis"] != "manual"):
            return None
        if factor == 0.0:
            return {"stats": st, "typical": None, "low": None, "high": None, "note": note, "confidence": st["confidence"]}
        return {
            "stats": st,
            "typical": st["typical"] * factor,
            "low": st["low"] * factor,
            "high": st["high"] * factor,
            "note": note,
            "confidence": st["confidence"] * (0.8 if factor != 1.0 else 1.0),
            "basis": st["basis"],
            "n": st["n"],
        }

    def category_stats(self, category: str) -> dict | None:
        return self.stats(f"category:{category}", "working")

    # ---------------------------------------------------------------- compute
    def recalc_all(self) -> dict:
        t0 = time.time()
        cutoff = t0 - WINDOW_DAYS * 86400
        rows = self.db.query(
            """SELECT id, product_key, product_name, category_key, price, condition, flags, status, first_seen,
                      last_seen, removed_at, fingerprint, score_details, is_buying
               FROM listings WHERE price IS NOT NULL AND price > 0 AND last_seen >= ?""", (cutoff,))
        corrections = self.db.query("SELECT * FROM market_corrections WHERE active=1")
        lw = self.settings.get("learning", {})
        corr_w = float(lw.get("market_correction_weight", 3.0))
        sale_w = float(lw.get("confirmed_sale_weight", 4.0))

        by_product: dict[str, list[dict]] = defaultdict(list)
        by_category: dict[str, list[dict]] = defaultdict(list)
        names: dict[str, tuple[str, str]] = {}
        reposted = {r["repost_of"] for r in self.db.query(
            "SELECT DISTINCT repost_of FROM listings WHERE repost_of IS NOT NULL")}
        kept: list[dict] = []
        for r in rows:
            flags = set(jloads(r["flags"], []))
            if r["is_buying"] or flags & {"buying", "service", "exchange"}:
                continue
            if r["id"] in reposted:
                continue  # an older copy of a reposted ad: only the newest copy counts
            kept.append(r)
        for r in kept:
            flags = set(jloads(r["flags"], []))
            if r["product_key"]:
                by_product[r["product_key"]].append({**r, "_flags": flags})
                names.setdefault(r["product_key"], (r["product_name"] or r["product_key"], r["category_key"]))
            if r["category_key"] and "collection" not in flags and r["condition"] not in BROKEN_CONDS:
                by_category[r["category_key"]].append({**r, "_flags": flags})

        corr_by_product: dict[str, list[dict]] = defaultdict(list)
        for c in corrections:
            corr_by_product[c["product_key"]].append(c)
            if c["product_key"] not in names:
                names[c["product_key"]] = (c["product_key"], c["product_key"].split(":")[0])

        out_rows = []
        today = time.strftime("%Y-%m-%d")
        hist_rows = []
        for key in set(by_product) | set(corr_by_product):
            items = by_product.get(key, [])
            name, cat = names.get(key, (key, None))
            corr = corr_by_product.get(key, [])
            for bucket in ("working", "used", "new", "broken"):
                st = self._bucket_stats(items, bucket, corr if bucket in ("working", "used") else [],
                                        corr_w, sale_w, t0)
                if not st:
                    continue
                st.update(product_key=key, bucket=bucket, product_name=name, category_key=cat, updated_at=t0)
                out_rows.append(st)
                if bucket == "working":
                    hist_rows.append((key, today, st["typical"], st["median"], st["low"], st["high"], st["n"]))
        for cat, items in by_category.items():
            st = self._bucket_stats(items, "category", [], corr_w, sale_w, t0)
            if st:
                st.update(product_key=f"category:{cat}", bucket="working", product_name=f"All {cat}",
                          category_key=cat, updated_at=t0)
                out_rows.append(st)

        cols = ["product_key", "bucket", "product_name", "category_key", "low", "typical", "high", "median", "mean",
                "n", "n_active", "n_sales", "n_corrections", "confidence", "basis", "demand", "avg_days_listed",
                "bundle_premium", "updated_at", "own_typical"]
        with self.db.transaction() as conn:
            conn.execute("DELETE FROM market_stats")
            conn.executemany(
                f"INSERT INTO market_stats ({','.join(cols)}) VALUES ({','.join('?' * len(cols))})",
                [[r.get(c) for c in cols] for r in out_rows])
            conn.executemany(
                """INSERT INTO market_history(product_key, day, typical, median, low, high, n) VALUES(?,?,?,?,?,?,?)
                   ON CONFLICT(product_key, day) DO UPDATE SET typical=excluded.typical, median=excluded.median,
                   low=excluded.low, high=excluded.high, n=excluded.n""", hist_rows)
        self.invalidate()
        elapsed = time.time() - t0
        log.event("market.recalc", products=len({r["product_key"] for r in out_rows}), rows=len(out_rows),
                  observations=len(rows), seconds=round(elapsed, 3))
        return {"products": len({r["product_key"] for r in out_rows}), "seconds": elapsed}

    def _bucket_stats(self, items: list[dict], bucket: str, corrections: list[dict], corr_w: float,
                      sale_w: float, now: float) -> dict | None:
        def in_bucket(r: dict) -> bool:
            c = r["condition"]
            if bucket in ("working", "category"):
                return c in ("new", "used")
            if bucket == "used":
                return c == "used"
            if bucket == "new":
                return c == "new"
            if bucket == "broken":
                return c in BROKEN_CONDS
            return False

        sel = [r for r in items if in_bucket(r)]
        singles = [r for r in sel if "bundle" not in r["_flags"] and "collection" not in r["_flags"]]
        bundles = [r for r in sel if "bundle" in r["_flags"]]
        base = singles if len(singles) >= 2 or not bundles else sel
        obs: list[tuple[float, float]] = []
        for r in base:
            age_days = (now - (r["last_seen"] or now)) / 86400
            w = 0.5 ** (age_days / HALF_LIFE_DAYS)
            ident = jloads(r.get("score_details"), {}).get("identification_confidence", 0.7)
            obs.append((float(r["price"]), w * max(0.3, ident)))
        override = None
        n_sales = n_corr = 0
        for c in corrections:
            if c["kind"] == "override":
                override = c
            elif c["kind"] == "sale":
                obs.append((float(c["value"]), sale_w))
                n_sales += 1
            else:
                obs.append((float(c["value"]), corr_w))
                n_corr += 1
        if not obs and not override:
            return None
        obs = robust_filter(obs) if obs else obs
        if obs:
            vals = [p for p, _ in obs]
            wts = [w for _, w in obs]
            low, typ, high = (wquantile(vals, wts, q) for q in (0.25, 0.5, 0.75))
            median = statistics.median(vals)
            mean = statistics.fmean(vals)
            n_eff = (sum(wts) ** 2) / sum(w * w for w in wts) if sum(wts) else 0
            spread = (high - low) / typ if typ else 1.0
            conf = (1 - math.exp(-n_eff / 6.0)) * max(0.35, min(1.0, 1.25 - spread))
        else:
            low = typ = high = median = mean = float(override["value"])
            conf, n_eff = 0.0, 0
        basis = "asking_prices" + ("+sales" if n_sales else "") + ("+corrections" if n_corr else "")
        own_typ = typ if obs else None          # what the app itself believes, before a user's price replaces it
        if override:
            v = float(override["value"])
            low, typ, high = v * 0.88, v, v * 1.12
            conf = max(conf, 0.85)
            basis = "manual"
        removed = [r for r in sel if r["status"] == "removed" and r["removed_at"]]
        avg_days = None
        demand = None
        if removed:
            days = [max(0.1, (r["removed_at"] - r["first_seen"]) / 86400) for r in removed]
            avg_days = statistics.median(days)
            demand = max(0.0, min(1.0, 1.0 - avg_days / 30.0))
        bundle_premium = None
        if bundles and singles and bucket == "working":
            bundle_premium = statistics.median(r["price"] for r in bundles) / max(1.0, statistics.median(
                r["price"] for r in singles)) - 1.0
        return {
            "low": round(low, 2), "typical": round(typ, 2), "high": round(high, 2),
            "median": round(median, 2), "mean": round(mean, 2),
            "n": len(base) + n_sales + n_corr, "n_active": sum(1 for r in base if r["status"] == "active"),
            "n_sales": n_sales, "n_corrections": n_corr, "own_typical": round(own_typ, 2) if own_typ else None,
            "confidence": round(conf, 3), "basis": basis, "demand": demand, "avg_days_listed": avg_days,
            "bundle_premium": bundle_premium,
        }

    # ---------------------------------------------------------------- corrections
    def add_correction(self, product_key: str, value: float, kind: str = "reference", note: str = "",
                       listing_id: int | None = None) -> int:
        if kind not in ("reference", "sale", "override"):
            raise ValueError("kind must be reference, sale or override")
        if not (0 < value < 1_000_000):
            raise ValueError("value out of range")
        if kind == "override":
            self.db.execute("UPDATE market_corrections SET active=0 WHERE product_key=? AND kind='override'",
                            (product_key,))
        cid = self.db.insert("market_corrections", {
            "product_key": product_key, "value": value, "kind": kind, "note": note,
            "listing_id": listing_id, "created_at": time.time(), "active": 1})
        log.event("market.correction", product_key=product_key, value=value, kind=kind)
        return cid

    def history(self, product_key: str, days: int = 180) -> list[dict]:
        return self.db.query(
            "SELECT * FROM market_history WHERE product_key=? ORDER BY day DESC LIMIT ?", (product_key, days))[::-1]
