"""Deal Score (objective) and repair/opportunity evaluation.

The Deal Score answers: "how attractive is this price compared with the
market and resale potential?" It never looks at personal preferences.
Every point added or removed is recorded with a human readable reason.
"""
from __future__ import annotations

import math
import re
import time

from .catalog import Match, pc_components
from .feeds import CATEGORIES
from .generations import age_notes
from .market import Market
from .textutil import norm

# Repair heuristics per category: (typical repair cost as share of working value,
# probability a repair attempt succeeds, value of a dead unit as parts share)
REPAIR_PROFILE = {
    "gpu": (0.35, 0.45, 0.20), "cpu": (0.0, 0.10, 0.10), "motherboard": (0.35, 0.40, 0.15),
    "ram": (0.0, 0.10, 0.05), "storage": (0.0, 0.05, 0.05), "psu": (0.40, 0.40, 0.10),
    "laptop": (0.30, 0.60, 0.25), "pc": (0.20, 0.70, 0.45), "phone": (0.30, 0.65, 0.15),
    "tablet": (0.30, 0.55, 0.15), "camera": (0.35, 0.50, 0.25), "lens": (0.30, 0.45, 0.20),
    "console": (0.25, 0.60, 0.25), "monitor": (0.35, 0.45, 0.10), "tv": (0.35, 0.40, 0.08),
    "audio": (0.25, 0.60, 0.20), "headphones_mic": (0.30, 0.50, 0.10), "video": (0.35, 0.45, 0.20),
}
DEFAULT_REPAIR = (0.35, 0.40, 0.15)

SYMPTOMS = [
    (r"artefakt|артефакт|artifact", "display artifacts (often VRAM/GPU core — hard repair)", 1.4, 0.7),
    (r"neiesledzas|nestrada vispar|не включается|no power|dead", "does not power on", 1.2, 0.8),
    (r"ventilator|fan|kulers|вентилятор", "fan problem (usually cheap fix)", 0.4, 1.3),
    (r"ekran|экран|screen|display|lcd", "screen damage (replacement part needed)", 1.1, 1.1),
    (r"akumulator|baterij|аккумулятор|battery", "battery issue (usually cheap fix)", 0.5, 1.3),
    (r"pieslegvieta|port|ligzda|разъем|charging port", "port/connector damage", 0.6, 1.2),
    (r"udens|udeni|залит|water", "water damage (high risk)", 1.5, 0.5),
    (r"bios|programmatur|прошив|software|icloud|lock|blok[eē]t", "software / lock problem", 0.7, 0.6),
]


def _price_points(discount: float) -> float:
    if discount >= 0:
        return 45 + 55 * (1 - math.exp(-4.5 * discount))
    return max(0.0, 45 + 130 * discount)


def noise_allowance(low: float | None, high: float | None, typical: float | None) -> float:
    """Normal price scatter: a listing only a little below the median is not a deal."""
    if not (low and high and typical):
        return 0.08
    return max(0.04, min(0.10, (high - low) / typical / 2.5))


