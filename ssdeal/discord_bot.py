"""Interactive Discord bot (not a webhook).

* Posts deal notifications as embeds with buttons (Interested, Save, Ignore,
  Too expensive, Bought, More info) and a 1–10 rating menu.
* Button presses and natural-language replies update the database through the
  same Actions layer the desktop UI uses.
* Ambiguous replies get a clarifying question with quick-answer buttons.

Setup (see README): create a bot at https://discord.com/developers, enable the
"Message Content Intent", invite it with Send Messages + Read Message History
+ Embed Links, then paste the token and channel ID into Settings → Discord.
"""
from __future__ import annotations

import asyncio
import datetime as dt
import time

from .actions import Actions
from .db import Database, jdumps, jloads
from .intents import parse_reply
from .logs import get_logger, register_secret

log = get_logger("discord")

LEVEL_COLORS = {"GOOD_DEAL": 0x22C55E, "INTERESTING": 0xF59E0B, "IGNORE": 0x64748B, "REMINDER": 0x3B82F6}
BUTTONS = [("interested", "Interested", "success"), ("saved", "Save", "primary"), ("ignored", "Ignore", "secondary"),
           ("too_expensive", "Too expensive", "secondary"), ("bought", "Bought", "success"), ("info", "More info", "primary")]


# ---------------------------------------------------------------- pure helpers (unit-testable)

def format_value(details: dict) -> str:
    v = details.get("valuation") or {}
    if v.get("low") and v.get("high"):
        basis = v.get("basis") or v.get("method") or ""
        tag = "asking-price based" if "sales" not in str(basis) else "incl. confirmed sales"
        return f"€{v['low']:.0f}–{v['high']:.0f} ({tag}, conf. {int((details.get('deal', {}).get('confidence') or 0) * 100)}%)"
    if v.get("category_median"):
        return f"unknown model · category median €{v['category_median']:.0f}"
    return "not enough data yet"


def build_embed_dict(listing: dict, level: str, reason: str) -> dict:
    d = jloads(listing.get("score_details"), {}) if isinstance(listing.get("score_details"), str) else (listing.get("score_details") or {})
    title = listing.get("product_name") or (listing.get("title") or "")[:90]
    tag = {"GOOD_DEAL": "🔥 GOOD DEAL", "INTERESTING": "👀 INTERESTING"}.get(level, level)
    fields = [
        ("Asking price", f"€{listing['price']:.0f}" if listing.get("price") is not None else "—", True),
        ("Estimated market value", format_value(d), True),
        ("Profit / ROI", (f"~€{listing['profit_est']:.0f} / ~{listing.get('roi_est') or 0:.0f}%" if listing.get("profit_est") is not None else "–"), True),
        ("Condition", (listing.get("condition") or "unknown").capitalize(), True),
        ("Category", listing.get("category_key") or "—", True),
        ("Reason", reason[:1000] or "—", False),
    ]
    rep = (d.get("deal") or {}).get("repair")
    if rep:
        fields.append(("Repair outlook", f"expected profit €{rep['expected_profit']:.0f}, worst-case loss "
                                         f"€{rep['worst_case_loss']:.0f}, success ~{int(rep['success_probability'] * 100)}% "
                                         f"(uncertainty {rep['uncertainty']})", False))
    if listing.get("title") and listing.get("product_name"):
        fields.append(("Listing text", listing["title"][:200], False))
    return {"title": f"{tag} · {title}"[:250], "url": listing.get("url"), "color": LEVEL_COLORS.get(level, 0x64748B),
            "fields": fields, "thumbnail": listing.get("image_url"),
            "footer": f"Listing #{listing['id']} · reply to this message to give feedback (e.g. 'would buy for €100')"}


