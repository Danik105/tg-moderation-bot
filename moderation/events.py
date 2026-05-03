"""
moderation/events.py

Обработка событий:
- Вход / выход пользователей
- Антиспам в группах
- Сообщения в группах (учёт статистики)
"""
from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime

from aiogram import Router
from aiogram.enums import ChatType
from aiogram.filters import ChatMemberUpdatedFilter, IS_NOT_MEMBER, MEMBER, KICKED, LEFT
from aiogram.types import ChatMemberUpdated, Message

from captcha import CaptchaEntry, active_captchas, generate_captcha, create_captcha_keyboard
from config.settings import settings
from database.repositories import (
    add_user, remove_user, get_chat_settings, log_admin_action,
    increment_stat, increment_message_count,
)
from moderation.antispam import spam_tracker, message_history

logger = logging.getLogger(__name__)
router = Router()

# processing_users: защита от дублей при быстром входе
_processing_users: dict[int, float] = {}


# ──────────────────────────── Вход / выход ────────────────────────────

@router.chat_member(ChatMemberUpdatedFilter(member_status_changed=(IS_NOT_MEMBER >> MEMBER)))
async def on_user_join(event: ChatMemberUpdated) -> None:
    from utils.bot_ref import bot
    user = event.new_chat_member.user
    if user.is_bot:
        return
    await _handle_new_member(bot, user, event.chat.id)


@router.chat_member(ChatMemberUpdatedFilter(member_status_changed=((KICKED | LEFT) << MEMBER)))
async def on_user_leave(event: ChatMemberUpdated) -> None:
    user_id = event.new_chat_member.user.id
    remove_user(user_id, event.chat.id)
    active_captchas.pop(user_id)


@router.my_chat_member()
async def on_bot_added(event: ChatMemberUpdated) -> None:
    if event.new_chat_member.status not in ("member", "administrator"):
        return
    get_chat_settings(event.chat.id)  # создаёт запись если нет
    logger.info("[BOT] Добавлен в чат %d (%s)", event.chat.id, event.chat.title)


async def _handle_new_member(bot, user, chat_id: int) -> None:
    now = time.monotonic()
    if user.id in _processing_users and now - _processing_users[user.id] < settings.processing_timeout:
        return
    _processing_users[user.id] = now

    log_admin_action(chat_id, 0, "system", "Новый участник", user.id, user.username)
    chat_settings = get_chat_settings(chat_id)

    if not chat_settings["captcha_enabled"]:
        add_user(user.id, chat_id, user.username, user.first_name)
        from database.repositories import verify_user
        verify_user(user.id, chat_id)
        _processing_users.pop(user.id, None)
        return

    add_user(user.id, chat_id, user.username, user.first_name)
    try:
        await bot.restrict_chat_member(
            chat_id, user.id,
            permissions={"can_send_messages": False, "can_send_media_messages": False,
                         "can_send_other_messages": False, "can_add_web_page_previews": False},
        )
    except Exception as exc:
        logger.error("[captcha restrict] %s", exc)
        _processing_users.pop(user.id, None)
        return

    question, answer = generate_captcha()
    keyboard = create_captcha_keyboard(answer)
    active_captchas.set(user.id, CaptchaEntry(chat_id=chat_id, answer=answer, message_id=None))

    try:
        msg = await bot.send_message(
            chat_id,
            f"👋 Привет, {user.first_name}!\n\n"
            f"🔐 Реши пример для доступа к чату:\n\n"
            f"❓ {question} = ?\n\n"
            f"⏱ У тебя есть {settings.captcha_timeout} секунд.",
            reply_markup=keyboard,
        )
        entry = active_captchas.get(user.id)
        if entry:
            entry.message_id = msg.message_id

        asyncio.create_task(_captcha_timeout(bot, user.id, chat_id, msg.message_id))
    except Exception as exc:
        logger.error("[captcha send] %s", exc)
    finally:
        await asyncio.sleep(settings.processing_timeout)
        _processing_users.pop(user.id, None)


async def _captcha_timeout(bot, user_id: int, chat_id: int, message_id: int) -> None:
    await asyncio.sleep(settings.captcha_timeout)
    if active_captchas.get(user_id) is None:
        return  # уже решена
    active_captchas.pop(user_id)
    try:
        await bot.ban_chat_member(chat_id, user_id)
        await bot.unban_chat_member(chat_id, user_id)
        await bot.delete_message(chat_id, message_id)
        remove_user(user_id, chat_id)
    except Exception as exc:
        logger.error("[captcha_timeout] %s", exc)


