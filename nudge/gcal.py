"""Google Calendar access: OAuth credentials and read-only API calls."""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path

from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

SCOPES = ["https://www.googleapis.com/auth/calendar.readonly"]
CONFIG_DIR = Path(os.environ.get("NUDGE_CONFIG_DIR", "~/.config/nudge")).expanduser()
CLIENT_SECRETS = CONFIG_DIR / "credentials.json"
TOKEN = CONFIG_DIR / "token.json"


class AuthError(RuntimeError):
    pass


def _save(creds: Credentials) -> None:
    TOKEN.parent.mkdir(parents=True, exist_ok=True)
    TOKEN.write_text(creds.to_json())
    TOKEN.chmod(0o600)


def authorize(port: int = 0, open_browser: bool = True) -> Credentials:
    """Run the one-time browser consent flow and save the token."""
    if not CLIENT_SECRETS.exists():
        raise AuthError(f"Missing OAuth client file: {CLIENT_SECRETS}")
    flow = InstalledAppFlow.from_client_secrets_file(str(CLIENT_SECRETS), SCOPES)
    creds = flow.run_local_server(port=port, open_browser=open_browser)
    _save(creds)
    return creds


def load_credentials() -> Credentials:
    """Load the saved token, refreshing it if needed. Never prompts."""
    if not TOKEN.exists():
        raise AuthError("Not authorized yet. Run: python -m nudge auth")
    creds = Credentials.from_authorized_user_file(str(TOKEN), SCOPES)
    if creds.valid:
        return creds
    try:
        creds.refresh(Request())
    except RefreshError as e:
        raise AuthError(f"Google token refresh failed ({e}). Run: python -m nudge auth") from e
    _save(creds)
    return creds


def service(creds: Credentials | None = None):
    return build("calendar", "v3", credentials=creds or load_credentials(), cache_discovery=False)


def _paged(request_fn, **kwargs) -> list[dict]:
    items, token = [], None
    while True:
        resp = request_fn(pageToken=token, **kwargs).execute()
        items.extend(resp.get("items", []))
        token = resp.get("nextPageToken")
        if not token:
            return items


def list_calendars(svc) -> list[dict]:
    return _paged(svc.calendarList().list)


def user_timezone(svc) -> str:
    """The account's time zone setting (Settings > Time zone in GCal).

    Preferred over each calendar's own timeZone, which can be stale
    (e.g. a shared calendar left on UTC).
    """
    return svc.settings().get(setting="timezone").execute()["value"]


def get_calendar(svc, calendar_id: str) -> dict:
    """calendarList entry: includes timeZone and defaultReminders."""
    return svc.calendarList().get(calendarId=calendar_id).execute()


def list_events(svc, calendar_id: str, time_min: datetime, time_max: datetime) -> list[dict]:
    """Event instances in the window, recurring events expanded."""
    return _paged(
        svc.events().list,
        calendarId=calendar_id,
        timeMin=time_min.isoformat(),
        timeMax=time_max.isoformat(),
        singleEvents=True,
        orderBy="startTime",
        maxResults=250,
    )
