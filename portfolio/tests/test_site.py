"""End-to-end checks of the site through its real HTTP interface (no browser needed)."""
import io
import re

import pytest
from PIL import Image
from starlette.testclient import TestClient

from app import main

PW = "correct horse battery"
H = {"X-MG": "1"}


@pytest.fixture()
def anon():
    return TestClient(main.app)


@pytest.fixture()
def admin():
    main.auth.fails.clear()
    c = TestClient(main.app)
    assert c.post("/admin/api/login", json={"password": PW}).status_code == 200
    return c


def png(size=(640, 480), color=(200, 80, 40), exif=None) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, "JPEG", **({"exif": exif} if exif else {}))
    return buf.getvalue()


def add(admin, type_, data, published=True):
    r = admin.post(f"/admin/api/items?type={type_}", json={"data": data, "published": published}, headers=H)
    assert r.status_code == 200, r.text
    return r.json()


# ---- public pages ----------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("url", ["/", "/projects", "/projects/ss-lv-deal-finder", "/projects/pc-toolkit", "/lab", "/photos", "/shop", "/listings",
                                 "/devlog", "/about", "/now", "/playground", "/playground/flip-calculator", "/playground/value-compare",
                                 "/playground/exposure", "/themes", "/search", "/search?q=deal", "/robots.txt", "/sitemap.xml", "/healthz", "/admin"])
def test_pages_load(anon, url):
    assert anon.get(url).status_code == 200


def test_unknown_page_is_a_real_404(anon):
    r = anon.get("/projects/does-not-exist")
    assert r.status_code == 404 and "This page does not exist" in r.text
    assert anon.get("/api/nope").json() == {"error": "Not found."}


def test_security_headers(anon):
    h = anon.get("/").headers
    assert "script-src 'self'" in h["content-security-policy"] and h["x-content-type-options"] == "nosniff"
    assert "<script>" not in anon.get("/").text.replace('<script src', '')      # no inline scripts, so the policy can stay strict


def test_seed_makes_no_claims(anon):
    """Sections with nothing real in them start empty instead of showing invented content."""
    assert "No photographs yet" in anon.get("/photos").text
    assert "Nothing for sale here right now" in anon.get("/shop").text
    assert "No listings added yet" in anon.get("/listings").text
    assert "The notebook is empty" in anon.get("/lab").text
    assert "mrgrass.me is live" not in anon.get("/devlog").text                  # the starter post is a draft


# ---- sign-in ----------------------------------------------------------------------------------------------------------
def test_dashboard_api_needs_sign_in(anon):
    assert anon.get("/admin/api/me").status_code == 401
    assert anon.get("/admin/api/items?type=project").status_code == 401
    assert anon.post("/admin/api/upload", content=png(), headers=H).status_code == 401
    assert anon.put("/admin/api/settings", json={}, headers=H).status_code == 401


def test_wrong_password_and_throttle(anon):
    main.auth.fails.clear()
    for _ in range(6):
        assert anon.post("/admin/api/login", json={"password": "nope"}).status_code == 401
    r = anon.post("/admin/api/login", json={"password": PW})
    assert r.status_code == 429 and "Wait" in r.json()["error"]
    main.auth.fails.clear()


def test_cookie_is_httponly_and_changes_need_the_header(admin):
    c = TestClient(main.app)
    r = c.post("/admin/api/login", json={"password": PW})
    assert "httponly" in r.headers["set-cookie"].lower() and "samesite=strict" in r.headers["set-cookie"].lower()
    assert admin.post("/admin/api/items?type=now", json={"data": {"text": "x"}}).status_code == 403          # no X-MG header
    assert admin.post("/admin/api/items?type=now", json={"data": {"text": "x"}}, headers={**H, "Origin": "https://evil.example"}).status_code == 403


def test_password_is_never_sent_to_the_browser(admin):
    me = admin.get("/admin/api/me").text
    assert PW not in me and "pw_hash" not in me
    assert PW not in admin.get("/admin").text


# ---- content ----------------------------------------------------------------------------------------------------------
def test_validation(admin):
    r = admin.post("/admin/api/items?type=project", json={"data": {"summary": "no title"}}, headers=H)
    assert r.status_code == 422 and "title" in r.json()["errors"]
    r = admin.post("/admin/api/items?type=listing", json={"data": {"title": "x", "url": "javascript:alert(1)"}}, headers=H)
    assert r.status_code == 422 and "url" in r.json()["errors"]
    r = admin.post("/admin/api/items?type=experiment", json={"data": {"title": "x", "difficulty": 14}}, headers=H)
    assert r.status_code == 422 and "difficulty" in r.json()["errors"]
    assert admin.post("/admin/api/items?type=nope", json={"data": {}}, headers=H).status_code == 400


