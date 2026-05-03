"""
database/repositories.py

Все операции с БД. Нет f-строк для имён колонок — только whitelist.
remove_user принимает chat_id для точечного удаления.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from .connection import db, ALLOWED_STAT_COLUMNS, ALLOWED_SETTING_COLUMNS

logger = logging.getLogger(__name__)


# ──────────────────────────── Users ────────────────────────────

def add_user(user_id: int, chat_id: int, username: Optional[str], first_name: str) -> None:
    with db.connection() as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO users
                (user_id, chat_id, username, first_name, joined_at, verified)
            VALUES (?, ?, ?, ?, ?, 0)
            """,
            (user_id, chat_id, username, first_name, datetime.now().isoformat()),
        )


def verify_user(user_id: int, chat_id: int) -> None:
    """Верифицирует пользователя в конкретном чате."""
    with db.connection() as conn:
        conn.execute(
            "UPDATE users SET verified = 1 WHERE user_id = ? AND chat_id = ?",
            (user_id, chat_id),
        )


def remove_user(user_id: int, chat_id: int) -> None:
    """
    Удаляет пользователя ТОЛЬКО из указанного чата.
    (В оригинале была ошибка: удалялось из всех чатов сразу.)
    """
    with db.connection() as conn:
        conn.execute(
            "DELETE FROM users WHERE user_id = ? AND chat_id = ?",
            (user_id, chat_id),
        )


def get_user_chat_id(user_id: int) -> Optional[int]:
    with db.connection() as conn:
        row = conn.execute(
            "SELECT chat_id FROM users WHERE user_id = ? LIMIT 1", (user_id,)
        ).fetchone()
    return row["chat_id"] if row else None


def find_user_by_username(username: str, chat_id: int) -> Optional[Dict[str, Any]]:
    username = username.lstrip("@").lower()
    with db.connection() as conn:
        row = conn.execute(
            """
            SELECT user_id, username, first_name
            FROM users
            WHERE LOWER(username) = ? AND chat_id = ?
            """,
            (username, chat_id),
        ).fetchone()
    if row:
        return {"user_id": row["user_id"], "username": row["username"], "first_name": row["first_name"]}
    return None


def get_user_stats(user_id: int, chat_id: int) -> Optional[Dict[str, Any]]:
    with db.connection() as conn:
        user = conn.execute(
            "SELECT username, first_name, joined_at, verified FROM users WHERE user_id = ? AND chat_id = ?",
            (user_id, chat_id),
        ).fetchone()
        if not user:
            return None

        warns = conn.execute(
            "SELECT COUNT(*) as cnt FROM warnings WHERE user_id = ? AND chat_id = ?",
            (user_id, chat_id),
        ).fetchone()["cnt"]

        spam = conn.execute(
            "SELECT ban_count FROM spam_bans WHERE user_id = ? AND chat_id = ?",
            (user_id, chat_id),
        ).fetchone()

        stats = conn.execute(
            "SELECT kicks, bans, mutes, messages FROM user_stats WHERE user_id = ? AND chat_id = ?",
            (user_id, chat_id),
        ).fetchone()

    return {
        "username": user["username"],
        "first_name": user["first_name"],
        "joined_at": user["joined_at"],
        "verified": user["verified"],
        "warns": warns,
        "spam_bans": spam["ban_count"] if spam else 0,
        "kicks": stats["kicks"] if stats else 0,
        "bans": stats["bans"] if stats else 0,
        "mutes": stats["mutes"] if stats else 0,
        "messages": stats["messages"] if stats else 0,
    }


def get_users_in_chat(chat_id: int) -> List[int]:
    with db.connection() as conn:
        rows = conn.execute(
            "SELECT user_id FROM users WHERE chat_id = ? AND verified = 1", (chat_id,)
        ).fetchall()
    return [r["user_id"] for r in rows]


# ──────────────────────────── Stats ────────────────────────────

def increment_stat(user_id: int, chat_id: int, stat_type: str) -> None:
    """SQL-safe: только колонки из whitelist."""
    if stat_type not in ALLOWED_STAT_COLUMNS:
        raise ValueError(f"Недопустимый тип статистики: {stat_type!r}")

    # Используем именованные параметры — имя колонки проверено по whitelist
    col = stat_type  # safe: только ASCII идентификаторы из frozenset
    with db.connection() as conn:
        existing = conn.execute(
            "SELECT 1 FROM user_stats WHERE user_id = ? AND chat_id = ?",
            (user_id, chat_id),
        ).fetchone()
        if existing:
            # Имя колонки из whitelist — безопасно подставлять в SQL
            conn.execute(
                f"UPDATE user_stats SET {col} = {col} + 1 WHERE user_id = ? AND chat_id = ?",
                (user_id, chat_id),
            )
        else:
            conn.execute(
                f"INSERT INTO user_stats (user_id, chat_id, {col}) VALUES (?, ?, 1)",
                (user_id, chat_id),
            )