class Scorer:
    def __init__(self, market: Market, settings):
        self.market = market
        self.settings = settings

    # ---------------------------------------------------------------- valuation
    def valuation(self, listing: dict, match: Match | None) -> dict:
        """Estimate the market value of what is offered in this listing."""
        cond = listing.get("condition") or "used"
        flags = set(listing.get("flags") or [])
        cat = listing.get("category_key") or "other"
        val: dict = {"method": None, "typical": None, "low": None, "high": None, "confidence": 0.0, "notes": []}
        main = self.market.value_for(match.key, "used" if cond in ("broken", "parts", "untested") else cond) if match else None
        if main and main.get("typical"):
            val.update(method="comparables", typical=main["typical"], low=main["low"], high=main["high"],
                       confidence=main["confidence"] * (match.confidence if match else 0.5),
                       n=main["n"], basis=main["basis"])
            if main["note"]:
                val["notes"].append(main["note"])
        # components (camera + lens bundles, PCs, laptops without a model match)
        comps = list(match.components) if match else []
        if cat in ("pc", "laptop") and not (main and main.get("typical")):
            comps = pc_components(listing.get("title", ""), listing.get("description", "") or "")
        comp_vals = []
        for c in comps:
            cv = self.market.value_for(c.key, "used")
            if cv and cv.get("typical"):
                comp_vals.append((c, cv))
        if comp_vals:
            comp_sum = sum(cv["typical"] for _, cv in comp_vals)
            comp_conf = min(cv["confidence"] for _, cv in comp_vals)
            if val["typical"]:
                # bundle: main item plus accessories, buyers pay ~80% of parts value
                extra = comp_sum * 0.8
                val["typical"] += extra
                val["low"] += extra * 0.85
                val["high"] += extra * 1.1
                val["method"] = "comparables+bundle"
                val["notes"].append("bundle valued as main item + 80% of included items: " +
                                    ", ".join(c.name for c, _ in comp_vals))
            elif cat in ("pc", "laptop"):
                base = 60.0 if cat == "pc" else 80.0
                typ = comp_sum * 0.85 + base
                val.update(method="component_sum", typical=typ, low=typ * 0.8, high=typ * 1.15,
                           confidence=min(0.45, comp_conf * 0.6))
                val["notes"].append("valued from identified components (" +
                                    ", ".join(c.name for c, _ in comp_vals) + f") + €{base:.0f} for the rest")
        if not val["typical"] and match and main and main.get("typical") is None and main.get("stats"):
            val["notes"].append(main.get("note", ""))
        # category reference for unidentified items
        cst = self.market.category_stats(cat)
        if cst:
            val["category_low"] = cst["low"]
            val["category_median"] = cst["typical"]
            val["category_n"] = cst["n"]
        return val

    # ---------------------------------------------------------------- repair
    def repair_eval(self, listing: dict, working_value: float | None, price: float | None) -> dict | None:
        cond = listing.get("condition")
        if cond not in ("broken", "parts", "untested") or not working_value or price is None:
            return None
        cat = listing.get("category_key") or "other"
        cost_share, p_success, parts_share = REPAIR_PROFILE.get(cat, DEFAULT_REPAIR)
        text = norm(f"{listing.get('title', '')} {listing.get('description', '') or ''}")
        symptoms = []
        for rx, label, cost_mult, p_mult in SYMPTOMS:
            if re.search(rx, text):
                symptoms.append(label)
                cost_share *= cost_mult
                p_success *= p_mult
        p_success = max(0.05, min(0.9, p_success))
        broken_stats = self.market.stats(listing.get("product_key"), "broken")
        if broken_stats and broken_stats["n"] >= 3:
            parts_value = broken_stats["typical"]
            parts_basis = f"median of {broken_stats['n']} broken/parts listings"
        else:
            parts_value = working_value * parts_share
            parts_basis = f"heuristic {int(parts_share * 100)}% of working value"
        if cond == "untested":
            p_success = 0.6
            repair_cost = 0.0
            symptoms.append("untested — may work as-is")
        elif cond == "parts":
            p_success *= 0.6
            repair_cost = working_value * cost_share * 1.2
        else:
            repair_cost = working_value * cost_share
        ev = p_success * (working_value - repair_cost) + (1 - p_success) * parts_value
        worst_loss = max(0.0, price - parts_value * 0.8)
        return {
            "working_value": round(working_value, 2),
            "repair_cost_est": round(repair_cost, 2),
            "success_probability": round(p_success, 2),
            "parts_value": round(parts_value, 2),
            "parts_basis": parts_basis,
            "expected_value": round(ev, 2),
            "expected_profit": round(ev - price, 2),
            "best_case_profit": round(working_value - repair_cost - price, 2),
            "worst_case_loss": round(worst_loss, 2),
            "worth_for_parts": parts_value >= price,
            "symptoms": symptoms,
            "uncertainty": "high" if not broken_stats else "medium",
        }

    # ---------------------------------------------------------------- deal score
    def deal_score(self, listing: dict, match: Match | None, history: dict | None = None) -> dict:
        history = history or {}
        price = listing.get("price")
        flags = set(listing.get("flags") or [])
        cat = listing.get("category_key") or "other"
        cond = listing.get("condition") or "used"
        reasons: list[dict] = []
        val = self.valuation(listing, match)

        def add(points: float, text: str) -> None:
            reasons.append({"points": round(points, 1), "text": text})

        if price is None:
            return {"score": 0, "confidence": 0, "reasons": [{"points": 0, "text": "No price given"}],
                    "valuation": val, "headline": "No price", "repair": None, "flags_out": []}
        score = 40.0
        confidence = val.get("confidence") or 0.0
        repair = None
        out_flags: list[str] = []
        value_for_discount = val.get("typical")
        if cond in ("broken", "parts", "untested") and val.get("typical"):
            repair = self.repair_eval(listing, val["typical"], price)
            if repair:
                value_for_discount = repair["expected_value"]
                confidence *= 0.6
        if value_for_discount and value_for_discount > 0:
            discount = 1 - price / value_for_discount
            allowance = 0.0 if repair else noise_allowance(val.get("low"), val.get("high"), val.get("typical"))
            raw = _price_points(max(0.0, discount - allowance) if discount > 0 else discount)
            score = 45 + (raw - 45) * (0.55 + 0.45 * min(1.0, confidence * 1.4))
            pct = int(round(discount * 100))
            lo, hi = val.get("low"), val.get("high")
            rng = f"€{lo:.0f}–{hi:.0f}" if lo and hi else f"~€{value_for_discount:.0f}"
            basis = "repair-adjusted expected value" if repair else (
                "asking-price-based estimate" if "sales" not in str(val.get("basis", "")) else "asking prices + confirmed sales")
            if discount >= 0.05:
                add(score - 45, f"{pct}% below estimated value {rng} ({basis})")
            elif discount <= -0.05:
                add(score - 45, f"{-pct}% above estimated value {rng} ({basis})")
            else:
                add(score - 45, f"Priced around market value {rng} ({basis})")
            if confidence < 0.35:
                add(0, f"Low confidence in market value ({int(confidence * 100)}%) — verify manually")
            if (discount > 0.6 and value_for_discount > 80 and confidence > 0.35 and not repair
                    and cond not in ("broken", "parts")):
                out_flags.append("suspicious")
                score -= 3
                add(-3, "Suspiciously low price — verify the item, photos and seller before paying")
            if confidence < 0.35 and discount > 0.35:
                out_flags.append("uncertain_bargain")
        else:
            # no valuation: use category reference, never discard potential bargains
            cmed = val.get("category_median")
            clow = val.get("category_low")
            if cmed and clow and val.get("category_n", 0) >= 10:
                if price <= clow * 0.6 and CATEGORIES.get(cat, {}).get("value_floor", 10) >= 25:
                    score = 62
                    out_flags.append("cheap_for_category")
                    add(22, f"Unidentified item priced well below typical {cat} listings (median €{cmed:.0f}) — worth a look")
                elif match:
                    add(0, f"Only a few comparable listings for {match.name} so far; typical {cat} listing is ~€{cmed:.0f}")
                else:
                    add(0, f"Model not identified; typical {cat} listing is ~€{cmed:.0f}")
            else:
                add(0, f"Not enough market data to value {match.name if match else 'this item'} yet")
            if "collection" in flags:
                score = max(score, 55)
                add(15, "Lot / collection — may contain valuable individual items; review manually")
                out_flags.append("review_collection")
        # ---- model age / specs (an old or unknown-generation model is not a bargain just because it is cheap)
        for pts, text, flag in age_notes(listing, match):
            score += pts
            add(pts, text)
            if flag:
                out_flags.append(flag)
            if flag == "recent_cheap" and score < 64:
                add(64 - score, "Recent model at a give-away price")
                score = 64.0
                out_flags.append("cheap_for_category")
            if flag == "age_unknown" and value_for_discount and price < value_for_discount * 0.85 and score > 45:
                cut = (score - 45) * 0.5
                score -= cut
                add(-cut, "Looks cheap only if it is a recent one — not counted as a bargain until the age is known")
        if repair:
            if repair["expected_profit"] > 0:
                add(0, f"Repair opportunity: expected profit €{repair['expected_profit']:.0f} "
                       f"(success ~{int(repair['success_probability'] * 100)}%), worst-case loss €{repair['worst_case_loss']:.0f}")
            if repair["worth_for_parts"]:
                score += 4
                add(4, "Worth at least its price for parts alone")
        # ---- adjustments
        initial = history.get("initial_price")
        if initial and price < initial:
            drop = (initial - price) / initial
            pts = min(8.0, drop * 40)
            score += pts
            add(pts, f"Price reduced {int(drop * 100)}% (was €{initial:.0f})")
        st = val.get("method") == "comparables" and match and self.market.stats(match.key, "working")
        if st and st.get("demand") is not None:
            pts = (st["demand"] - 0.5) * 8
            score += pts
            add(pts, f"{'High' if pts > 0 else 'Low'} demand: comparable ads sell in ~{st['avg_days_listed']:.0f} days")
        if listing.get("image_url") or listing.get("photos"):
            score += 1.5
        else:
            score -= 2
            add(-2, "No photos")
        desc_len = len(listing.get("description") or "")
        if desc_len and desc_len < 40:
            score -= 2
            add(-2, "Very short description")
        age_h = (time.time() - (listing.get("first_seen") or time.time())) / 3600
        if age_h < 3:
            score += 2
            add(2, "Fresh listing — good deals go fast")
        elif age_h > 24 * 21:
            score -= 2
            add(-2, "Listed for weeks — little competition, room to negotiate")
        if history.get("repost_of"):
            prev = history.get("repost_prev_price")
            if prev and price < prev:
                score += 2
                add(2, f"Reposted cheaper (previously €{prev:.0f})")
            else:
                add(0, "Reposted listing (seen before)")
        if "mining" in flags and cat == "gpu":
            score -= 4
            add(-4, "Used for mining — higher wear risk")
        if "warranty" in flags:
            score += 3
            add(3, "Warranty mentioned")
        if "receipt" in flags or "box" in flags:
            score += 1
            add(1, "Box / receipt included — easier resale")
        if "shop" in flags:
            score -= 3
            add(-3, "Looks like a shop listing (retail pricing)")
        if "negotiable" in flags or "urgent" in flags:
            score += 1.5
            add(1.5, "Seller open to negotiation / urgent sale")
        if "bundle" in flags and val.get("method") == "comparables":
            add(0, "Bundle: check what is included")
        score = max(0.0, min(100.0, score))
        headline = max(reasons, key=lambda r: abs(r["points"]))["text"] if reasons else ""
        return {"score": round(score, 1), "confidence": round(confidence, 3), "reasons": reasons,
                "valuation": val, "repair": repair, "headline": headline, "flags_out": out_flags}
