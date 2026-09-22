"""CLI: python -m nudge {auth,calendars,upcoming}"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from . import gcal
from .triggers import triggers_for_event

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
    else:
        cal_ids = [c["id"] for c in gcal.list_calendars(svc) if c.get("selected")]
    now = datetime.now(timezone.utc)
    tz = ZoneInfo(gcal.user_timezone(svc))
    for cal_id in cal_ids:
        cal = gcal.get_calendar(svc, cal_id)
        defaults = cal.get("defaultReminders", [])
        events = gcal.list_events(svc, cal_id, now, now + timedelta(days=args.days))
        print(f"\n=== {cal.get('summary', cal_id)}  ({len(events)} events; showing {tz.key}, calendar tz {cal.get('timeZone')}) ===")
        for ev in events:
            triggers = triggers_for_event(ev, cal_id, defaults, tz)
            when = ev["start"].get("date") or datetime.fromisoformat(ev["start"]["dateTime"]).astimezone(tz).strftime(FMT)
            print(f"- {when}  {ev.get('summary', '(no title)')}")
            print(f"    raw reminders: {ev.get('reminders')}")
            if not triggers:
                print("    -> no popup triggers")
            for t in triggers:
                late = "  (already past)" if t.fire_at < now else ""
                print(f"    -> popup {t.minutes_before} min: fires {t.fire_at.astimezone(tz).strftime(FMT)}{late}")


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
    p.add_argument("--calendar", action="append", help="calendar ID (repeatable); default: all visible")
    p.set_defaults(func=cmd_upcoming)

    args = parser.parse_args(argv)
    try:
        args.func(args)
    except gcal.AuthError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
