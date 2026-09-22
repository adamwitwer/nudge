"""Message text. MVP: title plus how soon it starts."""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from .triggers import Trigger

EMOJI = "⏰"
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


_MD_SPECIAL = re.compile(r"([\\*_~`|>])")


def escape_markdown(text: str) -> str:
    return _MD_SPECIAL.sub(r"\\\1", text)


def message(trigger: Trigger, now: datetime, tz: ZoneInfo, late: bool = False) -> str:
    text = f"{EMOJI} **{escape_markdown(trigger.title)}** · {lead_text(trigger.start, trigger.all_day, now, tz)}"
    if late:
        text += " _(late)_"
    return text