def test_project_lifecycle(admin, anon):
    p = add(admin, "project", {"title": "Älpha Tool", "summary": "A thing", "status": "Testing", "technologies": "Python, Rust", "features": "one\ntwo",
                               "timeline": "2026-01 | Started\n2026-03 | Shipped", "description": "Hello <script>alert(1)</script> **bold**"})
    assert p["slug"] == "alpha-tool" and p["technologies"] == ["Python", "Rust"] and p["timeline"][1] == ["2026-03", "Shipped"]
    page = anon.get("/projects/alpha-tool").text
    assert "<strong>bold</strong>" in page and "<script>alert(1)</script>" not in page and "&lt;script&gt;" in page
    assert "Älpha Tool" in anon.get("/projects").text
    same = add(admin, "project", {"title": "Älpha Tool"})
    assert same["slug"] == "alpha-tool-2"
    r = admin.patch(f"/admin/api/items/{p['id']}", json={"set": {"featured": True, "status": "Completed"}}, headers=H)
    assert r.json()["featured"] is True and r.json()["status"] == "Completed" and r.json()["summary"] == "A thing"
    assert "Älpha Tool" in anon.get("/").text                                     # featured projects reach the home page
    admin.patch(f"/admin/api/items/{p['id']}", json={"published": False}, headers=H)
    assert anon.get("/projects/alpha-tool").status_code == 404 and 'href="/projects/alpha-tool"' not in anon.get("/projects").text
    for x in (p, same):
        assert admin.delete(f"/admin/api/items/{x['id']}", headers=H).status_code == 200
    assert admin.delete(f"/admin/api/items/{p['id']}", headers=H).status_code == 404


def test_listing_states(admin, anon):
    it = add(admin, "listing", {"title": "RX 580 8GB", "platform": "eBay", "url": "https://www.ebay.com/itm/1", "price": 70, "currency": "EUR"})
    page = anon.get("/listings").text
    assert "RX 580 8GB" in page and "€70" in page and 'data-state="Available"' in page
    detail = anon.get("/listings/rx-580-8gb").text
    assert "Open on eBay" in detail and "https://www.ebay.com/itm/1" in detail and "Ask about this" in detail
    admin.patch(f"/admin/api/items/{it['id']}", json={"set": {"status": "Sold"}}, headers=H)
    assert 'data-state="Sold"' in anon.get("/listings").text
    sold = anon.get("/listings/rx-580-8gb").text
    assert "has been sold" in sold and "Open on eBay" not in sold                # no way to "buy" a sold item
    admin.patch(f"/admin/api/items/{it['id']}", json={"set": {"status": "Archived"}}, headers=H)
    assert "RX 580 8GB" not in anon.get("/listings").text and anon.get("/listings/rx-580-8gb").status_code == 404
    admin.delete(f"/admin/api/items/{it['id']}", headers=H)


def test_shop_has_no_fake_checkout(admin, anon):
    it = add(admin, "product", {"name": "Mech keyboard", "price": 25.5, "specs": "Layout | ISO"})
    detail = anon.get("/shop/mech-keyboard").text
    assert "€25.50" in detail and "Ask about this" in detail and "Go to the listing" not in detail      # no buy link was given
    assert not re.search(r"add to cart|checkout|pay now", detail, re.I)
    admin.delete(f"/admin/api/items/{it['id']}", headers=H)


def test_drafts_stay_private(admin, anon):
    post = add(admin, "post", {"title": "Secret draft", "date": "2026-11-01", "content": "words " * 500}, published=False)
    assert anon.get("/devlog/secret-draft").status_code == 404
    assert "Secret draft" not in anon.get("/devlog").text and anon.get("/api/search?q=secret").json() == []
    admin.patch(f"/admin/api/items/{post['id']}", json={"published": True}, headers=H)
    assert "2 min read" in anon.get("/devlog/secret-draft").text
    assert anon.get("/api/search?q=secret").json()[0]["url"] == "/devlog/secret-draft"
    admin.delete(f"/admin/api/items/{post['id']}", headers=H)


def test_search(anon):
    hits = anon.get("/api/search?q=gemini").json()
    assert hits and hits[0]["title"] == "SS.lv Deal Finder"
    assert "SS.lv Deal Finder" in anon.get("/search?q=classifieds").text
    assert "Nothing on the site matches" in anon.get("/search?q=zzzzqqq").text


