"""
moderation/commands.py

Обработчики команд модерации: /warn, /unwarn, /ban, /unban, /mute, /unmute,
/stat, /report, /resetspam, /resetviolations.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime

from aiogram import Router
from aiogram.enums import ChatType
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from database.repositories import (
    add_warning, get_warning_count, remove_last_warning,
    increment_stat, log_admin_action, find_user_by_username,
    get_user_stats, add_report, set_report_confirmation_message_id,
)
from moderation.antispam import spam_tracker, message_history
from utils.helpers import parse_time, is_admin, get_target_user, format_time
from moderation.states import ModerationFSM

logger = logging.getLogger(__name__)
router = Router()


# ──────────────────────────── /stat ────────────────────────────

@router.message(Command("stat"))
async def handle_stat(message: Message) -> None:
    from utils.bot_ref import bot  # импорт здесь, чтобы избежать цикла

    if message.chat.type == ChatType.PRIVATE:
        target_user, chat_id = await get_target_user(message, bot)
        if not target_user or not chat_id:
            await message.reply("❌ В ЛС нужно указать пользователя!\nПример: /stat @username")
            return
    else:
        target_user, chat_id = await get_target_user(message, bot)
        if not target_user:
            target_user = message.from_user
            chat_id = message.chat.id

    stats = get_user_stats(target_user.id, chat_id)
    if not stats:
        await message.reply("ℹ️ Пользователь не найден в базе данных.")
        return

    user_name = f"@{stats['username']}" if stats["username"] else stats["first_name"]
    try:
        joined = datetime.fromisoformat(stats["joined_at"])
        joined_str = joined.strftime("%d.%m.%Y %H:%M")
        delta = datetime.now() - joined
        time_in_chat = f"{delta.days} дн." if delta.days > 0 else "сегодня"
    except Exception:
        joined_str = time_in_chat = "неизвестно"

    spam_viol = spam_tracker.get_violations(target_user.id)
    status_emoji = "✅" if stats["verified"] else "⏳"

    text = (
        f"📊 <b>Статистика пользователя</b>\n\n"
        f"👤 {user_name}\n{status_emoji} {'Верифицирован' if stats['verified'] else 'Не верифицирован'}\n\n"
        f"📅 Присоединился: {joined_str} ({time_in_chat})\n\n"
        f"💬 Сообщений: {stats['messages']}\n"
        f"⚠️ Варны: {stats['warns']}/3 | Спам: {spam_viol}/3\n"
        f"🔇 Муты: {stats['mutes']} | 👢 Кики: {stats['kicks']} | 🔨 Баны: {stats['bans']}\n\n"
        f"{'🟢 Чистая репутация' if stats['warns'] == 0 and stats['kicks'] == 0 and stats['bans'] == 0 else '🔴 Есть нарушения'}"
    )
    await message.reply(text, parse_mode="HTML")
    if message.chat.type != ChatType.PRIVATE:
        await asyncio.sleep(5)
        try:
            await message.delete()
        except Exception:
            pass


# ──────────────────────────── /warn ────────────────────────────

@router.message(Command("warn"))
async def handle_warn(message: Message) -> None:
    from utils.bot_ref import bot
    if message.chat.type != ChatType.PRIVATE and not await is_admin(message.chat.id, message.from_user.id, bot):
        return

    target_user, chat_id = await get_target_user(message, bot)
    if not target_user or not chat_id:
        await message.reply("❌ Укажите пользователя!\nПример: /warn @user 30m Причина")
        return
    if target_user.is_bot:
        await message.reply("❌ Нельзя выдать предупреждение боту!")
        return

    args = message.text.split(maxsplit=3)
    offset = 2 if message.reply_to_message else 3
    if len(args) < offset + 1:
        await message.reply("❌ Формат: /warn @user 30m Причина")
        return

    time_str = args[offset - 1]
    reason = args[offset]
    try:
        duration_minutes = parse_time(time_str)
    except ValueError:
        await message.reply("❌ Неверный формат времени! Используй: 5m, 2h, 1d")
        return

    add_warning(target_user.id, chat_id, message.from_user.id, reason, duration_minutes)
    warn_count = get_warning_count(target_user.id, chat_id)
    user_name = f"@{target_user.username}" if target_user.username else target_user.first_name
    time_text = format_time(duration_minutes)

    try:
        if warn_count == 1:
            until = int(datetime.now().timestamp() + duration_minutes * 60)
            await bot.restrict_chat_member(chat_id, target_user.id,
                                           permissions={"can_send_messages": False}, until_date=until)
            increment_stat(target_user.id, chat_id, "mutes")
            await bot.send_message(chat_id, f"⚠️ Предупреждение 1/3 для {user_name}\n📝 {reason}\n⏱ Мут: {time_text}")
        elif warn_count == 2:
            until = int(datetime.now().timestamp() + 86400)
            await bot.restrict_chat_member(chat_id, target_user.id,
                                           permissions={"can_send_messages": False}, until_date=until)
            increment_stat(target_user.id, chat_id, "mutes")
            await bot.send_message(chat_id, f"⚠️ Предупреждение 2/3 для {user_name}\n📝 {reason}\n⏱ Мут: 24 часа ⚠️ Следующий = кик!")
        else:
            await bot.ban_chat_member(chat_id, target_user.id)
            await bot.unban_chat_member(chat_id, target_user.id)
            increment_stat(target_user.id, chat_id, "kicks")
            from database.repositories import remove_user
            remove_user(target_user.id, chat_id)
            await bot.send_message(chat_id, f"🚫 Предупреждение 3/3 для {user_name}\n📝 {reason}\n👋 Кикнут!")

        log_admin_action(chat_id, message.from_user.id, message.from_user.username,
                         f"Варн {warn_count}/3", target_user.id, target_user.username, reason)
        if message.chat.type != ChatType.PRIVATE:
            try:
                await message.delete()
                if message.reply_to_message:
                    await message.reply_to_message.delete()
            except Exception:
                pass
        else:
            await message.reply("✅ Команда выполнена!")
    except Exception as exc:
        await message.reply(f"❌ Ошибка: {exc}")


# ──────────────────────────── /unwarn ────────────────────────────

@router.message(Command("unwarn"))
async def handle_unwarn(message: Message) -> None:
    from utils.bot_ref import bot
    if message.chat.type != ChatType.PRIVATE and not await is_admin(message.chat.id, message.from_user.id, bot):
        return
    target_user, chat_id = await get_target_user(message, bot)
    if not target_user or not chat_id:
        await message.reply("❌ Укажите пользователя!")
        return
    if get_warning_count(target_user.id, chat_id) == 0:
        await message.reply("ℹ️ У пользователя нет предупреждений!")
        return
    remove_last_warning(target_user.id, chat_id)
    new_count = get_warning_count(target_user.id, chat_id)
    user_name = f"@{target_user.username}" if target_user.username else target_user.first_name
    await message.reply(f"✅ Предупреждение снято с {user_name}\n🔢 Осталось: {new_count}/3")
    if message.chat.type != ChatType.PRIVATE:
        try:
            await message.delete()
        except Exception:
            pass


# ──────────────────────────── /ban ────────────────────────────

@router.message(Command("ban"))
async def handle_ban(message: Message) -> None:
    from utils.bot_ref import bot
    if message.chat.type != ChatType.PRIVATE and not await is_admin(message.chat.id, message.from_user.id, bot):
        return
    target_user, chat_id = await get_target_user(message, bot)
    if not target_user or not chat_id:
        await message.reply("❌ Укажите пользователя!\nПример: /ban @username Причина")
        return
    if target_user.is_bot:
        await message.reply("❌ Нельзя забанить бота!")
        return
    args = message.text.split(maxsplit=2)
    reason = args[-1] if len(args) > 1 else "Не указана"
    user_name = f"@{target_user.username}" if target_user.username else target_user.first_name
    admin_name = f"@{message.from_user.username}" if message.from_user.username else message.from_user.first_name
    try:
        await bot.ban_chat_member(chat_id, target_user.id)
        increment_stat(target_user.id, chat_id, "bans")
        from database.repositories import remove_user
        remove_user(target_user.id, chat_id)
        await bot.send_message(chat_id, f"🔨 {user_name} забанен\n📝 {reason}\n👮 {admin_name}")
        log_admin_action(chat_id, message.from_user.id, message.from_user.username, "Бан", target_user.id, target_user.username, reason)
        if message.chat.type != ChatType.PRIVATE:
            try:
                await message.delete()
                if message.reply_to_message:
                    await message.reply_to_message.delete()
            except Exception:
                pass
        else:
            await message.reply("✅ Команда выполнена!")
    except Exception as exc:
        await message.reply(f"❌ Ошибка: {exc}")


# ──────────────────────────── /unban ────────────────────────────

@router.message(Command("unban"))
async def handle_unban(message: Message) -> None:
    from utils.bot_ref import bot
    if message.chat.type != ChatType.PRIVATE and not await is_admin(message.chat.id, message.from_user.id, bot):
        return
    target_user, chat_id = await get_target_user(message, bot)
    if not target_user or not chat_id:
        await message.reply("❌ Укажите пользователя!")
        return
    user_name = f"@{target_user.username}" if target_user.username else target_user.first_name
    try:
        await bot.unban_chat_member(chat_id, target_user.id, only_if_banned=True)
        await message.reply(f"✅ {user_name} разбанен")
        log_admin_action(chat_id, message.from_user.id, message.from_user.username, "Разбан", target_user.id, target_user.username)
        if message.chat.type != ChatType.PRIVATE:
            try:
                await message.delete()
            except Exception:
                pass
    except Exception as exc:
        await message.reply(f"❌ Ошибка: {exc}")


# ──────────────────────────── /mute ────────────────────────────

@router.message(Command("mute"))
async def handle_mute(message: Message) -> None:
    from utils.bot_ref import bot
    if message.chat.type != ChatType.PRIVATE and not await is_admin(message.chat.id, message.from_user.id, bot):
        return
    target_user, chat_id = await get_target_user(message, bot)
    if not target_user or not chat_id:
        await message.reply("❌ Укажите пользователя!\nПример: /mute @user 1h Причина")
        return
    args = message.text.split(maxsplit=3)
    offset = 2 if message.reply_to_message else 3
    if len(args) < offset + 1:
        await message.reply("❌ Формат: /mute @user 1h Причина")
        return
    time_str = args[offset - 1]
    reason = args[offset]
    try:
        duration_minutes = parse_time(time_str)
    except ValueError:
        await message.reply("❌ Неверный формат времени!")
        return
    until = int(datetime.now().timestamp() + duration_minutes * 60)
    user_name = f"@{target_user.username}" if target_user.username else target_user.first_name
    admin_name = f"@{message.from_user.username}" if message.from_user.username else message.from_user.first_name
    time_text = format_time(duration_minutes)
    try:
        await bot.restrict_chat_member(chat_id, target_user.id,
                                       permissions={"can_send_messages": False}, until_date=until)
        increment_stat(target_user.id, chat_id, "mutes")
        await bot.send_message(chat_id, f"🔇 {user_name} заглушен\n📝 {reason}\n⏱ {time_text}\n👮 {admin_name}")
        log_admin_action(chat_id, message.from_user.id, message.from_user.username, f"Мут {time_text}", target_user.id, target_user.username, reason)
        if message.chat.type != ChatType.PRIVATE:
            try:
                await message.delete()
                if message.reply_to_message:
                    await message.reply_to_message.delete()
            except Exception:
                pass
        else:
            await message.reply("✅ Команда выполнена!")
    except Exception as exc:
        await message.reply(f"❌ Ошибка: {exc}")


# ──────────────────────────── /unmute ────────────────────────────

@router.message(Command("unmute"))
async def handle_unmute(message: Message) -> None:
    from utils.bot_ref import bot
    if message.chat.type != ChatType.PRIVATE and not await is_admin(message.chat.id, message.from_user.id, bot):
        return
    target_user, chat_id = await get_target_user(message, bot)
    if not target_user or not chat_id:
        await message.reply("❌ Укажите пользователя!")
        return
    user_name = f"@{target_user.username}" if target_user.username else target_user.first_name
    try:
        await bot.restrict_chat_member(
            chat_id, target_user.id,
            permissions={"can_send_messages": True, "can_send_media_messages": True,
                         "can_send_other_messages": True, "can_add_web_page_previews": True},
        )
        spam_tracker.clear_mute(target_user.id)
        log_admin_action(chat_id, message.from_user.id, message.from_user.username, "Размут", target_user.id, target_user.username)
        await message.reply(f"✅ {user_name} размучен")
        if message.chat.type != ChatType.PRIVATE:
            try:
                await message.delete()
            except Exception:
                pass
    except Exception as exc:
        await message.reply(f"❌ Ошибка: {exc}")


# ──────────────────────────── /resetspam ────────────────────────────

@router.message(Command("resetspam"))
async def handle_reset_spam(message: Message) -> None:
    from utils.bot_ref import bot
    if not await is_admin(message.chat.id, message.from_user.id, bot):
        return
    target_user, chat_id = await get_target_user(message, bot)
    if not target_user or not chat_id:
        await message.reply("❌ Укажите пользователя!")
        return
    from database.repositories import reset_spam_bans
    reset_spam_bans(target_user.id, chat_id)
    user_name = f"@{target_user.username}" if target_user.username else target_user.first_name
    await message.reply(f"✅ Счётчик спам-банов для {user_name} сброшен")


# ──────────────────────────── /resetviolations ────────────────────────────

@router.message(Command("resetviolations"))
async def handle_reset_violations(message: Message) -> None:
    from utils.bot_ref import bot
    if not await is_admin(message.chat.id, message.from_user.id, bot):
        return
    target_user, chat_id = await get_target_user(message, bot)
    if not target_user or not chat_id:
        await message.reply("❌ Укажите пользователя!")
        return
    spam_tracker.reset_violations(target_user.id)
    user_name = f"@{target_user.username}" if target_user.username else target_user.first_name
    await message.reply(f"✅ Спам-нарушения для {user_name} сброшены")


# ──────────────────────────── /report ────────────────────────────

@router.message(Command("report"))
async def handle_report(message: Message) -> None:
    from utils.bot_ref import bot
    if message.chat.type == ChatType.PRIVATE:
        await message.reply("⚠️ Команда /report работает только в группах!")
        return

    chat_id = message.chat.id
    reporter_id = message.from_user.id
    reporter_username = message.from_user.username
    reason = "Нарушение правил чата"
    message_link = None
    reported_id = None
    reported_username = None

    if message.reply_to_message:
        reported_user = message.reply_to_message.from_user
        if reported_user.is_bot:
            await message.reply("❌ Нельзя жаловаться на ботов!")
            try:
                await message.delete()
            except Exception:
                pass
            return
        if reported_user.id == reporter_id:
            await message.reply("❌ Нельзя жаловаться на самого себя!")
            try:
                await message.delete()
            except Exception:
                pass
            return
        if await is_admin(chat_id, reported_user.id, bot):
            await message.reply("❌ Нельзя жаловаться на администраторов!")
            try:
                await message.delete()
            except Exception:
                pass
            return
        args = message.text.split(maxsplit=1)
        reason = args[1] if len(args) > 1 else reason
        message_link = f"https://t.me/c/{str(chat_id)[4:]}/{message.reply_to_message.message_id}"
        reported_id = reported_user.id
        reported_username = reported_user.username
    else:
        args = message.text.split(maxsplit=2)
        if len(args) < 2:
            await message.reply("❌ Неверный формат!\n1. Ответьте на сообщение: /report Причина\n2. Укажите: /report @username Причина")
            return
        username = args[1].lstrip("@")
        reason = args[2] if len(args) > 2 else reason
        user_data = find_user_by_username(username, chat_id)
        if not user_data:
            await message.reply(f"❌ Пользователь @{username} не найден")
            return
        reported_id = user_data["user_id"]
        reported_username = user_data["username"]
        if reported_id == reporter_id:
            await message.reply("❌ Нельзя жаловаться на самого себя!")
            return
        if await is_admin(chat_id, reported_id, bot):
            await message.reply("❌ Нельзя жаловаться на администраторов!")
            return

    reported_name = f"@{reported_username}" if reported_username else f"ID: {reported_id}"
    try:
        report_id = add_report(chat_id, reporter_id, reporter_username,
                               reported_id, reported_username, reason, message_link, None)
    except Exception:
        await message.reply("❌ Не удалось создать жалобу.")
        return

    try:
        conf_msg = await message.reply(
            f"✅ Жалоба #{report_id} отправлена администраторам!\n"
            f"👤 На пользователя: {reported_name}\n📝 Причина: {reason}\n⏳ Ожидайте рассмотрения.",
            parse_mode="HTML",
        )
        set_report_confirmation_message_id(report_id, conf_msg.message_id)
    except Exception as exc:
        logger.error("[report] conf_msg: %s", exc)

    # Уведомляем администраторов
    try:
        admins = await bot.get_chat_administrators(chat_id)
        for admin in admins:
            if admin.user.is_bot:
                continue
            try:
                await bot.send_message(
                    admin.user.id,
                    f"🚨 <b>Новая жалоба #{report_id}</b>\n\n"
                    f"👥 Чат: {message.chat.title}\n"
                    f"👤 На: {reported_name}\n"
                    f"📝 Причина: {reason}\n"
                    f"👮 От: @{reporter_username or 'неизвестно'}\n\n"
                    f"Откройте 📋 Репорты для рассмотрения.",
                    parse_mode="HTML",
                )
            except Exception:
                pass
    except Exception:
        pass

    try:
        await message.delete()
    except Exception:
        pass
