"""Notification backends. Each renders a format.Message in its own markup."""

from __future__ import annotations

from typing import Protocol

from ..config import Config
from ..format import Message


class Notifier(Protocol):
    name: str  # stable: part of the store's per-notifier dedupe key

    def send(self, message: Message) -> None: ...


def from_config(cfg: Config) -> list[Notifier]:
    notifiers: list[Notifier] = []
    if cfg.discord_webhook_url:
        from .discord import DiscordWebhook

        notifiers.append(DiscordWebhook(cfg.discord_webhook_url))
    if cfg.telegram_bot_token and cfg.telegram_chat_id:
        from .telegram import TelegramBot

        notifiers.append(TelegramBot(cfg.telegram_bot_token, cfg.telegram_chat_id))
    return notifiers
