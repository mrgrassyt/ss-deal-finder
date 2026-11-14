"""Listing analysis pipeline: identify -> evaluate -> score -> classify -> watchlist.

Used by the scanner for every new or changed listing, and by the API when
something is re-evaluated (e.g. after market recalculation or feedback).
"""
from __future__ import annotations

import re
import time

from .catalog import Match, identify
from .db import Database, jdumps, jloads
from .feeds import CATEGORIES, category_from_path, is_service_path
from .flip import compute_flip
from .learning import PreferenceModel
from .logs import get_logger
from .market import Market
from .scoring import Scorer
from .flip import compute_flip
from .wants import WantsModel
from .textutil import detect_condition, detect_flags, detect_kind, fingerprint, is_low_value_item, jaccard, norm, service_verdict, tokens

log = get_logger("engine")

LEVELS = ("GOOD_DEAL", "INTERESTING", "IGNORE")
CAT_REFINE = {"gpu", "cpu", "ram", "storage", "psu", "motherboard"}


class Engine:
    def __init__(self, db: Database, settings):
        self.db = db
        self.settings = settings
        self.market = Market(db, settings)
        self.scorer = Scorer(self.market, settings)
        self.prefs = PreferenceModel(db, settings)
        self.wants = WantsModel(db)

    # ---------------------------------------------------------------- analysis
    def analyze(self, title: str, description: str, ss_path: str, feed_category: str,
                attrs: dict | None = None, price_kind: str = "sale") -> dict:
        path_cat = category_from_path(ss_path, feed_category)
        text = f"{title}\n{description or ''}"
        match = identify(title, description or "", path_cat)
        category = path_cat
        if match and (path_cat in ("pc_parts_other", "other", "camera_accessory") or
                      (match.category in CAT_REFINE and path_cat in CAT_REFINE)):
            category = match.category if match.category in CATEGORIES else path_cat
        cond, evidence = detect_condition(text, attrs)
        flags = detect_flags(text)
        if price_kind == "buying" and "buying" not in flags:
            flags.append("buying")
        if price_kind == "exchange" and "exchange" not in flags:
            flags.append("exchange")
        if price_kind == "rent" or is_service_path(ss_path):
            flags.append("service")
        if match and match.components and "bundle" not in flags:
            flags.append("bundle")
        # a battery / screen / case FOR a phone is not the phone: never value it against the device market
        kind, kind_why = detect_kind(title, description or "", category)
        # anything filed under computer / camera accessories is an accessory, whatever device name it mentions
        if kind == "device" and category in ("peripheral", "camera_accessory") and match and match.category in (
                "console", "phone", "tablet", "laptop", "wearable", "camera", "pc"):
            kind = "accessory"
        if kind != "device":
            flags.append(kind)
            match = None
        return {
            "category_key": category,
            "category_path": ss_path.rsplit("/", 1)[0],
            "product_key": match.key if match else None,
            "product_name": match.name if match else None,
            "brand": match.brand if match else None,
            "condition": cond,
            "condition_evidence": evidence,
            "flags": sorted(set(flags)),
            "is_buying": 1 if "buying" in flags else 0,
            "fingerprint": fingerprint(description or title),
            "_match": match,
        }

    # ---------------------------------------------------------------- reposts
    def find_repost(self, listing_id: int, fp: str, title: str, category: str, product_key: str | None) -> dict | None:
        same = self.db.one(
            "SELECT id, price, status, first_seen FROM listings WHERE fingerprint=? AND id<>? "
            + ("AND status='removed' " if fp.startswith("t:") else "") + "ORDER BY first_seen DESC LIMIT 1",
            (fp, listing_id))
        if same:
            return same
        if not product_key:
            return None
        cutoff = time.time() - 60 * 86400
        cands = self.db.query(
            """SELECT id, title, price, status, first_seen FROM listings
               WHERE product_key=? AND id<>? AND first_seen>=? ORDER BY first_seen DESC LIMIT 60""",
            (product_key, listing_id, cutoff))
        tk = tokens(title)
        if len(tk) < 5:
            return None  # too little text to tell different sellers apart
        for c in cands:
            if c["status"] == "removed" and jaccard(tk, tokens(c["title"] or "")) >= 0.85:
                return c
        return None

    # ---------------------------------------------------------------- watchlist
    def watch_hits(self, listing: dict) -> list[dict]:
        hits = []
        text = norm(f"{listing.get('title', '')} {listing.get('description') or ''} {listing.get('product_name') or ''}")
        for w in self._watchlist():
            lk = listing.get("product_key") or ""
            # a watch on "MacBook Air (Intel)" still covers the year-specific keys (…-intel-2012-17) made from it
            if w["product_key"] and w["product_key"] != lk and not lk.startswith(w["product_key"] + "-"):
                continue
            if w["category_key"] and w["category_key"] != listing.get("category_key"):
                continue
            if w["query"]:
                ok = True
                for term in w["query"].split():
                    alts = [norm(a) for a in term.split("|") if a]
                    if not any(_contains(text, a) for a in alts):
                        ok = False
                        break
                if not ok:
                    continue
            if w["exclude"] and any(_contains(text, norm(x)) for x in w["exclude"].split() if x):
                continue
            cond = w["condition"] or "any"
            lc = listing.get("condition")
            if cond == "new" and lc != "new":
                continue
            if cond == "used" and lc not in ("used", "new"):
                continue
            if cond == "working" and lc in ("broken", "parts"):
                continue
            hits.append(w)
        return hits

    _wl_cache: tuple[float, list] = (0.0, [])

    def _watchlist(self) -> list[dict]:
        t, rows = self._wl_cache
        if time.time() - t > 15:
            rows = self.db.query("SELECT * FROM watchlist WHERE active=1")
            self._wl_cache = (time.time(), rows)
        return rows

    def invalidate_watchlist(self) -> None:
        self._wl_cache = (0.0, [])

    # ---------------------------------------------------------------- scoring
    def evaluate(self, listing: dict, match: Match | None = None, reidentify: bool = False) -> dict:
        """Compute Deal Score, Personal Value Score and classification for a listing row (dict)."""
        listing = dict(listing)
        listing["flags"] = listing["flags"] if isinstance(listing.get("flags"), list) else jloads(listing.get("flags"), [])
        if match is None and not set(listing["flags"]) & {"part", "accessory"}:
            match = identify(listing.get("title") or "", listing.get("description") or "",
                             category_from_path(listing.get("ss_id") or "", listing.get("category_key") or "other"))
            if match and listing.get("product_key") and match.key != listing["product_key"] and not reidentify:
                match = Match(listing["product_key"], listing.get("product_name") or listing["product_key"],
                              listing.get("category_key") or "other", listing.get("brand"), 0.7, variant=dict(match.variant))
        # rows analysed by an older version (or from the title only) get the part / accessory check again
        new_kind = None
        if not set(listing["flags"]) & {"part", "accessory"}:
            kind, _ = detect_kind(listing.get("title") or "", listing.get("description") or "", listing.get("category_key"))
            if kind == "device" and listing.get("category_key") in ("peripheral", "camera_accessory") and match and match.category in (
                    "console", "phone", "tablet", "laptop", "wearable", "camera", "pc"):
                kind = "accessory"
            if kind != "device":
                listing["flags"] = list(listing["flags"]) + [kind]
                match = None
                new_kind = kind
        # services: read the whole text again with the current rules (older rows were flagged with fewer phrases)
        if "service" not in listing["flags"] and "buying" not in listing["flags"]:
            if service_verdict(f"{listing.get('title') or ''}\n{listing.get('description') or ''}")[0]:
                listing["flags"] = list(listing["flags"]) + ["service"]
                new_kind = new_kind or "service"
        rekey = None
        if reidentify and new_kind is None and not set(listing["flags"]) & {"part", "accessory"}:
            nk = match.key if match else None
            if nk != listing.get("product_key"):
                rekey = {"product_key": nk, "product_name": match.name if match else None, "brand": match.brand if match else None}
        history = {"initial_price": listing.get("initial_price"), "repost_of": listing.get("repost_of")}
        if listing.get("repost_of"):
            prev = self.db.one("SELECT price FROM listings WHERE id=?", (listing["repost_of"],))
            history["repost_prev_price"] = prev["price"] if prev else None
        deal = self.scorer.deal_score(listing, match, history)
        hits = self.watch_hits(listing)
        personal = self.wants.score(listing)
        level, why = self.classify(listing, deal, personal, hits)
        if level != "IGNORE" and not hits and not (personal.get("matched") and personal["score"] >= 66) \
                and (self.settings.get("filters", {}) or {}).get("hide_negative_profit", True):
            fl = compute_flip(listing.get("price"), listing.get("condition"), {"valuation": deal["valuation"], "deal": deal},
                              self.settings.get("flip", {}) or {})
            if fl and not fl.get("rough") and fl["profit"] < 0:
                level, why = "IGNORE", f"would be a loss to resell (about −€{abs(fl['profit'])})"
        details = {
            "deal": {k: deal[k] for k in ("score", "confidence", "reasons", "headline", "repair", "flags_out")},
            "valuation": deal["valuation"],
            "personal": personal,
            "classification_reason": why,
            "watch_hits": [{"id": w["id"], "name": w["name"]} for w in hits],
            "identification_confidence": match.confidence if match else 0.0,
            "match": match.to_dict() if match else None,
        }
        return {"deal_score": deal["score"], "personal_score": personal["score"], "confidence": deal["confidence"],
                "classification": level, "score_details": details, "watch_hits": hits, "new_kind": new_kind, "rekey": rekey,
                "flags": listing["flags"]}

    def classify(self, listing: dict, deal: dict, personal: dict, hits: list[dict]) -> tuple[str, str]:
        n = self.settings.get("notify", {})
        f = self.settings.get("filters", {})
        shift = {"high_recall": -6, "balanced": 0, "strict": 6}.get(n.get("sensitivity", "balanced"), 0)
        good_t = n.get("good_deal_threshold", 78) + shift
        int_t = n.get("interesting_threshold", 60) + shift
        pgood = n.get("personal_good_threshold", 80) + shift
        pint = n.get("personal_interesting_threshold", 66) + shift
        flags = set(listing.get("flags") or [])
        price = listing.get("price")
        cat = listing.get("category_key") or "other"
        ds, ps = deal["score"], personal["score"]
        out_flags = set(deal.get("flags_out") or [])

        # --- hard filters (junk / not an offer)
        if listing.get("is_buying") or "buying" in flags:
            if f.get("ignore_buying_ads", True):
                return "IGNORE", "wanted ad (someone is buying)"
        if "service" in flags and f.get("ignore_services", True):
            return "IGNORE", "service / rental, not an item for sale"
        if flags & {"part", "accessory"} and f.get("ignore_parts", True) and not any(
                not w.get("max_price") or (price is not None and price <= w["max_price"]) for w in hits):
            return "IGNORE", ("spare part" if "part" in flags else "accessory") + " for a device, not the device itself"
        if price is None:
            return ("INTERESTING", "watchlist match without price") if hits else ("IGNORE", "no price")
        catcfg = (f.get("categories") or {}).get(cat, {})
        within_watch = [w for w in hits if not w.get("max_price") or price <= w["max_price"]]
        if catcfg.get("enabled") is False and not within_watch:
            return "IGNORE", f"category {cat} disabled in filters"
        if not within_watch:
            if f.get("min_price") and price < f["min_price"]:
                return "IGNORE", "below minimum price filter"
            maxp = catcfg.get("max_budget") or f.get("max_price")
            if maxp and price > maxp:
                return "IGNORE", f"above budget filter €{maxp:.0f}"
        floor = f.get("junk_value_floor", 8)
        if (is_low_value_item(listing.get("title") or "") and price < max(floor, 1)
                and not flags & {"bundle", "collection"} and not within_watch):
            return "IGNORE", "low-value accessory (junk filter)"
        if price < CATEGORIES.get(cat, {}).get("value_floor", 10) * 0.25 and not listing.get("product_key") \
                and not flags & {"bundle", "collection"} and not within_watch:
            return "IGNORE", "very low value item"
        min_deal = catcfg.get("min_deal")
        # --- watchlist
        for w in within_watch:
            if ds >= (w.get("min_deal") or 0):
                return "GOOD_DEAL", f"watchlist '{w['name']}' match within budget"
        # --- good deal
        if ds >= max(good_t, min_deal or 0):
            return "GOOD_DEAL", f"Deal Score {ds:.0f} ≥ {good_t}"
        if ps >= pgood and ds >= int_t - 5:
            return "GOOD_DEAL", f"Personal Value {ps:.0f} ≥ {pgood} with fair price (Deal {ds:.0f})"
        # --- interesting (high recall)
        if ds >= int_t:
            return "INTERESTING", f"Deal Score {ds:.0f} ≥ {int_t}"
        if ps >= pint:
            return "INTERESTING", f"Personal Value {ps:.0f} ≥ {pint}"
        if hits:
            return "INTERESTING", "watchlist match (above budget or below min deal)"
        if out_flags & {"uncertain_bargain", "cheap_for_category"}:
            return "INTERESTING", "possible bargain with uncertain value — worth checking"
        if "review_collection" in out_flags and price <= 250 and shift <= 0:
            return "INTERESTING", "lot / collection worth reviewing"
        rep = deal.get("repair")
        if rep and rep.get("expected_profit", 0) > 15 and shift <= 0:
            return "INTERESTING", "repair opportunity with positive expected profit"
        return "IGNORE", f"Deal {ds:.0f} / Personal {ps:.0f} below thresholds"

    def apply_scores(self, listing_id: int, result: dict) -> None:
        if result.get("rekey") is not None:
            self.db.update("listings", listing_id, result["rekey"])
        if result.get("new_kind") == "service":
            self.db.update("listings", listing_id, {"flags": jdumps(sorted(set(result["flags"])))})
        elif result.get("new_kind"):
            # remember it: a part is removed from the device's market data on the next recalculation
            self.db.update("listings", listing_id, {"flags": jdumps(sorted(set(result["flags"]))),
                                                    "product_key": None, "product_name": None})
        meta = self.db.one("SELECT price, condition FROM listings WHERE id=?", (listing_id,)) or {}
        flip = compute_flip(meta.get("price"), meta.get("condition"), result["score_details"], self.settings.get("flip", {}) or {})
        self.db.update("listings", listing_id, {
            "profit_est": flip["profit"] if flip else None, "roi_est": flip["roi"] if flip else None,
            "deal_score": result["deal_score"],
            "personal_score": result["personal_score"] if (result["score_details"].get("personal") or {}).get("matched") else None,
            "confidence": result["confidence"], "classification": result["classification"],
            "score_details": jdumps(result["score_details"]), "scored_at": time.time()})

    def rescore_all(self, only_active: bool = True, limit: int | None = None, reidentify: bool = False) -> int:
        q = "SELECT * FROM listings" + (" WHERE status='active'" if only_active else "") + " ORDER BY last_seen DESC"
        if limit:
            q += f" LIMIT {int(limit)}"
        n = marked = 0
        for row in self.db.query(q):
            res = self.evaluate(row, reidentify=reidentify)
            self.apply_scores(row["id"], res)
            marked += 1 if (res.get("new_kind") or res.get("rekey") is not None) else 0
            n += 1
        log.event("engine.rescore", count=n, newly_marked_parts=marked)
        if marked:
            # parts/accessories just left their device's market: recompute prices without them, then score once more
            self.market.recalc_all()
            for row in self.db.query(q):
                self.apply_scores(row["id"], self.evaluate(row, reidentify=reidentify))
        return n


def _contains(text: str, term: str) -> bool:
    if not term:
        return True
    if re.fullmatch(r"[a-z0-9]+", term):
        # loose match: "rx6700" matches "rx 6700"
        squashed = re.sub(r"[\s\-]", "", text)
        return re.search(rf"(?<![a-z0-9]){re.escape(term)}(?![0-9])", text) is not None or \
            re.search(rf"(?<![a-z0-9]){re.escape(term)}(?![0-9])", squashed) is not None
    return term in text
