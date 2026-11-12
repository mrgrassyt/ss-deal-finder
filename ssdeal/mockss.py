"""A local MOCK of SS.lv used for automated tests and the offline demo.

It reproduces the table markup of SS.lv list pages (tr id="tr_<num>",
a.am links to /msg/lv/..., price cells) and ad pages (#msg_div_msg,
td.ads_opt_name / td.ads_opt, td.ads_price, msg_footer date), plus
robots.txt, pagination, removed ads, price drops and a CAPTCHA switch.

All data here is SYNTHETIC. Run:  python -m ssdeal.mockss --port 8899
"""
from __future__ import annotations

import argparse
import html
import random
import string
import time

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, PlainTextResponse, RedirectResponse, Response

# (feed path, title template, base price, condition text)
CATALOG = {
    "/lv/electronics/computers/completing-pc/": [
        ("video", "Radeon RX 6700 10GB, labā stāvoklī, strādā perfekti", 190),
        ("video", "RTX 3060 12GB Asus Dual, nav majnota", 220),
        ("video", "GTX 1060 6GB", 75),
        ("video", "RTX 3070 Gigabyte Gaming OC", 300),
        ("video", "RX 580 8GB Sapphire Nitro+", 70),
        ("video", "RTX 2060 6GB MSI Ventus", 140),
        ("cpu", "Intel Core i5-12400F, box", 105),
        ("cpu", "Ryzen 5 5600X", 110),
        ("cpu", "Ryzen 7 5800X3D", 250),
        ("ram", "DDR4 2x8GB 3200MHz Corsair Vengeance", 35),
        ("ram", "DDR5 32GB 6000MHz Kingston Fury", 95),
        ("ssd", "Samsung 970 EVO Plus 1TB NVMe", 60),
        ("ssd", "Kingston SSD 240GB SATA", 18),
        ("hdd", "WD 2TB HDD 7200rpm", 35),
        ("motherboards", "MSI B550 Tomahawk mātesplate", 110),
        ("accessories-and-cables", "Corsair RM750x 750W barošanas bloks 80+ gold", 80),
        ("other", "Kaste ar dažādiem datoru vadiem un detaļām", 25),
    ],
    "/lv/electronics/photo-optics/slr-cameras/": [
        ("", "Nikon D610 body, 25k kadri", 520),
        ("", "Canon EOS 5D Mark III body", 650),
        ("", "Nikon D7200 + 18-140mm objektīvs komplektā", 450),
        ("", "Canon EOS 80D body", 430),
    ],
    "/lv/electronics/photo-optics/digital-cameras/": [
        ("", "Sony A7 III body, labā stāvoklī", 1150),
        ("", "Fujifilm X-T3 body", 650),
        ("", "Sony a6400 ar kit objektīvu", 600),
    ],
    "/lv/electronics/photo-optics/objectives/": [
        ("", "Sigma 18-35mm f/1.8 Art Canon EF", 420),
        ("", "Nikon AF-S 50mm f/1.8G", 120),
        ("", "Canon EF 70-200mm f/2.8L IS II USM", 950),
        ("", "Sony FE 85mm f/1.8", 420),
    ],
    "/lv/electronics/computers/game-consoles/": [
        ("", "PS5 disku versija ar 2 kontrolieriem", 380),
        ("", "Nintendo Switch OLED", 240),
        ("", "Xbox Series X 1TB", 330),
        ("", "Steam Deck 512GB", 360),
    ],
    "/lv/electronics/computers/noutbooks/": [
        ("", "MacBook Air M1 8/256, akumulators 92%", 520),
        ("", "Lenovo ThinkPad T480 i5-8350U 16GB 256GB SSD", 260),
    ],
    "/lv/electronics/phones/mobile-phones/": [
        ("", "iPhone 13 Pro Max 256GB", 600),
        ("", "Samsung Galaxy S23 Ultra 256GB", 650),
        ("", "iPhone 12 64GB", 280),
    ],
}

