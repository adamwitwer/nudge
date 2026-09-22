# nudge

A small Raspberry Pi service that reads your Google Calendar **popup**
reminders and sends them to Discord (Telegram planned) at the times set in
GCal.

```
⏰ **Trash Night** · in 1 hour
```

## Setup

1. Google Cloud: enable the Calendar API and create an OAuth client of type
   "Desktop app". Publish the consent screen "In production" so tokens don't
   expire after 7 days. Save the client JSON as
   `~/.config/nudge/credentials.json`.
2. `python3 -m venv .venv && .venv/bin/pip install -e .`
3. `.venv/bin/python -m nudge auth` (one-time browser sign-in)
4. `.venv/bin/python -m nudge calendars`, then copy `config.example.toml`
   to `~/.config/nudge/config.toml` and fill in calendar IDs and your
   Discord webhook URL.
5. `.venv/bin/python -m nudge test` sends a sample message.
6. `.venv/bin/python -m nudge upcoming` shows what will fire and when.
7. `.venv/bin/python -m nudge run` runs the service.

Only **popup** notifications trigger nudge. Email notifications are ignored.

See [`miniPRD.txt`](miniPRD.txt) for the spec and plan.
