"""
database/connection.py

Thread-safe SQLite connection pool через contextlib.contextmanager.
db — прокси-объект, init_pool() задаёт реальный пул.
"""
import sqlite3
import threading
import logging
from contextlib import contextmanager
from typing import Generator

logger = logging.getLogger(__name__)

ALLOWED_STAT_COLUMNS = frozenset({"kicks", "bans", "mutes", "messages"})
ALLOWED_SETTING_COLUMNS = frozenset({"captcha_enabled", "safe_mode"})


class DatabasePool:
    def __init__(self, db_path: str = "users.db") -> None:
        self._db_path = db_path
        self._local = threading.local()

    def _get_conn(self) -> sqlite3.Connection:
        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = sqlite3.connect(self._db_path, check_same_thread=False)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA foreign_keys=ON")
            self._local.conn = conn
        return conn

    @contextmanager
    def connection(self) -> Generator[sqlite3.Connection, None, None]:
        conn = self._get_conn()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise

    def close(self) -> None:
        conn = getattr(self._local, "conn", None)
        if conn:
            conn.close()
            self._local.conn = None


class _DbProxy:
    """
    Прокси, который делегирует все вызовы реальному пулу.
    Позволяет писать 'from .connection import db' на уровне модуля
    и не получать None — реальный пул подставляется через init_pool().
    """
    _pool: "DatabasePool | None" = None

    def _require(self) -> DatabasePool:
        if self._pool is None:
            raise RuntimeError(
                "База данных не инициализирована. "
                "Вызовите init_pool() перед использованием db."
            )
        return self._pool

    @contextmanager
    def connection(self) -> Generator[sqlite3.Connection, None, None]:
        with self._require().connection() as conn:
            yield conn

    def close(self) -> None:
        if self._pool:
            self._pool.close()


# Глобальный прокси — безопасно импортировать на уровне модуля
db = _DbProxy()


def init_pool(db_path: str = "users.db") -> DatabasePool:
    pool = DatabasePool(db_path)
    db._pool = pool
    return pool
