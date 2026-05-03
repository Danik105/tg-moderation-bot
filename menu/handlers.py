"""
menu/handlers.py

Обработчики главного меню, постинга, авторизации Telethon.
FSM вместо глобальных множеств waiting_for_*.
_auth_code_buffer и _links_edit_idx убраны из глобального состояния — данные хранятся в FSMContext.
"""
from __future__ import annotations

import asyncio
import logging

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message, BufferedInputFile, InlineKeyboardButton, InlineKeyboardMarkup

from config.settings import settings, save_telethon_credentials
from menu.keyboards import (
    main_menu, posting_menu, moderation_menu, system_menu, back_button,
    sources_menu, remove_group_menu, links_menu, numpad_keyboard, reply_main_menu,
)
from menu.states import PostingFSM
from posting.state import posting_state, PostEntry
from posting.sender import send_post
import utils.bot_ref as _bot_ref
from utils.git_update import git_check_updates, git_pull, git_restart

logger = logging.getLogger(__name__)
router = Router()

ALLOWED_COMMANDS_FOR_ALL = {"/report", "/help", "/commands", "/stat"}
ALLOWED_IN_PRIVATE = {"/start", "/menu", "/version", "/update"}


# ──────────────────────────── Gate ────────────────────────────

async def _admin_gate(message: Message) -> bool:
    from utils.helpers import is_admin
    from aiogram.enums import ChatType
    from config.settings import settings

    # /start доступен всем без ограничений
    text = (message.text or "").strip()
    command = text.split()[0].lower().split("@")[0] if text else ""

    if command == "/start":
        return True

    # В группах пропускаем не-команды
    if message.chat.type in (ChatType.GROUP, ChatType.SUPERGROUP) and not text.startswith("/"):
        return True

    # Команды доступные всем
    if command in ALLOWED_COMMANDS_FOR_ALL:
        return True

    # В ЛС: пропускаем разрешённые команды
    if message.chat.type == ChatType.PRIVATE and command in ALLOWED_IN_PRIVATE:
        return True

    # Проверяем: является ли пользователь bot-admin (из .env)
    if message.from_user.id in settings.admin_ids:
        return True

    # Проверяем права в чате через Telegram API
    _bot = _bot_ref.bot
    if _bot and await is_admin(message.chat.id, message.from_user.id, _bot):
        return True

    if message.chat.type == ChatType.PRIVATE:
        await message.reply("❌ Вы не можете пользоваться данным ботом.")
    return False


# ──────────────────────────── /start ────────────────────────────

