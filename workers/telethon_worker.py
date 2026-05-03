"""
workers/telethon_worker.py

- processed_message_ids ограничен по размеру (LRU-like через deque) — нет утечки памяти
- Источники обновляются каждые 5 секунд из posting_state (не перечитывают файл напрямую)
- reinit_telethon_client() вызывается при смене API credentials через меню
"""
from __future__ import annotations

import asyncio
import logging
from collections import deque
from typing import Optional

from telethon import TelegramClient, events
from telethon.tl.types import MessageMediaPhoto, MessageMediaDocument

from config.settings import settings
from posting.state import posting_state, PostEntry
from posting.llm import clean_text_with_llm

logger = logging.getLogger(__name__)

telethon_client: Optional[TelegramClient] = None


def _is_supported_media(event) -> bool:
    media = getattr(event.message, "media", None)
    return isinstance(media, (MessageMediaPhoto, MessageMediaDocument))


def _chat_id_match(event_chat, stored_chat: str) -> bool:
    if not stored_chat or not event_chat:
        return False
    stored = str(stored_chat).strip()
    username = getattr(event_chat, "username", None)
    if username:
        if stored.lstrip("@").lower() == username.lower():
            return True
    try:
        event_id = int(getattr(event_chat, "id", 0))
        if stored.lstrip("-").isdigit() and int(stored) == event_id:
            return True
    except Exception:
        pass
    return False


async def _notify_admins(post_idx: int) -> None:
    """Уведомляет администраторов о новом посте."""
    from utils.bot_ref import bot
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    if not bot:
        return
    notify_text = (
        "✅ Готов новый пост!\n"
        "Зайдите в раздел <b>Посты</b>, чтобы подтвердить или отменить публикацию."
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🟢 Понял", callback_data=f"seen_{post_idx}")]
    ])
    for admin_id in settings.admin_ids:
        try:
            await bot.send_message(admin_id, notify_text, parse_mode="HTML", reply_markup=kb)
        except Exception as exc:
            logger.error("[notify_post] admin %d: %s", admin_id, exc)


async def reinit_telethon_client() -> None:
    """Пересоздаёт клиент после смены credentials."""
    global telethon_client
    if telethon_client:
        try:
            await telethon_client.disconnect()
        except Exception:
            pass
    settings.reload_telethon()
    telethon_client = TelegramClient(settings.session_name, settings.api_id, settings.api_hash)
    await telethon_client.connect()
    logger.info("[Telethon] Клиент переинициализирован.")


async def run_telethon() -> None:
    global telethon_client

    while True:
        try:
            settings.reload_telethon()
            telethon_client = TelegramClient(settings.session_name, settings.api_id, settings.api_hash)
            await telethon_client.connect()

            if not await telethon_client.is_user_authorized():
                logger.warning("[Telethon] Нет авторизации. Используйте 📱 TG Аккаунт в меню.")
                while not await telethon_client.is_user_authorized():
                    await asyncio.sleep(3)

            logger.info("[Telethon] Userbot запущен.")

            # Кольцевой буфер для processed_message_ids — нет утечки памяти
            _MAX = settings.processed_ids_max_size
            _processed: deque[tuple[int, int]] = deque(maxlen=_MAX)
            _processed_set: set[tuple[int, int]] = set()

            def _mark_seen(uid: tuple[int, int]) -> None:
                if len(_processed) == _MAX:
                    old = _processed[0]
                    _processed_set.discard(old)
                _processed.append(uid)
                _processed_set.add(uid)

            @telethon_client.on(events.NewMessage)
            async def on_new_message(event) -> None:
                chat = event.chat
                if chat is None:
                    return
                if not any(_chat_id_match(chat, src) for src in posting_state.sources):
                    return

                msg_id = getattr(event.message, "id", None)
                chat_id = getattr(chat, "id", None)
                unique_id = (chat_id, msg_id)

                if unique_id in _processed_set:
                    return
                _mark_seen(unique_id)

                text = event.text or getattr(event.message, "message", "") or ""
                if not text:
                    return

                media = event.message.media if _is_supported_media(event) else None

                # LLM очистка текста
                clean_text = await clean_text_with_llm(text, posting_state.prompt)

                # Скачиваем видео заранее
                video_bytes: bytes | None = None
                if media and isinstance(media, MessageMediaDocument):
                    mime = getattr(media, "mime_type", "")
                    if mime.startswith("video"):
                        try:
                            video_bytes = await telethon_client.download_media(event.message, file=bytes)
                        except Exception:
                            pass

                # Проверяем дубликат по тексту в pending_posts
                for _, existing in await posting_state.pending_posts():
                    if existing.clean_text == clean_text:
                        return

                post = PostEntry(
                    clean_text=clean_text,
                    media=media,
                    source_event=event,
                    source_message=event.message,
                    video_bytes=video_bytes,
                )
                idx = await posting_state.add_post(post)
                await _notify_admins(idx)

            async def _reload_sources_loop() -> None:
                prev = set(posting_state.sources)
                while True:
                    await asyncio.sleep(5)
                    try:
                        posting_state.reload_sources()
                        current = set(posting_state.sources)
                        if current != prev:
                            logger.info("[Telethon] Источники обновлены: %s", posting_state.sources)
                            prev = current
                    except Exception as exc:
                        logger.error("[Telethon] Ошибка обновления источников: %s", exc)

            asyncio.create_task(_reload_sources_loop())
            logger.info("[Telethon] Ожидание сообщений...")
            await telethon_client.run_until_disconnected()

        except Exception as exc:
            logger.error("[Telethon] Ошибка: %s. Переподключение через 10 сек...", exc)
            await asyncio.sleep(10)
