from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

from nudge import create, parse
from nudge.config import ClaudeConfig, Config, CreateConfig
from nudge.format import as_html
from nudge.parse import ParsedEvent, ParseError, Proposal
from nudge.runtime import Runtime
from nudge.store import Store

NY = ZoneInfo("America/New_York")
NOW = datetime(2026, 9, 28, 16, 0, tzinfo=timezone.utc)  # Mon noon ET
FAMILY, PERSONAL = "fam@group.calendar.google.com", "me@gmail.com"
CREATE = CreateConfig(default_calendar=FAMILY, alt_calendar=PERSONAL, duration=timedelta(minutes=30), reminder_minutes=10)


def parsed(**kw):
    base = dict(understood=True, problem=None, title="Dentist", date="2026-10-01", time="15:00",
                duration_minutes=None, reminder_minutes=None, calendar="family", note=None)
    return ParsedEvent(**{**base, **kw})


# --- turning a model answer into a proposal


def test_timed_event_gets_default_duration_and_reminder():
    p = parse.to_proposal(parsed(), CREATE, NY)
    assert p.start == datetime(2026, 10, 1, 15, 0, tzinfo=NY)
    assert p.end == datetime(2026, 10, 1, 15, 30, tzinfo=NY)
    assert not p.all_day and p.calendar_id == FAMILY and p.reminder_minutes == 10


def test_stated_duration_reminder_and_personal_calendar():
    p = parse.to_proposal(parsed(duration_minutes=120, reminder_minutes=60, calendar="personal"), CREATE, NY)
    assert p.end - p.start == timedelta(hours=2)
    assert p.reminder_minutes == 60 and p.calendar_id == PERSONAL


def test_all_day_event():
    p = parse.to_proposal(parsed(time=None), CREATE, NY)
    assert p.all_day
    assert p.start == datetime(2026, 10, 1, tzinfo=NY)
    assert p.end == datetime(2026, 10, 2, tzinfo=NY)  # GCal's end date is exclusive


def test_not_understood_raises_with_the_reason():
    with pytest.raises(ParseError, match="no date"):
        parse.to_proposal(parsed(understood=False, problem="no date in there"), CREATE, NY)


def test_garbage_dates_raise():
    with pytest.raises(ParseError, match="bad date"):
        parse.to_proposal(parsed(date="next thursday"), CREATE, NY)


def test_reminder_is_clamped_to_gcal_maximum():
    p = parse.to_proposal(parsed(reminder_minutes=999999), CREATE, NY)
    assert p.reminder_minutes == 40320  # 4 weeks


# --- the event body sent to Google


def test_timed_body():
    p = parse.to_proposal(parsed(), CREATE, NY)
    body = create.event_body(p, NY)
    assert body["summary"] == "Dentist"
    assert body["start"] == {"dateTime": "2026-10-01T15:00:00-04:00", "timeZone": "America/New_York"}
    assert body["reminders"] == {"useDefault": False, "overrides": [{"method": "popup", "minutes": 10}]}


def test_all_day_body_uses_dates():
    body = create.event_body(parse.to_proposal(parsed(time=None), CREATE, NY), NY)
    assert body["start"] == {"date": "2026-10-01"} and body["end"] == {"date": "2026-10-02"}


# --- the confirm / create / undo flow


class FakeEvents:
    def __init__(self):
        self.inserted, self.deleted = [], []

    def insert(self, calendarId, body):
        self.inserted.append((calendarId, body))
        return _Exec({"id": "ev123"})

    def delete(self, calendarId, eventId):
        self.deleted.append((calendarId, eventId))
        return _Exec({})


class _Exec:
    def __init__(self, result):
        self.result = result

    def execute(self):
        return self.result


class FakeService:
    def __init__(self):
        self._events = FakeEvents()

    def events(self):
        return self._events


class FakeBot:
    chat_id = 42

    def __init__(self):
        self.sent = []

    def send(self, message, reply_markup=None):
        self.sent.append((as_html(message), reply_markup))


