"""Liveness: an outside heartbeat, and systemd's watchdog.

Two failure modes that `Restart=always` alone does not cover:

- the Pi is off, offline, or the SD card is dead -> nothing on the Pi can tell
  you, so nudge pings an external service (healthchecks.io) after every
  successful poll. No ping for a while and that service alerts you.
- the loop wedges (a network call that never returns) -> the process is alive
  but useless, so nudge tells systemd "still here" each tick and systemd
  restarts it if that stops (WatchdogSec in the unit).

Neither path may ever disturb a reminder: everything here swallows its errors.
"""

from __future__ import annotations

import logging
import os
import socket
import urllib.error
import urllib.request

log = logging.getLogger("nudge")

PING_TIMEOUT = 5


def ping(url: str | None, suffix: str = "") -> None:
    """Tell the heartbeat service we're alive (or, with /fail, that we're not)."""
    if not url:
        return
    try:
        with urllib.request.urlopen(url.rstrip("/") + suffix, timeout=PING_TIMEOUT):
            pass
    except (urllib.error.URLError, OSError) as e:  # a heartbeat must never raise
        log.debug("heartbeat ping failed: %s", e)


def notify(state: str) -> None:
    """sd_notify: READY=1 at startup, WATCHDOG=1 each tick.

    Does nothing when not run under systemd (no NOTIFY_SOCKET).
    """
    address = os.environ.get("NOTIFY_SOCKET")
    if not address:
        return
    if address.startswith("@"):  # abstract namespace
        address = "\0" + address[1:]
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as sock:
            sock.connect(address)
            sock.sendall(state.encode())
    except OSError as e:
        log.debug("sd_notify failed: %s", e)
