"""
config/settings.py — Вся конфигурация берётся из переменных окружения.
Никаких захардкоженных секретов. Используйте .env + python-dotenv или
экспортируйте переменные перед запуском.

Обязательные переменные окружения:
    BOT_TOKEN   — токен Telegram-бота
    API_ID      — Telethon API ID
    API_HASH    — Telethon API Hash
    ADMIN_IDS   — список ID администраторов через запятую, например: 123,456
"""
import os
import json
import logging
from dataclasses import dataclass, field
from typing import List

logger = logging.getLogger(__name__)

# Пытаемся загрузить .env если есть python-dotenv
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

_CREDENTIALS_FILE = "credentials.json"


def _require(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(
            f"Переменная окружения '{name}' не установлена. "
            "Создайте файл .env или экспортируйте переменную."
        )
    return value


def _load_telethon_credentials() -> tuple[int, str]:
    """
    Порядок: credentials.json → переменные окружения.
    credentials.json создаётся при смене API через меню бота.
    """
    if os.path.exists(_CREDENTIALS_FILE):
        try:
            with open(_CREDENTIALS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            api_id = data.get("API_ID")
            api_hash = data.get("API_HASH")
            if api_id and api_hash:
                return int(api_id), str(api_hash)
        except Exception as exc:
            logger.warning("Не удалось прочитать %s: %s", _CREDENTIALS_FILE, exc)
    return int(_require("API_ID")), _require("API_HASH")


def save_telethon_credentials(api_id: int, api_hash: str) -> None:
    with open(_CREDENTIALS_FILE, "w", encoding="utf-8") as f:
        json.dump({"API_ID": api_id, "API_HASH": api_hash}, f, ensure_ascii=False, indent=2)


@dataclass
class Settings:
    bot_token: str = field(default_factory=lambda: _require("BOT_TOKEN"))
    api_id: int = field(default_factory=lambda: _load_telethon_credentials()[0])
    api_hash: str = field(default_factory=lambda: _load_telethon_credentials()[1])
    admin_ids: List[int] = field(
        default_factory=lambda: [
            int(x.strip())
            for x in os.getenv("ADMIN_IDS", "").split(",")
            if x.strip().isdigit()
        ]
    )

    session_name: str = "user_session"
    db_path: str = "users.db"

    # Антиспам
    captcha_timeout: int = 60
    processing_timeout: int = 5
    spam_time_window: int = 5
    spam_message_limit: int = 5
    message_history_duration: int = 86400

    # Лимит кэша processed_message_ids в Telethon-воркере
    processed_ids_max_size: int = 10_000

    def reload_telethon(self) -> None:
        """Перечитать credentials после изменения через меню."""
        self.api_id, self.api_hash = _load_telethon_credentials()


# Единственный экземпляр конфигурации
settings = Settings()
