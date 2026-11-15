"""Every kind of content on the site, described once.

The admin dashboard builds its forms from this file and the server validates saves against it, so adding a field
(or a whole new content type) is one edit here plus, if it should be shown, one line in a template.

Field kinds: text, textarea, markdown, code, select, bool, number, url, date, tags, list, rows, image, images.
  tags / list -> list of strings          rows -> list of [left, right] pairs (edited as "left | right" lines)
  image       -> {"src", "thumb", "w", "h", "exif"} or None      images -> list of those
"""
from __future__ import annotations

import re
from datetime import date

PROJECT_STATUS = ["Planning", "In Development", "Testing", "Completed", "Archived"]
SALE_STATUS = ["Available", "Reserved", "Sold", "Archived"]
CONDITIONS = ["New", "Like new", "Very good", "Good", "Fair", "For parts"]
LAB_CATEGORIES = ["Electronics repair", "Soldering", "PC hardware", "GPU testing", "Computer upgrades",
                  "Hardware troubleshooting", "Component identification", "Technical experiment"]
SHOP_CATEGORIES = ["PC components", "Electronics", "Gaming accessories", "Cameras and photography", "Games", "Books and vinyl", "Miscellaneous"]
GEAR_GROUPS = ["PC", "Camera", "Peripherals", "Electronics tools", "Other"]
NOW_SECTIONS = ["Working on", "Learning", "Experimenting with", "Next few weeks", "Long-term"]
ROADMAP_STATES = ["Planned", "In progress", "Completed"]
CURRENCIES = ["EUR", "USD", "GBP"]


def f(key, kind, label, **kw):
    return {"key": key, "kind": kind, "label": label, **kw}


