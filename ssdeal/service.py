"""Background monitoring service: scheduler + API + Discord bot in one process.

Run:   python -m ssdeal.service            (real SS.lv)
       python -m ssdeal.service --demo     (offline demo against a local mock, separate data folder)

The desktop window only talks to this service over HTTP, so closing the window
never stops monitoring. The same service can run on a separate always-on
machine later (set api.allow_lan + an API token).
"""
from __future__ import annotations

import argparse
import asyncio
import os
import shutil
import signal
import socket
import sys
import time
from pathlib import Path

import uvicorn

from . import __version__
from .actions import Actions
from .config import Settings, data_dir
from .db import Database
from .discord_bot import DealBot
from .engine import Engine
from .feeds import effective_feeds
from .fetcher import make_fetcher
from .logs import get_logger, prune_logs, register_secret, setup_logging
from .notify import Notifier
from .scanner import Scanner

log = get_logger("service")


ENGINE_REV = 9   # bump when identification / part / service rules change; triggers one full re-check on start


class Service:
    def __init__(self, home: Path, demo: bool = False, server: bool = False):
        self.home = home
        self.demo = demo
        self.server_mode = server
        self.settings = Settings(home)
        setup_logging(home / "logs", self.settings.get("logs.level", "INFO"), self.settings.get("logs.max_file_mb", 10))
        for k in ("discord_token", "ntfy_token", "api_token", "telegram_token"):
            register_secret(self.settings.secret(k))
        self.db = Database(home / "ssdeal.db")
        self.engine = Engine(self.db, self.settings)
        self.notifier = Notifier(self.db, self.settings, home)
        self.fetcher = make_fetcher(self.settings)
        self.scanner = Scanner(self.db, self.settings, self.fetcher, self.engine, self.notifier)
        self.actions = Actions(self.db, self.engine)
        self.bot = DealBot(self.db, self.settings, self.actions, self.notifier)
        self.started_at = time.time()
        self.next_runs: dict[str, float] = {}
        self._manual: asyncio.Queue | None = None
        self._rescore_pending = False
        self._stop = asyncio.Event() if False else None
        self.phase = "starting"
        self._last_warmup = 0.0

    # ---------------------------------------------------------------- control hooks used by the API
    def request_run(self, job: str, feed: str | None) -> None:
        if self._manual is not None:
            self._manual.put_nowait((job, feed))

    def schedule_rescore(self) -> None:
        self._rescore_pending = True

    def recheck_everything(self) -> dict:
        """Re-read every listing with the current rules (parts, accessories, services), rebuild prices, rescore."""
        n = self.engine.rescore_all(only_active=False, reidentify=True)
        self.engine.market.recalc_all()
        self.engine.rescore_all(only_active=True, reidentify=True)
        return {"listings": n}

    def on_settings_changed(self) -> None:
        self.engine.market.invalidate()
        self.engine.prefs.invalidate()
        self.engine.wants.invalidate()
        self.schedule_rescore()

    def request_shutdown(self) -> None:
        if self._stop is not None:
            self._stop.set()

    def backup(self, prefix: str = "backup") -> Path:
        d = self.home / "backups"
        dest = d / f"{prefix}-{time.strftime('%Y%m%d-%H%M%S')}.db"
        self.db.backup_to(dest)
        keep = int(self.settings.get("backup.keep", 10))
        files = sorted(d.glob("backup-*.db"), key=lambda p: p.stat().st_mtime, reverse=True)
        for old in files[keep:]:
            old.unlink(missing_ok=True)
        log.event("backup.created", file=dest.name)
        return dest

    def status(self) -> dict:
        last_ok = self.db.scalar("SELECT MAX(finished_at) FROM scan_runs WHERE ok=1")
        hour_req = self.db.scalar("SELECT COALESCE(SUM(requests),0) FROM scan_runs WHERE started_at > ?",
                                  (time.time() - 3600,), 0)
        feeds = effective_feeds(self.settings)
        return {
            "version": __version__, "demo": self.demo, "phase": self.phase,
            "uptime": time.time() - self.started_at,
            "scanner": {
                "enabled": self.settings.get("scan.enabled", True), "paused": self.scanner.paused,
                "current": self.scanner.current, "last_success": last_ok,
                "warmup_complete": self.settings.get("scan.warmup_complete", False),
                "requests_last_hour": hour_req,
                "enabled_feeds": sum(1 for f in feeds if f["enabled"]),
                "priority_feeds": sum(1 for f in feeds if f["enabled"] and f["priority"]),
                "next_runs": self.next_runs, "mode": "periodic polling (not real-time)",
                "base_url": self.settings.get("scan.base_url"),
            },
            "fetcher": self.fetcher.status(),
            "discord": self.bot.info(),
            "ntfy": {"enabled": bool(self.settings.get("ntfy.enabled") and self.settings.get("ntfy.topic"))},
            "listings": self.db.scalar("SELECT COUNT(*) FROM listings WHERE status='active'", default=0),
            "unread": self.db.scalar("SELECT COUNT(*) FROM notifications WHERE read=0", default=0),
        }

    # ---------------------------------------------------------------- scheduler
    async def scheduler(self) -> None:
        self._manual = asyncio.Queue()
        await asyncio.sleep(1)
        await self._warmup()
        last = {"price": time.time(), "market": time.time(), "reconcile": time.time(), "maint": 0.0,
                "backup_day": ""}
        price_idx = 0
        while True:
            try:
                self.settings.reload_if_changed()
                s = self.settings.get("scan", {})
                now = time.time()
                # manual requests first
                while not self._manual.empty():
                    job, feed = self._manual.get_nowait()
                    await self._run_manual(job, feed)
                await self._reminders()
                await self.notifier.flush_pending()
                if self.engine.wants.dirty:            # likes / My items changed: personal ratings of similar ads change too
                    self.engine.wants.dirty = False
                    self._rescore_pending = True
                if self._rescore_pending:
                    self._rescore_pending = False
                    await asyncio.to_thread(self.engine.rescore_all)
                active = s.get("enabled", True) and not self.scanner.paused and not self.fetcher.cooling_down()
                if active and not s.get("warmup_complete"):
                    if now - self._last_warmup >= 600:
                        await self._warmup()
                    await asyncio.sleep(5)
                    continue
                if active:
                    feeds = [f for f in effective_feeds(self.settings) if f["enabled"]]
                    due = []
                    for f in feeds:
                        interval = (s.get("new_listings_interval_min", 2) if f["priority"]
                                    else s.get("normal_feed_interval_min", 10)) * 60
                        lr = self.scanner.feed_last_run.get(f["key"], 0)
                        self.next_runs[f["key"]] = lr + interval
                        if now - lr >= interval:
                            due.append((lr, f))
                    due.sort(key=lambda x: (not x[1]["priority"], x[0]))
                    for _, f in due[:6]:
                        if self.scanner.paused or self.fetcher.cooling_down():
                            break
                        await self.scanner.scan_new(f["key"])
                    if now - last["price"] >= s.get("price_check_interval_min", 12) * 60:
                        pri = [f for f in feeds if f["priority"]]
                        if pri:
                            f = pri[price_idx % len(pri)]
                            price_idx += 1
                            await self.scanner.scan_pages(f["key"], range(2, 4), job="price")
                        last["price"] = now
                    if now - last.get("history", 0) >= s.get("history_interval_min", 5) * 60:
                        await self.scanner.history_step()
                        last["history"] = now
                    if now - last["reconcile"] >= s.get("reconcile_interval_min", 240) * 60:
                        await self.scanner.reconcile()
                        pages = int(s.get("reconcile_pages", 5))
                        for f in feeds:
                            if self.scanner.paused or self.fetcher.cooling_down():
                                break
                            await self.scanner.scan_pages(f["key"], range(4, pages + 1), job="reconcile-pages")
                        last["reconcile"] = now
                if now - last["market"] >= s.get("market_recalc_interval_min", 30) * 60:
                    await asyncio.to_thread(self.engine.market.recalc_all)
                    await asyncio.to_thread(self.engine.rescore_all)
                    last["market"] = now
                if now - last["maint"] >= 3600:
                    prune_logs(self.home / "logs", int(self.settings.get("logs.retention_days", 30)))
                    day = time.strftime("%Y-%m-%d")
                    if self.settings.get("backup.auto_daily", True) and last["backup_day"] != day:
                        if not any(p.name.startswith(f"backup-{day.replace('-', '')}") for p in (self.home / "backups").glob("*.db")):
                            await asyncio.to_thread(self.backup)
                        last["backup_day"] = day
                    self.db.execute("DELETE FROM app_errors WHERE at < ?", (now - 30 * 86400,))
                    self.db.execute("DELETE FROM scan_runs WHERE started_at < ?", (now - 14 * 86400,))
                    last["maint"] = now
            except asyncio.CancelledError:
                raise
            except Exception as e:
                log.error(f"scheduler loop error: {e}", exc_info=True, event="scheduler.error")
                self.db.log_error("scheduler", str(e))
            await asyncio.sleep(5)

    async def _warmup(self) -> None:
        """First-run backfill. Retried from the main loop until it has collected data."""
        if self.settings.get("scan.warmup_complete") or not self.settings.get("scan.enabled", True):
            self.phase = "monitoring"
            return
        if self.fetcher.cooling_down() or self.scanner.paused:
            self.phase = "warm-up waiting: SS.lv not reachable yet (see Activity)"
            return
        self.phase = "warm-up: building market database (notifications suppressed)"
        self._last_warmup = time.time()
        try:
            await self.scanner.backfill()
        except Exception:
            log.error("backfill failed", exc_info=True)
        if self.db.scalar("SELECT COUNT(*) FROM listings", default=0) > 0:
            self.settings.set("scan.warmup_done_at", time.time())
            self.settings.set("scan.warmup_complete", True)
            self.phase = "monitoring"
        else:
            self.phase = "warm-up waiting: no listings collected yet (will retry)"

    async def _run_manual(self, job: str, feed: str | None) -> None:
        log.event("scanner.manual", job=job, feed=feed)
        if job == "backfill":
            await self.scanner.backfill()
            self.settings.set("scan.warmup_done_at", time.time())
            self.settings.set("scan.warmup_complete", True)
        elif job == "reconcile":
            await self.scanner.reconcile()
        elif feed:
            await self.scanner.scan_new(feed)
        else:
            for f in effective_feeds(self.settings):
                if f["enabled"] and f["priority"]:
                    await self.scanner.scan_new(f["key"])

    async def _reminders(self) -> None:
        due = self.db.query("SELECT * FROM tasks WHERE remind_at IS NOT NULL AND remind_at <= ? AND reminded=0 AND done=0",
                            (time.time(),))
        for t in due:
            url = None
            body = t["notes"] or ""
            if t["listing_id"]:
                l = self.db.one("SELECT url, price, status, title FROM listings WHERE id=?", (t["listing_id"],))
                if l:
                    url = l["url"]
                    body = f"{l['title'][:120]} — €{l['price'] or 0:.0f} ({l['status']})\n{body}"
            await self.notifier.notify_text(f"⏰ Reminder: {t['title']}", body.strip(), url)
            self.db.update("tasks", t["id"], {"reminded": 1})
            log.event("reminder.sent", task_id=t["id"])

    # ---------------------------------------------------------------- run
    async def run(self, host: str, port: int) -> None:
        from .api import create_api

        self._stop = asyncio.Event()
        app = create_api(self)
        config = uvicorn.Config(app, host=host, port=port, log_level="warning", access_log=False, log_config=None)
        server = uvicorn.Server(config)
        tasks = [asyncio.create_task(server.serve(), name="api"),
                 asyncio.create_task(self.scheduler(), name="scheduler"),
                 asyncio.create_task(self.bot.run_forever(), name="discord")]
        if self.settings.get("scan.engine_rev", 0) != ENGINE_REV:      # new rules shipped: apply them to everything already stored
            self.settings.set("scan.engine_rev", ENGINE_REV)
            self._rescore_pending = True
            asyncio.get_running_loop().run_in_executor(None, self.recheck_everything)
        log.event("service.start", version=__version__, host=host, port=port, demo=self.demo, home=str(self.home))
        stop_wait = asyncio.create_task(self._stop.wait())
        done, _ = await asyncio.wait([stop_wait, tasks[0]], return_when=asyncio.FIRST_COMPLETED)
        server.should_exit = True
        for t in tasks[1:]:
            t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        await self.fetcher.close()
        self.db.close()
        log.event("service.stop")


