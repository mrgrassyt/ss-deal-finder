"""Personal ("For you") rating: things the user wants (My items) and things the user liked before. Only listings that are the same as, or similar to, one of these get a Personal score.

Nothing else is ever scored (the score is None), so a Personal score always means "this is what you asked for".
  exact   every word of the item is in the ad, including the model numbers      -> 85..99
  close   most words and model numbers match ("iphone 13" vs "iphone 13 mini")    -> 62..84
  similar same category and shares the brand or series word                      -> 52..61
A price at or under the item's budget adds points; clearly over it removes some.

Liked before (rated 7+, interested, saved, good deal, bought, would pay):
  the same model                                   -> 80..92
  same brand + category and a similar title        -> 64..78
  same brand + category                            -> 56..62
Something you marked "not for me", ignored or rated 1–3 pulls the score of the same model down by 15.
"""
from __future__ import annotations

import re

from .textutil import norm

STOP = {"the", "a", "an", "and", "or", "for", "with", "ar", "un", "uz", "no", "ir", "pardodu", "pardod", "used", "new", "jauns", "jauna", "lietots",
        "lietota", "good", "labs", "laba", "labaja", "stavokli", "gb", "tb", "gen", "generation", "edition", "model", "case", "box"}
GENERIC = {"pro", "max", "plus", "mini", "ultra", "slim", "lite", "air", "se", "digital", "disc"}


def tokens(text: str) -> list[str]:
    out = []
    for t in re.findall(r"[a-z0-9]+", norm(text or "")):
        if t in STOP or (len(t) < 2 and not t.isdigit()):
            continue
        out.append(t)
    return out


def _is_model(t: str) -> bool:
    return any(c.isdigit() for c in t) or t in {"ii", "iii", "iv", "v", "vi", "vii"}


LIKE_KINDS = {"interested": 0.8, "saved": 0.7, "good_deal": 0.8, "bought": 0.9, "would_pay": 0.8, "brand_like": 0.6}
DISLIKE_KINDS = {"not_for_me", "ignored", "brand_dislike"}


def _model_tokens(toks) -> set[str]:
    return {t for t in toks if t not in GENERIC}


