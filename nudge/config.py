"""Load ~/.config/nudge/config.toml."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from datetime import datetime, time, timedelta
from pathlib import Path

from .format import DEFAULT_KEYWORDS, EMOJI, EmojiRules
from .gcal import CONFIG_DIR

CONFIG_FILE = CONFIG_DIR / "config.toml"


class ConfigError(RuntimeError):
    pass


@dataclass(frozen=True)
class MorningConfig:
    """The once-a-day brief: today's agenda plus the missing-popup audit."""

    enabled: bool = True
    at: time = time(8, 30)
    agenda: bool = True  # list today's events (and say so on an empty day)
    days: int = 14  # audit look-ahead
    via: tuple[str, ...] = ("telegram",)  # notifier names
    tag: str = "#nonudge"  # put this in an event's description to skip it


@dataclass(frozen=True)
class Config:
    calendars: list[str]
    poll: timedelta
    grace: timedelta
    discord_webhook_url: str | None
    telegram_bot_token: str | None = None
    telegram_chat_id: int | str | None = None
    emoji: EmojiRules = field(default_factory=EmojiRules)
    morning: MorningConfig = field(default_factory=lambda: MorningConfig())


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

    telegram = raw.get("telegram", {})
    token = telegram.get("bot_token")
    if token and ":" not in token:
        raise ConfigError(f"{path}: telegram.bot_token doesn't look like a bot token")
    chat_id = telegram.get("chat_id")

    emoji_cfg = raw.get("emoji", {})
    user_keywords = {k.lower(): v for k, v in emoji_cfg.get("keywords", {}).items()}
    if not all(isinstance(v, str) and v for v in user_keywords.values()):
        raise ConfigError(f"{path}: emoji.keywords values must be non-empty strings")
    builtin = DEFAULT_KEYWORDS if emoji_cfg.get("builtin", True) else {}
    emoji = EmojiRules(
        keywords={**user_keywords, **{k: v for k, v in builtin.items() if k not in user_keywords}},
        default=emoji_cfg.get("default", EMOJI),
    )

    m = raw.get("morning", raw.get("audit", {}))  # [audit] was the old name
    try:
        at = datetime.strptime(m.get("time", "08:30"), "%H:%M").time()
    except ValueError:
        raise ConfigError(f"{path}: morning.time must be HH:MM (24-hour)") from None
    morning = MorningConfig(
        enabled=m.get("enabled", True),
        at=at,
        agenda=m.get("agenda", True),
        days=int(m.get("days", 14)),
        via=tuple(m.get("via", ["telegram"])),
        tag=m.get("tag", "#nonudge"),
    )

    return Config(
        calendars=calendars,
        poll=timedelta(minutes=raw.get("poll_minutes", 5)),
        grace=timedelta(minutes=raw.get("grace_minutes", 15)),
        discord_webhook_url=webhook,
        telegram_bot_token=token,
        telegram_chat_id=chat_id,
        emoji=emoji,
        morning=morning,
    )
