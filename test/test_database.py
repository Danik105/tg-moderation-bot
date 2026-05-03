"""
tests/test_database.py

Тесты DatabasePool / _DbProxy и основных функций репозитория.
Используем :memory: где возможно, а для файловых тестов — корректная
очистка под Windows (явное закрытие всех соединений перед unlink).
"""
import sys
import os
import gc
import sqlite3
import tempfile
import threading
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database.connection import DatabasePool, init_pool, db, ALLOWED_STAT_COLUMNS, ALLOWED_SETTING_COLUMNS


def _safe_unlink(path):
    """Удаляет файл, игнорируя ошибки (для Windows где файл может ещё держаться)."""
    gc.collect()
    try:
        os.unlink(path)
    except PermissionError:
        pass  # Windows: файл освободится позже, тест уже прошёл


class TestDatabasePool(unittest.TestCase):
    """Тесты класса DatabasePool"""

    def setUp(self):
        self.tmpfile = tempfile.NamedTemporaryFile(suffix='.db', delete=False)
        self.tmpfile.close()
        self.pool = DatabasePool(self.tmpfile.name)

    def tearDown(self):
        # Закрываем соединение в текущем потоке
        self.pool.close()
        # Убиваем ссылку на пул, чтобы GC мог закрыть остальные соединения
        self.pool = None
        gc.collect()
        _safe_unlink(self.tmpfile.name)

    def test_connection_returns_connection(self):
        with self.pool.connection() as conn:
            self.assertIsInstance(conn, sqlite3.Connection)

    def test_connection_commits_on_success(self):
        with self.pool.connection() as conn:
            conn.execute("CREATE TABLE IF NOT EXISTS t (x INTEGER)")
            conn.execute("INSERT INTO t VALUES (42)")
        with self.pool.connection() as conn:
            row = conn.execute("SELECT x FROM t").fetchone()
            self.assertEqual(row[0], 42)

    def test_connection_rollback_on_exception(self):
        with self.pool.connection() as conn:
            conn.execute("CREATE TABLE IF NOT EXISTS t2 (x INTEGER)")
        try:
            with self.pool.connection() as conn:
                conn.execute("INSERT INTO t2 VALUES (99)")
                raise ValueError("test error")
        except ValueError:
            pass
        with self.pool.connection() as conn:
            count = conn.execute("SELECT COUNT(*) FROM t2").fetchone()[0]
            self.assertEqual(count, 0)

    def test_row_factory_sqlite_row(self):
        with self.pool.connection() as conn:
            conn.execute("CREATE TABLE IF NOT EXISTS t3 (name TEXT)")
            conn.execute("INSERT INTO t3 VALUES ('hello')")
        with self.pool.connection() as conn:
            row = conn.execute("SELECT name FROM t3").fetchone()
            self.assertEqual(row['name'], 'hello')

    def test_thread_local_connections(self):
        """Каждый поток должен получить свой объект соединения"""
        import time
        connections = []
        lock = threading.Lock()

        def get_conn():
            conn = self.pool._get_conn()
            with lock:
                connections.append(id(conn))
            # Держим поток живым пока все не зафиксируют id
            time.sleep(0.05)

        threads = [threading.Thread(target=get_conn) for _ in range(3)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        # Все соединения должны быть разными объектами
        self.assertEqual(len(set(connections)), 3)

    def test_close_releases_connection(self):
        self.pool._get_conn()
        self.pool.close()
        self.assertIsNone(getattr(self.pool._local, 'conn', None))


class TestDbProxy(unittest.TestCase):
    """Тесты прокси-объекта db"""

    def test_requires_init_before_use(self):
        from database.connection import _DbProxy
        proxy = _DbProxy()
        with self.assertRaises(RuntimeError):
            with proxy.connection():
                pass

    def test_init_pool_sets_pool(self):
        tmpfile = tempfile.NamedTemporaryFile(suffix='.db', delete=False)
        tmpfile.close()
        try:
            pool = init_pool(tmpfile.name)
            self.assertIsNotNone(db._pool)
        finally:
            db._pool = None
            pool.close()
            pool = None
            gc.collect()
            _safe_unlink(tmpfile.name)


class TestAllowedColumns(unittest.TestCase):
    """Тесты whitelist колонок (защита от SQL-инъекций)"""

    def test_stat_columns_contains_expected(self):
        self.assertIn('kicks', ALLOWED_STAT_COLUMNS)
        self.assertIn('bans', ALLOWED_STAT_COLUMNS)
        self.assertIn('mutes', ALLOWED_STAT_COLUMNS)
        self.assertIn('messages', ALLOWED_STAT_COLUMNS)

    def test_stat_columns_is_frozenset(self):
        self.assertIsInstance(ALLOWED_STAT_COLUMNS, frozenset)

    def test_setting_columns_contains_expected(self):
        self.assertIn('captcha_enabled', ALLOWED_SETTING_COLUMNS)
        self.assertIn('safe_mode', ALLOWED_SETTING_COLUMNS)

    def test_setting_columns_is_frozenset(self):
        self.assertIsInstance(ALLOWED_SETTING_COLUMNS, frozenset)

    def test_injection_attempt_not_in_whitelist(self):
        injection = "kicks; DROP TABLE users--"
        self.assertNotIn(injection, ALLOWED_STAT_COLUMNS)
        self.assertNotIn(injection, ALLOWED_SETTING_COLUMNS)


_SCHEMA = """
    CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER NOT NULL,
        chat_id INTEGER NOT NULL,
        username TEXT,
        first_name TEXT NOT NULL,
        joined_at TEXT NOT NULL,
        verified INTEGER NOT NULL DEFAULT 0,
        PRIMARY KEY (user_id, chat_id)
    );
    CREATE TABLE IF NOT EXISTS mod_stats (
        chat_id INTEGER PRIMARY KEY,
        kicks INTEGER DEFAULT 0,
        bans INTEGER DEFAULT 0,
        mutes INTEGER DEFAULT 0,
        messages INTEGER DEFAULT 0
    );
    CREATE TABLE IF NOT EXISTS settings (
        chat_id INTEGER PRIMARY KEY,
        captcha_enabled INTEGER DEFAULT 1,
        safe_mode INTEGER DEFAULT 0
    );
    CREATE TABLE IF NOT EXISTS warns (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        chat_id INTEGER NOT NULL,
        reason TEXT,
        warned_at TEXT NOT NULL
    );
"""


class TestRepositoriesWithRealDB(unittest.TestCase):
    """
    Интеграционные тесты репозитория на реальной SQLite-базе.
    """

    def setUp(self):
        self.tmpfile = tempfile.NamedTemporaryFile(suffix='.db', delete=False)
        self.tmpfile.close()
        self._pool = init_pool(self.tmpfile.name)
        with self._pool.connection() as conn:
            conn.executescript(_SCHEMA)

    def tearDown(self):
        # Явно закрываем соединение текущего потока
        self._pool.close()
        db._pool = None
        self._pool = None
        gc.collect()
        _safe_unlink(self.tmpfile.name)

    def test_add_and_verify_user(self):
        from database.repositories import add_user, verify_user
        add_user(user_id=1, chat_id=100, username='testuser', first_name='Test')
        verify_user(user_id=1, chat_id=100)
        with db.connection() as conn:
            row = conn.execute(
                "SELECT verified FROM users WHERE user_id=1 AND chat_id=100"
            ).fetchone()
        self.assertEqual(row['verified'], 1)

    def test_remove_user_only_from_specific_chat(self):
        """remove_user удаляет только из нужного чата (исправленный баг)"""
        from database.repositories import add_user, remove_user
        add_user(1, 100, 'u', 'U')
        add_user(1, 200, 'u', 'U')
        remove_user(1, 100)
        with db.connection() as conn:
            rows = conn.execute("SELECT chat_id FROM users WHERE user_id=1").fetchall()
        chat_ids = [r['chat_id'] for r in rows]
        self.assertNotIn(100, chat_ids)
        self.assertIn(200, chat_ids)

    def test_find_user_by_username(self):
        from database.repositories import add_user, find_user_by_username
        add_user(42, 100, 'alice', 'Alice')
        result = find_user_by_username('@alice', 100)
        self.assertIsNotNone(result)
        self.assertEqual(result['user_id'], 42)

    def test_find_user_by_username_case_insensitive(self):
        from database.repositories import add_user, find_user_by_username
        add_user(43, 100, 'Bob', 'Bob')
        result = find_user_by_username('@BOB', 100)
        self.assertIsNotNone(result)

    def test_find_user_not_found(self):
        from database.repositories import find_user_by_username
        result = find_user_by_username('@nobody', 100)
        self.assertIsNone(result)

    def test_get_user_chat_id(self):
        from database.repositories import add_user, get_user_chat_id
        add_user(55, 777, 'x', 'X')
        chat_id = get_user_chat_id(55)
        self.assertEqual(chat_id, 777)

    def test_get_user_chat_id_not_found(self):
        from database.repositories import get_user_chat_id
        result = get_user_chat_id(9999)
        self.assertIsNone(result)

    def test_add_user_replace_on_duplicate(self):
        """INSERT OR REPLACE — повторный add_user не должен падать"""
        from database.repositories import add_user
        add_user(1, 100, 'u', 'First')
        try:
            add_user(1, 100, 'u', 'Updated')
        except Exception as e:
            self.fail(f"Повторный add_user упал: {e}")


if __name__ == '__main__':
    unittest.main(verbosity=2)
