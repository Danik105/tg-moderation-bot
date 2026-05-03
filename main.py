"""
Точка входа. Инициализирует все подсистемы и запускает workers.
"""
import asyncio
import logging

from config.settings import settings
from database.connection import init_pool
from database.init import init_db
from workers.aiogram_worker import run_aiogram
from workers.telethon_worker import run_telethon
from posting.state import posting_state

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)


async def main() -> None:
    # Инициализация пула соединений и БД
    init_pool(settings.db_path)
    await asyncio.to_thread(init_db)

    # Загрузка конфигурации постинга
    posting_state.load_all()

    logger.info("Запуск workers...")

    aiogram_task = asyncio.create_task(run_aiogram(), name="aiogram")
    telethon_task = asyncio.create_task(run_telethon(), name="telethon")

    try:
        await asyncio.gather(aiogram_task, telethon_task)
    except (asyncio.CancelledError, KeyboardInterrupt):
        logger.info("Получен сигнал остановки.")
    except Exception as exc:
        logger.exception("Критическая ошибка: %s", exc)
    finally:
        for task in (aiogram_task, telethon_task):
            if not task.done():
                task.cancel()
        await asyncio.gather(aiogram_task, telethon_task, return_exceptions=True)
        logger.info("Бот остановлен.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        pass
