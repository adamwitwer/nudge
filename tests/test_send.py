import sqlite3
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

import pytest

from nudge import send, snooze
from nudge.notifiers import telegram
from nudge.notifiers.telegram import TelegramBot
from nudge.store import Store

NY = ZoneInfo("America/New_York")
NOW = datetime(2026, 10, 10, 14, 14, tzinfo=NY)  # 2:14 PM ET
MORNING = time(8, 30)
CHAT = 42


@pytest.fixture
def api(monkeypatch):
    """Fake Telegram Bot API: records every call."""
    calls = []

    def fake_call(token, method, params=None, timeout=10):
        calls.append((method, params or {}))
        return {"message_id": 1} if method == "sendMessage" else True

    monkeypatch.setattr(telegram, "call", fake_call)
    monkeypatch.setattr(snooze, "call", fake_call)
    return calls


def outage(store, now=NOW, hold=None):
    bot = TelegramBot("1:x", CHAT)
    return send.send([bot], store, "Power outage at 2:14 PM", "reset the clocks", "⚡", now, hold)


def test_send_goes_out_with_snooze_buttons(api):
    store = Store(":memory:")
    msg, held = outage(store)
    assert held is None
    (method, sent), = api
    assert method == "sendMessage"
    assert sent["text"] == "⚡ <b>Power outage at 2:14 PM</b> · reset the clocks"
    assert sent["reply_markup"]["inline_keyboard"][0][0]["callback_data"] == f"snooze10:{msg.ref}"


def test_snoozed_send_repeats_its_own_detail(api):
    """Not "started 1 hour ago": the detail is text, not a lead time."""
    store = Store(":memory:")
    msg, _ = outage(store)
    store.set_snooze(msg.ref, NOW + timedelta(hours=1))
    api.clear()
    snooze.fire_due([TelegramBot("1:x", CHAT)], store, NOW + timedelta(hours=1), NY)
    assert api[0][1]["text"] == "⚡ <b>Power outage at 2:14 PM</b> · reset the clocks"


@pytest.mark.parametrize("hour, minute, expected", [
    (14, 14, None),  # daytime: send now
    (21, 59, None),
    (22, 0, datetime(2026, 10, 11, 8, 30, tzinfo=NY)),  # late evening: tomorrow's brief
    (3, 12, datetime(2026, 10, 10, 8, 30, tzinfo=NY)),  # small hours: today's brief
    (8, 30, None),
])
def test_hold_until(hour, minute, expected):
    assert send.hold_until(NOW.replace(hour=hour, minute=minute), MORNING) == expected


def test_held_send_is_delivered_by_the_service_later(api):
    store = Store(":memory:")
    at_3am = NOW.replace(hour=3, minute=12)
    _, held = outage(store, at_3am, send.hold_until(at_3am, MORNING))
    assert api == []  # nothing sent at 3 AM
    bot = TelegramBot("1:x", CHAT)
    snooze.fire_due([bot], store, held - timedelta(minutes=1), NY)
    assert api == []
    snooze.fire_due([bot], store, held, NY)
    assert [m for m, _ in api] == ["sendMessage"]
    assert "reply_markup" in api[0][1]


def test_hold_is_ignored_without_a_notifier_that_can_deliver_it():
    """Held nudges come back through the Telegram snooze path only."""
    class Plain:
        name = "discord"

        def __init__(self):
            self.got = []

        def send(self, message):
            self.got.append(message)

    plain = Plain()
    _, held = send.send([plain], Store(":memory:"), "x", "", "⏰", NOW, NOW + timedelta(hours=5))
    assert held is None and len(plain.got) == 1


def test_store_adds_the_fixed_column_to_an_older_db(tmp_path):
    """The Pi's state.db predates `fixed`; opening it must migrate, not crash."""
    path = tmp_path / "state.db"
    db = sqlite3.connect(path)
    db.execute(
        "CREATE TABLE reminders (id INTEGER PRIMARY KEY AUTOINCREMENT,"
        " title TEXT NOT NULL, detail TEXT NOT NULL, emoji TEXT NOT NULL, late INTEGER NOT NULL,"
        " start TEXT NOT NULL, all_day INTEGER NOT NULL, snooze_until TEXT, created TEXT NOT NULL)"
    )
    db.execute(
        "INSERT INTO reminders (title, detail, emoji, late, start, all_day, created)"
        " VALUES ('Dentist', 'in 10 minutes', '🦷', 0, ?, 0, ?)",
        (NOW.isoformat(), NOW.isoformat()),
    )
    db.commit()
    db.close()

    store = Store(path)
    old = store.get_reminder(1)
    assert old.message.title == "Dentist" and old.fixed is False
    Store(path)  # opening again is a no-op
