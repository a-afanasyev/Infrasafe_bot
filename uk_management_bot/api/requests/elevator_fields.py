"""Поля лифта на ``RequestCard`` (Ф4a-1): подпись и статус — без N+1.

Один batch-запрос лифтов (с домами) на страницу карточек; подпись — единая
``elevator_label`` из домена. Используется роутерами заявок и колл-центра.
Никакого relationship на ``Request``: в async-сессии lazy-load невозможен,
явный словарь ``{id: Elevator}`` не даёт случайно наступить на него.
"""

from __future__ import annotations

from collections.abc import Iterable

from sqlalchemy.ext.asyncio import AsyncSession

from uk_management_bot.api.requests.schemas import RequestCard
from uk_management_bot.database.models.elevator import Elevator
from uk_management_bot.services.elevator_service import (
    elevator_label,
    get_elevators_by_ids_async,
)

DEFAULT_LANGUAGE = "ru"


def card_language(user) -> str:
    """Язык подписи лифта — язык пользователя API (``ru`` по умолчанию)."""
    return getattr(user, "language", None) or DEFAULT_LANGUAGE


async def load_elevators(db: AsyncSession, requests: Iterable) -> dict[int, Elevator]:
    """``{elevator_id: Elevator}`` для набора заявок одним запросом (пусто — без запроса)."""
    ids = {r.elevator_id for r in requests if r.elevator_id is not None}
    return await get_elevators_by_ids_async(db, ids)


def attach_elevator(card: RequestCard, elevator: Elevator | None, language: str) -> RequestCard:
    """Новая карточка с ``elevator_label``/``elevator_status``; без лифта — та же карточка."""
    if elevator is None:
        return card
    return card.model_copy(update={
        "elevator_label": elevator_label(elevator, language),
        "elevator_status": elevator.current_status,
    })


async def card_with_elevator(db: AsyncSession, req, *, language: str) -> RequestCard:
    """Карточка одной свежесозданной заявки с полями лифта (ответ POST)."""
    elevators = await load_elevators(db, [req])
    return attach_elevator(RequestCard.model_validate(req), elevators.get(req.elevator_id), language)
