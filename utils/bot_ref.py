"""
utils/bot_ref.py

Единственный экземпляр aiogram.Bot, разделяемый между модулями.
Устанавливается в aiogram_worker перед запуском polling.
"""
from __future__ import annotations
from typing import Optional
from aiogram import Bot

bot: Optional[Bot] = None


def set_bot(instance: Bot) -> None:
    global bot
    bot = instance
