"""Message content. MVP: title plus how soon it starts.

`message()` returns a structured Message; each notifier renders it in its own
markup (Discord markdown, Telegram HTML).
"""

from __future__ import annotations

import html
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from .triggers import Trigger

EMOJI = "⏰"

# Built-in keyword -> emoji rules. Config [emoji.keywords] entries are checked
# first and can override these. Matching is case-insensitive at the start of
# a word, so "birthday" matches "Birthdays!" but "call" doesn't match "Recall".
DEFAULT_KEYWORDS = {
    "trash": "🗑️",
    "garbage": "🗑️",
    "recycling": "♻️",
    "birthday": "🎂",
    "anniversary": "💐",
    "dentist": "🦷",
    "doctor": "🩺",
    "vet": "🐾",
    "meds": "💊",
    "pill": "💊",
    "flight": "✈️",
    "haircut": "💇",
    "gym": "🏋️",
    "workout": "🏋️",
    "call": "📞",
    "dinner": "🍽️",
    "lunch": "🍽️",
    "breakfast": "🍽️",
    "pay": "💳",
    "bill": "💳",
}


@dataclass(frozen=True)
class EmojiRules:
    keywords: dict[str, str] = field(default_factory=lambda: dict(DEFAULT_KEYWORDS))
    default: str = EMOJI

    def pick(self, title: str) -> str:
        for keyword, emoji in self.keywords.items():
            if re.search(rf"\b{re.escape(keyword)}", title, re.IGNORECASE):
                return emoji
        return self.default
RELATIVE_UNDER = timedelta(hours=6)  # "in 2 hours" below this, "today at 4:00 PM" above


def _clock(dt: datetime) -> str:
    return dt.strftime("%I:%M %p").lstrip("0")


def _plural(n: int, unit: str) -> str:
    return f"{n} {unit}" + ("" if n == 1 else "s")


def lead_text(start: datetime, all_day: bool, now: datetime, tz: ZoneInfo) -> str:
    """'in 10 minutes', 'in 1 hour 30 minutes', 'tomorrow at 9:00 AM', 'today', ..."""
    local_start = start.astimezone(tz) if not all_day else start
    days = (local_start.date() - now.astimezone(tz).date()).days

    if all_day:
        if days <= 0:
            return "today"
        if days == 1:
            return "tomorrow"
        return local_start.strftime("on %a %b ") + str(local_start.day)

    minutes = round((start - now).total_seconds() / 60)
    if minutes <= 0:
        return "now"
    if timedelta(minutes=minutes) < RELATIVE_UNDER:
        hours, mins = divmod(minutes, 60)
        parts = ([_plural(hours, "hour")] if hours else []) + ([_plural(mins, "minute")] if mins else [])
        return "in " + " ".join(parts)
    if days == 0:
        return f"today at {_clock(local_start)}"
    if days == 1:
        return f"tomorrow at {_clock(local_start)}"
    return local_start.strftime("%a %b ") + f"{local_start.day} at {_clock(local_start)}"


@dataclass(frozen=True)
class Message:
    title: str
    detail: str = ""
    late: bool = False
    emoji: str = EMOJI


_MD_SPECIAL = re.compile(r"([\\*_~`|>])")


def escape_markdown(text: str) -> str:
    return _MD_SPECIAL.sub(r"\\\1", text)


def as_markdown(m: Message) -> str:
    """Discord."""
    text = f"{m.emoji} **{escape_markdown(m.title)}**"
    if m.detail:
        text += f" · {escape_markdown(m.detail)}"
    if m.late:
        text += " _(late)_"
    return text


def as_html(m: Message) -> str:
    """Telegram (parse_mode=HTML)."""
    text = f"{m.emoji} <b>{html.escape(m.title, quote=False)}</b>"
    if m.detail:
        text += f" · {html.escape(m.detail, quote=False)}"
    if m.late:
        text += " <i>(late)</i>"
    return text


def message(
    trigger: Trigger, now: datetime, tz: ZoneInfo, late: bool = False, rules: EmojiRules = EmojiRules()
) -> Message:
    lead = lead_text(trigger.start, trigger.all_day, now, tz)
    return Message(trigger.title, lead, late, emoji=rules.pick(trigger.title))
