from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from nudge.format import Message, as_html, as_markdown, escape_markdown, lead_text, message
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
    assert lead(timedelta(seconds=20)) == "now"
    assert lead(timedelta(minutes=-3)) == "started 3 minutes ago"
    assert lead(timedelta(minutes=-70)) == "started 1 hour 10 minutes ago"
    assert lead(timedelta(hours=-7)) == "started at 5:00 AM"


def test_all_day():
    assert lead(all_day_date=(2026, 9, 22)) == "today"
    assert lead(all_day_date=(2026, 9, 23)) == "tomorrow"
    assert lead(all_day_date=(2026, 9, 29)) == "on Tue Sep 29"


def test_message_is_structured():
    t = Trigger("c", "e", "Dentist", NOW + timedelta(hours=1), False, 60, NOW)
    assert message(t, NOW, NY) == Message("Dentist", "in 1 hour", emoji="🦷")
    assert message(t, NOW, NY, late=True).late


def test_markdown_rendering_escapes_title_and_marks_late():
    assert as_markdown(Message("Pay *rent*_now", "in 1 hour")) == "⏰ **Pay \\*rent\\*\\_now** · in 1 hour"
    assert as_markdown(Message("x", "in 5 minutes", late=True)).endswith(" _(late)_")
    assert escape_markdown("[Reminder] Trash Night") == "[Reminder] Trash Night"


def test_html_rendering_escapes_title_and_marks_late():
    assert as_html(Message("Tom & Jerry <3", "tomorrow")) == "⏰ <b>Tom &amp; Jerry &lt;3</b> · tomorrow"
    assert as_html(Message("x", "now", late=True)) == "⏰ <b>x</b> · now <i>(late)</i>"
    assert as_html(Message("alert", emoji="⚠️")) == "⚠️ <b>alert</b>"


def test_emoji_rules_match_word_starts_case_insensitively():
    from nudge.format import EmojiRules

    r = EmojiRules()
    assert r.pick("[Reminder] Trash Night") == "🗑️"
    assert r.pick("Mom's BIRTHDAY") == "🎂"
    assert r.pick("Birthdays at school") == "🎂"
    assert r.pick("Recall notice") == "⏰"  # "call" must start a word
    assert r.pick("✨ nudge test ✨") == "⏰"


def test_message_uses_emoji_rules():
    from nudge.format import EmojiRules

    t = Trigger("c", "e", "Dentist", NOW + timedelta(hours=1), False, 60, NOW)
    assert message(t, NOW, NY).emoji == "🦷"
    assert message(t, NOW, NY, rules=EmojiRules({}, "🔔")).emoji == "🔔"
