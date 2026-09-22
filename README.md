# nudge

A small Raspberry Pi service that reads your Google Calendar **popup**
reminders and sends them to Discord and/or Telegram at the times set in
GCal.

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
   Discord webhook URL and/or Telegram bot token. For Telegram, message your
   bot once, then run `.venv/bin/python -m nudge telegram-chats` to get your
   `chat_id`.
5. `.venv/bin/python -m nudge test` sends a sample message to every
   configured destination.
6. `.venv/bin/python -m nudge upcoming` shows what will fire and when.
7. `.venv/bin/python -m nudge run` runs the service.

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
