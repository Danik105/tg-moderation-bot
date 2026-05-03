"""
menu/keyboards.py — Все inline-клавиатуры главного меню.
"""
from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton


def main_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📢 Постинг", callback_data="section_posting")],
        [InlineKeyboardButton(text="🛡 Модерация", callback_data="section_moderation")],
        [InlineKeyboardButton(text="⚙️ Система", callback_data="section_system")],
        [InlineKeyboardButton(text="📖 Справка", callback_data="section_help")],
    ])


def posting_menu(pending_count: int = 0) -> InlineKeyboardMarkup:
    posts_text = f"📄 Посты ({pending_count} шт.)"
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📝 Промпт", callback_data="prompt"),
            InlineKeyboardButton(text="📚 Источники", callback_data="sources"),
        ],
        [
            InlineKeyboardButton(text="👥 Целевая группа", callback_data="target_group"),
            InlineKeyboardButton(text=posts_text, callback_data="posts"),
        ],
        [
            InlineKeyboardButton(text="🔗 Ссылки подписи", callback_data="links"),
            InlineKeyboardButton(text="📱 TG Аккаунт", callback_data="tg_auth"),
        ],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_main")],
    ])


def moderation_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="⚙️ Настройки", callback_data="mod_settings"),
            InlineKeyboardButton(text="📋 Репорты", callback_data="back_to_reports_menu"),
        ],
        [
            InlineKeyboardButton(text="📊 Логи", callback_data="mod_logs"),
            InlineKeyboardButton(text="🆘 Безопасный режим", callback_data="mod_safe_mode"),
        ],
        [
            InlineKeyboardButton(text="👥 Пользователи", callback_data="mod_users"),
            InlineKeyboardButton(text="📋 Команды", callback_data="mod_commands"),
        ],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_main")],
    ])


def system_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🔄 Обновить меню", callback_data="refresh"),
            InlineKeyboardButton(text="⬆️ Обновить бота", callback_data="bot_update"),
        ],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_main")],
    ])


def reply_main_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🏠 Главное меню"), KeyboardButton(text="📄 Посты")],
            [KeyboardButton(text="📋 Репорты"), KeyboardButton(text="📊 Логи")],
            [KeyboardButton(text="👥 Пользователи"), KeyboardButton(text="⚙️ Настройки")],
        ],
        resize_keyboard=True,
    )


def sources_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Добавить группу", callback_data="add_group")],
        [InlineKeyboardButton(text="➖ Удалить группу", callback_data="remove_group")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_main")],
    ])


def remove_group_menu(sources: list[str]) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=f"❌ {src}", callback_data=f"delgroup_{idx}")]
        for idx, src in enumerate(sources)
    ]
    rows.append([InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_main")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def links_menu(signature_links: list[dict]) -> InlineKeyboardMarkup:
    rows = []
    for idx, lnk in enumerate(signature_links):
        rows.append([
            InlineKeyboardButton(text=f"✏️ {lnk['label']}", callback_data=f"link_edit_{idx}"),
            InlineKeyboardButton(text="🗑", callback_data=f"link_del_{idx}"),
        ])
    rows.append([InlineKeyboardButton(text="➕ Добавить кнопку", callback_data="link_add")])
    rows.append([InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_main")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def back_button(callback_data: str = "back_to_main") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ Назад", callback_data=callback_data)]
    ])


def settings_keyboard(chat_id: int, captcha_enabled: bool) -> InlineKeyboardMarkup:
    cap_text = "✅ Капча: включена" if captcha_enabled else "❌ Капча: выключена"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=cap_text, callback_data=f"toggle_captcha_{chat_id}")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="mod_settings")],
    ])


def safe_mode_keyboard(chat_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🔒 Включить", callback_data=f"safe_mode_on_{chat_id}"),
            InlineKeyboardButton(text="🔓 Выключить", callback_data=f"safe_mode_off_{chat_id}"),
        ],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="mod_safe_mode")],
    ])


def reports_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📋 Активные репорты", callback_data="reports_active")],
        [InlineKeyboardButton(text="📊 Статистика репортов", callback_data="reports_stats")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_main")],
    ])


def report_action_keyboard(report_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="⚠️ Варн", callback_data=f"report_warn_{report_id}"),
            InlineKeyboardButton(text="🔇 Мут", callback_data=f"report_mute_{report_id}"),
        ],
        [
            InlineKeyboardButton(text="🔨 Бан", callback_data=f"report_ban_{report_id}"),
            InlineKeyboardButton(text="✅ Закрыть", callback_data=f"report_close_{report_id}"),
        ],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="reports_active")],
    ])


def numpad_keyboard(current_code: str = "") -> InlineKeyboardMarkup:
    """Цифровая клавиатура для ввода кода авторизации."""
    rows = []
    for row in [["1", "2", "3"], ["4", "5", "6"], ["7", "8", "9"], ["⌫", "0", "✅"]]:
        rows.append([InlineKeyboardButton(text=d, callback_data=f"numpad_{d}") for d in row])
    return InlineKeyboardMarkup(inline_keyboard=rows)
