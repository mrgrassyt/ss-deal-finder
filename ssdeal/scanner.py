"""SS.lv monitoring jobs (periodic polling — not real-time).

Jobs
* new listings      : page 1.. of each feed until already-known ads appear
* price check       : deeper pages of priority feeds (price changes / reappearances)
* reconciliation    : re-check listings not seen recently via their ad page (removals)
* warm-up backfill  : first start only, builds the market database before notifying
"""
from __future__ import annotations

import time
from dataclasses import dataclass

from .db import Database, jdumps, jloads
from .engine import Engine
from .feeds import effective_feeds
from .fetcher import PoliteFetcher
from .logs import get_logger
from .notify import Notifier
from .parsers import ListRow, looks_like_rss, parse_detail_page, parse_list_page, parse_rss

log = get_logger("scanner")


@dataclass
class RunStats:
    pages: int = 0
    requests: int = 0
    new: int = 0
    updated: int = 0
    removed: int = 0
    error: str | None = None
    ended: bool = False          # the feed had no more pages


class Scanner:
    def __init__(self, db: Database, settings, fetcher: PoliteFetcher, engine: Engine, notifier: Notifier):
        self.db = db
        self.settings = settings
        self.fetcher = fetcher
        self.engine = engine
        self.notifier = notifier
        self.current: str | None = None
        self.feed_last_run: dict[str, float] = {}
        self.paused = False
        self.pending_alerts: list[tuple[int, float, float]] = []

    # ---------------------------------------------------------------- helpers
    def _start_run(self, job: str, feed: str | None) -> int:
        self.current = f"{job}:{feed}" if feed else job
        return self.db.insert("scan_runs", {"job": job, "feed_key": feed, "started_at": time.time()})

    def _end_run(self, run_id: int, st: RunStats) -> None:
        self.current = None
        self.db.update("scan_runs", run_id, {
            "finished_at": time.time(), "ok": 0 if st.error else 1, "pages": st.pages, "requests": st.requests,
            "new_count": st.new, "updated_count": st.updated, "removed_count": st.removed, "error": st.error})
        if st.error:
            self.db.log_error("scanner", st.error)

    def _feed(self, key: str) -> dict | None:
        for f in effective_feeds(self.settings):
            if f["key"] == key:
                return f
        return None

    def page_url(self, feed: dict, page: int) -> str:
        return feed["path"] if page <= 1 else f"{feed['path']}page{page}.html"

    async def fetch_feed_page(self, feed: dict, page: int, st: RunStats) -> list[ListRow] | None:
        # RSS first (lighter) when available for this feed
        if page == 1 and self.settings.get("scan.use_rss_when_available", True):
            mode = self.db.get_meta(f"rss:{feed['key']}")
            if mode != "no":
                res = await self.fetcher.get(feed["path"] + "rss/")
                st.requests += 1
                if res.ok and looks_like_rss(res.text):
                    rows = parse_rss(res.text, self.fetcher.base_url)
                    if rows:
                        if mode != "yes":
                            self.db.set_meta(f"rss:{feed['key']}", "yes")
                            log.event("scanner.rss_detected", feed=feed["key"])
                        st.pages += 1
                        return rows
                if res.blocked:
                    st.error = res.error
                    return None
                self.db.set_meta(f"rss:{feed['key']}", "no")
        res = await self.fetcher.get(self.page_url(feed, page))
        st.requests += 1
        if not res.ok:
            if res.status == 404:
                return []
            st.error = res.error or f"HTTP {res.status}"
            return None
        if page > 1 and res.final_url and f"page{page}" not in res.final_url:
            return []  # SS.lv redirects past-the-end pages back to page 1
        lp = parse_list_page(res.text, self.fetcher.base_url, page)
        st.pages += 1
        for w in lp.warnings:
            log.warning(f"{feed['key']} p{page}: {w}", event="parser.warning")
        return lp.rows

    # ---------------------------------------------------------------- jobs
    async def scan_new(self, feed_key: str, max_pages: int | None = None, notify: bool = True) -> RunStats:
        feed = self._feed(feed_key)
        st = RunStats()
        if not feed:
            st.error = f"unknown feed {feed_key}"
            return st
        run = self._start_run("new", feed_key)
        max_pages = max_pages or int(self.settings.get("scan.max_pages_new", 3))
        candidates: list[int] = []
        try:
            for page in range(1, max_pages + 1):
                rows = await self.fetch_feed_page(feed, page, st)
                if rows is None:
                    break
                if not rows:
                    break
                new_here = 0
                for row in rows:
                    lid, created, changed = self.upsert_row(row, feed)
                    if created:
                        new_here += 1
                        st.new += 1
                        candidates.append(lid)
                    elif changed:
                        st.updated += 1
                        candidates.append(lid)
                if new_here == 0:
                    break
            await self.process_candidates(candidates, notify=notify, st=st)
        except Exception as e:  # never let one feed kill the service
            st.error = f"{type(e).__name__}: {e}"
            log.error(f"scan_new {feed_key} failed", exc_info=True, event="scanner.error")
        self.feed_last_run[feed_key] = time.time()
        self._end_run(run, st)
        if st.new or st.updated:
            log.event("scanner.feed", feed=feed_key, new=st.new, updated=st.updated, pages=st.pages)
        return st

    async def scan_pages(self, feed_key: str, pages: range, job: str = "price", notify: bool = True) -> RunStats:
        feed = self._feed(feed_key)
        st = RunStats()
        if not feed:
            return st
        run = self._start_run(job, feed_key)
        candidates: list[int] = []
        try:
            for page in pages:
                rows = await self.fetch_feed_page(feed, page, st)
                if not rows:
                    st.ended = True
                    break
                st.pages += 1
                for row in rows:
                    lid, created, changed = self.upsert_row(row, feed)
                    if created:
                        st.new += 1
                    if created or changed:
                        st.updated += int(changed)
                        candidates.append(lid)
            await self.process_candidates(candidates, notify=notify, st=st)
        except Exception as e:
            st.error = f"{type(e).__name__}: {e}"
            log.error(f"{job} {feed_key} failed", exc_info=True, event="scanner.error")
        self._end_run(run, st)
        return st

    async def reconcile(self, max_checks: int = 40) -> RunStats:
        """Check listings that have not been seen in list pages recently."""
        st = RunStats()
        run = self._start_run("reconcile", None)
        now = time.time()
        try:
            stale = self.db.query(
                """SELECT * FROM listings WHERE status='active' AND last_seen < ?
                   ORDER BY (saved=1 OR user_state IS NOT NULL) DESC,
                            (classification IN ('GOOD_DEAL','INTERESTING')) DESC, last_seen ASC LIMIT ?""",
                (now - 20 * 3600, max_checks))
            for row in stale:
                if self.fetcher.cooling_down():
                    break
                await self.check_listing(row, st)
            # ads not seen for a long time and never re-checked successfully are expired
            expired = self.db.query("SELECT id FROM listings WHERE status='active' AND last_seen < ?",
                                    (now - 21 * 86400,))
            for r in expired:
                self._mark_removed(r["id"], "not seen for 21 days (assumed expired)")
                st.removed += 1
        except Exception as e:
            st.error = f"{type(e).__name__}: {e}"
            log.error("reconcile failed", exc_info=True, event="scanner.error")
        self._end_run(run, st)
        return st

    async def check_listing(self, row: dict, st: RunStats | None = None) -> dict:
        """Fetch one ad page: refresh details or detect removal."""
        st = st or RunStats()
        res = await self.fetcher.get(row["url"])
        st.requests += 1
        if res.blocked or (res.error and res.status not in (404, 410)):
            return {"ok": False, "error": res.error}
        det = parse_detail_page(res.text, self.fetcher.base_url, res.status, res.final_url)
        if det.removed:
            self._mark_removed(row["id"], "ad page removed")
            st.removed += 1
            return {"ok": True, "removed": True}
        self._apply_detail(row, det)
        st.updated += 1
        return {"ok": True, "removed": False}

    # ---------------------------------------------------------------- persistence
    def upsert_row(self, row: ListRow, feed: dict) -> tuple[int, bool, bool]:
        now = time.time()
        existing = self.db.one("SELECT * FROM listings WHERE ss_id=?", (row.ss_id,))
        if existing:
            changes: dict = {"last_seen": now}
            changed = False
            if existing["status"] == "removed":
                changes.update(status="active", removed_at=None)
                self._event(existing["id"], "reappeared", {})
                changed = True
            if row.price is not None and existing["price"] is not None and abs(row.price - existing["price"]) >= 0.01:
                changes.update(price=row.price, price_text=row.price_text,
                               min_price=min(existing["min_price"] or row.price, row.price))
                self.db.insert("price_history", {"listing_id": existing["id"], "price": row.price, "observed_at": now})
                self._event(existing["id"], "price_change", {"from": existing["price"], "to": row.price})
                log.event("listing.price_change", listing_id=existing["id"], title=existing["title"][:80],
                          old=existing["price"], new=row.price)
                if row.price < existing["price"] and (existing["saved"] or self._watched_with_drops(existing["id"])):
                    self.pending_alerts.append((existing["id"], existing["price"], row.price))
                changed = True
            elif row.price is not None and existing["price"] is None:
                changes.update(price=row.price, price_text=row.price_text, initial_price=row.price, min_price=row.price)
                changed = True
            if row.image_url and not existing["image_url"]:
                changes["image_url"] = row.image_url
            self.db.update("listings", existing["id"], changes)
            return existing["id"], False, changed
        a = self.engine.analyze(row.title, "", row.ss_id, feed["category"], row.attrs, row.price_kind)
        rec = {
            "ss_id": row.ss_id, "ss_num": row.ss_num, "url": row.url, "feed_key": feed["key"],
            "category_path": a["category_path"], "category_key": a["category_key"], "title": row.title,
            "description": None, "price": row.price, "price_text": row.price_text, "location": row.location,
            "attrs": jdumps(row.attrs), "image_url": row.image_url, "product_key": a["product_key"],
            "product_name": a["product_name"], "brand": a["brand"], "condition": a["condition"],
            "flags": jdumps(a["flags"]), "is_buying": a["is_buying"], "fingerprint": a["fingerprint"],
            "status": "active", "first_seen": now, "last_seen": now, "posted_at": row.posted_at,
            "initial_price": row.price, "min_price": row.price,
        }
        lid = self.db.insert("listings", rec)
        if row.price is not None:
            self.db.insert("price_history", {"listing_id": lid, "price": row.price, "observed_at": now})
        rep = self.engine.find_repost(lid, a["fingerprint"], row.title, a["category_key"], a["product_key"])
        if rep:
            self.db.update("listings", lid, {"repost_of": rep["id"]})
            self._event(lid, "repost", {"of": rep["id"], "previous_price": rep["price"]})
        self._event(lid, "created", {"price": row.price})
        log.event("listing.new", listing_id=lid, title=row.title[:100], price=row.price,
                  product=a["product_key"], category=a["category_key"], condition=a["condition"], flags=a["flags"])
        return lid, True, False

    def _apply_detail(self, row: dict, det) -> None:
        now = time.time()
        attrs = {**jloads(row.get("attrs"), {}), **det.attrs}
        a = self.engine.analyze(row["title"] or "", det.description, row["ss_id"], row["category_key"] or "other",
                                attrs, det.price_kind)
        changes = {
            "description": det.description[:8000], "attrs": jdumps(attrs), "photos": jdumps(det.photos),
            "detail_fetched": now, "last_seen": now, "category_key": a["category_key"],
            "product_key": a["product_key"] or (None if set(a["flags"]) & {"part", "accessory"} else row.get("product_key")),
            "product_name": a["product_name"] or (None if set(a["flags"]) & {"part", "accessory"} else row.get("product_name")),
            "brand": a["brand"] or row.get("brand"),
            "condition": a["condition"], "flags": jdumps(a["flags"]), "is_buying": a["is_buying"],
            "fingerprint": a["fingerprint"],
        }
        if det.posted_at:
            changes["posted_at"] = det.posted_at
        if det.location:
            changes["location"] = det.location
        if det.price is not None and row.get("price") is not None and abs(det.price - row["price"]) >= 0.01:
            changes["price"] = det.price
            changes["min_price"] = min(row.get("min_price") or det.price, det.price)
            self.db.insert("price_history", {"listing_id": row["id"], "price": det.price, "observed_at": now})
            self._event(row["id"], "price_change", {"from": row["price"], "to": det.price})
        self.db.update("listings", row["id"], changes)
        self._event(row["id"], "detail", {"chars": len(det.description), "photos": len(det.photos)})

    def _mark_removed(self, lid: int, reason: str) -> None:
        self.db.update("listings", lid, {"status": "removed", "removed_at": time.time()})
        self._event(lid, "removed", {"reason": reason})
        log.event("listing.removed", listing_id=lid, reason=reason)

    def _event(self, lid: int, etype: str, data: dict) -> None:
        self.db.insert("listing_events", {"listing_id": lid, "type": etype, "data": jdumps(data), "at": time.time()})

    # ---------------------------------------------------------------- scoring + notifying
    async def process_candidates(self, ids: list[int], notify: bool = True, st: RunStats | None = None,
                                 details: bool | None = None) -> None:
        if self.pending_alerts and notify:
            await self.flush_alerts()
        if not ids:
            return
        st = st or RunStats()
        min_score = float(self.settings.get("scan.detail_fetch_min_score", 45))
        max_detail = int(self.settings.get("scan.detail_fetch_max_per_cycle", 15))
        if details is None:
            details = notify  # the warm-up backfill reads list pages only (far fewer requests)
        if not details:
            max_detail = 0
        fetched = 0
        # Score everything from the list data first, then handle the most promising ads first: a deal that is 15th on
        # the page used to wait behind 14 ordinary detail-page fetches (~5 s each) before it was notified.
        first: list[tuple[float, int, dict]] = []
        for lid in dict.fromkeys(ids):
            row = self.db.one("SELECT * FROM listings WHERE id=?", (lid,))
            if not row:
                continue
            res = self.engine.evaluate(row)
            self.engine.apply_scores(lid, res)
            rank = {"GOOD_DEAL": 2, "INTERESTING": 1}.get(res["classification"], 0) * 1000 + float(res["deal_score"] or 0) \
                + (500 if res["watch_hits"] else 0) + float(res["personal_score"] or 0) * 0.5
            first.append((rank, lid, res))
        first.sort(key=lambda x: -x[0])
        for _, lid, res in first:
            row = self.db.one("SELECT * FROM listings WHERE id=?", (lid,))
            if not row:
                continue
            flags = set(jloads(row["flags"], []))
            wants_detail = (not row["detail_fetched"] and not row["is_buying"] and "service" not in flags and (
                res["classification"] != "IGNORE" or res["deal_score"] >= min_score or
                res["personal_score"] >= min_score + 15 or bool(res["watch_hits"]) or
                row["condition"] in ("broken", "parts", "untested") or flags & {"bundle", "collection"}))
            if wants_detail and fetched < max_detail and not self.fetcher.cooling_down():
                fetched += 1
                await self.check_listing(row, st)
                row = self.db.one("SELECT * FROM listings WHERE id=?", (lid,))
                if not row or row["status"] == "removed":
                    continue
                res = self.engine.evaluate(row)
                self.engine.apply_scores(lid, res)
            self._record_watch_matches(row, res)
            log.event("listing.scored", listing_id=lid, deal=res["deal_score"], personal=res["personal_score"],
                      level=res["classification"], confidence=res["confidence"],
                      reason=res["score_details"]["classification_reason"],
                      headline=res["score_details"]["deal"]["headline"])
            if notify and res["classification"] != "IGNORE":
                try:
                    full = dict(self.db.one("SELECT * FROM listings WHERE id=?", (lid,)))
                    ok, why = self.notifier.should_notify(full, res["classification"])
                    if ok:
                        reason = res["score_details"]["deal"]["headline"] or res["score_details"]["classification_reason"]
                        await self.notifier.notify(full, res["classification"], reason, why)
                except Exception as e:  # noqa: BLE001 — a notification problem must never stop the rest of the scan
                    log.error(f"notifying listing {lid} failed: {e}", exc_info=True, event="notify.error")
        # price drops found during this scan go out now, not at the start of the next scan
        if self.pending_alerts and notify:
            await self.flush_alerts()

    def _watched_with_drops(self, lid: int) -> bool:
        return bool(self.db.scalar(
            """SELECT COUNT(*) FROM watch_matches m JOIN watchlist w ON w.id=m.watch_id
               WHERE m.listing_id=? AND w.active=1 AND w.notify_drops=1""", (lid,), 0))

    async def flush_alerts(self) -> None:
        """Price-drop alerts for saved and watch-listed listings (sent even if not a 'deal')."""
        while self.pending_alerts:
            lid, old, new = self.pending_alerts.pop(0)
            row = self.db.one("SELECT * FROM listings WHERE id=?", (lid,))
            if not row:
                continue
            title = f"📉 Price drop: {row['product_name'] or row['title'][:60]}"
            body = f"€{old:.0f} → €{new:.0f} ({(old - new) / old * 100:.0f}% lower)" + (
                f" · profit ~€{row['profit_est']:.0f}" if row.get("profit_est") is not None else "")
            try:
                await self.notifier.notify_text(title, body, row["url"], listing_id=lid)
            except Exception as e:  # noqa: BLE001
                log.error(f"price-drop alert failed: {e}", event="notify.error")
            log.event("notify.price_drop", listing_id=lid, old=old, new=new)

    def _record_watch_matches(self, row: dict, res: dict) -> None:
        for w in res["watch_hits"]:
            self.db.execute("INSERT OR IGNORE INTO watch_matches(watch_id, listing_id, matched_at, price) VALUES(?,?,?,?)",
                            (w["id"], row["id"], time.time(), row["price"]))

    # ---------------------------------------------------------------- older listings
    async def history_step(self) -> dict:
        """Walk deeper into the enabled feeds, beyond the warm-up depth, so older ads that are still for sale show up in
        Listings and the price model gets more comparables (higher confidence). A step fetches only a few pages in
        total, taking turns between feeds, so it never delays the checks for new listings; the next step continues
        where this one stopped. A feed that is done starts over after a day (prices and ads change). No alerts."""
        depth = int(self.settings.get("scan.history_pages", 40))
        budget = int(self.settings.get("scan.history_pages_per_step", 6))
        start0 = int(self.settings.get("scan.backfill_pages", 4)) + 1
        cur = dict(self.settings.get("scan.history_cursor", {}) or {})
        out = {"pages": 0, "new": 0}
        if depth < start0:
            return out
        feeds = [f["key"] for f in effective_feeds(self.settings) if f["enabled"]]
        now = time.time()
        for k in feeds:
            c = cur.get(k) or {"page": start0, "done_at": 0}
            if c["done_at"] and now - c["done_at"] >= 86400:
                c = {"page": start0, "done_at": 0}
            cur[k] = c
        todo = [k for k in feeds if not cur[k]["done_at"]]
        tries = 0
        while todo and tries < budget and not self.paused and not self.fetcher.cooling_down():
            tries += 1
            k = min(todo, key=lambda x: cur[x]["page"])            # the feed that is furthest behind goes first
            c = cur[k]
            st = await self.scan_pages(k, range(c["page"], c["page"] + 1), job="history", notify=False)
            if st.error:
                todo.remove(k)
                continue
            out["pages"] += st.pages
            out["new"] += st.new
            c["page"] += 1
            if st.ended or c["page"] > depth:
                c["done_at"] = time.time()
                todo.remove(k)
        self.settings.set("scan.history_cursor", cur)
        if out["new"]:
            log.event("scanner.history", **out)
        return out

    # ---------------------------------------------------------------- warm-up
    async def backfill(self, pages: int | None = None) -> dict:
        pages = pages if pages is not None else int(self.settings.get("scan.backfill_pages", 4))
        total = RunStats()
        feeds = [f for f in effective_feeds(self.settings) if f["enabled"]]
        feeds.sort(key=lambda f: not f["priority"])
        log.event("scanner.backfill_start", feeds=len(feeds), pages=pages)
        for f in feeds:
            if self.paused:
                break
            st = await self.scan_pages(f["key"], range(1, pages + 1), job="backfill", notify=False)
            total.new += st.new
            total.requests += st.requests
            if st.error and self.fetcher.cooling_down():
                break
            self.feed_last_run[f["key"]] = time.time()
        self.engine.market.recalc_all()
        self.engine.rescore_all()
        # fetch the full text of the most promising backfilled ads so their scores use complete information
        top = self.db.query(
            """SELECT id FROM listings WHERE status='active' AND detail_fetched IS NULL AND classification!='IGNORE'
               ORDER BY deal_score DESC LIMIT ?""", (int(self.settings.get("scan.detail_fetch_max_per_cycle", 15)) * 2,))
        st = RunStats()
        for r in top:
            if self.paused or self.fetcher.cooling_down():
                break
            row = self.db.one("SELECT * FROM listings WHERE id=?", (r["id"],))
            await self.check_listing(row, st)
            row = self.db.one("SELECT * FROM listings WHERE id=?", (r["id"],))
            if row and row["status"] == "active":
                self.engine.apply_scores(row["id"], self.engine.evaluate(row))
        total.requests += st.requests
        log.event("scanner.backfill_done", new=total.new, requests=total.requests)
        return {"new": total.new, "requests": total.requests}
