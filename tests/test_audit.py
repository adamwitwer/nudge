from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from nudge import audit
from nudge.format import as_html

NY = ZoneInfo("America/New_York")
CAL = "family"
POPUP = {"useDefault": False, "overrides": [{"method": "popup", "minutes": 10}]}


def ev(id_, title, start="2026-09-24T15:00:00-04:00", reminders=None, **extra):
    e = {"id": id_, "summary": title, "start": {"dateTime": start} if "T" in start else {"date": start}}
    e["reminders"] = reminders if reminders is not None else {"useDefault": False}
    e.update(extra)
    return e


def find(events, defaults=None, tag="#nonudge"):
    return audit.find_missing([(CAL, e) for e in events], {CAL: defaults or []}, NY, tag)


def test_only_events_without_popups_are_listed():
    f = find([ev("a", "Has popup", reminders=POPUP), ev("b", "Dentist")])
    assert [x.title for x in f] == ["Dentist"]


def test_email_only_is_flagged():
    (f,) = find([ev("a", "Book club", reminders={"useDefault": False, "overrides": [{"method": "email", "minutes": 30}]})])
    assert f.email_only
    assert f.line(NY) == "Thu Sep 24 3:00 PM · Book club (email only)"


def test_calendar_defaults_count():
    events = [ev("a", "Uses default", reminders={"useDefault": True})]
    assert find(events, defaults=[{"method": "popup", "minutes": 30}]) == []
    assert len(find(events, defaults=[])) == 1


def test_recurring_series_listed_once_at_next_occurrence():
    f = find([
        ev("s_2", "Soccer", "2026-10-01T17:00:00-04:00", recurringEventId="s"),
        ev("s_1", "Soccer", "2026-09-24T17:00:00-04:00", recurringEventId="s"),
    ])
    assert len(f) == 1 and f[0].recurring
    assert f[0].line(NY) == "Thu Sep 24 5:00 PM · Soccer (repeats)"


def test_skips_declined_cancelled_and_tagged():
    f = find([
        ev("a", "Declined", attendees=[{"self": True, "responseStatus": "declined"}]),
        ev("b", "Cancelled", status="cancelled"),
        ev("c", "Birthday", "2026-09-25", description="Just FYI #NoNudge"),
        ev("d", "Keep me", "2026-09-25"),
    ])
    assert [(x.title, x.line(NY)) for x in f] == [("Keep me", "Fri Sep 25 · Keep me")]


def test_message_lists_findings():
    f = find([ev("b", "Tom & Jerry"), ev("a", "Dentist", "2026-09-23T09:00:00-04:00")])
    html = as_html(audit.build_message(f, NY))
    assert html == ("🔍 <b>2 events with no popup notification</b>"
                    "\n• Wed Sep 23 9:00 AM · Dentist\n• Thu Sep 24 3:00 PM · Tom &amp; Jerry")
