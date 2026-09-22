# AGENTS.md

Guidance for AI agents (Claude Code and others) working in this repo. This
project is a collaboration: agents are expected to offer opinions, push back,
and suggest improvements, not just execute. Record that input here.

## Project

**nudge** is a small service for a Raspberry Pi. It reads Google Calendar events (from a
configured list of calendars) and sends each event's **popup** reminders as
Discord and/or Telegram messages at the times set in GCal. The spec and plan
are in `miniPRD.txt`, which is the source of truth for requirements.

## Working agreements

- Keep it simple. This is a personal tool, not a platform. Prefer the stdlib
  and a few dependencies over frameworks.
- **Public repo: never commit secrets.** OAuth client secrets, `token.json`,
  webhook URLs, bot tokens, chat IDs, and real calendar IDs stay out of git.
  Commit `config.example.toml` only.
- Target is Python 3.11+ (dev machine has 3.14) (Raspberry Pi OS Bookworm). Don't use newer syntax
  without checking.
- Trigger computation is the risky logic (all-day events, `useDefault`,
  time zones, DST), so it gets unit tests.
- Layout: `nudge/` package, run as `python -m nudge <command>`. Tests are in
  `tests/` (pytest). Local secrets live in `~/.config/nudge/`.
- Deployment: Raspberry Pi 5 (`raspberrypi`, over Tailscale at
  100.107.81.122; Debian 12, Python 3.11.2). It follows the Pi's conventions:
  a git clone in `~/Projects/nudge` with a `venv/`, secrets beside the code
  (gitignored), and the unit in `systemd/nudge.service` copied to
  `/etc/systemd/system/`. Config lookup: `$NUDGE_CONFIG_DIR`, then the
  project folder if it has `config.toml`, then `~/.config/nudge` (dev Mac).
- Deploy an update: `ssh adam@100.107.81.122 'cd ~/Projects/nudge && git pull
  && venv/bin/pip install -q -e . && sudo systemctl restart nudge'`
- Gotcha (macOS, Python 3.13+): macOS can flag the venv's editable-install
  `.pth` as hidden, and Python then skips it. pytest sets `pythonpath = ["."]`,
  and `python -m nudge` works from the repo root regardless.
- Run `pytest` before every commit.
- When a requirement changes, update `miniPRD.txt` section 3 as well as the
  code.

## Agent input log

Suggestions, concerns, and opinions from agents, with their status. Newest
first. Status is one of: open / adopted / declined / done.

| Date | Input | Status |
|------|-------|--------|
| 2026-09-21 | M4: deployed to the Pi as `nudge.service` (enabled, active). Verified `upcoming` and `test` from the Pi. First live check: TEST EVENT FOR CLAUDE popup at 3:50 PM ET on 2026-09-22. Only one machine should run `nudge run`, or you get double sends. | done |
| 2026-09-21 | The Pi's LAN IP (192.168.50.53) isn't in the Mac's known_hosts, so SSH over LAN failed host-key verification. Use Tailscale (100.107.81.122), or verify and add the LAN key by hand. | open (minor) |
| 2026-09-21 | M2+M3 done: SQLite dedupe store, 30 s tick / 5 min poll loop, Discord webhook (mentions disabled so a title can't ping @everyone), `nudge test` and `nudge run`. The auth-failure alert (from M5) is also in. Sample message delivered to Discord. | done |
| 2026-09-21 | With more than one notifier, a send failure on the second means a retry re-sends on the first. That's fine while Discord is the only notifier. Track per-notifier sent state when Telegram is added. | open (Telegram) |
| 2026-09-21 | M1 verified against the real API: popup and email overrides come back exactly as set in GCal. The Family calendar's own tz is UTC, so display and all-day math use the **account** tz (`settings.get('timezone')`) instead. | done |
| 2026-09-21 | Existing recurring events (Trash Night, Yard Trash) use **email** reminders only, so nudge won't fire for them until popups are added. | open: user to update events |
| 2026-09-21 | Tested the secret iCal feed as an alternative to OAuth. **Rejected:** a test event with popup and email reminders came through with no VALARMs, and 0 of 23 events on the family calendar had reminders. The feed can't be trusted for reminder data. Proceed with OAuth (with branding and PRIVACY.md filled in). | declined |
| 2026-09-21 | Set the Google OAuth consent screen to "In production", not "Testing". Otherwise refresh tokens expire after 7 days and the Pi fails silently. | open (M0) |
| 2026-09-21 | Read the calendar as the user (OAuth), not with a service account. Reminders are per-user, so a service account would see none. | adopted |
| 2026-09-21 | Poll the API (every 5 min) rather than use push/watch, which needs a public HTTPS endpoint. | adopted |
| 2026-09-21 | Dedupe key `calendar:event:start:minutes` in SQLite. Moved events re-fire correctly and restarts don't double-send. | adopted |
| 2026-09-21 | Put a Notifier interface in front of Discord and Telegram and implement both. Each is about 30 lines. Telegram if phone push reliability matters most, Discord for richer formatting. | adopted: Discord first, Telegram later |
| 2026-09-21 | Add an alert (via the notifier) when Google auth fails, so the service can't die silently. | open (M5) |
| 2026-09-21 | Make sure NTP time sync is on for the Pi (it has no RTC). | open (M4) |
| 2026-09-21 | A daily "today's agenda" digest message would fit well later. | open (idea) |
