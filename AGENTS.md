# AGENTS.md

Guidance for AI agents (Claude Code and others) working in this repo. This
project is a collaboration: agents are expected to offer opinions, push back,
and suggest improvements, not just execute. Record that input here.

## Project

**nudge** is a small service for a Raspberry Pi. It reads Google Calendar events (from a
configured list of calendars) and sends each event's **popup** reminders as
Telegram messages (Discord is supported but retired) at the times set in GCal. The spec and plan
are in `miniPRD.txt`, which is the source of truth for requirements.

## Where we left off (2026-09-28)

**Live on the Pi** (`nudge.service`), Telegram only. Reminders + snooze +
8:30 AM brief, and now **creating events from Telegram**: type an event at the
bot, Claude parses it, a preview with [✅ Create] [📅 Personal] [✖️ Cancel]
appears, and [↩️ Undo] deletes it again. Verified live 2026-09-28 (created
"Test event" on Family, then undid it). Commands: `/next`, `/today`, `/help`.

**New pieces:** `nudge/commands.py` (router), `nudge/parse.py` (one Claude
call, structured output), `nudge/create.py` (preview/confirm/write/undo, the
only code that writes to Google), `nudge/runtime.py` (Runtime passed to the
Telegram listener), `proposals` table in the store. Scope is now
`calendar.readonly` + `calendar.events`; the token on both Macs and the Pi was
re-issued 2026-09-28.

**Claude setup:** `[claude] api_key` in config.toml, model `claude-opus-5-5`,
~0.5 cent and 2.5-5 s per parse. The user's key is **org-level**, so
`claude.workspace_id` (`wrkspc_...`) is required - without it the API returns
400 "not scoped to a workspace". Without an api_key nudge stays read-only.

**Liveness (2026-09-29):** three layers - healthchecks.io ping after every
successful poll (`[health] ping_url`, `/fail` on a failed poll or auth error),
systemd watchdog (`Type=notify`, `WatchdogSec=120`, sd_notify from
`nudge/health.py`), and `/health` in Telegram. The watchdog was verified by
SIGSTOPping the process: killed and restarted two minutes later.

**Ideas not built yet:** snooze presets tuned to real use ("this evening",
"tomorrow 8am"), location/Meet lines for events that have them, `#emoji:`
overrides in a description, editing or deleting existing events from Telegram
(only Undo today).

## Working agreements

- Keep it simple. This is a personal tool, not a platform. Prefer the stdlib
  and a few dependencies over frameworks.
- **Public repo: never commit secrets.** OAuth client secrets, `token.json`,
  webhook URLs, bot tokens, chat IDs, Anthropic API keys, and real calendar
  IDs stay out of git. Never print config.toml or a key to the terminal
  either (it happened once, 2026-09-28; the key was rotated) - check secrets
  with a boolean, e.g. `print(bool(cfg.claude.api_key))`.
  Never print the Telegram token: it's embedded in API URLs, so keep URLs
  out of errors and logs.
  Commit `config.example.toml` only.
- Target is Python 3.11+ (the Pi has 3.11.2; the dev Mac has 3.14). Don't use
  newer syntax without checking.
- Trigger computation is the risky logic (all-day events, `useDefault`,
  time zones, DST), so it gets unit tests.
- Layout: `nudge/` package, run as `python -m nudge <command>`. Tests are in
  `tests/` (pytest). The architecture as built is in `miniPRD.txt` section 4.
- Deployment: Raspberry Pi 5 (`raspberrypi`: LAN 192.168.50.167, Tailscale
  100.107.81.122; Debian 12, Python 3.11.2). It follows the Pi's conventions:
  a git clone in `~/Projects/nudge` with a `venv/`, secrets beside the code
  (gitignored), and the unit in `systemd/nudge.service` copied to
  `/etc/systemd/system/`. Config lookup: `$NUDGE_CONFIG_DIR`, then the
  project folder if it has `config.toml`, then `~/.config/nudge` (dev Mac).
- Deploy an update: `ssh adam@100.107.81.122 'cd ~/Projects/nudge && git pull
  && venv/bin/pip install -q -e . && sudo systemctl restart nudge'`
- Reach the Pi over **Tailscale** (100.107.81.122) by default. The LAN
  address (.167) only works when the Mac is at home.
- Gotcha (macOS, Python 3.13+): macOS can flag the venv's editable-install
  `.pth` as hidden, and Python then skips it. pytest sets `pythonpath = ["."]`,
  and `python -m nudge` works from the repo root regardless.
- Run `pytest` before every commit.
- After a string-replace edit, verify the change actually landed (grep for it)
  - a missed replace is silent. Unit tests don't import `engine.run`'s
  startup path end to end, so also check `systemctl is-active nudge` and a
  fresh journal line after every deploy.
- When a requirement changes, update `miniPRD.txt` section 3 as well as the
  code.

## Agent input log

Suggestions, concerns, and opinions from agents, with their status. Newest
first. Status is one of: open / adopted / declined / done.

