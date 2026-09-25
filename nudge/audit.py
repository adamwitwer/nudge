"""Upcoming events with no popup notification.

Part of the morning brief (see morning.py); `nudge audit` also runs it alone.

nudge can only send reminders for events that have a popup notification, and
the GCal UI makes it easy to forget one. This lists the next N days' events that
would never fire.

- Recurring events are listed once (their next occurrence), marked "repeats".
- Events with only email notifications are marked "email only".
- Declined and cancelled events are skipped, as are events whose description
  contains the opt-out tag (default #nonudge).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from . import format, gcal
from .triggers import event_start, is_declined, popup_minutes

log = logging.getLogger("nudge")

@dataclass(frozen=True)
class Finding:
    title: str
    start: datetime
    all_day: bool
    recurring: bool
    email_only: bool

    def line(self, tz: ZoneInfo) -> str:
        if self.all_day:
            when = self.start.strftime("%a %b ") + str(self.start.day)
        else:
            local = self.start.astimezone(tz)
            when = local.strftime("%a %b ") + f"{local.day} {format.clock(local)}"
        notes = [n for n, on in (("repeats", self.recurring), ("email only", self.email_only)) if on]
        return f"{when} · {self.title}" + (f" ({', '.join(notes)})" if notes else "")


def find_missing(events: list[tuple[str, dict]], defaults: dict[str, list[dict]], tz: ZoneInfo, tag: str) -> list[Finding]:
    """events: (calendar_id, event) pairs, expanded (singleEvents=True)."""
    by_series: dict[str, Finding] = {}
    for cal_id, ev in events:
        if ev.get("status") == "cancelled" or is_declined(ev):
            continue
        if tag and tag.lower() in (ev.get("description") or "").lower():
            continue
        cal_defaults = defaults.get(cal_id, [])
        if popup_minutes(ev, cal_defaults):
            continue
        reminders = ev.get("reminders", {})
        effective = cal_defaults if reminders.get("useDefault") else reminders.get("overrides", [])
        start, all_day = event_start(ev, tz)
        series = f"{cal_id}:{ev.get('recurringEventId') or ev['id']}"
        finding = Finding(
            title=ev.get("summary", "(no title)"),
            start=start,
            all_day=all_day,
            recurring="recurringEventId" in ev,
            email_only=any(r.get("method") == "email" for r in effective),
        )
        if series not in by_series or start < by_series[series].start:
            by_series[series] = finding
    return sorted(by_series.values(), key=lambda f: f.start)


def build_message(findings: list[Finding], tz: ZoneInfo) -> format.Message:
    n = len(findings)
    return format.Message(
        f"{n} event{'s' if n != 1 else ''} with no popup notification",
        emoji="🔍",
        sections=((None, tuple(f.line(tz) for f in findings)),),
    )


def collect(svc, calendar_ids: list[str], tz: ZoneInfo, now: datetime, days: int) -> tuple[list, dict]:
    events, defaults = [], {}
    for cal_id in calendar_ids:
        defaults[cal_id] = gcal.get_calendar(svc, cal_id).get("defaultReminders", [])
        events += [(cal_id, ev) for ev in gcal.list_events(svc, cal_id, now, now + timedelta(days=days))]
    return events, defaults
