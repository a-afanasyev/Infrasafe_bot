"""A11-CODE-02: бюджет LLM-вызовов news-watch.

Без лимита каждое сообщение канала, прошедшее префильтр по подстрокам, шло в
LLM (и ещё раз — повтором на транзиентном сбое): флуд в публичном канале
выжигал счёт провайдера и упирал общий ключ в 429, от которого страдал и
ИИ-триаж заявок. Ключ ГЛОБАЛЬНЫЙ — один бюджет на все uvicorn-воркеры API.
Механизм — общий оконный счётчик Group Intake (INCR + TTL одной Lua-операцией).
"""
from __future__ import annotations

from uk_management_bot.config.settings import settings
from uk_management_bot.services.group_intake.pending import window_allowed

KEY = "nw:llm"
WINDOW_SECONDS = 60


async def news_watch_llm_allowed() -> bool:
    """Можно ли сделать ещё один платный LLM-вызов. Redis недоступен → False."""
    return await window_allowed(KEY, settings.NEWS_WATCH_LLM_PER_MINUTE, WINDOW_SECONDS)
