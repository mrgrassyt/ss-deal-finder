"""Multi-user server ("hub"): one web address, several private accounts, one shared SS.lv fetcher.

Run with `--hub` (or SSDEAL_HUB=1), normally inside Docker (see SERVER.md). What it does:

  * accounts: sign up with an invite code made by the admin, log in once, a signed cookie keeps you logged in for 30 days;
  * every account is a completely separate copy of the app (its own folder, database, settings, alerts, Discord bot) run as
    its own small background process on this machine, so one person's settings or data can never touch another's;
  * the hub is the only thing reachable from outside. It checks the login cookie and passes the request to YOUR copy;
  * ONE shared scan: every copy gets its SS.lv pages from the hub, which fetches each page once (single polite request
    rate, robots.txt, cool-downs) and hands the same copy to everybody while it is fresh. Each copy then rates the same
    listings with its own settings, so a deal can be great for one person and uninteresting for another.
"""
from __future__ import annotations

import asyncio
import base64
import contextlib
import hashlib
import hmac
import html
import json
import os
import re
import secrets
import shutil
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

import httpx
import uvicorn
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse, RedirectResponse, Response, StreamingResponse
from starlette.routing import Route

from . import server as server_mod
from .config import Settings
from .fetcher import PoliteFetcher
from .logs import get_logger

log = get_logger("hub")
COOKIE = server_mod.COOKIE
SESSION_DAYS = server_mod.SESSION_DAYS
NAME_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{2,23}$")
KEEP_AT_ROOT = {"hub", "users", "session.key"}          # everything else in an old single-user data folder moves to the admin
HOP = {"connection", "keep-alive", "proxy-authenticate", "proxy-authorization", "te", "trailers", "transfer-encoding", "upgrade", "host"}
STRIP_REQ = HOP | {"cookie", "x-api-token", "forwarded", "x-real-ip", "x-forwarded-for", "x-forwarded-host", "x-forwarded-proto",
                   "x-forwarded-port", "tailscale-user-login", "cf-connecting-ip", "content-length"}


# ------------------------------------------------------------------------------------------------- passwords
def hash_pw(pw: str, salt: bytes | None = None) -> str:
    salt = salt or secrets.token_bytes(16)
    h = hashlib.scrypt(pw.encode(), salt=salt, n=2 ** 14, r=8, p=1, dklen=32)
    return f"scrypt${salt.hex()}${h.hex()}"


def check_pw(pw: str, stored: str) -> bool:
    try:
        kind, salt, h = stored.split("$")
        if kind != "scrypt":
            return False
        return hmac.compare_digest(hashlib.scrypt(pw.encode(), salt=bytes.fromhex(salt), n=2 ** 14, r=8, p=1, dklen=32).hex(), h)
    except (ValueError, TypeError):
        return False


# ------------------------------------------------------------------------------------------------- user store
class Store:
    """users.json: {"users": {name: {...}}, "invites": {code: {...}}, "next_port": n}. Tiny, so it is simply rewritten."""

    def __init__(self, hub_home: Path):
        self.path = hub_home / "users.json"
        self.data = {"users": {}, "invites": {}, "next_port": 9100}
        if self.path.exists():
            self.data.update(json.loads(self.path.read_text(encoding="utf-8")))

    def save(self) -> None:
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.data, indent=1), encoding="utf-8")
        with contextlib.suppress(OSError):
            tmp.chmod(0o600)
        os.replace(tmp, self.path)

    @property
    def users(self) -> dict:
        return self.data["users"]

    def add_user(self, name: str, password_hash: str, admin: bool) -> dict:
        port = self.data["next_port"]
        self.data["next_port"] = port + 1
        u = {"hash": password_hash, "gen": 1, "port": port, "admin": admin, "created": int(time.time())}
        self.users[name] = u
        self.save()
        return u

    def new_invite(self, by: str) -> str:
        self.prune_invites()
        code = secrets.token_urlsafe(9)
        self.data["invites"][code] = {"by": by, "created": int(time.time())}
        self.save()
        return code

    def prune_invites(self) -> None:
        cut = time.time() - 7 * 86400
        self.data["invites"] = {k: v for k, v in self.data["invites"].items() if v["created"] > cut}

    def invite_ok(self, code: str) -> bool:
        self.prune_invites()
        return code in self.data["invites"]


class Throttle:
    """Lock out an address (or a name) for a while after repeated wrong passwords."""

    def __init__(self, limit: int = 5):
        self.limit, self.fails = limit, {}

    def wait(self, key: str) -> int:
        n, until = self.fails.get(key, (0, 0.0))
        return max(0, int(until - time.time())) if n >= self.limit else 0

    def bad(self, key: str) -> None:
        n, _ = self.fails.get(key, (0, 0.0))
        n += 1
        self.fails[key] = (n, time.time() + min(900, 30 * 2 ** max(0, n - self.limit)) if n >= self.limit else 0.0)
        if len(self.fails) > 500:
            self.fails = {k: v for k, v in self.fails.items() if v[1] > time.time()}

    def good(self, key: str) -> None:
        self.fails.pop(key, None)


