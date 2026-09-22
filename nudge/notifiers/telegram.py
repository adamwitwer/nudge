"""Telegram via a bot (@BotFather) messaging one chat."""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request

from ..format import Message, as_html

API = "https://api.telegram.org/bot{token}/{method}"


class TelegramError(RuntimeError):
    pass


def call(token: str, method: str, params: dict | None = None, timeout: float = 10) -> dict:
    """POST a Bot API method. Errors never include the URL (it holds the token)."""
    req = urllib.request.Request(
        API.format(token=token, method=method),
        data=json.dumps(params or {}).encode(),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.load(resp)["result"]
    except urllib.error.HTTPError as e:
        body = json.loads(e.read() or b"{}")
        err = TelegramError(f"Telegram {method} failed: HTTP {e.code} {body.get('description', '')}".strip())
        err.retry_after = body.get("parameters", {}).get("retry_after")
        raise err from None
    except urllib.error.URLError as e:
        raise TelegramError(f"Telegram {method} failed: {e.reason}") from None


class TelegramBot:
    name = "telegram"

    def __init__(self, token: str, chat_id: int | str):
        self.token = token
        self.chat_id = chat_id

    def payload(self, text: str) -> dict:
        return {
            "chat_id": self.chat_id,
            "text": text,
            "parse_mode": "HTML",
            "link_preview_options": {"is_disabled": True},
        }

    def send(self, message: Message) -> None:
        params = self.payload(as_html(message))
        for attempt in range(3):
            try:
                call(self.token, "sendMessage", params)
                return
            except TelegramError as e:
                if e.retry_after and attempt < 2:  # rate limited
                    time.sleep(min(float(e.retry_after), 30))
                    continue
                raise


def recent_chats(token: str) -> dict[int, str]:
    """Chats that have messaged the bot recently (for finding chat_id)."""
    chats = {}
    for update in call(token, "getUpdates"):
        chat = (update.get("message") or update.get("my_chat_member") or {}).get("chat")
        if chat:
            chats[chat["id"]] = chat.get("first_name") or chat.get("title") or chat.get("type", "?")
    return chats
