"""Telegram messages you type at the bot.

Commands are answered here; anything else will become an event-creation
request once nudge.parse lands. Only the configured chat is listened to.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from . import agenda, create, format, gcal
from .parse import ParseError
from .runtime import Runtime

log = logging.getLogger("nudge")

NEXT_DAYS = 7
NEXT_COUNT = 3

HELP = (
    "Type an event (\"dentist thursday 3pm\") and I'll offer to add it\n"
    "/next — the next few events\n"
    "/today — today's agenda\n"
    "/help — this message"
)


def dispatch(bot, rt: Runtime, message: dict) -> None:
    """Answer one incoming Telegram message."""
    chat = message.get("chat", {})
    if str(chat.get("id")) != str(bot.chat_id):
        log.warning("ignored message from chat_id=%s", chat.get("id"))
        return

    text = (message.get("text") or "").strip()
    if not text:
        return
    word = text.split()[0].lower()
    command = word[1:].split("@")[0] if word.startswith("/") else ""

    if command in ("next", "upcoming"):
        bot.send(next_message(rt))
    elif command in ("today", "agenda"):
        bot.send(today_message(rt))
    elif command in ("help", "start"):
        bot.send(format.Message("nudge", emoji="👋", sections=((None, tuple(HELP.split("\n"))),)))
    elif command:
        bot.send(format.Message(f"No such command: /{command}", emoji="🤔",
                                sections=((None, tuple(HELP.split("\n"))),)))
    else:
        _propose(bot, rt, text)


def _propose(bot, rt: Runtime, text: str) -> None:
    """Plain text: try to turn it into a calendar event."""
    if not (rt.cfg.create.enabled and rt.cfg.claude.enabled):
        bot.send(format.Message("Event creation isn't set up", emoji="🤔",
                                sections=((None, tuple(HELP.split("\n"))),)))
        return
    try:
        create.propose(bot, rt, text, datetime.now(timezone.utc))
    except ParseError as e:
        bot.send(format.Message("I couldn't make an event from that", str(e), emoji="🤔"))
    except Exception as e:
        log.warning("propose failed: %s", e)
        bot.send(format.Message("Something went wrong reading that", type(e).__name__, emoji="⚠️"))


def upcoming(rt: Runtime, now: datetime, days: int = NEXT_DAYS, limit: int = NEXT_COUNT) -> list[agenda.Item]:
    """The next few events across the watched calendars."""
    items = []
    for cal_id in rt.cfg.calendars:
        for ev in gcal.list_events(rt.svc, cal_id, now, now + timedelta(days=days)):
            if ev.get("status") == "cancelled":
                continue
            start, all_day = agenda.event_start(ev, rt.tz)
            if not all_day and start < now:
                continue  # already started
            items.append(agenda.Item(ev.get("summary", "(no title)"), start, all_day))
    return sorted(items, key=lambda i: i.start)[:limit]


def _when(item: agenda.Item, now: datetime, tz: ZoneInfo) -> str:
    local = item.start.astimezone(tz)
    days = (local.date() - now.astimezone(tz).date()).days
    day = "today" if days == 0 else "tomorrow" if days == 1 else local.strftime("%a %b ") + str(local.day)
    return day if item.all_day else f"{day} {format.clock(local)}"


def next_message(rt: Runtime, now: datetime | None = None) -> format.Message:
    now = now or datetime.now(timezone.utc)
    items = upcoming(rt, now)
    if not items:
        return format.Message(f"Nothing in the next {NEXT_DAYS} days", emoji="🌤️")
    return format.Message(
        "Next up",
        emoji="⏭️",
        sections=((None, tuple(
            f"{_when(i, now, rt.tz)} · {rt.cfg.emoji.pick(i.title)} {i.title}" for i in items
        )),),
    )


def today_message(rt: Runtime, now: datetime | None = None) -> format.Message:
    now = now or datetime.now(timezone.utc)
    items = agenda.today(rt.svc, rt.cfg.calendars, rt.tz, now, rt.cfg.morning.tag)
    if not items:
        return format.Message("Nothing on the calendar today", emoji="🌤️")
    return format.Message(
        "Today",
        emoji="📅",
        sections=((None, tuple(i.line(rt.tz, rt.cfg.emoji) for i in items)),),
    )
