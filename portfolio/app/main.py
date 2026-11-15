"""mrgrass.me: public pages, a JSON API for the private dashboard, uploads, search and the contact form.

Run:  uvicorn app.main:app --port 8770      (data goes to $SITE_DATA, default ./data)
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import smtplib
import threading
import time
from datetime import date, datetime
from email.message import EmailMessage
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape
from markdown_it import MarkdownIt
from markupsafe import Markup
from starlette.applications import Starlette
from starlette.exceptions import HTTPException
from starlette.requests import Request
from starlette.responses import FileResponse, HTMLResponse, JSONResponse, PlainTextResponse, Response
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles

from . import media, seed
from .auth import COOKIE, SESSION_DAYS, Auth
from .db import DB
from .schema import ACCENTS, EXTRA_PAGES, PAGES, SETTINGS, STATS, TYPES, clean

ROOT = Path(__file__).resolve().parent.parent
DATA = Path(os.environ.get("SITE_DATA") or ROOT / "data")
MEDIA = DATA / "media"
SITE_URL = (os.environ.get("SITE_URL") or "").rstrip("/")

db = DB(DATA / "site.db")
auth = Auth(db)
seed.run(db, MEDIA, ROOT / "seed")
md = MarkdownIt("commonmark", {"html": False, "typographer": False}).enable(["table", "strikethrough"])

# ---- templates ----------------------------------------------------------------------------------------------------------
env = Environment(loader=FileSystemLoader(ROOT / "templates"), autoescape=select_autoescape(["html"]), trim_blocks=True, lstrip_blocks=True)
_ver = hashlib.sha1("".join(f"{p}{p.stat().st_mtime_ns}" for p in sorted((ROOT / "static").rglob("*")) if p.is_file()).encode()).hexdigest()[:8]
SYMBOL = {"EUR": "€", "USD": "$", "GBP": "£"}


def f_date(v, short=False) -> str:
    if not v:
        return ""
    d = datetime.fromtimestamp(v) if isinstance(v, (int, float)) else datetime.fromisoformat(str(v)[:10]) if len(str(v)) >= 10 else None
    if not d:
        return str(v)                                         # things like "2026-11" or "v1.2" in timelines stay as written
    return f"{d.day} {d:%b}" if short else f"{d.day} {d:%b %Y}"


def f_money(item: dict) -> str:
    p = item.get("price")
    if p is None:
        return ""
    return f"{SYMBOL.get(item.get('currency'), '')}{p:,.2f}".replace(".00", "")


def f_iso(v) -> str:
    return datetime.fromtimestamp(v).date().isoformat() if isinstance(v, (int, float)) else str(v or "")[:10]


env.filters.update(md=lambda s: Markup(md.render(s or "")), date=f_date, money=f_money, iso=f_iso,
                   slug=lambda s: re.sub(r"[^a-z0-9]+", "-", str(s).lower()).strip("-"))
env.globals.update(static=lambda p: f"/static/{p}?v={_ver}", types=TYPES)


def settings() -> dict:
    return {**seed.SETTINGS, **(db.kv("site") or {})}


def public(type_: str) -> list[dict]:
    items = db.all(type_, public=True)
    if type_ in ("product", "listing"):
        items = [i for i in items if i.get("status") != "Archived"]
    if type_ in ("post", "listing", "experiment"):
        items.sort(key=lambda i: (i.get("date") or f_iso(i["created"]), i["created"]), reverse=True)
    return items


def url_of(item: dict) -> str:
    return TYPES[item["type"]]["url"].format(slug=item["slug"])


env.globals["url_of"] = url_of


def stats(site: dict) -> list[dict]:
    hidden = set(site.get("hidden_stats") or [])
    if "all" in hidden:
        return []
    projects, listings, products = public("project"), public("listing"), public("product")
    sold = [i for i in listings + products if i.get("status") == "Sold"]
    sales: dict[str, float] = {}
    for i in sold:
        if i.get("price"):
            sales[i.get("currency", "EUR")] = sales.get(i.get("currency", "EUR"), 0) + i["price"]
    values = {
        "projects": len(projects), "current": sum(p.get("status") == "In Development" for p in projects),
        "completed": sum(p.get("status") == "Completed" for p in projects), "photos": len(public("photo")), "posts": len(public("post")),
        "listings": sum(i.get("status") == "Available" for i in listings + products), "sold": len(sold),
        "sales": " + ".join(f_money({"price": v, "currency": c}) for c, v in sales.items()),
    }
    return [{"key": k, "label": label, "value": values[k]} for k, label in STATS if k not in hidden and values[k]]   # only real, non-zero numbers


def page(request: Request, template: str, status: int = 200, **ctx) -> HTMLResponse:
    site = settings()
    hidden = set(site.get("hidden_pages") or [])
    ctx.setdefault("title", "")
    ctx.setdefault("description", site["intro"])
    html = env.get_template(template).render(
        request=request, site=site, path=request.url.path, nav=[p for p in PAGES if p[0] not in hidden],
        extra_nav=[p for p in EXTRA_PAGES if p[0] not in hidden], accent=(site.get("accent") or "Ember").lower(),
        site_url=SITE_URL or str(request.base_url).rstrip("/"), year=date.today().year, **ctx)
    return HTMLResponse(html, status_code=status)


def not_found(request: Request) -> HTMLResponse:
    return page(request, "404.html", 404, title="Page not found")


def need(item):
    if not item:
        raise HTTPException(404)
    return item


# ---- public pages -------------------------------------------------------------------------------------------------------
async def home(request: Request):
    projects = public("project")
    feed = []
    for t, label in (("project", "Project"), ("post", "Devlog"), ("experiment", "Tech Lab"), ("photo", "Photo"), ("listing", "Listing"), ("product", "Shop")):
        for i in public(t)[:6]:
            if not (t in ("listing", "product") and i.get("status") != "Available"):
                feed.append({"when": i.get("date") or f_iso(i["created"]), "kind": label, "title": i.get(TYPES[t]["title"]) or "Untitled", "url": url_of(i), "t": i["created"]})
    feed.sort(key=lambda x: (x["when"], x["t"]), reverse=True)
    working = [n for n in public("now") if n.get("section") == "Working on"] or \
              [{"text": p["title"], "note": p.get("summary", "")} for p in projects if p.get("status") == "In Development"]
    return page(request, "home.html", featured=[p for p in projects if p.get("featured")][:4], working=working[:4], feed=feed[:6],
                counts={t: len(public(t)) for t in ("project", "experiment", "photo", "product", "listing", "post")})


async def projects(request: Request):
    items = public("project")
    return page(request, "projects.html", title="Projects", description="Things I am building, with where each one stands.", items=items,
                statuses=[s for s in TYPES["project"]["fields"][2]["options"] if any(p.get("status") == s for p in items)])


async def project(request: Request):
    p = need(db.one("project", request.path_params["slug"], public=True))
    posts = [x for x in public("post") if p["title"] in (x.get("projects") or [])]
    return page(request, "project.html", title=p["title"], description=p.get("summary") or "", p=p, posts=posts, og_image=(p.get("hero") or {}).get("src"))


async def lab(request: Request):
    items, gear = public("experiment"), public("gear")
    groups = [(g, [x for x in reversed(gear) if x.get("group") == g]) for g in TYPES["gear"]["fields"][1]["options"]]
    return page(request, "lab.html", title="Tech Lab", description="Hardware experiments, repairs and what came out of them.", items=items,
                categories=sorted({i.get("category") for i in items if i.get("category")}), gear=[g for g in groups if g[1]])


async def experiment(request: Request):
    e = need(db.one("experiment", request.path_params["slug"], public=True))
    return page(request, "experiment.html", title=e["title"], description=(e.get("description") or "")[:160], e=e, og_image=((e.get("photos") or [{}])[0]).get("src"))


async def photos(request: Request):
    items = public("photo")
    items.sort(key=lambda i: (bool(i.get("featured")), i.get("taken") or "", i["created"]), reverse=True)
    return page(request, "photos.html", title="Photography", description="Photographs, with the camera details where I have them.", items=items,
                albums=sorted({i.get("album") for i in items if i.get("album")}))


async def shop(request: Request):
    items = public("product")
    return page(request, "shop.html", title="Shop", description="Things I am selling directly.", items=items,
                categories=[c for c in TYPES["product"]["fields"][5]["options"] if any(i.get("category") == c for i in items)])


async def product(request: Request):
    p = need(db.one("product", request.path_params["slug"], public=True))
    if p.get("status") == "Archived":
        raise HTTPException(404)
    return page(request, "product.html", title=p["name"], description=p.get("short") or "", p=p, og_image=((p.get("images") or [{}])[0]).get("src"))


async def listings(request: Request):
    items = public("listing")
    return page(request, "listings.html", title="My Listings", description="Everything I currently have for sale on Vinted and eBay.", items=items,
                available=sum(i.get("status") in ("Available", "Reserved") for i in items))


async def listing(request: Request):
    p = need(db.one("listing", request.path_params["slug"], public=True))
    if p.get("status") == "Archived":
        raise HTTPException(404)
    return page(request, "listing.html", title=p["title"], description=(p.get("description") or "")[:160], p=p, og_image=((p.get("images") or [{}])[0]).get("src"))


def reading_time(text: str) -> int:
    return max(1, round(len(re.findall(r"\w+", text or "")) / 220))


async def devlog(request: Request):
    items = public("post")
    for i in items:
        i["minutes"] = reading_time(i.get("content"))
    return page(request, "devlog.html", title="Devlog", description="Notes on what I build, break and learn.", items=items,
                categories=sorted({i.get("category") for i in items if i.get("category")}))


async def post(request: Request):
    p = need(db.one("post", request.path_params["slug"], public=True))
    related = [x for x in public("project") if x["title"] in (p.get("projects") or [])]
    others = [x for x in public("post") if x["id"] != p["id"]][:3]
    return page(request, "post.html", title=p["title"], description=p.get("excerpt") or "", p=p, minutes=reading_time(p.get("content")),
                related=related, others=others, og_image=(p.get("cover") or {}).get("src"))


async def about(request: Request):
    gear = public("gear")
    groups = [(g, [x for x in reversed(gear) if x.get("group") == g]) for g in TYPES["gear"]["fields"][1]["options"]]
    return page(request, "about.html", title="About", stats=stats(settings()), gear=[g for g in groups if g[1]])


async def now(request: Request):
    items, road = public("now"), public("roadmap")
    sections = [(s, [i for i in reversed(items) if i.get("section") == s]) for s in TYPES["now"]["fields"][1]["options"]]
    lanes = [(s, [i for i in reversed(road) if i.get("state") == s]) for s in TYPES["roadmap"]["fields"][1]["options"]]
    updated = max([i["updated"] for i in items + road] or [0])
    return page(request, "now.html", title="Now", description="What I am working on at the moment, and what comes next.",
                sections=[s for s in sections if s[1]], lanes=lanes, has_road=bool(road), updated=updated)


BUILTIN_TOYS = [
    {"slug": "flip-calculator", "title": "Flip calculator", "summary": "Buy, fix, resell: what is left after fees, parts and shipping, and whether it is worth the time."},
    {"slug": "value-compare", "title": "Value comparison", "summary": "Price per gigabyte, per frame, per anything. Put parts side by side and see which gives the most for the money."},
    {"slug": "grass", "title": "Grass", "summary": "The field from the home page, with the wind in your hands."},
]


async def playground(request: Request):
    return page(request, "playground.html", title="Playground", description="Small tools and experiments you can use right here.",
                builtin=BUILTIN_TOYS, custom=public("toy"))


async def toy(request: Request):
    slug = request.path_params["slug"]
    built = next((t for t in BUILTIN_TOYS if t["slug"] == slug), None)
    t = built or need(db.one("toy", slug, public=True))
    return page(request, "toy.html", title=t["title"], description=t.get("summary") or "", t=t, builtin=bool(built))


async def toy_embed(request: Request):
    t = need(db.one("toy", request.path_params["slug"], public=True))
    return HTMLResponse(t.get("html") or "", headers={"Content-Security-Policy": "sandbox allow-scripts; default-src 'unsafe-inline' data: blob:; img-src * data: blob:"})


# ---- search -------------------------------------------------------------------------------------------------------------
SEARCHABLE = [("project", "Project"), ("post", "Devlog"), ("experiment", "Tech Lab"), ("listing", "Listing"), ("product", "Shop"), ("photo", "Photo"), ("toy", "Playground")]


def _text(v) -> str:
    if isinstance(v, str):
        return v
    if isinstance(v, list):
        return " ".join(_text(x) for x in v)
    return ""


def search(q: str, only: str = "") -> list[dict]:
    terms = [t for t in q.lower().split() if t][:6]
    if not terms:
        return []
    out = []
    for t, label in SEARCHABLE:
        if only and only != t:
            continue
        for i in public(t):
            title = str(i.get(TYPES[t]["title"]) or "Untitled")
            hay = " ".join(_text(v) for k, v in i.items() if k not in ("type", "slug", "html")).lower()
            if all(term in hay for term in terms):
                body = i.get("summary") or i.get("excerpt") or i.get("short") or i.get("caption") or i.get("description") or i.get("content") or ""
                thumb = (i.get("hero") or i.get("cover") or i.get("image") or (i.get("images") or i.get("photos") or [None])[0] or {}).get("thumb")
                out.append({"type": t, "kind": label, "title": title, "url": url_of(i), "text": re.sub(r"[#*_`>\[\]]", "", body)[:150], "thumb": thumb,
                            "score": sum(3 * title.lower().count(term) + hay.count(term) for term in terms)})
    return sorted(out, key=lambda r: -r["score"])[:40]


async def search_page(request: Request):
    q, only = request.query_params.get("q", "").strip()[:80], request.query_params.get("in", "")
    return page(request, "search.html", title="Search", q=q, only=only, results=search(q, only), kinds=SEARCHABLE)


async def api_search(request: Request):
    return JSONResponse(search(request.query_params.get("q", "").strip()[:80])[:12])


async def api_site(request: Request):
    """What the terminal needs to answer its commands."""
    site = settings()
    return JSONResponse({
        "intro": site["intro"], "socials": site.get("socials") or [], "email": site.get("contact_email") or "",
        "projects": [{"title": p["title"], "status": p.get("status"), "url": url_of(p)} for p in public("project")],
        "posts": [{"title": p["title"], "url": url_of(p)} for p in public("post")[:8]],
        "counts": {t: len(public(t)) for t in ("experiment", "photo", "product", "listing")},
        "pages": [[k, label, url] for k, label, url in PAGES + EXTRA_PAGES if k not in set(site.get("hidden_pages") or [])],
    })


# ---- contact form -------------------------------------------------------------------------------------------------------
_inquiries: dict[str, list[float]] = {}


def client_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for", "")
    return fwd.split(",")[-1].strip() if fwd else (request.client.host if request.client else "?")


def send_mail(subject: str, body: str, reply_to: str) -> None:
    """Forward a message by email when SMTP is configured (SMTP_HOST, SMTP_USER, SMTP_PASSWORD, SITE_MAIL_TO). Optional."""
    host, to = os.environ.get("SMTP_HOST"), os.environ.get("SITE_MAIL_TO")
    if not (host and to):
        return
    msg = EmailMessage()
    msg["Subject"], msg["From"], msg["To"], msg["Reply-To"] = subject, os.environ.get("SMTP_FROM") or os.environ.get("SMTP_USER") or to, to, reply_to
    msg.set_content(body)
    try:
        with smtplib.SMTP(host, int(os.environ.get("SMTP_PORT") or 587), timeout=20) as s:
            s.starttls()
            if os.environ.get("SMTP_USER"):
                s.login(os.environ["SMTP_USER"], os.environ.get("SMTP_PASSWORD", ""))
            s.send_message(msg)
    except Exception as e:                                    # the message is already saved in the dashboard; mail is a bonus
        print("mail failed:", e, flush=True)


async def api_inquiry(request: Request):
    try:
        d = await request.json()
    except ValueError:
        return JSONResponse({"error": "Could not read the form."}, 400)
    if d.get("website"):                                      # hidden field that only bots fill in
        return JSONResponse({"ok": True})
    ip, now_ = client_ip(request), time.time()
    recent = [t for t in _inquiries.get(ip, []) if now_ - t < 3600]
    if len(recent) >= 5:
        return JSONResponse({"error": "That is a lot of messages in one hour. Try again later."}, 429)
    name, email, message = str(d.get("name") or "").strip(), str(d.get("email") or "").strip(), str(d.get("message") or "").strip()
    errors = {}
    if not 1 <= len(name) <= 100:
        errors["name"] = "Add your name."
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]{2,}", email) or len(email) > 200:
        errors["email"] = "That does not look like an email address."
    if not 5 <= len(message) <= 4000:
        errors["message"] = "Write a few words (up to 4000 characters)."
    if errors:
        return JSONResponse({"errors": errors}, 422)
    _inquiries[ip] = recent + [now_]
    about_ = str(d.get("about") or "")[:200]
    db.save("message", {"name": name, "email": email, "about": about_, "message": message, "read": False}, published=False, slug=f"m-{int(now_ * 1000)}")
    threading.Thread(target=send_mail, args=(f"mrgrass.me: message from {name}" + (f" about {about_}" if about_ else ""),
                                             f"{message}\n\nFrom: {name} <{email}>\nAbout: {about_ or '-'}", email), daemon=True).start()
    return JSONResponse({"ok": True})


# ---- files, robots, sitemap ---------------------------------------------------------------------------------------------
async def media_file(request: Request):
    name = request.path_params["name"]
    path = MEDIA / name
    if not re.fullmatch(r"[a-f0-9]{16}(_s)?\.webp", name) or not path.is_file():
        raise HTTPException(404)
    return FileResponse(path, headers={"Cache-Control": "public, max-age=31536000, immutable"})


async def robots(request: Request):
    return PlainTextResponse(f"User-agent: *\nDisallow: /admin\nDisallow: /search\nSitemap: {SITE_URL or str(request.base_url).rstrip('/')}/sitemap.xml\n")


async def sitemap(request: Request):
    base = SITE_URL or str(request.base_url).rstrip("/")
    hidden = set(settings().get("hidden_pages") or [])
    urls = [u for k, _, u in PAGES + EXTRA_PAGES if k not in hidden]
    for t in ("project", "experiment", "product", "listing", "post", "toy"):
        urls += [url_of(i) for i in public(t)]
    body = "".join(f"<url><loc>{base}{u}</loc></url>" for u in urls)
    return Response(f'<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{body}</urlset>', media_type="application/xml")


# ---- dashboard API ------------------------------------------------------------------------------------------------------
def admin_only(fn):
    async def wrapped(request: Request):
        if not auth.valid(request.cookies.get(COOKIE)):
            return JSONResponse({"error": "Sign in first."}, 401)
        if request.method != "GET":
            origin = request.headers.get("origin")
            if request.headers.get("x-mg") != "1" or (origin and origin.split("//")[-1] != request.headers.get("host")):
                return JSONResponse({"error": "Request blocked."}, 403)
        return await fn(request)
    return wrapped


async def admin_page(request: Request):
    return HTMLResponse(env.get_template("admin.html").render(), headers={"X-Robots-Tag": "noindex"})


async def admin_login(request: Request):
    ip = client_ip(request)
    if (wait := auth.blocked(ip)):
        return JSONResponse({"error": f"Too many wrong tries. Wait {wait // 60 + 1} minutes."}, 429)
    if not auth.configured():
        return JSONResponse({"error": "No password is set on the server yet. Set SITE_ADMIN_PASSWORD and restart."}, 503)
    try:
        pw = str((await request.json()).get("password") or "")
    except ValueError:
        pw = ""
    if not auth.verify(pw):
        auth.failed(ip)
        return JSONResponse({"error": "Wrong password."}, 401)
    res = JSONResponse({"ok": True})
    https = request.headers.get("x-forwarded-proto") == "https" or request.url.scheme == "https"
    res.set_cookie(COOKIE, auth.start(), max_age=SESSION_DAYS * 86400, httponly=True, secure=https, samesite="strict", path="/")
    return res


async def admin_logout(request: Request):
    auth.end(request.cookies.get(COOKIE))
    res = JSONResponse({"ok": True})
    res.delete_cookie(COOKIE, path="/")
    return res


@admin_only
async def admin_me(request: Request):
    return JSONResponse({
        "types": {k: {x: v[x] for x in ("label", "one", "title", "url", "list", "fields") } | {"readonly": v.get("readonly", False), "draft_first": v.get("draft_first", False)}
                  for k, v in TYPES.items()},
        "settings_fields": SETTINGS, "settings": settings(), "counts": {k: db.count(k) for k in TYPES},
        "unread": sum(not m.get("read") for m in db.all("message")), "default_password": not db.kv("pw_hash"),
        "mail": bool(os.environ.get("SMTP_HOST") and os.environ.get("SITE_MAIL_TO")),
    })


@admin_only
async def admin_items(request: Request):
    t = request.query_params.get("type", "")
    if t not in TYPES:
        return JSONResponse({"error": "Unknown type."}, 400)
    if request.method == "GET":
        return JSONResponse(db.all(t))
    if TYPES[t].get("readonly"):
        return JSONResponse({"error": "These cannot be created here."}, 400)
    body = await request.json()
    data, bad = clean(TYPES[t]["fields"], body.get("data") or {})
    if bad:
        return JSONResponse({"errors": bad}, 422)
    return JSONResponse(db.save(t, data, published=bool(body.get("published", True))))


def _media_srcs(item: dict) -> list[str]:
    return re.findall(r"/media/[a-f0-9]{16}\.webp", json.dumps(item))


@admin_only
async def admin_item(request: Request):
    item = db.by_id(int(request.path_params["id"]))
    if not item:
        return JSONResponse({"error": "That item no longer exists."}, 404)
    t = TYPES[item["type"]]
    before = _media_srcs(item)
    if request.method == "DELETE":
        db.delete(item["id"])
        media.remove_unused(MEDIA, db.media_in_use(), before)
        return JSONResponse({"ok": True})
    body = await request.json()
    current = {fd["key"]: item.get(fd["key"]) for fd in t["fields"]}
    incoming = body.get("data") if request.method == "PUT" else {**current, **(body.get("set") or {})}
    if t.get("readonly"):                                     # messages: only the "read" mark can change
        incoming = {**current, "read": bool((body.get("set") or {}).get("read", current.get("read")))}
    data, bad = clean(t["fields"], incoming or {})
    if bad:
        return JSONResponse({"errors": bad}, 422)
    saved = db.save(item["type"], data, id_=item["id"], published=bool(body.get("published", item["published"])), slug=str(body.get("slug") or ""))
    media.remove_unused(MEDIA, db.media_in_use(), before)
    return JSONResponse(saved)


@admin_only
async def admin_upload(request: Request):
    raw = await request.body()
    try:
        return JSONResponse(media.store(raw, MEDIA, request.query_params.get("quality", "normal")))
    except media.BadImage as e:
        return JSONResponse({"error": str(e)}, 400)


@admin_only
async def admin_settings(request: Request):
    data, bad = clean(SETTINGS, await request.json())
    if bad:
        return JSONResponse({"errors": bad}, 422)
    known = {k for k, _, _ in PAGES + EXTRA_PAGES} - {"home"}
    data["hidden_pages"] = [p for p in (x.lower() for x in data["hidden_pages"]) if p in known]
    data["hidden_stats"] = [s for s in (x.lower() for x in data["hidden_stats"]) if s in {k for k, _ in STATS} | {"all"}]
    if data["accent"] not in ACCENTS:
        data["accent"] = "Ember"
    db.set_kv("site", data)
    return JSONResponse(data)


@admin_only
async def admin_password(request: Request):
    body = await request.json()
    if not auth.verify(str(body.get("current") or "")):
        return JSONResponse({"errors": {"current": "That is not the current password."}}, 422)
    new = str(body.get("new") or "")
    if len(new) < 10:
        return JSONResponse({"errors": {"new": "Use at least 10 characters."}}, 422)
    auth.set_password(new)
    res = JSONResponse({"ok": True})
    res.set_cookie(COOKIE, auth.start(), max_age=SESSION_DAYS * 86400, httponly=True, samesite="strict", path="/",
                   secure=request.headers.get("x-forwarded-proto") == "https" or request.url.scheme == "https")
    return res


@admin_only
async def admin_preview(request: Request):
    return JSONResponse({"html": md.render(str((await request.json()).get("text") or ""))})


# ---- app ----------------------------------------------------------------------------------------------------------------
CSP = "default-src 'self'; img-src 'self' data: blob:; style-src 'self' 'unsafe-inline'; script-src 'self'; frame-src 'self'; " \
      "frame-ancestors 'self'; base-uri 'self'; form-action 'self'; object-src 'none'"


class Headers:
    """Security headers on everything, and no caching of pages so edits show up at once."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)

        async def wrapped(message):
            if message["type"] == "http.response.start":
                h = {k.decode().lower(): v.decode() for k, v in message["headers"]}
                extra = {"x-content-type-options": "nosniff", "referrer-policy": "strict-origin-when-cross-origin",
                         "permissions-policy": "camera=(), microphone=(), geolocation=()"}
                if "content-security-policy" not in h:
                    extra["content-security-policy"] = CSP
                if scope["path"].startswith("/static/"):
                    extra["cache-control"] = "public, max-age=31536000, immutable" if b"v=" in scope.get("query_string", b"") else "public, max-age=3600"
                elif "cache-control" not in h:
                    extra["cache-control"] = "no-cache"
                message["headers"] = list(message["headers"]) + [(k.encode(), v.encode()) for k, v in extra.items()]
            await send(message)
        await self.app(scope, receive, wrapped)