SPECIAL = [  # injected deals for testing the intelligence layer
    ("/lv/electronics/computers/completing-pc/", "video", "Radeon RX 6700 10GB, steidzami", 120, ""),
    ("/lv/electronics/computers/completing-pc/", "video", "RTX 3070 nestrādā, artefakti, uz detaļām", 60, ""),
    ("/lv/electronics/computers/completing-pc/", "video", "GPU videokarte, nezinu modeli", 40, ""),
    ("/lv/electronics/photo-optics/slr-cameras/", "", "Nikon D610 + 24-85mm objektīvs, akumulators, lādētājs", 560, ""),
    ("/lv/electronics/computers/completing-pc/", "accessories-and-cables", "Telefona lādētāja kabelis", 3, ""),
    ("/lv/electronics/computers/completing-pc/", "video", "Pērku RTX 3080", None, "pērku"),
]


PHRASES = ["Pārdodu sakarā ar jaunināšanu.", "Lietots mājās, nekad nav remontēts.", "Viss strādā kā nākas.",
           "Pārdodu, jo vairs nav vajadzīgs.", "Iegādāts pirms gada veikalā.", "Labā stāvoklī, nelieli skrāpējumi."]
PHRASES2 = ["Var apskatīt Rīgā.", "Iespējams nosūtīt ar pakomātu.", "Zvaniet pēc 18:00.", "Cena nav galīgā.",
            "Apskate Purvciemā.", "Rakstiet SMS."]


class MockSS:
    def __init__(self, seed: int = 7, per_template: int = 6):
        self.rng = random.Random(seed)
        self.ads: dict[str, dict] = {}
        self.order: dict[str, list[str]] = {}
        self.captcha = False
        self.rate_limit = False
        self.counter = 50_000_000
        self.requests = 0
        now = time.time()
        for feed, items in CATALOG.items():
            self.order[feed] = []
            for sub, title, base in items:
                for _ in range(per_template):
                    price = round(base * self.rng.uniform(0.82, 1.22))
                    self._add(feed, sub, title, price, now - self.rng.uniform(3600, 40 * 86400))
        for feed, sub, title, price, ptext in SPECIAL:
            self._add(feed, sub, title, price, now - 600, price_text=ptext)
        for feed in self.order:
            self.order[feed].sort(key=lambda k: self.ads[k]["posted"], reverse=True)

    def _add(self, feed: str, sub: str, title: str, price, posted: float, price_text: str = "") -> str:
        self.counter += self.rng.randint(1, 900)
        slug = "".join(self.rng.choice(string.ascii_lowercase) for _ in range(5))
        cat_path = feed.rstrip("/") + (f"/{sub}" if sub else "")
        path = f"/msg{cat_path}/{slug}.html"
        self.ads[path] = {"num": self.counter, "path": path, "feed": feed, "title": title, "price": price,
                          "price_text": price_text, "posted": posted, "removed": False,
                          "desc": title + ". " + self.rng.choice(PHRASES) + " " + self.rng.choice(PHRASES2)}
        if feed in self.order:
            self.order[feed].insert(0, path)
        return path

    def add_new(self, feed: str, sub: str, title: str, price) -> str:
        p = self._add(feed, sub, title, price, time.time())
        return p

    # ---------------------------------------------------------------- rendering
    def list_page(self, feed: str, page: int) -> str | None:
        ids = [p for p in self.order.get(feed, []) if not self.ads[p]["removed"]]
        per = 30
        chunk = ids[(page - 1) * per: page * per]
        if page > 1 and not chunk:
            return None
        rows = []
        for p in chunk:
            a = self.ads[p]
            ptxt = a["price_text"] or (f"{a['price']:,} €".replace(",", ",") if a["price"] is not None else "")
            rows.append(f'''<tr id="tr_{a['num']}"><td class="msga2 pp0"><input type="checkbox" id="c{a['num']}"></td>
<td class="msga2"><a href="{p}" id="im{a['num']}"><img src="https://i.ss.lv/gallery/1/2/{a['num']}/x.th2.jpg" alt="" class="isfoto foto_list"></a></td>
<td class="msg2"><div class="d1"><a href="{p}" id="dm_{a['num']}" class="am">{html.escape(a['title'])}</a></div></td>
<td class="msga2-o pp6" nowrap>Rīga</td><td class="msga2-o pp6" nowrap>{ptxt}</td></tr>''')
        nxt = f'<a href="{feed}page{page + 1}.html" class="navi">Nākamie</a>' if len(ids) > page * per else ""
        return f'''<html><head><meta charset="utf-8"><title>SS.LV mock</title></head><body>
<form><table border=0 cellpadding=2 cellspacing=0 width="100%">
<tr id="head_line"><td class="msg_column" colspan=3>Sludinājumi</td><td class="msg_column_td">Pilsēta</td><td class="msg_column_td">Cena</td></tr>
{''.join(rows)}
<tr id="tr_bnr_712"><td colspan=5>banner</td></tr>
</table></form><div class="td2">{nxt}</div></body></html>'''

    def ad_page(self, path: str) -> str | None:
        a = self.ads.get(path)
        if not a or a["removed"]:
            return None
        d = time.localtime(a["posted"])
        price = a["price_text"] or (f"{a['price']} €" if a["price"] is not None else "")
        return f'''<html><head><meta charset="utf-8"></head><body>
<div id="msg_div_msg">{html.escape(a['desc'])}<br><br>Zvaniet vakaros.
<table class="options_list"><tr><td class="ads_opt_name">Stāvoklis:</td><td class="ads_opt" id="tdo_1352">lietots</td></tr>
<tr><td class="ads_opt_name">Vieta:</td><td class="ads_opt">Rīga</td></tr></table></div>
<table><tr><td class="ads_opt_name_big">Cena:</td><td class="ads_price" id="tdo_8">{price}</td></tr></table>
<div class="pic_dv_thumbnail"><a href="https://i.ss.lv/gallery/1/2/{a['num']}/x.800.jpg"><img src="https://i.ss.lv/gallery/1/2/{a['num']}/x.t.jpg"></a></div>
<table><tr><td class="msg_footer">Datums: {time.strftime('%d.%m.%Y %H:%M', d)}</td></tr></table>
</body></html>'''