# ---- uploads ----------------------------------------------------------------------------------------------------------
def test_upload_and_cleanup(admin, anon):
    assert admin.post("/admin/api/upload", content=b"not an image", headers=H).status_code == 400
    exif = Image.Exif()
    exif[0x0110] = "X-T30"                                                       # camera model
    exif[0x8825] = {1: "N", 2: (56.0, 57.0, 0.0)}                                # GPS position, must not survive
    img = admin.post("/admin/api/upload?quality=photo", content=png((4000, 3000), exif=exif.tobytes()), headers=H).json()
    assert img["w"] == 3000 and img["exif"].get("camera") == "X-T30"
    stored = main.MEDIA / img["src"].split("/")[-1]
    assert stored.is_file() and not Image.open(stored).getexif()                 # metadata (and location) is gone from the public file
    assert anon.get(img["src"]).headers["content-type"] == "image/webp" and anon.get(img["thumb"]).status_code == 200
    assert anon.get("/media/../site.db").status_code == 404 and anon.get("/media/site.db").status_code == 404
    photo = add(admin, "photo", {"image": img, "title": "Sunset", "camera": "X-T30"})
    assert "Sunset" in anon.get("/photos").text and "X-T30" in anon.get("/photos").text
    assert admin.post("/admin/api/items?type=photo", json={"data": {"title": "no file"}}, headers=H).status_code == 422
    admin.delete(f"/admin/api/items/{photo['id']}", headers=H)
    assert not stored.exists()                                                   # deleting the photo removes its files


def test_image_reference_must_be_an_upload(admin):
    r = admin.post("/admin/api/items?type=photo", json={"data": {"image": {"src": "https://evil.example/x.png"}}}, headers=H)
    assert r.status_code == 422


# ---- contact form -----------------------------------------------------------------------------------------------------
def test_inquiry(admin, anon):
    main._inquiries.clear()
    bad = anon.post("/api/inquiry", json={"name": "", "email": "nope", "message": "hi"}).json()["errors"]
    assert set(bad) == {"name", "email", "message"}
    assert anon.post("/api/inquiry", json={"name": "Bot", "email": "b@x.io", "message": "spam spam", "website": "http://x"}).json() == {"ok": True}
    assert not main.db.all("message")                                            # the hidden field caught it, nothing stored
    ok = anon.post("/api/inquiry", json={"name": "Anna", "email": "anna@example.com", "message": "Is the GPU still available?", "about": "RX 580"})
    assert ok.json() == {"ok": True}
    msgs = admin.get("/admin/api/items?type=message").json()
    assert len(msgs) == 1 and msgs[0]["about"] == "RX 580" and msgs[0]["read"] is False
    assert admin.get("/admin/api/me").json()["unread"] == 1
    r = admin.patch(f"/admin/api/items/{msgs[0]['id']}", json={"set": {"read": True, "message": "tampered"}}, headers=H).json()
    assert r["read"] is True and r["message"] == "Is the GPU still available?"   # only the read mark can change
    for _ in range(4):
        anon.post("/api/inquiry", json={"name": "Anna", "email": "anna@example.com", "message": "again and again"})
    assert anon.post("/api/inquiry", json={"name": "Anna", "email": "anna@example.com", "message": "one too many"}).status_code == 429
    for m in admin.get("/admin/api/items?type=message").json():
        admin.delete(f"/admin/api/items/{m['id']}", headers=H)
    main._inquiries.clear()


# ---- settings ---------------------------------------------------------------------------------------------------------
def test_settings(admin, anon):
    s = admin.get("/admin/api/me").json()["settings"]
    r = admin.put("/admin/api/settings", json={**s, "headline": "New headline. Second line.", "hidden_pages": "shop, bogus", "accent": "Rose",
                                               "socials": "GitHub | https://github.com/mrgrassyt", "hidden_stats": "all"}, headers=H)
    assert r.status_code == 200 and r.json()["hidden_pages"] == ["shop"] and r.json()["socials"] == [["GitHub", "https://github.com/mrgrassyt"]]
    home = anon.get("/").text
    assert "New headline." in home and 'data-accent="rose"' in home and 'href="/shop"' not in home
    assert "In numbers" not in anon.get("/about").text
    assert admin.put("/admin/api/settings", json={**s, "headline": ""}, headers=H).status_code == 422
    assert admin.put("/admin/api/settings", json={**s, "vinted_url": "ftp://x"}, headers=H).status_code == 422
    admin.put("/admin/api/settings", json=s, headers=H)
    assert 'href="/shop"' in anon.get("/").text


def test_custom_playground_toy_is_sandboxed(admin, anon):
    toy = add(admin, "toy", {"title": "Dice", "summary": "Rolls a die", "html": "<button onclick=\"this.textContent=1+Math.floor(Math.random()*6)\">Roll</button>"})
    assert 'sandbox="allow-scripts"' in anon.get("/playground/dice").text
    emb = anon.get("/playground/embed/dice")
    assert emb.headers["content-security-policy"].startswith("sandbox allow-scripts") and "Roll" in emb.text
    admin.delete(f"/admin/api/items/{toy['id']}", headers=H)


