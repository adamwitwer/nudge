"""One-off nudges from the command line: `nudge send "Power outage" ...`.

For things that aren't calendar events: a script noticed something and wants
you told (see outage/watch.sh). The message gets the usual snooze/Done
buttons, so run it on the machine that runs the service. Its detail is fixed
text, so a snoozed re-send repeats it rather than "started 10 minutes ago".
"""

from __future__ import annotations

import dataclasses
from datetime import datetime, time, timedelta

from .format import Message
from .notifiers import Notifier
from .store import Store
from .triggers import Trigger

QUIET_FROM = time(22, 0)  # --quiet holds from here until the morning brief


def hold_until(now: datetime, morning: time) -> datetime | None:
    """When --quiet should deliver instead of now; None means send now.

    `now` is aware local time.
    """
    if now.time() >= QUIET_FROM:
        return datetime.combine(now.date() + timedelta(days=1), morning, now.tzinfo)
    if now.time() < morning:
        return datetime.combine(now.date(), morning, now.tzinfo)
    return None


def send(notifiers: list[Notifier], store: Store, title: str, detail: str, emoji: str,
         now: datetime, hold: datetime | None = None) -> tuple[Message, datetime | None]:
    """Send now, or with `hold` leave it for the service to deliver then.

    A held nudge is stored as a reminder that is already snoozed, so the
    running service sends it (to Telegram) when the time comes. Returns the
    message and the hold time actually used.
    """
    msg = Message(title, detail, emoji=emoji)
    ref = store.add_reminder(Trigger("send", "send", title, now, False, 0, now), msg, now, fixed=True)
    if hold and any(getattr(n, "supports_actions", False) for n in notifiers):
        store.set_snooze(ref, hold)
        return msg, hold
    msg = dataclasses.replace(msg, ref=ref)
    for n in notifiers:
        n.send(msg)
    return msg, None
