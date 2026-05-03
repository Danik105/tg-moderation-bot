"""
workers/aiogram_worker.py

Регистрирует все роутеры и запускает polling.
"""
from __future__ import annotations

import logging

from aiogram import Bot, Dispatcher
from aiogram.client.bot import DefaultBotProperties
from aiogram.fsm.storage.memory import MemoryStorage

from config.settings import settings
from menu.handlers import router as menu_router
from menu.moderation_handlers import router as mod_menu_router
from moderation.commands import router as mod_commands_router
from moderation.events import router as mod_events_router, cleanup_spam_tracker_loop
import asyncio

logger = logging.getLogger(__name__)


async def run_aiogram() -> None:
    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode="HTML"),
    )

    # Регистрируем бота в глобальной ссылке
    from utils.bot_ref import set_bot
    set_bot(bot)

    storage = MemoryStorage()
    dp = Dispatcher(storage=storage)

    # Порядок важен: более специфичные роутеры — раньше
    dp.include_router(mod_commands_router)    # /warn /ban /mute etc.
    dp.include_router(mod_events_router)      # chat_member events, antispam
    dp.include_router(menu_router)            # главное меню, постинг, FSM
    dp.include_router(mod_menu_router)        # модерация через меню

    # Фоновая задача очистки spam_tracker
    asyncio.create_task(cleanup_spam_tracker_loop())

    logger.info("[Aiogram] Бот запущен.")
    try:
        await dp.start_polling(
            bot,
            allowed_updates=["chat_member", "message", "callback_query", "my_chat_member"],
        )
    except Exception as exc:
        logger.exception("[Aiogram] Критическая ошибка: %s", exc)
        raise
    finally:
        await bot.session.close()
