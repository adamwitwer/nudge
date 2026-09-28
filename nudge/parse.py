"""Turn a Telegram message into a proposed calendar event.

One Claude call per message, with structured outputs so the reply has to match
`ParsedEvent`. Nothing here touches Google Calendar: the caller shows the
result for confirmation first (nudge.create).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Literal, Optional
from zoneinfo import ZoneInfo

from pydantic import BaseModel

from .config import ClaudeConfig, CreateConfig

log = logging.getLogger("nudge")

MAX_TOKENS = 2000
MAX_MESSAGE_CHARS = 400  # a reminder request, not an essay


class ParseError(RuntimeError):
    """The model couldn't be reached, or answered with something unusable."""


class ParsedEvent(BaseModel):
    """What the model must return."""

    understood: bool
    problem: Optional[str]  # why not, when understood is false
    title: Optional[str]
    date: Optional[str]  # YYYY-MM-DD
    time: Optional[str]  # HH:MM 24-hour; null means all-day
    duration_minutes: Optional[int]
    reminder_minutes: Optional[int]
    calendar: Optional[Literal["family", "personal"]]
    note: Optional[str]  # anything it assumed


SYSTEM = """You turn short messages into calendar events for a home calendar.

Now: {now}. Time zone: {tz}.

Rules:
- date: YYYY-MM-DD. time: HH:MM 24-hour, or null for an all-day event.
- Resolve relative dates against "now". A bare weekday means the next one of
  those, never one in the past. "tonight" is today.
- duration_minutes: only when stated or implied by a range; otherwise null.
- reminder_minutes: minutes before the start, only when the message asks for a
  reminder lead time; otherwise null.
- calendar: "family" unless the message says it is personal, private, or just
  for the sender.
- title: the event itself, sentence case, without the date, time or reminder
  words. Keep the sender's own wording where you can.
- If there is no clear event, or no date can be worked out, set
  understood=false and say why in problem.
- note: anything you assumed or dropped, in a few words; otherwise null."""


@dataclass(frozen=True)
class Proposal:
    """A parsed event, resolved into real datetimes."""

    title: str
    start: datetime  # aware; local midnight for all-day
    end: datetime
    all_day: bool
    calendar_id: str
    reminder_minutes: int
    note: str | None = None


def client(cfg: ClaudeConfig):
    import anthropic  # imported lazily: the service runs without it configured

    headers = {"anthropic-workspace-id": cfg.workspace_id} if cfg.workspace_id else None
    return anthropic.Anthropic(api_key=cfg.api_key, default_headers=headers)


def ask(cfg: ClaudeConfig, text: str, now: datetime, tz: ZoneInfo, api=None) -> ParsedEvent:
    """One model call. Raises ParseError if the API can't be used."""
    import anthropic

    api = api or client(cfg)
    system = SYSTEM.format(now=now.astimezone(tz).strftime("%A %Y-%m-%d %H:%M"), tz=tz.key)
    try:
        response = api.messages.parse(
            model=cfg.model,
            max_tokens=MAX_TOKENS,
            system=system,
            messages=[{"role": "user", "content": text[:MAX_MESSAGE_CHARS]}],
            output_format=ParsedEvent,
        )
    except anthropic.APIError as e:
        raise ParseError(str(e)) from None
    if response.parsed_output is None:
        raise ParseError("no structured output in the reply")
    log.info("parsed %r (in=%d out=%d)", text[:40], response.usage.input_tokens, response.usage.output_tokens)
    return response.parsed_output


def to_proposal(parsed: ParsedEvent, create: CreateConfig, tz: ZoneInfo) -> Proposal:
    """Resolve a ParsedEvent into datetimes and a calendar id.

    Raises ParseError when the model's fields don't make a usable event.
    """
    if not parsed.understood or not parsed.title or not parsed.date:
        raise ParseError(parsed.problem or "I couldn't find an event in that")
    try:
        day = date.fromisoformat(parsed.date)
        clock = time.fromisoformat(parsed.time) if parsed.time else None
    except ValueError:
        raise ParseError(f"bad date or time from the model: {parsed.date} {parsed.time}") from None

    all_day = clock is None
    start = datetime.combine(day, clock or time(), tzinfo=tz)
    minutes = parsed.duration_minutes or int(create.duration.total_seconds() // 60)
    end = start + (timedelta(days=1) if all_day else timedelta(minutes=minutes))

    calendar_id = create.alt_calendar if parsed.calendar == "personal" else create.default_calendar
    if not calendar_id:
        raise ParseError("no calendar configured for new events")

    reminder = parsed.reminder_minutes
    if reminder is None:
        reminder = create.reminder_minutes
    return Proposal(
        title=parsed.title,
        start=start,
        end=end,
        all_day=all_day,
        calendar_id=calendar_id,
        reminder_minutes=max(0, min(reminder, 40320)),  # GCal's 4-week ceiling
        note=parsed.note,
    )