def info_text(db: Database, listing_id: int) -> str:
    row = db.one("SELECT * FROM listings WHERE id=?", (listing_id,))
    if not row:
        return "Listing not found."
    d = jloads(row["score_details"], {})
    lines = [f"**{row['product_name'] or row['title'][:80]}** — €{row['price'] or 0:.0f} ({row['status']})", ""]
    lines.append("**Why this Deal Score:**")
    for r in (d.get("deal") or {}).get("reasons", [])[:8]:
        lines.append(f"• {r['points']:+.0f} {r['text']}")
    lines.append("")
    lines.append("**Personal Value factors:**")
    for p in (d.get("personal") or {}).get("parts", [])[:6]:
        lines.append(f"• {p['value']:+.2f} {p['text']}")
    v = d.get("valuation") or {}
    if v.get("notes"):
        lines.append("")
        lines.extend(f"_{n}_" for n in v["notes"] if n)
    hist = db.query("SELECT price, observed_at FROM price_history WHERE listing_id=? ORDER BY observed_at", (listing_id,))
    if len(hist) > 1:
        lines.append("")
        lines.append("**Price history:** " + " → ".join(f"€{h['price']:.0f}" for h in hist))
    if row["repost_of"]:
        lines.append(f"Repost of listing #{row['repost_of']}")
    lines.append(f"First seen {dt.datetime.fromtimestamp(row['first_seen']):%d.%m %H:%M} · {row['url']}")
    return "\n".join(lines)[:1900]


def apply_parsed(actions: Actions, listing_id: int, parsed: list[dict], source: str = "discord") -> tuple[list[str], dict | None]:
    """Apply parsed reply actions. Returns (messages, clarification or None)."""
    msgs: list[str] = []
    for a in parsed:
        t = a["type"]
        if t == "clarify":
            return msgs, a
        try:
            if t == "remind":
                r = actions.apply(listing_id, "remind", at=a["at"], source=source)
            elif t == "market_value":
                r = actions.apply(listing_id, "market_value", a["value"], source=source)
            elif t == "bought":
                r = actions.apply(listing_id, "bought", a.get("value"), source=source)
                if not a.get("value"):
                    msgs.append(r["message"])
                    return msgs, {"type": "clarify", "question": "What price did you pay? (e.g. 'bought for €120')",
                                  "options": []}
            elif t in ("rating", "would_pay", "sold"):
                r = actions.apply(listing_id, t, a["value"], source=source)
            else:
                r = actions.apply(listing_id, t, source=source)
            msgs.append(r["message"])
            if r.get("clarify"):
                return msgs, {"type": "clarify", "question": r["message"], "options": []}
        except (ValueError, KeyError) as e:
            msgs.append(f"⚠️ {e}")
    return msgs, None


# ---------------------------------------------------------------- bot

