"""Notification routing: Windows toasts, phone (ntfy and Telegram), Discord, and the in-app feed.

Rules that keep delivery reliable:
* every channel is sent separately and can never raise: one broken channel cannot stop the others or the scan;
* what each channel answered is stored on the notification (channels + push_errors), and Settings can send a test;
* pushes held back by the hourly limit or quiet hours are queued (push_pending) and sent later, not dropped;
* the in-app feed uses a running sequence number, not clock times (a phone with a fast clock missed events).
"""
from __future__ import annotations

import asyncio
import html
import os
import sys
import time
from pathlib import Path

import httpx

from . import wintoast
from .db import Database, jdumps
from .logs import get_logger

log = get_logger("notify")

LEVEL_RANK = {"IGNORE": 0, "INTERESTING": 1, "GOOD_DEAL": 2}
PUSH_CHANNELS = ("desktop", "ntfy", "telegram", "discord")
PENDING_MAX_AGE = 3 * 3600          # a held push older than this is no longer worth sending


def in_quiet_hours(cfg: dict, now: float | None = None) -> bool:
    if not cfg.get("enabled"):
        return False
    t = time.localtime(now or time.time())
    cur = t.tm_hour * 60 + t.tm_min
    try:
        sh, sm = map(int, cfg.get("start", "23:00").split(":"))
        eh, em = map(int, cfg.get("end", "07:30").split(":"))
    except ValueError:
        return False
    s, e = sh * 60 + sm, eh * 60 + em
    return (s <= cur < e) if s < e else (cur >= s or cur < e)


