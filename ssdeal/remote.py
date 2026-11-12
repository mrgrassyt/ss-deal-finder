"""Remote access through Tailscale (a private network between your own devices).

`tailscale serve` publishes the local app at https://<this-pc>.<your-tailnet>.ts.net with a real certificate, reachable
only from devices signed in to the same Tailscale account. Nothing is opened to the internet and no router change is
needed. The HTTPS address is also what makes the app installable on the phone (a PWA needs HTTPS).
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys

NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0


def find_cli() -> str | None:
    exe = shutil.which("tailscale")
    if exe:
        return exe
    for cand in (r"C:\Program Files\Tailscale\tailscale.exe", r"C:\Program Files (x86)\Tailscale\tailscale.exe",
                 "/Applications/Tailscale.app/Contents/MacOS/Tailscale"):
        if os.path.exists(cand):
            return cand
    return None


def _run(args: list[str], timeout: float = 15) -> tuple[int, str]:
    cli = find_cli()
    if not cli:
        return 127, "Tailscale is not installed"
    try:
        r = subprocess.run([cli, *args], capture_output=True, text=True, timeout=timeout, creationflags=NO_WINDOW)
        return r.returncode, (r.stdout or "") + (r.stderr or "")
    except subprocess.TimeoutExpired as e:
        out = (e.stdout or b"") if isinstance(e.stdout, bytes) else (e.stdout or "")
        return 124, (out.decode() if isinstance(out, bytes) else out) or "Tailscale did not answer in time"
    except OSError as e:
        return 126, str(e)


def status(port: int) -> dict:
    out: dict = {"installed": bool(find_cli()), "running": False, "logged_in": False, "dns_name": "", "ips": [],
                 "serving": False, "url": "", "port": port}
    if not out["installed"]:
        return out
    code, text = _run(["status", "--json"])
    try:
        st = json.loads(text)
    except ValueError:
        out["error"] = text.strip()[:300]
        return out
    out["running"] = True
    out["backend"] = st.get("BackendState", "")
    out["logged_in"] = st.get("BackendState") == "Running"
    me = st.get("Self") or {}
    out["dns_name"] = (me.get("DNSName") or "").rstrip(".")
    out["ips"] = me.get("TailscaleIPs") or []
    out["https_enabled"] = bool(st.get("CertDomains"))
    code, text = _run(["serve", "status", "--json"])
    try:
        sv = json.loads(text or "{}") or {}
    except ValueError:
        sv = {}
    target = f"127.0.0.1:{port}"
    blob = json.dumps(sv)
    out["serving"] = target in blob or f"localhost:{port}" in blob
    if out["serving"] and out["dns_name"]:
        out["url"] = f"https://{out['dns_name']}/"
    return out


def serve(port: int, on: bool = True) -> dict:
    """Start (or stop) `tailscale serve` for the app; it keeps running in the background and survives reboots."""
    if on:
        code, text = _run(["serve", "--bg", f"http://127.0.0.1:{port}"], timeout=25)
    else:
        code, text = _run(["serve", "reset"], timeout=25)
    res = status(port)
    res["ok"] = code == 0 and (res["serving"] if on else not res["serving"])
    res["output"] = text.strip()[:600]
    # first use on a tailnet: Tailscale asks to switch on HTTPS certificates / Serve and prints a link to do it
    link = next((w for w in text.split() if w.startswith("https://login.tailscale.com")), "")
    if link:
        res["enable_link"] = link
    return res
