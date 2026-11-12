"""Polite HTTP access to SS.lv.

* One request at a time through a single queue, with a minimum interval + jitter.
* robots.txt is fetched, cached and obeyed for every URL.
* 429/503/403 and CAPTCHA/anti-bot pages trigger an escalating cool-down.
  The fetcher never tries to bypass protections: it simply waits.
"""
from __future__ import annotations

import asyncio
import random
import time
import urllib.robotparser
from dataclasses import dataclass, field
from urllib.parse import urljoin, urlparse

import httpx

from .logs import get_logger

log = get_logger("fetcher")

BLOCK_MARKERS = ("captcha", "g-recaptcha", "cf-chl", "challenge-platform", "are you a robot", "access denied")
CONTENT_MARKERS = ('id="tr_', "id='tr_", "msg_div_msg", "<rss", "<channel", 'id="head_line"', "ads_price")


def looks_like_challenge(text: str) -> bool:
    low = text[:30000].lower()
    if any(c in low for c in CONTENT_MARKERS):
        return False
    return any(m in low for m in BLOCK_MARKERS)


@dataclass
class FetchResult:
    url: str
    status: int = 0
    text: str = ""
    final_url: str = ""
    error: str | None = None
    elapsed: float = 0.0
    blocked: bool = False
    disallowed: bool = False

    @property
    def ok(self) -> bool:
        return self.error is None and 200 <= self.status < 300


@dataclass
class FetcherState:
    requests: int = 0
    errors: int = 0
    last_ok: float = 0.0
    last_error: str = ""
    last_error_at: float = 0.0
    cooldown_until: float = 0.0
    cooldown_level: int = 0
    blocked_reason: str = ""
    robots_loaded_at: float = 0.0
    robots_status: str = "not loaded"
    recent_latency: list[float] = field(default_factory=list)


