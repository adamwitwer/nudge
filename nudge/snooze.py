"""Telegram snooze buttons: handle taps and re-send snoozed reminders.

Every reminder sent to Telegram carries buttons whose callback_data is
"<action>:<ref>", where ref is a `reminders` row id in the store.

- snooze10 / snooze60: set snooze_until, edit the message to say so, and
  remove the buttons. When snooze_until passes, the reminder is re-sent to
  Telegram only, with fresh wording and new buttons.
- done: remove the buttons.

Taps are only accepted from the configured chat.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from . import format
from .notifiers.telegram import TelegramBot, TelegramError, call
from .store import Store

log = logging.getLogger("nudge")

SNOOZES = {"snooze10": timedelta(minutes=10), "snooze60": timedelta(hours=1)}


def listen(bot: TelegramBot, store: Store, tz: ZoneInfo, seconds: float) -> None:
    """Long-poll Telegram for up to `seconds`, handling button taps.

    Used in place of the engine's sleep, so taps get answered right away.
    """
    try:
        updates = call(
            bot.token,
            "getUpdates",
            {"offset": bot.update_offset, "timeout": int(seconds), "allowed_updates": ["message", "callback_query"]},
            timeout=seconds + 10,
        )
    except TelegramError as e:
        log.warning("%s", e)
        time.sleep(seconds)
        return
    for update in updates:
        bot.update_offset = update["update_id"] + 1
        if "callback_query" in update:
            try:
                handle_callback(bot, store, update["callback_query"], datetime.now(timezone.utc), tz)
            except Exception as e:
                log.warning("button tap failed: %s", e)
        elif "message" in update:
            chat = update["message"].get("chat", {})
            log.info("telegram message from chat_id=%s (%s)", chat.get("id"), chat.get("first_name") or chat.get("title"))


def handle_callback(bot: TelegramBot, store: Store, cq: dict, now: datetime, tz: ZoneInfo) -> None:
    msg = cq.get("message") or {}
    if str(msg.get("chat", {}).get("id")) != str(bot.chat_id):
        call(bot.token, "answerCallbackQuery", {"callback_query_id": cq["id"]})
        log.warning("ignored button tap from another chat")
        return

    action, _, ref = cq.get("data", "").partition(":")
    reminder = store.get_reminder(int(ref)) if ref.isdigit() else None
    if reminder is None or (action not in SNOOZES and action != "done"):
        toast, note = "This reminder has expired", None
    elif action == "done":
        store.set_snooze(reminder.id, None)
        toast, note = "Done", "✅ <i>Done</i>"
    else:
        until = now + SNOOZES[action]
        store.set_snooze(reminder.id, until)
        when = format.clock(until.astimezone(tz))
        toast, note = f"Snoozed until {when}", f"💤 <i>Snoozed until {when}</i>"
        log.info("snoozed %r until %s", reminder.message.title, when)

    # Answer first: Telegram shows a spinner on the button until we do.
    call(bot.token, "answerCallbackQuery", {"callback_query_id": cq["id"], "text": toast})
    text = format.as_html(reminder.message) + (f"\n{note}" if note else "") if reminder else None
    params = {"chat_id": bot.chat_id, "message_id": msg.get("message_id")}
    if text:  # editing the text without reply_markup also removes the buttons
        call(bot.token, "editMessageText", {**params, "text": text, "parse_mode": "HTML"})
    else:
        call(bot.token, "editMessageReplyMarkup", params)


def fire_due(bots: list[TelegramBot], store: Store, now: datetime, tz: ZoneInfo) -> None:
    """Re-send reminders whose snooze has run out (Telegram only)."""
    for r in store.due_snoozes(now):
        msg = format.Message(
            r.message.title,
            format.lead_text(r.start, r.all_day, now, tz),
            emoji=r.message.emoji,
            ref=r.id,
        )
        try:
            for bot in bots:
                bot.send(msg)
        except Exception as e:  # keep snooze_until; retried next tick
            log.warning("snoozed re-send failed for %r: %s", msg.title, e)
            continue
        store.update_message(r.id, msg)
        store.set_snooze(r.id, None)
        log.info("re-sent snoozed %r", msg.title)