def port_in_use(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex((host if host != "0.0.0.0" else "127.0.0.1", port)) == 0


def start_demo_mock(port: int) -> None:
    import threading

    from .mockss import create_app

    cfg = uvicorn.Config(create_app(), host="127.0.0.1", port=port, log_level="warning", log_config=None)
    srv = uvicorn.Server(cfg)
    threading.Thread(target=srv.run, daemon=True, name="mock-ss").start()
    for _ in range(50):
        if port_in_use("127.0.0.1", port):
            break
        time.sleep(0.1)


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description="SS Deal Finder background service")
    ap.add_argument("--demo", action="store_true", help="offline demo against a local mock of SS.lv")
    ap.add_argument("--port", type=int, default=None)
    ap.add_argument("--server", action="store_true", help="always-on server mode: password login, listens for a reverse proxy (see SERVER.md)")
    ap.add_argument("--hub", action="store_true", help="multi-user server: private accounts, one copy of the app per person (see SERVER.md)")
    ap.add_argument("--home", default=None, help="data folder (default: %%LOCALAPPDATA%%\\SSDealFinder)")
    args = ap.parse_args(argv)
    home = Path(args.home) if args.home else data_dir()
    if args.demo:
        home = home / "demo"
        os.environ["SSDEAL_HOME"] = str(home)
    home.mkdir(parents=True, exist_ok=True)
    for sub in ("logs", "backups", "exports"):
        (home / sub).mkdir(exist_ok=True)
    from . import hub as hub_mod
    if hub_mod.enabled(args.hub) and not args.demo:
        os.environ["SSDEAL_SERVER"] = "1"
        hub_mod.main(home, args.port or int(os.environ.get("SSDEAL_HUB_PORT", "8765")))
        return
    from . import server as server_mod
    server = server_mod.enabled(args.server) and not args.demo
    if server:
        os.environ["SSDEAL_SERVER"] = "1"
        if not server_mod.password() or len(server_mod.password()) < 8:
            print("Server mode needs a password of at least 8 characters: set SSDEAL_PASSWORD (see SERVER.md).")
            sys.exit(2)
        server_mod.import_pending(home, print)
    svc_settings = Settings(home)
    port = args.port or (int(svc_settings.get("api.port", 8765)) + (1 if args.demo else 0))
    host = os.environ.get("SSDEAL_BIND") or ("0.0.0.0" if (server or svc_settings.get("api.allow_lan")) else "127.0.0.1")
    if os.environ.get("SSDEAL_WAIT_PORT"):          # started by "restart service": wait for the old copy to let go
        for _ in range(80):
            if not port_in_use("127.0.0.1", port):
                break
            time.sleep(0.5)
    if port_in_use("127.0.0.1", port):
        print(f"SS Deal Finder service already running on port {port}.")
        return
    if args.demo:
        mport = port + 100
        start_demo_mock(mport)
        svc_settings.update({"scan": {"base_url": f"http://127.0.0.1:{mport}", "min_request_interval": 2.0,
                                      "request_jitter": 0.2, "backfill_pages": 3, "new_listings_interval_min": 1}})
        from .feeds import FEEDS
        from .mockss import CATALOG

        svc_settings.replace_section("feeds", {k: {"enabled": f["path"] in CATALOG} for k, f in FEEDS.items()})
    svc = Service(home, demo=args.demo, server=server)
    svc.notifier.local_url = (os.environ.get("SSDEAL_PUBLIC_URL", "").rstrip("/") if (server or os.environ.get("SSDEAL_MANAGED")) else "") or f"http://127.0.0.1:{port}"
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    if sys.platform != "win32":
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, svc.request_shutdown)
    try:
        loop.run_until_complete(svc.run(host, port))
    except KeyboardInterrupt:
        pass
    finally:
        # leftover non-daemon threads (browser helpers, executors) must not keep the process alive in Task Manager
        import logging
        logging.shutdown()
        os._exit(0)


if __name__ == "__main__":
    main()
