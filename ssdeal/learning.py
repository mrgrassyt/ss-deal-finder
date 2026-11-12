"""Personal preference learning -> Personal Value Score.

Design
* The model is a pure function of (active feedback events + explicit preferences).
  That makes every decision reviewable, and undo/reset trivial: deactivate the
  event and recompute.
* Each feedback event stores a snapshot of the listing's features at the time.
* Features are shrunk towards neutral (Bayesian prior) so one rating cannot
  swing the model, and old feedback slowly decays.
* Nothing here ever changes market prices (see market.py).
"""
from __future__ import annotations

import math
import time
from collections import defaultdict

from .db import Database, jloads
from .textutil import norm

# signal in [-1, 1] and strength for each feedback kind
SIGNALS = {
    "interested": (0.6, 1.0),
    "saved": (0.5, 0.8),
    "bought": (1.0, 1.5),
    "ignored": (-0.4, 0.6),
    "not_for_me": (-0.7, 1.0),
    "good_deal": (0.3, 0.5),
    "too_expensive": (0.0, 0.0),   # price feedback, not dislike of the product
    "overpriced": (0.0, 0.0),
    "would_pay": (0.2, 0.4),
    "remind": (0.4, 0.5),
}
FEATURE_WEIGHTS = {"product": 1.2, "brand": 0.8, "cat": 1.0, "cond": 0.5, "band": 0.5, "flag": 0.4}
PRIOR = 3.0
HALF_LIFE = 120 * 86400


def price_band(price: float | None) -> str:
    if not price or price <= 0:
        return "free"
    for lim, name in ((25, "<25"), (75, "25-75"), (150, "75-150"), (300, "150-300"), (600, "300-600"),
                      (1200, "600-1200")):
        if price < lim:
            return name
    return "1200+"


def features_of(listing: dict) -> dict[str, str]:
    f = {}
    if listing.get("product_key"):
        f["product"] = listing["product_key"]
    if listing.get("brand"):
        f["brand"] = listing["brand"]
    if listing.get("category_key"):
        f["cat"] = listing["category_key"]
    if listing.get("condition"):
        f["cond"] = listing["condition"]
    f["band"] = price_band(listing.get("price"))
    flags = listing.get("flags") or []
    for fl in ("bundle", "collection"):
        if fl in flags:
            f[f"flag:{fl}"] = fl
    return f


def _fkey(ftype: str, value: str) -> str:
    return f"{ftype.split(':')[0]}={value}"


