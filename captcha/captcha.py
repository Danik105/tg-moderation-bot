"""
captcha/captcha.py

- generate_captcha() — математическая задача
- create_captcha_keyboard() — гарантирует 4 уникальных ответа (включая отрицательные)
- CaptchaStorage — TTL-ограниченное хранилище активных капч (нет бесконечного роста)
"""
from __future__ import annotations

import asyncio
import logging
import random
import time
from dataclasses import dataclass, field
from typing import Dict, Optional, Tuple

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

logger = logging.getLogger(__name__)


def generate_captcha() -> Tuple[str, int]:
    num1 = random.randint(1, 10)
    num2 = random.randint(1, 10)
    operation = random.choice(["+", "-", "*"])
    if operation == "+":
        answer = num1 + num2
    elif operation == "-":
        answer = num1 - num2
    else:
        answer = num1 * num2
    return f"{num1} {operation} {num2}", answer


def create_captcha_keyboard(correct_answer: int) -> InlineKeyboardMarkup:
    """
    Генерирует 4 уникальных варианта ответа.
    Исправлен оригинальный баг: wrong >= 0 исключало отрицательный правильный ответ.
    Теперь диапазон смещений ±10, без ограничения на знак.
    """
    answers = {correct_answer}
    attempts = 0
    while len(answers) < 4 and attempts < 50:
        wrong = correct_answer + random.randint(-10, 10)
        if wrong != correct_answer:
            answers.add(wrong)
        attempts += 1

    answer_list = list(answers)
    random.shuffle(answer_list)

    buttons = [
        [InlineKeyboardButton(text=str(ans), callback_data=f"captcha_{ans}_{correct_answer}")]
        for ans in answer_list
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


@dataclass
class CaptchaEntry:
    chat_id: int
    answer: int
    message_id: Optional[int]
    created_at: float = field(default_factory=time.monotonic)


class CaptchaStorage:
    """
    Хранилище активных капч с автоочисткой устаревших записей.
    Нет бесконечного роста словаря.
    """

    def __init__(self, ttl: int = 120) -> None:
        self._data: Dict[int, CaptchaEntry] = {}
        self._ttl = ttl

    def set(self, user_id: int, entry: CaptchaEntry) -> None:
        self._cleanup()
        self._data[user_id] = entry

    def get(self, user_id: int) -> Optional[CaptchaEntry]:
        entry = self._data.get(user_id)
        if entry and time.monotonic() - entry.created_at > self._ttl:
            del self._data[user_id]
            return None
        return entry

    def pop(self, user_id: int) -> Optional[CaptchaEntry]:
        return self._data.pop(user_id, None)

    def __contains__(self, user_id: int) -> bool:
        return self.get(user_id) is not None

    def _cleanup(self) -> None:
        now = time.monotonic()
        expired = [uid for uid, e in self._data.items() if now - e.created_at > self._ttl]
        for uid in expired:
            del self._data[uid]


# Глобальный экземпляр
active_captchas = CaptchaStorage(ttl=120)
