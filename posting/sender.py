"""
posting/sender.py — Отправка постов через Telethon-клиент.
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from telethon.tl.types import MessageMediaPhoto, MessageMediaDocument

from posting.state import posting_state, PostEntry

if TYPE_CHECKING:
    from telethon import TelegramClient

logger = logging.getLogger(__name__)


def _safe_target_chat():
    t = posting_state.target_chat
    if not t:
        raise ValueError("Целевая группа не задана.")
    t = str(t).strip()
    if t.startswith("@"):
        return t
    if t.lstrip("-").isdigit():
        return int(t)
    return "@" + t


async def send_post(client: "TelegramClient", post: PostEntry, *, with_media: bool = True) -> None:
    chat = _safe_target_chat()
    text = post.clean_text

    # Подпись
    if posting_state.signature_links:
        sig = " | ".join(
            f'<a href="{lnk["url"]}">{lnk["label"]}</a>'
            for lnk in posting_state.signature_links
        )
        text = text + "\n\n" + sig

    media = post.media if with_media else None

    if media and isinstance(media, MessageMediaPhoto):
        caption = text[:1024]
        await client.send_message(chat, caption, file=media, parse_mode="html", supports_streaming=True)
        if len(text) > 1024:
            for i in range(1024, len(text), 4096):
                await client.send_message(chat, text[i : i + 4096], parse_mode="html")
    elif media and isinstance(media, MessageMediaDocument):
        caption = text[:1024]
        await client.send_message(chat, caption, file=media, parse_mode="html", supports_streaming=True)
        if len(text) > 1024:
            for i in range(1024, len(text), 4096):
                await client.send_message(chat, text[i : i + 4096], parse_mode="html")
    else:
        for i in range(0, len(text), 4096):
            await client.send_message(chat, text[i : i + 4096], parse_mode="html")
