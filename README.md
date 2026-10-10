# nudge

A small Raspberry Pi service that reads your Google Calendar **popup**
reminders and sends them to Telegram (or Discord, or both) at the times set
in GCal.

```
🗑️ **Trash Night** · in 1 hour
```

The emoji comes from keywords in the title (trash 🗑️, birthday 🎂,
dentist 🦷, ...). You can add your own under `[emoji.keywords]` in the config.

On Telegram, each reminder has **💤 10 min**, **💤 1 hour** and **✅ Done**
buttons. A snoozed reminder comes back (to Telegram only) with fresh wording.
Run `nudge test` on the machine that runs the service, because button taps
are looked up in its local state.

## Setup

1. Google Cloud: enable the Calendar API and create an OAuth client of type
   "Desktop app". Publish the consent screen "In production" so tokens don't
   expire after 7 days. Save the client JSON as
   `~/.config/nudge/credentials.json`.
2. `python3 -m venv .venv && .venv/bin/pip install -e .`
3. `.venv/bin/python -m nudge auth` (one-time browser sign-in)
4. `.venv/bin/python -m nudge calendars`, then copy `config.example.toml`
   to `~/.config/nudge/config.toml` (or the project folder) and fill in calendar IDs and your
   Telegram bot token (and a Discord webhook URL if you want Discord too).
   For Telegram, message your bot once, then run `.venv/bin/python -m nudge telegram-chats` to get your
   `chat_id`.
5. `.venv/bin/python -m nudge test` sends a sample message to every
   configured destination.
6. `.venv/bin/python -m nudge upcoming` shows what will fire and when.
7. `.venv/bin/python -m nudge run` runs the service.

Every morning at 8:30 nudge sends one brief to Telegram: today's events,
followed by any event in the next 14 days with **no popup notification**
(nudge would never fire for those). It sends even on an empty day, so a
missing brief means the service is down. `#nonudge` in an event's description
keeps it out of both parts. `nudge morning` runs it by hand, `nudge audit`
just the notification check.

```
☀️ Sunday, Sep 27
• 8:00 PM · 🗑️ Yard Trash

1 event with no popup notification
• Wed Jan 20 · Adam and Jenny's anniversary (repeats)
```

## Creating events from Telegram

Type an event at the bot and it offers to add it:

```
you:   lunch w/ Sam next tues noon at Joe's, remind me 30 before
nudge: 🍽️ Lunch w/ Sam at Joe's · Tue Oct 6 · 12:00 PM–12:30 PM
       📅 Family · 🔔 popup 30 min
       ℹ️ took "next tues" as Tuesday of next week
       [✅ Create] [📅 Personal] [✖️ Cancel]
```

Claude parses the message (structured output, one call); nothing is written
until you tap **Create**, and **↩️ Undo** deletes it again. Every created event
gets a popup reminder, so nudge fires for what it made.

Commands: `/next`, `/today`, `/help`.

This needs an `[claude]` api_key in the config and the `calendar.events`
scope, so re-run `nudge auth` after upgrading from a read-only install.

## Staying alive

nudge pings a [healthchecks.io](https://healthchecks.io) check after every
successful poll (`[health] ping_url`), so a Pi that loses power is noticed by
something that isn't the Pi. The systemd unit is `Type=notify` with
`WatchdogSec=120`, so a wedged loop gets restarted, not just a crashed one.
`/health` in Telegram reports last poll, uptime and what's enabled.

## One-off nudges and the power-outage watcher

`nudge send "Title" --detail "more"` sends a message that isn't a calendar
event, with the same snooze and Done buttons, so a script can nudge you.
Run it on the machine that runs the service. With `--quiet`, a nudge sent
between 10 PM and the morning brief time waits for the brief time.

`outage/watch.sh` uses it. Brief power outages reset clocks and lamp
timers, but a Pi on a UPS never notices one. A Mac with a UPS on USB does:
the script reads `pmset -g pslog` and, when the Mac switches to UPS power,
runs `nudge send` on the Pi over ssh (one nudge per 30 minutes at most):

```
⚡ **Power outage at 2:14 PM** · reset the clocks, gaming PC, and plant lamp timers
```

The list of things to reset is `DETAIL` at the top of the script.
Install steps are in `outage/nudge.outage-watch.plist`.

## Identity

The avatar is `assets/avatar.svg`: an amber dot with two waves leaving it, on
a deep-indigo disc. Re-render after editing:

```
rsvg-convert -w 512 -h 512 assets/avatar.svg -o assets/avatar-512.png
rsvg-convert -w 120 -h 120 assets/avatar.svg -o assets/avatar-120.png
```

Use `rsvg-convert` (`brew install librsvg`), not ImageMagick: ImageMagick's
built-in SVG renderer silently drops stroked paths and arcs.
512 px is the Telegram bot photo and the Discord webhook avatar; 120 px is
the Google OAuth consent screen.

## Running on a Raspberry Pi

```
cd ~/Projects && git clone git@github.com:adamwitwer/nudge.git && cd nudge
python3 -m venv venv && venv/bin/pip install -e .
# copy config.toml, credentials.json, token.json into this folder (chmod 600)
sudo cp systemd/nudge.service /etc/systemd/system/
sudo systemctl daemon-reload && sudo systemctl enable --now nudge
journalctl -u nudge -f
```

nudge looks for its config and secrets in `$NUDGE_CONFIG_DIR`, then in the
project folder (if `config.toml` is there), then in `~/.config/nudge`. Run
the service on one machine only, or you'll get duplicate messages.

## Notes

Only **popup** notifications trigger nudge. Email notifications are ignored.
Tip: set a default popup notification per calendar in GCal settings, and
nudge will use it.

See [`miniPRD.txt`](miniPRD.txt) for the spec and plan.
