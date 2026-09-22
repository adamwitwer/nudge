from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from nudge.format import escape_markdown, lead_text, message
from nudge.triggers import Trigger

NY = ZoneInfo("America/New_York")
NOW = datetime(2026, 9, 22, 12, 0, tzinfo=NY)  # Tue noon


def lead(delta=None, all_day_date=None):
    if all_day_date:
        return lead_text(datetime(*all_day_date, tzinfo=NY), True, NOW, NY)
    return lead_text(NOW + delta, False, NOW, NY)


def test_relative_minutes_and_hours():
    assert lead(timedelta(minutes=10)) == "in 10 minutes"
    assert lead(timedelta(minutes=1)) == "in 1 minute"
    assert lead(timedelta(hours=1)) == "in 1 hour"
    assert lead(timedelta(minutes=90)) == "in 1 hour 30 minutes"
    assert lead(timedelta(minutes=9, seconds=40)) == "in 10 minutes"  # a tick late still reads right


def test_clock_times_for_longer_leads():
    assert lead(timedelta(hours=8)) == "today at 8:00 PM"
    assert lead(timedelta(hours=21)) == "tomorrow at 9:00 AM"
    assert lead(timedelta(days=3)) == "Fri Sep 25 at 12:00 PM"


def test_started_already():
    assert lead(timedelta(minutes=-3)) == "now"


def test_all_day():
    assert lead(all_day_date=(2026, 9, 22)) == "today"
    assert lead(all_day_date=(2026, 9, 23)) == "tomorrow"
    assert lead(all_day_date=(2026, 9, 29)) == "on Tue Sep 29"


def test_message_escapes_title_and_marks_late():
    t = Trigger("c", "e", "Pay *rent*_now", NOW + timedelta(hours=1), False, 60, NOW)
    assert message(t, NOW, NY) == "⏰ **Pay \\*rent\\*\\_now** · in 1 hour"
    assert message(t, NOW, NY, late=True).endswith(" _(late)_")
    assert escape_markdown("[Reminder] Trash Night") == "[Reminder] Trash Night"
