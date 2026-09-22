"""CLI: python -m nudge {auth,calendars,upcoming}"""

from __future__ import annotations

import argparse
import dataclasses
import logging
import sys
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from . import config, engine, format, gcal, notifiers
from .store import Store
from .triggers import Trigger, triggers_for_event

FMT = "%a %b %d %I:%M %p"


def cmd_auth(args) -> None:
    gcal.authorize(port=args.port, open_browser=not args.no_browser)
    print(f"Authorized. Token saved to {gcal.TOKEN}")


def cmd_calendars(args) -> None:
    svc = gcal.service()
    for cal in gcal.list_calendars(svc):
        popups = [r["minutes"] for r in cal.get("defaultReminders", []) if r["method"] == "popup"]
        print(f"{cal.get('summary', '?')}")
        print(f"    id:       {cal['id']}")
        print(f"    access:   {cal.get('accessRole')}   tz: {cal.get('timeZone')}")
        print(f"    default popup reminders (min): {popups or 'none'}")


def cmd_upcoming(args) -> None:
    svc = gcal.service()
    if args.calendar:
        cal_ids = args.calendar
    elif config.CONFIG_FILE.exists():
        cal_ids = config.load().calendars
    else:
        cal_ids = [c["id"] for c in gcal.list_calendars(svc) if c.get("selected")]
    now = datetime.now(timezone.utc)
    tz = ZoneInfo(gcal.user_timezone(svc))
    rules = config.load().emoji if config.CONFIG_FILE.exists() else format.EmojiRules()
    for cal_id in cal_ids:
        cal = gcal.get_calendar(svc, cal_id)
        defaults = cal.get("defaultReminders", [])
        events = gcal.list_events(svc, cal_id, now, now + timedelta(days=args.days))
        print(f"\n=== {cal.get('summary', cal_id)}  ({len(events)} events; showing {tz.key}, calendar tz {cal.get('timeZone')}) ===")
        for ev in events:
            triggers = triggers_for_event(ev, cal_id, defaults, tz)
            when = ev["start"].get("date") or datetime.fromisoformat(ev["start"]["dateTime"]).astimezone(tz).strftime(FMT)
            title = ev.get("summary", "(no title)")
            print(f"- {when}  {rules.pick(title)} {title}")
            print(f"    raw reminders: {ev.get('reminders')}")
            if not triggers:
                print("    -> no popup triggers")
            for t in triggers:
                late = "  (already past)" if t.fire_at < now else ""
                print(f"    -> popup {t.minutes_before} min: fires {t.fire_at.astimezone(tz).strftime(FMT)}{late}")


def _notifiers(cfg: config.Config):
    ns = notifiers.from_config(cfg)
    if not ns:
        raise config.ConfigError("No notifier configured (set discord.webhook_url)")
    return ns


def cmd_test(args) -> None:
    cfg = config.load()
    now = datetime.now(timezone.utc)
    sample = Trigger("test", "test", "nudge test message", now + timedelta(minutes=10), False, 10, now)
    msg = format.message(sample, now, ZoneInfo("UTC"))  # relative wording; tz unused
    ns = _notifiers(cfg)
    if any(getattr(n, "supports_actions", False) for n in ns):
        # Real snooze buttons. They only work when the machine running the
        # service (the Pi) sent this, since taps are looked up in its store.
        msg = dataclasses.replace(msg, ref=Store().add_reminder(sample, msg, now))
    for n in ns:
        n.send(msg)
        print(f"sent via {n.name}: {msg.title} · {msg.detail}")


def cmd_telegram_chats(args) -> None:
    from .notifiers.telegram import recent_chats

    cfg = config.load()
    if not cfg.telegram_bot_token:
        raise config.ConfigError("Set telegram.bot_token first")
    chats = recent_chats(cfg.telegram_bot_token)
    if not chats:
        print("No messages yet. Send your bot any message in Telegram, then re-run.")
    for chat_id, name in chats.items():
        print(f"chat_id = {chat_id}    # {name}")


def cmd_run(args) -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    cfg = config.load()
    engine.run(cfg, _notifiers(cfg), Store())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="nudge")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("auth", help="one-time Google sign-in; saves token")
    p.add_argument("--port", type=int, default=0, help="fixed local port (for SSH forwarding on the Pi)")
    p.add_argument("--no-browser", action="store_true", help="print the URL instead of opening a browser")
    p.set_defaults(func=cmd_auth)

    p = sub.add_parser("calendars", help="list calendars and their IDs")
    p.set_defaults(func=cmd_calendars)

    p = sub.add_parser("upcoming", help="show upcoming events and computed popup triggers")
    p.add_argument("--days", type=int, default=14)
    p.add_argument("--calendar", action="append", help="calendar ID (repeatable); default: config, else all visible")
    p.set_defaults(func=cmd_upcoming)

    p = sub.add_parser("test", help="send a sample notification")
    p.set_defaults(func=cmd_test)

    p = sub.add_parser("telegram-chats", help="show chat IDs that have messaged your bot")
    p.set_defaults(func=cmd_telegram_chats)

    p = sub.add_parser("run", help="run the reminder service (foreground)")
    p.set_defaults(func=cmd_run)

    args = parser.parse_args(argv)
    try:
        args.func(args)
    except KeyboardInterrupt:
        return 130
    except (gcal.AuthError, config.ConfigError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