def test_change_password(admin):
    assert admin.post("/admin/api/password", json={"current": "wrong", "new": "a new long password"}, headers=H).status_code == 422
    assert admin.post("/admin/api/password", json={"current": PW, "new": "short"}, headers=H).status_code == 422
    other = TestClient(main.app)
    other.post("/admin/api/login", json={"password": PW})
    assert admin.post("/admin/api/password", json={"current": PW, "new": "a new long password"}, headers=H).status_code == 200
    assert other.get("/admin/api/me").status_code == 401                         # other devices are signed out
    assert admin.get("/admin/api/me").json()["default_password"] is False
    fresh = TestClient(main.app)
    assert fresh.post("/admin/api/login", json={"password": PW}).status_code == 401
    assert fresh.post("/admin/api/login", json={"password": "a new long password"}).status_code == 200
    assert ":" in main.db.kv("pw_hash") and "a new long password" not in main.db.kv("pw_hash")
    main.db.set_kv("pw_hash", None)                                               # back to the starting password for the other tests
    main.auth.fails.clear()


def test_content_drop_imports_once_and_respects_edits(admin, anon, tmp_path):
    from app import importer
    (tmp_path / "images").mkdir()
    (tmp_path / "images" / "a.jpg").write_bytes(png())
    (tmp_path / "drop.json").write_text('[{"key": "t-1", "type": "listing", "images": {"images": ["a.jpg"]}, "data": {"title": "Dropped item", '
                                        '"platform": "Vinted", "url": "https://www.vinted.lv/items/1", "price": 9, "status": "Available"}},'
                                        '{"key": "t-bad", "type": "listing", "data": {"title": "No link"}}]')
    assert importer.run(main.db, main.MEDIA, tmp_path) == ["t-1"]                   # the invalid one is skipped, not half-imported
    assert "Dropped item" in anon.get("/listings").text
    assert importer.run(main.db, main.MEDIA, tmp_path) == []                        # second run changes nothing
    item = next(i for i in admin.get("/admin/api/items?type=listing").json() if i["title"] == "Dropped item")
    admin.delete(f"/admin/api/items/{item['id']}", headers=H)
    assert importer.run(main.db, main.MEDIA, tmp_path) == [] and "Dropped item" not in anon.get("/listings").text   # deleted stays deleted


def test_content_drop_can_change_settings_and_existing_items(admin, anon, tmp_path):
    from app import importer
    add(admin, "project", {"title": "Updatable", "summary": "old summary"})
    (tmp_path / "drop.json").write_text('[{"key": "s-1", "type": "settings", "data": {"intro": "A new intro line.", "accent": "Nope", "hidden_pages": ["shop", "bogus"]}},'
                                        '{"key": "u-1", "type": "project", "update": "updatable", "data": {"summary": "new summary"}},'
                                        '{"key": "u-missing", "type": "project", "update": "does-not-exist", "data": {"summary": "x"}}]')
    assert importer.run(main.db, main.MEDIA, tmp_path) == ["s-1", "u-1"]            # a missing target is skipped, not invented
    home = anon.get("/").text
    assert "A new intro line." in home and 'data-accent="ember"' in home and 'href="/shop"' not in home
    p = anon.get("/projects/updatable").text
    assert "new summary" in p and "old summary" not in p and "Updatable" in p
    assert importer.run(main.db, main.MEDIA, tmp_path) == []                        # applied once
    main.db.set_kv("site", None)


def test_home_has_no_grass_and_has_sections_in_colour(anon):
    home = anon.get("/").text
    assert "grass.js" not in home and 'class="wm"' not in home and 'class="grass' not in home and "<canvas" not in home
    assert 'data-sec="home"' in home and 'data-sec="lab"' in anon.get("/lab").text and "mrgrass.me" in home
    assert anon.get("/playground/grass").status_code == 404
    assert "Same exposure calculator" in anon.get("/playground").text and 'id="expo"' in anon.get("/playground/exposure").text


def test_theme_studio_lists_every_look_and_has_no_inline_script(anon):
    from app.schema import LOOKS, clean_settings
    r = anon.get("/themes")
    assert r.status_code == 200
    for key, *_ in LOOKS:
        assert f'data-look="{key}"' in r.text
    assert len(LOOKS) == 11 and "<script>" not in r.text and "js/studio.js" in r.text
    assert 'data-default-look="aurora"' in anon.get("/").text
    data, bad = clean_settings({"look": "Blueprint"})
    assert data["look"] == "Blueprint" and "look" not in bad
