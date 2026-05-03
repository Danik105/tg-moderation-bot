"""
menu/moderation_handlers.py

Callback-обработчики раздела «Модерация»:
настройки чата, логи, безопасный режим, пользователи, репорты.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup,
)

from database.repositories import (
    get_chat_settings, update_chat_setting, log_admin_action, get_admin_logs,
    get_users_in_chat, get_user_stats, get_pending_reports, get_report_by_id,
    resolve_report, get_top_reporters, get_top_reported,
    increment_stat, remove_user,
)
from menu.keyboards import (
    moderation_menu, settings_keyboard, safe_mode_keyboard,
    reports_keyboard, report_action_keyboard, back_button,
)
from moderation.states import ModerationFSM
from utils.helpers import is_admin, get_admin_chats

logger = logging.getLogger(__name__)
router = Router()


# ──────────────────────────── Настройки ────────────────────────────

@router.callback_query(F.data == "mod_settings")
async def cb_mod_settings(query: CallbackQuery) -> None:
    from utils.bot_ref import bot
    user_chats = await get_admin_chats(query.from_user.id, bot)
    if not user_chats:
        await query.message.answer("❌ Вы не администратор ни в одной группе!", reply_markup=_back_to_mod())
        await query.answer()
        return
    if len(user_chats) == 1:
        await _show_chat_settings(query, user_chats[0])
    else:
        buttons = []
        for chat_id in user_chats:
            try:
                from utils.bot_ref import bot
                chat = await bot.get_chat(chat_id)
                buttons.append([InlineKeyboardButton(text=chat.title, callback_data=f"settings_chat_{chat_id}")])
            except Exception:
                pass
        buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="section_moderation")])
        await query.message.answer("⚙️ <b>Выберите группу:</b>", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons), parse_mode="HTML")
    await query.answer()


@router.callback_query(F.data.startswith("settings_chat_"))
async def cb_settings_chat(query: CallbackQuery) -> None:
    chat_id = int(query.data.split("_")[2])
    await _show_chat_settings(query, chat_id)
    await query.answer()


async def _show_chat_settings(query: CallbackQuery, chat_id: int) -> None:
    from utils.bot_ref import bot
    try:
        chat = await bot.get_chat(chat_id)
        settings = get_chat_settings(chat_id)
        try:
            await query.message.edit_text(
                f"⚙️ <b>Настройки для группы:</b>\n{chat.title}",
                reply_markup=settings_keyboard(chat_id, bool(settings["captcha_enabled"])),
                parse_mode="HTML",
            )
        except Exception:
            await query.message.answer(
                f"⚙️ <b>Настройки для группы:</b>\n{chat.title}",
                reply_markup=settings_keyboard(chat_id, bool(settings["captcha_enabled"])),
                parse_mode="HTML",
            )
    except Exception:
        await query.answer("❌ Ошибка", show_alert=True)


@router.callback_query(F.data.startswith("toggle_captcha_"))
async def cb_toggle_captcha(query: CallbackQuery) -> None:
    from utils.bot_ref import bot
    chat_id = int(query.data.split("_")[2])
    if not await is_admin(chat_id, query.from_user.id, bot):
        await query.answer("❌ Вы не администратор", show_alert=True)
        return
    settings = get_chat_settings(chat_id)
    new_value = 0 if settings["captcha_enabled"] else 1
    update_chat_setting(chat_id, "captcha_enabled", new_value)
    action = "Включил капчу" if new_value else "Выключил капчу"
    log_admin_action(chat_id, query.from_user.id, query.from_user.username, action)
    await _show_chat_settings(query, chat_id)
    status = "включена ✅" if new_value else "выключена ❌"
    await query.answer(f"Капча {status}", show_alert=True)


# ──────────────────────────── Логи ────────────────────────────

@router.callback_query(F.data == "mod_logs")
async def cb_mod_logs(query: CallbackQuery) -> None:
    from utils.bot_ref import bot
    user_chats = await get_admin_chats(query.from_user.id, bot)
    if not user_chats:
        await query.message.answer("❌ Вы не администратор ни в одной группе!", reply_markup=_back_to_mod())
        await query.answer()
        return
    if len(user_chats) == 1:
        await _show_logs(query.message, user_chats[0])
    else:
        buttons = [
            [InlineKeyboardButton(text=(await _safe_chat_title(bot, c)), callback_data=f"logs_chat_{c}")]
            for c in user_chats
        ]
        buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="section_moderation")])
        await query.message.answer("📊 <b>Выберите группу:</b>", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons), parse_mode="HTML")
    await query.answer()


@router.callback_query(F.data.startswith("logs_chat_"))
async def cb_logs_chat(query: CallbackQuery) -> None:
    chat_id = int(query.data.split("_")[2])
    await _show_logs(query.message, chat_id)
    await query.answer()


async def _show_logs(message, chat_id: int) -> None:
    logs = get_admin_logs(chat_id, limit=20)
    if not logs:
        await message.answer("📋 Логи пусты.", reply_markup=_back_to_mod())
        return
    text = "📊 <b>Последние действия:</b>\n\n"
    for row in logs:
        try:
            ts = datetime.fromisoformat(row["timestamp"]).strftime("%d.%m %H:%M")
        except Exception:
            ts = "?"
        admin = f"@{row['admin_username']}" if row["admin_username"] else "system"
        target = f"@{row['target_username']}" if row["target_username"] else ""
        reason = f" — {row['reason']}" if row["reason"] else ""
        text += f"[{ts}] {admin}: {row['action']} {target}{reason}\n"
    await message.answer(text, parse_mode="HTML", reply_markup=_back_to_mod())


# ──────────────────────────── Безопасный режим ────────────────────────────

@router.callback_query(F.data == "mod_safe_mode")
async def cb_mod_safe_mode(query: CallbackQuery) -> None:
    from utils.bot_ref import bot
    user_chats = await get_admin_chats(query.from_user.id, bot)
    if not user_chats:
        await query.message.answer("❌ Нет прав.", reply_markup=_back_to_mod())
        await query.answer()
        return
    if len(user_chats) == 1:
        await _show_safe_mode(query, user_chats[0])
    else:
        buttons = []
        for chat_id in user_chats:
            settings = get_chat_settings(chat_id)
            icon = "🔒" if settings["safe_mode"] else "🔓"
            title = await _safe_chat_title(bot, chat_id)
            buttons.append([InlineKeyboardButton(text=f"{icon} {title}", callback_data=f"safe_mode_chat_{chat_id}")])
        buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="section_moderation")])
        await query.message.answer("🆘 <b>Выберите группу:</b>", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons), parse_mode="HTML")
    await query.answer()


@router.callback_query(F.data.startswith("safe_mode_chat_"))
async def cb_safe_mode_chat(query: CallbackQuery) -> None:
    chat_id = int(query.data.split("_")[3])
    await _show_safe_mode(query, chat_id)
    await query.answer()


async def _show_safe_mode(query: CallbackQuery, chat_id: int) -> None:
    from utils.bot_ref import bot
    settings = get_chat_settings(chat_id)
    status = "🔒 ВКЛЮЧЕН" if settings["safe_mode"] else "🔓 Выключен"
    title = await _safe_chat_title(bot, chat_id)
    text = (
        f"🆘 <b>Безопасный режим</b>\n\nГруппа: {title}\nСтатус: {status}\n\n"
        f"ℹ️ В безопасном режиме все участники (кроме администраторов) не могут писать."
    )
    try:
        await query.message.edit_text(text, reply_markup=safe_mode_keyboard(chat_id), parse_mode="HTML")
    except Exception:
        await query.message.answer(text, reply_markup=safe_mode_keyboard(chat_id), parse_mode="HTML")


@router.callback_query(F.data.startswith("safe_mode_on_"))
async def cb_safe_mode_on(query: CallbackQuery) -> None:
    from utils.bot_ref import bot
    chat_id = int(query.data.split("_")[3])
    if not await is_admin(chat_id, query.from_user.id, bot):
        await query.answer("❌ Вы не администратор", show_alert=True)
        return
    update_chat_setting(chat_id, "safe_mode", 1)
    users = get_users_in_chat(chat_id)
    muted = 0
    for user_id in users:
        if not await is_admin(chat_id, user_id, bot):
            try:
                await bot.restrict_chat_member(chat_id, user_id, permissions={"can_send_messages": False})
                muted += 1
            except Exception:
                pass
    admin_name = f"@{query.from_user.username}" if query.from_user.username else query.from_user.first_name
    await bot.send_message(
        chat_id,
        f"🔒 <b>БЕЗОПАСНЫЙ РЕЖИМ АКТИВИРОВАН</b>\nЗамучено: {muted}\nАктивировал: {admin_name}",
        parse_mode="HTML",
    )
    log_admin_action(chat_id, query.from_user.id, query.from_user.username, f"Включил безопасный режим (замучено: {muted})")
    await _show_safe_mode(query, chat_id)
    await query.answer(f"✅ Безопасный режим включён! Замучено: {muted}", show_alert=True)


@router.callback_query(F.data.startswith("safe_mode_off_"))
async def cb_safe_mode_off(query: CallbackQuery) -> None:
    from utils.bot_ref import bot
    chat_id = int(query.data.split("_")[3])
    if not await is_admin(chat_id, query.from_user.id, bot):
        await query.answer("❌ Вы не администратор", show_alert=True)
        return
    update_chat_setting(chat_id, "safe_mode", 0)
    users = get_users_in_chat(chat_id)
    unmuted = 0
    for user_id in users:
        try:
            await bot.restrict_chat_member(
                chat_id, user_id,
                permissions={"can_send_messages": True, "can_send_media_messages": True,
                             "can_send_other_messages": True, "can_add_web_page_previews": True},
            )
            unmuted += 1
        except Exception:
            pass
    admin_name = f"@{query.from_user.username}" if query.from_user.username else query.from_user.first_name
    await bot.send_message(
        chat_id,
        f"🔓 <b>БЕЗОПАСНЫЙ РЕЖИМ ОТКЛЮЧЁН</b>\nРазмучено: {unmuted}\nОтключил: {admin_name}",
        parse_mode="HTML",
    )
    log_admin_action(chat_id, query.from_user.id, query.from_user.username, f"Выключил безопасный режим (размучено: {unmuted})")
    await _show_safe_mode(query, chat_id)
    await query.answer(f"✅ Безопасный режим выключен! Размучено: {unmuted}", show_alert=True)


# ──────────────────────────── Команды ────────────────────────────

@router.callback_query(F.data == "mod_commands")
async def cb_mod_commands(query: CallbackQuery) -> None:
    text = """🛡️ <b>Команды модерации</b>

