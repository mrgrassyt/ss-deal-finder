"""Parsers for SS.lv list pages, ad (detail) pages and RSS feeds.

The parsers are deliberately defensive: SS.lv markup is old-school table
HTML and categories have different columns. Every field is optional and the
parser reports what it could not find instead of crashing.
"""
from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from email.utils import parsedate_to_datetime
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

ROW_ID = re.compile(r"^tr_(\d+)$")
PAGE_RE = re.compile(r"/page(\d+)\.html")
MSG_RE = re.compile(r"/msg/[a-z]{2}/[^\"'\s<>]+?\.html")
PRICE_NUM = re.compile(r"(\d[\d\s.,]*)\s*(€|eur|euro)", re.I)

BUYING_WORDS = ("pērku", "perku", "куплю", "nopirkšu", "meklēju", "meklēju", "ищу")
EXCHANGE_WORDS = ("maiņai", "maiņa", "обмен", "меняю")
FREE_WORDS = ("bez maksas", "par velti", "бесплатно", "atdodu")
RENT_MARKERS = ("/mēn", "/men", "/dien", "/st", "/мес", "/день", "/nedēļ")


@dataclass
class ListRow:
    ss_id: str                    # canonical path /msg/lv/.../xxx.html
    url: str
    ss_num: str | None = None
    title: str = ""
    price: float | None = None
    price_text: str = ""
    price_kind: str = "unknown"   # sale | buying | exchange | free | rent | unknown
    image_url: str | None = None
    location: str | None = None
    attrs: dict = field(default_factory=dict)
    posted_at: float | None = None


@dataclass
class ListPage:
    rows: list[ListRow]
    page: int = 1
    has_next: bool = False
    total_hint: int | None = None
    warnings: list[str] = field(default_factory=list)


@dataclass
class AdDetail:
    removed: bool = False
    description: str = ""
    price: float | None = None
    price_text: str = ""
    price_kind: str = "unknown"
    attrs: dict = field(default_factory=dict)
    photos: list[str] = field(default_factory=list)
    posted_at: float | None = None
    location: str | None = None
    warnings: list[str] = field(default_factory=list)


def clean(text: str | None) -> str:
    if not text:
        return ""
    return re.sub(r"\s+", " ", text.replace("\xa0", " ")).strip()


def parse_price(text: str) -> tuple[float | None, str]:
    t = clean(text).lower()
    if not t:
        return None, "unknown"
    if any(w in t for w in BUYING_WORDS):
        return None, "buying"
    m = PRICE_NUM.search(t)
    if not m:
        if any(w in t for w in EXCHANGE_WORDS):
            return None, "exchange"
        if any(w in t for w in FREE_WORDS):
            return 0.0, "free"
        bare = re.fullmatch(r"(\d[\d\s.,]*)", t)
        if not bare:
            return None, "unknown"
        num = bare.group(1)
    else:
        num = m.group(1)
    value = _to_number(num)
    if value is None:
        return None, "unknown"
    tail = t[m.end():] if m else ""
    if any(r in tail[:8] for r in RENT_MARKERS):
        return value, "rent"
    return value, "sale"


def _to_number(num: str) -> float | None:
    s = num.replace(" ", "").strip(".,")
    if not s:
        return None
    # "1,200" / "1.200" thousands vs "9.90" / "9,90" decimals
    if "," in s and "." in s:
        s = s.replace(",", "")
    elif "," in s:
        head, _, tail = s.rpartition(",")
        s = s.replace(",", "") if len(tail) == 3 else head.replace(",", "") + "." + tail
    elif s.count(".") >= 1:
        head, _, tail = s.rpartition(".")
        if len(tail) == 3 and s.count(".") >= 1 and len(head) <= 3 and not head.startswith("0"):
            s = s.replace(".", "")
    try:
        return float(s)
    except ValueError:
        return None


def canonical_msg_path(href: str) -> str | None:
    if not href:
        return None
    path = urlparse(href).path or href
    m = MSG_RE.search(path)
    if not m:
        return None
    p = m.group(0)
    # use the Latvian path as the canonical identity (ru mirrors the same ad)
    return re.sub(r"^/msg/[a-z]{2}/", "/msg/lv/", p)


