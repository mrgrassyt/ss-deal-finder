"""User actions shared by the desktop UI and the Discord bot.

Every action is recorded as a feedback row (with a feature snapshot and a
human-readable description of its learning effect) so it can be reviewed,
corrected or undone later.
"""
from __future__ import annotations

import time

from .db import Database, jdumps, jloads
from .engine import Engine
from .learning import features_of
from .logs import get_logger

log = get_logger("actions")

STATE_FOR = {"interested": "interested", "ignored": "ignored", "too_expensive": "too_expensive",
             "bought": "bought", "not_for_me": "ignored", "saved": None}
VALID_KINDS = {"rating", "interested", "saved", "unsaved", "ignored", "too_expensive", "overpriced", "bought",
               "would_pay", "not_for_me", "good_deal", "brand_dislike", "brand_like", "remind", "market_value",
               "sold"}


class Actions:
    def __init__(self, db: Database, engine: Engine):
        self.db = db
        self.engine = engine

    def _listing(self, listing_id: int) -> dict:
        row = self.db.one("SELECT * FROM listings WHERE id=?", (listing_id,))
        if not row:
            raise KeyError(f"listing {listing_id} not found")
        row["flags"] = jloads(row["flags"], [])
        return row

    def apply(self, listing_id: int, kind: str, value: float | None = None, text: str | None = None,
              source: str = "ui", at: float | None = None) -> dict:
        if kind not in VALID_KINDS:
            raise ValueError(f"unknown action {kind}")
        row = self._listing(listing_id)
        msg = ""
        if kind == "rating":
            if value is None or not (1 <= float(value) <= 10):
                raise ValueError("rating must be 1-10")
            value = int(value)
        if kind in ("would_pay", "market_value", "sold") and (value is None or value <= 0):
            raise ValueError("a positive price is required")

        if kind == "market_value":
            if not row["product_key"]:
                raise ValueError("this listing has no identified product, so the market value can't be corrected")
            self.engine.market.add_correction(row["product_key"], float(value), "reference",
                                              note=f"from listing {listing_id} via {source}", listing_id=listing_id)
            self.engine.market.recalc_all()
            msg = (f"Recorded €{value:.0f} as a market reference for {row['product_name']} "
                   f"(counts as a few observations, not an override).")
            fid = self._record(row, "market_value", value, text, source, effect="market reference added (objective)")
            self._rescore(listing_id)
            return {"ok": True, "message": msg, "feedback_id": fid}

        if kind == "remind":
            when = at or time.time() + 86400
            self.db.insert("tasks", {"title": f"Check: {row['product_name'] or row['title'][:60]}", "kind": "check",
                                     "listing_id": listing_id, "due_at": when, "remind_at": when,
                                     "notes": text or "", "created_at": time.time()})
            fid = self._record(row, "remind", None, text, source)
            return {"ok": True, "message": f"Reminder set for {time.strftime('%a %d %b %H:%M', time.localtime(when))}.",
                    "feedback_id": fid}

        if kind == "brand_dislike" or kind == "brand_like":
            if not row["brand"]:
                return {"ok": False, "clarify": True,
                        "message": "I couldn't identify the brand of this listing. Which brand do you mean?"}
            prefs = self.engine.settings.get("preferences", {})
            brands = prefs.get("brands") or {}
            brands[row["brand"]] = -1.0 if kind == "brand_dislike" else 0.6
            self.engine.settings.update({"preferences": {"brands": brands}})
            msg = f"{'Lowering' if kind == 'brand_dislike' else 'Raising'} Personal Value for {row['brand']}. Market prices are not affected."

        if kind == "rating":
            # a changed rating supersedes the previous one instead of stacking
            prev = self.db.query("SELECT id FROM feedback WHERE listing_id=? AND kind='rating' AND active=1", (listing_id,))
        else:
            prev = []

        changes: dict = {}
        if kind == "saved":
            changes["saved"] = 1
        elif kind == "unsaved":
            changes["saved"] = 0
        state = STATE_FOR.get(kind)
        if state:
            changes["user_state"] = state
        if changes:
            self.db.update("listings", listing_id, changes)

        if kind == "bought":
            plan = self.db.one("SELECT id FROM roi_plans WHERE listing_id=? ORDER BY id DESC LIMIT 1", (listing_id,))
            vals = {"status": "bought", "bought_at": time.time(), "updated_at": time.time()}
            if value:
                vals["actual_purchase"] = float(value)
            if plan:
                self.db.update("roi_plans", plan["id"], vals)
            else:
                est = jloads(self.db.scalar("SELECT score_details FROM listings WHERE id=?", (listing_id,)), {})
                v = (est.get("valuation") or {})
                self.db.insert("roi_plans", {
                    "listing_id": listing_id, "title": row["product_name"] or row["title"][:80],
                    "product_key": row["product_key"], "purchase_price": value or row["price"] or 0,
                    "resale_price": v.get("typical") or 0, "resale_low": v.get("low"), "resale_high": v.get("high"),
                    "created_at": time.time(), **vals})
            msg = msg or (f"Marked as bought{f' for €{value:.0f}' if value else ''}. A purchase record was added to the ROI planner.")

        if kind == "sold":
            plan = self.db.one("SELECT * FROM roi_plans WHERE listing_id=? ORDER BY id DESC LIMIT 1", (listing_id,))
            if plan:
                self.db.update("roi_plans", plan["id"], {"status": "sold", "actual_sale": float(value),
                                                         "sold_at": time.time(), "updated_at": time.time()})
            if row["product_key"]:
                self.engine.market.add_correction(row["product_key"], float(value), "sale",
                                                  note="confirmed sale", listing_id=listing_id)
                self.engine.market.recalc_all()
            msg = f"Recorded sale at €{value:.0f} (confirmed sale price feeds the market database)."

        before, _ = self.engine.prefs.build()
        fid = self._record(row, kind, value, text, source)
        for p in prev:
            self.db.update("feedback", p["id"], {"active": 0, "superseded_by": fid})
        self.engine.prefs.invalidate()
        self.engine.wants.invalidate()
        after, _ = self.engine.prefs.build()
        effect = self.engine.prefs.describe_effect(before, after, features_of(row))
        self.db.update("feedback", fid, {"effect": effect})
        self._rescore(listing_id)
        if kind == "rating":
            self.db.execute("UPDATE notifications SET rating=? WHERE id=(SELECT MAX(id) FROM notifications WHERE listing_id=?)",
                            (value, listing_id))
        log.event("feedback", kind=kind, listing_id=listing_id, value=value, source=source, effect=effect)
        default_msgs = {
            "rating": f"Rated {value}/10.", "interested": "Marked as interested.", "saved": "Saved.",
            "unsaved": "Removed from saved.", "ignored": "Ignored — you won't be notified about it again.",
            "too_expensive": "Noted: too expensive. This lowers your personal price target, not the market value.",
            "would_pay": f"Noted: you'd pay €{(value or 0):.0f}. Used for your Personal Value Score only.",
            "not_for_me": "Noted: not for you. Personal Value adapts; Deal Score stays objective.",
            "good_deal": "Noted: you consider this a good deal.", "overpriced": "Marked overpriced.",
        }
        return {"ok": True, "message": msg or default_msgs.get(kind, "Done."), "feedback_id": fid, "effect": effect}

    def _record(self, row: dict, kind: str, value, text, source, effect: str = "") -> int:
        snap = {"features": features_of(row), "price": row["price"], "deal_score": row["deal_score"],
                "personal_score": row["personal_score"], "classification": row["classification"],
                "title": (row["title"] or "")[:120]}
        return self.db.insert("feedback", {
            "listing_id": row["id"], "kind": kind, "value": value, "text": text, "source": source,
            "snapshot": jdumps(snap), "effect": effect, "created_at": time.time(), "active": 1})

    def _rescore(self, listing_id: int) -> None:
        row = self.db.one("SELECT * FROM listings WHERE id=?", (listing_id,))
        if row:
            self.engine.apply_scores(listing_id, self.engine.evaluate(row))

    # ---------------------------------------------------------------- learning control
    def undo(self, feedback_id: int) -> dict:
        fb = self.db.one("SELECT * FROM feedback WHERE id=?", (feedback_id,))
        if not fb:
            raise KeyError("feedback not found")
        self.db.update("feedback", feedback_id, {"active": 0})
        # restore a superseded rating, if this was the replacement
        prev = self.db.one("SELECT id FROM feedback WHERE superseded_by=? ORDER BY id DESC LIMIT 1", (feedback_id,))
        if prev:
            self.db.update("feedback", prev["id"], {"active": 1, "superseded_by": None})
        if fb["kind"] == "market_value":
            self.db.execute("UPDATE market_corrections SET active=0 WHERE listing_id=? AND kind='reference' AND value=?",
                            (fb["listing_id"], fb["value"]))
            self.engine.market.recalc_all()
        self.engine.prefs.invalidate()
        self.engine.wants.invalidate()
        if fb["listing_id"]:
            self._rescore(fb["listing_id"])
        log.event("learning.undo", feedback_id=feedback_id, kind=fb["kind"])
        return {"ok": True, "message": f"Undid {fb['kind']} feedback #{feedback_id}"}

    def redo(self, feedback_id: int) -> dict:
        self.db.update("feedback", feedback_id, {"active": 1})
        self.engine.prefs.invalidate()
        self.engine.wants.invalidate()
        return {"ok": True}

    def reset_learning(self) -> dict:
        n = self.db.scalar("SELECT COUNT(*) FROM feedback WHERE active=1", default=0)
        self.db.execute("UPDATE feedback SET active=0 WHERE active=1 AND kind NOT IN ('market_value','sold')")
        self.engine.prefs.invalidate()
        self.engine.wants.invalidate()
        self.engine.rescore_all()
        log.event("learning.reset", deactivated=n)
        return {"ok": True, "message": f"Personal learning reset ({n} feedback events deactivated; history kept)."}
