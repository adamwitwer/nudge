import os
import socket
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from nudge import commands, health
from nudge.config import ClaudeConfig, Config, CreateConfig, HealthConfig
from nudge.format import as_html
from nudge.runtime import Runtime
from nudge.store import Store

NY = ZoneInfo("America/New_York")
NOW = datetime(2026, 9, 29, 16, 0, tzinfo=timezone.utc)
URL = "https://hc-ping.com/abc"


# --- the outside heartbeat


def test_ping_calls_the_url(monkeypatch):
    seen = []
    monkeypatch.setattr(health.urllib.request, "urlopen", lambda url, timeout=None: seen.append(url) or _Null())
    health.ping(URL)
    health.ping(URL, "/fail")
    assert seen == [URL, URL + "/fail"]


def test_ping_without_a_url_does_nothing(monkeypatch):
    monkeypatch.setattr(health.urllib.request, "urlopen", lambda *a, **k: 1 / 0)
    health.ping(None)  # must not raise


def test_ping_swallows_network_errors(monkeypatch):
    def boom(url, timeout=None):
        raise OSError("network is unreachable")

    monkeypatch.setattr(health.urllib.request, "urlopen", boom)
    health.ping(URL)  # a dead heartbeat must never break a reminder


class _Null:
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


# --- systemd watchdog


class FakeSocket:
    """Records what sd_notify would have sent (no real AF_UNIX path limits)."""

    last = None

    def __init__(self, family, type_):
        FakeSocket.last = self
        self.connected = None
        self.sent = None

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def connect(self, address):
        self.connected = address

    def sendall(self, data):
        self.sent = data


def test_notify_sends_to_the_systemd_socket(monkeypatch):
    monkeypatch.setenv("NOTIFY_SOCKET", "/run/systemd/notify")
    monkeypatch.setattr(health.socket, "socket", FakeSocket)
    health.notify("WATCHDOG=1")
    assert FakeSocket.last.connected == "/run/systemd/notify"
    assert FakeSocket.last.sent == b"WATCHDOG=1"


def test_notify_handles_an_abstract_socket(monkeypatch):
    monkeypatch.setenv("NOTIFY_SOCKET", "@/org/freedesktop/systemd1/notify")
    monkeypatch.setattr(health.socket, "socket", FakeSocket)
    health.notify("READY=1")
    assert FakeSocket.last.connected == "\0/org/freedesktop/systemd1/notify"


def test_notify_without_systemd_is_a_no_op(monkeypatch):
    monkeypatch.delenv("NOTIFY_SOCKET", raising=False)
    health.notify("READY=1")  # must not raise


def test_notify_survives_a_dead_socket(monkeypatch):
    monkeypatch.setenv("NOTIFY_SOCKET", "/run/nope/gone.sock")
    health.notify("WATCHDOG=1")  # must not raise


# --- /health


@pytest.fixture
def rt():
    cfg = Config(calendars=["fam", "per"], poll=timedelta(minutes=5), grace=timedelta(minutes=15),
                 discord_webhook_url=None, claude=ClaudeConfig(api_key="sk-ant-test"),
                 create=CreateConfig(default_calendar="fam"), health=HealthConfig(ping_url=URL))
    return Runtime(cfg=cfg, store=Store(":memory:"), tz=NY, svc=object())


def test_health_reports_the_state(rt):
    rt.store.set_meta("last_poll", (NOW - timedelta(minutes=3)).isoformat())
    rt.store.set_meta("started", (NOW - timedelta(hours=26)).isoformat())
    rt.store.set_meta("upcoming", "24")
    out = as_html(commands.health_message(rt, NOW))
    assert "last checked the calendar 3 min ago" in out
    assert "running for 1d 2h" in out
    assert "24 reminders ahead" in out
    assert "2 calendars · ✍️ event creation on" in out
    assert "heartbeat on" in out


def test_health_before_the_first_poll(rt):
    out = as_html(commands.health_message(rt, NOW))
    assert "? reminders ahead" in out and "last checked" not in out
