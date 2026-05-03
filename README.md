# Telegram Bot — Модульная архитектура

## Структура проекта

```
bot/
├── main.py                      # Точка входа
├── requirements.txt
├── .env.example                 # Шаблон переменных окружения
├── .gitignore
│
├── config/
│   ├── __init__.py
│   └── settings.py              # Конфигурация из env-переменных, БЕЗ хардкода
│
├── database/
│   ├── __init__.py
│   ├── connection.py            # Thread-safe пул соединений + context manager
│   ├── init.py                  # Создание таблиц
│   └── repositories.py         # Все запросы к БД (SQL-safe whitelist для колонок)
│
├── posting/
│   ├── __init__.py
│   ├── state.py                 # PostingState — замена глобальных переменных
│   │                            # pending_posts защищён asyncio.Lock
│   ├── llm.py                   # Очистка текста через g4f
│   └── sender.py                # Отправка постов через Telethon
│
├── captcha/
│   ├── __init__.py
│   └── captcha.py               # Генерация капчи + CaptchaStorage с TTL
│
├── moderation/
│   ├── __init__.py
│   ├── states.py                # FSM-состояния модерации
│   ├── antispam.py              # SpamTracker + MessageHistory (нет утечек памяти)
│   ├── commands.py              # /warn /ban /mute /report etc.
│   └── events.py                # Вход/выход пользователей, антиспам в группах
│
├── menu/
│   ├── __init__.py
│   ├── states.py                # FSM-состояния меню (PostingFSM)
│   ├── keyboards.py             # Все inline/reply клавиатуры
│   ├── handlers.py              # Главное меню, постинг, авторизация (FSM)
│   └── moderation_handlers.py  # Меню модерации (настройки, логи, репорты, пользователи)
│
├── workers/
│   ├── __init__.py
│   ├── aiogram_worker.py        # Регистрация роутеров, polling
│   └── telethon_worker.py       # Userbot, чтение источников, bounded кэш ID
│
└── utils/
    ├── __init__.py
    ├── bot_ref.py               # Глобальная ссылка на Bot instance
    ├── helpers.py               # parse_time, is_admin, get_target_user, format_time
    └── git_update.py            # git pull/restart
```

## Запуск

```bash
# 1. Установить зависимости
pip install -r requirements.txt

# 2. Создать .env из шаблона
cp .env.example .env
# Заполнить BOT_TOKEN, API_ID, API_HASH, ADMIN_IDS

# 3. Запустить
python main.py
```

## Исправленные проблемы оригинала

| # | Проблема | Решение |
|---|----------|---------|
| 1 | Секреты захардкожены в коде | `config/settings.py` — только из `.env` |
| 2 | SQL-инъекции через f-строки колонок | Whitelist `ALLOWED_STAT_COLUMNS` / `ALLOWED_SETTING_COLUMNS` |
| 3 | Монолит 3865 строк | 15 модулей по ответственностям |
| 4 | Глобальные множества `waiting_for_*` | FSM (`PostingFSM`, `ModerationFSM`) |
| 5 | Множественные `sqlite3.connect()` без пула | `DatabasePool` с thread-local + `contextmanager` |
| 6 | Утечка памяти `processed_message_ids` | `deque(maxlen=10_000)` + зеркальный `set` |
| 7 | Race conditions `pending_posts.pop(idx)` | `asyncio.Lock` в `PostingState` |
| 8 | `remove_user()` удалял из ВСЕХ чатов | `remove_user(user_id, chat_id)` — только из нужного |
| 9 | Капча: отрицательные ответы не попадали | Убрано `wrong >= 0`, диапазон `±10` |
| 10 | `_links_edit_idx` / `_auth_code_buffer` растут бесконечно | Данные в `FSMContext` (очищаются при `state.clear()`) |
| 11 | `CaptchaStorage` — бесконечный dict | TTL-хранилище с автоочисткой |
| 12 | `SpamTracker` — глобальный dict без очистки | `SpamTracker.cleanup_expired()` каждые 5 мин |
