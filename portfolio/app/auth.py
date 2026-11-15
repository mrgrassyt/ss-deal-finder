"""Admin sign-in: one password (stored as a scrypt hash), server-side sessions, and a brake on guessing.

There is no username and nothing about the password ever reaches the browser. The first password comes from the
SITE_ADMIN_PASSWORD environment variable; after it is changed in the dashboard the stored hash wins.
"""
from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import time

COOKIE = "mg_admin"
SESSION_DAYS = 30


def hash_password(pw: str, salt: bytes | None = None) -> str:
    salt = salt or secrets.token_bytes(16)
    h = hashlib.scrypt(pw.encode(), salt=salt, n=2 ** 14, r=8, p=1, dklen=32)
    return salt.hex() + ":" + h.hex()


def check_password(pw: str, stored: str) -> bool:
    try:
        salt, _ = stored.split(":")
        return hmac.compare_digest(hash_password(pw, bytes.fromhex(salt)), stored)
    except (ValueError, AttributeError):
        return False


class Auth:
    def __init__(self, db):
        self.db = db
        self.fails: dict[str, list[float]] = {}

    def configured(self) -> bool:
        return bool(self.db.kv("pw_hash") or os.environ.get("SITE_ADMIN_PASSWORD"))

    def verify(self, pw: str) -> bool:
        stored = self.db.kv("pw_hash")
        if stored:
            return check_password(pw, stored)
        env = os.environ.get("SITE_ADMIN_PASSWORD") or ""
        return bool(env) and hmac.compare_digest(pw.encode(), env.encode())

    def set_password(self, pw: str) -> None:
        self.db.set_kv("pw_hash", hash_password(pw))
        self.db.set_kv("sessions", {})                       # signs every device out

    # ---- throttle: 6 wrong tries per address in 10 minutes ---------------------------------------------------------
    def blocked(self, ip: str) -> int:
        now = time.time()
        tries = [t for t in self.fails.get(ip, []) if now - t < 600]
        self.fails[ip] = tries
        return int(600 - (now - tries[0])) if len(tries) >= 6 else 0

    def failed(self, ip: str) -> None:
        self.fails.setdefault(ip, []).append(time.time())

    # ---- sessions ------------------------------------------------------------------------------------------------
    @staticmethod
    def _key(token: str) -> str:
        return hashlib.sha256(token.encode()).hexdigest()

    def start(self) -> str:
        token = secrets.token_urlsafe(32)
        now = time.time()
        sessions = {k: v for k, v in (self.db.kv("sessions") or {}).items() if v > now}
        sessions[self._key(token)] = now + SESSION_DAYS * 86400
        self.db.set_kv("sessions", sessions)
        return token

    def valid(self, token: str | None) -> bool:
        return bool(token) and (self.db.kv("sessions") or {}).get(self._key(token), 0) > time.time()

    def end(self, token: str | None) -> None:
        if token:
            sessions = self.db.kv("sessions") or {}
            sessions.pop(self._key(token), None)
            self.db.set_kv("sessions", sessions)
