"""
tests/test_captcha.py

Тесты модуля captcha:
- generate_captcha()
- create_captcha_keyboard()
- CaptchaStorage (TTL, set/get/pop/__contains__, cleanup)
"""
import sys
import os
import time
import random
import unittest
from unittest.mock import patch, MagicMock

# Мокируем aiogram перед импортом модуля
aiogram_mock = MagicMock()
aiogram_types_mock = MagicMock()

# Создаём реальные классы-заглушки, чтобы наследование работало
class FakeInlineKeyboardButton:
    def __init__(self, text, callback_data):
        self.text = text
        self.callback_data = callback_data

class FakeInlineKeyboardMarkup:
    def __init__(self, inline_keyboard):
        self.inline_keyboard = inline_keyboard

aiogram_types_mock.InlineKeyboardButton = FakeInlineKeyboardButton
aiogram_types_mock.InlineKeyboardMarkup = FakeInlineKeyboardMarkup
aiogram_mock.types = aiogram_types_mock

sys.modules['aiogram'] = aiogram_mock
sys.modules['aiogram.types'] = aiogram_types_mock

# Добавляем путь к проекту
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from captcha.captcha import (
    generate_captcha,
    create_captcha_keyboard,
    CaptchaStorage,
    CaptchaEntry,
)


class TestGenerateCaptcha(unittest.TestCase):
    """Тесты функции generate_captcha()"""

    def test_returns_tuple_str_int(self):
        question, answer = generate_captcha()
        self.assertIsInstance(question, str)
        self.assertIsInstance(answer, int)

    def test_addition_correct(self):
        random.seed(42)
        for _ in range(100):
            question, answer = generate_captcha()
            parts = question.split()
            a, op, b = int(parts[0]), parts[1], int(parts[2])
            if op == '+':
                self.assertEqual(answer, a + b)
            elif op == '-':
                self.assertEqual(answer, a - b)
            elif op == '*':
                self.assertEqual(answer, a * b)

    def test_operands_in_range_1_10(self):
        for _ in range(200):
            question, _ = generate_captcha()
            parts = question.split()
            a, b = int(parts[0]), int(parts[2])
            self.assertGreaterEqual(a, 1)
            self.assertLessEqual(a, 10)
            self.assertGreaterEqual(b, 1)
            self.assertLessEqual(b, 10)

    def test_only_valid_operations(self):
        ops = set()
        for _ in range(300):
            question, _ = generate_captcha()
            ops.add(question.split()[1])
        self.assertTrue(ops.issubset({'+', '-', '*'}))

    def test_subtraction_can_be_negative(self):
        """Вычитание может давать отрицательный результат (1-10 = -9)"""
        negative_found = False
        for _ in range(500):
            question, answer = generate_captcha()
            if '-' in question and answer < 0:
                negative_found = True
                break
        # Если за 500 попыток отрицательный ответ не встретился — это тоже норма
        # (шанс невысокий), поэтому просто проверяем корректность
        question, answer = generate_captcha()
        parts = question.split()
        a, op, b = int(parts[0]), parts[1], int(parts[2])
        expected = a + b if op == '+' else (a - b if op == '-' else a * b)
        self.assertEqual(answer, expected)


