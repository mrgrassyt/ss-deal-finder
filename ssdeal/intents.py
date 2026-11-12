"""Interpret natural replies to notifications (English + Latvian, some Russian).

parse_reply() returns a list of actions. If the meaning is unclear it returns a
single {"type": "clarify"} action with options instead of guessing — the bot
then asks the user rather than changing data incorrectly.
"""
from __future__ import annotations

import datetime as dt
import re

from .textutil import fold

NUM = r"€?\s*(\d{1,6}(?:[.,]\d{1,2})?)\s*(?:€|eur|euro|eiro)?"

WEEKDAYS = {
    "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3, "friday": 4, "saturday": 5, "sunday": 6,
    "pirmdien": 0, "otrdien": 1, "tresdien": 2, "ceturtdien": 3, "piektdien": 4, "sestdien": 5, "svetdien": 6,
}


def _num(s: str) -> float:
    return float(s.replace(",", "."))


def parse_when(text: str, now: dt.datetime | None = None) -> dt.datetime | None:
    t = fold(text)
    now = now or dt.datetime.now()
    m = re.search(r"(?:in|pec|через)\s+(\d{1,3})\s*(min\w*|minut\w*|h\b|hour\w*|stund\w*|час\w*|d\b|day\w*|dien\w*|дн\w*|week\w*|ned\w*)", t)
    if m:
        n = int(m.group(1))
        u = m.group(2)
        if u.startswith(("min", "мин")):
            return now + dt.timedelta(minutes=n)
        if u.startswith(("h", "stund", "час")):
            return now + dt.timedelta(hours=n)
        if u.startswith(("week", "ned")):
            return now + dt.timedelta(weeks=n)
        return now + dt.timedelta(days=n)
    hour = 10
    hm = re.search(r"(?:at|plkst\.?|в)\s*(\d{1,2})(?::(\d{2}))?", t)
    minute = 0
    if hm:
        hour = int(hm.group(1)) % 24
        minute = int(hm.group(2) or 0)
    if re.search(r"day after tomorrow|parit|послезавтра", t):
        d = now + dt.timedelta(days=2)
        return d.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if re.search(r"tomorrow|\brit\b|завтра", t):
        d = now + dt.timedelta(days=1)
        return d.replace(hour=hour if hm else 9, minute=minute, second=0, microsecond=0)
    if re.search(r"tonight|this evening|vakara|vakar[aā] |вечером", t):
        return now.replace(hour=19, minute=0, second=0, microsecond=0) if now.hour < 19 else now + dt.timedelta(hours=1)
    if re.search(r"later|velak|позже", t):
        return now + dt.timedelta(hours=3)
    for name, wd in WEEKDAYS.items():
        if re.search(rf"\b{name}", t):
            days = (wd - now.weekday()) % 7 or 7
            d = now + dt.timedelta(days=days)
            return d.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if hm:
        d = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        return d if d > now else d + dt.timedelta(days=1)
    return None


