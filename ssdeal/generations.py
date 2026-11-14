"""Model age and specs: telling an old version of a product from a new one.

Problem this solves: "MacBook Air" covers laptops from 2010 to 2020 (and then the Apple-chip ones). A 2013 one is worth
a fraction of a 2020 one, so comparing every "MacBook Air" with every other one makes an old laptop look like a bargain.
The same happens with "XPS 13", "ThinkPad X1 Carbon", "Legion 5", "iPad Pro", "Zephyrus G14" and so on.

What happens here, for every ad (not only Apple):
  * the model year is read from the text ("2015", "early 2015", "2015. g.", "(2015)", "modelis 2015"...), ignoring years
    that are about the purchase, warranty or receipt ("pirkts 2021", "garantija līdz 2026");
  * Apple model numbers (A1466, A2179, ...) and the Intel CPU generation (i5-5250U = 5th gen = about 2015) give the age
    when the seller does not;
  * RAM, storage and HDD-vs-SSD are read too;
  * for product families that span many years, the year goes into the product key, so a 2013 laptop is compared only
    with other laptops of that age; when the age cannot be found the deal is marked "age unknown" instead of "bargain";
  * very old models and outdated specs lower the deal score with a plain explanation.
"""
from __future__ import annotations

import functools
import re
import time

from .textutil import norm

YEAR_NOW = time.localtime().tm_year

# Families where one product key would mix very different years. Value = buckets (first year, last year, label) or None
# (None = use the exact year).
MACBOOK_AIR_BUCKETS = [(2008, 2009, "2008-09"), (2010, 2011, "2010-11"), (2012, 2017, "2012-17"), (2018, 2020, "2018-20")]
MACBOOK_PRO_BUCKETS = [(2006, 2011, "2006-11"), (2012, 2015, "2012-15"), (2016, 2019, "2016-19"), (2020, 2020, "2020")]
AMBIGUOUS: dict[str, list | None] = {
    "laptop:apple:macbook-air-intel": MACBOOK_AIR_BUCKETS,
    "laptop:apple:macbook-pro-intel": MACBOOK_PRO_BUCKETS,
    "laptop:lenovo:x1-carbon": None, "laptop:lenovo:legion-5": None, "laptop:lenovo:legion-7": None,
    "laptop:lenovo:legion-pro-5": None, "laptop:lenovo:legion-pro-7": None, "laptop:lenovo:legion-slim-5": None,
    "laptop:dell:xps-13": None, "laptop:dell:xps-15": None, "laptop:dell:xps-17": None,
    "laptop:asus:zephyrus-g14": None, "laptop:asus:zephyrus-g15": None, "laptop:asus:zephyrus-g16": None,
    "laptop:asus:zephyrus-m16": None,
    "pc:apple:mac-studio": None,
    "tablet:apple:ipad": None, "tablet:apple:ipad-pro": None, "tablet:apple:ipad-air": None, "tablet:apple:ipad-mini": None,
    "wearable:apple:watch-se": None, "headphones_mic:apple:airpods": None,
}

# Apple model numbers printed on the bottom of the laptop -> (family, bucket/first year, last year)
APPLE_A = {
    "a1237": ("air", 2008, 2008), "a1304": ("air", 2009, 2009), "a1369": ("air", 2010, 2011), "a1370": ("air", 2010, 2011),
    "a1465": ("air", 2012, 2015), "a1466": ("air", 2012, 2017), "a1932": ("air", 2018, 2019), "a2179": ("air", 2020, 2020),
    "a2337": ("air-m1", 2020, 2020), "a2681": ("air-m2", 2022, 2022), "a2941": ("air-m2", 2023, 2023),
    "a3113": ("air-m3", 2024, 2024), "a3114": ("air-m3", 2024, 2024), "a3240": ("air-m4", 2025, 2025), "a3241": ("air-m4", 2025, 2025),
    "a1278": ("pro", 2009, 2012), "a1286": ("pro", 2008, 2012), "a1297": ("pro", 2009, 2011), "a1425": ("pro", 2012, 2013),
    "a1502": ("pro", 2013, 2015), "a1398": ("pro", 2012, 2015), "a1706": ("pro", 2016, 2017), "a1707": ("pro", 2016, 2017),
    "a1708": ("pro", 2016, 2017), "a1989": ("pro", 2018, 2019), "a1990": ("pro", 2018, 2019), "a2159": ("pro", 2019, 2019),
    "a2141": ("pro", 2019, 2019), "a2251": ("pro", 2020, 2020), "a2289": ("pro", 2020, 2020),
}
APPLE_CHIP_YEAR = {"m1": 2020, "m2": 2022, "m3": 2023, "m4": 2024, "m5": 2025}
INTEL_GEN_YEAR = {2: 2011, 3: 2012, 4: 2013, 5: 2015, 6: 2016, 7: 2017, 8: 2018, 9: 2019, 10: 2020, 11: 2021, 12: 2022,
                  13: 2023, 14: 2024}