| Date | Input | Status |
|------|-------|--------|
| 2026-09-29 | Dead-man's switch shipped: healthchecks.io heartbeat + systemd watchdog + `/health`. Watchdog proven with SIGSTOP (2 min to restart). | done |
| 2026-09-29 | **Deploy lesson:** a `sed`/replace against an import line silently missed (the line had changed in another session), every unit test still passed, and the service crash-looped on the Pi. `run()` is now covered by a smoke test, and a deploy is not done until `systemctl is-active` plus a fresh log line are checked. | done |
| 2026-09-28 | Event creation from Telegram shipped (Claude parse -> preview -> create -> undo). Gotchas: an org-level Anthropic key needs `anthropic-workspace-id`; the SDK logs every request at INFO (silenced); Telegram `sendChatAction` covers the 2.5-5 s parse. | done |
| 2026-09-28 | **Deploy hazard, hit once:** copying `config.toml` from a Mac to the Pi silently re-enabled Discord (the Mac copy still had the webhook). Diff the two before `scp`, or keep the retired block commented in both. | done (both configs now match) |
| 2026-09-28 | A dead Pi is still invisible: no reminders and no alert. Recommended an external heartbeat (healthchecks.io) as the next piece of work. | open |
| 2026-09-25 | Week-one review of the journal caught two silent crashes that the user hadn't noticed (uncaught socket timeout in the long-poll). Worth re-reading `journalctl -u nudge` for `NRestarts` and WARNING lines whenever the user reports back. | done |
| 2026-09-25 | Discord retired after the trial; Telegram only. Kept the notifier and a commented config block rather than deleting, so it can come back. | adopted |
| 2026-09-22 | Identity: the user picked the "Ping" concept (amber dot + two waves) from four; the disc went deep indigo #231F5E so the circle keeps its edge on dark chat backgrounds. Gotcha: **ImageMagick cannot render stroked paths or SVG arcs** (it drew only the fills), so `rsvg-convert` (brew librsvg) renders the PNGs. Discord webhook PATCH needs a `User-Agent` header or Cloudflare returns 403 code 1010. | done |
| 2026-09-22 | The user's idea: a daily audit for events with no popup. Built at 8:30 AM, Telegram only, 14 days, `#nonudge` opt-out, recurring listed once, email-only flagged. Against real data, the 14-day window is clean; over 365 days, 3 yearly birthday/anniversary events have no popup. | done |
| 2026-09-22 | Before recommending per-calendar default notifications: check what the API returns for an **all-day** event using defaults. Concern was unfounded — **tested 2026-09-25**: GCal materializes the all-day default onto the event as a concrete override (900 min = 1 day before at 9 AM); only timed events come back as `useDefault`. No code change. Caveat recorded: changing the all-day default later does not reach existing all-day events. | done |
| 2026-09-22 | Telegram snooze: the user chose 10 min / 1 hour / Done, with re-sends to Telegram only. The long-poll replaces the tick sleep. Gotchas: (1) only one getUpdates consumer at a time, so running `telegram-chats` on the Mac while the Pi service runs can 409 or miss messages (the service logs incoming chat IDs instead); (2) a `nudge test` sent from the Mac has buttons the Pi doesn't know (they answer "expired"), so run `nudge test` on the Pi. | done |
| 2026-09-22 | Emoji keyword rules: about 20 built-ins, overridable in config, word-start matching (so "Recall" doesn't match "call"). Next up, as agreed with the user: **Telegram snooze buttons**. Trial week of Discord and Telegram runs until about 2026-09-29. | done |
| 2026-09-22 | Telegram notifier added. Messages are now structured (`format.Message`) and rendered per destination (Discord markdown, Telegram HTML). The dedupe key gained a `|notifier` suffix. Existing rows no longer match, which was harmless at deploy time because no trigger was inside the grace window. | done |
| 2026-09-21 | M4: deployed to the Pi as `nudge.service` (enabled, active). Verified `upcoming` and `test` from the Pi. First live check: TEST EVENT FOR CLAUDE popup at 3:50 PM ET on 2026-09-22. Only one machine should run `nudge run`, or you get double sends. | done |
| 2026-09-21 | M2+M3 done: SQLite dedupe store, 30 s tick / 5 min poll loop, Discord webhook (mentions disabled so a title can't ping @everyone), `nudge test` and `nudge run`. The auth-failure alert (from M5) is also in. Sample message delivered to Discord. | done |
| 2026-09-21 | With more than one notifier, a send failure on the second means a retry re-sends on the first. That's fine while Discord is the only notifier. Track per-notifier sent state when Telegram is added. | done (key suffix `|notifier`) |
| 2026-09-21 | M1 verified against the real API: popup and email overrides come back exactly as set in GCal. The Family calendar's own tz is UTC, so display and all-day math use the **account** tz (`settings.get('timezone')`) instead. | done |
| 2026-09-21 | Existing recurring events (Trash Night, Yard Trash) use **email** reminders only, so nudge won't fire for them until popups are added. | done (user added popups 2026-09-22) |
| 2026-09-21 | Tested the secret iCal feed as an alternative to OAuth. **Rejected:** a test event with popup and email reminders came through with no VALARMs, and 0 of 23 events on the family calendar had reminders. The feed can't be trusted for reminder data. Proceed with OAuth (with branding and PRIVACY.md filled in). | declined |
| 2026-09-21 | Set the Google OAuth consent screen to "In production", not "Testing". Otherwise refresh tokens expire after 7 days and the Pi fails silently. | done |
| 2026-09-21 | Read the calendar as the user (OAuth), not with a service account. Reminders are per-user, so a service account would see none. | adopted |
| 2026-09-21 | Poll the API (every 5 min) rather than use push/watch, which needs a public HTTPS endpoint. | adopted |
| 2026-09-21 | Dedupe key `calendar:event:start:minutes` in SQLite. Moved events re-fire correctly and restarts don't double-send. | adopted |
| 2026-09-21 | Put a Notifier interface in front of Discord and Telegram and implement both. Each is about 30 lines. Telegram if phone push reliability matters most, Discord for richer formatting. | adopted: Discord first, Telegram later |
| 2026-09-21 | Add an alert (via the notifier) when Google auth fails, so the service can't die silently. | done (engine.py) |
| 2026-09-21 | Make sure NTP time sync is on for the Pi (it has no RTC). | done (NTPSynchronized=yes) |
| 2026-09-21 | A daily "today's agenda" digest message would fit well later. | open (idea) |