class DealBot:
    def __init__(self, db: Database, settings, actions: Actions, notifier):
        self.db = db
        self.settings = settings
        self.actions = actions
        self.notifier = notifier
        self.queue: asyncio.Queue = asyncio.Queue()
        notifier.discord_queue = self.queue
        notifier.discord_online = lambda: str(self.status).startswith("online")
        self.client = None
        self.status = "disabled"
        self.last_error = ""
        self._task: asyncio.Task | None = None

    def enabled(self) -> bool:
        return bool(self.settings.get("discord.enabled") and self.settings.secret("discord_token")
                    and str(self.settings.get("discord.channel_id") or "").isdigit())

    async def run_forever(self) -> None:
        """Supervisor: (re)starts the bot when it is enabled, backs off on failures."""
        backoff = 10
        while True:
            if not self.enabled():
                self.status = "disabled (configure token + channel in Settings)"
                await asyncio.sleep(15)
                continue
            try:
                await self._run_once()
                backoff = 10
            except asyncio.CancelledError:
                raise
            except Exception as e:  # login failure, network...
                self.status = "error"
                self.last_error = f"{type(e).__name__}: {e}"
                log.error(f"Discord bot stopped: {self.last_error}", event="discord.error")
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 600)

    async def _run_once(self) -> None:
        import discord

        token = self.settings.secret("discord_token")
        register_secret(token)
        intents = discord.Intents.default()
        intents.message_content = True
        client = discord.Client(intents=intents)
        self.client = client
        bot = self

        @client.event
        async def on_ready():
            bot.status = f"online as {client.user}"
            log.event("discord.ready", user=str(client.user))

        @client.event
        async def on_interaction(interaction: "discord.Interaction"):
            try:
                await bot._on_interaction(interaction)
            except Exception as e:
                log.error(f"interaction failed: {e}", exc_info=True, event="discord.error")

        @client.event
        async def on_message(message: "discord.Message"):
            try:
                await bot._on_message(message)
            except Exception as e:
                log.error(f"message handling failed: {e}", exc_info=True, event="discord.error")

        sender = asyncio.create_task(self._sender())
        try:
            self.status = "connecting"
            await client.start(token)
        finally:
            sender.cancel()
            if not client.is_closed():
                await client.close()

    # ---------------------------------------------------------------- outgoing
    async def _channel(self):
        cid = int(self.settings.get("discord.channel_id"))
        ch = self.client.get_channel(cid)
        if ch is None:
            ch = await self.client.fetch_channel(cid)
        return ch

    async def _sender(self) -> None:
        import discord

        await self.client.wait_until_ready()
        while True:
            item = await self.queue.get()
            try:
                ch = await self._channel()
                if item["type"] == "deal":
                    listing = self.db.one("SELECT * FROM listings WHERE id=?", (item["listing_id"],))
                    note = self.db.one("SELECT * FROM notifications WHERE id=?", (item["notification_id"],))
                    if not listing or not note:
                        continue
                    msg = await ch.send(embed=self._embed(listing, note["level"], note["reason"] or ""),
                                        view=self._view(listing["id"]))
                    self.db.update("notifications", note["id"], {"discord_message_id": str(msg.id)})
                else:
                    e = discord.Embed(title=item["title"][:250], description=item["body"][:3000],
                                      url=item.get("url") or None, color=LEVEL_COLORS["REMINDER"])
                    await ch.send(embed=e)
            except Exception as e:
                self.last_error = f"{type(e).__name__}: {e}"
                log.error(f"Discord send failed: {self.last_error}", event="discord.error")
                await asyncio.sleep(5)

    def _embed(self, listing: dict, level: str, reason: str):
        import discord

        d = build_embed_dict(listing, level, reason)
        e = discord.Embed(title=d["title"], url=d["url"], color=d["color"])
        for name, value, inline in d["fields"]:
            e.add_field(name=name, value=value, inline=inline)
        if d["thumbnail"]:
            e.set_thumbnail(url=d["thumbnail"])
        e.set_footer(text=d["footer"])
        return e

    def _view(self, listing_id: int):
        import discord

        view = discord.ui.View(timeout=None)
        styles = {"success": discord.ButtonStyle.success, "primary": discord.ButtonStyle.primary,
                  "secondary": discord.ButtonStyle.secondary}
        for key, label, style in BUTTONS:
            view.add_item(discord.ui.Button(label=label, style=styles[style], custom_id=f"ssd:{key}:{listing_id}"))
        select = discord.ui.Select(custom_id=f"ssd:rate:{listing_id}", placeholder="Rate this notification 1–10",
                                   options=[discord.SelectOption(label=f"{i}/10", value=str(i),
                                                                 description={1: "Completely useless", 5: "Somewhat interesting",
                                                                              10: "Exactly what I want"}.get(i))
                                            for i in range(1, 11)])
        view.add_item(select)
        return view

    def _allowed(self, user_id: int) -> bool:
        raw = str(self.settings.get("discord.allowed_user_ids") or "").strip()
        if not raw:
            return True
        return str(user_id) in {x.strip() for x in raw.split(",")}

    # ---------------------------------------------------------------- incoming
    async def _on_interaction(self, interaction) -> None:
        import discord

        data = interaction.data or {}
        cid = data.get("custom_id", "")
        if not cid.startswith("ssd:"):
            return
        if not self._allowed(interaction.user.id):
            await interaction.response.send_message("You're not allowed to manage these deals.", ephemeral=True)
            return
        parts = cid.split(":")
        kind, lid = parts[1], int(parts[2])
        if interaction.type == discord.InteractionType.modal_submit:
            raw = ""
            for row in data.get("components", []):
                for c in row.get("components", []):
                    raw = c.get("value", "")
            parsed = parse_reply(f"bought for {raw}")
            msgs, _ = apply_parsed(self.actions, lid, parsed)
            await interaction.response.send_message("\n".join(msgs) or "Recorded.", ephemeral=True)
            return
        if kind == "info":
            await interaction.response.send_message(info_text(self.db, lid), ephemeral=True)
            return
        if kind == "bought":
            listing = self.db.one("SELECT price FROM listings WHERE id=?", (lid,))
            modal = discord.ui.Modal(title="Bought — what did you pay?", custom_id=f"ssd:boughtmodal:{lid}")
            modal.add_item(discord.ui.TextInput(label="Price paid (€)", default=f"{(listing or {}).get('price') or ''}",
                                                required=True, max_length=10))
            await interaction.response.send_modal(modal)
            return
        if kind == "rate":
            value = int((data.get("values") or ["5"])[0])
            r = self.actions.apply(lid, "rating", value, source="discord")
        elif kind == "clar":
            idx = int(parts[3])
            pend = self.db.one("SELECT * FROM pending_clarifications WHERE id=?", (lid,))
            if not pend:
                await interaction.response.send_message("That question has expired.", ephemeral=True)
                return
            opts = jloads(pend["options"], [])
            parsed = parse_reply(opts[idx]) if idx < len(opts) else []
            msgs, clar = apply_parsed(self.actions, pend["listing_id"], parsed)
            self.db.update("pending_clarifications", pend["id"], {"resolved": 1})
            await interaction.response.send_message("\n".join(msgs) or (clar or {}).get("question", "OK"))
            return
        else:
            r = self.actions.apply(lid, kind, source="discord")
        await interaction.response.send_message(r["message"], ephemeral=True)

    async def _on_message(self, message) -> None:
        if message.author.bot or not self.client:
            return
        if str(message.channel.id) != str(self.settings.get("discord.channel_id")):
            return
        if not self._allowed(message.author.id):
            return
        content = (message.content or "").strip()
        if content.lower() in ("!help", "help"):
            await message.reply("Reply to a deal message with things like: *too expensive*, *I would buy this for €100*, "
                                "*bought for €120*, *remind me tomorrow*, *7/10*, *not interested in this brand*, "
                                "*it's worth €200*.\nCommands: `!status`, `!top`")
            return
        if content.lower() == "!status":
            n = self.db.scalar("SELECT COUNT(*) FROM listings WHERE status='active'", default=0)
            last = self.db.scalar("SELECT MAX(finished_at) FROM scan_runs WHERE ok=1", default=0)
            await message.reply(f"Monitoring {n} active listings. Last successful scan: "
                                f"{dt.datetime.fromtimestamp(last):%H:%M:%S}" if last else "No successful scan yet.")
            return
        if content.lower() == "!top":
            rows = self.db.query("""SELECT id, product_name, title, price, deal_score, url FROM listings
                                    WHERE status='active' AND classification!='IGNORE' ORDER BY deal_score DESC LIMIT 5""")
            await message.reply("\n".join(f"**{r['deal_score']:.0f}** · €{r['price'] or 0:.0f} · "
                                          f"[{(r['product_name'] or r['title'])[:60]}]({r['url']})" for r in rows) or "Nothing yet.")
            return
        if not message.reference or not message.reference.message_id:
            return
        ref = str(message.reference.message_id)
        note = self.db.one("SELECT listing_id FROM notifications WHERE discord_message_id=?", (ref,))
        pend = None
        if not note:
            pend = self.db.one("SELECT * FROM pending_clarifications WHERE channel_message_id=? AND resolved=0", (ref,))
            if not pend:
                return
            lid = pend["listing_id"]
        else:
            lid = note["listing_id"]
        parsed = parse_reply(content)
        msgs, clar = apply_parsed(self.actions, lid, parsed)
        if pend and not clar:
            self.db.update("pending_clarifications", pend["id"], {"resolved": 1})
        if clar:
            await self._ask(message, lid, clar, msgs)
        else:
            await message.reply("\n".join(msgs) or "OK.")

    async def _ask(self, message, listing_id: int, clar: dict, prefix: list[str]) -> None:
        import discord

        opts = clar.get("options") or []
        pid = self.db.insert("pending_clarifications", {"listing_id": listing_id, "text": clar["question"],
                                                        "options": jdumps(opts), "created_at": time.time()})
        view = discord.ui.View(timeout=None)
        for i, o in enumerate(opts[:5]):
            view.add_item(discord.ui.Button(label=o[:80], style=discord.ButtonStyle.secondary,
                                            custom_id=f"ssd:clar:{pid}:{i}"))
        sent = await message.reply("\n".join(prefix + [f"❓ {clar['question']}"]), view=view if opts else None)
        self.db.update("pending_clarifications", pid, {"channel_message_id": str(sent.id)})

    def info(self) -> dict:
        return {"status": self.status, "last_error": self.last_error, "enabled": self.enabled(),
                "queue": self.queue.qsize()}
