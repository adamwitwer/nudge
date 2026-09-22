"""Turn Google Calendar events into reminder triggers.

Pure functions only (no API calls), so this is where the tricky rules live
and get tested:

- `reminders.useDefault` means the calendar's default reminders apply; they
  are not on the event itself.
- Only `popup` reminders count (email reminders are ignored by design).
- All-day events: `minutes` counts back from midnight at the start of the
  event date, in the calendar's time zone (wall-clock), e.g. 420 = 5 PM the
  day before.
- Events the user has declined never fire.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo


@dataclass(frozen=True)
class Trigger:
    calendar_id: str
    event_id: str
    title: str
    start: datetime  # aware; midnight in the calendar tz for all-day events
    all_day: bool
    minutes_before: int
    fire_at: datetime  # aware, UTC

    @property
    def key(self) -> str:
        """Dedupe key. Moving an event changes `start`, so it re-fires."""
        return f"{self.calendar_id}:{self.event_id}:{self.start.isoformat()}:{self.minutes_before}"


def event_start(event: dict, tz: ZoneInfo) -> tuple[datetime, bool]:
    """Return (aware start datetime, is_all_day)."""
    start = event["start"]
    if "dateTime" in start:
        return datetime.fromisoformat(start["dateTime"]), False
    day = date.fromisoformat(start["date"])
    return datetime.combine(day, time(), tzinfo=tz), True


def popup_minutes(event: dict, default_reminders: list[dict]) -> list[int]:
    """Minutes-before for each effective popup reminder, sorted, deduped."""
    reminders = event.get("reminders", {})
    items = default_reminders if reminders.get("useDefault") else reminders.get("overrides", [])
    return sorted({item["minutes"] for item in items if item.get("method") == "popup"})


def is_declined(event: dict) -> bool:
    return any(
        a.get("self") and a.get("responseStatus") == "declined"
        for a in event.get("attendees", [])
    )


def triggers_for_event(
    event: dict, calendar_id: str, default_reminders: list[dict], tz: ZoneInfo
) -> list[Trigger]:
    if event.get("status") == "cancelled" or is_declined(event):
        return []
    start, all_day = event_start(event, tz)
    triggers = []
    for minutes in popup_minutes(event, default_reminders):
        if all_day:
            # Wall-clock arithmetic in the calendar tz, then pin the real offset.
            local = (start.replace(tzinfo=None) - timedelta(minutes=minutes)).replace(tzinfo=tz)
            fire_at = local.astimezone(timezone.utc)
        else:
            fire_at = (start - timedelta(minutes=minutes)).astimezone(timezone.utc)
        triggers.append(
            Trigger(
                calendar_id=calendar_id,
                event_id=event["id"],
                title=event.get("summary", "(no title)"),
                start=start,
                all_day=all_day,
                minutes_before=minutes,
                fire_at=fire_at,
            )
        )
    return triggers