class PoliteFetcher:
    def __init__(self, settings, client: httpx.AsyncClient | None = None):
        self.settings = settings
        self.state = FetcherState()
        self._lock = asyncio.Lock()
        self._last_request = 0.0
        self._robots: urllib.robotparser.RobotFileParser | None = None
        self._client = client

    # ---------------------------------------------------------------- config
    @property
    def base_url(self) -> str:
        return self.settings.get("scan.base_url", "https://www.ss.lv").rstrip("/")

    def _client_get(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                follow_redirects=True,
                timeout=self.settings.get("scan.timeout", 20.0),
                headers={
                    "User-Agent": self.settings.get("scan.user_agent"),
                    "Accept-Language": "lv,en;q=0.7",
                },
            )
        return self._client

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    def absolute(self, path_or_url: str) -> str:
        return urljoin(self.base_url + "/", path_or_url)

    # ---------------------------------------------------------------- robots
    async def _ensure_robots(self) -> None:
        if self._robots and time.time() - self.state.robots_loaded_at < 12 * 3600:
            return
        url = self.base_url + "/robots.txt"
        rp = urllib.robotparser.RobotFileParser()
        try:
            await self._wait_turn()
            r = await self._client_get().get(url)
            self.state.requests += 1
            if r.status_code == 200:
                rp.parse(r.text.splitlines())
                self.state.robots_status = "loaded"
            elif 400 <= r.status_code < 500:
                rp.parse([])  # no robots file -> everything allowed
                self.state.robots_status = f"none (HTTP {r.status_code})"
            else:
                raise httpx.HTTPError(f"robots.txt HTTP {r.status_code}")
            self._robots = rp
            self.state.robots_loaded_at = time.time()
            log.event("robots.loaded", status=self.state.robots_status)
        except httpx.HTTPError as e:
            # Cannot verify permissions: do not crawl until we can.
            self.state.robots_status = f"unavailable: {e}"
            raise

    def allowed(self, url: str) -> bool:
        if not self._robots:
            return False
        ua = self.settings.get("scan.user_agent", "*").split("/")[0]
        return self._robots.can_fetch(ua, url) and self._robots.can_fetch("*", url)

    # ---------------------------------------------------------------- pacing
    async def _wait_turn(self) -> None:
        interval = float(self.settings.get("scan.min_request_interval", 4.0))
        jitter = float(self.settings.get("scan.request_jitter", 1.5))
        now = time.monotonic()
        wait = self._last_request + interval + random.uniform(0, jitter) - now
        if wait > 0:
            await asyncio.sleep(wait)
        self._last_request = time.monotonic()

    def cooling_down(self) -> float:
        return max(0.0, self.state.cooldown_until - time.time())

    def _escalate(self, reason: str) -> None:
        self.state.cooldown_level = min(self.state.cooldown_level + 1, 5)
        minutes = [2, 5, 15, 30, 60, 120][self.state.cooldown_level]
        self.state.cooldown_until = time.time() + minutes * 60
        self.state.blocked_reason = reason
        log.event("fetch.cooldown", f"Pausing requests for {minutes} min: {reason}", _level=30,
                  minutes=minutes, reason=reason)

    def reset_cooldown(self) -> None:
        self.state.cooldown_until = 0
        self.state.cooldown_level = 0
        self.state.blocked_reason = ""

    # ---------------------------------------------------------------- get
    async def get(self, path_or_url: str, retries: int = 2) -> FetchResult:
        url = self.absolute(path_or_url)
        res = FetchResult(url=url)
        if urlparse(url).netloc != urlparse(self.base_url).netloc:
            res.error = "refusing to fetch outside the configured site"
            return res
        if self.cooling_down():
            res.error = f"cooling down ({int(self.cooling_down())}s left): {self.state.blocked_reason}"
            res.blocked = True
            return res
        async with self._lock:
            try:
                await self._ensure_robots()
            except httpx.HTTPError as e:
                res.error = f"robots.txt unavailable: {e}"
                self._note_error(res.error)
                self._escalate("robots.txt unavailable")
                return res
            if not self.allowed(url):
                res.disallowed = True
                res.error = "disallowed by robots.txt"
                log.event("fetch.disallowed", url=url, _level=30)
                return res
            attempt = 0
            while True:
                attempt += 1
                await self._wait_turn()
                t0 = time.monotonic()
                try:
                    r = await self._client_get().get(url)
                    self.state.requests += 1
                    res.elapsed = time.monotonic() - t0
                    res.status = r.status_code
                    res.final_url = str(r.url)
                    res.text = r.text
                except httpx.HTTPError as e:
                    self.state.requests += 1
                    res.error = f"{type(e).__name__}: {e}"
                    if attempt <= retries:
                        await asyncio.sleep(3 * attempt)
                        continue
                    self._note_error(res.error)
                    return res
                if res.status in (429, 503) or (res.status == 403):
                    res.blocked = True
                    res.error = f"HTTP {res.status}"
                    self._escalate(f"server responded HTTP {res.status}")
                    self._note_error(res.error)
                    return res
                if res.status == 200 and looks_like_challenge(res.text):
                    # A challenge page instead of content: stop and wait, never try to solve it.
                    res.blocked = True
                    res.error = "anti-bot/CAPTCHA page detected"
                    self._escalate(res.error)
                    self._note_error(res.error)
                    return res
                if 500 <= res.status < 600 and attempt <= retries:
                    await asyncio.sleep(5 * attempt)
                    continue
                if res.status == 200:
                    self.state.last_ok = time.time()
                    if self.state.cooldown_level and not self.cooling_down():
                        self.state.cooldown_level = max(0, self.state.cooldown_level - 1)
                    self.state.recent_latency = (self.state.recent_latency + [res.elapsed])[-50:]
                elif res.status != 404:
                    res.error = f"HTTP {res.status}"
                    self._note_error(res.error)
                return res

    def _note_error(self, err: str) -> None:
        self.state.errors += 1
        self.state.last_error = err
        self.state.last_error_at = time.time()
        log.event("fetch.error", err, _level=30)

    def status(self) -> dict:
        s = self.state
        lat = s.recent_latency
        return {
            "requests": s.requests,
            "errors": s.errors,
            "last_ok": s.last_ok,
            "last_error": s.last_error,
            "last_error_at": s.last_error_at,
            "cooldown_seconds": int(self.cooling_down()),
            "blocked_reason": s.blocked_reason if self.cooling_down() else "",
            "robots": s.robots_status,
            "avg_latency": round(sum(lat) / len(lat), 3) if lat else None,
        }