class WantsModel:
    def __init__(self, db):
        self.db = db
        self._items: list[dict] | None = None
        self._liked: tuple[list[dict], dict] | None = None
        self.dirty = False                # set when likes change: the scheduler rescores everything once

    def invalidate(self) -> None:
        self._items = None
        self._liked = None
        self.dirty = True

    def liked(self) -> tuple[list[dict], dict]:
        """(liked listing profiles, {product_key: penalty} from dislikes)."""
        if self._liked is None:
            weights: dict[int, float] = {}
            dislikes: set[int] = set()
            for f in self.db.query("SELECT listing_id, kind, value FROM feedback WHERE active=1 AND listing_id IS NOT NULL"):
                k, lid = f["kind"], f["listing_id"]
                if k == "rating" and f["value"] is not None:
                    if f["value"] >= 7:
                        weights[lid] = max(weights.get(lid, 0), min(1.0, f["value"] / 10))
                    elif f["value"] <= 3:
                        dislikes.add(lid)
                elif k in LIKE_KINDS:
                    weights[lid] = max(weights.get(lid, 0), LIKE_KINDS[k])
                elif k in DISLIKE_KINDS:
                    dislikes.add(lid)
            for r in self.db.query("SELECT id FROM listings WHERE saved=1"):
                weights[r["id"]] = max(weights.get(r["id"], 0), 0.7)
            for lid in dislikes:
                weights.pop(lid, None)
            profiles = []
            if weights:
                q = ",".join("?" * len(weights))
                for r in self.db.query(f"SELECT id, title, product_name, product_key, brand, category_key FROM listings WHERE id IN ({q})", list(weights)):
                    toks = tokens(f"{r['title'] or ''} {r['product_name'] or ''}")
                    profiles.append({**r, "w": weights[r["id"]], "toks": set(toks), "mtoks": _model_tokens(toks)})
            bad: dict[str, float] = {}
            if dislikes:
                q = ",".join("?" * len(dislikes))
                for r in self.db.query(f"SELECT product_key FROM listings WHERE id IN ({q}) AND product_key IS NOT NULL", list(dislikes)):
                    bad[r["product_key"]] = 15.0
            self._liked = (profiles, bad)
        return self._liked

    def _from_likes(self, listing: dict, have: set[str]) -> dict | None:
        profiles, _ = self.liked()
        if not profiles:
            return None
        key, cat = listing.get("product_key"), listing.get("category_key")
        brand = (listing.get("brand") or "").lower()
        best = None
        for p in profiles:
            w = p["w"]
            name = (p["product_name"] or p["title"] or "")[:50]
            if p["id"] == listing.get("id"):
                s, kind = 80 + 12 * w, "you liked this one"
            elif key and p["product_key"] == key:
                s, kind = 80 + 12 * w, f"same model as “{name}” you liked"
            elif cat and p["category_key"] == cat and brand and (p["brand"] or "").lower() == brand:
                sim = len(p["mtoks"] & have) / max(1, len(p["mtoks"]))
                if sim >= 0.5:
                    s, kind = 64 + 14 * sim * w, f"similar to “{name}” you liked"
                else:
                    s, kind = 56 + 6 * w, f"same brand and category as “{name}” you liked"
            else:
                continue
            if best is None or s > best["score"]:
                best = {"score": round(min(s, 95), 1), "matched": True, "want": None, "liked_id": p["id"],
                        "parts": [{"points": round(min(s, 95), 1), "text": kind}]}
        return best

    def items(self) -> list[dict]:
        if self._items is None:
            rows = self.db.query("SELECT * FROM wants WHERE active=1")
            for r in rows:
                r["toks"] = tokens(f"{r['name']} {r.get('keywords') or ''}")
            self._items = rows
        return self._items

    def score(self, listing: dict) -> dict:
        res = self._score_wants(listing)
        tk = tokens(f"{listing.get('title') or ''} {listing.get('product_name') or ''}")
        liked = self._from_likes(listing, set(tk))
        if liked and (not res["matched"] or liked["score"] > res["score"]):
            res = liked
        _, bad = self.liked()
        pen = bad.get(listing.get("product_key") or "", 0.0)
        if res["matched"] and pen:
            res = {**res, "score": max(1.0, round(res["score"] - pen, 1)), "parts": res["parts"] + [{"points": -pen, "text": "you marked this model “not for me” before"}]}
        return res

    def _score_wants(self, listing: dict) -> dict:
        items = self.items()
        if not items:
            return {"score": 0, "matched": False, "parts": [], "want": None}
        text = f"{listing.get('title') or ''} {listing.get('product_name') or ''} {(listing.get('attrs') or {}).get('brand', '') if isinstance(listing.get('attrs'), dict) else ''}"
        tk = tokens(text)
        have = set(tk) | {a + b for a, b in zip(tk, tk[1:])}       # "a7 iii" == "a7iii"
        price = listing.get("price")
        best = None
        for w in items:
            wt = w["toks"]
            if not wt:
                continue
            model = [t for t in wt if _is_model(t)]
            ok = {t for i, t in enumerate(wt) if t in have or (i + 1 < len(wt) and wt[i] + wt[i + 1] in have) or (i > 0 and wt[i - 1] + t in have)}
            cov = sum(1 for t in wt if t in ok) / len(wt)
            mcov = (sum(1 for t in model if t in ok) / len(model)) if model else cov
            variant = (have & GENERIC) - set(wt)          # "iPhone 13 mini" is not the "iPhone 13" you asked for
            if cov >= 0.999 and mcov >= 0.999 and not variant:
                base, kind = 85 + 8 * min(1, len(wt) / 4), "same item"
            elif cov >= 0.6 and mcov >= 0.6 or (cov >= 0.999 and variant):
                base, kind = 62 + 22 * (cov + mcov) / 2 - 11, "close to your item"
            elif w.get("category_key") and w["category_key"] == listing.get("category_key") and any(t in have and t not in GENERIC for t in wt if not _is_model(t) or len(t) > 2):
                base, kind = 52 + 9 * cov, "similar to your item"
            else:
                continue
            base = min(base, 99 if kind == "same item" else 84 if kind.startswith("close") else 61)
            adj, note = 0.0, None
            mp = w.get("max_price")
            if mp and price is not None:
                if price <= mp:
                    adj, note = 6.0 if kind != "similar to your item" else 3.0, f"within your budget €{mp:.0f}"
                elif price > mp * 1.15:
                    adj, note = -15.0, f"over your budget €{mp:.0f}"
            s = max(40.0, min(99.0, base + adj))
            if best is None or s > best["score"]:
                best = {"score": round(s, 1), "matched": True, "want": w["name"], "want_id": w["id"],
                        "parts": [{"points": round(s, 1), "text": f"{kind}: “{w['name']}”"}] + ([{"points": adj, "text": note}] if note else [])}
        return best or {"score": 0, "matched": False, "parts": [], "want": None}
