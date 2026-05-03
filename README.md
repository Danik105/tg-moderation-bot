# 🤖 Telegram Moderation Bot

<div align="center">

![Python](https://img.shields.io/badge/Python-3.10%2B-blue?style=for-the-badge&logo=python&logoColor=white)
![aiogram](https://img.shields.io/badge/aiogram-3.x-blue?style=for-the-badge)
![Telethon](https://img.shields.io/badge/Telethon-1.36%2B-blue?style=for-the-badge)
![SQLite](https://img.shields.io/badge/SQLite-3-lightgrey?style=for-the-badge&logo=sqlite)
![License](https://img.shields.io/badge/License-MIT-green?style=for-the-badge)
![Tests](https://img.shields.io/badge/Tests-101%20passed-brightgreen?style=for-the-badge)

**A production-ready, modular Telegram bot for automated community management.**  
Captcha verification · Anti-spam · Full moderation toolkit · LLM-powered auto-posting · Live Git updates

</div>

---

## 📋 Table of Contents

- [Overview](#-overview)
- [Features](#-features)
- [Architecture](#-architecture)
- [Project Structure](#-project-structure)
- [Getting Started](#-getting-started)
- [Configuration](#-configuration)
- [How It Works](#-how-it-works)
- [Testing](#-testing)
- [Bug Fixes & Improvements](#-bug-fixes--improvements)
- [Tech Stack](#-tech-stack)

---

## 🌟 Overview

This bot was developed as a graduation project and represents a complete rewrite of a monolithic 3865-line Telegram bot into a clean, modular architecture. Every component has a single responsibility, secrets are loaded from environment variables only, and all critical bugs from the original codebase have been identified and fixed.

The bot operates in two modes simultaneously:
- **Bot mode** (aiogram) — handles commands, menus, moderation actions, and user interactions
- **Userbot mode** (Telethon) — monitors source channels and forwards new posts for review

---

## ✨ Features

### 🛡️ Member Verification
- Math captcha on join (addition, subtraction, multiplication)
- Configurable timeout — user is kicked if they don't solve it in time
- TTL-based captcha storage — no memory leaks
- Supports negative answers (original bug fixed)

### 🚫 Anti-Spam
- Sliding window algorithm — detects message floods in real time
- Automatic mute with escalating duration on repeat violations
- Per-user message history with 24-hour TTL
- Periodic cleanup of expired entries — no unbounded memory growth

### ⚖️ Moderation Tools
| Command | Description |
|---------|-------------|
| `/warn` | Issue a warning to a user |
| `/ban` | Ban a user from the chat |
| `/mute` | Temporarily restrict a user |
| `/unmute` | Remove mute restriction |
| `/unwarn` | Remove a warning |
| `/report` | Report a message to admins |
| `/stats` | View user statistics |

### 📢 Auto-Posting
- Monitors multiple Telegram source channels via Telethon userbot
- LLM-powered text rewriting (via g4f) — removes ads, links, watermarks
- Admin approval queue — every post is reviewed before publishing
- Configurable prompt, signature links, and target channel
- Thread-safe pending post queue protected by `asyncio.Lock`

### 🔄 Live Updates
- Check for new commits directly from the bot menu
- One-click `git pull` + automatic restart — no server access required
- Shows recent commit log before updating

### 🗄️ Admin Menu
Full inline keyboard interface for:
- Moderation settings (captcha on/off, safe mode)
- Viewing reports and logs
- Managing users and warnings
- Posting configuration
- System updates

---

## 🏗️ Architecture

The project is split into **8 independent packages**, each with a single responsibility:

```
┌─────────────────────────────────────────────────────┐
│                      main.py                        │
│              (entry point, startup)                 │
└──────────┬──────────────────────────┬───────────────┘
           │                          │
    ┌──────▼──────┐           ┌───────▼───────┐
    │   aiogram   │           │   Telethon    │
    │   worker    │           │   worker      │
    │  (bot API)  │           │  (userbot)    │
    └──────┬──────┘           └───────┬───────┘
           │                          │
    ┌──────▼──────────────────────────▼───────┐
    │                  menu/                  │
    │     handlers · keyboards · states       │
    └──────┬──────────────────────────────────┘
           │
    ┌──────▼────────────────────────────────────────┐
    │  moderation/   captcha/   posting/   utils/   │
    │  antispam     captcha     state      helpers  │
    │  commands     storage     llm        git      │
    │  events                   sender              │
    └──────┬────────────────────────────────────────┘
           │
    ┌──────▼──────┐     ┌──────────────┐
    │  database/  │     │   config/    │
    │  pool       │     │   settings   │
    │  repos      │     │   (.env)     │
    └─────────────┘     └──────────────┘
```

---

## 📁 Project Structure

```
bot/
├── main.py                      # Entry point — starts both workers
├── requirements.txt             # Dependencies
├── .env.example                 # Environment variables template
│
├── config/
│   └── settings.py              # All config from env vars — zero hardcoded secrets
│
├── database/
│   ├── connection.py            # Thread-safe SQLite pool + context manager
│   ├── init.py                  # Schema creation
│   └── repositories.py         # All DB queries — SQL-injection-safe column whitelist
│
├── posting/
│   ├── state.py                 # PostingState — replaces global variables
│   │                            # pending_posts protected by asyncio.Lock
│   ├── llm.py                   # Text cleanup via g4f LLM
│   └── sender.py                # Post delivery via Telethon
│
├── captcha/
│   └── captcha.py               # Math captcha generator + TTL storage
│
├── moderation/
│   ├── antispam.py              # SpamTracker + MessageHistory (no memory leaks)
│   ├── commands.py              # /warn /ban /mute /report and more
│   └── events.py                # Join/leave handlers, group anti-spam
│
├── menu/
│   ├── keyboards.py             # All inline/reply keyboards
│   ├── handlers.py              # Main menu, posting, auth (FSM)
│   └── moderation_handlers.py  # Moderation menu — settings, logs, reports
│
├── workers/
│   ├── aiogram_worker.py        # Router registration, polling
│   └── telethon_worker.py       # Userbot, source monitoring, bounded ID cache
│
├── utils/
│   ├── helpers.py               # parse_time, is_admin, get_target_user
│   ├── bot_ref.py               # Global Bot instance reference
│   └── git_update.py            # git pull / restart utilities
│
└── test/
    ├── test_captcha.py          # 22 tests
    ├── test_antispam.py         # 24 tests
    ├── test_posting_state.py    # 21 tests
    ├── test_database.py         # 21 tests
    └── test_settings.py         # 13 tests
```

---

## 🚀 Getting Started

### Prerequisites

- Python 3.10 or higher
- Git
- A Telegram bot token from [@BotFather](https://t.me/BotFather)
- Telegram API credentials from [my.telegram.org](https://my.telegram.org)

### Installation

**1. Clone the repository**
```bash
git clone https://github.com/YOUR_USERNAME/telegram-moderation-bot.git
cd telegram-moderation-bot
```

**2. Install dependencies**
```bash
pip install -r requirements.txt
```

**3. Set up environment variables**
```bash
cp .env.example .env
```
Edit `.env` and fill in your credentials (see [Configuration](#-configuration)).

**4. Run the bot**
```bash
python main.py
```

On first run, Telethon will ask you to log in to your Telegram account — enter your phone number and the confirmation code.

---

## ⚙️ Configuration

Copy `.env.example` to `.env` and fill in the values:

```env
# Telegram Bot token — get from @BotFather
BOT_TOKEN=your_bot_token_here

# Telethon API credentials — get from my.telegram.org
API_ID=12345678
API_HASH=your_api_hash_here

# Admin user IDs (comma-separated)
ADMIN_IDS=123456789,987654321
```

> ⚠️ **Never commit `.env` to Git.** It is already listed in `.gitignore`.

### Optional settings (in `config/settings.py`)

| Parameter | Default | Description |
|-----------|---------|-------------|
| `captcha_timeout` | `60` | Seconds before unverified user is kicked |
| `spam_time_window` | `5` | Sliding window size in seconds |
| `spam_message_limit` | `5` | Max messages in window before mute |
| `message_history_duration` | `86400` | Message history TTL in seconds (24h) |
| `processed_ids_max_size` | `10000` | Max cached message IDs in Telethon worker |

---

## 🔍 How It Works

### Captcha Flow
```
User joins group
      │
      ▼
Bot sends math question + 4 answer buttons
      │
   ┌──▼──────────────────────┐
   │  Correct answer?         │
   └──┬──────────────────────┘
      │ Yes              │ No / Timeout
      ▼                  ▼
  Verified ✅       Kick from group ❌
```

### Anti-Spam Flow
```
User sends message
      │
      ▼
SpamTracker.record_message()
      │
  ┌───▼────────────────────────┐
  │  Messages in window >= 5?  │
  └───┬────────────────────────┘
      │ Yes              │ No
      ▼                  ▼
Mute + increment       Allow ✅
violations counter
      │
  violations >= 3?
      │ Yes
      ▼
   Auto-ban 🔨
```

### Auto-Posting Flow
```
Telethon monitors source channels
      │
New post detected
      │
      ▼
LLM rewrites text (removes ads, links, watermarks)
      │
      ▼
Post sent to admin approval queue
      │
      ▼
Admin reviews in bot menu → Publish / Edit / Reject
      │
      ▼
Published to target channel 📢
```

---

## 🧪 Testing

The project includes **101 unit and integration tests** covering all core modules.

### Run all tests
```bash
python -m pytest test -v
```

### Test coverage by module

| File | Tests | Coverage |
|------|-------|----------|
| `test_captcha.py` | 22 | `generate_captcha`, `create_captcha_keyboard`, `CaptchaStorage` |
| `test_antispam.py` | 24 | `SpamTracker`, `MessageHistory` |
| `test_posting_state.py` | 21 | `PostingState`, `PostEntry`, persistence |
| `test_database.py` | 21 | `DatabasePool`, `_DbProxy`, repositories |
| `test_settings.py` | 13 | `_require`, credentials, `Settings` |
| **Total** | **101** | |

### Example output
```
collected 101 items

test/test_antispam.py::TestSpamTracker::test_spam_at_limit PASSED
test/test_captcha.py::TestCaptchaStorage::test_ttl_expired_returns_none PASSED
test/test_database.py::TestRepositoriesWithRealDB::test_remove_user_only_from_specific_chat PASSED
...
101 passed in 4.2s
```

---

## 🔧 Bug Fixes & Improvements

This project is a complete refactor of the original monolithic bot. Here are the key issues that were identified and resolved:

| # | Original Problem | Solution |
|---|-----------------|----------|
| 1 | Secrets hardcoded in source code | `config/settings.py` — loaded from `.env` only |
| 2 | SQL injection via f-string column names | `ALLOWED_STAT_COLUMNS` / `ALLOWED_SETTING_COLUMNS` whitelist |
| 3 | Single file with 3865 lines | Split into 15 modules by responsibility |
| 4 | Global `waiting_for_*` sets for state | FSM via `PostingFSM` / `ModerationFSM` |
| 5 | Multiple bare `sqlite3.connect()` calls | `DatabasePool` with thread-local connections + context manager |
| 6 | `processed_message_ids` grew forever | `deque(maxlen=10_000)` + mirrored `set` |
| 7 | Race condition on `pending_posts.pop(idx)` | `asyncio.Lock` in `PostingState` |
| 8 | `remove_user()` deleted from ALL chats | Added `chat_id` parameter — deletes from specific chat only |
| 9 | Captcha: negative correct answers never appeared | Removed `wrong >= 0` guard, range expanded to `±10` |
| 10 | `_links_edit_idx` / `_auth_code_buffer` grew unbounded | Stored in `FSMContext` — cleared on `state.clear()` |
| 11 | `CaptchaStorage` was an unbounded dict | TTL storage with automatic cleanup on every `set()` |
| 12 | `SpamTracker` was a global dict with no cleanup | `cleanup_expired()` called every 5 minutes |

---

## 🛠️ Tech Stack

| Technology | Purpose |
|------------|---------|
| [Python 3.10+](https://python.org) | Core language |
| [aiogram 3.x](https://docs.aiogram.dev) | Telegram Bot API framework |
| [Telethon](https://docs.telethon.dev) | Telegram MTProto client (userbot) |
| [SQLite](https://sqlite.org) | Local database |
| [g4f](https://github.com/xtekky/gpt4free) | Free LLM API for text rewriting |
| [python-dotenv](https://pypi.org/project/python-dotenv/) | Environment variable loading |
| [pytest](https://pytest.org) | Testing framework |

---

## 📄 License

This project is licensed under the MIT License.

---

<div align="center">
  Developed as a graduation project · 2025
</div>
