"""Product identification: turns free-text SS.lv ads into canonical product keys.

A product key groups comparable listings for market pricing, e.g.
``gpu:amd:rx-6700`` or ``camera:nikon:d610``. When no specific pattern matches,
a looser ``loose:<category>:<brand>:<model-token>`` key is produced with lower
confidence, so even unknown products accumulate a market history.

No prices are hard-coded anywhere: market values come exclusively from
observed listings, your corrections and your confirmed sales.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .textutil import norm


@dataclass
class Match:
    key: str
    name: str
    category: str
    brand: str | None = None
    confidence: float = 0.8     # how sure we are that the ad is this product
    components: list["Match"] = field(default_factory=list)
    variant: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {"key": self.key, "name": self.name, "category": self.category, "brand": self.brand,
                "confidence": self.confidence, "variant": self.variant,
                "components": [c.to_dict() for c in self.components]}


BRANDS = {
    # computers & parts
    "asus": "ASUS", "rog": "ASUS", "msi": "MSI", "gigabyte": "Gigabyte", "aorus": "Gigabyte", "evga": "EVGA",
    "zotac": "Zotac", "palit": "Palit", "gainward": "Gainward", "sapphire": "Sapphire", "powercolor": "PowerColor",
    "xfx": "XFX", "asrock": "ASRock", "pny": "PNY", "inno3d": "Inno3D", "kfa2": "KFA2", "galax": "Galax",
    "nvidia": "NVIDIA", "amd": "AMD", "intel": "Intel", "corsair": "Corsair", "kingston": "Kingston",
    "crucial": "Crucial", "samsung": "Samsung", "wd": "WD", "western digital": "WD", "seagate": "Seagate",
    "toshiba": "Toshiba", "sandisk": "SanDisk", "adata": "ADATA", "g.skill": "G.Skill", "gskill": "G.Skill",
    "seasonic": "Seasonic", "be quiet": "be quiet!", "cooler master": "Cooler Master", "nzxt": "NZXT",
    "fractal": "Fractal Design", "lian li": "Lian Li", "noctua": "Noctua", "thermaltake": "Thermaltake",
    "lenovo": "Lenovo", "thinkpad": "Lenovo", "dell": "Dell", "alienware": "Dell", "hp": "HP", "acer": "Acer",
    "apple": "Apple", "macbook": "Apple", "iphone": "Apple", "ipad": "Apple", "huawei": "Huawei",
    "xiaomi": "Xiaomi", "redmi": "Xiaomi", "oneplus": "OnePlus", "google": "Google", "pixel": "Google",
    "razer": "Razer", "logitech": "Logitech", "steelseries": "SteelSeries", "hyperx": "HyperX",
    "lg": "LG", "benq": "BenQ", "aoc": "AOC", "philips": "Philips", "iiyama": "iiyama", "viewsonic": "ViewSonic",
    "eizo": "EIZO", "tp-link": "TP-Link", "mikrotik": "MikroTik", "ubiquiti": "Ubiquiti", "synology": "Synology",
    # photo & video
    "nikon": "Nikon", "nikkor": "Nikon", "canon": "Canon", "sony": "Sony", "fujifilm": "Fujifilm", "fuji": "Fujifilm",
    "panasonic": "Panasonic", "lumix": "Panasonic", "olympus": "Olympus", "om system": "OM System",
    "pentax": "Pentax", "leica": "Leica", "sigma": "Sigma", "tamron": "Tamron", "tokina": "Tokina",
    "samyang": "Samyang", "rokinon": "Samyang", "viltrox": "Viltrox", "zeiss": "Zeiss", "helios": "Helios",
    "yongnuo": "Yongnuo", "godox": "Godox", "gopro": "GoPro", "dji": "DJI", "insta360": "Insta360",
    "blackmagic": "Blackmagic", "manfrotto": "Manfrotto",
    # audio / tv / gaming
    "sennheiser": "Sennheiser", "bose": "Bose", "jbl": "JBL", "beyerdynamic": "beyerdynamic",
    "audio-technica": "Audio-Technica", "shure": "Shure", "rode": "RØDE", "yamaha": "Yamaha", "denon": "Denon",
    "marantz": "Marantz", "pioneer": "Pioneer", "technics": "Technics", "onkyo": "Onkyo", "harman": "Harman Kardon",
    "bang & olufsen": "Bang & Olufsen", "b&o": "Bang & Olufsen", "focusrite": "Focusrite", "akg": "AKG",
    "sonos": "Sonos", "klipsch": "Klipsch", "kef": "KEF", "dali": "DALI", "tcl": "TCL", "hisense": "Hisense",
    "playstation": "Sony", "xbox": "Microsoft", "microsoft": "Microsoft", "nintendo": "Nintendo",
    "valve": "Valve", "steam deck": "Valve", "garmin": "Garmin", "fitbit": "Fitbit",
}
_BRAND_RE = re.compile(r"(?<![a-z0-9])(" + "|".join(sorted((re.escape(b) for b in BRANDS), key=len, reverse=True))
                       + r")(?![a-z0-9])")


def find_brand(t: str) -> str | None:
    m = _BRAND_RE.search(t)
    return BRANDS[m.group(1)] if m else None


def _slug(s: str) -> str:
    s = re.sub(r"[^a-z0-9.+]+", "-", s.lower()).strip("-")
    return re.sub(r"-{2,}", "-", s)


ROMAN = {"2": "ii", "3": "iii", "4": "iv", "5": "v", "ii": "ii", "iii": "iii", "iv": "iv", "v": "v",
         "mark ii": "ii", "mark iii": "iii", "mark iv": "iv", "mk2": "ii", "mk3": "iii", "m2": "ii", "m3": "iii"}

# ---------------------------------------------------------------- GPUs
GPU_VRAM_AMBIGUOUS = {"gtx-1060", "gtx-1050", "rtx-3060", "rtx-3050", "rtx-4060-ti", "rx-580", "rx-570",
                      "rx-480", "rx-470", "rx-5500-xt", "rx-6500-xt", "gt-1030", "gtx-960", "rtx-2060",
                      "rtx-3080", "a770"}
NV_RE = re.compile(r"(?<![a-z0-9])(rtx|gtx|gt)\s*-?\s*(\d{3,4})(?:\s*-?\s*(ti\s*super|super|ti))?(?![0-9])")
AMD_RE = re.compile(r"(?<![a-z0-9])(?:radeon\s*)?(rx)\s*-?\s*(\d{3,4})(?:\s*-?\s*(xtx|xt|gre))?(?![0-9])")
AMD_OLD_RE = re.compile(r"(?<![a-z0-9])(?:radeon\s*)?(r9|r7)\s*-?\s*(\d{3})(x?)(?![0-9])|(?<![a-z])(vega)\s*(56|64)\b")
ARC_RE = re.compile(r"(?<![a-z0-9])(?:intel\s*)?arc\s*-?\s*([ab]\d{3})\b")
VRAM_RE = re.compile(r"(?<![0-9])(\d{1,2})\s*(?:gb|g)\b(?!\s*(?:ddr|ram|ssd|hdd|nvme|operat))")


def match_gpu(t: str) -> Match | None:
    m = NV_RE.search(t)
    if m:
        series, num, suf = m.group(1), m.group(2), (m.group(3) or "").replace(" ", "-")
        if series == "gt" and len(num) == 4 and num[0] in "1234":
            series = "gt" if num.startswith("10") else "gtx"
        model = f"{series}-{num}" + (f"-{suf}" if suf else "")
        name = f"{'GeForce ' if series != 'rtx' else ''}{series.upper()} {num}" + (f" {suf.replace('-', ' ').title()}" if suf else "")
        if series == "rtx":
            name = f"RTX {num}" + (f" {suf.replace('-', ' ').title()}" if suf else "")
        return _with_vram(Match(f"gpu:nvidia:{model}", name, "gpu", "NVIDIA", 0.9), t, model)
    m = AMD_RE.search(t)
    if m and int(m.group(2)) >= 400:
        num, suf = m.group(2), (m.group(3) or "")
        model = f"rx-{num}" + (f"-{suf}" if suf else "")
        return _with_vram(Match(f"gpu:amd:{model}", f"Radeon RX {num}{(' ' + suf.upper()) if suf else ''}", "gpu",
                                "AMD", 0.9), t, model)
    m = AMD_OLD_RE.search(t)
    if m:
        if m.group(4):
            return Match(f"gpu:amd:vega-{m.group(5)}", f"Radeon Vega {m.group(5)}", "gpu", "AMD", 0.85)
        model = f"{m.group(1)}-{m.group(2)}{m.group(3)}"
        return Match(f"gpu:amd:{model}", f"Radeon {model.upper().replace('-', ' ')}", "gpu", "AMD", 0.8)
    m = ARC_RE.search(t)
    if m:
        model = m.group(1)
        return _with_vram(Match(f"gpu:intel:arc-{model}", f"Arc {model.upper()}", "gpu", "Intel", 0.85), t, model)
    return None


def _with_vram(mt: Match, t: str, model: str) -> Match:
    vr = VRAM_RE.search(t)
    if vr:
        mt.variant["vram_gb"] = int(vr.group(1))
        if model in GPU_VRAM_AMBIGUOUS and 2 <= int(vr.group(1)) <= 24:
            mt.key += f"-{vr.group(1)}gb"
            mt.name += f" {vr.group(1)}GB"
    return mt


# ---------------------------------------------------------------- CPUs
INTEL_RE = re.compile(r"(?<![a-z0-9])(?:core\s*)?i([3579])\s*-?\s*(\d{4,5})([a-z]{0,3})(?![a-z0-9])")
ULTRA_RE = re.compile(r"core\s*ultra\s*([579])\s*-?\s*(\d{3}[a-z]{0,2})")
XEON_RE = re.compile(r"xeon\s*(e[3579])?\s*-?\s*(\d{4})\s*(v\d)?")
RYZEN_RE = re.compile(r"ryzen\s*([3579])\s*(?:pro\s*)?(\d{4})\s*(x3d|xt|x|ge|g|h|hs|u)?(?![a-z0-9])")
TR_RE = re.compile(r"threadripper\s*(?:pro\s*)?(\d{4})(wx|x)?")


def match_cpu(t: str) -> Match | None:
    m = ULTRA_RE.search(t)
    if m:
        return Match(f"cpu:intel:ultra-{m.group(1)}-{m.group(2)}", f"Core Ultra {m.group(1)} {m.group(2).upper()}",
                     "cpu", "Intel", 0.85)
    m = INTEL_RE.search(t)
    if m:
        tier, num, suf = m.groups()
        if suf in ("gb", "g") and num.isdigit() and int(num) < 2000:
            return None
        model = f"i{tier}-{num}{suf}"
        return Match(f"cpu:intel:{model}", f"Core {model.upper().replace('I', 'i', 1)}", "cpu", "Intel", 0.9)
    m = RYZEN_RE.search(t)
    if m:
        tier, num, suf = m.group(1), m.group(2), m.group(3) or ""
        return Match(f"cpu:amd:ryzen-{tier}-{num}{suf}", f"Ryzen {tier} {num}{suf.upper()}", "cpu", "AMD", 0.9)
    m = TR_RE.search(t)
    if m:
        return Match(f"cpu:amd:threadripper-{m.group(1)}{m.group(2) or ''}", f"Threadripper {m.group(1)}{(m.group(2) or '').upper()}",
                     "cpu", "AMD", 0.85)
    m = XEON_RE.search(t)
    if m:
        model = "-".join(x for x in (m.group(1), m.group(2), m.group(3)) if x)
        return Match(f"cpu:intel:xeon-{model}", f"Xeon {model.upper()}", "cpu", "Intel", 0.8)
    return None


# ---------------------------------------------------------------- RAM / storage / PSU / board
CAP_RE = re.compile(r"(?<![0-9.])(\d{1,4}(?:[.,]\d)?)\s*(tb|gb)\b")
KIT_RE = re.compile(r"(?<![0-9])(\d)\s*[x×]\s*(\d{1,3})\s*gb")


def _cap_bucket(value: float, unit: str) -> str:
    gb = value * 1000 if unit == "tb" else value
    for limit, label in ((140, "128gb"), (280, "256gb"), (560, "512gb"), (1100, "1tb"), (2200, "2tb"),
                         (4400, "4tb"), (8800, "8tb"), (20000, "16tb")):
        if gb <= limit:
            if gb < 100:
                return f"{int(gb)}gb"
            return label
    return f"{int(gb // 1000)}tb"


def match_ram(t: str) -> Match | None:
    m = re.search(r"ddr\s*([2-5])", t)
    if not m:
        return None
    gen = m.group(1)
    total = None
    k = KIT_RE.search(t)
    if k:
        total = int(k.group(1)) * int(k.group(2))
    else:
        c = re.search(r"(?<![0-9])(4|8|16|32|64|128)\s*gb", t)
        if c:
            total = int(c.group(1))
    if not total:
        return Match(f"ram:ddr{gen}", f"DDR{gen} RAM", "ram", None, 0.4)
    laptop = bool(re.search(r"so-?dimm|portativ|klēpjdator|klepjdator|laptop|notebook|piezimjdator|ноутбук", t))
    form = "-sodimm" if laptop else ""
    return Match(f"ram:ddr{gen}{form}:{total}gb", f"DDR{gen}{' SO-DIMM' if laptop else ''} {total}GB", "ram",
                 find_brand(t), 0.75, variant={"total_gb": total})


def match_storage(t: str) -> Match | None:
    kind = None
    if re.search(r"nvme|m\.2|m2 ", t):
        kind = "nvme"
    elif re.search(r"\bssd\b", t):
        kind = "ssd-sata"
    elif re.search(r"\bhdd\b|cietais disks|cietais disk|жесткий диск|hard drive|\b\d{4} ?rpm", t):
        kind = "hdd"
    if not kind:
        return None
    caps = [_cap_bucket(float(v.replace(",", ".")), u) for v, u in CAP_RE.findall(t)
            if (u == "tb" and float(v.replace(",", ".")) <= 30) or (u == "gb" and 60 <= float(v.replace(",", ".")) <= 8000)]
    if not caps:
        return Match(f"storage:{kind}", f"{kind.upper()} drive", "storage", find_brand(t), 0.35)
    cap = caps[0]
    return Match(f"storage:{kind}:{cap}", f"{ {'nvme': 'NVMe SSD', 'ssd-sata': 'SATA SSD', 'hdd': 'HDD'}[kind]} {cap.upper()}",
                 "storage", find_brand(t), 0.7, variant={"capacity": cap})


def match_psu(t: str) -> Match | None:
    if not re.search(r"barosanas bloks|barošanas bloks|\bpsu\b|power supply|блок питания|\bbp\b", t):
        return None
    m = re.search(r"(?<![0-9])(\d{3,4})\s*w\b", t)
    if not m or not (250 <= int(m.group(1)) <= 2000):
        return Match("psu:unknown", "PC power supply", "psu", find_brand(t), 0.35)
    w = int(m.group(1))
    w = int(round(w / 50.0) * 50)
    tier = ""
    if re.search(r"80\s*\+?\s*(plus\s*)?(gold|platinum|titanium)", t):
        tier = "-gold+"
    return Match(f"psu:{w}w{tier}", f"PSU {w}W{' 80+ Gold or better' if tier else ''}", "psu", find_brand(t), 0.65)


def match_motherboard(t: str) -> Match | None:
    if not re.search(r"motherboard|matesplat|sistemplat|mātesplat|материнск|\bmobo\b|\bmb\b|plate", t):
        return None
    m = re.search(r"(?<![a-z0-9])([abhxzq])\s?(\d{2,3})([a-z]?)(?![0-9])", t)
    if not m:
        return Match("motherboard:unknown", "Motherboard", "motherboard", find_brand(t), 0.3)
    chip = f"{m.group(1)}{m.group(2)}{m.group(3)}"
    return Match(f"motherboard:{chip}", f"{chip.upper()} motherboard", "motherboard", find_brand(t), 0.6)


# ---------------------------------------------------------------- cameras / lenses
CAMERA_PATTERNS: list[tuple[str, re.Pattern, str]] = [
    ("Nikon", re.compile(r"(?:nikon\s*)?(?<![a-z0-9])(d\s?\d{2,4}[sxh]?)(?![0-9])"), "nikon"),
    ("Nikon", re.compile(r"nikon\s*(z\s?\d{1,2}(?:\s*(?:ii|2))?|zf|z\s?fc|z\s?50|coolpix\s*[a-z]?\d{2,4})"), "nikon"),
    ("Canon", re.compile(r"(?:canon\s*)?(?:eos\s*)(\d{1,4}d(?:\s*(?:mark|mk)?\s*(?:ii|iii|iv|2|3|4))?|r\d{0,2}|rp|m\d{1,3})(?![a-z0-9])"), "canon"),
    ("Canon", re.compile(r"canon\s*(\d{1,4}d(?:\s*(?:mark|mk)?\s*(?:ii|iii|iv|2|3|4))?)(?![a-z0-9])"), "canon"),
    ("Canon", re.compile(r"canon\s*(?:eos\s*)?(r\d{1,2}|rp|r50|r100|g7\s*x(?:\s*mark\s*(?:ii|iii))?|powershot\s*\w+)"), "canon"),
    ("Sony", re.compile(r"(?:sony\s*)?(?:alpha\s*)?(?<![a-z0-9])(a7\s?(?:r|s|c)?\s?(?:ii|iii|iv|v|2|3|4|5|m2|m3|m4)?|a6\d{3}|a5\d{3}|a3\d{3}|a9\s?(?:ii|iii)?|a1|zv-?e?\d{1,2}(?:\s?ii)?|rx100\s?(?:m?\d|[ivx]+)?|nex-?\d[a-z]?)(?![a-z0-9])"), "sony"),
    ("Fujifilm", re.compile(r"(?:fuji(?:film)?\s*)?(?<![a-z0-9])(x-?t\d{1,2}|x-?s\d{1,2}|x-?e\d|x-?h\d[s]?|x-?pro\d|x100[a-z]{0,2}|x-?a\d|gfx\s?\d{2,3}[a-z]{0,2})(?![a-z0-9])"), "fujifilm"),
    ("Panasonic", re.compile(r"(?:panasonic\s*|lumix\s*)+(dc-|dmc-)?(gh\d[s]?|g\d{1,3}|gx\d{1,3}|s\d[hr]?|fz\d{2,4}|lx\d{2,3}|tz\d{2,3})(?![a-z0-9])"), "panasonic"),
    ("Olympus", re.compile(r"(?:olympus|om-?d|om system)\s*(?:om-?d\s*)?(e-?m\d{1,2}(?:\s*(?:mark|mk)?\s*(?:ii|iii|iv|2|3|4))?|e-?pl\d{1,2}|om-?\d)"), "olympus"),
    ("Pentax", re.compile(r"pentax\s*(k-?\d{1,2}[a-z]{0,2}(?:\s*ii)?|kp|k-?\d{1,4})"), "pentax"),
    ("GoPro", re.compile(r"gopro\s*(?:hero\s*)?(\d{1,2}(?:\s*black|\s*silver)?|max)"), "gopro"),
    ("DJI", re.compile(r"dji\s*(mini\s*\d?\s*(?:pro|se)?|air\s*\d?s?|mavic\s*\d?\s*(?:pro|air|mini|classic)?|avata\s*\d?|osmo\s*(?:pocket|action)\s*\d?|pocket\s*\d|action\s*\d|ronin\s*\w*|rs\s?\d)"), "dji"),
]


def _norm_mark(model: str) -> str:
    m = re.sub(r"\s*(?:mark|mk)\s*", " ", model)
    m = re.sub(r"\s+(ii|iii|iv|2|3|4)$", lambda x: "-" + ROMAN.get(x.group(1), x.group(1)), m)
    m = re.sub(r"(a7[rsc]?)(m?)([2-5])$", lambda x: x.group(1) + "-" + ROMAN.get(x.group(3), x.group(3)), m)
    m = re.sub(r"(a7[rsc]?)(ii|iii|iv|v)$", r"\1-\2", m)
    return _slug(m.replace(" ", ""))if "-" not in m else _slug(m.replace(" ", ""))


def match_camera(t: str, photo_context: bool) -> Match | None:
    for brand, rx, slug in CAMERA_PATTERNS:
        m = rx.search(t)
        if not m:
            continue
        model = m.group(m.lastindex or 1) if m.lastindex else m.group(0)
        model = (m.group(2) if brand == "Panasonic" else m.group(1)).strip()
        if brand == "Nikon" and model.startswith("d") and "nikon" not in t and not photo_context:
            continue
        if brand in ("Sony", "Fujifilm") and slug not in t and not photo_context:
            continue
        if brand == "Nikon" and model.startswith("d") and len(re.sub(r"\D", "", model)) < 2:
            continue
        key_model = _norm_mark(model)
        category = "drone" if brand in ("DJI", "GoPro") else "camera"
        disp = re.sub(r"MARK", "Mark", model.upper()) if len(model) > 8 else model.upper().replace(" ", "")
        return Match(f"{category}:{slug}:{key_model}", f"{brand} {disp}", category, brand, 0.85)
    return None


# the aperture only counts when written as f/1.8, f1.8, f 1.8 or 1:1.8 - a bare number after "mm" (fan "140mm 1500 rpm") is not one
LENS_RE = re.compile(
    r"(?<![0-9])(\d{1,3}(?:[.,]\d)?(?:\s*-\s*\d{1,3})?)\s*mm(?:\s*[,/]?\s*(?:f\s*/?\s*|1\s*:\s*)(\d{1,2}(?:[.,]\d{1,2})?)(?:\s*-\s*(\d{1,2}(?:[.,]\d)?))?)?")
# PC cooling / case hardware: never a lens, whatever "mm" it mentions
NOT_LENS = re.compile(r"\baio\b|cooler|\bcooling\b|radiator|radiators|kraken|nzxt|\bfans?\b|ventilator|dzesetaj|dzesesanas|sidrum|liquid|\bcpu\b|heatsink|pump|"
                      r"\bsocket\b|\blga ?\d|\bam[45]\b|corsair|noctua|be quiet|arctic|deepcool|thermalright|cooler master|\brpm\b|\bargb\b|\brgb\b|\bpwm\b|кулер|охлажден|радиатор|вентилятор")
LENS_CONTEXT = re.compile(r"objektiv|объектив|\blens(?:es)?\b|nikkor|\bef-?s?\b|\brf\b|\bfe\b|\bdx\b|\busm\b|\bstm\b|\bf ?/ ?\d|\b1 ?: ?\d(?:\.\d)?\b|canon|nikon|sony|sigma|tamron|samyang|fuji|olympus|panasonic|pentax|leica|zeiss|\bkamer|camera|fotoaparat|fotoapar|\bdslr\b|mirrorless|bajonet|mount")
LENS_BRANDS = ("sigma", "tamron", "tokina", "samyang", "viltrox", "zeiss", "helios", "nikkor", "nikon", "canon",
               "sony", "fujinon", "fujifilm", "fuji", "olympus", "panasonic", "pentax", "yongnuo", "meike", "7artisans",
               "ttartisan", "laowa", "voigtlander", "jupiter", "industar", "leica", "lumix", "mir")


def match_lens(t: str, lens_context: bool) -> Match | None:
    m = LENS_RE.search(t)
    if not m:
        return None
    if NOT_LENS.search(t):
        return None
    focal = m.group(1).replace(" ", "").replace(",", ".")
    ap = (m.group(2) or "").replace(",", ".")
    if not ap and LENS_CONTEXT.search(t):
        bare = re.search(r"mm\s*[,/]?\s*(\d{1,2}\.\d{1,2})(?![\d.]|\s*(?:mm|gb|tb|rpm|w\b|hz|cm|kg))", t)   # "Sigma 35mm 1.4 Art": only with lens words around
        if bare:
            ap = bare.group(1)
    # require an aperture or a lens word to avoid matching "35mm film" etc.
    lens_word = LENS_CONTEXT.search(t)
    if not lens_word and not lens_context:
        return None
    try:
        first = float(focal.split("-")[0])
        if not (4 <= first <= 1200):
            return None
        if ap and not (0.7 <= float(ap) <= 32):
            ap = ""
    except ValueError:
        return None
    brand = None
    for b in LENS_BRANDS:
        if re.search(rf"(?<![a-z]){b}(?![a-z])", t):
            brand = {"nikkor": "nikon", "fujinon": "fujifilm", "fuji": "fujifilm", "lumix": "panasonic"}.get(b, b)
            break
    if not brand:
        return Match(f"lens:generic:{focal}" + (f"-f{ap}" if ap else ""), f"{focal}mm" + (f" f/{ap}" if ap else "") + " lens",
                     "lens", None, 0.4)
    key = f"lens:{brand}:{focal}" + (f"-f{ap}" if ap else "")
    for tag, rx in (("art", r"\bart\b"), ("gm", r"\bg ?master\b|\bgm\b"), ("l", r"\b\d+l\b|\bf/?\d(?:\.\d)?l\b| l is| l usm"),
                    ("macro", r"macro|makro")):
        if re.search(rx, t):
            key += f"-{tag}"
    # the same focal length/aperture exists as very different lenses per mount and generation (Canon FD vs EF vs RF 50mm f/1.4)
    mount = None
    for tag, rx in (("rf", r"\brf\b"), ("ef-s", r"\bef-s\b"), ("ef", r"\bef\b"), ("fd", r"\bfd\b|\bnew fd\b|\bfdn\b"),
                    ("af-s", r"\baf-s\b"), ("af-d", r"\baf-d\b"), ("ai", r"\bai-?s?\b(?!r)"), ("z", r"\bnikkor z\b|\bz mount\b|\bz-mount\b"),
                    ("fe", r"\bfe\b"), ("e", r"\be-mount\b|\be mount\b"), ("m42", r"\bm42\b"), ("x", r"\bx-mount\b|\bxf\b"),
                    ("mft", r"\bm4/3\b|\bmicro four thirds\b|\bmft\b")):
        if re.search(rx, t):
            mount = tag
            break
    if mount:
        key += f"-{mount}"
    name = f"{brand.title()} {focal}mm" + (f" f/{ap}" if ap else "") + (f" {mount.upper()}" if mount else "")
    return Match(key, name, "lens", BRANDS.get(brand, brand.title()), (0.75 if ap else 0.55) - (0.0 if mount else 0.15))


# ---------------------------------------------------------------- consoles / phones / tablets / laptops / misc
SIMPLE_PATTERNS: list[tuple[str, str, str, str | None, float]] = [
    # (regex, key, name, brand, confidence)  — evaluated in order, first match wins
    (r"steam\s*deck\s*oled", "console:valve:steam-deck-oled", "Steam Deck OLED", "Valve", 0.9),
    (r"steam\s*deck", "console:valve:steam-deck", "Steam Deck", "Valve", 0.85),
    (r"(?:ps\s?5|playstation\s*5)\s*pro", "console:sony:ps5-pro", "PlayStation 5 Pro", "Sony", 0.9),
    (r"(?:ps\s?5|playstation\s*5)\s*(?:slim\s*)?digital", "console:sony:ps5-digital", "PlayStation 5 Digital", "Sony", 0.85),
    (r"(?:ps\s?5|playstation\s*5)", "console:sony:ps5", "PlayStation 5", "Sony", 0.8),
    (r"(?:ps\s?4|playstation\s*4)\s*pro", "console:sony:ps4-pro", "PlayStation 4 Pro", "Sony", 0.85),
    (r"(?:ps\s?4|playstation\s*4)", "console:sony:ps4", "PlayStation 4", "Sony", 0.75),
    (r"(?:ps\s?3|playstation\s*3)", "console:sony:ps3", "PlayStation 3", "Sony", 0.7),
    (r"(?:ps\s?vita|playstation\s*vita)", "console:sony:ps-vita", "PS Vita", "Sony", 0.8),
    (r"\bpsp\b", "console:sony:psp", "PSP", "Sony", 0.7),
    (r"xbox\s*series\s*x", "console:microsoft:xbox-series-x", "Xbox Series X", "Microsoft", 0.9),
    (r"xbox\s*series\s*s", "console:microsoft:xbox-series-s", "Xbox Series S", "Microsoft", 0.9),
    (r"xbox\s*one\s*x", "console:microsoft:xbox-one-x", "Xbox One X", "Microsoft", 0.85),
    (r"xbox\s*one", "console:microsoft:xbox-one", "Xbox One", "Microsoft", 0.75),
    (r"xbox\s*360", "console:microsoft:xbox-360", "Xbox 360", "Microsoft", 0.75),
    (r"switch\s*2\b", "console:nintendo:switch-2", "Nintendo Switch 2", "Nintendo", 0.85),
    (r"switch\s*oled|oled\s*switch", "console:nintendo:switch-oled", "Switch OLED", "Nintendo", 0.9),
    (r"switch\s*lite", "console:nintendo:switch-lite", "Switch Lite", "Nintendo", 0.9),
    (r"nintendo\s*switch|\bswitch\b.*(?:joy-?con|nintendo)", "console:nintendo:switch", "Nintendo Switch", "Nintendo", 0.8),
    (r"meta\s*quest\s*3s|quest\s*3s", "console:meta:quest-3s", "Meta Quest 3S", "Meta", 0.85),
    (r"(?:meta|oculus)\s*quest\s*3|quest\s*3\b", "console:meta:quest-3", "Meta Quest 3", "Meta", 0.85),
    (r"(?:meta|oculus)\s*quest\s*2|quest\s*2\b", "console:meta:quest-2", "Meta Quest 2", "Meta", 0.85),
    # Apple computers
    (r"macbook\s*pro\s*(1[3-6])?.{0,12}?\bm([1-5])\s*(pro|max)?", "laptop:apple:macbook-pro-m{2}{-3}", "MacBook Pro M{2}{-3}", "Apple", 0.75),
    (r"macbook\s*air.{0,12}?\bm([1-5])", "laptop:apple:macbook-air-m{1}", "MacBook Air M{1}", "Apple", 0.8),
    (r"mac\s*mini.{0,12}?\bm([1-5])\s*(pro)?", "pc:apple:mac-mini-m{1}{-2}", "Mac mini M{1}{-2}", "Apple", 0.8),
    (r"mac\s*studio", "pc:apple:mac-studio", "Mac Studio", "Apple", 0.6),
    (r"macbook\s*pro", "laptop:apple:macbook-pro-intel", "MacBook Pro (Intel)", "Apple", 0.4),
    (r"macbook\s*air", "laptop:apple:macbook-air-intel", "MacBook Air (Intel)", "Apple", 0.4),
    # phones
    (r"iphone\s*(1[0-9]|[6-9]|x[rs]?|se)\s*(pro\s*max|pro|plus|max|mini|e)?", "phone:apple:iphone-{1}{-2}", "iPhone{-1}{-2}", "Apple", 0.85),
    (r"(?:galaxy\s*)?(s2[0-6]|s1\d)\s*(ultra|plus|\+|fe)?(?![0-9])", "phone:samsung:galaxy-{1}{-2}", "Galaxy{-1}{-2}", "Samsung", 0.75),
    (r"galaxy\s*(z\s*fold|z\s*flip|fold|flip)\s*(\d)", "phone:samsung:galaxy-{1}{-2}", "Galaxy{-1}{-2}", "Samsung", 0.85),
    (r"galaxy\s*(a\d{2})", "phone:samsung:galaxy-{1}", "Galaxy{-1}", "Samsung", 0.75),
    (r"pixel\s*(\d{1,2})\s*(pro\s*xl|pro\s*fold|pro|a|xl)?", "phone:google:pixel-{1}{-2}", "Pixel{-1}{-2}", "Google", 0.8),
    (r"oneplus\s*(\d{1,2}[tr]?)\s*(pro)?", "phone:oneplus:oneplus-{1}{-2}", "OnePlus{-1}{-2}", "OnePlus", 0.75),
    # tablets & wearables
    (r"ipad\s*(pro|air|mini)?\s*(?:(\d{1,2})(?:\.\d)?\s*(?:''|\"|collu|inch|in)?)?.{0,15}?\b(m[1-5])", "tablet:apple:ipad-{1}-{3}", "iPad {1} {3}", "Apple", 0.75),
    # iPads: the generation decides the price (an iPad 6th gen and a 10th gen are €120 apart), so use it when the ad gives it
    (r"ipad\s*(pro|air|mini)?\W{0,3}(?:\d{1,2}(?:[.,]\d)?\s*(?:''|\"|inch|in|collu)?\W{0,3})?.{0,12}?\b(\d{1,2})\s*(?:th|st|nd|rd)?\.?\s*(?:gen\b|gen\.|paaud|generation)",
     "tablet:apple:ipad-{1}-g{2}", "iPad{-1} gen {2}", "Apple", 0.7),
    (r"ipad\s*(mini|air)\s*(\d)\b(?!\s*(?:gb|tb))", "tablet:apple:ipad-{1}-g{2}", "iPad {1} {2}", "Apple", 0.7),
    (r"ipad\s*(\d{1,2})\b(?![.,]\d)(?!\s*(?:gb|tb|inch|''|\"|collu|in\b|mm))", "tablet:apple:ipad-g{1}", "iPad gen {1}", "Apple", 0.6),
    (r"ipad\s*(pro|air|mini)", "tablet:apple:ipad-{1}", "iPad{-1}", "Apple", 0.5),
    (r"\bipad\b", "tablet:apple:ipad", "iPad", "Apple", 0.4),
    (r"galaxy\s*tab\s*(s\d{1,2})\s*(ultra|\+|plus|fe)?", "tablet:samsung:galaxy-tab-{1}{-2}", "Galaxy Tab{-1}{-2}", "Samsung", 0.75),
    (r"apple\s*watch\s*(ultra\s*\d?|series\s*\d{1,2}|se)", "wearable:apple:watch-{1}", "Apple Watch{-1}", "Apple", 0.75),
    (r"airpods\s*(pro\s*\d?|max|\d)?", "headphones_mic:apple:airpods-{1}", "AirPods{-1}", "Apple", 0.7),
    # headphones / audio
    (r"wh-?1000\s*x?m\s*(\d)", "headphones_mic:sony:wh-1000xm{1}", "Sony WH-1000XM{1}", "Sony", 0.85),
    (r"wf-?1000\s*x?m\s*(\d)", "headphones_mic:sony:wf-1000xm{1}", "Sony WF-1000XM{1}", "Sony", 0.85),
    (r"bose\s*(?:quiet\s*comfort|qc)\s*(\d{2}|ultra|\d)", "headphones_mic:bose:qc-{1}", "Bose QC{-1}", "Bose", 0.8),
    (r"sennheiser\s*(hd\s?\d{3}\w*|momentum\s*\d?)", "headphones_mic:sennheiser:{1}", "Sennheiser{-1}", "Sennheiser", 0.8),
    (r"(?:shure\s*)?sm\s?(7b|58|57)", "headphones_mic:shure:sm{1}", "Shure SM{1}", "Shure", 0.75),
    (r"(?:rode|røde)\s*(nt-?usb|nt1|nt2|podmic|procaster|videomic\s*\w*|wireless\s*go\s*\w*)", "headphones_mic:rode:{1}", "RØDE{-1}", "RØDE", 0.75),
    # monitors / TVs handled separately; laptops lines
    (r"thinkpad\s*([txpelw]\d{2,3}[sp]?)(?:\s*gen\s*(\d))?", "laptop:lenovo:thinkpad-{1}{-2}", "ThinkPad{-1}{-2}", "Lenovo", 0.75),
    (r"thinkpad\s*x1\s*carbon(?:\s*gen\s*(\d+))?", "laptop:lenovo:x1-carbon-{1}", "ThinkPad X1 Carbon{-1}", "Lenovo", 0.75),
    (r"legion\s*(5|7|pro\s*5|pro\s*7|slim\s*5)", "laptop:lenovo:legion-{1}", "Lenovo Legion{-1}", "Lenovo", 0.5),
    (r"xps\s*(13|15|17)\s*(\d{4})?", "laptop:dell:xps-{1}{-2}", "Dell XPS{-1}{-2}", "Dell", 0.6),
    (r"latitude\s*(\d{4})", "laptop:dell:latitude-{1}", "Dell Latitude{-1}", "Dell", 0.7),
    (r"elitebook\s*(\d{3,4})\s*(g\d{1,2})?", "laptop:hp:elitebook-{1}{-2}", "HP EliteBook{-1}{-2}", "HP", 0.7),
    (r"probook\s*(\d{3,4})\s*(g\d{1,2})?", "laptop:hp:probook-{1}{-2}", "HP ProBook{-1}{-2}", "HP", 0.65),
    (r"elitebook\s*(g\d{1,2})\b", "laptop:hp:elitebook-{1}", "HP EliteBook{-1}", "HP", 0.5),
    (r"probook\s*(g\d{1,2})\b", "laptop:hp:probook-{1}", "HP ProBook{-1}", "HP", 0.5),
    (r"(?:rog\s*)?zephyrus\s*(g14|g15|g16|m16)", "laptop:asus:zephyrus-{1}", "ASUS Zephyrus{-1}", "ASUS", 0.6),
]
_SIMPLE = [(re.compile(rx), k, n, b, c) for rx, k, n, b, c in SIMPLE_PATTERNS]


def match_simple(t: str) -> Match | None:
    for rx, key, name, brand, conf in _SIMPLE:
        m = rx.search(t)
        if not m:
            continue
        groups = [""] + [(g or "") for g in m.groups()]

        def fill(tpl: str, joiner: str) -> str:
            # {n} inserts group n; {-n} inserts "-value" (key) / " value" (name) only when present
            def rep(x):
                dash, idx = x.group(1), int(x.group(2))
                v = groups[idx] if idx < len(groups) else ""
                v = re.sub(r"(?<=[a-z])\s+(?=\d)", "", v.strip())
                v = re.sub(r"\s+", joiner, v)
                return (joiner + v) if (dash and v) else v
            return re.sub(r"\{(-?)(\d)\}", rep, tpl)

        k = fill(key, "-").replace("+", "plus")
        parts = k.split(":")
        k = ":".join([parts[0]] + [_slug(part) for part in parts[1:]])
        nm = re.sub(r"\s+", " ", fill(name, " ")).strip()
        nm = " ".join(w if any(ch.isupper() for ch in w) else (w.upper() if any(ch.isdigit() for ch in w) else w.title()) for w in nm.split())
        cat = key.split(":")[0]
        return Match(k, nm, cat, brand, conf)
    return None


def match_display(t: str, category: str) -> Match | None:
    m = re.search(r"(?<![0-9])(\d{2}(?:[.,]\d)?)\s*(?:''|\"|”|collu|colli|coll|inch|in\b|дюйм|“)", t)
    if not m:
        m = re.search(r"(?<![0-9])(1[5-9]|2\d|3\d|4\d|5\d|6\d|7\d|8\d)\s*(?:''|\")", t)
    if not m:
        return None
    size = int(round(float(m.group(1).replace(",", "."))))
    if category == "monitor" and 15 <= size <= 57:
        hz = re.search(r"(\d{2,3})\s*hz", t)
        hz_v = int(hz.group(1)) if hz else 60
        tier = "high-hz" if hz_v >= 120 else "60hz"
        res = "4k" if re.search(r"\b4k\b|3840|uhd", t) else ("1440p" if re.search(r"1440|2k|qhd|2560", t) else "")
        key = f"monitor:{size}in-{tier}" + (f"-{res}" if res else "")
        return Match(key, f'{size}" monitor {hz_v if hz else ""}{"Hz" if hz else ""} {res}'.strip(), "monitor",
                     find_brand(t), 0.5)
    if category == "tv" and 19 <= size <= 100:
        panel = "oled" if "oled" in t else ("qled" if "qled" in t else ("4k" if re.search(r"\b4k\b|uhd|3840", t) else ""))
        return Match(f"tv:{size}in" + (f"-{panel}" if panel else ""), f'{size}" TV {panel.upper()}'.strip(), "tv",
                     find_brand(t), 0.5)
    return None


MODEL_TOKEN = re.compile(r"(?<![a-z0-9])([a-z]{1,5}-?\d{2,5}[a-z]{0,4}(?:-?[a-z0-9]{1,4})?)(?![a-z0-9])")


def loose_match(t: str, category: str) -> Match | None:
    brand = find_brand(t)
    if not brand:
        return None
    for tok in MODEL_TOKEN.findall(t):
        if re.fullmatch(r"(?:\d+|gb\d+|ddr\d|usb\d|hdmi\d|x\d|\d+gb|\d+tb|\d+w|\d+mm|\d+hz|19\d\d|20\d\d)", tok):
            continue
        if re.fullmatch(r"(?:dn|sia|nr|pvn|lv)-?\d+", tok):
            continue
        return Match(f"loose:{category}:{_slug(brand)}:{_slug(tok)}", f"{brand} {tok.upper()}", category, brand, 0.35)
    return None


# ---------------------------------------------------------------- main entry

def identify(title: str, description: str = "", category: str = "other") -> Match | None:
    """Identify the product in an ad. ``category`` is the category implied by the SS.lv path."""
    head = norm(title)
    full = norm(f"{title} {description[:600]}")
    photo_ctx = category in ("camera", "lens", "camera_accessory", "film_camera", "drone")

    def first(t: str) -> Match | None:
        if category in ("pc", "laptop"):
            mt = match_simple(t)
            if mt and mt.category in ("pc", "laptop"):
                return mt
            return None  # PCs/laptops are valued from components (see valuation)
        if category == "lens":
            return match_lens(t, True) or match_camera(t, True)
        if category in ("camera", "film_camera", "drone"):
            cam = match_camera(t, True)
            if cam:
                lens = match_lens(t, False)
                if lens:
                    cam.components = [lens]
                return cam
            return match_lens(t, False)
        if category in ("monitor", "tv"):
            return match_simple(t) if category == "tv" and re.search(r"switch|ps\d|xbox", t) else match_display(t, category)
        return (match_gpu(t) or match_cpu(t) or match_simple(t) or match_ram(t) or match_storage(t)
                or match_psu(t) or match_motherboard(t) or match_camera(t, photo_ctx) or match_lens(t, photo_ctx)
                or match_display(t, category))

    m = first(head) or first(full)
    if m is None and category not in ("pc", "laptop"):
        m = loose_match(head, category) or loose_match(full, category)
    if m and not m.brand:
        m.brand = find_brand(full)
    from .generations import refine
    return refine(m, title, description or "")


def pc_components(title: str, description: str = "") -> list[Match]:
    """Components found in a PC / laptop / bundle ad — used for component-sum valuation."""
    t = norm(f"{title} {description}")
    comps: list[Match] = []
    for fn in (match_gpu, match_cpu, match_ram, match_storage, match_psu):
        mt = fn(t)
        if mt and mt.confidence >= 0.5:
            comps.append(mt)
    return comps