TYPES: dict[str, dict] = {
    "project": {
        "label": "Projects", "one": "project", "title": "title", "url": "/projects/{slug}", "list": ["status", "featured"],
        "fields": [
            f("title", "text", "Title", required=True),
            f("summary", "textarea", "One or two sentences", help="Shown on cards and in search results.", rows=2),
            f("status", "select", "Status", options=PROJECT_STATUS, default="Planning"),
            f("featured", "bool", "Feature on the home page"),
            f("hero", "image", "Main image"),
            f("description", "markdown", "Description"),
            f("purpose", "textarea", "Why it exists", rows=3),
            f("features", "list", "Features", help="One per line."),
            f("planned", "list", "Planned features", help="One per line."),
            f("technologies", "tags", "Technologies", help="Separate with commas."),
            f("screenshots", "images", "Screenshots"),
            f("timeline", "rows", "Timeline", help="One per line: 2026-11 | What happened"),
            f("changelog", "rows", "Changelog", help="One per line: date or version | What changed"),
            f("learned", "markdown", "What I learned"),
            f("future", "markdown", "Future plans"),
            f("github", "url", "GitHub link"),
            f("demo", "url", "Live link"),
        ],
    },
    "experiment": {
        "label": "Tech Lab", "one": "experiment", "title": "title", "url": "/lab/{slug}", "list": ["category", "outcome"],
        "fields": [
            f("title", "text", "Title", required=True),
            f("category", "select", "Category", options=LAB_CATEGORIES, default=LAB_CATEGORIES[0]),
            f("date", "date", "Date"),
            f("outcome", "select", "Result", options=["In progress", "Success", "Partial", "Failed"], default="In progress"),
            f("difficulty", "number", "Difficulty (1 to 10)", min=1, max=10, step=1, default=5),
            f("description", "markdown", "What this was about"),
            f("tools", "list", "Tools used", help="One per line."),
            f("photos", "images", "Photos"),
            f("steps", "list", "Steps taken", help="One per line, in order."),
            f("results", "markdown", "Results"),
            f("problems", "markdown", "Problems I ran into"),
            f("lessons", "markdown", "Lessons learned"),
        ],
    },
    "gear": {
        "label": "Equipment", "one": "item", "title": "name", "url": "/lab#equipment", "list": ["group"],
        "fields": [
            f("name", "text", "Name", required=True),
            f("group", "select", "Group", options=GEAR_GROUPS, default="PC"),
            f("details", "text", "Details", help="For example: 16 GB DDR4, or 50mm f/1.8"),
        ],
    },
    "photo": {
        "label": "Photography", "one": "photo", "title": "title", "url": "/photos#p-{slug}", "list": ["album", "featured"],
        "fields": [
            f("image", "image", "Photo", required=True, quality="photo"),
            f("title", "text", "Title"),
            f("caption", "textarea", "Description", rows=2),
            f("album", "text", "Album or category", help="Photos with the same album are grouped."),
            f("taken", "date", "Date taken"),
            f("camera", "text", "Camera"),
            f("lens", "text", "Lens"),
            f("settings", "text", "Settings", help="For example: 35mm, f/2.8, 1/250s, ISO 200. Filled in from the file when it has the data."),
            f("before", "image", "Unedited version", help="Optional. Adds a before/after slider.", quality="photo"),
            f("featured", "bool", "Featured"),
        ],
    },
    "product": {
        "label": "Shop", "one": "product", "title": "name", "url": "/shop/{slug}", "list": ["status", "price", "featured"],
        "fields": [
            f("name", "text", "Name", required=True),
            f("price", "number", "Price", min=0, step=0.01),
            f("currency", "select", "Currency", options=CURRENCIES, default="EUR"),
            f("status", "select", "Availability", options=SALE_STATUS, default="Available"),
            f("condition", "select", "Condition", options=CONDITIONS, default="Good"),
            f("category", "select", "Category", options=SHOP_CATEGORIES, default="Miscellaneous"),
            f("featured", "bool", "Featured"),
            f("short", "textarea", "Short description", rows=2),
            f("images", "images", "Photos"),
            f("description", "markdown", "Full description"),
            f("specs", "rows", "Specifications", help="One per line: Name | Value"),
            f("buy_url", "url", "Where to buy it", help="Link to the marketplace listing, if there is one. Without it visitors get the inquiry form."),
        ],
    },
    "listing": {
        "label": "My Listings", "one": "listing", "title": "title", "url": "/listings/{slug}", "list": ["platform", "status", "price"],
        "fields": [
            f("title", "text", "Title", required=True),
            f("platform", "select", "Marketplace", options=["Vinted", "eBay"], default="Vinted"),
            f("url", "url", "Link to the original listing", required=True),
            f("price", "number", "Price", min=0, step=0.01),
            f("currency", "select", "Currency", options=CURRENCIES, default="EUR"),
            f("status", "select", "Availability", options=SALE_STATUS, default="Available"),
            f("condition", "select", "Condition", options=CONDITIONS, default="Good"),
            f("category", "select", "Category", options=SHOP_CATEGORIES, default="Miscellaneous"),
            f("date", "date", "Date added", default="today"),
            f("images", "images", "Photos"),
            f("description", "markdown", "Description"),
        ],
    },
    "post": {
        "label": "Devlog", "one": "article", "title": "title", "url": "/devlog/{slug}", "list": ["category", "date"], "draft_first": True,
        "fields": [
            f("title", "text", "Title", required=True),
            f("date", "date", "Publication date", default="today"),
            f("category", "text", "Category", help="For example: Project update, Hardware, Photography"),
            f("tags", "tags", "Tags", help="Separate with commas."),
            f("cover", "image", "Cover image"),
            f("excerpt", "textarea", "Short summary", rows=2),
            f("content", "markdown", "Article", tall=True),
            f("projects", "tags", "Related projects", help="Project titles, separated with commas."),
        ],
    },
    "toy": {
        "label": "Playground", "one": "experiment", "title": "title", "url": "/playground/{slug}", "list": [],
        "fields": [
            f("title", "text", "Title", required=True),
            f("summary", "textarea", "What it does", rows=2),
            f("html", "code", "HTML, CSS and JavaScript", help="A complete small page. It runs in its own sandboxed frame, so it cannot touch the rest of the site.", tall=True),
        ],
    },
    "now": {
        "label": "Now", "one": "entry", "title": "text", "url": "/now", "list": ["section"],
        "fields": [
            f("text", "text", "What", required=True),
            f("section", "select", "Section", options=NOW_SECTIONS, default=NOW_SECTIONS[0]),
            f("note", "textarea", "Details", rows=2),
        ],
    },
    "roadmap": {
        "label": "Roadmap", "one": "entry", "title": "title", "url": "/now#roadmap", "list": ["state"],
        "fields": [
            f("title", "text", "What", required=True),
            f("state", "select", "State", options=ROADMAP_STATES, default="Planned"),
            f("note", "textarea", "Details", rows=2),
        ],
    },
    "message": {
        "label": "Messages", "one": "message", "title": "name", "url": "", "list": [], "private": True, "readonly": True,
        "fields": [
            f("name", "text", "From"), f("email", "text", "Email"), f("about", "text", "About"),
            f("message", "textarea", "Message"), f("read", "bool", "Read"),
        ],
    },
}

PAGES = [  # main navigation, in order; the key is what Settings -> hidden pages uses
    ("home", "Home", "/"), ("projects", "Projects", "/projects"), ("lab", "Tech Lab", "/lab"),
    ("photos", "Photography", "/photos"), ("shop", "Shop", "/shop"), ("listings", "My Listings", "/listings"),
    ("devlog", "Devlog", "/devlog"), ("about", "About", "/about"),
]
EXTRA_PAGES = [("now", "Now", "/now"), ("playground", "Playground", "/playground")]
STATS = [("projects", "Projects"), ("current", "In development"), ("completed", "Completed projects"), ("photos", "Photographs"),
         ("posts", "Devlog articles"), ("listings", "Active listings"), ("sold", "Items sold"), ("sales", "Total sales")]
ACCENTS = ["Ember", "Rose", "Ice", "Violet"]

