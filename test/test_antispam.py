"""
tests/test_antispam.py

Тесты модулей SpamTracker и MessageHistory из moderation/antispam.py
"""
import sys
import os
import time
import unittest
from unittest.mock import MagicMock

# Мокируем тяжёлые зависимости до любого импорта пакета
for mod in ['aiogram', 'aiogram.types', 'aiogram.filters', 'aiogram.fsm.context',
            'aiogram.fsm.state', 'telethon', 'telethon.tl', 'telethon.tl.types',
            'g4f', 'g4f.client']:
    sys.modules.setdefault(mod, MagicMock())

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Загружаем только нужный файл напрямую, минуя __init__.py пакета
import importlib.util

def _load_module(name, filepath):
    spec = importlib.util.spec_from_file_location(name, filepath)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod

_base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
antispam = _load_module('moderation.antispam', os.path.join(_base, 'moderation', 'antispam.py'))
SpamTracker = antispam.SpamTracker
MessageHistory = antispam.MessageHistory
SpamEntry = antispam.SpamEntry


class TestSpamTracker(unittest.TestCase):
    """Тесты SpamTracker"""

    def setUp(self):
        self.tracker = SpamTracker(window=5, limit=3)

    def test_no_spam_below_limit(self):
        for _ in range(2):
            result = self.tracker.record_message(user_id=1)
        self.assertFalse(result)

    def test_spam_at_limit(self):
        for _ in range(2):
            self.tracker.record_message(user_id=1)
        result = self.tracker.record_message(user_id=1)
        self.assertTrue(result)

    def test_independent_users(self):
        for _ in range(3):
            self.tracker.record_message(user_id=1)
        result = self.tracker.record_message(user_id=2)
        self.assertFalse(result)

    def test_sliding_window_resets(self):
        tracker = SpamTracker(window=1, limit=3)
        tracker.record_message(user_id=1)
        tracker.record_message(user_id=1)
        time.sleep(1.1)
        tracker.record_message(user_id=1)
        result = tracker.record_message(user_id=1)
        self.assertFalse(result)

    def test_get_violations_default_zero(self):
        self.assertEqual(self.tracker.get_violations(99), 0)

    def test_increment_violations(self):
        v1 = self.tracker.increment_violations(1)
        v2 = self.tracker.increment_violations(1)
        self.assertEqual(v1, 1)
        self.assertEqual(v2, 2)

    def test_set_and_check_mute(self):
        self.tracker.set_mute(1, duration=100)
        self.assertFalse(self.tracker.is_mute_expired(1))

    def test_mute_expired(self):
        self.tracker.set_mute(1, duration=0.01)
        time.sleep(0.05)
        self.assertTrue(self.tracker.is_mute_expired(1))

    def test_no_mute_is_expired(self):
        self.assertTrue(self.tracker.is_mute_expired(999))

    def test_clear_mute(self):
        self.tracker.set_mute(1, duration=100)
        self.tracker.clear_mute(1)
        self.assertTrue(self.tracker.is_mute_expired(1))

    def test_clear_mute_clears_messages(self):
        for _ in range(3):
            self.tracker.record_message(1)
        self.tracker.set_mute(1, duration=100)
        self.tracker.clear_mute(1)
        entry = self.tracker._data.get(1)
        self.assertIsNotNone(entry)
        self.assertEqual(len(entry.messages), 0)

    def test_remove(self):
        self.tracker.record_message(1)
        self.tracker.remove(1)
        self.assertNotIn(1, self.tracker._data)

    def test_reset_violations(self):
        self.tracker.increment_violations(1)
        self.tracker.reset_violations(1)
        self.assertEqual(self.tracker.get_violations(1), 0)

    def test_cleanup_expired_removes_idle(self):
        self.tracker.set_mute(1, duration=0.01)
        time.sleep(0.05)
        self.tracker.cleanup_expired()
        self.assertNotIn(1, self.tracker._data)

    def test_cleanup_keeps_violations(self):
        for _ in range(3):
            self.tracker.increment_violations(1)
        self.tracker.set_mute(1, duration=0.01)
        time.sleep(0.05)
        self.tracker.cleanup_expired()
        self.assertIn(1, self.tracker._data)

    def test_cleanup_keeps_active_mute(self):
        self.tracker.set_mute(1, duration=100)
        self.tracker.cleanup_expired()
        self.assertIn(1, self.tracker._data)


class TestMessageHistory(unittest.TestCase):
    """Тесты MessageHistory"""

    def setUp(self):
        self.history = MessageHistory(ttl=86400)

    def test_add_and_get(self):
        self.history.add(user_id=1, chat_id=10, message_id=100, text="Hello")
        msgs = self.history.get(user_id=1, chat_id=10)
        self.assertEqual(len(msgs), 1)
        self.assertEqual(msgs[0]['text'], "Hello")
        self.assertEqual(msgs[0]['message_id'], 100)

    def test_multiple_messages(self):
        for i in range(5):
            self.history.add(1, 10, i, f"msg {i}")
        msgs = self.history.get(1, 10)
        self.assertEqual(len(msgs), 5)

    def test_different_chats_isolated(self):
        self.history.add(1, 10, 1, "chat 10")
        self.history.add(1, 20, 2, "chat 20")
        self.assertEqual(len(self.history.get(1, 10)), 1)
        self.assertEqual(len(self.history.get(1, 20)), 1)

    def test_different_users_isolated(self):
        self.history.add(1, 10, 1, "user 1")
        self.history.add(2, 10, 2, "user 2")
        self.assertEqual(len(self.history.get(1, 10)), 1)
        self.assertEqual(len(self.history.get(2, 10)), 1)

    def test_empty_history_returns_empty_list(self):
        msgs = self.history.get(999, 999)
        self.assertEqual(msgs, [])

    def test_expired_messages_filtered_on_get(self):
        history = MessageHistory(ttl=1)
        history.add(1, 10, 1, "old")
        time.sleep(1.1)
        msgs = history.get(1, 10)
        self.assertEqual(msgs, [])

    def test_expired_messages_cleaned_on_add(self):
        history = MessageHistory(ttl=1)
        history.add(1, 10, 1, "old")
        time.sleep(1.1)
        history.add(1, 10, 2, "new")
        bucket = history._data[1][10]
        self.assertEqual(len(bucket), 1)
        self.assertEqual(bucket[0]['text'], "new")

    def test_timestamp_is_set(self):
        before = time.time()
        self.history.add(1, 10, 1, "test")
        after = time.time()
        ts = self.history._data[1][10][0]['timestamp']
        self.assertGreaterEqual(ts, before)
        self.assertLessEqual(ts, after)


if __name__ == '__main__':
    unittest.main(verbosity=2)
