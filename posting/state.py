"""
posting/state.py

Заменяет глобальные переменные sources, target_chat, PROMPT, pending_posts,
signature_links на инкапсулированный класс с явным API.

pending_posts защищён asyncio.Lock — нет race conditions при pop().
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_CONFIG_FILE = "config.json"
_SOURCES_FILE = "sources.json"
_TARGET_FILE = "target.json"
_LINKS_FILE = "links.json"

DEFAULT_PROMPT = (
    "Перепиши этот текст для публикации в Telegram-канале по правилам:\n"
    "— Удали все ссылки, упоминания, имена чатов, призывы подписаться, рекламу, хэштеги.\n"
    "— Перескажи своими словами, сохраняя суть и факты, не добавляй ничего нового.\n"
    "— Где уместно, вставь шаблоны: [ССЫЛКА НА НАШ ЧАТ], [ССЫЛКА НАШ КАНАЛ], [ОПИСАНИЕ ИЗ НАШЕГО БРЕНДА].\n"
    "— Только чистый текст поста для публикации, без пояснений, без повторения правил, без оформления.\n"
    "— Всегда пиши только на русском языке.\n"
    "— Не добавляй никаких пометок, пояснений, комментариев, только готовый текст поста.\n\n"
    "Текст:\n{text}\n\nОтветь только готовым текстом поста."
)


@dataclass
class PostEntry:
    clean_text: str
    media: Any = None
    source_event: Any = None
    source_message: Any = None
    video_bytes: Optional[bytes] = None
    status: str = "pending"
    aiogram_message_ids: List[int] = field(default_factory=list)
    edit_prompt_message_id: Optional[int] = None


class PostingState:
    def __init__(self) -> None:
        self.prompt: str = DEFAULT_PROMPT
        self.sources: List[str] = []
        self.target_chat: Optional[str] = None
        self.signature_links: List[Dict[str, str]] = [
            {"label": "НАШ ЧАТ", "url": "https://t.me/example_chat"},
            {"label": "НАША ГРУППА", "url": "https://t.me/example_channel"},
        ]
        self._posts: List[PostEntry] = []
        self._lock = asyncio.Lock()

    # ── Posts (thread-safe через Lock) ──

    async def add_post(self, post: PostEntry) -> int:
        async with self._lock:
            self._posts.append(post)
            return len(self._posts) - 1

    async def get_post(self, idx: int) -> Optional[PostEntry]:
        async with self._lock:
            if 0 <= idx < len(self._posts):
                return self._posts[idx]
        return None

    async def remove_post(self, idx: int) -> Optional[PostEntry]:
        """Безопасное удаление по индексу."""
        async with self._lock:
            if 0 <= idx < len(self._posts):
                return self._posts.pop(idx)
        return None

    async def pending_posts(self) -> List[tuple[int, PostEntry]]:
        async with self._lock:
            return [(i, p) for i, p in enumerate(self._posts) if p.status == "pending"]

    async def pending_count(self) -> int:
        async with self._lock:
            return sum(1 for p in self._posts if p.status == "pending")

    # ── Persistence ──

    def load_all(self) -> None:
        self._load_config()
        self._load_sources()
        self._load_target()
        self._load_links()

    def _load_config(self) -> None:
        if os.path.exists(_CONFIG_FILE):
            try:
                with open(_CONFIG_FILE, "r", encoding="utf-8") as f:
                    self.prompt = json.load(f).get("PROMPT", DEFAULT_PROMPT)
            except Exception as exc:
                logger.warning("config.json: %s", exc)

    def _load_sources(self) -> None:
        if os.path.exists(_SOURCES_FILE):
            try:
                with open(_SOURCES_FILE, "r", encoding="utf-8") as f:
                    self.sources = json.load(f)
            except Exception as exc:
                logger.warning("sources.json: %s", exc)

    def _load_target(self) -> None:
        if os.path.exists(_TARGET_FILE):
            try:
                with open(_TARGET_FILE, "r", encoding="utf-8") as f:
                    self.target_chat = json.load(f).get("target_chat")
            except Exception as exc:
                logger.warning("target.json: %s", exc)

    def _load_links(self) -> None:
        if os.path.exists(_LINKS_FILE):
            try:
                with open(_LINKS_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if "signature_links" in data:
                    self.signature_links = data["signature_links"]
                else:
                    # Обратная совместимость со старым форматом
                    links = []
                    if data.get("chat_link"):
                        links.append({"label": "НАШ ЧАТ", "url": data["chat_link"]})
                    if data.get("channel_link"):
                        links.append({"label": "НАША ГРУППА", "url": data["channel_link"]})
                    if links:
                        self.signature_links = links
            except Exception as exc:
                logger.warning("links.json: %s", exc)

    def save_config(self) -> None:
        with open(_CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump({"PROMPT": self.prompt}, f, ensure_ascii=False, indent=2)

    def save_sources(self) -> None:
        with open(_SOURCES_FILE, "w", encoding="utf-8") as f:
            json.dump(self.sources, f, ensure_ascii=False, indent=2)

    def save_target(self) -> None:
        with open(_TARGET_FILE, "w", encoding="utf-8") as f:
            json.dump({"target_chat": self.target_chat}, f, ensure_ascii=False, indent=2)

    def save_links(self) -> None:
        with open(_LINKS_FILE, "w", encoding="utf-8") as f:
            json.dump({"signature_links": self.signature_links}, f, ensure_ascii=False, indent=2)

    def reload_sources(self) -> None:
        """Перечитать источники (вызывается периодически в telethon-воркере)."""
        self._load_sources()


# Единственный экземпляр
posting_state = PostingState()