@router.message(Command("start"))
async def handle_start(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(
        "🏠 <b>Главное меню</b>\n\nВыберите раздел:",
        parse_mode="HTML",
        reply_markup=main_menu(),
    )


# ──────────────────────────── Навигация ────────────────────────────

@router.callback_query(F.data == "back_to_main")
async def cb_back_to_main(query: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    try:
        await query.message.edit_text("🏠 <b>Главное меню</b>\n\nВыберите раздел:", parse_mode="HTML", reply_markup=main_menu())
    except Exception:
        await query.message.answer("🏠 <b>Главное меню</b>", parse_mode="HTML", reply_markup=main_menu())
    await query.answer()


@router.callback_query(F.data == "refresh")
async def cb_refresh(query: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    try:
        await query.message.edit_text("🏠 <b>Главное меню</b>\n\nВыберите раздел:", parse_mode="HTML", reply_markup=main_menu())
    except Exception:
        await query.message.answer("🏠 <b>Главное меню</b>", parse_mode="HTML", reply_markup=main_menu())
    await query.answer()


@router.callback_query(F.data == "section_posting")
async def cb_section_posting(query: CallbackQuery) -> None:
    count = await posting_state.pending_count()
    try:
        await query.message.edit_text("📢 <b>Постинг</b>\n\nВыберите действие:", parse_mode="HTML", reply_markup=posting_menu(count))
    except Exception:
        await query.message.answer("📢 <b>Постинг</b>", parse_mode="HTML", reply_markup=posting_menu(count))
    await query.answer()


@router.callback_query(F.data == "section_moderation")
async def cb_section_moderation(query: CallbackQuery) -> None:
    try:
        await query.message.edit_text("🛡 <b>Модерация</b>\n\nВыберите действие:", parse_mode="HTML", reply_markup=moderation_menu())
    except Exception:
        await query.message.answer("🛡 <b>Модерация</b>", parse_mode="HTML", reply_markup=moderation_menu())
    await query.answer()


@router.callback_query(F.data == "section_system")
async def cb_section_system(query: CallbackQuery) -> None:
    try:
        await query.message.edit_text("⚙️ <b>Система</b>", parse_mode="HTML", reply_markup=system_menu())
    except Exception:
        await query.message.answer("⚙️ <b>Система</b>", parse_mode="HTML", reply_markup=system_menu())
    await query.answer()


@router.callback_query(F.data == "section_help")
async def cb_section_help(query: CallbackQuery) -> None:
    help_text = (
        "📖 <b>Справка по боту</b>\n\n"
        "<b>📢 Постинг:</b> настройка источников, целевой группы, LLM-промпта, подпись постов.\n"
        "<b>🛡 Модерация:</b> капча, варны, муты, баны, репорты, безопасный режим.\n"
        "<b>⚙️ Система:</b> git-обновление бота.\n\n"
        "<b>Команды в группах:</b>\n"
        "/warn @user 30m Причина — предупреждение\n"
        "/mute @user 1h Причина — мут\n"
        "/ban @user Причина — бан\n"
        "/report — жалоба на пользователя\n"
        "/stat @user — статистика\n"
    )
    try:
        await query.message.edit_text(help_text, parse_mode="HTML", reply_markup=back_button())
    except Exception:
        await query.message.answer(help_text, parse_mode="HTML", reply_markup=back_button())
    await query.answer()


# ──────────────────────────── Промпт ────────────────────────────

@router.callback_query(F.data == "prompt")
async def cb_prompt(query: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(PostingFSM.waiting_prompt)
    await query.message.answer(
        f"<b>Текущий PROMPT:</b>\n<code>{posting_state.prompt}</code>\n\nВведите новый текст PROMPT:",
        parse_mode="HTML", reply_markup=back_button(),
    )
    await query.answer()


# ──────────────────────────── Источники ────────────────────────────

@router.callback_query(F.data == "sources")
async def cb_sources(query: CallbackQuery) -> None:
    text = "📚 <b>Группы-источники:</b>\n"
    text += "\n".join(f"- {s}" for s in posting_state.sources) if posting_state.sources else "(список пуст)"
    await query.message.answer(text, parse_mode="HTML", reply_markup=sources_menu())
    await query.answer()


@router.callback_query(F.data == "add_group")
async def cb_add_group(query: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(PostingFSM.waiting_source)
    await query.message.answer("Введите @username или ID группы для добавления:", reply_markup=back_button())
    await query.answer()


@router.callback_query(F.data == "remove_group")
async def cb_remove_group(query: CallbackQuery) -> None:
    if not posting_state.sources:
        await query.message.answer("Список групп пуст.", reply_markup=sources_menu())
    else:
        await query.message.answer("Выберите группу для удаления:", reply_markup=remove_group_menu(posting_state.sources))
    await query.answer()


@router.callback_query(F.data.startswith("delgroup_"))
async def cb_del_group(query: CallbackQuery) -> None:
    idx = int(query.data.split("_")[1])
    if 0 <= idx < len(posting_state.sources):
        removed = posting_state.sources.pop(idx)
        posting_state.save_sources()
        await query.message.answer(f"❌ Группа <b>{removed}</b> удалена.", parse_mode="HTML")
    await query.message.answer("Обновлённый список:", reply_markup=sources_menu())
    await query.answer()


# ──────────────────────────── Целевая группа ────────────────────────────

@router.callback_query(F.data == "target_group")
async def cb_target_group(query: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(PostingFSM.waiting_target)
    current = posting_state.target_chat or "(не задана)"
    await query.message.answer(
        f"👥 <b>Целевая группа:</b> {current}\n\nВведите @username или ID:",
        parse_mode="HTML", reply_markup=back_button(),
    )
    await query.answer()


# ──────────────────────────── Посты ────────────────────────────

@router.callback_query(F.data == "posts")
async def cb_posts(query: CallbackQuery) -> None:
    from telethon.tl.types import MessageMediaPhoto
    posts = await posting_state.pending_posts()
    if not posts:
        await query.message.answer("📄 Нет ожидающих постов.", reply_markup=main_menu())
        await query.answer()
        return

    for num, (idx, post) in enumerate(posts, 1):
        text = post.clean_text
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Отправить", callback_data=f"confirm_{idx}"),
                InlineKeyboardButton(text="❌ Отменить", callback_data=f"cancel_{idx}"),
                InlineKeyboardButton(text="📤 Без медиа", callback_data=f"sendtext_{idx}"),
            ],
            [InlineKeyboardButton(text="✏️ Редактировать", callback_data=f"edit_{idx}")],
            [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_main")],
        ])
        post.aiogram_message_ids = []
        msg = await query.message.answer(f"🆕 <b>ПОСТ {num}:</b>", parse_mode="HTML")
        post.aiogram_message_ids.append(msg.message_id)

        if post.media and isinstance(post.media, MessageMediaPhoto) and post.source_message:
            from workers.telethon_worker import telethon_client
            if telethon_client:
                file_bytes = await telethon_client.download_media(post.source_message, file=bytes)
                if file_bytes:
                    caption = text[:1024]
                    photo = BufferedInputFile(file_bytes, filename="post.jpg")
                    msg = await query.message.answer_photo(photo=photo, caption=caption, parse_mode="HTML")
                    post.aiogram_message_ids.append(msg.message_id)
                    if len(text) > 1024:
                        for i in range(1024, len(text), 4096):
                            chunk = text[i:i+4096]
                            is_last = (i + 4096 >= len(text))
                            msg = await query.message.answer(chunk, parse_mode="HTML", reply_markup=kb if is_last else None)
                            post.aiogram_message_ids.append(msg.message_id)
                    else:
                        msg = await query.message.answer("❓ Отправить в целевую группу?", reply_markup=kb)
                        post.aiogram_message_ids.append(msg.message_id)
                    continue

        # Текстовый пост
        chunks = [text[i:i+4096] for i in range(0, len(text), 4096)]
        for i, chunk in enumerate(chunks):
            is_last = (i == len(chunks) - 1)
            suffix = "\n\n❓ Отправить?" if is_last else ""
            msg = await query.message.answer(chunk + suffix, parse_mode="HTML", reply_markup=kb if is_last else None)
            post.aiogram_message_ids.append(msg.message_id)

    await query.answer()


async def _delete_post_messages(post: PostEntry, chat_id: int) -> None:
    for msg_id in post.aiogram_message_ids:
        try:
            await _bot_ref.bot.delete_message(chat_id, msg_id)
        except Exception:
            pass
    post.aiogram_message_ids = []


@router.callback_query(F.data.startswith("confirm_"))
async def cb_confirm(query: CallbackQuery) -> None:
    idx = int(query.data.split("_")[1])
    post = await posting_state.get_post(idx)
    if not post:
        await query.message.answer("Пост не найден.", reply_markup=main_menu())
        await query.answer()
        return
    await _delete_post_messages(post, query.message.chat.id)
    await _do_send_post(query, idx, with_media=True)


@router.callback_query(F.data.startswith("sendtext_"))
async def cb_sendtext(query: CallbackQuery) -> None:
    idx = int(query.data.split("_")[1])
    post = await posting_state.get_post(idx)
    if post:
        await _delete_post_messages(post, query.message.chat.id)
    await _do_send_post(query, idx, with_media=False)


@router.callback_query(F.data.startswith("cancel_"))
async def cb_cancel(query: CallbackQuery) -> None:
    idx = int(query.data.split("_")[1])
    post = await posting_state.get_post(idx)
    if not post:
        await query.message.answer("Пост не найден.", reply_markup=main_menu())
        await query.answer()
        return
    if post.status != "pending":
        await query.message.answer("Пост уже обработан.", reply_markup=main_menu())
        await query.answer()
        return
    await _delete_post_messages(post, query.message.chat.id)
    await posting_state.remove_post(idx)
    await query.message.answer("❌ Пост отменён.", reply_markup=main_menu())
    await query.answer()


async def _do_send_post(query: CallbackQuery, idx: int, *, with_media: bool) -> None:
    from workers.telethon_worker import telethon_client
    post = await posting_state.get_post(idx)
    if not post:
        await query.message.answer("Пост не найден.", reply_markup=main_menu())
        await query.answer()
        return
    if post.status != "pending":
        await query.message.answer("Пост уже обработан.", reply_markup=main_menu())
        await query.answer()
        return
    post.status = "sending"
    try:
        await send_post(telethon_client, post, with_media=with_media)
        await posting_state.remove_post(idx)
        await query.message.answer("✅ Пост отправлен!", reply_markup=main_menu())
    except Exception as exc:
        post.status = "pending"
        await query.message.answer(f"❌ Ошибка отправки: {exc}", reply_markup=main_menu())
    await query.answer()


@router.callback_query(F.data.startswith("edit_"))
async def cb_edit_post(query: CallbackQuery, state: FSMContext) -> None:
    idx = int(query.data.split("_")[1])
    post = await posting_state.get_post(idx)
    if not post:
        await query.message.answer("Пост не найден.", reply_markup=main_menu())
        await query.answer()
        return
    await state.set_state(PostingFSM.editing_post)
    await state.update_data(editing_post_idx=idx)
    msg = await query.message.answer("✏️ Введите новый текст для поста:", reply_markup=back_button())
    post.edit_prompt_message_id = msg.message_id
    await query.answer()


@router.callback_query(F.data.startswith("seen_"))
async def cb_seen(query: CallbackQuery) -> None:
    try:
        await query.message.delete()
        await query.answer("✅ Уведомление скрыто")
    except Exception:
        await query.answer()


# ──────────────────────────── Ссылки ────────────────────────────

@router.callback_query(F.data == "links")
async def cb_links(query: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    lines = "\n".join(
        f"  {i+1}. <b>{lnk['label']}</b> — <code>{lnk['url']}</code>"
        for i, lnk in enumerate(posting_state.signature_links)
    ) or "  (список пуст)"
    await query.message.answer(
        f"🔗 <b>Кнопки подписи постов</b>\n\n{lines}",
        parse_mode="HTML", reply_markup=links_menu(posting_state.signature_links),
    )
    await query.answer()


@router.callback_query(F.data == "link_add")
async def cb_link_add(query: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(PostingFSM.waiting_links_label)
    await state.update_data(link_edit_idx=None)
    await query.message.answer(
        "➕ <b>Новая кнопка подписи</b>\n\nВведите <b>название</b> кнопки:",
        parse_mode="HTML", reply_markup=back_button("links"),
    )
    await query.answer()


@router.callback_query(F.data.startswith("link_edit_"))
async def cb_link_edit(query: CallbackQuery, state: FSMContext) -> None:
    idx = int(query.data.split("_")[2])
    if idx >= len(posting_state.signature_links):
        await query.answer("Кнопка не найдена")
        return
    lnk = posting_state.signature_links[idx]
    await state.set_state(PostingFSM.waiting_links_label)
    await state.update_data(link_edit_idx=idx)
    await query.message.answer(
        f"✏️ <b>Редактирование: {lnk['label']}</b>\n"
        f"Текущая ссылка: <code>{lnk['url']}</code>\n\n"
        f"Введите новое название (или <code>-</code> чтобы оставить прежнее):",
        parse_mode="HTML", reply_markup=back_button("links"),
    )
    await query.answer()


@router.callback_query(F.data.startswith("link_del_"))
async def cb_link_del(query: CallbackQuery) -> None:
    idx = int(query.data.split("_")[2])
    if 0 <= idx < len(posting_state.signature_links):
        removed = posting_state.signature_links.pop(idx)
        posting_state.save_links()
        await query.answer(f"🗑 «{removed['label']}» удалена")
    await cb_links(query, None)


# ──────────────────────────── TG Авторизация ────────────────────────────

@router.callback_query(F.data == "tg_auth")
async def cb_tg_auth(query: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    from workers.telethon_worker import telethon_client
    is_auth = False
    try:
        if telethon_client and telethon_client.is_connected():
            is_auth = await telethon_client.is_user_authorized()
    except Exception:
        pass
    status = "✅ Сессия активна" if is_auth else "❌ Сессия отсутствует"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📱 Войти в аккаунт", callback_data="auth_start")],
        [InlineKeyboardButton(text="🔑 Изменить API_ID / API_HASH", callback_data="auth_set_api")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_main")],
    ])
    await query.message.answer(
        f"📱 <b>Telegram аккаунт (userbot)</b>\n\nСтатус: {status}\n"
        f"API_ID: <code>{settings.api_id}</code>\n"
        f"API_HASH: <code>{settings.api_hash[:8]}...</code>",
        parse_mode="HTML", reply_markup=kb,
    )
    await query.answer()


@router.callback_query(F.data == "auth_start")
async def cb_auth_start(query: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(PostingFSM.waiting_auth_phone)
    await query.message.answer(
        "📱 Введите номер телефона в формате +7XXXXXXXXXX:",
        reply_markup=back_button("tg_auth"),
    )
    await query.answer()


@router.callback_query(F.data == "auth_set_api")
async def cb_auth_set_api(query: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(PostingFSM.waiting_api_id)
    await query.message.answer(
        "🔑 Введите <b>API_ID</b> (число):",
        parse_mode="HTML", reply_markup=back_button("tg_auth"),
    )
    await query.answer()


# ──────────────────────────── Git update ────────────────────────────

@router.callback_query(F.data == "bot_update")
async def cb_bot_update(query: CallbackQuery) -> None:
    await query.message.answer("⏳ Проверяю обновления...")
    ok, count, text = git_check_updates()
    if not ok or count == 0:
        await query.message.answer(text, parse_mode="HTML", reply_markup=back_button("section_system"))
        await query.answer()
        return
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Обновить и перезапустить", callback_data="bot_update_confirm")],
        [InlineKeyboardButton(text="◀️ Отмена", callback_data="section_system")],
    ])
    await query.message.answer(text, parse_mode="HTML", reply_markup=kb)
    await query.answer()


@router.callback_query(F.data == "bot_update_confirm")
async def cb_bot_update_confirm(query: CallbackQuery) -> None:
    await query.message.answer("⬆️ Обновляю...")
    ok, text = git_pull()
    await query.message.answer(text, parse_mode="HTML")
    if ok:
        await asyncio.sleep(2)
        git_restart()
    await query.answer()


# ──────────────────────────── Numpad (код авторизации) ────────────────────────────

@router.callback_query(F.data.startswith("numpad_"))
async def cb_numpad(query: CallbackQuery, state: FSMContext) -> None:
    digit = query.data.split("_")[1]
    data = await state.get_data()
    code = data.get("auth_code_buffer", "")

    if digit == "⌫":
        code = code[:-1]
    elif digit == "✅":
        # Подтверждение кода — переходим к обработке
        await state.update_data(auth_code_buffer=code)
        # Симулируем как будто пользователь ввёл код текстом
        from aiogram.types import Message as AioMessage
        await _process_auth_code(query, state, code)
        return
    else:
        code += digit

    await state.update_data(auth_code_buffer=code)
    display = "•" * len(code)
    await query.message.edit_text(
        f"🔑 Введите код из SMS:\n\n<code>{display}</code> ({len(code)} цифр)\n\nили нажмите ✅",
        parse_mode="HTML", reply_markup=numpad_keyboard(code),
    )
    await query.answer()


async def _process_auth_code(query: CallbackQuery, state: FSMContext, code: str) -> None:
    from workers.telethon_worker import telethon_client
    data = await state.get_data()
    phone_code_hash = data.get("phone_code_hash")
    phone = data.get("auth_phone")
    try:
        await telethon_client.sign_in(phone, code, phone_code_hash=phone_code_hash)
        await state.clear()
        await query.message.answer("✅ Авторизация успешна!", reply_markup=back_button("tg_auth"))
    except Exception as exc:
        err = str(exc)
        if "2FA" in err or "password" in err.lower():
            await state.set_state(PostingFSM.waiting_auth_2fa)
            await query.message.answer("🔐 Введите пароль двухфакторной аутентификации:")
        else:
            await query.message.answer(f"❌ Ошибка авторизации: {exc}")
            await state.clear()


# ──────────────────────────── Текстовый обработчик ЛС (FSM) ────────────────────────────

@router.message(PostingFSM.waiting_prompt)
async def fsm_waiting_prompt(message: Message, state: FSMContext) -> None:
    text = (message.text or "").strip()
    if not text:
        await message.answer("❗ PROMPT не может быть пустым.")
        return
    posting_state.prompt = text
    posting_state.save_config()
    await state.clear()
    await message.answer("✅ PROMPT обновлён!", reply_markup=main_menu())


@router.message(PostingFSM.waiting_target)
async def fsm_waiting_target(message: Message, state: FSMContext) -> None:
    text = (message.text or "").strip()
    if not text:
        await message.answer("❗ Целевая группа не может быть пустой.")
        return
    if not (text.startswith("@") or text.lstrip("-").isdigit()):
        text = "@" + text
    posting_state.target_chat = text
    posting_state.save_target()
    await state.clear()
    await message.answer(f"✅ Целевая группа: <b>{text}</b>", parse_mode="HTML", reply_markup=main_menu())


@router.message(PostingFSM.waiting_source)
async def fsm_waiting_source(message: Message, state: FSMContext) -> None:
    text = (message.text or "").strip()
    if not text:
        await message.answer("❗ Не может быть пустым.")
        return
    if text not in posting_state.sources:
        posting_state.sources.append(text)
        posting_state.save_sources()
        await message.answer(f"✅ Группа <b>{text}</b> добавлена!", parse_mode="HTML", reply_markup=sources_menu())
    else:
        await message.answer(f"⚠️ <b>{text}</b> уже в списке.", parse_mode="HTML", reply_markup=sources_menu())
    await state.clear()


@router.message(PostingFSM.waiting_links_label)
async def fsm_waiting_links_label(message: Message, state: FSMContext) -> None:
    text = (message.text or "").strip()
    data = await state.get_data()
    idx = data.get("link_edit_idx")
    label = posting_state.signature_links[idx]["label"] if (text == "-" and idx is not None) else text
    await state.update_data(pending_link_label=label)
    await state.set_state(PostingFSM.waiting_links_url)
    hint = f"\nТекущая: <code>{posting_state.signature_links[idx]['url']}</code>" if idx is not None else ""
    await message.answer(
        f"🔗 Введите ссылку для «{label}»:{hint}\nПример: <code>https://t.me/mychannel</code>",
        parse_mode="HTML", reply_markup=back_button("links"),
    )


@router.message(PostingFSM.waiting_links_url)
async def fsm_waiting_links_url(message: Message, state: FSMContext) -> None:
    text = (message.text or "").strip()
    data = await state.get_data()
    label = data.get("pending_link_label", "")
    idx = data.get("link_edit_idx")
    if not text.startswith("http"):
        await message.answer("❗ Ссылка должна начинаться с https://")
        return
    if idx is None:
        posting_state.signature_links.append({"label": label, "url": text})
    else:
        posting_state.signature_links[idx] = {"label": label, "url": text}
    posting_state.save_links()
    await state.clear()
    await message.answer(f"✅ Кнопка <b>{label}</b> сохранена!", parse_mode="HTML", reply_markup=main_menu())


@router.message(PostingFSM.waiting_auth_phone)
async def fsm_waiting_auth_phone(message: Message, state: FSMContext) -> None:
    from workers.telethon_worker import telethon_client
    phone = (message.text or "").strip()
    if not phone.startswith("+"):
        phone = "+" + phone
    try:
        result = await telethon_client.send_code_request(phone)
        await state.update_data(auth_phone=phone, phone_code_hash=result.phone_code_hash, auth_code_buffer="")
        await state.set_state(PostingFSM.waiting_auth_code)
        await message.answer(
            "🔑 Введите код из SMS:\n\n<code></code> (0 цифр)\n\nили нажмите ✅",
            parse_mode="HTML", reply_markup=numpad_keyboard(""),
        )
    except Exception as exc:
        await state.clear()
        await message.answer(f"❌ Ошибка: {exc}", reply_markup=main_menu())


@router.message(PostingFSM.waiting_auth_code)
async def fsm_waiting_auth_code(message: Message, state: FSMContext) -> None:
    from workers.telethon_worker import telethon_client
    code = (message.text or "").strip()
    data = await state.get_data()
    phone = data.get("auth_phone")
    phone_code_hash = data.get("phone_code_hash")
    try:
        await telethon_client.sign_in(phone, code, phone_code_hash=phone_code_hash)
        await state.clear()
        await message.answer("✅ Авторизация успешна!", reply_markup=main_menu())
    except Exception as exc:
        if "2FA" in str(exc) or "password" in str(exc).lower():
            await state.set_state(PostingFSM.waiting_auth_2fa)
            await message.answer("🔐 Введите пароль двухфакторной аутентификации:")
        else:
            await state.clear()
            await message.answer(f"❌ Ошибка: {exc}", reply_markup=main_menu())


@router.message(PostingFSM.waiting_auth_2fa)
async def fsm_waiting_auth_2fa(message: Message, state: FSMContext) -> None:
    from workers.telethon_worker import telethon_client
    password = (message.text or "").strip()
    try:
        await telethon_client.sign_in(password=password)
        await state.clear()
        await message.answer("✅ Авторизация успешна!", reply_markup=main_menu())
    except Exception as exc:
        await state.clear()
        await message.answer(f"❌ Ошибка 2FA: {exc}", reply_markup=main_menu())


@router.message(PostingFSM.waiting_api_id)
async def fsm_waiting_api_id(message: Message, state: FSMContext) -> None:
    text = (message.text or "").strip()
    if not text.isdigit():
        await message.answer("❗ API_ID должен быть числом.")
        return
    await state.update_data(new_api_id=text)
    await state.set_state(PostingFSM.waiting_api_hash)
    await message.answer(
        f"✅ API_ID = <code>{text}</code>\n\nТеперь введите <b>API_HASH</b>:",
        parse_mode="HTML", reply_markup=back_button("tg_auth"),
    )


@router.message(PostingFSM.waiting_api_hash)
async def fsm_waiting_api_hash(message: Message, state: FSMContext) -> None:
    from workers.telethon_worker import reinit_telethon_client
    data = await state.get_data()
    new_api_id = data.get("new_api_id")
    if not new_api_id:
        await state.clear()
        await message.answer("❗ Сессия истекла.", reply_markup=main_menu())
        return
    new_api_hash = (message.text or "").strip()
    save_telethon_credentials(int(new_api_id), new_api_hash)
    settings.reload_telethon()
    await state.clear()
    await message.answer(
        f"✅ <b>Credentials сохранены!</b>\nAPI_ID: <code>{new_api_id}</code>\n"
        f"API_HASH: <code>{new_api_hash[:8]}...</code>",
        parse_mode="HTML", reply_markup=main_menu(),
    )
    await reinit_telethon_client()


@router.message(PostingFSM.editing_post)
async def fsm_editing_post(message: Message, state: FSMContext) -> None:
    text = (message.text or "").strip()
    data = await state.get_data()
    idx = data.get("editing_post_idx")
    if idx is None:
        await state.clear()
        return
    post = await posting_state.get_post(idx)
    if not post:
        await state.clear()
        await message.answer("Пост не найден.", reply_markup=main_menu())
        return
    post.clean_text = text
    await state.clear()
    await message.answer("✅ Текст поста обновлён!", reply_markup=main_menu())