# ------------------------------------------------------------------------------------------------- shared fetcher
class Broker:
    """The ONE scanner connection to SS.lv for every account on this server.

    Every page anyone's copy asks for is fetched once and kept in a small shared store (hub/pages.db). Until it is
    stale, every other account gets the same copy instead of a new request: list pages stay fresh for LIST_TTL seconds
    (shorter than the fastest scan interval), single ads for DETAIL_TTL. So SS.lv sees the same traffic whether one
    person or six use the server; each account then rates the same listings with its own settings."""

    LIST_TTL = float(os.environ.get("SSDEAL_SHARED_LIST_TTL", "110"))
    DETAIL_TTL = float(os.environ.get("SSDEAL_SHARED_DETAIL_TTL", str(3 * 3600)))

    def __init__(self, settings: Settings, path: Path | None = None):
        self.settings = settings
        self.fetcher = PoliteFetcher(settings)
        self.inflight: dict[str, asyncio.Future] = {}
        self.hits = self.misses = 0
        self.db = sqlite3.connect(str(path) if path else ":memory:", check_same_thread=False)
        if path:
            self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("CREATE TABLE IF NOT EXISTS pages (url TEXT PRIMARY KEY, fetched_at REAL, payload TEXT)")
        self._pruned = 0.0

    def ttl(self, url: str) -> float:
        return self.DETAIL_TTL if "/msg/" in url else self.LIST_TTL

    def _pack(self, r) -> dict:
        s = self.fetcher.status()
        return {"status": r.status, "text": r.text, "final_url": r.final_url, "error": r.error, "elapsed": r.elapsed,
                "blocked": r.blocked, "disallowed": r.disallowed, "robots": s["robots"],
                "cooldown_seconds": s["cooldown_seconds"], "blocked_reason": s["blocked_reason"]}

    def _stored(self, url: str) -> dict | None:
        row = self.db.execute("SELECT fetched_at, payload FROM pages WHERE url=?", (url,)).fetchone()
        if not row or time.time() - row[0] >= self.ttl(url):
            return None
        out = json.loads(row[1])
        s = self.fetcher.status()
        out.update(cooldown_seconds=s["cooldown_seconds"], blocked_reason=s["blocked_reason"], shared=True, age=round(time.time() - row[0]))
        return out

    async def fetch(self, url: str) -> dict:
        hit = self._stored(url)
        if hit:
            self.hits += 1
            return hit
        if url in self.inflight:                                  # two people asked for the same page at once: one request
            self.hits += 1
            return await asyncio.shield(self.inflight[url])
        self.misses += 1
        fut = asyncio.ensure_future(self._do(url))
        self.inflight[url] = fut
        try:
            return await fut
        finally:
            self.inflight.pop(url, None)

    async def _do(self, url: str) -> dict:
        out = self._pack(await self.fetcher.get(url))
        if (out["status"] == 200 and not out["error"]) or out["status"] == 404:
            self.db.execute("INSERT OR REPLACE INTO pages VALUES (?,?,?)", (url, time.time(), json.dumps(out)))
            self.db.commit()
        if time.time() - self._pruned > 3600:
            self._pruned = time.time()
            self.db.execute("DELETE FROM pages WHERE fetched_at < ?", (time.time() - 2 * 86400,))
            self.db.commit()
        return out

    def stats(self) -> dict:
        n = self.db.execute("SELECT COUNT(*) FROM pages").fetchone()[0]
        total = self.hits + self.misses
        return {"requests": self.fetcher.state.requests, "cache_hits": self.hits, "pages_stored": n,
                "shared_pct": round(100 * self.hits / total) if total else 0}


# ------------------------------------------------------------------------------------------------- children
class Child:
    def __init__(self, name: str, port: int):
        self.name, self.port = name, port
        self.proc: subprocess.Popen | None = None
        self.fails, self.next_try, self.started = 0, 0.0, 0.0

    @property
    def running(self) -> bool:
        return self.proc is not None and self.proc.poll() is None

    def mem_mb(self) -> int | None:
        if not self.running:
            return None
        try:
            for line in Path(f"/proc/{self.proc.pid}/status").read_text().splitlines():
                if line.startswith("VmRSS:"):
                    return int(line.split()[1]) // 1024
        except OSError:
            pass
        return None


