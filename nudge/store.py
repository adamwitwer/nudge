"""SQLite state.

- `handled`: triggers already sent or skipped, per notifier, so restarts never
  double-send.
- `reminders`: each sent reminder's content, keyed by a short id that Telegram
  buttons carry, plus any pending snooze.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import NamedTuple

from .format import Message
from .gcal import CONFIG_DIR
from .triggers import Trigger

DB_FILE = CONFIG_DIR / "state.db"


class Reminder(NamedTuple):
    id: int
    message: Message
    start: datetime
    all_day: bool
    snooze_until: datetime | None


def _utc(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat()


class Store:
    def __init__(self, path: Path | str = DB_FILE):
        self.db = sqlite3.connect(str(path))
        self.db.execute(
            "CREATE TABLE IF NOT EXISTS handled ("
            " key TEXT PRIMARY KEY,"
            " status TEXT NOT NULL,"  # sent | skipped
            " at TEXT NOT NULL)"
        )
        self.db.execute(
            "CREATE TABLE IF NOT EXISTS reminders ("
            " id INTEGER PRIMARY KEY AUTOINCREMENT,"
            " title TEXT NOT NULL, detail TEXT NOT NULL, emoji TEXT NOT NULL, late INTEGER NOT NULL,"
            " start TEXT NOT NULL, all_day INTEGER NOT NULL,"
            " snooze_until TEXT,"  # UTC ISO; NULL = no pending snooze
            " created TEXT NOT NULL)"
        )
        self.db.execute("CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        self.db.commit()

    def get_meta(self, key: str) -> str | None:
        row = self.db.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
        return row[0] if row else None

    def set_meta(self, key: str, value: str) -> None:
        self.db.execute("INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)", (key, value))
        self.db.commit()

    def seen(self, key: str) -> bool:
        return self.db.execute("SELECT 1 FROM handled WHERE key = ?", (key,)).fetchone() is not None

    def mark(self, key: str, status: str, at: datetime) -> None:
        self.db.execute(
            "INSERT OR REPLACE INTO handled (key, status, at) VALUES (?, ?, ?)",
            (key, status, at.isoformat()),
        )
        self.db.commit()

    def prune(self, now: datetime, keep: timedelta = timedelta(days=60)) -> None:
        cutoff = _utc(now - keep)
        self.db.execute("DELETE FROM handled WHERE at < ?", (cutoff,))
        self.db.execute("DELETE FROM reminders WHERE created < ? AND snooze_until IS NULL", (cutoff,))
        self.db.commit()

    # --- reminders / snooze

    def add_reminder(self, trigger: Trigger, message: Message, now: datetime) -> int:
        cur = self.db.execute(
            "INSERT INTO reminders (title, detail, emoji, late, start, all_day, created)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)",
            (message.title, message.detail, message.emoji, int(message.late),
             trigger.start.isoformat(), int(trigger.all_day), _utc(now)),
        )
        self.db.commit()
        return cur.lastrowid

    def update_message(self, ref: int, message: Message) -> None:
        self.db.execute(
            "UPDATE reminders SET detail = ?, late = ? WHERE id = ?",
            (message.detail, int(message.late), ref),
        )
        self.db.commit()

    def set_snooze(self, ref: int, until: datetime | None) -> None:
        self.db.execute(
            "UPDATE reminders SET snooze_until = ? WHERE id = ?",
            (_utc(until) if until else None, ref),
        )
        self.db.commit()

    def get_reminder(self, ref: int) -> Reminder | None:
        row = self.db.execute("SELECT * FROM reminders WHERE id = ?", (ref,)).fetchone()
        return self._reminder(row) if row else None

    def due_snoozes(self, now: datetime) -> list[Reminder]:
        rows = self.db.execute(
            "SELECT * FROM reminders WHERE snooze_until IS NOT NULL AND snooze_until <= ?"
            " ORDER BY snooze_until",
            (_utc(now),),
        ).fetchall()
        return [self._reminder(r) for r in rows]

    @staticmethod
    def _reminder(row) -> Reminder:
        id_, title, detail, emoji, late, start, all_day, snooze_until, _ = row
        return Reminder(
            id=id_,
            message=Message(title, detail, bool(late), emoji, ref=id_),
            start=datetime.fromisoformat(start),
            all_day=bool(all_day),
            snooze_until=datetime.fromisoformat(snooze_until) if snooze_until else None,
        )
