from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

from nudge import snooze
from nudge.engine import process_due
from nudge.format import Message
from nudge.notifiers import telegram
from nudge.notifiers.telegram import TelegramBot
from nudge.store import Store
from nudge.triggers import Trigger

NY = ZoneInfo("America/New_York")
NOW = datetime(2026, 9, 22, 19, 50, tzinfo=timezone.utc)  # 3:50 PM ET
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


def sent_reminder(store, api, title="Dentist"):
    """Run a due trigger through the engine; return (trigger, ref)."""
    t = Trigger("cal", "e1", title, NOW + timedelta(minutes=10), False, 10, NOW)
    process_due([t], store, [TelegramBot("1:x", CHAT)], NOW, NY, timedelta(minutes=15))
    send = [p for m, p in api if m == "sendMessage"][-1]
    ref = int(send["reply_markup"]["inline_keyboard"][0][0]["callback_data"].split(":")[1])
    return t, ref


def tap(store, action, ref, now=NOW, chat=CHAT):
    cq = {"id": "cq1", "data": f"{action}:{ref}", "message": {"message_id": 1, "chat": {"id": chat}}}
    snooze.handle_callback(TelegramBot("1:x", CHAT), store, cq, now, NY)


def test_reminder_gets_three_buttons(api):
    store = Store(":memory:")
    _, ref = sent_reminder(store, api)
    buttons = [p for m, p in api if m == "sendMessage"][0]["reply_markup"]["inline_keyboard"][0]
    assert [b["text"] for b in buttons] == ["💤 10 min", "💤 1 hour", "✅ Done"]
    assert [b["callback_data"] for b in buttons] == [f"snooze10:{ref}", f"snooze60:{ref}", f"done:{ref}"]


def test_snooze_edits_message_and_refires_later(api):
    store = Store(":memory:")
    _, ref = sent_reminder(store, api)
    api.clear()
    tap(store, "snooze10", ref)
    assert api[0] == ("answerCallbackQuery", {"callback_query_id": "cq1", "text": "Snoozed until 4:00 PM"})
    method, edit = api[1]
    assert method == "editMessageText" and "reply_markup" not in edit  # buttons removed
    assert edit["text"].endswith("💤 <i>Snoozed until 4:00 PM</i>")

    bot = TelegramBot("1:x", CHAT)
    api.clear()
    snooze.fire_due([bot], store, NOW + timedelta(minutes=9), NY)
    assert api == []  # not yet
    snooze.fire_due([bot], store, NOW + timedelta(minutes=10), NY)
    (method, resend), = api
    assert method == "sendMessage"
    assert resend["text"] == "🦷 <b>Dentist</b> · now"
    assert resend["reply_markup"]["inline_keyboard"][0][0]["callback_data"] == f"snooze10:{ref}"
    api.clear()
    snooze.fire_due([bot], store, NOW + timedelta(minutes=11), NY)
    assert api == []  # fired once only


def test_snoozed_past_start_says_started_ago(api):
    store = Store(":memory:")
    _, ref = sent_reminder(store, api)
    tap(store, "snooze60", ref)
    api.clear()
    snooze.fire_due([TelegramBot("1:x", CHAT)], store, NOW + timedelta(hours=1), NY)
    assert api[0][1]["text"] == "🦷 <b>Dentist</b> · started 50 minutes ago"


def test_done_removes_buttons_and_cancels_snooze(api):
    store = Store(":memory:")
    _, ref = sent_reminder(store, api)
    tap(store, "snooze10", ref)
    tap(store, "done", ref)
    assert store.get_reminder(ref).snooze_until is None
    assert api[-1][1]["text"].endswith("✅ <i>Done</i>")


def test_taps_from_other_chats_are_ignored(api):
    store = Store(":memory:")
    _, ref = sent_reminder(store, api)
    api.clear()
    tap(store, "snooze10", ref, chat=999)
    assert [m for m, _ in api] == ["answerCallbackQuery"]
    assert store.get_reminder(ref).snooze_until is None


def test_unknown_ref_says_expired(api):
    store = Store(":memory:")
    tap(store, "snooze10", 12345)
    assert api[0][1]["text"] == "This reminder has expired"
    assert api[1][0] == "editMessageReplyMarkup"


def test_discord_only_reminders_get_no_ref(api):
    from nudge.notifiers.discord import DiscordWebhook

    class FakeDiscord(DiscordWebhook):
        def __init__(self):
            self.got = []

        def send(self, message):
            self.got.append(message)

    store, d = Store(":memory:"), FakeDiscord()
    t = Trigger("cal", "e1", "x", NOW + timedelta(minutes=10), False, 10, NOW)
    process_due([t], store, [d], NOW, NY, timedelta(minutes=15))
    assert d.got[0].ref is None
