"""Structured JSONL logging designed for later analysis by a local LLM.

Every line is one JSON object: {"ts", "level", "event", "msg", ...fields}.
Secrets (tokens, webhook URLs, authorization headers) are redacted before
anything is written. Files rotate by size and old files are pruned by age.
"""
from __future__ import annotations

import collections
import json
import logging
import logging.handlers
import re
import sys
import time
from pathlib import Path
from typing import Any

_REDACT_PATTERNS = [
    (re.compile(r"https://(?:\w+\.)?discord(?:app)?\.com/api/webhooks/\S+", re.I), "[REDACTED_WEBHOOK]"),
    (re.compile(r"[MNO][A-Za-z\d_-]{23,25}\.[A-Za-z\d_-]{6}\.[A-Za-z\d_-]{27,40}"), "[REDACTED_TOKEN]"),
    (re.compile(r"(?i)(authorization|token|password|secret|api[_-]?key)(['\"]?\s*[:=]\s*['\"]?)([^\s'\",}]+)"),
     r"\1\2[REDACTED]"),
    (re.compile(r"(?i)bearer\s+[a-z0-9._\-]+"), "Bearer [REDACTED]"),
]
_known_secrets: set[str] = set()


def register_secret(value: str) -> None:
    if value and len(value) >= 6:
        _known_secrets.add(value)


def redact(text: str) -> str:
    if not isinstance(text, str):
        text = str(text)
    for s in _known_secrets:
        if s in text:
            text = text.replace(s, "[REDACTED]")
    for pat, repl in _REDACT_PATTERNS:
        text = pat.sub(repl, text)
    return text


def _redact_obj(v: Any) -> Any:
    if isinstance(v, str):
        return redact(v)
    if isinstance(v, dict):
        return {k: ("[REDACTED]" if re.search(r"(?i)token|secret|password|webhook", str(k)) else _redact_obj(x))
                for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [_redact_obj(x) for x in v]
    return v


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(record.created)) + f".{int(record.msecs):03d}",
            "level": record.levelname,
            "logger": record.name,
            "event": getattr(record, "event", None) or "log",
            "msg": redact(record.getMessage()),
        }
        fields = getattr(record, "fields", None)
        if fields:
            payload.update(_redact_obj(fields))
        if record.exc_info:
            payload["exception"] = redact(self.formatException(record.exc_info))
        return json.dumps(payload, ensure_ascii=False, default=str)


class RingBuffer(logging.Handler):
    """Keeps the latest records in memory for the System page."""

    def __init__(self, size: int = 500):
        super().__init__()
        self.buf: collections.deque[str] = collections.deque(maxlen=size)
        self.setFormatter(JsonFormatter())

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self.buf.append(self.format(record))
        except Exception:  # pragma: no cover
            pass

    def tail(self, n: int = 200, level: str | None = None) -> list[dict]:
        out = []
        for line in list(self.buf)[-n * 3:]:
            try:
                d = json.loads(line)
            except json.JSONDecodeError:
                continue
            if level and d.get("level") != level:
                continue
            out.append(d)
        return out[-n:]


ring = RingBuffer()
CONSOLE_EVENTS = {"service.start", "service.stop", "scanner.backfill_start", "scanner.backfill_done", "notify.sent",
                  "scanner.feed", "discord.ready", "backup.created", "reminder.sent"}
_configured = False


def setup_logging(log_dir: Path, level: str = "INFO", max_mb: int = 10, console: bool = True) -> None:
    global _configured
    root = logging.getLogger("ssdeal")
    if _configured:
        root.setLevel(level)
        return
    root.setLevel(level)
    root.propagate = False
    fh = logging.handlers.RotatingFileHandler(
        log_dir / "ssdeal.jsonl", maxBytes=max_mb * 1024 * 1024, backupCount=50, encoding="utf-8"
    )
    fh.setFormatter(JsonFormatter())
    root.addHandler(fh)
    root.addHandler(ring)
    if console and sys.stderr is not None:  # pythonw has no console
        ch = logging.StreamHandler()
        ch.setFormatter(logging.Formatter("%(asctime)s %(levelname)-7s %(message)s", "%H:%M:%S"))
        ch.setLevel("INFO")
        ch.addFilter(lambda r: r.levelno >= 30 or getattr(r, "event", "") in CONSOLE_EVENTS)
        root.addHandler(ch)
    _configured = True


def get_logger(name: str = "ssdeal") -> "EventLogger":
    return EventLogger(logging.getLogger(name if name.startswith("ssdeal") else f"ssdeal.{name}"))


class EventLogger:
    def __init__(self, logger: logging.Logger):
        self.logger = logger

    def event(self, event: str, msg: str = "", _level: int = logging.INFO, **fields: Any) -> None:
        self.logger.log(_level, msg or event, extra={"event": event, "fields": fields})

    def info(self, msg: str, **fields: Any) -> None:
        self.logger.info(msg, extra={"event": fields.pop("event", "log"), "fields": fields})

    def warning(self, msg: str, **fields: Any) -> None:
        self.logger.warning(msg, extra={"event": fields.pop("event", "warning"), "fields": fields})

    def error(self, msg: str, exc_info: bool = False, **fields: Any) -> None:
        self.logger.error(msg, exc_info=exc_info, extra={"event": fields.pop("event", "error"), "fields": fields})

    def debug(self, msg: str, **fields: Any) -> None:
        self.logger.debug(msg, extra={"event": fields.pop("event", "debug"), "fields": fields})


def prune_logs(log_dir: Path, retention_days: int) -> int:
    cutoff = time.time() - retention_days * 86400
    removed = 0
    for p in log_dir.glob("ssdeal.jsonl.*"):
        try:
            if p.stat().st_mtime < cutoff:
                p.unlink()
                removed += 1
        except OSError:
            pass
    return removed