# categories where age matters for the price (a 1975 film camera is not "outdated", it is the point)
AGE_CATS = {"laptop", "pc", "phone", "tablet", "gpu", "cpu", "console", "tv", "monitor", "wearable", "headphones_mic",
            "motherboard", "ram", "storage"}
SPEC_CATS = {"laptop", "pc"}

_YEAR = re.compile(r"(?<![\d.,/-])((?:199[5-9]|20[0-3]\d))(?![\d])(?![a-fh-z])(?!g[a-z])")
_NOT_MODEL = re.compile(r"(pirkt|pirku|pirkam|nopirk|iegad|bought|purchas|kupl|купл|garantij|warrant|lidz\b|until|\bдо\b|cek|receipt|"
                        r"ceks|rekin|invoice|kopš|kops|since|remont|nomain|replaced|mainit|jauns akum|baterij|akumulator|battery|"
                        r"lietot|used since|izmantot)[^.\n]{0,18}$")
_UNIT_AFTER = re.compile(r"\s*(mah|wh?\b|eur|€|euro|ls\b|rpm|mhz|ghz|hz\b|km\b|gb|mb|tb|mm\b|cm\b|px|dpi|lm\b|v\b|x\b|\*|kg\b|\s+g\b)")
_INTEL = re.compile(r"(?<![a-z0-9])(?:core\s*)?i[3579]\s*-?\s*(\d{4,5})[a-z]{0,3}\d?(?![0-9])")
_A_NUM = re.compile(r"(?<![a-z0-9])(a[12-3]\d{3})(?![0-9])")
_CHIP = re.compile(r"(?<![a-z0-9])(m[1-5])(?:\s*(?:pro|max|ultra))?(?![a-z0-9])")
_HP_GEN = re.compile(r"(?:probook|elitebook|zbook)[\w\s-]{0,12}?\bg(\d{1,2})\b")
_TP_GEN = re.compile(r"thinkpad[\w\s-]{0,20}?\bgen\.?\s*(\d{1,2})\b")
# below these prices a RECENT working item is very unusual: a find, a typo or a scam, but always worth a look
RECENT_FLOOR = {"laptop": 150, "pc": 150, "phone": 60, "tablet": 60, "gpu": 60, "console": 80, "monitor": 40, "tv": 60,
                "wearable": 30, "cpu": 30, "camera": 80, "drone": 80}
_RAM = re.compile(r"(?<![0-9])(\d{1,3})\s*gb\s*(?:ram|ddr\d?|lpddr\d?x?|operat\w*|atmin\w*|memor\w*|unified)|(?:ram|atmin\w*|operativ\w*)\W{0,3}(\d{1,3})\s*gb")
_STORAGE = re.compile(r"(?<![0-9])(\d{2,4}|[1-8])\s*(gb|tb)\s*(ssd|hdd|nvme|m\.?2|flash|storage|ciet\w*|disk\w*|atmin\w*)|(ssd|hdd|nvme)\W{0,3}(\d{2,4}|[1-8])\s*(gb|tb)")


def _is_unit(t: str, end: int) -> bool:
    return bool(_UNIT_AFTER.match(t, end))


@functools.lru_cache(maxsize=4096)
def specs(title: str, description: str = "") -> dict:
    """Everything we can read about age and specs. Keys only present when found."""
    head, full = norm(title), norm(f"{title} {description[:1500]}")
    out: dict = {}
    years = []
    for t in (head, full):
        for m in _YEAR.finditer(t):
            y = int(m.group(1))
            if y > YEAR_NOW or _is_unit(t, m.end()) or _NOT_MODEL.search(t[max(0, m.start() - 40):m.start()]):
                continue
            years.append(y)
        if years:
            break                                      # the title wins over the description
    if years:
        out["year"], out["year_from"] = min(years), "text"
    if "year" not in out:
        m = _HP_GEN.search(full)
        if m and 1 <= int(m.group(1)) <= 12:
            out["year"], out["year_from"] = 2013 + int(m.group(1)), f"HP generation G{m.group(1)}"
    if "year" not in out:
        m = _TP_GEN.search(full)
        if m and 1 <= int(m.group(1)) <= 14:
            out["year"], out["year_from"] = 2011 + int(m.group(1)), f"ThinkPad Gen {m.group(1)}"
    m = _A_NUM.search(full)
    if m and m.group(1) in APPLE_A:
        fam, y0, y1 = APPLE_A[m.group(1)]
        out["apple_model"], out["apple_family"], out["apple_years"] = m.group(1).upper(), fam, (y0, y1)
        if "year" not in out:            # a range like 2012-2017: count it as the newest (benefit of the doubt)
            out["year"], out["year_from"] = y1, f"model number {m.group(1).upper()}" + (f", made {y0}-{y1}" if y0 != y1 else "")
    m = _CHIP.search(full)
    if m and ("mac" in full or "ipad" in full):
        out["chip"] = m.group(1)
    m = _INTEL.search(full)
    if m:
        num = m.group(1)
        gen = int(num[:2]) if len(num) == 5 else int(num[0])
        if gen in INTEL_GEN_YEAR:
            out["cpu_gen"] = gen
            if "year" not in out:
                out["year"], out["year_from"] = INTEL_GEN_YEAR[gen], "CPU generation"
    elif "core 2 duo" in full or "core2duo" in full:
        out.setdefault("year", 2009)
        out.setdefault("year_from", "CPU (Core 2 Duo)")
    m = _RAM.search(full)
    if m:
        v = int(m.group(1) or m.group(2))
        if 1 <= v <= 256:
            out["ram_gb"] = v
    m = _STORAGE.search(full)
    if m:
        num, unit, kind = (m.group(1), m.group(2), m.group(3)) if m.group(1) else (m.group(5), m.group(6), m.group(4))
        gb = int(num) * (1024 if unit == "tb" else 1)
        if 8 <= gb <= 16384:
            out["storage_gb"] = gb
            out["storage_kind"] = "hdd" if "hdd" in kind else "ssd"
    if "hdd" in full and "ssd" not in full and "nvme" not in full:
        out["storage_kind"] = "hdd"
    return out