class Hub:
    def __init__(self, home: Path, port: int):
        self.home, self.port = home, port
        self.hub_home = home / "hub"
        self.users_dir = home / "users"
        for d in (self.hub_home, self.users_dir):
            d.mkdir(parents=True, exist_ok=True)
        self.store = Store(self.hub_home)
        self.broker = Broker(Settings(self.hub_home), self.hub_home / "pages.db")
        self.token = secrets.token_hex(24)                      # only the child copies know it
        self.children: dict[str, Child] = {}
        self.throttle = Throttle()
        self.max_users = int(os.environ.get("SSDEAL_MAX_USERS", "6"))
        kf = self.hub_home / "session.key"
        if not kf.exists():
            kf.write_text(secrets.token_hex(32), encoding="ascii")
            with contextlib.suppress(OSError):
                kf.chmod(0o600)
        self.key = kf.read_text(encoding="ascii").strip().encode()
        self.client = httpx.AsyncClient(timeout=httpx.Timeout(300, connect=3), limits=httpx.Limits(max_connections=60))
        self._task: asyncio.Task | None = None
        self.bootstrap()
        self.full_app_once()

    def full_app_once(self) -> None:
        """One time: switch existing accounts from the stripped-down Simple view to the full app (they can switch back)."""
        flag = self.hub_home / "full-app-v1"
        if flag.exists():
            return
        for name in self.store.users:
            f = self.users_dir / name / "settings.json"
            try:
                d = json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}
                if (d.get("ui") or {}).get("mode") != "advanced":
                    d.setdefault("ui", {})["mode"] = "advanced"
                    f.parent.mkdir(parents=True, exist_ok=True)
                    f.write_text(json.dumps(d, indent=2), encoding="utf-8")
            except (OSError, ValueError):
                pass
        flag.write_text("1")

    # ---- first start / moving an existing single-user install into the admin account
    def bootstrap(self) -> None:
        if self.store.users:
            return
        name = os.environ.get("SSDEAL_ADMIN_USER", "admin").strip().lower()
        pw = server_mod.password()
        if not NAME_RE.match(name) or len(pw) < 8:
            print("Hub mode needs SSDEAL_ADMIN_USER (3-24 letters/digits) and SSDEAL_PASSWORD (8+ characters) for the first admin account.")
            sys.exit(2)
        self.store.add_user(name, hash_pw(pw), True)
        dest = self.users_dir / name
        dest.mkdir(parents=True, exist_ok=True)
        moved = []
        for p in list(self.home.iterdir()):
            if p.name in KEEP_AT_ROOT:
                continue
            shutil.move(str(p), str(dest / p.name))
            moved.append(p.name)
        log.event("hub.bootstrap", f"admin '{name}' created; moved existing data: {', '.join(moved) or 'none'}")
        print(f"Created admin account '{name}'" + (f" and moved the existing data into it ({', '.join(moved)})" if moved else ""))

    # ---- sessions
    def _sig(self, body: str) -> str:
        return hmac.new(self.key, body.encode(), hashlib.sha256).hexdigest()[:40]

    def make_cookie(self, name: str) -> str:
        u = self.store.users[name]
        body = base64.urlsafe_b64encode(json.dumps({"u": name, "g": u["gen"], "exp": int(time.time()) + SESSION_DAYS * 86400}).encode()).decode()
        return f"{body}.{self._sig(body)}"

    def user_from_cookie(self, cookie: str | None) -> str | None:
        if not cookie or "." not in cookie:
            return None
        body, sig = cookie.rsplit(".", 1)
        if not hmac.compare_digest(sig, self._sig(body)):
            return None
        try:
            d = json.loads(base64.urlsafe_b64decode(body.encode()))
        except (ValueError, TypeError):
            return None
        u = self.store.users.get(d.get("u"))
        return d["u"] if u and u["gen"] == d.get("g") and d.get("exp", 0) > time.time() else None

    def user_from_token(self, token: str | None) -> str | None:
        """The Android app / scripts send the user's own API token (Settings -> Remote access) instead of a cookie."""
        if not token or len(token) < 8:
            return None
        for name in self.store.users:
            try:
                sec = json.loads((self.users_dir / name / "secrets.json").read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            t = sec.get("api_token", "")
            if t and hmac.compare_digest(str(t), token):
                return name
        return None

    def current_user(self, request: Request) -> str | None:
        return self.user_from_cookie(request.cookies.get(COOKIE)) or \
            self.user_from_token(request.headers.get("x-api-token") or request.query_params.get("token"))

    # ---- child processes
    def child(self, name: str) -> Child:
        c = self.children.get(name)
        if c is None:
            c = self.children[name] = Child(name, self.store.users[name]["port"])
        return c

    def start_child(self, name: str) -> None:
        c = self.child(name)
        if c.running:
            return
        home = self.users_dir / name
        home.mkdir(parents=True, exist_ok=True)
        if not (home / "settings.json").exists() and not (home / "import.zip").exists():
            # a new account starts with the full app (Advanced), not the stripped-down Simple view
            (home / "settings.json").write_text(json.dumps({"ui": {"mode": "advanced"}}), encoding="utf-8")
        server_mod.import_pending(home, lambda m: log.event("hub.import", f"{name}: {m}"))
        env = {k: v for k, v in os.environ.items() if not k.startswith("SSDEAL_") or k in ("SSDEAL_PUBLIC_URL",)}
        env.update(SSDEAL_MANAGED="1", SSDEAL_BIND="127.0.0.1", SSDEAL_FETCH_BROKER=f"http://127.0.0.1:{self.port}/_broker",
                   SSDEAL_BROKER_TOKEN=self.token)
        script = str(Path(__file__).resolve().parent.parent / "run_service.pyw")
        out = open(home / "child.out", "w", encoding="utf-8")
        c.proc = subprocess.Popen([sys.executable, script, "--port", str(c.port), "--home", str(home)], env=env,
                                  stdin=subprocess.DEVNULL, stdout=out, stderr=subprocess.STDOUT, cwd=str(Path(script).parent))
        out.close()
        c.started = time.time()
        log.event("hub.child_started", name=name, pid=c.proc.pid, port=c.port)

    async def stop_child(self, name: str) -> None:
        c = self.children.get(name)
        if not c or not c.proc:
            return
        p = c.proc
        if p.poll() is None:
            p.terminate()
            for _ in range(60):
                if p.poll() is not None:
                    break
                await asyncio.sleep(0.25)
            else:
                p.kill()
        c.proc = None

    async def supervise(self) -> None:
        while True:
            try:
                now = time.time()
                for name in list(self.store.users):
                    c = self.child(name)
                    if c.running:
                        if c.fails and now - c.started > 60:
                            c.fails = 0
                    elif now >= c.next_try:
                        if c.proc is not None:                  # it died
                            c.fails += 1
                            log.event("hub.child_exited", f"{name} exited with {c.proc.returncode}", _level=30)
                            c.proc = None
                        c.next_try = now + min(60, 2 ** c.fails)
                        await asyncio.to_thread(self.start_child, name)
            except Exception as e:                              # the supervisor itself must never die
                log.event("hub.supervisor_error", str(e), _level=40)
            await asyncio.sleep(3)

    async def shutdown(self) -> None:
        if self._task:
            self._task.cancel()
        await asyncio.gather(*(self.stop_child(n) for n in list(self.children)))
        await self.client.aclose()
        await self.broker.fetcher.close()


# ------------------------------------------------------------------------------------------------- pages
CSS = """
:root{--bg:#f4f5f7;--card:#fff;--fg:#14171c;--mut:#667085;--line:#d9dde3;--acc:#2563eb;--err:#c2261b}
@media(prefers-color-scheme:dark){:root{--bg:#0f1318;--card:#171c23;--fg:#e8ebf0;--mut:#98a2b3;--line:#2a313b;--acc:#5b8cff;--err:#ff6b5e}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:16px/1.45 system-ui,sans-serif;display:flex;justify-content:center;padding:24px 16px}
main{width:100%;max-width:440px}.wide{max-width:760px}h1{font-size:22px;margin:8px 0 4px}h2{font-size:17px;margin:24px 0 8px}
p{color:var(--mut);margin:4px 0 14px}.card{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:18px;margin:12px 0}
label{display:block;font-size:14px;color:var(--mut);margin:12px 0 4px}input{width:100%;padding:11px 12px;border-radius:10px;border:1px solid var(--line);background:var(--bg);color:var(--fg);font:inherit}
button,.btn{display:inline-block;margin-top:16px;padding:11px 16px;border:0;border-radius:10px;background:var(--acc);color:#fff;font:inherit;font-weight:600;cursor:pointer;text-decoration:none}
button.sec{background:transparent;color:var(--fg);border:1px solid var(--line);margin:0 6px 0 0;padding:6px 10px;font-size:14px;font-weight:500}
.full{width:100%}.err{color:var(--err);margin:10px 0 0}.ok{color:#188a4a;margin:10px 0 0}a{color:var(--acc)}
table{width:100%;border-collapse:collapse;font-size:14px}td,th{text-align:left;padding:8px 6px;border-bottom:1px solid var(--line)}
code{background:var(--bg);padding:2px 6px;border-radius:6px;word-break:break-all}.row{display:flex;gap:8px;flex-wrap:wrap;align-items:center}
"""


def page(title: str, body: str, wide: bool = False) -> HTMLResponse:
    return HTMLResponse(f"<!doctype html><html lang=en><meta charset=utf-8><meta name=viewport content='width=device-width,initial-scale=1'>"
                        f"<meta name=theme-color content='#0f1318'><title>{html.escape(title)}</title><style>{CSS}</style>"
                        f"<body><main class='{'wide' if wide else ''}'>{body}</main></body></html>",
                        headers={"Cache-Control": "no-store"})


def esc(s) -> str:
    return html.escape(str(s), quote=True)


def login_page(msg: str = "", name: str = "", nxt: str = "/", signup: bool = True) -> HTMLResponse:
    return page("SS Deal Finder - log in", f"""
<h1>SS Deal Finder</h1><p>Log in to your private account.</p>
<form class=card method=post action=/login>
<label for=u>Username</label><input id=u name=username value="{esc(name)}" autocomplete=username autocapitalize=none autofocus required>
<label for=p>Password</label><input id=p name=password type=password autocomplete=current-password required>
<input type=hidden name=next value="{esc(nxt)}">
{f'<div class=err>{esc(msg)}</div>' if msg else ''}
<button class=full type=submit>Log in</button></form>
{'<p>Got an invite? <a href=/signup>Create your account</a></p>' if signup else ''}""")


def signup_page(msg: str = "", name: str = "", code: str = "") -> HTMLResponse:
    return page("SS Deal Finder - sign up", f"""
<h1>Create your account</h1><p>You need an invite code from the person who runs this server. Your data stays private to your account.</p>
<form class=card method=post action=/signup>
<label for=c>Invite code</label><input id=c name=code value="{esc(code)}" autocapitalize=none required>
<label for=u>Choose a username (letters, digits, - or _; 3-24)</label><input id=u name=username value="{esc(name)}" autocomplete=username autocapitalize=none required>
<label for=p>Choose a password (at least 8 characters)</label><input id=p name=password type=password autocomplete=new-password minlength=8 required>
{f'<div class=err>{esc(msg)}</div>' if msg else ''}
<button class=full type=submit>Create account</button></form>
<p><a href=/login>I already have an account</a></p>""")


def account_page(name: str, admin: bool, msg: str = "", ok: bool = False) -> HTMLResponse:
    return page("Account", f"""
<h1>Account</h1><p>Logged in as <b>{esc(name)}</b>{' (admin)' if admin else ''}. <a href=/>Back to the app</a>{' · <a href=/admin>Manage users</a>' if admin else ''}</p>
<form class=card method=post action=/account>
<h2 style=margin-top:0>Change password</h2>
<label for=o>Current password</label><input id=o name=old type=password autocomplete=current-password required>
<label for=n>New password (at least 8 characters)</label><input id=n name=new type=password autocomplete=new-password minlength=8 required>
{f'<div class="{"ok" if ok else "err"}">{esc(msg)}</div>' if msg else ''}
<button type=submit>Change password</button><p style=margin-top:10px>Changing it logs you out on every other device.</p></form>
<form class=card method=post action=/logout><h2 style=margin-top:0>Log out</h2><p>Only this device.</p>
<button class=sec type=submit style="margin:0">Log out</button></form>""")


ADMIN_JS = """
const $=s=>document.querySelector(s);
async function api(path,body){const r=await fetch(path,{method:body?'POST':'GET',headers:{'content-type':'application/json'},body:body?JSON.stringify(body):undefined});
 const d=await r.json().catch(()=>({}));if(!r.ok)throw new Error(d.detail||('HTTP '+r.status));return d}
function el(t,txt,cls){const e=document.createElement(t);if(txt!=null)e.textContent=txt;if(cls)e.className=cls;return e}
async function load(){
 const d=await api('/hub/users');const tb=$('#users');tb.replaceChildren();
 for(const u of d.users){const tr=el('tr');tr.append(el('td',u.name+(u.admin?' (admin)':'')),el('td',u.running?'running':'stopped'),el('td',u.mem_mb?u.mem_mb+' MB':'-'));
  const td=el('td');
  if(!u.admin){const b=el('button','Delete','sec');b.onclick=async()=>{if(confirm('Delete '+u.name+'? Their data is kept in a folder on the server but they can no longer log in.')){await api('/hub/user/delete',{name:u.name});load()}};td.append(b)}
  const r=el('button','Reset password','sec');r.onclick=async()=>{if(confirm('Make a new temporary password for '+u.name+'?')){const x=await api('/hub/user/reset',{name:u.name});alert('Temporary password for '+u.name+':\\n\\n'+x.password+'\\n\\nGive it to them; they can change it under Account.');load()}};td.append(r);
  tr.append(td);tb.append(tr)}
 const iv=$('#invites');iv.replaceChildren();
 for(const c of d.invites){const p=el('p');p.append(el('code',location.origin+'/signup?code='+c));iv.append(p)}
 $('#cap').textContent=d.users.length+' of '+d.max+' accounts used';
 $('#cache').textContent='One shared scan for everyone: '+d.broker.requests+' requests to SS.lv, '+d.broker.cache_hits+' pages handed out from the shared copy ('+d.broker.shared_pct+'% of all page requests).'}
$('#inv').onclick=async()=>{try{await api('/hub/invite',{});load()}catch(e){alert(e.message)}};
load().catch(e=>alert(e.message));setInterval(()=>load().catch(()=>{}),15000);
"""


def admin_page() -> HTMLResponse:
    return page("Manage users", f"""
<h1>Manage users</h1><p><a href=/>Back to the app</a> · <a href=/account>Account</a></p>
<div class=card><table><thead><tr><th>User<th>State<th>Memory<th></thead><tbody id=users></tbody></table>
<p id=cap style=margin-top:12px></p><p id=cache></p></div>
<div class=card><h2 style=margin-top:0>Invite someone</h2><p>Make a link, send it to your friend. It works once and for 7 days.</p>
<div id=invites></div><button id=inv>New invite link</button></div><script>{ADMIN_JS}</script>""", wide=True)


# ------------------------------------------------------------------------------------------------- the app
def ip_of(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for", "")
    return (fwd.split(",")[0].strip() if fwd else (request.client.host if request.client else "?")) or "?"


async def read_form(request: Request) -> dict:
    """The login/sign-up forms are plain URL-encoded posts; parsed here so no extra library (python-multipart) is needed."""
    from urllib.parse import parse_qs
    body = (await request.body())[:20000].decode("utf-8", "replace")
    return {k: v[0] for k, v in parse_qs(body, keep_blank_values=True).items()}


def safe_next(n: str) -> str:
    return n if n.startswith("/") and not n.startswith("//") and "\\" not in n else "/"


def create_app(hub: Hub) -> Starlette:
    def secure(request: Request) -> bool:
        return request.headers.get("x-forwarded-proto", request.url.scheme) == "https"

    def set_cookie(resp: Response, request: Request, name: str) -> Response:
        resp.set_cookie(COOKIE, hub.make_cookie(name), max_age=SESSION_DAYS * 86400, httponly=True, secure=secure(request), samesite="lax", path="/")
        return resp

    def same_origin(request: Request) -> bool:
        o = request.headers.get("origin")
        return not o or o.split("://", 1)[-1] == request.headers.get("x-forwarded-host", request.headers.get("host", ""))

    async def healthz(request: Request):
        up = {n: hub.child(n).running for n in hub.store.users}
        return JSONResponse({"ok": True, "users": len(up), "running": sum(up.values())})

    async def login(request: Request):
        if request.method == "GET":
            return login_page(nxt=safe_next(request.query_params.get("next", "/")))
        form = await read_form(request)
        name, pw, nxt = str(form.get("username", "")).strip().lower(), str(form.get("password", "")), safe_next(str(form.get("next", "/")))
        if not same_origin(request):
            return login_page("Please try again.", name, nxt)
        keys = (f"ip:{ip_of(request)}", f"user:{name}")
        wait = max(hub.throttle.wait(k) for k in keys)
        if wait:
            return login_page(f"Too many wrong passwords. Try again in {wait // 60 + 1} min.", name, nxt)
        u = hub.store.users.get(name)
        ok = await asyncio.to_thread(check_pw, pw, u["hash"] if u else hash_pw("x" * 8, b"0" * 16))      # same work whether the name exists or not
        if not (u and ok):
            for k in keys:
                hub.throttle.bad(k)
            return login_page("Wrong username or password.", name, nxt)
        for k in keys:
            hub.throttle.good(k)
        return set_cookie(RedirectResponse(nxt, status_code=303), request, name)

    async def signup(request: Request):
        if request.method == "GET":
            return signup_page(code=request.query_params.get("code", ""))
        form = await read_form(request)
        code, name, pw = str(form.get("code", "")).strip(), str(form.get("username", "")).strip().lower(), str(form.get("password", ""))
        if not same_origin(request):
            return signup_page("Please try again.", name, code)
        k = f"ip:{ip_of(request)}"
        if hub.throttle.wait(k):
            return signup_page("Too many tries. Wait a few minutes.", name, code)
        if not hub.store.invite_ok(code):
            hub.throttle.bad(k)
            return signup_page("That invite code is not valid (or it was already used or is older than 7 days).", name, code)
        if not NAME_RE.match(name):
            return signup_page("Username: 3-24 characters, lowercase letters, digits, - or _.", name, code)
        if name in hub.store.users or (hub.users_dir / name).exists():
            return signup_page("That username is taken.", name, code)
        if len(pw) < 8:
            return signup_page("Password needs at least 8 characters.", name, code)
        if len(hub.store.users) >= hub.max_users:
            return signup_page("This server is full.", name, code)
        h = await asyncio.to_thread(hash_pw, pw)
        hub.store.data["invites"].pop(code, None)
        hub.store.add_user(name, h, False)
        log.event("hub.signup", name=name)
        return set_cookie(RedirectResponse("/", status_code=303), request, name)

    async def logout(request: Request):
        resp = RedirectResponse("/login", status_code=303) if request.method == "POST" or request.url.path == "/logout" else JSONResponse({"ok": True})
        resp.delete_cookie(COOKIE, path="/")
        return resp

    async def api_logout(request: Request):
        resp = JSONResponse({"ok": True})
        resp.delete_cookie(COOKIE, path="/")
        return resp

    async def api_auth(request: Request):
        name = hub.current_user(request)
        if not name:
            return JSONResponse({"server": True, "hub": True, "authed": False})
        resp = JSONResponse({"server": True, "hub": True, "authed": True, "user": name, "admin": bool(hub.store.users[name]["admin"])})
        if request.cookies.get(COOKIE):
            set_cookie(resp, request, name)             # an active user stays logged in: the 30 days restart on every visit
        return resp

    def need_user(request: Request) -> str | None:
        return hub.user_from_cookie(request.cookies.get(COOKIE))

    async def account(request: Request):
        name = need_user(request)
        if not name:
            return RedirectResponse("/login?next=/account", status_code=303)
        u = hub.store.users[name]
        if request.method == "GET":
            return account_page(name, u["admin"])
        form = await read_form(request)
        if not same_origin(request):
            return account_page(name, u["admin"], "Please try again.")
        if hub.throttle.wait(f"user:{name}"):
            return account_page(name, u["admin"], "Too many wrong passwords. Wait a few minutes.")
        if not await asyncio.to_thread(check_pw, str(form.get("old", "")), u["hash"]):
            hub.throttle.bad(f"user:{name}")
            return account_page(name, u["admin"], "Current password is wrong.")
        new = str(form.get("new", ""))
        if len(new) < 8:
            return account_page(name, u["admin"], "New password needs at least 8 characters.")
        u["hash"] = await asyncio.to_thread(hash_pw, new)
        u["gen"] += 1
        hub.store.save()
        resp = account_page(name, u["admin"], "Password changed. Other devices were logged out.", ok=True)
        return set_cookie(resp, request, name)

    def admin_user(request: Request) -> str | None:
        n = need_user(request)
        return n if n and hub.store.users[n]["admin"] else None

    async def admin(request: Request):
        if not admin_user(request):
            return RedirectResponse("/login?next=/admin", status_code=303)
        return admin_page()

    async def hub_users(request: Request):
        if not admin_user(request):
            return JSONResponse({"detail": "Admins only"}, status_code=403)
        users = [{"name": n, "admin": u["admin"], "running": hub.child(n).running, "mem_mb": hub.child(n).mem_mb()} for n, u in hub.store.users.items()]
        hub.store.prune_invites()
        return {"users": users, "invites": list(hub.store.data["invites"]), "max": hub.max_users,
                "broker": hub.broker.stats()}

    async def hub_invite(request: Request):
        me = admin_user(request)
        if not me or not same_origin(request):
            return JSONResponse({"detail": "Admins only"}, status_code=403)
        if len(hub.store.users) >= hub.max_users:
            return JSONResponse({"detail": f"The server is limited to {hub.max_users} accounts."}, status_code=400)
        return {"code": hub.store.new_invite(me)}

    async def hub_delete(request: Request):
        me = admin_user(request)
        if not me or not same_origin(request):
            return JSONResponse({"detail": "Admins only"}, status_code=403)
        name = str((await request.json()).get("name", ""))
        u = hub.store.users.get(name)
        if not u or u["admin"]:
            return JSONResponse({"detail": "Cannot delete that account."}, status_code=400)
        await hub.stop_child(name)
        hub.children.pop(name, None)
        hub.store.users.pop(name)
        hub.store.save()
        src = hub.users_dir / name
        if src.exists():
            src.rename(hub.users_dir / f"_deleted-{name}-{time.strftime('%Y%m%d-%H%M%S')}")
        return {"ok": True}

    async def hub_reset(request: Request):
        me = admin_user(request)
        if not me or not same_origin(request):
            return JSONResponse({"detail": "Admins only"}, status_code=403)
        name = str((await request.json()).get("name", ""))
        u = hub.store.users.get(name)
        if not u:
            return JSONResponse({"detail": "No such user"}, status_code=400)
        pw = secrets.token_urlsafe(9)
        u["hash"] = await asyncio.to_thread(hash_pw, pw)
        u["gen"] += 1
        hub.store.save()
        return {"password": pw}

    async def server_import(request: Request):
        name = hub.current_user(request)
        if not name:
            return JSONResponse({"detail": "Please log in", "login": True, "hub": True}, status_code=401)
        data = await request.body()
        if len(data) > 300 * 1024 * 1024:
            return JSONResponse({"detail": "That file is too big (limit 300 MB)"}, status_code=413)
        why = server_mod.check_pack(data)
        if why:
            return JSONResponse({"detail": why}, status_code=400)
        home = hub.users_dir / name
        await hub.stop_child(name)
        (home / "import.zip").write_bytes(data)
        (home / "import.force").write_text("1")
        hub.child(name).next_try = 0                            # the supervisor starts it again within seconds, importing first
        return {"ok": True, "restarting": True}

    # ---- the shared fetcher
    def broker_ok(request: Request) -> bool:
        return "x-forwarded-for" not in request.headers and hmac.compare_digest(request.headers.get("x-broker-token", ""), hub.token)

    async def broker_fetch(request: Request):
        if not broker_ok(request):
            return JSONResponse({"detail": "no"}, status_code=403)
        url = str((await request.json()).get("url", ""))
        return await hub.broker.fetch(url)

    async def broker_reset(request: Request):
        if not broker_ok(request):
            return JSONResponse({"detail": "no"}, status_code=403)
        hub.broker.fetcher.reset_cooldown()
        return {"ok": True}

    # ---- everything else goes to the logged-in person's own copy
    async def proxy(request: Request):
        path = request.url.path
        name = hub.current_user(request)
        if not name:
            if path.startswith("/api"):
                return JSONResponse({"detail": "Please log in", "login": True, "hub": True}, status_code=401)
            return RedirectResponse("/login" + (f"?next={request.url.path}" if request.method == "GET" and path != "/" else ""), status_code=303)
        c = hub.child(name)
        url = f"http://127.0.0.1:{c.port}{path}" + (f"?{request.url.query}" if request.url.query else "")
        headers = {k: v for k, v in request.headers.items() if k.lower() not in STRIP_REQ}
        try:
            up = await hub.client.send(hub.client.build_request(request.method, url, headers=headers, content=request.stream()), stream=True)
        except httpx.ConnectError:
            if path.startswith("/api"):
                return JSONResponse({"detail": "Your copy is starting up, try again in a few seconds."}, status_code=503, headers={"Retry-After": "3"})
            return HTMLResponse("<meta http-equiv=refresh content=3><body style='font:16px system-ui;padding:24px;background:#0f1318;color:#e8ebf0'>"
                                "Starting your copy of the app... this page reloads by itself.", status_code=503)
        except httpx.HTTPError as e:
            return JSONResponse({"detail": f"Could not reach your copy: {e}"}, status_code=502)

        async def body():
            try:
                async for chunk in up.aiter_raw():
                    yield chunk
            finally:
                await up.aclose()

        resp = StreamingResponse(body(), status_code=up.status_code)
        resp.raw_headers = [(k, v) for k, v in up.headers.raw if k.decode().lower() not in HOP]
        return resp

    def J(fn):
        async def wrapped(request: Request):
            r = await fn(request)
            return JSONResponse(r) if isinstance(r, dict) else r
        return wrapped

    methods = ["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"]
    routes = [
        Route("/healthz", J(healthz)),
        Route("/login", J(login), methods=["GET", "POST"]),
        Route("/signup", J(signup), methods=["GET", "POST"]),
        Route("/logout", J(logout), methods=["GET", "POST"]),
        Route("/account", J(account), methods=["GET", "POST"]),
        Route("/admin", J(admin)),
        Route("/hub/users", J(hub_users)),
        Route("/hub/invite", J(hub_invite), methods=["POST"]),
        Route("/hub/user/delete", J(hub_delete), methods=["POST"]),
        Route("/hub/user/reset", J(hub_reset), methods=["POST"]),
        Route("/api/auth", J(api_auth)),
        Route("/api/logout", J(api_logout), methods=["POST"]),
        Route("/api/login", lambda r: JSONResponse({"detail": "This server now has accounts. Open /login (press Ctrl+F5 if this box comes back) and log in with your username.", "hub": True}, status_code=400), methods=["POST"]),
        Route("/api/server/import", J(server_import), methods=["POST"]),
        Route("/_broker/fetch", J(broker_fetch), methods=["POST"]),
        Route("/_broker/reset", J(broker_reset), methods=["POST"]),
        Route("/{path:path}", J(proxy), methods=methods),
    ]

    @contextlib.asynccontextmanager
    async def lifespan(app):
        hub._task = asyncio.ensure_future(hub.supervise())
        try:
            yield
        finally:
            await hub.shutdown()

    return Starlette(routes=routes, lifespan=lifespan)


def enabled(flag: bool = False) -> bool:
    return bool(flag or os.environ.get("SSDEAL_HUB", "").strip() not in ("", "0", "false", "no"))


def main(home: Path, port: int, host: str = "0.0.0.0") -> None:
    hub = Hub(home, port)
    uvicorn.run(create_app(hub), host=host, port=port, log_level="warning", proxy_headers=False, timeout_graceful_shutdown=20)
