"""First-run content. Only things that are known to be true go in here; everything is editable in the dashboard.

Sections with nothing real to show yet (photos, shop, listings, lab experiments, equipment) start empty on purpose.
"""
from __future__ import annotations

from pathlib import Path

from . import media

SETTINGS = {
    "headline": "Building things. Learning by doing.",
    "intro": "I'm mrgrass. I'm into programming, PC hardware, electronics and photography, and I learn by building things I actually use.",
    "accent": "Ember",
    "portrait": None,
    "bio": "I'm mrgrass. I like finding out how things work: software, PC hardware, electronics, cameras.\n\n"
           "Most of what is on this site started as something I wanted for myself. I build it, break it, fix it and write down what I learned, "
           "so the next thing goes a little better.",
    "interests": ["Programming", "Technology", "Electronics", "PC hardware", "Photography", "Building practical projects"],
    "skills": [],
    "goals": [],
    "socials": [["Discord", "https://discord.gg/5hSj8fX2u"], ["YouTube", "https://www.youtube.com/@mrgrass_gltouiu"],
                ["TikTok", "https://www.tiktok.com/@mrgrassyt"], ["Steam", "https://steamcommunity.com/profiles/76561199803288336/"],
                ["GitHub", "https://github.com/mrgrassyt"]],
    "vinted_url": "https://www.vinted.lv/member/3132334289",
    "ebay_url": "https://www.ebay.com/usr/nameisis",
    "contact_email": "",
    "hidden_pages": [],
    "hidden_stats": ["sold", "sales"],
    "terminal": True,
}

PROJECTS = [
    {
        "title": "SS.lv Deal Finder", "status": "In Development", "featured": True, "_image": "deal-finder.jpg",
        "summary": "Watches SS.lv, Latvia's biggest classifieds site, and points out electronics that are listed for less than they usually sell for.",
        "description": "SS.lv gets thousands of new electronics ads a day and the good ones are gone in minutes. Deal Finder reads the listings "
                       "for me, works out what each item normally sells for, and tells me when something is priced well below that.\n\n"
                       "It started as a Windows app for my own use. It now also runs on a small server, so it keeps watching when my PC is off "
                       "and a few friends can use it with their own accounts and settings.",
        "purpose": "I kept finding good deals only by searching manually, usually too late. I wanted something that checks every new ad and only bothers me when it is worth a look.",
        "features": [
            "Scans the SS.lv electronics sections and keeps a history of listings, including a slow crawl through older ads",
            "Works out a normal price from comparable listings and scores every ad against it",
            "Tells model generations apart, so a 2013 and a 2020 MacBook Air are not treated as the same thing",
            "Recognises parts and accessories: an SSD \"for PS5\" is not a PS5, and GDDR5 is not DDR5",
            "Shows broken and for-parts devices with a price that accounts for the repair",
            "Estimates the profit of buying and reselling",
            "Optional second opinion from Google Gemini before an alert goes out",
            "Alerts in the app and as notifications",
            "Accounts by invite: one shared scan, private settings and ratings for each person",
            "Runs as a Windows app or on a server with Docker",
        ],
        "planned": ["A goals tab: pick an item and a target price, follow it on a chart", "Sign in with Google or Discord",
                    "One Telegram alert bot shared by all accounts", "More themes and a layout option"],
        "technologies": ["Python", "FastAPI", "SQLite", "JavaScript", "Docker", "Caddy", "Gemini API", "Playwright"],
        "changelog": [
            ["2026-11-15", "AI check with Gemini before alerts. Fixed look-alike names (GDDR vs DDR, console SSDs). Moved to deals.mrgrass.me."],
            ["2026-11-14", "Older listings through a slow deep crawl. Broken and for-parts devices shown with repair-adjusted prices. Services and wanted ads hidden."],
            ["2026-11-13", "Accounts with invites, one shared scan for everyone, old versus new model detection. First server deployment."],
        ],
        "demo": "https://deals.mrgrass.me",
    },
    {
        "title": "mrgrass.me", "status": "In Development", "featured": True, "_image": "mrgrass-me.jpg",
        "summary": "This website: portfolio, lab notebook, photo gallery and a small shop, all managed from my own dashboard.",
        "description": "One place for everything I make and learn. Projects, hardware experiments, photos, a devlog and the things I am selling "
                       "all live here, and I can add or change any of it from a private dashboard without touching code.",
        "purpose": "I wanted a home for my work that I control, instead of scattering it across profiles.",
        "features": ["Separate sections for projects, tech lab, photography, shop, marketplace listings and devlog",
                     "Private dashboard for adding and editing everything, with image uploads",
                     "Search across the whole site", "A terminal, for those who prefer typing", "Light and dark themes"],
        "technologies": ["Python", "Starlette", "SQLite", "HTML", "CSS", "JavaScript", "Docker", "Caddy"],
        "changelog": [["2026-11-15", "First version online."]],
        "demo": "https://mrgrass.me",
    },
    {
        "title": "PC Toolkit", "status": "Planning", "featured": False,
        "summary": "A collection of small PC utilities and technical tools. Still on the drawing board.",
        "description": "", "features": [], "technologies": [],
    },
]

NOW = [("SS.lv Deal Finder", "Working on", "Smarter price estimates and fewer false alarms."),
       ("mrgrass.me", "Working on", "Filling this site with real content.")]
ROADMAP = [("SS.lv Deal Finder", "In progress", ""), ("mrgrass.me", "In progress", ""), ("PC Toolkit", "Planned", "")]
POST = {
    "title": "mrgrass.me is live", "date": "2026-11-15", "category": "Project update", "tags": ["website"],
    "excerpt": "The site is up. This is the first entry of the devlog.",
    "content": "This is a draft that came with the site. Rewrite it in your own words, or delete it.\n\n"
               "## What goes here\n\nProject updates, things that broke, things that finally worked, and whatever I learn along the way.",
    "projects": ["mrgrass.me"],
}


def run(db, media_dir: Path, seed_dir: Path) -> None:
    if db.kv("seeded"):
        return
    db.set_kv("site", SETTINGS)
    for p in reversed(PROJECTS):
        p = dict(p)
        img = seed_dir / p.pop("_image", "-")
        if img.is_file():
            try:
                p["hero"] = media.store(img.read_bytes(), media_dir)
            except media.BadImage:
                pass
        db.save("project", p)
    for text, section, note in reversed(NOW):
        db.save("now", {"text": text, "section": section, "note": note})
    for title, state, note in reversed(ROADMAP):
        db.save("roadmap", {"title": title, "state": state, "note": note})
    db.save("post", POST, published=False)
    db.set_kv("seeded", True)
