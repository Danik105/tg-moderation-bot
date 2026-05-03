"""
database/init.py — Создание таблиц при первом запуске.
"""
from .connection import db


def init_db() -> None:
    with db.connection() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                user_id    INTEGER,
                chat_id    INTEGER,
                username   TEXT,
                first_name TEXT,
                joined_at  TIMESTAMP,
                verified   INTEGER DEFAULT 0,
                PRIMARY KEY (user_id, chat_id)
            );

            CREATE TABLE IF NOT EXISTS warnings (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id          INTEGER,
                chat_id          INTEGER,
                admin_id         INTEGER,
                reason           TEXT,
                duration_minutes INTEGER,
                warned_at        TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS spam_bans (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id     INTEGER,
                chat_id     INTEGER,
                ban_count   INTEGER DEFAULT 0,
                last_ban_at TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS user_stats (
                user_id  INTEGER,
                chat_id  INTEGER,
                kicks    INTEGER DEFAULT 0,
                bans     INTEGER DEFAULT 0,
                mutes    INTEGER DEFAULT 0,
                messages INTEGER DEFAULT 0,
                PRIMARY KEY (user_id, chat_id)
            );

            CREATE TABLE IF NOT EXISTS chat_settings (
                chat_id          INTEGER PRIMARY KEY,
                captcha_enabled  INTEGER DEFAULT 1,
                safe_mode        INTEGER DEFAULT 0,
                created_at       TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS admin_logs (
                id                INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id           INTEGER,
                admin_id          INTEGER,
                admin_username    TEXT,
                action            TEXT,
                target_user_id    INTEGER,
                target_username   TEXT,
                reason            TEXT,
                timestamp         TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS reports (
                id                      INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id                 INTEGER,
                reporter_id             INTEGER,
                reporter_username       TEXT,
                reported_id             INTEGER,
                reported_username       TEXT,
                reason                  TEXT,
                message_link            TEXT,
                status                  TEXT DEFAULT 'pending',
                admin_id                INTEGER,
                admin_action            TEXT,
                created_at              TIMESTAMP,
                resolved_at             TIMESTAMP,
                confirmation_message_id INTEGER
            );

            CREATE TABLE IF NOT EXISTS report_stats (
                user_id          INTEGER,
                chat_id          INTEGER,
                reports_made     INTEGER DEFAULT 0,
                reports_received INTEGER DEFAULT 0,
                PRIMARY KEY (user_id, chat_id)
            );
        """)
