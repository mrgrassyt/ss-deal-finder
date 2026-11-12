"""Paths, default settings and the persistent settings store.

Settings live in ``settings.json`` inside the data directory. Secrets (Discord
bot token, ntfy token, API access token) live in a separate ``secrets.json`` so
they are never exported, logged or shown back in the UI in clear text.
"""
from __future__ import annotations

import copy
import json
import os
import sys
import threading
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------- paths


def data_dir() -> Path:
    env = os.environ.get("SSDEAL_HOME")
    if env:
        p = Path(env)
    elif sys.platform == "win32":
        p = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "SSDealFinder"
    else:
        p = Path.home() / ".ssdeal"
    p.mkdir(parents=True, exist_ok=True)
    for sub in ("logs", "backups", "exports"):
        (p / sub).mkdir(exist_ok=True)
    return p


APP_ROOT = Path(__file__).resolve().parent.parent
WEB_DIR = APP_ROOT / "web"

# ---------------------------------------------------------------- defaults

DEFAULT_SETTINGS: dict[str, Any] = {
    "scan": {
        "enabled": True,
        "base_url": "https://www.ss.lv",
        # Seconds between any two requests to SS.lv (a single polite queue).
        "min_request_interval": 4.0,
        "request_jitter": 1.5,
        "timeout": 20.0,
        "new_listings_interval_min": 2,      # priority feeds
        "normal_feed_interval_min": 10,      # all other enabled feeds
        "price_check_interval_min": 12,
        "market_recalc_interval_min": 30,
        "reconcile_interval_min": 240,
        "reconcile_pages": 5,                # pages per feed during reconciliation
        "max_pages_new": 3,                  # stop earlier when known listings appear
        "detail_fetch_min_score": 45,        # fetch full ad text for promising ones
        "detail_fetch_max_per_cycle": 15,
        "backfill_pages": 4,                 # warm-up crawl depth per feed
        "warmup_complete": False,
        "engine_rev": 0,            # last rule set applied to stored listings (see service.ENGINE_REV)
        "warmup_done_at": 0,        # ads first seen before this moment are the starting backlog, never "new"
        "use_rss_when_available": True,
        "user_agent": "SSDealFinder/1.0 (personal, low-rate; respects robots.txt)",
    },
    "feeds": {},  # feed_key -> {"enabled": bool, "priority": bool} overrides
    "filters": {
        "min_price": 0,
        "max_price": 0,             # 0 = no limit
        "ignore_buying_ads": True,  # "pērku" / "куплю" ads are wanted-ads, not offers
        "ignore_services": True,    # repairs, rentals, photographer services
        "ignore_parts": True,       # batteries, screens, cases… sold *for* a device are not the device
        "junk_value_floor": 8,      # € - low-value single accessories below this are junk
        "categories": {},           # category_key -> {"enabled": bool, "max_budget": n, "min_deal": n}
    },
    "notify": {
        "sensitivity": "balanced",  # high_recall | balanced | strict
        "good_deal_threshold": 78,
        "interesting_threshold": 60,
        "personal_good_threshold": 80,
        "personal_interesting_threshold": 66,
        "discord_good": True,
        "discord_interesting": False,
        "desktop_good": True,
        "desktop_interesting": True,
        "ntfy_good": True,
        "ntfy_interesting": False,
        "telegram_good": True,
        "telegram_interesting": False,
        "in_app_popups": False,     # pop-ups inside the app window; the real alerts are Windows / phone notifications
        "high_roi_pct": 40,         # ROI at or above this gets the 🚀 high-ROI style (0 = off); skips quiet hours and the hourly limit
        "high_roi_min_profit": 15,  # ... but only when the estimated profit is at least this many euros
        "renotify_price_drop_pct": 8,
        "quiet_hours": {"enabled": False, "start": "23:00", "end": "07:30"},
        "suppress_during_warmup": True,
        "max_age_hours": 12,        # a "new" ad older than this (by its own date) is shown in the app but never pushed
        "max_per_hour": 8,          # push notifications per hour; the rest wait quietly in the app (+1 summary)
        "calendar_min_score": 85,   # only great deals are added to the calendar
    },
    "flip": {
        "sale_discount_pct": 8,   # asking prices are not what items sell for: expect to land this much lower
        "extra_costs": 3,         # per flip: shipping, fuel, packaging
        "rough_margin_pct": 12,   # used only when there is no market data at all: a typical small margin as a rough guess
    },
    "discord": {
        "enabled": False,
        "channel_id": "",
        "allowed_user_ids": "",  # comma separated; empty = anyone in the channel
    },
    "ntfy": {"enabled": False, "server": "https://ntfy.sh", "topic": ""},
    "telegram": {"enabled": False, "chat_id": ""},
    "preferences": {
        "categories": {},     # category_key -> -1..1 explicit interest
        "brands": {},         # brand -> -1..1
        "keywords_like": [],
        "keywords_dislike": [],
        "budget_default": 0,
        "budgets": {},        # category_key -> max €
        "conditions": {"new": 0.0, "used": 0.0, "broken": -0.2},
    },
    "learning": {
        "enabled": True,
        "personal_weight": 1.0,
        "market_correction_weight": 3.0,  # one correction = N observations
        "confirmed_sale_weight": 4.0,
        "min_observations": 3,
    },
    "ui": {"theme": "blueprint", "performance_mode": "performance", "text_size": "normal", "mode": "simple", "page_size": 50},
    "startup": {"autostart": False, "start_minimized": True, "launch_service_with_ui": True},
    "logs": {"retention_days": 30, "max_file_mb": 10, "level": "INFO"},
    "backup": {"auto_daily": True, "keep": 10},
    "api": {"host": "127.0.0.1", "port": 8765, "allow_lan": False, "trust_tailscale": True},
}