def parse_ss_date(text: str) -> float | None:
    m = re.search(r"(\d{2})\.(\d{2})\.(\d{4})\.?\s+(\d{1,2}):(\d{2})", text or "")
    if not m:
        return None
    d, mo, y, h, mi = map(int, m.groups())
    try:
        return time.mktime((y, mo, d, h, mi, 0, 0, 0, -1))
    except (OverflowError, ValueError):
        return None


# ---------------------------------------------------------------- list pages

def parse_list_page(html: str, base_url: str, page: int = 1) -> ListPage:
    soup = BeautifulSoup(html, "lxml")
    warnings: list[str] = []
    headers = _header_names(soup)
    rows: list[ListRow] = []
    seen: set[str] = set()
    for tr in soup.find_all("tr", id=ROW_ID):
        row = _parse_row(tr, base_url, headers)
        if row and row.ss_id not in seen:
            seen.add(row.ss_id)
            rows.append(row)
    if not rows:
        # Fallback: any links to ads (markup change) — keeps monitoring alive.
        for a in soup.find_all("a", href=MSG_RE):
            path = canonical_msg_path(a.get("href"))
            if not path or path in seen:
                continue
            text = clean(a.get_text(" "))
            if not text:
                continue
            seen.add(path)
            rows.append(ListRow(ss_id=path, url=urljoin(base_url, path), title=text))
        if rows:
            warnings.append("list table rows not found; used link fallback (prices unavailable)")
    nxt = page + 1
    has_next = bool(soup.find("a", href=re.compile(rf"/page{nxt}\.html"))) or bool(
        soup.find("a", attrs={"rel": "next"})
    )
    return ListPage(rows=rows, page=page, has_next=has_next, warnings=warnings)


def _header_names(soup: BeautifulSoup) -> list[str]:
    head = soup.find("tr", id="head_line")
    if not head:
        return []
    return [clean(td.get_text(" ")) for td in head.find_all("td")]


def _parse_row(tr, base_url: str, headers: list[str]) -> ListRow | None:
    m = ROW_ID.match(tr.get("id", ""))
    num = m.group(1) if m else None
    link = tr.find("a", class_="am") or tr.find("a", href=MSG_RE)
    if not link:
        return None
    path = canonical_msg_path(link.get("href", ""))
    if not path:
        return None
    title = clean(link.get_text(" "))
    img = tr.find("img")
    image_url = None
    if img:
        src = img.get("src") or img.get("data-src")
        if src and "gallery" in src:
            image_url = urljoin(base_url, src)
    tds = tr.find_all("td", recursive=False) or tr.find_all("td")
    title_idx = None
    for i, td in enumerate(tds):
        if link in td.find_all("a"):
            title_idx = i
    if not title:
        title = clean(tds[title_idx].get_text(" ")) if title_idx is not None else ""
    values = [clean(td.get_text(" ")) for td in tds[(title_idx + 1 if title_idx is not None else 0):]]
    # header names line up with the full row; take the trailing part
    hdr = headers[-len(values):] if headers and len(headers) >= len(values) else [""] * len(values)
    attrs: dict = {}
    price_text = ""
    for name, val in zip(hdr, values):
        if not val:
            continue
        lname = name.lower()
        if "€" in val or lname.startswith("cena") or lname.startswith("цена"):
            price_text = val
        elif name:
            attrs[name.rstrip(":").strip()] = val
    if not price_text:
        for val in reversed(values):
            if "€" in val or any(w in val.lower() for w in BUYING_WORDS + EXCHANGE_WORDS):
                price_text = val
                break
    price, kind = parse_price(price_text)
    location = None
    for k in list(attrs):
        if k.lower() in ("pilsēta", "pilsēta, rajons", "vieta", "reģions", "город"):
            location = attrs[k]
    if kind == "unknown" and any(w in title.lower() for w in BUYING_WORDS):
        kind = "buying"
    return ListRow(ss_id=path, url=urljoin(base_url, path), ss_num=num, title=title, price=price,
                   price_text=price_text, price_kind=kind, image_url=image_url, location=location, attrs=attrs)


# ---------------------------------------------------------------- detail pages

REMOVED_MARKERS = ("sludinājums ir dzēsts", "sludinājums dzēsts", "объявление удалено",
                   "sludinājums nav atrasts", "объявление не найдено", "ad has been deleted")