<b>📊 Для всех:</b>
/stat @username — статистика пользователя
/report — жалоба на пользователя

<b>⚙️ Только для администраторов:</b>
⚠️ /warn @user 30m Причина
   • 1-й варн → мут, 2-й → мут 24ч, 3-й → кик
🔓 /unwarn @user — снять предупреждение
🔇 /mute @user 1h Причина — мут
🔊 /unmute @user — размут
🔨 /ban @user Причина — бан
🔓 /unban @user — разбан
🔄 /resetspam @user — сброс спам-банов
🔄 /resetviolations @user — сброс нарушений

⏱ <b>Форматы:</b> 5m, 2h, 1d"""
    try:
        await query.message.edit_text(text, reply_markup=_back_to_mod(), parse_mode="HTML")
    except Exception:
        await query.message.answer(text, reply_markup=_back_to_mod(), parse_mode="HTML")
    await query.answer()


# ──────────────────────────── Пользователи ────────────────────────────

@router.callback_query(F.data == "mod_users")
async def cb_mod_users(query: CallbackQuery, state: FSMContext) -> None:
    from utils.bot_ref import bot
    user_chats = await get_admin_chats(query.from_user.id, bot)
    if not user_chats:
        await query.message.answer("❌ Вы не администратор ни в одной группе!", reply_markup=_back_to_mod())
        await query.answer()
        return
    if len(user_chats) == 1:
        await state.update_data(selected_chat_id=user_chats[0])
        await _show_users_list(query.message, user_chats[0], state)
    else:
        buttons = []
        for chat_id in user_chats:
            title = await _safe_chat_title(bot, chat_id)
            buttons.append([InlineKeyboardButton(text=title, callback_data=f"users_chat_{chat_id}")])
        buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="section_moderation")])
        await query.message.answer("👥 <b>Выберите группу:</b>", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons), parse_mode="HTML")
    await query.answer()


@router.callback_query(F.data.startswith("users_chat_"))
async def cb_users_chat(query: CallbackQuery, state: FSMContext) -> None:
    chat_id = int(query.data.split("_")[2])
    await state.update_data(selected_chat_id=chat_id)
    await _show_users_list(query.message, chat_id, state)
    await query.answer()


async def _show_users_list(message, chat_id: int, state: FSMContext) -> None:
    from utils.bot_ref import bot
    from database.connection import db
    with db.connection() as conn:
        rows = conn.execute(
            "SELECT user_id, username, first_name FROM users WHERE chat_id = ? ORDER BY joined_at DESC LIMIT 50",
            (chat_id,),
        ).fetchall()
    if not rows:
        await message.answer("👥 Список пользователей пуст.", reply_markup=_back_to_mod())
        return
    buttons = []
    for row in rows:
        label = f"@{row['username']}" if row["username"] else row["first_name"]
        buttons.append([InlineKeyboardButton(text=label, callback_data=f"view_user_{row['user_id']}_{chat_id}")])
    buttons.append([InlineKeyboardButton(text="🔍 Поиск", callback_data=f"search_user_{chat_id}")])
    buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="section_moderation")])
    try:
        await message.edit_text("👥 <b>Пользователи:</b>", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons), parse_mode="HTML")
    except Exception:
        await message.answer("👥 <b>Пользователи:</b>", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons), parse_mode="HTML")


@router.callback_query(F.data.startswith("view_user_"))
async def cb_view_user(query: CallbackQuery) -> None:
    parts = query.data.split("_")
    user_id = int(parts[2])
    chat_id = int(parts[3])
    stats = get_user_stats(user_id, chat_id)
    if not stats:
        await query.answer("❌ Пользователь не найден", show_alert=True)
        return
    user_name = f"@{stats['username']}" if stats["username"] else stats["first_name"]
    try:
        joined = datetime.fromisoformat(stats["joined_at"]).strftime("%d.%m.%Y %H:%M")
    except Exception:
        joined = "?"
    text = (
        f"👤 <b>{user_name}</b>\n\n"
        f"📅 Вступил: {joined}\n"
        f"✅ Верифицирован: {'Да' if stats['verified'] else 'Нет'}\n\n"
        f"⚠️ Варны: {stats['warns']}/3\n"
        f"🔇 Муты: {stats['mutes']} | 👢 Кики: {stats['kicks']} | 🔨 Баны: {stats['bans']}\n"
        f"💬 Сообщений: {stats['messages']}"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="⚠️ Варн", callback_data=f"action_warn_{user_id}_{chat_id}"),
            InlineKeyboardButton(text="🔇 Мут", callback_data=f"action_mute_{user_id}_{chat_id}"),
        ],
        [
            InlineKeyboardButton(text="🔨 Бан", callback_data=f"action_ban_{user_id}_{chat_id}"),
            InlineKeyboardButton(text="👢 Кик", callback_data=f"action_kick_{user_id}_{chat_id}"),
        ],
        [
            InlineKeyboardButton(text="✅ Снять варн", callback_data=f"action_unwarn_{user_id}_{chat_id}"),
            InlineKeyboardButton(text="🔊 Размут", callback_data=f"action_unmute_{user_id}_{chat_id}"),
        ],
        [InlineKeyboardButton(text="◀️ Назад", callback_data=f"back_to_users_{chat_id}")],
    ])
    try:
        await query.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    except Exception:
        await query.message.answer(text, reply_markup=kb, parse_mode="HTML")
    await query.answer()


@router.callback_query(F.data.startswith("back_to_users_"))
async def cb_back_to_users(query: CallbackQuery, state: FSMContext) -> None:
    chat_id = int(query.data.split("_")[3])
    await _show_users_list(query.message, chat_id, state)
    await query.answer()


@router.callback_query(F.data.startswith("search_user_"))
async def cb_search_user(query: CallbackQuery, state: FSMContext) -> None:
    chat_id = int(query.data.split("_")[2])
    await state.update_data(selected_chat_id=chat_id)
    await state.set_state(ModerationFSM.waiting_for_username)
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="❌ Отмена", callback_data=f"back_to_users_{chat_id}")]])
    await query.message.edit_text("🔍 <b>Поиск пользователя</b>\n\nВведите @username:", reply_markup=kb, parse_mode="HTML")
    await query.answer()


@router.message(ModerationFSM.waiting_for_username)
async def fsm_search_user(message, state: FSMContext) -> None:
    from database.repositories import find_user_by_username
    data = await state.get_data()
    chat_id = data.get("selected_chat_id")
    username = (message.text or "").strip().lstrip("@")
    user_data = find_user_by_username(username, chat_id)
    if user_data:
        await state.clear()
        # Имитируем callback для просмотра
        from aiogram.types import CallbackQuery as CQ
        # Просто показываем статистику напрямую
        stats = get_user_stats(user_data["user_id"], chat_id)
        if stats:
            user_name = f"@{stats['username']}" if stats["username"] else stats["first_name"]
            text = (
                f"👤 <b>{user_name}</b>\n\n"
                f"⚠️ Варны: {stats['warns']}/3\n"
                f"🔇 Муты: {stats['mutes']} | 👢 Кики: {stats['kicks']} | 🔨 Баны: {stats['bans']}\n"
                f"💬 Сообщений: {stats['messages']}"
            )
            uid = user_data["user_id"]
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [
                    InlineKeyboardButton(text="⚠️ Варн", callback_data=f"action_warn_{uid}_{chat_id}"),
                    InlineKeyboardButton(text="🔇 Мут", callback_data=f"action_mute_{uid}_{chat_id}"),
                ],
                [
                    InlineKeyboardButton(text="🔨 Бан", callback_data=f"action_ban_{uid}_{chat_id}"),
                    InlineKeyboardButton(text="👢 Кик", callback_data=f"action_kick_{uid}_{chat_id}"),
                ],
                [InlineKeyboardButton(text="◀️ Назад", callback_data=f"back_to_users_{chat_id}")],
            ])
            await message.answer(text, reply_markup=kb, parse_mode="HTML")
        else:
            await message.answer("❌ Пользователь не найден в базе.", reply_markup=back_button(f"back_to_users_{chat_id}"))
    else:
        await message.answer(f"❌ @{username} не найден в базе.", reply_markup=back_button(f"back_to_users_{chat_id}"))
        await state.clear()


# ── Быстрые действия ──

@router.callback_query(F.data.startswith("action_ban_"))
async def cb_action_ban(query: CallbackQuery) -> None:
    from utils.bot_ref import bot
    parts = query.data.split("_")
    user_id, chat_id = int(parts[2]), int(parts[3])
    if not await is_admin(chat_id, query.from_user.id, bot):
        await query.answer("❌ Вы не администратор", show_alert=True)
        return
    try:
        member = await bot.get_chat_member(chat_id, user_id)
        target = member.user
    except Exception:
        await query.answer("❌ Ошибка получения данных", show_alert=True)
        return
    try:
        await bot.ban_chat_member(chat_id, user_id)
        increment_stat(user_id, chat_id, "bans")
        remove_user(user_id, chat_id)
        user_name = f"@{target.username}" if target.username else target.first_name
        log_admin_action(chat_id, query.from_user.id, query.from_user.username, "Бан (через меню)", user_id, target.username)
        await bot.send_message(chat_id, f"🔨 {user_name} забанен через меню бота")
        await query.answer("✅ Пользователь забанен", show_alert=True)
        await query.message.edit_text(
            f"✅ {user_name} забанен",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="◀️ Назад", callback_data=f"back_to_users_{chat_id}")]]),
        )
    except Exception as exc:
        await query.answer(f"❌ Ошибка: {exc}", show_alert=True)


@router.callback_query(F.data.startswith("action_kick_"))
async def cb_action_kick(query: CallbackQuery) -> None:
    from utils.bot_ref import bot
    parts = query.data.split("_")
    user_id, chat_id = int(parts[2]), int(parts[3])
    if not await is_admin(chat_id, query.from_user.id, bot):
        await query.answer("❌ Вы не администратор", show_alert=True)
        return
    try:
        member = await bot.get_chat_member(chat_id, user_id)
        target = member.user
    except Exception:
        await query.answer("❌ Ошибка получения данных", show_alert=True)
        return
    try:
        await bot.ban_chat_member(chat_id, user_id)
        await bot.unban_chat_member(chat_id, user_id)
        increment_stat(user_id, chat_id, "kicks")
        remove_user(user_id, chat_id)
        user_name = f"@{target.username}" if target.username else target.first_name
        log_admin_action(chat_id, query.from_user.id, query.from_user.username, "Кик (через меню)", user_id, target.username)
        await bot.send_message(chat_id, f"👢 {user_name} кикнут через меню бота")
        await query.answer("✅ Пользователь кикнут", show_alert=True)
        await query.message.edit_text(
            f"✅ {user_name} кикнут",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="◀️ Назад", callback_data=f"back_to_users_{chat_id}")]]),
        )
    except Exception as exc:
        await query.answer(f"❌ Ошибка: {exc}", show_alert=True)


@router.callback_query(F.data.startswith("action_unwarn_"))
async def cb_action_unwarn(query: CallbackQuery) -> None:
    from utils.bot_ref import bot
    from database.repositories import get_warning_count, remove_last_warning
    parts = query.data.split("_")
    user_id, chat_id = int(parts[2]), int(parts[3])
    if not await is_admin(chat_id, query.from_user.id, bot):
        await query.answer("❌ Вы не администратор", show_alert=True)
        return
    if get_warning_count(user_id, chat_id) == 0:
        await query.answer("ℹ️ У пользователя нет предупреждений", show_alert=True)
        return
    remove_last_warning(user_id, chat_id)
    new_count = get_warning_count(user_id, chat_id)
    log_admin_action(chat_id, query.from_user.id, query.from_user.username, "Снятие варна (через меню)", user_id)
    await query.answer(f"✅ Варн снят! Осталось: {new_count}/3", show_alert=True)


@router.callback_query(F.data.startswith("action_unmute_"))
async def cb_action_unmute(query: CallbackQuery) -> None:
    from utils.bot_ref import bot
    from moderation.antispam import spam_tracker
    parts = query.data.split("_")
    user_id, chat_id = int(parts[2]), int(parts[3])
    if not await is_admin(chat_id, query.from_user.id, bot):
        await query.answer("❌ Вы не администратор", show_alert=True)
        return
    try:
        await bot.restrict_chat_member(
            chat_id, user_id,
            permissions={"can_send_messages": True, "can_send_media_messages": True,
                         "can_send_other_messages": True, "can_add_web_page_previews": True},
        )
        spam_tracker.clear_mute(user_id)
        log_admin_action(chat_id, query.from_user.id, query.from_user.username, "Размут (через меню)", user_id)
        await query.answer("✅ Пользователь размучен", show_alert=True)
    except Exception as exc:
        await query.answer(f"❌ Ошибка: {exc}", show_alert=True)


@router.callback_query(F.data.startswith("action_warn_"))
async def cb_action_warn(query: CallbackQuery, state: FSMContext) -> None:
    from utils.bot_ref import bot
    parts = query.data.split("_")
    user_id, chat_id = int(parts[2]), int(parts[3])
    if not await is_admin(chat_id, query.from_user.id, bot):
        await query.answer("❌ Вы не администратор", show_alert=True)
        return
    await state.update_data(action_user_id=user_id, action_chat_id=chat_id, action_type="warn")
    await state.set_state(ModerationFSM.waiting_for_username)
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="❌ Отмена", callback_data=f"view_user_{user_id}_{chat_id}")]])
    await query.message.edit_text(
        "⚠️ <b>Выдать предупреждение</b>\n\nВведите время и причину:\n<code>30m Причина варна</code>",
        reply_markup=kb, parse_mode="HTML",
    )
    await query.answer()


@router.callback_query(F.data.startswith("action_mute_"))
async def cb_action_mute(query: CallbackQuery, state: FSMContext) -> None:
    from utils.bot_ref import bot
    parts = query.data.split("_")
    user_id, chat_id = int(parts[2]), int(parts[3])
    if not await is_admin(chat_id, query.from_user.id, bot):
        await query.answer("❌ Вы не администратор", show_alert=True)
        return
    await state.update_data(action_user_id=user_id, action_chat_id=chat_id, action_type="mute")
    await state.set_state(ModerationFSM.waiting_for_username)
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="❌ Отмена", callback_data=f"view_user_{user_id}_{chat_id}")]])
    await query.message.edit_text(
        "🔇 <b>Замутить пользователя</b>\n\nВведите время и причину:\n<code>1h Причина мута</code>",
        reply_markup=kb, parse_mode="HTML",
    )
    await query.answer()


# ──────────────────────────── Репорты ────────────────────────────

@router.callback_query(F.data == "back_to_reports_menu")
async def cb_back_to_reports(query: CallbackQuery) -> None:
    try:
        await query.message.edit_text(
            "📋 <b>Система репортов</b>\n\nВыберите действие:",
            reply_markup=reports_keyboard(), parse_mode="HTML",
        )
    except Exception:
        await query.message.answer(
            "📋 <b>Система репортов</b>",
            reply_markup=reports_keyboard(), parse_mode="HTML",
        )
    await query.answer()


@router.callback_query(F.data == "reports_active")
async def cb_reports_active(query: CallbackQuery) -> None:
    from utils.bot_ref import bot
    user_chats = await get_admin_chats(query.from_user.id, bot)
    if not user_chats:
        await query.answer("❌ Вы не администратор", show_alert=True)
        return
    all_reports = []
    for chat_id in user_chats:
        all_reports.extend(get_pending_reports(chat_id))
    if not all_reports:
        try:
            await query.message.edit_text(
                "📋 <b>Активные репорты</b>\n\n✅ Нет активных жалоб!",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_reports_menu")]]),
                parse_mode="HTML",
            )
        except Exception:
            await query.message.answer("✅ Нет активных жалоб!", reply_markup=_back_to_reports())
        await query.answer()
        return
    buttons = []
    for rep in all_reports[:20]:
        title = await _safe_chat_title(bot, rep["chat_id"])
        reported = rep["reported_username"] or "?"
        buttons.append([InlineKeyboardButton(text=f"#{rep['id']} • @{reported} • {title[:20]}", callback_data=f"report_view_{rep['id']}")])
    buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_reports_menu")])
    try:
        await query.message.edit_text(
            f"📋 <b>Активные репорты</b>\n\nВсего: {len(all_reports)}",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons), parse_mode="HTML",
        )
    except Exception:
        await query.message.answer(
            f"📋 Репортов: {len(all_reports)}",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons), parse_mode="HTML",
        )
    await query.answer()


@router.callback_query(F.data.startswith("report_view_"))
async def cb_report_view(query: CallbackQuery) -> None:
    from utils.bot_ref import bot
    report_id = int(query.data.split("_")[2])
    report = get_report_by_id(report_id)
    if not report:
        await query.answer("❌ Репорт не найден", show_alert=True)
        return
    if not await is_admin(report["chat_id"], query.from_user.id, bot):
        await query.answer("❌ Вы не админ этой группы", show_alert=True)
        return
    try:
        created = datetime.fromisoformat(report["created_at"]).strftime("%d.%m.%Y %H:%M")
    except Exception:
        created = "?"
    title = await _safe_chat_title(bot, report["chat_id"])
    reporter = f"@{report['reporter_username']}" if report["reporter_username"] else f"ID: {report['reporter_id']}"
    reported = f"@{report['reported_username']}" if report["reported_username"] else f"ID: {report['reported_id']}"
    text = (
        f"📋 <b>Репорт #{report['id']}</b>\n\n"
        f"👥 Чат: {title}\n📅 Дата: {created}\n\n"
        f"👮 От: {reporter}\n👤 На: {reported}\n📝 Причина: {report['reason']}\n"
    )
    if report["message_link"]:
        text += f"\n🔗 <a href='{report['message_link']}'>Перейти к сообщению</a>\n"
    text += "\n<b>Выберите действие:</b>"
    try:
        await query.message.edit_text(text, reply_markup=report_action_keyboard(report_id), parse_mode="HTML", disable_web_page_preview=True)
    except Exception:
        await query.message.answer(text, reply_markup=report_action_keyboard(report_id), parse_mode="HTML", disable_web_page_preview=True)
    await query.answer()


@router.callback_query(F.data.startswith("report_close_"))
async def cb_report_close(query: CallbackQuery) -> None:
    from utils.bot_ref import bot
    report_id = int(query.data.split("_")[2])
    report = get_report_by_id(report_id)
    if not report:
        await query.answer("❌ Репорт не найден", show_alert=True)
        return
    if not await is_admin(report["chat_id"], query.from_user.id, bot):
        await query.answer("❌ Вы не администратор", show_alert=True)
        return
    resolve_report(report_id, query.from_user.id, "Закрыт без действий")
    await query.answer("✅ Репорт закрыт", show_alert=True)
    await cb_reports_active(query)


@router.callback_query(F.data == "reports_stats")
async def cb_reports_stats(query: CallbackQuery) -> None:
    from utils.bot_ref import bot
    user_chats = await get_admin_chats(query.from_user.id, bot)
    if not user_chats:
        await query.answer("❌ Вы не администратор", show_alert=True)
        return
    if len(user_chats) == 1:
        await _show_report_stats(query.message, user_chats[0], bot)
    else:
        buttons = [
            [InlineKeyboardButton(text=await _safe_chat_title(bot, c), callback_data=f"report_stats_chat_{c}")]
            for c in user_chats
        ]
        buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_reports_menu")])
        await query.message.answer("📊 <b>Выберите группу:</b>", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons), parse_mode="HTML")
    await query.answer()


@router.callback_query(F.data.startswith("report_stats_chat_"))
async def cb_report_stats_chat(query: CallbackQuery) -> None:
    from utils.bot_ref import bot
    chat_id = int(query.data.split("_")[3])
    await _show_report_stats(query.message, chat_id, bot)
    await query.answer()


async def _show_report_stats(message, chat_id: int, bot) -> None:
    title = await _safe_chat_title(bot, chat_id)
    top_reporters = get_top_reporters(chat_id, 10)
    top_reported = get_top_reported(chat_id, 10)
    text = f"📊 <b>Статистика репортов</b>\n\nГруппа: {title}\n\n"
    if top_reporters:
        text += "🏆 <b>Топ жалобщиков:</b>\n"
        for r in top_reporters:
            name = f"@{r['username']}" if r["username"] else r["first_name"]
            text += f"  • {name}: {r['reports_made']}\n"
    if top_reported:
        text += "\n🎯 <b>Топ нарушителей:</b>\n"
        for r in top_reported:
            name = f"@{r['username']}" if r["username"] else r["first_name"]
            text += f"  • {name}: {r['reports_received']}\n"
    await message.answer(text, parse_mode="HTML", reply_markup=_back_to_reports())


# ──────────────────────────── Helpers ────────────────────────────

def _back_to_mod() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="◀️ Назад", callback_data="section_moderation")]])


def _back_to_reports() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_reports_menu")]])


async def _safe_chat_title(bot, chat_id: int) -> str:
    try:
        chat = await bot.get_chat(chat_id)
        return chat.title or str(chat_id)
    except Exception:
        return str(chat_id)