SETTINGS = [
    f("headline", "text", "Home page headline", required=True),
    f("name", "text", "Your name on the home page", help="Shown under the big photo, for example: Gustavs, aka mrgrass."),
    f("intro", "textarea", "Home page introduction", rows=3),
    f("accent", "select", "Accent colour", options=ACCENTS, default="Ember"),
    f("portrait", "image", "Photo or avatar for the About page"),
    f("bio", "markdown", "About: biography"),
    f("interests", "list", "About: current interests", help="One per line."),
    f("skills", "list", "About: skills I am developing", help="One per line."),
    f("goals", "list", "About: current goals", help="One per line."),
    f("socials", "rows", "Links", help="One per line: Name | https://..."),
    f("vinted_url", "url", "Vinted profile"),
    f("ebay_url", "url", "eBay profile"),
    f("contact_email", "text", "Public contact email", help="Leave empty to keep your address private. Visitors can still use the contact form; messages arrive under Messages."),
    f("hidden_pages", "tags", "Hidden pages", help="Pages to take out of the menu until they have content: " + ", ".join(k for k, _, _ in PAGES[1:] + EXTRA_PAGES)),
    f("hidden_stats", "tags", "Hidden statistics", help="Any of: " + ", ".join(k for k, _ in STATS) + ". Write all to hide the whole block."),
    f("terminal", "bool", "Show the terminal button"),
]


def slugify(s: str) -> str:
    import unicodedata
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")[:70]


def _strs(v) -> list[str]:
    if isinstance(v, str):
        v = re.split(r"[\n]", v)
    return [str(x).strip()[:400] for x in (v or []) if str(x).strip()][:200]


def _image(v):
    if isinstance(v, dict) and str(v.get("src", "")).startswith("/media/") and ".." not in v["src"]:
        return {"src": v["src"], "thumb": v.get("thumb") if str(v.get("thumb", "")).startswith("/media/") else v["src"],
                "w": int(v.get("w") or 0), "h": int(v.get("h") or 0), "exif": v.get("exif") if isinstance(v.get("exif"), dict) else {}}
    return None


def clean(fields: list[dict], data: dict) -> tuple[dict, dict]:
    """Validate what the dashboard sent. Returns (clean values, {field: problem})."""
    out, bad = {}, {}
    for fd in fields:
        k, kind, v = fd["key"], fd["kind"], data.get(fd["key"])
        if kind in ("text", "textarea", "markdown", "code"):
            v = str(v or "").strip() if kind != "code" else str(v or "")
            limit = 300 if kind == "text" else 200_000
            if len(v) > limit:
                bad[k] = f"Too long (the limit is {limit} characters)."
        elif kind == "select":
            if v not in fd["options"]:
                v = fd.get("default", fd["options"][0])
        elif kind == "bool":
            v = bool(v)
        elif kind == "number":
            if v in ("", None):
                v = None
            else:
                try:
                    v = float(v)
                    if ("min" in fd and v < fd["min"]) or ("max" in fd and v > fd["max"]):
                        bad[k] = f"Use a number from {fd.get('min', 0)} to {fd.get('max', 'any')}."
                    if v == int(v):
                        v = int(v)
                except (TypeError, ValueError):
                    bad[k], v = "This needs to be a number.", None
        elif kind == "url":
            v = str(v or "").strip()
            if v and not re.match(r"https?://[^\s]+$", v):
                bad[k] = "Links start with https:// (or http://)."
        elif kind == "date":
            v = str(v or "").strip()
            if v:
                try:
                    date.fromisoformat(v)
                except ValueError:
                    bad[k] = "Use a date like 2026-11-15."
        elif kind == "tags":
            v = _strs(re.split(r"[,\n]", v) if isinstance(v, str) else v)
        elif kind == "list":
            v = _strs(v)
        elif kind == "rows":
            rows = []
            for r in (v.split("\n") if isinstance(v, str) else v or []):
                parts = [p.strip() for p in r.split("|", 1)] if isinstance(r, str) else [str(p).strip() for p in r][:2]
                if any(parts):
                    rows.append([parts[0][:200], (parts[1] if len(parts) > 1 else "")[:1000]])
            v = rows[:200]
        elif kind == "image":
            v = _image(v)
        elif kind == "images":
            v = [i for i in (_image(x) for x in (v or [])) if i][:40]
        if fd.get("required") and not v and k not in bad:
            bad[k] = "This is needed."
        out[k] = v
    return out, bad


def clean_settings(raw: dict) -> tuple[dict, dict]:
    """Validate the site settings (dashboard save and content drops share this)."""
    data, bad = clean(SETTINGS, raw)
    if bad:
        return data, bad
    known = {k for k, _, _ in PAGES + EXTRA_PAGES} - {"home"}
    data["hidden_pages"] = [p for p in (x.lower() for x in data["hidden_pages"]) if p in known]
    data["hidden_stats"] = [s for s in (x.lower() for x in data["hidden_stats"]) if s in {k for k, _ in STATS} | {"all"}]
    if data["accent"] not in ACCENTS:
        data["accent"] = "Ember"
    return data, {}