# ──────────────────────────── Группа: капча ────────────────────────────

@router.callback_query(lambda c: c.data and c.data.startswith("captcha_"))
async def process_captcha(callback) -> None:
    from utils.bot_ref import bot
    user_id = callback.from_user.id
    entry = active_captchas.get(user_id)
    if entry is None:
        await callback.answer("❌ Капча уже не активна", show_alert=True)
        return

    parts = callback.data.split("_")
    user_answer = int(parts[1])
    correct_answer = int(parts[2])
    chat_id = entry.chat_id
    message_id = entry.message_id

    if user_answer == correct_answer:
        active_captchas.pop(user_id)
        try:
            await bot.restrict_chat_member(
                chat_id, user_id,
                permissions={"can_send_messages": True, "can_send_media_messages": True,
                             "can_send_other_messages": True, "can_add_web_page_previews": True},
            )
            from database.repositories import verify_user
            verify_user(user_id, chat_id)
            await bot.delete_message(chat_id, message_id)
        except Exception as exc:
            logger.error("[captcha ok] %s", exc)
    else:
        active_captchas.pop(user_id)
        try:
            await bot.ban_chat_member(chat_id, user_id)
            await bot.unban_chat_member(chat_id, user_id)
            await bot.delete_message(chat_id, message_id)
            remove_user(user_id, chat_id)
        except Exception as exc:
            logger.error("[captcha fail] %s", exc)

    await callback.answer()


# ──────────────────────────── Группа: антиспам ────────────────────────────

@router.message(lambda m: m.chat.type in (ChatType.GROUP, ChatType.SUPERGROUP))
async def group_message_handler(message: Message) -> None:
    from utils.bot_ref import bot
    if not message.from_user:
        return

    user_id = message.from_user.id
    chat_id = message.chat.id

    # Учёт статистики сообщений
    increment_message_count(user_id, chat_id)
    if message.text:
        message_history.add(user_id, chat_id, message.message_id, message.text)

    # Антиспам
    is_spamming = spam_tracker.record_message(user_id)
    if not is_spamming:
        return

    violations = spam_tracker.increment_violations(user_id)
    now = time.time()

    try:
        await message.delete()
    except Exception:
        pass

    user_name = f"@{message.from_user.username}" if message.from_user.username else message.from_user.first_name

    if violations == 1:
        duration = 3600
        until = int(now + duration)
        await bot.restrict_chat_member(chat_id, user_id, permissions={"can_send_messages": False}, until_date=until)
        spam_tracker.set_mute(user_id, duration)
        increment_stat(user_id, chat_id, "mutes")
        await bot.send_message(chat_id, f"⚠️ {user_name} получил мут на 1 час за спам!\n🔢 Нарушение: {violations}/3")
    elif violations == 2:
        duration = 86400
        until = int(now + duration)
        await bot.restrict_chat_member(chat_id, user_id, permissions={"can_send_messages": False}, until_date=until)
        spam_tracker.set_mute(user_id, duration)
        increment_stat(user_id, chat_id, "mutes")
        await bot.send_message(chat_id, f"⚠️ {user_name} получил мут на 24 часа за спам!\n🔢 Нарушение: {violations}/3")
    elif violations >= 3:
        from database.repositories import get_spam_ban_count, increment_spam_ban
        ban_count = get_spam_ban_count(user_id, chat_id)
        new_ban_count = increment_spam_ban(user_id, chat_id)
        ban_days = 7 * (2 ** ban_count)
        until = int(now + ban_days * 86400)
        await bot.ban_chat_member(chat_id, user_id, until_date=until)
        increment_stat(user_id, chat_id, "bans")
        remove_user(user_id, chat_id)
        spam_tracker.remove(user_id)
        await bot.send_message(chat_id, f"🔨 {user_name} забанен на {ban_days} дней за спам!\n📊 Бан #{new_ban_count}")


async def cleanup_spam_tracker_loop() -> None:
    """Периодическая очистка spam_tracker (каждые 5 минут)."""
    while True:
        await asyncio.sleep(300)
        spam_tracker.cleanup_expired()
