from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from nudge import agenda, audit, morning
from nudge.config import MorningConfig
from nudge.format import EmojiRules, as_html
from nudge.store import Store

NY = ZoneInfo("America/New_York")
CAL = "family"
NOW = datetime(2026, 9, 25, 8, 30, tzinfo=NY).astimezone(timezone.utc)  # Friday
RULES = EmojiRules()


def ev(id_, title, start, **extra):
    e = {"id": id_, "summary": title, "start": {"dateTime": start} if "T" in start else {"date": start}}
    e.setdefault("reminders", {"useDefault": False, "overrides": [{"method": "popup", "minutes": 10}]})
    e.update(extra)
    return e


def items(events):
    return agenda.today(None, [CAL], NY, NOW, "")


def test_day_bounds_are_local_midnight():
    start, end = agenda.day_bounds(NOW, NY)
    assert start == datetime(2026, 9, 25, 0, 0, tzinfo=NY)
    assert end == datetime(2026, 9, 26, 0, 0, tzinfo=NY)


def test_agenda_orders_all_day_first(monkeypatch):
    evs = [
        ev("a", "Recycling", "2026-09-25T20:00:00-04:00"),
        ev("b", "Change water filters", "2026-09-25"),
        ev("c", "Dentist", "2026-09-25T09:00:00-04:00"),
        ev("d", "Declined", "2026-09-25T10:00:00-04:00", attendees=[{"self": True, "responseStatus": "declined"}]),
    ]
    monkeypatch.setattr(agenda.gcal, "list_events", lambda *a: evs)
    lines = [i.line(NY, RULES) for i in agenda.today(None, [CAL], NY, NOW, "#nonudge")]
    assert lines == [
        "all day · 💧 Change water filters",
        "9:00 AM · 🦷 Dentist",
        "8:00 PM · ♻️ Recycling",
    ]


def test_brief_merges_agenda_and_audit(monkeypatch):
    monkeypatch.setattr(agenda.gcal, "list_events", lambda *a: [ev("a", "Recycling", "2026-09-25T20:00:00-04:00")])
    day = agenda.today(None, [CAL], NY, NOW, "")
    findings = audit.find_missing([(CAL, ev("x", "Soccer", "2026-09-27T17:00:00-04:00", reminders={"useDefault": False}, recurringEventId="s"))], {CAL: []}, NY, "")
    msg = morning.build_message(day, findings, NOW, NY, RULES)
    assert as_html(msg) == (
        "☀️ <b>Friday, Sep 25</b>"
        "\n• 8:00 PM · ♻️ Recycling"
        "\n\n<b>1 event with no popup notification</b>"
        "\n• Sun Sep 27 5:00 PM · Soccer (repeats)"
    )


def test_empty_day_still_says_something():
    msg = morning.build_message([], [], NOW, NY, RULES)
    assert as_html(msg) == "☀️ <b>Friday, Sep 25</b> · nothing on the calendar today"


class FakeNotifier:
    def __init__(self, name="telegram"):
        self.name, self.sent = name, []

    def send(self, message):
        self.sent.append(message)


def run_at(local_hm, store, monkeypatch, cfg=MorningConfig()):
    monkeypatch.setattr(agenda, "today", lambda *a: [])
    monkeypatch.setattr(audit, "collect", lambda *a: ([], {}))
    monkeypatch.setattr(morning.audit, "collect", lambda *a: ([], {}))
    now = datetime(2026, 9, 25, *local_hm, tzinfo=NY).astimezone(timezone.utc)
    tg, dc = FakeNotifier(), FakeNotifier("discord")
    if morning.is_due(cfg, store, now, NY):
        morning.run(cfg, None, [CAL], [dc, tg], store, now, NY, RULES)
    return tg, dc


def test_sends_once_a_day_after_830_via_telegram(monkeypatch):
    store = Store(":memory:")
    tg, _ = run_at((8, 29), store, monkeypatch)
    assert tg.sent == []  # too early
    tg, dc = run_at((8, 30), store, monkeypatch)
    assert len(tg.sent) == 1 and dc.sent == []  # empty day still sends
    tg, _ = run_at((12, 0), store, monkeypatch)
    assert tg.sent == [] and store.get_meta(morning.LAST_RUN_KEY) == "2026-09-25"


def test_disabled(monkeypatch):
    tg, _ = run_at((9, 0), Store(":memory:"), monkeypatch, MorningConfig(enabled=False))
    assert tg.sent == []
