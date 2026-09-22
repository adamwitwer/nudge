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


# Button label -> callback_data prefix. callback_data is "<action>:<ref>".
BUTTONS = [("💤 10 min", "snooze10"), ("💤 1 hour", "snooze60"), ("✅ Done", "done")]


def keyboard(ref: int) -> dict:
    return {"inline_keyboard": [[{"text": label, "callback_data": f"{action}:{ref}"} for label, action in BUTTONS]]}


class TelegramBot:
    name = "telegram"
    supports_actions = True  # renders Message.ref as snooze buttons

    def __init__(self, token: str, chat_id: int | str):
        self.token = token
        self.chat_id = chat_id
        self.update_offset = 0  # getUpdates cursor (see nudge.snooze)

    def payload(self, text: str, ref: int | None = None) -> dict:
        p = {
            "chat_id": self.chat_id,
            "text": text,
            "parse_mode": "HTML",
            "link_preview_options": {"is_disabled": True},
        }
        if ref is not None:
            p["reply_markup"] = keyboard(ref)
        return p

    def send(self, message: Message) -> None:
        params = self.payload(as_html(message), message.ref)
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
    """Chats that have messaged the bot recently (for finding chat_id).

    The running service consumes updates too, and it logs the chat of any
    incoming message, so check `journalctl -u nudge` if this comes back empty.
    """
    chats = {}
    for update in call(token, "getUpdates"):
        chat = (update.get("message") or update.get("my_chat_member") or {}).get("chat")
        if chat:
            chats[chat["id"]] = chat.get("first_name") or chat.get("title") or chat.get("type", "?")
    return chats