@pytest.fixture
def rt():
    cfg = Config(calendars=[FAMILY], poll=timedelta(minutes=5), grace=timedelta(minutes=15),
                 discord_webhook_url=None, claude=ClaudeConfig(api_key="sk-ant-test"), create=CREATE)
    return Runtime(cfg=cfg, store=Store(":memory:"), tz=NY, svc=FakeService())


def propose(rt, bot, monkeypatch, **kw):
    monkeypatch.setattr(parse, "ask", lambda *a, **k: parsed(**kw))
    create.propose(bot, rt, "dentist thursday 3pm", NOW)
    return 1  # first proposal id


def test_preview_shows_when_calendar_and_buttons(rt, monkeypatch):
    bot = FakeBot()
    propose(rt, bot, monkeypatch, note="assumed next Thursday")
    text, keyboard = bot.sent[0]
    assert "🦷 <b>Dentist</b> · Thu Oct 1 · 3:00 PM–3:30 PM" in text
    assert "📅 Family · 🔔 popup 10 min" in text and "assumed next Thursday" in text
    assert [b["callback_data"] for b in keyboard["inline_keyboard"][0]] == ["create:1", "swapcal:1", "cancel:1"]
    assert rt.svc.events().inserted == []  # nothing written yet


def test_create_writes_the_event_and_offers_undo(rt, monkeypatch):
    bot = FakeBot()
    ref = propose(rt, bot, monkeypatch)
    toast, message, keyboard = create.handle(bot, rt, "create", ref, 1, NOW)
    (cal, body), = rt.svc.events().inserted
    assert toast == "Created" and cal == FAMILY and body["summary"] == "Dentist"
    assert keyboard["inline_keyboard"][0][0]["callback_data"] == f"undo:{ref}"
    assert "added" in as_html(message)


def test_create_twice_does_not_duplicate(rt, monkeypatch):
    bot = FakeBot()
    ref = propose(rt, bot, monkeypatch)
    create.handle(bot, rt, "create", ref, 1, NOW)
    toast, _, _ = create.handle(bot, rt, "create", ref, 1, NOW)
    assert toast == "Already created" and len(rt.svc.events().inserted) == 1


def test_undo_deletes_it(rt, monkeypatch):
    bot = FakeBot()
    ref = propose(rt, bot, monkeypatch)
    create.handle(bot, rt, "create", ref, 1, NOW)
    toast, message, keyboard = create.handle(bot, rt, "undo", ref, 1, NOW)
    assert toast == "Deleted" and rt.svc.events().deleted == [(FAMILY, "ev123")]
    assert keyboard is None and "deleted" in as_html(message)
    assert create.handle(bot, rt, "undo", ref, 1, NOW)[0] == "Nothing to undo"


def test_swapping_calendar_rerenders_the_preview(rt, monkeypatch):
    bot = FakeBot()
    ref = propose(rt, bot, monkeypatch)
    toast, message, keyboard = create.handle(bot, rt, "swapcal", ref, 1, NOW)
    assert toast == "→ Personal" and "📅 Personal" in as_html(message)
    assert keyboard["inline_keyboard"][0][1]["text"] == "📅 Family"  # offers the way back
    create.handle(bot, rt, "create", ref, 1, NOW)
    assert rt.svc.events().inserted[0][0] == PERSONAL  # the swap stuck


def test_cancel_writes_nothing(rt, monkeypatch):
    bot = FakeBot()
    ref = propose(rt, bot, monkeypatch)
    toast, message, keyboard = create.handle(bot, rt, "cancel", ref, 1, NOW)
    assert toast == "Cancelled" and keyboard is None
    assert rt.svc.events().inserted == []
    # a stale Create button from the same message must not write it afterwards
    assert create.handle(bot, rt, "create", ref, 1, NOW)[0] == "That one has expired"


def test_expired_proposal(rt):
    assert create.handle(FakeBot(), rt, "create", 999, 1, NOW)[0] == "That one has expired"