SECRET_KEYS = ("discord_token", "ntfy_token", "api_token", "telegram_token")


def _deep_merge(base: dict, override: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in (override or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def _atomic_write(path: Path, data: Any) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)


class Settings:
    """Thread-safe persistent settings with validation."""

    def __init__(self, home: Path | None = None):
        self.home = home or data_dir()
        self.path = self.home / "settings.json"
        self.secrets_path = self.home / "secrets.json"
        self._lock = threading.RLock()
        self._data = self._load()
        self._secrets = self._load_secrets()
        self._mtime = self._stat()

    def _stat(self) -> float:
        try:
            return self.path.stat().st_mtime
        except OSError:
            return 0.0

    def _load(self) -> dict:
        user = {}
        if self.path.exists():
            try:
                user = json.loads(self.path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                # keep a copy of the broken file and continue with defaults
                self.path.rename(self.path.with_suffix(".broken.json"))
        return _deep_merge(DEFAULT_SETTINGS, user)

    def _load_secrets(self) -> dict:
        if self.secrets_path.exists():
            try:
                return json.loads(self.secrets_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                return {}
        return {}

    def reload_if_changed(self) -> bool:
        """Pick up edits made by another process (the UI and service share files)."""
        m = self._stat()
        if m and m != self._mtime:
            with self._lock:
                self._data = self._load()
                self._secrets = self._load_secrets()
                self._mtime = m
            return True
        return False

    # ---- access
    def get(self, dotted: str, default: Any = None) -> Any:
        with self._lock:
            cur: Any = self._data
            for part in dotted.split("."):
                if not isinstance(cur, dict) or part not in cur:
                    return default
                cur = cur[part]
            return copy.deepcopy(cur)

    def all(self) -> dict:
        with self._lock:
            return copy.deepcopy(self._data)

    def update(self, patch: dict) -> dict:
        errors = validate_settings_patch(patch)
        if errors:
            raise ValueError("; ".join(errors))
        with self._lock:
            self._data = _deep_merge(self._data, patch)
            _atomic_write(self.path, self._data)
            self._mtime = self._stat()
            return copy.deepcopy(self._data)

    def set(self, dotted: str, value: Any) -> None:
        parts = dotted.split(".")
        patch: dict = {}
        cur = patch
        for p in parts[:-1]:
            cur[p] = {}
            cur = cur[p]
        cur[parts[-1]] = value
        self.update(patch)

    def replace_section(self, section: str, value: dict) -> None:
        """Replace a whole sub-dict (used for maps where keys can be removed)."""
        with self._lock:
            self._data[section] = value
            _atomic_write(self.path, self._data)
            self._mtime = self._stat()

    def reset(self, section: str | None = None) -> None:
        with self._lock:
            if section:
                self._data[section] = copy.deepcopy(DEFAULT_SETTINGS.get(section, {}))
            else:
                self._data = copy.deepcopy(DEFAULT_SETTINGS)
            _atomic_write(self.path, self._data)
            self._mtime = self._stat()

    # ---- secrets
    def secret(self, key: str) -> str:
        env = os.environ.get("SSDEAL_" + key.upper())
        if env:
            return env
        return str(self._secrets.get(key, "") or "")

    def set_secret(self, key: str, value: str) -> None:
        if key not in SECRET_KEYS:
            raise ValueError(f"unknown secret {key}")
        with self._lock:
            if value:
                self._secrets[key] = value
            else:
                self._secrets.pop(key, None)
            _atomic_write(self.secrets_path, self._secrets)
            try:
                os.chmod(self.secrets_path, 0o600)
            except OSError:
                pass

    def secret_status(self) -> dict:
        return {k: bool(self.secret(k)) for k in SECRET_KEYS}


# ---------------------------------------------------------------- validation

_NUMERIC_RULES = {
    ("scan", "min_request_interval"): (2.0, 120.0),
    ("scan", "request_jitter"): (0.0, 30.0),
    ("scan", "timeout"): (5.0, 120.0),
    ("scan", "new_listings_interval_min"): (1, 1440),
    ("scan", "normal_feed_interval_min"): (1, 1440),
    ("scan", "price_check_interval_min"): (5, 1440),
    ("scan", "market_recalc_interval_min"): (5, 1440),
    ("scan", "reconcile_interval_min"): (30, 10080),
    ("scan", "reconcile_pages"): (1, 30),
    ("scan", "max_pages_new"): (1, 10),
    ("scan", "detail_fetch_min_score"): (0, 100),
    ("scan", "detail_fetch_max_per_cycle"): (0, 200),
    ("scan", "backfill_pages"): (0, 30),
    ("notify", "good_deal_threshold"): (1, 100),
    ("notify", "interesting_threshold"): (1, 100),
    ("notify", "personal_good_threshold"): (1, 100),
    ("notify", "personal_interesting_threshold"): (1, 100),
    ("notify", "renotify_price_drop_pct"): (1, 90),
    ("notify", "max_age_hours"): (1, 720),
    ("notify", "max_per_hour"): (1, 200),
    ("notify", "calendar_min_score"): (1, 100),
    ("notify", "high_roi_pct"): (0, 1000),
    ("notify", "high_roi_min_profit"): (0, 100000),
    ("flip", "sale_discount_pct"): (0, 50),
    ("flip", "extra_costs"): (0, 1000),
    ("flip", "rough_margin_pct"): (0, 100),
    ("filters", "min_price"): (0, 1_000_000),
    ("filters", "max_price"): (0, 1_000_000),
    ("filters", "junk_value_floor"): (0, 10_000),
    ("logs", "retention_days"): (1, 3650),
    ("logs", "max_file_mb"): (1, 500),
    ("backup", "keep"): (1, 365),
    ("api", "port"): (1024, 65535),
    ("learning", "personal_weight"): (0.0, 3.0),
    ("learning", "market_correction_weight"): (0.5, 50.0),
    ("learning", "confirmed_sale_weight"): (0.5, 50.0),
    ("learning", "min_observations"): (1, 50),
}

_ENUMS = {
    ("notify", "sensitivity"): {"high_recall", "balanced", "strict"},
    ("ui", "performance_mode"): {"performance", "smooth"},
    ("ui", "text_size"): {"small", "normal", "large", "xlarge"},
    ("ui", "mode"): {"simple", "advanced"},
}


def validate_settings_patch(patch: dict) -> list[str]:
    errors: list[str] = []
    for section, values in (patch or {}).items():
        if section not in DEFAULT_SETTINGS:
            errors.append(f"Unknown settings section '{section}'")
            continue
        if not isinstance(values, dict):
            errors.append(f"Section '{section}' must be an object")
            continue
        for key, val in values.items():
            rule = _NUMERIC_RULES.get((section, key))
            if rule:
                lo, hi = rule
                if isinstance(val, bool) or not isinstance(val, (int, float)):
                    errors.append(f"{section}.{key} must be a number")
                elif not (lo <= val <= hi):
                    errors.append(f"{section}.{key} must be between {lo} and {hi}")
            enum = _ENUMS.get((section, key))
            if enum and val not in enum:
                errors.append(f"{section}.{key} must be one of {sorted(enum)}")
    n = patch.get("notify", {}) if isinstance(patch.get("notify"), dict) else {}
    if "good_deal_threshold" in n and "interesting_threshold" in n:
        if n["interesting_threshold"] > n["good_deal_threshold"]:
            errors.append("Interesting threshold must not exceed the Good Deal threshold")
    d = patch.get("discord", {}) if isinstance(patch.get("discord"), dict) else {}
    cid = str(d.get("channel_id", "") or "")
    if cid and not cid.isdigit():
        errors.append("Discord channel ID must be a number (enable Developer Mode → right click channel → Copy ID)")
    return errors