class Notifier:
    def __init__(self, db: Database, settings, home: Path | None = None):
        self.db = db
        self.settings = settings
        self.home = home
        self.discord_queue: asyncio.Queue | None = None    # set by the Discord bot
        self.discord_online = lambda: False                 # replaced by the bot
        self.ui_events: list[dict] = []                     # in-app feed, read by the UI with ?after=<seq>
        self.seq = 0
        self.local_url = "http://127.0.0.1:8765"
        self._toast_registered = None

    # ---------------------------------------------------------------- decision
    def should_notify(self, listing: dict, level: str) -> tuple[bool, str]:
        if level == "IGNORE":
            return False, "ignore"
        if listing.get("user_state") in ("ignored", "bought") and not listing.get("_force"):
            return False, "user already handled this listing"
        prev = self.db.one("SELECT * FROM notifications WHERE listing_id=? ORDER BY id DESC LIMIT 1", (listing["id"],))
        if listing.get("repost_of") and not prev:
            prev = self.db.one("SELECT * FROM notifications WHERE listing_id=? ORDER BY id DESC LIMIT 1",
                               (listing["repost_of"],))
            if prev and prev["price"] is not None and listing.get("price") is not None and listing["price"] >= prev["price"]:
                return False, "repost of an already-notified listing at the same or higher price"
            prev = None
        if not prev:
            hours = float(self.settings.get("notify.max_age_hours", 12) or 0)
            posted = listing.get("posted_at")
            if hours and posted and time.time() - posted > hours * 3600:
                return False, f"ad is older than {hours:g} h (not notified; it stays in Listings)"
            return True, "new"
        pct = float(self.settings.get("notify.renotify_price_drop_pct", 8)) / 100
        if prev["price"] and listing.get("price") is not None and listing["price"] <= prev["price"] * (1 - pct):
            return True, f"price dropped from €{prev['price']:.0f} to €{listing['price']:.0f}"
        if LEVEL_RANK[level] > LEVEL_RANK.get(prev["level"], 0):
            return True, f"upgraded to {level}"
        return False, "already notified"

    def is_high_roi(self, listing: dict) -> bool:
        n = self.settings.get("notify", {})
        pct = float(n.get("high_roi_pct", 40) or 0)
        roi, profit = listing.get("roi_est"), listing.get("profit_est")
        return bool(pct and roi is not None and roi >= pct and (profit or 0) >= float(n.get("high_roi_min_profit", 15) or 0))

    def wanted_channels(self, level: str, high_roi: bool = False) -> list[str]:
        n = self.settings.get("notify", {})
        good = level == "GOOD_DEAL" or high_roi
        out = []
        if not (os.environ.get("SSDEAL_SERVER") or os.environ.get("SSDEAL_MANAGED")) and (n.get("desktop_good") if good else n.get("desktop_interesting")):
            out.append("desktop")
        if self.settings.get("ntfy.enabled") and (n.get("ntfy_good") if good else n.get("ntfy_interesting")):
            out.append("ntfy")
        if self.settings.get("telegram.enabled") and (n.get("telegram_good", True) if good else n.get("telegram_interesting")):
            out.append("telegram")
        if self.settings.get("discord.enabled") and (n.get("discord_good") if good else n.get("discord_interesting")):
            out.append("discord")
        return out

    def pushes_last_hour(self) -> int:
        return int(self.db.scalar("SELECT COUNT(*) FROM notifications WHERE pushed_at > ?", (time.time() - 3600,), default=0))

    def _hold_reason(self, high_roi: bool) -> str:
        n = self.settings.get("notify", {})
        if in_quiet_hours(n.get("quiet_hours", {})) and not high_roi:
            return "quiet hours"
        cap = int(n.get("max_per_hour", 8) or 0)
        if cap and self.pushes_last_hour() >= cap and not high_roi:
            return f"hourly limit ({cap}) reached"
        return ""

    # ---------------------------------------------------------------- message
    def message(self, listing: dict, level: str, reason: str, nid: int | None) -> dict:
        high = self.is_high_roi(listing)
        name = listing.get("product_name") or (listing.get("title") or "")[:60]
        pe, ro = listing.get("profit_est"), listing.get("roi_est")
        if high:
            title = f"🚀 HIGH ROI {ro:.0f}%: {name}"
        else:
            title = f"{'🔥 Good deal' if level == 'GOOD_DEAL' else '👀 Interesting'}: {name}"
        money = f"Buy €{listing.get('price') or 0:.0f}"
        if pe is not None:
            money += f" · profit ~€{pe:.0f}" + (f" · ROI ~{ro:.0f}%" if ro is not None else "")
        if listing.get("personal_score"):
            money += f" · for you {listing['personal_score']:.0f}"
        app_link = f"{self.local_url}/#/notifications?listing={listing['id']}"
        return {"nid": nid, "listing_id": listing["id"], "level": level, "high_roi": high, "roi": ro, "profit": pe,
                "title": title, "body": f"{money}\n{reason}", "url": listing.get("url"), "app_url": app_link}

    # ---------------------------------------------------------------- send
    async def notify(self, listing: dict, level: str, reason: str, why_now: str) -> int | None:
        n = self.settings.get("notify", {})
        warm = not self.settings.get("scan.warmup_complete", False) and n.get("suppress_during_warmup", True)
        high = self.is_high_roi(listing)
        want = [] if warm else self.wanted_channels(level, high)
        hold = self._hold_reason(high) if want else ""
        nid = self.db.insert("notifications", {
            "listing_id": listing["id"], "level": level,
            "reason": (reason + (f" — {why_now}" if why_now not in ("new",) else ""))[:500],
            "price": listing.get("price"), "channels": jdumps(["app"]), "created_at": time.time(),
            "high_roi": 1 if high else 0, "push_pending": 1 if (want and hold) else 0,
            "push_errors": jdumps({"held": hold}) if hold else None})
        msg = self.message(listing, level, reason, nid)
        self._ui_event(msg)
        if want and not hold:
            await self._push(nid, msg, want)
        log.event("notify.created", level=level, listing_id=listing["id"], wanted=want, held=hold, high_roi=high, warmup=warm)
        return nid

    def _ui_event(self, msg: dict) -> None:
        self.seq += 1
        self.ui_events.append({"seq": self.seq, "id": msg.get("nid"), "level": "HIGH_ROI" if msg.get("high_roi") else msg["level"],
                               "title": msg["title"], "body": msg["body"], "listing_id": msg.get("listing_id"),
                               "url": msg.get("url"), "at": time.time()})
        self.ui_events = self.ui_events[-200:]

    async def _push(self, nid: int | None, msg: dict, channels: list[str]) -> dict:
        """Send to each channel independently. Returns {channel: '' (ok) | error text}."""
        result: dict[str, str] = {}
        for ch in channels:
            try:
                result[ch] = await getattr(self, f"_send_{ch}")(msg)
            except Exception as e:  # noqa: BLE001 — a channel must never break the others or the scan
                result[ch] = f"{type(e).__name__}: {e}"
            if result[ch]:
                log.warning(f"{ch} notification failed: {result[ch]}", event="notify.channel_failed", channel=ch)
        if nid is not None:
            ok = [c for c, err in result.items() if not err]
            errors = {c: err for c, err in result.items() if err}
            self.db.update("notifications", nid, {"channels": jdumps(["app"] + ok), "pushed_at": time.time() if ok else None,
                                                  "push_pending": 0, "push_errors": jdumps(errors) if errors else None})
        log.event("notify.sent", nid=nid, result={c: (e or "ok") for c, e in result.items()})
        return result

    async def flush_pending(self) -> int:
        """Send pushes that waited for the hourly limit or quiet hours. Called by the scheduler every few seconds."""
        sent = 0
        for note in self.db.query("SELECT * FROM notifications WHERE push_pending=1 ORDER BY high_roi DESC, id LIMIT 20"):
            listing = self.db.one("SELECT * FROM listings WHERE id=?", (note["listing_id"],))
            if (not listing or time.time() - note["created_at"] > PENDING_MAX_AGE or listing.get("status") == "removed"
                    or listing.get("user_state") in ("ignored", "bought")):
                self.db.update("notifications", note["id"], {"push_pending": 0, "push_errors": jdumps({"held": "expired before it could be sent"})})
                continue
            high = self.is_high_roi(listing)
            if self._hold_reason(high):
                break
            want = self.wanted_channels(note["level"], high)
            if want:
                await self._push(note["id"], self.message(listing, note["level"], note["reason"] or "", note["id"]), want)
                sent += 1
            else:
                self.db.update("notifications", note["id"], {"push_pending": 0})
        return sent

    async def notify_text(self, title: str, body: str, url: str | None = None, discord: bool = True, listing_id: int | None = None) -> None:
        """Price drops, reminders and system messages (not limited by the hourly cap)."""
        msg = {"nid": None, "listing_id": listing_id, "level": "REMINDER", "high_roi": False, "title": title, "body": body,
               "url": url, "app_url": f"{self.local_url}/#/listings?listing={listing_id}" if listing_id else None}
        self._ui_event(msg)
        chans = ["desktop"] if (not (os.environ.get("SSDEAL_SERVER") or os.environ.get("SSDEAL_MANAGED")) and self.settings.get("notify.desktop_good", True)) else []
        if self.settings.get("ntfy.enabled"):
            chans.append("ntfy")
        if self.settings.get("telegram.enabled"):
            chans.append("telegram")
        if discord and self.settings.get("discord.enabled"):
            chans.append("discord")
        if in_quiet_hours(self.settings.get("notify.quiet_hours", {}) or {}):
            chans = []
        await self._push(None, msg, chans)

    async def test(self, channel: str) -> dict:
        """Settings → 'Send test': really send through one channel and report the answer."""
        msg = {"nid": None, "listing_id": None, "level": "GOOD_DEAL", "high_roi": channel.endswith("high"), "roi": 64, "profit": 128,
               "title": "🚀 HIGH ROI 64%: test message" if channel.endswith("high") else "🔔 SS Deal Finder test",
               "body": "Buy €200 · profit ~€128 · ROI ~64%\nIf you can read this, notifications reach you.", "url": "https://www.ss.lv/",
               "app_url": f"{self.local_url}/#/notifications"}
        ch = channel.replace("-high", "")
        if ch not in PUSH_CHANNELS:
            return {"ok": False, "detail": "unknown channel"}
        try:
            fn = getattr(self, f"_send_{ch}")
            err = await (fn(msg, wait=True) if ch == "desktop" else fn(msg))
        except Exception as e:  # noqa: BLE001
            err = f"{type(e).__name__}: {e}"
        return {"ok": not err, "detail": err or "sent"}

    # ---------------------------------------------------------------- channels (each returns '' or an error)
    async def _send_desktop(self, msg: dict, wait: bool = False) -> str:
        if self._toast_registered is None:
            self._toast_registered = wintoast.register(self.home)
            if self._toast_registered:
                log.warning(f"could not register for Windows notifications: {self._toast_registered}")
        buttons = [("Open ad", msg.get("url") or ""), ("Open in app", msg.get("app_url") or "")]
        return await asyncio.to_thread(wintoast.show, msg["title"], msg["body"], msg.get("url") or msg.get("app_url"),
                                       buttons, bool(msg.get("high_roi")), wait)

    async def _send_ntfy(self, msg: dict) -> str:
        cfg = self.settings.get("ntfy", {}) or {}
        topic = (cfg.get("topic") or "").strip()
        if not topic:
            return "no ntfy topic set"
        high = bool(msg.get("high_roi"))
        payload = {"topic": topic, "title": msg["title"], "message": msg["body"],
                   "priority": 5 if high else 4 if msg["level"] == "GOOD_DEAL" else 3,
                   "tags": ["rocket"] if high else ["moneybag"] if msg["level"] == "GOOD_DEAL" else ["eyes"]}
        if msg.get("url"):
            payload["click"] = msg["url"]
            payload["actions"] = [{"action": "view", "label": "Open ad", "url": msg["url"]}]
        headers = {}
        token = self.settings.secret("ntfy_token")
        if token:
            headers["Authorization"] = f"Bearer {token}"
        # JSON publishing to the server root: titles with emoji and Latvian letters are sent as UTF-8 (headers cannot carry them)
        async with httpx.AsyncClient(timeout=12) as c:
            r = await c.post((cfg.get("server") or "https://ntfy.sh").rstrip("/") + "/", json=payload, headers=headers)
        if r.status_code >= 300:
            return f"ntfy answered HTTP {r.status_code}: {r.text[:200]}"
        return ""

    async def _send_telegram(self, msg: dict) -> str:
        token = self.settings.secret("telegram_token")
        chat = str(self.settings.get("telegram.chat_id") or "").strip()
        if not token or not chat:
            return "Telegram bot token or chat id missing"
        text = f"<b>{html.escape(msg['title'])}</b>\n{html.escape(msg['body'])}"
        payload = {"chat_id": chat, "text": text[:4000], "parse_mode": "HTML", "disable_web_page_preview": False,
                   "disable_notification": False}
        if msg.get("url"):
            payload["reply_markup"] = {"inline_keyboard": [[{"text": "Open ad", "url": msg["url"]}]]}
        async with httpx.AsyncClient(timeout=12) as c:
            r = await c.post(f"https://api.telegram.org/bot{token}/sendMessage", json=payload)
        try:
            data = r.json()
        except ValueError:
            data = {}
        if not data.get("ok"):
            return f"Telegram: {data.get('description') or ('HTTP ' + str(r.status_code))}"
        return ""

    async def _send_discord(self, msg: dict) -> str:
        if self.discord_queue is None or not self.discord_online():
            return "Discord bot is not online (check the token and channel in Settings → Discord)"
        if self.discord_queue.qsize() > 100:
            return "Discord queue is full"
        if msg.get("nid"):
            await self.discord_queue.put({"type": "deal", "notification_id": msg["nid"], "listing_id": msg["listing_id"]})
        else:
            await self.discord_queue.put({"type": "text", "title": msg["title"], "body": msg["body"], "url": msg.get("url")})
        return ""


async def telegram_find_chats(token: str) -> list[dict]:
    """Chats that recently wrote to the bot (send it any message first)."""
    async with httpx.AsyncClient(timeout=12) as c:
        r = await c.get(f"https://api.telegram.org/bot{token}/getUpdates")
    data = r.json()
    if not data.get("ok"):
        raise ValueError(data.get("description") or f"HTTP {r.status_code}")
    out: dict[str, dict] = {}
    for u in data.get("result", []):
        m = u.get("message") or u.get("channel_post") or {}
        ch = m.get("chat") or {}
        if ch.get("id") is not None:
            out[str(ch["id"])] = {"id": str(ch["id"]), "name": ch.get("title") or ch.get("username") or ch.get("first_name") or ""}
    return list(out.values())

