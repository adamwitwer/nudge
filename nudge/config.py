"""Load ~/.config/nudge/config.toml."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path

from .gcal import CONFIG_DIR

CONFIG_FILE = CONFIG_DIR / "config.toml"


class ConfigError(RuntimeError):
    pass


@dataclass(frozen=True)
class Config:
    calendars: list[str]
    poll: timedelta
    grace: timedelta
    discord_webhook_url: str | None


def load(path: Path = CONFIG_FILE) -> Config:
    if not path.exists():
        raise ConfigError(f"Missing {path} (see config.example.toml)")
    try:
        raw = tomllib.loads(path.read_text())
    except tomllib.TOMLDecodeError as e:
        raise ConfigError(f"{path}: {e}") from e

    calendars = raw.get("calendars")
    if not calendars or not all(isinstance(c, str) for c in calendars):
        raise ConfigError(f"{path}: `calendars` must be a non-empty list of calendar IDs")

    webhook = raw.get("discord", {}).get("webhook_url")
    if webhook and not webhook.startswith("https://"):
        raise ConfigError(f"{path}: discord.webhook_url doesn't look like a URL")

    return Config(
        calendars=calendars,
        poll=timedelta(minutes=raw.get("poll_minutes", 5)),
        grace=timedelta(minutes=raw.get("grace_minutes", 15)),
        discord_webhook_url=webhook,
    )