def _bucket(year: int, buckets: list) -> str | None:
    for y0, y1, label in buckets:
        if y0 <= year <= y1:
            return label
    return None


def refine(match, title: str, description: str = ""):
    """Put the model age into the product key of families that span many years (see AMBIGUOUS)."""
    if match is None:
        return None
    sp = specs(title, description)
    v = dict(match.variant or {})
    for k in ("year", "year_from", "ram_gb", "storage_gb", "storage_kind", "apple_model", "cpu_gen", "chip"):
        if k in sp:
            v[k] = sp[k]
    match.variant = v
    if match.key not in AMBIGUOUS:
        return match
    # an Apple-chip model number in an ad that only says "MacBook Air": it is not an Intel one
    fam = sp.get("apple_family", "")
    if match.key.endswith("macbook-air-intel") and fam.startswith("air-m"):
        chip = fam.split("-")[1]
        match.key, match.name, match.confidence = f"laptop:apple:macbook-air-{chip}", f"MacBook Air {chip.upper()}", max(match.confidence, 0.75)
        return match
    buckets = AMBIGUOUS[match.key]
    label = None
    if buckets and fam in ("air", "pro") and "apple_years" in sp and not sp.get("year_from") == "text":
        label = _bucket(sp["apple_years"][1], buckets)
    elif "year" in sp:
        label = _bucket(sp["year"], buckets) if buckets else str(sp["year"])
    if label:
        match.key = f"{match.key}-{label}"
        match.name = f"{match.name} {label}" if "(" not in match.name else match.name.replace(" (", f" {label} (")
        match.confidence = min(0.85, match.confidence + 0.3)
        v["generation"] = label
    else:
        v["generation_unknown"] = True
    return match


def age_notes(listing: dict, match) -> list[tuple[float, str, str | None]]:
    """(points, reason, flag) for the deal score: old model, outdated specs, unknown generation."""
    cat = listing.get("category_key") or (match.category if match else "other")
    sp = specs(listing.get("title") or "", listing.get("description") or "")
    out: list[tuple[float, str, str | None]] = []
    if cat in AGE_CATS and sp.get("year"):
        age = YEAR_NOW - sp["year"]
        src = "" if sp.get("year_from") == "text" else f", from the {sp['year_from']}"
        if age >= 8:
            out.append((-6.0, f"Old model ({sp['year']}{src}, ~{age} years) — outdated, worth much less and harder to resell", "old_model"))
        elif age >= 5:
            out.append((-3.0, f"Model from {sp['year']}{src} (~{age} years old) — check it still does what you need", None))
        else:
            out.append((0.0, f"Model year {sp['year']}{src}", None))
    if cat in SPEC_CATS:
        if sp.get("ram_gb") and sp["ram_gb"] <= 4:
            out.append((-4.0, f"Only {sp['ram_gb']} GB RAM — too little for today's software", "outdated_specs"))
        if sp.get("storage_kind") == "hdd":
            out.append((-2.0, "Hard disk (HDD) instead of an SSD — slow", "outdated_specs"))
        elif sp.get("storage_gb") and sp["storage_gb"] <= 128:
            out.append((-1.5, f"Small storage ({sp['storage_gb']} GB)", None))
    price = listing.get("price")
    if (cat in RECENT_FLOOR and sp.get("year") and YEAR_NOW - sp["year"] <= 5 and price is not None and 0 < price < RECENT_FLOOR[cat]
            and listing.get("condition") not in ("broken", "parts")):
        out.append((0.0, f"A {sp['year']} model for €{price:.0f} is far below what recent {cat}s sell for — a real find, a typo "
                         f"(€{price * 10:.0f}?) or a scam. Worth checking quickly: ask for photos and meet in person.", "recent_cheap"))
    if match is not None and (match.variant or {}).get("generation_unknown"):
        out.append((0.0, f"Model year / generation not given — {match.name} was sold for many years and older ones are worth "
                         f"much less. Ask the seller (model number on the bottom, or the year).", "age_unknown"))
    return out
