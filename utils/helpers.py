"""
utils/helpers.py

Вспомогательные функции без побочных эффектов.
"""
from __future__ import annotations

import logging
from typing import Optional, Tuple, TYPE_CHECKING

if TYPE_CHECKING:
    from aiogram import Bot
    from aiogram.types import Message

logger = logging.getLogger(__name__)


def parse_time(time_str: str) -> int:
    """
    Парсит строку вида '5m', '2h', '1d' → минуты.
    Поднимает ValueError при неверном формате.
    """
    if not time_str:
        raise ValueError("Пустая строка времени")
    time_str = time_str.lower().strip()
    if len(time_str) < 2:
        raise ValueError(f"Неверный формат: {time_str!r}")
    unit = time_str[-1]
    try:
        number = int(time_str[:-1])
    except ValueError:
        raise ValueError(f"Неверный формат: {time_str!r}")
    if unit == "m":
        return number
    if unit == "h":
        return number * 60
    if unit == "d":
        return number * 1440
    # Если просто число — считаем минутами
    try:
        return int(time_str)
    except ValueError:
        raise ValueError(f"Неверный формат: {time_str!r}")


def format_time(minutes: int) -> str:
    if minutes < 60:
        return f"{minutes} минут"
    if minutes < 1440:
        return f"{minutes // 60} часов"
    return f"{minutes // 1440} дней"


async def is_admin(chat_id: int, user_id: int, bot) -> bool:
    try:
        member = await bot.get_chat_member(chat_id, user_id)
        return member.status in ("creator", "administrator")
    except Exception:
        return False


async def get_admin_chats(user_id: int, bot) -> list[int]:
    from database.repositories import get_all_chat_ids
    chats = get_all_chat_ids()
    result = []
    for chat_id in chats:
        try:
            if await is_admin(chat_id, user_id, bot):
                result.append(chat_id)
        except Exception:
            pass
    return result


class FakeUser:
    """Заглушка пользователя для случаев поиска по username/ID."""
    def __init__(self, user_id: int, username: Optional[str], first_name: str) -> None:
        self.id = user_id
        self.username = username
        self.first_name = first_name
        self.is_bot = False


async def get_target_user(message: "Message", bot) -> Tuple[Optional[object], Optional[int]]:
    from database.repositories import get_user_chat_id, find_user_by_username
    from aiogram.enums import ChatType

    if message.chat.type == ChatType.PRIVATE:
        chat_id = None
    else:
        chat_id = message.chat.id

    # Из reply
    if message.reply_to_message:
        return message.reply_to_message.from_user, chat_id

    # Из text_mention entity
    if message.entities:
        for entity in message.entities:
            if entity.type == "text_mention":
                if chat_id is None:
                    chat_id = get_user_chat_id(entity.user.id)
                return entity.user, chat_id

    args = (message.text or "").split()
    if len(args) < 2:
        return None, None

    identifier = args[1]

    # По числовому ID
    if identifier.isdigit():
        user_id = int(identifier)
        if chat_id is None:
            chat_id = get_user_chat_id(user_id)
        if not chat_id:
            return None, None
        try:
            member = await bot.get_chat_member(chat_id, user_id)
            return member.user, chat_id
        except Exception:
            return None, None

    # По username
    username = identifier.lstrip("@")
    if chat_id is None:
        from database.repositories import db
        from database.connection import db as pool
        with pool.connection() as conn:
            row = conn.execute(
                "SELECT user_id, chat_id, username, first_name FROM users WHERE LOWER(username) = ? LIMIT 1",
                (username.lower(),),
            ).fetchone()
        if row:
            return FakeUser(row["user_id"], row["username"], row["first_name"]), row["chat_id"]
    else:
        user_data = find_user_by_username(username, chat_id)
        if user_data:
            return FakeUser(user_data["user_id"], user_data["username"], user_data["first_name"]), chat_id

    return None, None