class PreferenceModel:
    def __init__(self, db: Database, settings):
        self.db = db
        self.settings = settings
        self._stats: dict[str, list[float]] = {}
        self._price_targets: dict[str, float] = {}
        self._version = -1
        self._built_at = 0.0

    def invalidate(self) -> None:
        self._version = -1

    def _current_version(self) -> int:
        return int(self.db.scalar("SELECT COALESCE(MAX(id),0) + COUNT(*)*100000 + SUM(active) FROM feedback", default=0))

    def _ensure(self) -> None:
        v = self._current_version()
        if v != self._version or time.time() - self._built_at > 3600:
            self._stats, self._price_targets = self.build()
            self._version = v
            self._built_at = time.time()

    def build(self, exclude_id: int | None = None) -> tuple[dict, dict]:
        rows = self.db.query("SELECT * FROM feedback WHERE active=1 ORDER BY id")
        stats: dict[str, list[float]] = defaultdict(lambda: [0.0, 0.0])  # weighted sum, weight
        targets: dict[str, list[float]] = defaultdict(list)
        now = time.time()
        for r in rows:
            if exclude_id is not None and r["id"] == exclude_id:
                continue
            snap = jloads(r["snapshot"], {})
            feats = snap.get("features", {})
            kind = r["kind"]
            decay = 0.5 ** ((now - r["created_at"]) / HALF_LIFE)
            if kind == "rating" and r["value"] is not None:
                sig, strength = (float(r["value"]) - 5.5) / 4.5, 1.2
            elif kind == "brand_dislike":
                b = feats.get("brand") or r["text"]
                if b:
                    s = stats[_fkey("brand", b)]
                    s[0] += -1.0 * 3 * decay
                    s[1] += 3 * decay
                continue
            elif kind == "brand_like":
                b = feats.get("brand") or r["text"]
                if b:
                    s = stats[_fkey("brand", b)]
                    s[0] += 1.0 * 3 * decay
                    s[1] += 3 * decay
                continue
            else:
                sig, strength = SIGNALS.get(kind, (0.0, 0.0))
            if kind in ("would_pay", "too_expensive", "overpriced", "bought") and feats.get("product"):
                val = r["value"] if kind in ("would_pay", "bought") else None
                if val:
                    targets[feats["product"]].append(float(val))
                elif kind in ("too_expensive", "overpriced") and snap.get("price"):
                    targets[feats["product"]].append(float(snap["price"]) * 0.85)
            if strength <= 0:
                continue
            for ftype, value in feats.items():
                if ftype == "band" and kind in ("ignored", "not_for_me"):
                    continue  # ignoring an item is rarely about its price band
                s = stats[_fkey(ftype, value)]
                s[0] += sig * strength * decay
                s[1] += strength * decay
        return dict(stats), {k: sorted(v)[len(v) // 2] for k, v in targets.items()}

    # ---------------------------------------------------------------- scoring
    def feature_value(self, fkey: str) -> float:
        self._ensure()
        s = self._stats.get(fkey)
        if not s:
            return 0.0
        return s[0] / (s[1] + PRIOR)

    def score(self, listing: dict, watch_hits: list[dict] | None = None) -> dict:
        self._ensure()
        prefs = self.settings.get("preferences", {})
        weight = float(self.settings.get("learning.personal_weight", 1.0)) if self.settings.get(
            "learning.enabled", True) else 0.0
        feats = features_of(listing)
        parts: list[dict] = []
        z = 0.0

        def add(value: float, label: str, kind: str) -> None:
            nonlocal z
            if abs(value) < 0.01:
                return
            z += value
            parts.append({"value": round(value, 3), "text": label, "kind": kind})

        for ftype, value in feats.items():
            fv = self.feature_value(_fkey(ftype, value))
            add(fv * FEATURE_WEIGHTS.get(ftype.split(":")[0], 0.4) * weight,
                f"learned {ftype.split(':')[0]} '{value}'", "learned")
        cat = listing.get("category_key")
        cp = (prefs.get("categories") or {}).get(cat)
        if cp:
            add(float(cp) * 1.5, f"your interest in {cat}", "explicit")
        bp = (prefs.get("brands") or {}).get(listing.get("brand") or "")
        if bp:
            add(float(bp) * 1.2, f"your brand preference: {listing.get('brand')}", "explicit")
        cpref = (prefs.get("conditions") or {}).get(listing.get("condition") or "")
        if cpref:
            add(float(cpref), f"condition preference: {listing.get('condition')}", "explicit")
        text = norm(f"{listing.get('title', '')} {listing.get('description', '') or ''}")
        for kw in prefs.get("keywords_like") or []:
            if kw and norm(kw) in text:
                add(0.5, f"liked keyword '{kw}'", "explicit")
        for kw in prefs.get("keywords_dislike") or []:
            if kw and norm(kw) in text:
                add(-0.6, f"disliked keyword '{kw}'", "explicit")
        price = listing.get("price")
        budget = (prefs.get("budgets") or {}).get(cat) or prefs.get("budget_default") or 0
        if budget and price and price > budget:
            over = min(1.5, (price - budget) / budget)
            add(-0.4 - over, f"above your budget (€{budget:.0f})", "budget")
        target = self._price_targets.get(listing.get("product_key") or "")
        if target and price:
            if price <= target:
                add(0.5, f"at or below the price you said you'd pay (€{target:.0f})", "learned")
            else:
                add(-min(1.0, (price - target) / target * 1.5), f"above the price you'd pay (€{target:.0f})", "learned")
        for w in watch_hits or []:
            add(0.9, f"matches watchlist '{w['name']}'", "watchlist")
            if w.get("max_price") and price and price <= w["max_price"]:
                add(0.4, f"within watchlist budget (€{w['max_price']:.0f})", "watchlist")
        score = 50 + 50 * math.tanh(z * 0.9)
        parts.sort(key=lambda p: abs(p["value"]), reverse=True)
        return {"score": round(score, 1), "parts": parts[:8], "z": round(z, 3)}

    # ---------------------------------------------------------------- explanation
    def describe_effect(self, before: dict, after: dict, features: dict) -> str:
        changes = []
        for ftype, value in features.items():
            k = _fkey(ftype, value)
            b = before.get(k, [0, 0])
            a = after.get(k, [0, 0])
            bv = b[0] / (b[1] + PRIOR)
            av = a[0] / (a[1] + PRIOR)
            if abs(av - bv) >= 0.005:
                changes.append(f"{ftype.split(':')[0]} '{value}': {bv:+.2f} → {av:+.2f}")
        return "; ".join(changes) if changes else "no preference change (price/market feedback only)"

    def summary(self) -> dict:
        self._ensure()
        items = []
        for k, (s, w) in self._stats.items():
            ftype, _, value = k.partition("=")
            items.append({"type": ftype, "value": value, "preference": round(s / (w + PRIOR), 3),
                          "evidence": round(w, 2)})
        items.sort(key=lambda x: x["preference"], reverse=True)
        by_type: dict[str, list] = defaultdict(list)
        for it in items:
            by_type[it["type"]].append(it)
        return {"features": dict(by_type), "price_targets": self._price_targets}
