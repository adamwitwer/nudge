"""Creating events from Telegram: preview, confirm, write, undo.

A parsed message becomes a Proposal, which is shown with buttons and stored.
Nothing reaches Google Calendar until ✅ Create is tapped. Every created event
gets a popup reminder, so nudge will fire for what it just made.
"""

from __future__ import annotations

import logging
from dataclasses import asdict, replace
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from . import format, gcal, parse
from .config import CreateConfig
from .parse import ParseError, Proposal
from .runtime import Runtime
from .store import Store

log = logging.getLogger("nudge")

ACTIONS = ("create", "cancel", "swapcal", "undo")
DESCRIPTION = "Created by nudge from Telegram."


# --- proposal <-> stored payload


def _payload(p: Proposal) -> dict:
    d = asdict(p)
    d["start"] = p.start.isoformat()
    d["end"] = p.end.isoformat()
    return d


def _proposal(payload: dict) -> Proposal:
    return Proposal(
        **{**payload,
           "start": datetime.fromisoformat(payload["start"]),
           "end": datetime.fromisoformat(payload["end"])}
    )


# --- messages


def _when(p: Proposal, tz: ZoneInfo) -> str:
    start = p.start.astimezone(tz)
    day = start.strftime("%a %b ") + str(start.day)
    if p.all_day:
        return f"{day} · all day"
    end = p.end.astimezone(tz)
    return f"{day} · {format.clock(start)}–{format.clock(end)}"


def _calendar_name(rt: Runtime, calendar_id: str) -> str:
    return "Personal" if calendar_id == rt.cfg.create.alt_calendar else "Family"


def preview(rt: Runtime, p: Proposal, ref: int) -> format.Message:
    lines = [f"📅 {_calendar_name(rt, p.calendar_id)} · 🔔 popup {p.reminder_minutes} min"]
    if p.note:
        lines.append(f"ℹ️ {p.note}")
    return format.Message(
        p.title,
        _when(p, rt.tz),
        emoji=rt.cfg.emoji.pick(p.title),
        ref=ref,
        sections=((None, tuple(lines)),),
    )


def preview_keyboard(ref: int, other_calendar: str) -> dict:
    return {
        "inline_keyboard": [[
            {"text": "✅ Create", "callback_data": f"create:{ref}"},
            {"text": f"📅 {other_calendar}", "callback_data": f"swapcal:{ref}"},
            {"text": "✖️ Cancel", "callback_data": f"cancel:{ref}"},
        ]]
    }


def undo_keyboard(ref: int) -> dict:
    return {"inline_keyboard": [[{"text": "↩️ Undo", "callback_data": f"undo:{ref}"}]]}


def propose(bot, rt: Runtime, text: str, now: datetime) -> None:
    """Parse a message and send its preview. Raises ParseError if unusable."""
    parsed = parse.ask(rt.cfg.claude, text, now, rt.tz)
    proposal = parse.to_proposal(parsed, rt.cfg.create, rt.tz)
    ref = rt.store.add_proposal(_payload(proposal), now)
    other = "Personal" if _calendar_name(rt, proposal.calendar_id) == "Family" else "Family"
    bot.send(preview(rt, proposal, ref), reply_markup=preview_keyboard(ref, other))


# --- Google Calendar


def event_body(p: Proposal, tz: ZoneInfo) -> dict:
    if p.all_day:
        when = {"start": {"date": p.start.date().isoformat()}, "end": {"date": p.end.date().isoformat()}}
    else:
        when = {
            "start": {"dateTime": p.start.isoformat(), "timeZone": tz.key},
            "end": {"dateTime": p.end.isoformat(), "timeZone": tz.key},
        }
    return {
        "summary": p.title,
        "description": DESCRIPTION,
        "reminders": {"useDefault": False, "overrides": [{"method": "popup", "minutes": p.reminder_minutes}]},
        **when,
    }


def insert(svc, p: Proposal, tz: ZoneInfo) -> dict:
    return svc.events().insert(calendarId=p.calendar_id, body=event_body(p, tz)).execute()


def delete(svc, calendar_id: str, event_id: str) -> None:
    svc.events().delete(calendarId=calendar_id, eventId=event_id).execute()


# --- button taps


def handle(bot, rt: Runtime, action: str, ref: int, message_id: int, now: datetime) -> tuple[str, dict | None, dict | None]:
    """Act on a preview button.

    Returns (toast, message to re-render or None, keyboard or None).
    """
    stored = rt.store.get_proposal(ref)
    if stored is None:
        return "That one has expired", None, None
    payload, created_calendar, created_event = stored
    p = _proposal(payload)

    if action == "cancel":
        rt.store.drop_proposal(ref)  # a stale Create button can't revive it
        return "Cancelled", format.Message(p.title, _when(p, rt.tz), emoji="✖️"), None

    if action == "swapcal":
        cfg: CreateConfig = rt.cfg.create
        other = cfg.alt_calendar if p.calendar_id == cfg.default_calendar else cfg.default_calendar
        if not other:
            return "No other calendar configured", None, None
        p = replace(p, calendar_id=other)
        rt.store.update_proposal(ref, _payload(p))
        name = "Personal" if _calendar_name(rt, p.calendar_id) == "Family" else "Family"
        return f"→ {_calendar_name(rt, p.calendar_id)}", preview(rt, p, ref), preview_keyboard(ref, name)

    if action == "create":
        if created_event:
            return "Already created", None, None
        event = insert(rt.svc, p, rt.tz)
        rt.store.mark_created(ref, p.calendar_id, event["id"])
        log.info("created %r on %s (%s)", p.title, _calendar_name(rt, p.calendar_id), event["id"])
        msg = preview(rt, p, ref)
        return "Created", replace(msg, detail=f"{msg.detail} · added"), undo_keyboard(ref)

    if action == "undo":
        if not created_event:
            return "Nothing to undo", None, None
        delete(rt.svc, created_calendar, created_event)
        rt.store.mark_created(ref, None, None)
        log.info("undid %r", p.title)
        return "Deleted", format.Message(p.title, "deleted", emoji="↩️"), None

    return "I don't know that button", None, None
