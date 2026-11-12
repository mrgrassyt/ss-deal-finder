"""Cloud/server mode: the app runs 24/7 on a rented server (or any always-on machine) and you log in with a password.

Switched on with `--server` (or SSDEAL_SERVER=1). In this mode:
  * the service refuses to start without a password (SSDEAL_PASSWORD) so it can never be open by mistake,
  * every /api request from outside the machine needs a login cookie (or the API token, which the Android app uses),
  * the Windows-only parts (desktop pop-ups) are off; phone alerts (ntfy, Telegram, Discord) work as usual,
  * a data pack made on the PC (tools/pack_data.py) is imported once on the first start.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import shutil
import time
import zipfile
from pathlib import Path

COOKIE = "ssd_session"
SESSION_DAYS = 30
IMPORT_NAMES = ("ssdeal.db", "settings.json", "secrets.json")      # nothing else is ever extracted from a data pack


def enabled(flag: bool = False) -> bool:
    return bool(flag or os.environ.get("SSDEAL_SERVER", "").strip() not in ("", "0", "false", "no"))


def password() -> str:
    return os.environ.get("SSDEAL_PASSWORD", "")


class Sessions:
    """Signed, expiring login cookies. Nothing is stored server-side, so restarts do not log you out."""

    def __init__(self, home: Path):
        key_file = home / "session.key"
        if not key_file.exists():
            key_file.write_text(secrets.token_hex(32), encoding="ascii")
            try:
                key_file.chmod(0o600)
            except OSError:
                pass
        self._key = key_file.read_text(encoding="ascii").strip().encode()
        self._fails: dict[str, tuple[int, float]] = {}      # ip -> (failed attempts, locked until)

    # ---- cookie
    def _sig(self, body: str) -> str:
        pw = hashlib.sha256(password().encode()).hexdigest()[:16]       # changing the password logs everyone out
        return hmac.new(self._key, f"{body}.{pw}".encode(), hashlib.sha256).hexdigest()[:40]

    def make(self, days: int = SESSION_DAYS) -> str:
        body = base64.urlsafe_b64encode(json.dumps({"exp": int(time.time()) + days * 86400}).encode()).decode()
        return f"{body}.{self._sig(body)}"

    def valid(self, cookie: str | None) -> bool:
        if not cookie or "." not in cookie or not password():
            return False
        body, sig = cookie.rsplit(".", 1)
        if not hmac.compare_digest(sig, self._sig(body)):
            return False
        try:
            return json.loads(base64.urlsafe_b64decode(body.encode())).get("exp", 0) > time.time()
        except (ValueError, TypeError):
            return False

    # ---- password check with a lock-out after repeated mistakes
    def locked_for(self, ip: str) -> int:
        n, until = self._fails.get(ip, (0, 0.0))
        return max(0, int(until - time.time())) if n >= 5 else 0

    def attempt(self, ip: str, given: str) -> bool:
        if self.locked_for(ip):
            return False
        ok = bool(password()) and hmac.compare_digest(hashlib.sha256(given.encode()).digest(), hashlib.sha256(password().encode()).digest())
        if ok:
            self._fails.pop(ip, None)
            return True
        n, _ = self._fails.get(ip, (0, 0.0))
        n += 1
        self._fails[ip] = (n, time.time() + min(900, 30 * 2 ** max(0, n - 5)) if n >= 5 else 0.0)
        if len(self._fails) > 500:
            self._fails = {k: v for k, v in self._fails.items() if v[1] > time.time()}
        return False


def import_pending(home: Path, log=print) -> str:
    """Start-up: pick up import.zip made by tools/pack_data.py (copied by hand or uploaded in Settings).
    A first-time import never overwrites existing data; an upload from Settings sets import.force, which replaces the
    server's data after saving a copy of the old database in backups/."""
    pack, force_flag = home / "import.zip", home / "import.force"
    if not pack.exists():
        force_flag.unlink(missing_ok=True)
        return ""
    force = force_flag.exists()
    if (home / "ssdeal.db").exists():
        if not force:
            log("import.zip found but this server already has data; leaving it alone (delete ssdeal.db to import again)")
            return "skipped: data already exists"
        (home / "backups").mkdir(exist_ok=True)
        try:
            shutil.copy2(home / "ssdeal.db", home / "backups" / f"before-import-{time.strftime('%Y%m%d-%H%M%S')}.db")
        except OSError as e:
            log(f"could not back up the old database, import cancelled: {e}")
            return f"failed: {e}"
    done = []
    try:
        with zipfile.ZipFile(pack) as z:
            for name in IMPORT_NAMES:
                if name in z.namelist():                              # exact names only: no paths, no zip-slip
                    if name == "ssdeal.db":                           # leftovers of the old database would corrupt the new one
                        for ext in ("-wal", "-shm"):
                            (home / ("ssdeal.db" + ext)).unlink(missing_ok=True)
                    (home / name).write_bytes(z.read(name))
                    done.append(name)
        pack.rename(home / "import.done.zip")
        force_flag.unlink(missing_ok=True)
    except (OSError, zipfile.BadZipFile) as e:
        log(f"could not import data pack: {e}")
        return f"failed: {e}"
    log(f"imported from your PC: {', '.join(done)}")
    return "imported: " + ", ".join(done)


def check_pack(data: bytes) -> str:
    """'' if the bytes are a usable data pack, else why not."""
    import io
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            if "ssdeal.db" not in z.namelist():
                return "That zip has no ssdeal.db. Make it with Pack my data.bat."
            head = z.read("ssdeal.db")[:16]
    except zipfile.BadZipFile:
        return "That is not a zip file."
    return "" if head.startswith(b"SQLite format 3") else "ssdeal.db inside the zip is not a database."