def create_app(mock: MockSS | None = None) -> FastAPI:
    mock = mock or MockSS()
    app = FastAPI(title="SS.lv mock")
    app.state.mock = mock

    @app.middleware("http")
    async def count(request: Request, call_next):
        mock.requests += 1
        if mock.rate_limit and not request.url.path.startswith("/_mock") and request.url.path != "/robots.txt":
            return Response("Too many requests", status_code=429)
        return await call_next(request)

    @app.get("/robots.txt", response_class=PlainTextResponse)
    def robots():
        return "User-agent: *\nDisallow: /en/\nDisallow: /*/add-confirm/\nDisallow: /lv/electronics/secret/\n"

    @app.get("/_mock/state")
    def state():
        return {"ads": len(mock.ads), "requests": mock.requests}

    @app.post("/_mock/new")
    def new(feed: str, title: str, price: float, sub: str = ""):
        return {"path": mock.add_new(feed, sub, title, price)}

    @app.post("/_mock/price")
    def price(path: str, value: float):
        mock.ads[path]["price"] = value
        return {"ok": True}

    @app.post("/_mock/remove")
    def remove(path: str):
        mock.ads[path]["removed"] = True
        return {"ok": True}

    @app.post("/_mock/captcha")
    def captcha(on: bool):
        mock.captcha = on
        return {"ok": True}

    @app.post("/_mock/ratelimit")
    def ratelimit(on: bool):
        mock.rate_limit = on
        return {"ok": True}

    @app.get("/{full_path:path}")
    def catch(full_path: str):
        path = "/" + full_path
        if mock.captcha:
            return HTMLResponse("<html><body><div class='g-recaptcha'></div>Please complete the CAPTCHA</body></html>")
        if path.startswith("/msg/"):
            page = mock.ad_page(path)
            if page is None:
                return RedirectResponse(path.split("/msg")[1].rsplit("/", 1)[0] + "/", status_code=302)
            return HTMLResponse(page)
        page_no = 1
        feed = path
        if path.endswith(".html") and "/page" in path:
            feed, _, rest = path.rpartition("page")
            page_no = int(rest.split(".")[0])
        if path.endswith("/rss/"):
            return HTMLResponse("<html><body>Sludinājumi - SS.LV</body></html>")
        if feed in mock.order:
            body = mock.list_page(feed, page_no)
            if body is None:
                return RedirectResponse(feed, status_code=302)
            return HTMLResponse(body)
        # parent categories exist but list nothing
        return HTMLResponse("<html><body>Nav sludinājumu</body></html>")

    return app


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8899)
    args = ap.parse_args()
    import uvicorn

    uvicorn.run(create_app(), host="127.0.0.1", port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