def parse_detail_page(html: str, base_url: str, status: int = 200, final_url: str = "") -> AdDetail:
    det = AdDetail()
    if status == 404 or status == 410:
        det.removed = True
        return det
    if final_url and "/msg/" not in final_url:
        det.removed = True  # SS.lv redirects deleted ads back to the category
        return det
    low = html[:60000].lower()
    soup = BeautifulSoup(html, "lxml")
    body = soup.find(id="msg_div_msg")
    if body is None:
        if any(mk in low for mk in REMOVED_MARKERS):
            det.removed = True
            return det
        det.warnings.append("description block #msg_div_msg not found")
    else:
        # attributes table (Ražotājs, Modelis, Stāvoklis ...)
        for name_td in body.find_all("td", class_="ads_opt_name"):
            val_td = name_td.find_next_sibling("td")
            if val_td is None:
                continue
            name = clean(name_td.get_text(" ")).rstrip(":").strip()
            val = clean(val_td.get_text(" "))
            if name and val:
                det.attrs[name] = val
        body_copy = BeautifulSoup(str(body), "lxml")
        for t in body_copy.find_all(["table", "script", "style"]):
            t.decompose()
        for br in body_copy.find_all("br"):
            br.replace_with("\n")
        txt = body_copy.get_text("")
        det.description = "\n".join(clean(x) for x in txt.splitlines() if clean(x)).strip()
    # price
    ptd = soup.find("td", class_="ads_price") or soup.find(id="tdo_8")
    if ptd:
        det.price_text = clean(ptd.get_text(" "))
    else:
        for name, val in det.attrs.items():
            if name.lower().startswith("cena"):
                det.price_text = val
    det.price, det.price_kind = parse_price(det.price_text)
    # date
    for td in soup.find_all("td", class_="msg_footer"):
        t = clean(td.get_text(" "))
        if "datums" in t.lower() or "дата" in t.lower():
            det.posted_at = parse_ss_date(t)
    if det.posted_at is None:
        det.posted_at = parse_ss_date(clean(soup.get_text(" "))[-3000:])
    # location from attributes
    for k, v in det.attrs.items():
        if k.lower() in ("vieta", "pilsēta", "pilsēta, rajons", "rajons", "место"):
            det.location = v
    # photos
    photos: list[str] = []
    for a in soup.find_all("a", href=True):
        h = a["href"]
        if "/gallery/" in h and re.search(r"\.(jpg|jpeg|png|webp)$", h, re.I):
            u = urljoin(base_url, h)
            if u not in photos:
                photos.append(u)
    if not photos:
        for img in soup.find_all("img", src=True):
            s = img["src"]
            if "/gallery/" in s:
                u = urljoin(base_url, re.sub(r"\.t\.jpg$|\.th2\.jpg$", ".800.jpg", s))
                if u not in photos:
                    photos.append(u)
    det.photos = photos[:20]
    return det


# ---------------------------------------------------------------- RSS

def looks_like_rss(text: str) -> bool:
    head = text[:500].lower()
    return "<rss" in head or "<channel" in text[:2000].lower()


def parse_rss(xml: str, base_url: str) -> list[ListRow]:
    soup = BeautifulSoup(xml, "xml")
    rows: list[ListRow] = []
    for item in soup.find_all("item"):
        lt = item.find("link")
        link = clean(lt.get_text()) if lt else ""
        path = canonical_msg_path(link)
        if not path:
            continue
        title = clean(item.find("title").get_text()) if item.find("title") else ""
        desc_html = item.find("description").get_text() if item.find("description") else ""
        dsoup = BeautifulSoup(desc_html, "lxml")
        img = dsoup.find("img")
        dtext = clean(dsoup.get_text(" "))
        m = re.search(r"(?:cena|цена)\s*:?\s*([^\n]*?€)", dtext, re.I)
        price_text = m.group(1) if m else ""
        if not price_text:
            m2 = PRICE_NUM.search(dtext)
            price_text = m2.group(0) if m2 else ""
        price, kind = parse_price(price_text)
        posted = None
        pd = item.find("pubDate")
        if pd:
            try:
                posted = parsedate_to_datetime(clean(pd.get_text())).timestamp()
            except (TypeError, ValueError):
                posted = None
        rows.append(ListRow(ss_id=path, url=urljoin(base_url, path), title=title or dtext[:200],
                            price=price, price_text=price_text, price_kind=kind,
                            image_url=urljoin(base_url, img["src"]) if img and img.get("src") else None,
                            posted_at=posted))
    return rows