def increment_message_count(user_id: int, chat_id: int) -> None:
    increment_stat(user_id, chat_id, "messages")


# ──────────────────────────── Warnings ────────────────────────────

def add_warning(user_id: int, chat_id: int, admin_id: int, reason: str, duration_minutes: int) -> None:
    with db.connection() as conn:
        conn.execute(
            """
            INSERT INTO warnings (user_id, chat_id, admin_id, reason, duration_minutes, warned_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (user_id, chat_id, admin_id, reason, duration_minutes, datetime.now().isoformat()),
        )


def get_warning_count(user_id: int, chat_id: int) -> int:
    with db.connection() as conn:
        return conn.execute(
            "SELECT COUNT(*) as cnt FROM warnings WHERE user_id = ? AND chat_id = ?",
            (user_id, chat_id),
        ).fetchone()["cnt"]


def remove_last_warning(user_id: int, chat_id: int) -> None:
    with db.connection() as conn:
        conn.execute(
            """
            DELETE FROM warnings WHERE id = (
                SELECT id FROM warnings WHERE user_id = ? AND chat_id = ?
                ORDER BY warned_at DESC LIMIT 1
            )
            """,
            (user_id, chat_id),
        )


def get_all_warnings(user_id: int, chat_id: int) -> List[Tuple]:
    with db.connection() as conn:
        return conn.execute(
            """
            SELECT reason, duration_minutes, warned_at FROM warnings
            WHERE user_id = ? AND chat_id = ? ORDER BY warned_at DESC
            """,
            (user_id, chat_id),
        ).fetchall()


# ──────────────────────────── Spam bans ────────────────────────────

def get_spam_ban_count(user_id: int, chat_id: int) -> int:
    with db.connection() as conn:
        row = conn.execute(
            "SELECT ban_count FROM spam_bans WHERE user_id = ? AND chat_id = ?",
            (user_id, chat_id),
        ).fetchone()
    return row["ban_count"] if row else 0


def increment_spam_ban(user_id: int, chat_id: int) -> int:
    with db.connection() as conn:
        existing = conn.execute(
            "SELECT id FROM spam_bans WHERE user_id = ? AND chat_id = ?",
            (user_id, chat_id),
        ).fetchone()
        if existing:
            conn.execute(
                "UPDATE spam_bans SET ban_count = ban_count + 1, last_ban_at = ? WHERE user_id = ? AND chat_id = ?",
                (datetime.now().isoformat(), user_id, chat_id),
            )
        else:
            conn.execute(
                "INSERT INTO spam_bans (user_id, chat_id, ban_count, last_ban_at) VALUES (?, ?, 1, ?)",
                (user_id, chat_id, datetime.now().isoformat()),
            )
        row = conn.execute(
            "SELECT ban_count FROM spam_bans WHERE user_id = ? AND chat_id = ?",
            (user_id, chat_id),
        ).fetchone()
    return row["ban_count"]


def reset_spam_bans(user_id: int, chat_id: int) -> None:
    with db.connection() as conn:
        conn.execute(
            "DELETE FROM spam_bans WHERE user_id = ? AND chat_id = ?",
            (user_id, chat_id),
        )


# ──────────────────────────── Chat settings ────────────────────────────

def get_chat_settings(chat_id: int) -> Dict[str, Any]:
    with db.connection() as conn:
        row = conn.execute(
            "SELECT captcha_enabled, safe_mode FROM chat_settings WHERE chat_id = ?",
            (chat_id,),
        ).fetchone()
        if not row:
            conn.execute(
                "INSERT OR IGNORE INTO chat_settings (chat_id, captcha_enabled, safe_mode, created_at) VALUES (?, 1, 0, ?)",
                (chat_id, datetime.now().isoformat()),
            )
            return {"captcha_enabled": 1, "safe_mode": 0}
    return {"captcha_enabled": row["captcha_enabled"], "safe_mode": row["safe_mode"]}


def update_chat_setting(chat_id: int, column: str, value: int) -> None:
    """SQL-safe: только колонки из whitelist."""
    if column not in ALLOWED_SETTING_COLUMNS:
        raise ValueError(f"Недопустимая настройка: {column!r}")
    with db.connection() as conn:
        conn.execute(
            f"UPDATE chat_settings SET {column} = ? WHERE chat_id = ?",
            (value, chat_id),
        )


def get_all_chat_ids() -> List[int]:
    with db.connection() as conn:
        rows = conn.execute("SELECT DISTINCT chat_id FROM chat_settings").fetchall()
    return [r["chat_id"] for r in rows]


# ──────────────────────────── Admin logs ────────────────────────────

def log_admin_action(
    chat_id: int,
    admin_id: int,
    admin_username: Optional[str],
    action: str,
    target_user_id: int = 0,
    target_username: Optional[str] = None,
    reason: Optional[str] = None,
) -> None:
    with db.connection() as conn:
        conn.execute(
            """
            INSERT INTO admin_logs
                (chat_id, admin_id, admin_username, action, target_user_id, target_username, reason, timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (chat_id, admin_id, admin_username, action, target_user_id, target_username, reason, datetime.now().isoformat()),
        )


def get_admin_logs(chat_id: int, limit: int = 20) -> List[Any]:
    with db.connection() as conn:
        return conn.execute(
            """
            SELECT admin_username, action, target_username, reason, timestamp
            FROM admin_logs WHERE chat_id = ?
            ORDER BY timestamp DESC LIMIT ?
            """,
            (chat_id, limit),
        ).fetchall()


# ──────────────────────────── Reports ────────────────────────────

def add_report(
    chat_id: int, reporter_id: int, reporter_username: Optional[str],
    reported_id: int, reported_username: Optional[str],
    reason: str, message_link: Optional[str],
    confirmation_message_id: Optional[int],
) -> int:
    with db.connection() as conn:
        cur = conn.execute(
            """
            INSERT INTO reports
                (chat_id, reporter_id, reporter_username, reported_id, reported_username,
                 reason, message_link, confirmation_message_id, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (chat_id, reporter_id, reporter_username, reported_id, reported_username,
             reason, message_link, confirmation_message_id, datetime.now().isoformat()),
        )
        report_id = cur.lastrowid
        # Обновляем статистику
        for uid, col in ((reporter_id, "reports_made"), (reported_id, "reports_received")):
            existing = conn.execute(
                "SELECT 1 FROM report_stats WHERE user_id = ? AND chat_id = ?", (uid, chat_id)
            ).fetchone()
            if existing:
                conn.execute(
                    f"UPDATE report_stats SET {col} = {col} + 1 WHERE user_id = ? AND chat_id = ?",
                    (uid, chat_id),
                )
            else:
                conn.execute(
                    f"INSERT INTO report_stats (user_id, chat_id, {col}) VALUES (?, ?, 1)",
                    (uid, chat_id),
                )
    return report_id


def get_pending_reports(chat_id: int) -> List[Any]:
    with db.connection() as conn:
        return conn.execute(
            """
            SELECT id, chat_id, reporter_username, reported_username, reason, created_at, confirmation_message_id
            FROM reports WHERE chat_id = ? AND status = 'pending' ORDER BY created_at DESC
            """,
            (chat_id,),
        ).fetchall()


def get_report_by_id(report_id: int) -> Optional[Any]:
    with db.connection() as conn:
        return conn.execute(
            """
            SELECT id, chat_id, reporter_id, reporter_username, reported_id,
                   reported_username, reason, message_link, status, created_at, confirmation_message_id
            FROM reports WHERE id = ?
            """,
            (report_id,),
        ).fetchone()


def resolve_report(report_id: int, admin_id: int, action: str) -> None:
    with db.connection() as conn:
        conn.execute(
            """
            UPDATE reports SET status='resolved', admin_id=?, admin_action=?, resolved_at=?
            WHERE id=?
            """,
            (admin_id, action, datetime.now().isoformat(), report_id),
        )


def set_report_confirmation_message_id(report_id: int, message_id: int) -> None:
    with db.connection() as conn:
        conn.execute(
            "UPDATE reports SET confirmation_message_id = ? WHERE id = ?",
            (message_id, report_id),
        )


def get_top_reporters(chat_id: int, limit: int = 10) -> List[Any]:
    with db.connection() as conn:
        return conn.execute(
            """
            SELECT rs.user_id, u.username, u.first_name, rs.reports_made
            FROM report_stats rs
            JOIN users u ON rs.user_id = u.user_id AND rs.chat_id = u.chat_id
            WHERE rs.chat_id = ? AND rs.reports_made > 0
            ORDER BY rs.reports_made DESC LIMIT ?
            """,
            (chat_id, limit),
        ).fetchall()


def get_top_reported(chat_id: int, limit: int = 10) -> List[Any]:
    with db.connection() as conn:
        return conn.execute(
            """
            SELECT rs.user_id, u.username, u.first_name, rs.reports_received
            FROM report_stats rs
            JOIN users u ON rs.user_id = u.user_id AND rs.chat_id = u.chat_id
            WHERE rs.chat_id = ? AND rs.reports_received > 0
            ORDER BY rs.reports_received DESC LIMIT ?
            """,
            (chat_id, limit),
        ).fetchall()