async def on_404(request: Request, exc):
    if request.url.path.startswith(("/admin/api", "/api/")):
        return JSONResponse({"error": "Not found."}, 404)
    return not_found(request)


async def on_500(request: Request, exc):
    return HTMLResponse("<h1>Something went wrong</h1><p>The page could not be shown. Try again in a moment.</p>", 500)


routes = [
    Route("/", home), Route("/projects", projects), Route("/projects/{slug}", project),
    Route("/lab", lab), Route("/lab/{slug}", experiment), Route("/photos", photos),
    Route("/shop", shop), Route("/shop/{slug}", product), Route("/listings", listings), Route("/listings/{slug}", listing),
    Route("/devlog", devlog), Route("/devlog/{slug}", post), Route("/about", about), Route("/now", now),
    Route("/playground", playground), Route("/playground/embed/{slug}", toy_embed), Route("/playground/{slug}", toy),
    Route("/search", search_page), Route("/api/search", api_search), Route("/api/site", api_site),
    Route("/api/inquiry", api_inquiry, methods=["POST"]),
    Route("/media/{name}", media_file), Route("/robots.txt", robots), Route("/sitemap.xml", sitemap),
    Route("/healthz", lambda r: PlainTextResponse("ok")),
    Route("/admin", admin_page), Route("/admin/api/login", admin_login, methods=["POST"]), Route("/admin/api/logout", admin_logout, methods=["POST"]),
    Route("/admin/api/me", admin_me), Route("/admin/api/items", admin_items, methods=["GET", "POST"]),
    Route("/admin/api/items/{id:int}", admin_item, methods=["PUT", "PATCH", "DELETE"]),
    Route("/admin/api/upload", admin_upload, methods=["POST"]), Route("/admin/api/settings", admin_settings, methods=["PUT"]),
    Route("/admin/api/password", admin_password, methods=["POST"]), Route("/admin/api/preview", admin_preview, methods=["POST"]),
    Mount("/static", StaticFiles(directory=ROOT / "static"), name="static"),
]
app = Headers(Starlette(routes=routes, exception_handlers={404: on_404, 500: on_500}))