def parse_reply(text: str, now: dt.datetime | None = None) -> list[dict]:
    raw = text.strip()
    t = fold(raw)
    t = re.sub(r"\s+", " ", t)
    actions: list[dict] = []

    # --- ratings: "7/10", "rate 7", "8 no 10", "vērtējums 6"
    m = re.search(r"(?<![\d.,])(\d{1,2})\s*(?:/|no|of|из)\s*10\b", t) or \
        re.search(r"(?:rate|rating|vertejums|vertejum|оценка)\s*:?\s*(\d{1,2})\b", t)
    if m and 1 <= int(m.group(1)) <= 10:
        actions.append({"type": "rating", "value": int(m.group(1))})

    # --- bought
    m = re.search(rf"(?:bought|purchased|got it|nopirku|nopirkts|nopirku to|купил\w*)(?:\s+(?:it|this|to|šo|so))?(?:\s+(?:for|par|за))?\s*{NUM}", t)
    if m:
        actions.append({"type": "bought", "value": _num(m.group(1))})
    elif re.search(r"\b(?:bought|purchased|nopirku|nopirkts|купил)", t):
        actions.append({"type": "bought", "value": None})

    # --- sold (for ROI outcomes)
    m = re.search(rf"(?:sold|pardevu|pardots|продал\w*)(?:\s+(?:it|this|to))?(?:\s+(?:for|par|за))?\s*{NUM}", t)
    if m:
        actions.append({"type": "sold", "value": _num(m.group(1))})

    # --- would pay
    m = re.search(rf"(?:would|i'?d|i would)\s+(?:buy|pay|take)(?:\s+(?:it|this|that))?\s+(?:for|at)\s*{NUM}", t) or \
        re.search(rf"(?:pirktu|nopirktu|maksatu|nemtu|купил бы)(?:\s+(?:to|so|это))?\s+(?:par|за)\s*{NUM}", t) or \
        re.search(rf"(?:max|maximum|maksimums|ne vairak ka|не больше)\s*{NUM}", t) or \
        re.search(rf"(?:for|par|за)\s*{NUM}\s+(?:i'?d|i would|would)\s+(?:buy|take)", t)
    if m:
        actions.append({"type": "would_pay", "value": _num(m.group(1))})

    # --- market value correction (objective)
    m = re.search(rf"(?:worth|market value(?: is)?|really worth|real price(?: is)?|vertiba|tirgus cena(?: ir)?|vert[sa]|стоит)\s*(?:is|ir|about|ap|около|~)?\s*{NUM}", t)
    if m and not any(a["type"] in ("would_pay", "bought", "sold") for a in actions):
        actions.append({"type": "market_value", "value": _num(m.group(1))})

    # --- reminders
    if re.search(r"remind|atgadin|напомн|check (?:again|later|tomorrow)|parbaud\w* (?:rit|velak)", t):
        when = parse_when(t, now)
        if when:
            actions.append({"type": "remind", "at": when.timestamp(), "label": when.strftime("%a %d %b %H:%M")})
        else:
            return [{"type": "clarify", "question": "When should I remind you? (e.g. 'tomorrow', 'in 3 hours', 'Friday at 18')",
                     "options": ["in 3 hours", "tomorrow", "in 2 days"]}]

    # --- brand dislike / like
    if re.search(r"(?:not interested in|don'?t like|dislike|hate|nepatik|neinteres)\w*\s+(?:this |that |šis |sis |so |šo )?(?:brand|zimol|marka|бренд)", t):
        actions.append({"type": "brand_dislike"})
    elif re.search(r"(?:like|love|patik)\w*\s+(?:this |that |šis |sis )?(?:brand|zimol|marka)", t):
        actions.append({"type": "brand_like"})

    good = re.search(r"(?:actually|really|is|ir|tiesam)?\s*(?:a )?(?:good|great|nice|laba|labs|lielisk\w*|хорош\w*) (?:deal|price|cena|darijum\w*|сделк\w*|цен\w*)", t)
    not_for_me = re.search(r"not for me|ne man|nav priekš manis|nav prieks manis|не для меня|not my thing", t)
    if good:
        actions.append({"type": "good_deal"})
    if not_for_me:
        actions.append({"type": "not_for_me"})

    if re.search(r"too expensive|overpriced|too much|par dargu|parak dargi|dargi|dargs|дорого|завышен", t):
        actions.append({"type": "too_expensive"})
    if re.search(r"\bnot interested\b|\bnav interes\w*|\bneinteres\w*|не интерес", t) and not any(
            a["type"] in ("brand_dislike", "not_for_me") for a in actions):
        actions.append({"type": "not_for_me"})
    elif re.search(r"\binterest(?:ed|ing)\b|\binteres(?:e|ants|anti|ē)\b|интересн", t) and not any(
            a["type"] in ("not_for_me", "brand_dislike") for a in actions):
        actions.append({"type": "interested"})
    if re.search(r"^(?:save|saglabat|saglabā|сохрани)\b|\bsave (?:it|this)\b", t):
        actions.append({"type": "saved"})
    if re.search(r"^(?:ignore|skip|ignoret|izlaist|пропуст)\b", t):
        actions.append({"type": "ignored"})

    if actions:
        # de-duplicate by type, keep order
        seen, out = set(), []
        for a in actions:
            if a["type"] not in seen:
                seen.add(a["type"])
                out.append(a)
        return out

    # bare number -> ambiguous
    m = re.fullmatch(rf"\s*{NUM}\s*", t)
    if m:
        v = _num(m.group(1))
        if v <= 10 and float(v).is_integer():
            return [{"type": "clarify", "question": f"Is {int(v)} a rating (out of 10) or a price (€{v:g})?",
                     "options": [f"{int(v)}/10", f"would pay €{v:g}", f"bought for €{v:g}"]}]
        return [{"type": "clarify", "question": f"What does €{v:g} mean?",
                 "options": [f"would pay €{v:g}", f"bought for €{v:g}", f"worth €{v:g}"]}]
    return [{"type": "clarify",
             "question": "I'm not sure what you mean. You can say e.g. 'too expensive', 'I would buy this for €100', "
                         "'bought for €120', 'remind me tomorrow', '7/10', 'not interested in this brand'.",
             "options": ["interested", "too expensive", "not for me", "remind me tomorrow"]}]
