"""The once-a-day brief: today's agenda plus the missing-popup audit.

Sent at morning.time (default 8:30 AM local) to morning.via (Telegram).
It goes out even on an empty day: if the brief doesn't arrive, nudge is down.
"""

from __future__ import annotations

import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from . import agenda, audit, format
from .config import MorningConfig
from .notifiers import Notifier
from .store import Store

log = logging.getLogger("nudge")

LAST_RUN_KEY = "morning_last_run"  # local date of the last completed brief
EMOJI = "☀️"


def build_message(items: list[agenda.Item], findings: list[audit.Finding], now: datetime, tz: ZoneInfo, rules: format.EmojiRules) -> format.Message:
    local = now.astimezone(tz)
    title = local.strftime("%A, %b ") + str(local.day)
    sections: list[tuple[str | None, tuple[str, ...]]] = []
    detail = ""
    if items:
        sections.append((None, tuple(i.line(tz, rules) for i in items)))
    else:
        detail = "nothing on the calendar today"
    if findings:
        n = len(findings)
        heading = f"{n} event{'s' if n != 1 else ''} with no popup notification"
        sections.append((heading, tuple(f.line(tz) for f in findings)))
    return format.Message(title, detail, emoji=EMOJI, sections=tuple(sections))


def is_due(cfg: MorningConfig, store: Store, now: datetime, tz: ZoneInfo) -> bool:
    local = now.astimezone(tz)
    return cfg.enabled and local.time() >= cfg.at and store.get_meta(LAST_RUN_KEY) != local.date().isoformat()


def run(cfg: MorningConfig, svc, calendar_ids: list[str], notifiers: list[Notifier], store: Store,
        now: datetime, tz: ZoneInfo, rules: format.EmojiRules) -> None:
    """Send the brief and mark today done. Raises on failure (retried next poll)."""
    targets = [n for n in notifiers if n.name in cfg.via]
    items = agenda.today(svc, calendar_ids, tz, now, cfg.tag) if cfg.agenda else []
    events, defaults = audit.collect(svc, calendar_ids, tz, now, cfg.days)
    findings = audit.find_missing(events, defaults, tz, cfg.tag)
    if not targets:
        log.warning("morning brief: no notifier matches morning.via=%s", list(cfg.via))
    else:
        msg = build_message(items, findings, now, tz, rules)
        for n in targets:
            n.send(msg)
        log.info("morning brief: %d event(s) today, %d without a popup", len(items), len(findings))
    store.set_meta(LAST_RUN_KEY, now.astimezone(tz).date().isoformat())