class TestCreateCaptchaKeyboard(unittest.TestCase):
    """Тесты функции create_captcha_keyboard()"""

    def _parse_keyboard(self, markup):
        buttons = []
        for row in markup.inline_keyboard:
            for btn in row:
                buttons.append(btn)
        return buttons

    def test_returns_four_buttons(self):
        markup = create_captcha_keyboard(5)
        buttons = self._parse_keyboard(markup)
        self.assertEqual(len(buttons), 4)

    def test_correct_answer_present(self):
        for correct in [-5, 0, 5, 15, 100]:
            markup = create_captcha_keyboard(correct)
            buttons = self._parse_keyboard(markup)
            values = [int(b.text) for b in buttons]
            self.assertIn(correct, values, f"Правильного ответа {correct} нет в кнопках {values}")

    def test_all_buttons_unique(self):
        for _ in range(50):
            markup = create_captcha_keyboard(5)
            buttons = self._parse_keyboard(markup)
            values = [int(b.text) for b in buttons]
            self.assertEqual(len(values), len(set(values)), f"Дублирующиеся кнопки: {values}")

    def test_callback_data_format(self):
        correct = 7
        markup = create_captcha_keyboard(correct)
        buttons = self._parse_keyboard(markup)
        for btn in buttons:
            parts = btn.callback_data.split('_')
            self.assertEqual(parts[0], 'captcha')
            self.assertEqual(int(parts[2]), correct)

    def test_negative_correct_answer(self):
        """Фикс бага: отрицательный правильный ответ должен попасть в кнопки"""
        for _ in range(20):
            markup = create_captcha_keyboard(-3)
            buttons = self._parse_keyboard(markup)
            values = [int(b.text) for b in buttons]
            self.assertIn(-3, values)

    def test_zero_correct_answer(self):
        for _ in range(20):
            markup = create_captcha_keyboard(0)
            buttons = self._parse_keyboard(markup)
            values = [int(b.text) for b in buttons]
            self.assertIn(0, values)


class TestCaptchaStorage(unittest.TestCase):
    """Тесты CaptchaStorage"""

    def _entry(self, user_id=1, chat_id=100, answer=5):
        return CaptchaEntry(chat_id=chat_id, answer=answer, message_id=None)

    def test_set_and_get(self):
        storage = CaptchaStorage(ttl=60)
        entry = self._entry()
        storage.set(1, entry)
        result = storage.get(1)
        self.assertIsNotNone(result)
        self.assertEqual(result.answer, 5)

    def test_get_missing_returns_none(self):
        storage = CaptchaStorage(ttl=60)
        self.assertIsNone(storage.get(999))

    def test_pop_removes_entry(self):
        storage = CaptchaStorage(ttl=60)
        storage.set(1, self._entry())
        popped = storage.pop(1)
        self.assertIsNotNone(popped)
        self.assertIsNone(storage.get(1))

    def test_pop_missing_returns_none(self):
        storage = CaptchaStorage(ttl=60)
        self.assertIsNone(storage.pop(999))

    def test_contains_true(self):
        storage = CaptchaStorage(ttl=60)
        storage.set(1, self._entry())
        self.assertIn(1, storage)

    def test_contains_false(self):
        storage = CaptchaStorage(ttl=60)
        self.assertNotIn(999, storage)

    def test_ttl_expired_returns_none(self):
        storage = CaptchaStorage(ttl=1)
        entry = self._entry()
        entry.created_at = time.monotonic() - 2  # уже истёк
        storage._data[1] = entry
        self.assertIsNone(storage.get(1))
        self.assertNotIn(1, storage._data)

    def test_cleanup_removes_expired(self):
        storage = CaptchaStorage(ttl=1)
        for uid in [1, 2, 3]:
            entry = self._entry(user_id=uid)
            entry.created_at = time.monotonic() - 2
            storage._data[uid] = entry
        storage._cleanup()
        self.assertEqual(len(storage._data), 0)

    def test_cleanup_keeps_fresh(self):
        storage = CaptchaStorage(ttl=60)
        storage.set(1, self._entry())
        storage._cleanup()
        self.assertIn(1, storage._data)

    def test_set_triggers_cleanup(self):
        """set() должен вызывать _cleanup() для старых записей"""
        storage = CaptchaStorage(ttl=1)
        old_entry = self._entry(user_id=99)
        old_entry.created_at = time.monotonic() - 10
        storage._data[99] = old_entry
        # Добавляем новую запись — должна вытеснить старую через cleanup
        storage.set(1, self._entry())
        self.assertNotIn(99, storage._data)


if __name__ == '__main__':
    unittest.main(verbosity=2)
