from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from nudge.engine import process_due
from nudge.format import as_markdown
from nudge.notifiers.discord import DiscordWebhook
from nudge.notifiers.telegram import TelegramBot
from nudge.store import Store
from nudge.triggers import Trigger

NY = ZoneInfo("America/New_York")
NOW = datetime(2026, 9, 22, 19, 50, tzinfo=timezone.utc)
GRACE = timedelta(minutes=15)


class FakeNotifier:
    def __init__(self, name="fake", fail=False):
        self.name, self.fail, self.sent = name, fail, []

    def send(self, message):
        if self.fail:
            raise RuntimeError("boom")
        self.sent.append(as_markdown(message))


def trig(title, fire_offset_min, minutes_before=10):
    fire_at = NOW + timedelta(minutes=fire_offset_min)
    return Trigger("cal", title, title, fire_at + timedelta(minutes=minutes_before), False, minutes_before, fire_at)


def test_sends_due_once_and_skips_future():
    store, n = Store(":memory:"), FakeNotifier()
    ts = [trig("due", 0), trig("future", 5)]
    process_due(ts, store, [n], NOW, NY, GRACE)
    process_due(ts, store, [n], NOW + timedelta(seconds=30), NY, GRACE)
    assert n.sent == ["⏰ **due** · in 10 minutes"]


def test_late_within_grace_is_marked_late():
    store, n = Store(":memory:"), FakeNotifier()
    process_due([trig("late", -5)], store, [n], NOW, NY, GRACE)
    assert n.sent == ["⏰ **late** · in 5 minutes _(late)_"]


def test_beyond_grace_is_skipped_not_sent():
    store, n = Store(":memory:"), FakeNotifier()
    t = trig("stale", -20)
    process_due([t], store, [n], NOW, NY, GRACE)
    process_due([t], store, [n], NOW, NY, GRACE)
    assert n.sent == [] and store.seen(f"{t.key}|fake")


def test_failed_send_is_retried_next_tick():
    store = Store(":memory:")
    t = trig("flaky", 0)
    process_due([t], store, [FakeNotifier(fail=True)], NOW, NY, GRACE)
    ok = FakeNotifier()
    process_due([t], store, [ok], NOW + timedelta(seconds=30), NY, GRACE)
    assert len(ok.sent) == 1


def test_one_notifier_failing_does_not_resend_on_the_other():
    store, t = Store(":memory:"), trig("both", 0)
    discord, telegram = FakeNotifier("discord"), FakeNotifier("telegram", fail=True)
    process_due([t], store, [discord, telegram], NOW, NY, GRACE)
    telegram.fail = False
    process_due([t], store, [discord, telegram], NOW + timedelta(seconds=30), NY, GRACE)
    assert len(discord.sent) == 1 and len(telegram.sent) == 1


def test_discord_payload_blocks_mentions():
    p = DiscordWebhook("https://example.invalid").payload("@everyone hi")
    assert p == {"content": "@everyone hi", "allowed_mentions": {"parse": []}}


def test_telegram_payload_uses_html_without_previews():
    p = TelegramBot("123:abc", 42).payload("<b>x</b>")
    assert p["chat_id"] == 42 and p["parse_mode"] == "HTML"
    assert p["link_preview_options"] == {"is_disabled": True}
