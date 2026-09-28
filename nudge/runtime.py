"""What the Telegram listener needs to answer a message or a button tap.

The engine owns these and hands them to `snooze.listen`, which passes them on
to the command router. Kept in its own module so `snooze` and `commands` don't
have to import `engine` (which imports them).
"""

from __future__ import annotations

from dataclasses import dataclass
from zoneinfo import ZoneInfo

from .config import Config
from .store import Store


@dataclass
class Runtime:
    cfg: Config
    store: Store
    tz: ZoneInfo
    svc: object | None = None  # Google Calendar service; rebuilt after auth errors
