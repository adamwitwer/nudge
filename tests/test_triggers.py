from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from nudge.triggers import triggers_for_event

NY = ZoneInfo("America/New_York")
CAL = "family@group.calendar.google.com"
DEFAULTS = [{"method": "popup", "minutes": 30}, {"method": "email", "minutes": 60}]


def timed(start="2026-09-22T16:00:00-04:00", reminders=None, **extra):
    ev = {"id": "e1", "summary": "Dentist", "start": {"dateTime": start}}
    ev["reminders"] = reminders if reminders is not None else {"useDefault": True}
    ev.update(extra)
    return ev


def all_day(day="2026-09-22", overrides=()):
    return {
        "id": "e2",
        "summary": "Birthday",
        "start": {"date": day},
        "reminders": {"useDefault": False, "overrides": list(overrides)},
    }


def utc(*args):
    return datetime(*args, tzinfo=timezone.utc)


def test_overrides_popup_only():
    ev = timed(reminders={"useDefault": False, "overrides": [
        {"method": "popup", "minutes": 10},
        {"method": "email", "minutes": 30},
        {"method": "popup", "minutes": 60},
    ]})
    ts = triggers_for_event(ev, CAL, DEFAULTS, NY)
    assert [t.minutes_before for t in ts] == [10, 60]
    assert ts[0].fire_at == utc(2026, 9, 22, 19, 50)
    assert ts[1].fire_at == utc(2026, 9, 22, 19, 0)


def test_use_default_uses_calendar_defaults():
    ts = triggers_for_event(timed(), CAL, DEFAULTS, NY)
    assert [t.minutes_before for t in ts] == [30]
    assert ts[0].fire_at == utc(2026, 9, 22, 19, 30)


def test_no_overrides_means_no_triggers():
    ev = timed(reminders={"useDefault": False})
    assert triggers_for_event(ev, CAL, DEFAULTS, NY) == []


def test_duplicate_minutes_collapse():
    ev = timed(reminders={"useDefault": False, "overrides": [
        {"method": "popup", "minutes": 10}, {"method": "popup", "minutes": 10},
    ]})
    assert len(triggers_for_event(ev, CAL, DEFAULTS, NY)) == 1


def test_declined_and_cancelled_skipped():
    declined = timed(attendees=[{"email": "me@x", "self": True, "responseStatus": "declined"}])
    accepted = timed(attendees=[{"email": "me@x", "self": True, "responseStatus": "accepted"}])
    assert triggers_for_event(declined, CAL, DEFAULTS, NY) == []
    assert triggers_for_event(timed(status="cancelled"), CAL, DEFAULTS, NY) == []
    assert len(triggers_for_event(accepted, CAL, DEFAULTS, NY)) == 1


def test_all_day_counts_back_from_local_midnight():
    # 420 min before midnight = 5 PM the day before, in the calendar's tz.
    ts = triggers_for_event(all_day(overrides=[{"method": "popup", "minutes": 420}]), CAL, [], NY)
    assert ts[0].all_day
    assert ts[0].fire_at.astimezone(NY) == datetime(2026, 9, 21, 17, 0, tzinfo=NY)


def test_all_day_across_dst_uses_wall_clock():
    # DST ends Nov 1 2026 in New York. "Day before at 9 AM" = 900 minutes.
    ts = triggers_for_event(all_day("2026-11-02", [{"method": "popup", "minutes": 900}]), CAL, [], NY)
    local = ts[0].fire_at.astimezone(NY)
    assert (local.day, local.hour, local.minute) == (1, 9, 0)
    assert ts[0].fire_at == utc(2026, 11, 1, 14, 0)  # 9 AM EST = 14:00 UTC


def test_key_changes_when_event_moves():
    a = triggers_for_event(timed(), CAL, DEFAULTS, NY)[0]
    b = triggers_for_event(timed(start="2026-09-22T17:00:00-04:00"), CAL, DEFAULTS, NY)[0]
    assert a.key != b.key
    assert a.key == triggers_for_event(timed(), CAL, DEFAULTS, NY)[0].key
