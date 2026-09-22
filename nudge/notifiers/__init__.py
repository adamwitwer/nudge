"""Notification backends. Each takes a Markdown-ish text line and delivers it."""

from __future__ import annotations

from typing import Protocol

from ..config import Config


class Notifier(Protocol):
    name: str

    def send(self, text: str) -> None: ...


def from_config(cfg: Config) -> list[Notifier]:
    notifiers: list[Notifier] = []
    if cfg.discord_webhook_url:
        from .discord import DiscordWebhook

        notifiers.append(DiscordWebhook(cfg.discord_webhook_url))
    return notifiers
