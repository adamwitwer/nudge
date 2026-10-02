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

from . import commands, create, format
from .notifiers.telegram import TelegramBot, TelegramError, call
from .runtime import Runtime
from .store import Store

log = logging.getLogger("nudge")

SNOOZES = {"snooze10": timedelta(minutes=10), "snooze60": timedelta(hours=1)}


def listen(bot: TelegramBot, rt: Runtime, seconds: float) -> None:
    """Long-poll Telegram for up to `seconds`, handling taps and messages.

    Used in place of the engine's sleep, so replies come back right away.
    """
    store, tz = rt.store, rt.tz
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
                handle_callback(bot, rt, update["callback_query"], datetime.now(timezone.utc))
            except Exception as e:
                log.warning("button tap failed: %s", e)
        elif "message" in update:
            try:
                commands.dispatch(bot, rt, update["message"])
            except Exception as e:
                log.warning("message handling failed: %s", e)


def handle_callback(bot: TelegramBot, rt: Runtime, cq: dict, now: datetime) -> None:
    store, tz = rt.store, rt.tz
    msg = cq.get("message") or {}
    if str(msg.get("chat", {}).get("id")) != str(bot.chat_id):
        call(bot.token, "answerCallbackQuery", {"callback_query_id": cq["id"]})
        log.warning("ignored button tap from another chat")
        return

    action, _, ref = cq.get("data", "").partition(":")
    if action in create.ACTIONS:
        _handle_create(bot, rt, action, ref, cq, now)
        return
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
        _edit(bot, "editMessageText", {**params, "text": text, "parse_mode": "HTML"})
    else:
        _edit(bot, "editMessageReplyMarkup", params)


def _edit(bot: TelegramBot, method: str, params: dict) -> None:
    """Edit a message, ignoring "message is not modified".

    That 400 means the edit already happened: a second tap from a phone
    whose view hadn't refreshed (seen 2026-10-01). Not a failure.
    """
    try:
        call(bot.token, method, params)
    except TelegramError as e:
        if "message is not modified" not in str(e):
            raise
        log.info("button tap: message already up to date")


def _handle_create(bot: TelegramBot, rt: Runtime, action: str, ref: str, cq: dict, now: datetime) -> None:
    """Preview buttons: Create / swap calendar / Cancel / Undo."""
    message_id = (cq.get("message") or {}).get("message_id")
    if not ref.isdigit():
        toast, message, keyboard = "I don't know that button", None, None
    else:
        try:
            toast, message, keyboard = create.handle(bot, rt, action, int(ref), message_id, now)
        except Exception as e:
            log.warning("%s failed: %s", action, e)
            toast, message, keyboard = f"Couldn't {action} that ({type(e).__name__})", None, None

    call(bot.token, "answerCallbackQuery", {"callback_query_id": cq["id"], "text": toast})
    if message is not None:
        params = {"chat_id": bot.chat_id, "message_id": message_id,
                  "text": format.as_html(message), "parse_mode": "HTML"}
        if keyboard is not None:
            params["reply_markup"] = keyboard
        _edit(bot, "editMessageText", params)


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
