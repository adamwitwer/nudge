"""Today's events, for the morning brief.

All-day events first, then timed ones in order. Declined and cancelled
events are skipped, as are events tagged with the opt-out tag.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from . import format, gcal
from .triggers import event_start, is_declined


@dataclass(frozen=True)
class Item:
    title: str
    start: datetime
    all_day: bool

    def line(self, tz: ZoneInfo, rules: format.EmojiRules) -> str:
        when = "all day" if self.all_day else format.clock(self.start.astimezone(tz))
        return f"{when} · {rules.pick(self.title)} {self.title}"


def day_bounds(now: datetime, tz: ZoneInfo) -> tuple[datetime, datetime]:
    """Local midnight today and tomorrow, as aware datetimes."""
    today = now.astimezone(tz).date()
    start = datetime.combine(today, time(), tzinfo=tz)
    return start, start + timedelta(days=1)


def today(svc, calendar_ids: list[str], tz: ZoneInfo, now: datetime, tag: str = "") -> list[Item]:
    start, end = day_bounds(now, tz)
    items = []
    for cal_id in calendar_ids:
        for ev in gcal.list_events(svc, cal_id, start, end):
            if ev.get("status") == "cancelled" or is_declined(ev):
                continue
            if tag and tag.lower() in (ev.get("description") or "").lower():
                continue
            ev_start, all_day = event_start(ev, tz)
            if all_day and date.fromisoformat(ev["start"]["date"]) != start.date():
                continue  # a multi-day event's later days
            items.append(Item(ev.get("summary", "(no title)"), ev_start, all_day))
    # All-day first, then by start time.
    return sorted(items, key=lambda i: (not i.all_day, i.start))
