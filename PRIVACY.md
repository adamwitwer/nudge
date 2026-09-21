# Privacy Policy: nudge

_Last updated: 2026-09-21_

nudge is a personal, self-hosted tool. It is not a hosted service, and it has
no users other than the person who runs it.

## What it accesses
- **Google Calendar (read-only).** It reads events and reminder settings from
  the calendars you configure, using the `calendar.readonly` scope. It never
  creates, changes, or deletes anything in your calendar.

## What it stores
- An OAuth token and a small SQLite file recording which reminders have been
  sent. Both stay on the machine you run it on (e.g. your Raspberry Pi).
- Nothing is sent to the developer or to any third-party analytics.

## What it sends
- When a reminder is due, it sends the event title and time to the Discord
  channel and/or Telegram chat **you** configure, and nowhere else.

## Revoking access
Remove access at any time at https://myaccount.google.com/permissions and
delete the local token file.

## Contact
Open an issue at https://github.com/adamwitwer/nudge/issues.
