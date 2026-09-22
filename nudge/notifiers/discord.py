"""Discord via channel webhook (no bot needed)."""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request

from ..format import Message, as_markdown


class DiscordWebhook:
    name = "discord"
    supports_actions = False  # webhooks can't have buttons; Message.ref is ignored

    def __init__(self, url: str, timeout: float = 10):
        self.url = url
        self.timeout = timeout

    def payload(self, text: str) -> dict:
        # allowed_mentions: never let an event title ping @everyone / roles.
        return {"content": text, "allowed_mentions": {"parse": []}}

    def send(self, message: Message) -> None:
        body = json.dumps(self.payload(as_markdown(message))).encode()
        for attempt in range(3):
            req = urllib.request.Request(
                self.url,
                data=body,
                headers={"Content-Type": "application/json", "User-Agent": "nudge (github.com/adamwitwer/nudge)"},
            )
            try:
                with urllib.request.urlopen(req, timeout=self.timeout):
                    return
            except urllib.error.HTTPError as e:
                if e.code == 429 and attempt < 2:  # rate limited
                    retry_after = json.loads(e.read() or b"{}").get("retry_after", 1)
                    time.sleep(min(float(retry_after), 30))
                    continue
                raise RuntimeError(f"Discord webhook failed: HTTP {e.code}") from None
