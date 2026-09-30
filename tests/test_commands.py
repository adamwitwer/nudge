from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

from nudge import commands
from nudge.config import Config
from nudge.format import as_html
from nudge.runtime import Runtime
from nudge.store import Store

NY = ZoneInfo("America/New_York")
NOW = datetime(2026, 9, 28, 16, 0, tzinfo=timezone.utc)  # Mon noon ET
CHAT = 42


class FakeBot:
    chat_id = CHAT

    def __init__(self):
        self.sent = []
        self.typed = 0

    def typing(self):
        self.typed += 1

    def send(self, message):
        self.sent.append(as_html(message))


def ev(title, start, cal="fam", **extra):
    e = {"id": title, "summary": title, "start": {"dateTime": start} if "T" in start else {"date": start}}
    e.update(extra)
    return e


@pytest.fixture
def rt(monkeypatch):
    events = {
        "fam": [
            ev("Recycling", "2026-09-29T20:00:00-04:00"),
            ev("Garbage", "2026-10-01T20:00:00-04:00"),
            ev("Dentist", "2026-09-28T09:00:00-04:00"),  # already started
        ],
        "per": [ev("Mom's birthday", "2026-09-30")],
    }
    def list_events(svc, cal, time_min, time_max):
        """Like the real call: only events that overlap the window."""
        out = []
        for e in events[cal]:
            start = e["start"]
            when = (datetime.fromisoformat(start["dateTime"]) if "dateTime" in start
                    else datetime.fromisoformat(start["date"]).replace(tzinfo=NY))
            if time_min <= when < time_max:
                out.append(e)
        return out

    monkeypatch.setattr(commands.gcal, "list_events", list_events)
    monkeypatch.setattr(commands.agenda.gcal, "list_events", list_events)
    cfg = Config(calendars=["fam", "per"], poll=timedelta(minutes=5), grace=timedelta(minutes=15), discord_webhook_url=None)
    return Runtime(cfg=cfg, store=Store(":memory:"), tz=NY, svc=object())


def message(text, chat=CHAT):
    return {"text": text, "chat": {"id": chat}}


def test_next_lists_upcoming_and_skips_started(rt):
    # A fixed `now`: the fixture's events are dated, so a real clock would
    # age this test out (it did, 2026-09-30).
    out = as_html(commands.next_message(rt, NOW))
    assert "Dentist" not in out  # already started
    assert "Recycling" in out and "Garbage" in out


def test_next_command_routes_to_next_message(rt, monkeypatch):
    monkeypatch.setattr(commands, "next_message", lambda rt, now=None: commands.format.Message("stub"))
    bot = FakeBot()
    commands.dispatch(bot, rt, message("/next"))
    assert "stub" in bot.sent[0]


def test_next_wording_is_relative(rt):
    msg = commands.next_message(rt, NOW)
    (_, lines), = msg.sections
    assert lines[0] == "tomorrow 8:00 PM · ♻️ Recycling"
    assert lines[1] == "Wed Sep 30 · 🎂 Mom's birthday"  # all-day, no time


def test_today_lists_todays_events(rt):
    msg = commands.today_message(rt, NOW)
    assert msg.title == "Today"
    assert msg.sections == ((None, ("9:00 AM · 🦷 Dentist",)),)


def test_empty_day_says_so(rt, monkeypatch):
    monkeypatch.setattr(commands.agenda, "today", lambda *a, **k: [])
    assert "Nothing on the calendar" in commands.today_message(rt, NOW).title


def test_help_and_unknown_command(rt):
    bot = FakeBot()
    commands.dispatch(bot, rt, message("/help"))
    commands.dispatch(bot, rt, message("/frobnicate"))
    assert "/next" in bot.sent[0]
    assert "No such command" in bot.sent[1]


def test_plain_text_without_a_key_says_so(rt):
    bot = FakeBot()
    commands.dispatch(bot, rt, message("dentist thursday 3pm"))
    assert "isn't set up" in bot.sent[0]


def test_plain_text_is_proposed(rt, monkeypatch):
    from dataclasses import replace as dc_replace
    from nudge.config import ClaudeConfig

    rt.cfg = dc_replace(rt.cfg, claude=ClaudeConfig(api_key="sk-ant-test"))
    seen = []
    monkeypatch.setattr(commands.create, "propose", lambda bot, rt, text, now: seen.append(text))
    bot = FakeBot()
    commands.dispatch(bot, rt, message("dentist thursday 3pm"))
    assert seen == ["dentist thursday 3pm"] and bot.typed == 1


def test_parse_failure_is_reported(rt, monkeypatch):
    from dataclasses import replace as dc_replace
    from nudge.config import ClaudeConfig
    from nudge.parse import ParseError

    rt.cfg = dc_replace(rt.cfg, claude=ClaudeConfig(api_key="sk-ant-test"))

    def boom(*a, **k):
        raise ParseError("no date in there")

    monkeypatch.setattr(commands.create, "propose", boom)
    bot = FakeBot()
    commands.dispatch(bot, rt, message("hello"))
    assert "couldn't make an event" in bot.sent[0] and "no date in there" in bot.sent[0]


def test_other_chats_are_ignored(rt):
    bot = FakeBot()
    commands.dispatch(bot, rt, message("/today", chat=999))
    assert bot.sent == []


def test_command_with_bot_suffix(rt):
    bot = FakeBot()
    commands.dispatch(bot, rt, message("/today@adam_nudge_bot"))
    assert bot.sent and "Today" in bot.sent[0]
