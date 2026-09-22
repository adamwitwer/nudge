"""The service loop: poll Google Calendar, fire due triggers, remember them."""

from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from google.auth.exceptions import RefreshError

from . import format, gcal
from .config import Config
from .notifiers import Notifier
from .store import Store
from .triggers import Trigger, triggers_for_event

log = logging.getLogger("nudge")

TICK_SECONDS = 30
LATE_AFTER = timedelta(minutes=2)
# Popup reminders max out at 4 weeks; all-day events add up to a day.
LOOKAHEAD = timedelta(days=29)


def collect_triggers(svc, calendar_ids: list[str], tz: ZoneInfo, now: datetime, grace: timedelta) -> list[Trigger]:
    triggers: list[Trigger] = []
    for cal_id in calendar_ids:
        cal = gcal.get_calendar(svc, cal_id)
        defaults = cal.get("defaultReminders", [])
        for ev in gcal.list_events(svc, cal_id, now - grace, now + LOOKAHEAD):
            triggers.extend(triggers_for_event(ev, cal_id, defaults, tz))
    return triggers


def process_due(
    triggers: list[Trigger],
    store: Store,
    notifiers: list[Notifier],
    now: datetime,
    tz: ZoneInfo,
    grace: timedelta,
) -> None:
    for t in sorted(triggers, key=lambda t: t.fire_at):
        if t.fire_at > now or store.seen(t.key):
            continue
        lateness = now - t.fire_at
        if lateness > grace:
            log.info("skipping %r (%d min late)", t.title, lateness.total_seconds() // 60)
            store.mark(t.key, "skipped", now)
            continue
        text = format.message(t, now, tz, late=lateness > LATE_AFTER)
        try:
            for n in notifiers:
                n.send(text)
        except Exception as e:  # leave unmarked; retried next tick until grace runs out
            log.warning("send failed for %r: %s", t.title, e)
            continue
        log.info("sent %r (%d min before)", t.title, t.minutes_before)
        store.mark(t.key, "sent", now)


def run(cfg: Config, notifiers: list[Notifier], store: Store) -> None:
    triggers: list[Trigger] = []
    last_poll: datetime | None = None
    auth_alerted = False
    svc = tz = None

    while True:
        now = datetime.now(timezone.utc)
        if last_poll is None or now - last_poll >= cfg.poll:
            try:
                svc = svc or gcal.service()
                tz = tz or ZoneInfo(gcal.user_timezone(svc))
                triggers = collect_triggers(svc, cfg.calendars, tz, now, cfg.grace)
                last_poll = now
                auth_alerted = False
                store.prune(now)
                log.info("polled: %d upcoming popup triggers", sum(t.fire_at > now for t in triggers))
            except (gcal.AuthError, RefreshError) as e:  # refresh can also fail mid-run
                log.error("%s", e)
                if not auth_alerted:
                    _alert(notifiers, f"⚠️ nudge can't read Google Calendar: re-run `python -m nudge auth` on the Pi. ({e})")
                    auth_alerted = True
                svc = None
                last_poll = now  # retry on the next poll interval, not every tick
            except Exception as e:  # network blips etc.: keep the last good trigger list
                log.warning("poll failed: %s", e)
                last_poll = now
        if tz is not None:
            process_due(triggers, store, notifiers, now, tz, cfg.grace)
        time.sleep(TICK_SECONDS)


def _alert(notifiers: list[Notifier], text: str) -> None:
    for n in notifiers:
        try:
            n.send(text)
        except Exception as e:
            log.warning("alert via %s failed: %s", n.name, e)
