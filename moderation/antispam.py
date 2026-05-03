"""
moderation/antispam.py

SpamTracker заменяет глобальный dict spam_tracker.
Обрабатывает сообщения в скользящем окне и выдаёт мут/бан.
message_history хранится с TTL, не растёт бесконечно.
"""
from __future__ import annotations

import asyncio
import logging
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Deque, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class SpamEntry:
    messages: Deque[float] = field(default_factory=deque)   # timestamps
    violations: int = 0
    last_mute_time: Optional[float] = None
    mute_duration: Optional[float] = None


class SpamTracker:
    """
    Отслеживает сообщения пользователей в скользящем окне.
    Автоматически очищает устаревшие записи.
    """

    def __init__(self, window: int = 5, limit: int = 5) -> None:
        self._data: Dict[int, SpamEntry] = {}
        self._window = window   # секунд
        self._limit = limit     # сообщений в окне

    def _entry(self, user_id: int) -> SpamEntry:
        if user_id not in self._data:
            self._data[user_id] = SpamEntry()
        return self._data[user_id]

    def record_message(self, user_id: int) -> bool:
        """
        Регистрирует сообщение. Возвращает True если пользователь спамит.
        """
        now = time.monotonic()
        e = self._entry(user_id)
        e.messages.append(now)
        # Удаляем сообщения вне окна
        while e.messages and now - e.messages[0] > self._window:
            e.messages.popleft()
        return len(e.messages) >= self._limit

    def get_violations(self, user_id: int) -> int:
        return self._data.get(user_id, SpamEntry()).violations

    def increment_violations(self, user_id: int) -> int:
        e = self._entry(user_id)
        e.violations += 1
        return e.violations

    def set_mute(self, user_id: int, duration: float) -> None:
        e = self._entry(user_id)
        e.last_mute_time = time.monotonic()
        e.mute_duration = duration

    def is_mute_expired(self, user_id: int) -> bool:
        e = self._data.get(user_id)
        if not e or not e.last_mute_time or not e.mute_duration:
            return True
        return time.monotonic() - e.last_mute_time > e.mute_duration

    def clear_mute(self, user_id: int) -> None:
        e = self._data.get(user_id)
        if e:
            e.last_mute_time = None
            e.mute_duration = None
            e.messages.clear()

    def remove(self, user_id: int) -> None:
        self._data.pop(user_id, None)

    def reset_violations(self, user_id: int) -> None:
        self._data.pop(user_id, None)

    def cleanup_expired(self) -> None:
        """Удаляет записи с истёкшим мутом и пустой историей."""
        to_del = []
        for uid, e in self._data.items():
            mute_expired = self.is_mute_expired(uid)
            if mute_expired and len(e.messages) == 0 and e.violations < 3:
                to_del.append(uid)
        for uid in to_del:
            del self._data[uid]


# Глобальный экземпляр
spam_tracker = SpamTracker()


# ──────────────────────────── Message history ────────────────────────────

class MessageHistory:
    """
    Хранит историю сообщений с TTL (по умолчанию 24 ч).
    Никакого бесконечного роста словаря.
    """

    def __init__(self, ttl: int = 86400) -> None:
        self._ttl = ttl
        # {user_id: {chat_id: [{"message_id", "text", "timestamp"}]}}
        self._data: Dict[int, Dict[int, List[dict]]] = {}

    def add(self, user_id: int, chat_id: int, message_id: int, text: str) -> None:
        now = time.time()
        bucket = self._data.setdefault(user_id, {}).setdefault(chat_id, [])
        bucket.append({"message_id": message_id, "text": text, "timestamp": now})
        # Очистка старых записей
        self._data[user_id][chat_id] = [m for m in bucket if now - m["timestamp"] < self._ttl]

    def get(self, user_id: int, chat_id: int) -> List[dict]:
        now = time.time()
        bucket = self._data.get(user_id, {}).get(chat_id, [])
        return [m for m in bucket if now - m["timestamp"] < self._ttl]


message_history = MessageHistory()
