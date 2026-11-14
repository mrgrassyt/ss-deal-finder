"""Plain-money view of a deal: where it probably resells and what is left after costs.

Always returns a number when there is a price: with market data it is based on the typical asking price (cautious end
when the data is thin); without any, a clearly labelled rough guess is used instead of nothing."""
from __future__ import annotations


def compute_flip(price, condition, det: dict, cfg: dict) -> dict | None:
    if price is None:
        return None
    v = (det or {}).get("valuation") or {}
    typical, lo, hi = v.get("typical"), v.get("low"), v.get("high")
    disc = float(cfg.get("sale_discount_pct", 8)) / 100
    extra = float(cfg.get("extra_costs", 3))
    invest = price + extra
    sale = lambda x: x * (1 - disc)  # noqa: E731
    conf = ((det or {}).get("deal") or {}).get("confidence") or 0
    needs_work = condition in ("broken", "parts", "untested")
    rep = ((det or {}).get("deal") or {}).get("repair")
    if needs_work and rep:
        fixed = max(0.0, rep["working_value"] - rep["repair_cost_est"])
        ev = rep["expected_value"]
        profit = sale(ev) - invest
        return {"rough": False, "uncertain": False, "wide_range": True, "repair": True, "resale": round(sale(ev)),
                "resale_low": round(sale(rep["parts_value"])), "resale_high": round(sale(fixed)), "profit": round(profit),
                "roi": round(profit / invest * 100) if invest else None,
                "profit_low": round(sale(rep["parts_value"]) - invest), "profit_high": round(sale(fixed) - invest),
                "confidence": "low", "n": v.get("n"), "costs": extra, "fix_chance": rep["success_probability"],
                "why": f"needs work: €{round(sale(rep['parts_value']))} in parts, about €{round(sale(fixed))} if fixed "
                       f"({int(rep['success_probability'] * 100)}% chance)"}
    if not typical or needs_work:
        # no usable market value (or the item needs repair): rough guess = a typical small margin on the buying price
        margin = float(cfg.get("rough_margin_pct", 12)) / 100 * (0.5 if needs_work else 1)
        resale = price * (1 + margin)
        profit = resale - invest
        return {"rough": True, "uncertain": False, "wide_range": False, "resale": round(resale), "resale_low": None,
                "resale_high": None, "profit": round(profit), "roi": round(profit / invest * 100) if invest else None,
                "profit_low": None, "profit_high": None, "confidence": "low", "n": v.get("n"), "costs": extra,
                "why": "needs repair or checking: rough guess" if needs_work else "no market data yet: rough guess"}
    # a wide range or low confidence means the model is probably not exact (e.g. "Canon 50mm f/1.4" = EUR 100 FD lens or
    # EUR 1,000 L lens): plan with the cautious end of the range
    wide = bool(lo and hi and hi / max(lo, 1) > 1.6) or (v.get("n") is not None and v.get("n") < 4)
    basis = typical if conf >= 0.6 and not wide else (lo + typical) / 2 if conf >= 0.35 and lo else (lo or typical)
    profit = sale(basis) - invest
    shown = basis if (conf < 0.6 or wide) else typical
    uncertain = (conf < 0.35 or wide) and invest > 0 and profit / invest > 0.6
    return {"rough": False, "uncertain": uncertain, "wide_range": wide, "resale": round(sale(shown)),
            "resale_low": round(sale(lo)) if lo else None, "resale_high": round(sale(hi)) if hi else None,
            "profit": round(profit), "roi": round(profit / invest * 100) if invest else None,
            "profit_low": round(sale(lo) - invest) if lo else None, "profit_high": round(sale(hi) - invest) if hi else None,
            "confidence": "high" if conf >= 0.6 else "medium" if conf >= 0.35 else "low", "n": v.get("n"), "costs": extra}
