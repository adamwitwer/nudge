"""SQLite record of triggers already handled, so restarts never double-send."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .gcal import CONFIG_DIR

DB_FILE = CONFIG_DIR / "state.db"


class Store:
    def __init__(self, path: Path | str = DB_FILE):
        self.db = sqlite3.connect(str(path))
        self.db.execute(
            "CREATE TABLE IF NOT EXISTS handled ("
            " key TEXT PRIMARY KEY,"
            " status TEXT NOT NULL,"  # sent | skipped
            " at TEXT NOT NULL)"
        )
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
        cutoff = (now - keep).astimezone(timezone.utc).isoformat()
        self.db.execute("DELETE FROM handled WHERE at < ?", (cutoff,))
        self.db.commit()
